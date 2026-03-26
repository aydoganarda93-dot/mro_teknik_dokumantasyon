"""PDF ayrıştırma motoru — PyMuPDF ile metin, tablo ve metadata çıkarma.

Havacılık teknik dokümanlarının karmaşık düzenlerini (çok sütun, tablolar,
header/footer tekrarları) işler.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import pymupdf  # PyMuPDF >= 1.24

from mro.mro_domain import detect_doc_type, extract_effectivity, extract_revision


@dataclass
class PageContent:
    """Tek bir sayfadan çıkarılan ham içerik."""
    page_number: int
    text: str
    tables: list[list[list[str]]] = field(default_factory=list)
    image_count: int = 0
    figure_refs: list[str] = field(default_factory=list)


@dataclass
class ProcessedDocument:
    """Tamamen işlenmiş bir PDF dokümanı."""
    doc_id: str
    source_file: str
    doc_type: Optional[str]
    revision: Optional[str]
    effectivity: Optional[str]
    total_pages: int
    pages: list[PageContent]
    full_text: str
    tables_markdown: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Sabit regex'ler ──────────────────────────────────────────────────────────

_FIGURE_REF_RE = re.compile(
    r'\b(?:Fig(?:ure|ür)?|Şekil)[.\s]*(\d+[A-Z]?(?:[.-]\d+)?)\b',
    re.IGNORECASE,
)

_HEADER_FOOTER_THRESHOLD = 60  # karakter — tekrar eden kısa satırlar header/footer


def _generate_doc_id(file_path: str, content_hash: str) -> str:
    """Dosya adı + içerik hash'inden benzersiz doc_id üret."""
    name = Path(file_path).stem
    short_hash = content_hash[:8]
    return f"{name}_{short_hash}"


def _merge_multicolumn_blocks(blocks: list[dict], page_width: float) -> str:
    """Çok sütunlu blokları soldan sağa, yukarıdan aşağıya birleştir.

    PyMuPDF dict modundaki bloklar (x0, y0, x1, y1) koordinatlarına sahiptir.
    Sütun tespiti: sayfa genişliğinin ortasına yakın bloklar farklı sütunlardır.
    """
    text_blocks = []
    for b in blocks:
        if b.get("type") != 0:  # sadece metin blokları
            continue
        lines_text = []
        for line in b.get("lines", []):
            spans_text = "".join(s.get("text", "") for s in line.get("spans", []))
            if spans_text.strip():
                lines_text.append(spans_text)
        if lines_text:
            text_blocks.append({
                "x0": b["bbox"][0],
                "y0": b["bbox"][1],
                "x1": b["bbox"][2],
                "y1": b["bbox"][3],
                "text": "\n".join(lines_text),
            })

    if not text_blocks:
        return ""

    # Sütun tespiti: x0 < sayfa_genişliği/2 → sol sütun, değilse sağ sütun
    mid_x = page_width / 2
    left_blocks = [b for b in text_blocks if b["x0"] < mid_x - 20]
    right_blocks = [b for b in text_blocks if b["x0"] >= mid_x - 20]

    # Tek sütunluysa veya sağ sütun boşsa basit sıralama
    if not right_blocks or not left_blocks:
        text_blocks.sort(key=lambda b: (b["y0"], b["x0"]))
        return "\n\n".join(b["text"] for b in text_blocks)

    # Çok sütun: önce sol, sonra sağ (aynı y-bandında)
    left_blocks.sort(key=lambda b: b["y0"])
    right_blocks.sort(key=lambda b: b["y0"])

    merged = []
    for b in left_blocks:
        merged.append(b["text"])
    for b in right_blocks:
        merged.append(b["text"])

    return "\n\n".join(merged)


def _extract_tables_as_markdown(page) -> list[str]:
    """Sayfadaki tabloları markdown formatında çıkar."""
    markdown_tables = []
    try:
        tables = page.find_tables()
        for table in tables:
            data = table.extract()
            if not data or len(data) < 2:
                continue

            # Header satırı
            header = data[0]
            header_cells = [str(c) if c else "" for c in header]
            md = "| " + " | ".join(header_cells) + " |\n"
            md += "| " + " | ".join(["---"] * len(header_cells)) + " |\n"

            # Veri satırları
            for row in data[1:]:
                cells = [str(c) if c else "" for c in row]
                # Hücre sayısını header ile eşitle
                while len(cells) < len(header_cells):
                    cells.append("")
                md += "| " + " | ".join(cells[:len(header_cells)]) + " |\n"

            markdown_tables.append(md.strip())
    except Exception:
        pass

    return markdown_tables


def _detect_header_footer(pages_text: list[str]) -> set[str]:
    """Tekrar eden kısa satırları (header/footer) tespit et."""
    if len(pages_text) < 3:
        return set()

    line_counts: dict[str, int] = {}
    for text in pages_text:
        seen_in_page: set[str] = set()
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped and len(stripped) < _HEADER_FOOTER_THRESHOLD and stripped not in seen_in_page:
                seen_in_page.add(stripped)
                line_counts[stripped] = line_counts.get(stripped, 0) + 1

    threshold = max(3, len(pages_text) * 0.6)
    return {line for line, count in line_counts.items() if count >= threshold}


def _extract_figure_refs(text: str) -> list[str]:
    """Metinden figür referanslarını çıkar."""
    return list(set(m.group(0) for m in _FIGURE_REF_RE.finditer(text)))


def _remove_header_footer_lines(text: str, hf_lines: set[str]) -> str:
    """Header/footer satırlarını metinden çıkar."""
    if not hf_lines:
        return text
    cleaned = []
    for line in text.split("\n"):
        if line.strip() not in hf_lines:
            cleaned.append(line)
    return "\n".join(cleaned)


def process_pdf(pdf_path: str | Path) -> ProcessedDocument:
    """PDF dosyasını tamamen işle ve ProcessedDocument döndür.

    Args:
        pdf_path: PDF dosyasının yolu

    Returns:
        ProcessedDocument: İşlenmiş doküman verisi
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF bulunamadı: {pdf_path}")

    doc = pymupdf.open(str(pdf_path))

    # İçerik hash'i
    raw_bytes = pdf_path.read_bytes()
    content_hash = hashlib.sha256(raw_bytes).hexdigest()

    # Her sayfadan ham metin çıkar (header/footer tespiti için)
    raw_page_texts: list[str] = []
    for page in doc:
        raw_page_texts.append(page.get_text("text"))

    # Header/footer tespiti
    hf_lines = _detect_header_footer(raw_page_texts)

    # Her sayfayı detaylı işle
    pages: list[PageContent] = []
    all_tables_md: list[str] = []

    for page_idx, page in enumerate(doc):
        page_width = page.rect.width

        # Blok tabanlı metin çıkarma (sütun desteği)
        blocks_data = page.get_text("dict")["blocks"]
        merged_text = _merge_multicolumn_blocks(blocks_data, page_width)

        # Header/footer temizleme
        cleaned_text = _remove_header_footer_lines(merged_text, hf_lines)

        # Tablo çıkarma
        tables_md = _extract_tables_as_markdown(page)
        all_tables_md.extend(tables_md)

        # Tablo verilerini raw list olarak da sakla
        raw_tables = []
        try:
            for table in page.find_tables():
                raw_tables.append(table.extract())
        except Exception:
            pass

        # Görsel sayısı ve figür referansları
        image_count = len(page.get_images())
        figure_refs = _extract_figure_refs(cleaned_text)

        pages.append(PageContent(
            page_number=page_idx + 1,
            text=cleaned_text,
            tables=raw_tables,
            image_count=image_count,
            figure_refs=figure_refs,
        ))

    doc.close()

    # Tam metin
    full_text = "\n\n".join(p.text for p in pages if p.text.strip())

    # Doküman seviyesi metadata
    first_pages_text = "\n".join(raw_page_texts[:3])
    doc_type = detect_doc_type(first_pages_text)
    revision = extract_revision(first_pages_text)
    effectivity = extract_effectivity(first_pages_text)
    doc_id = _generate_doc_id(str(pdf_path), content_hash)

    return ProcessedDocument(
        doc_id=doc_id,
        source_file=str(pdf_path),
        doc_type=doc_type,
        revision=revision,
        effectivity=effectivity,
        total_pages=len(pages),
        pages=pages,
        full_text=full_text,
        tables_markdown=all_tables_md,
    )


def process_pdf_cached(pdf_path: str | Path, cache_dir: str | Path) -> ProcessedDocument:
    """PDF'yi işle, sonucu cache'le. Varsa cache'ten oku."""
    pdf_path = Path(pdf_path)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    content_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:16]
    cache_file = cache_dir / f"{pdf_path.stem}_{content_hash}.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            pages = [PageContent(**p) for p in data["pages"]]
            return ProcessedDocument(
                doc_id=data["doc_id"],
                source_file=data["source_file"],
                doc_type=data.get("doc_type"),
                revision=data.get("revision"),
                effectivity=data.get("effectivity"),
                total_pages=data["total_pages"],
                pages=pages,
                full_text=data["full_text"],
                tables_markdown=data.get("tables_markdown", []),
            )
        except Exception:
            pass  # bozuk cache, yeniden işle

    result = process_pdf(pdf_path)

    try:
        cache_file.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    return result
