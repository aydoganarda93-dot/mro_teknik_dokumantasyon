"""ATA-farkında parçalama motoru — Havacılık teknik dokümanlarını akıllı bölme.

Bölme hiyerarşisi:
1. ATA bölüm başlıkları (32-10-01 gibi)
2. Prosedür sınırları (TASK, WARNING, CAUTION, vb.)
3. Fallback: Recursive karakter bölme (1500 token, 200 overlap)

Kurallar:
- Tablolar asla bölünmez (tek chunk olarak saklanır)
- WARNING/CAUTION blokları asla ortadan bölünmez
- Her chunk'a kaynak sayfa numaraları eklenir
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from mro.mro_domain import (
    ATA_HEADING_RE,
    WARNING_CAUTION_RE,
    PROCEDURE_BOUNDARY_KEYWORDS,
)
from mro.pdf_processor import ProcessedDocument, PageContent

# ── Varsayılan Ayarlar ────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 1500       # karakter
DEFAULT_CHUNK_OVERLAP = 200     # karakter
MIN_CHUNK_SIZE = 100            # bu kadardan kısa chunk'lar birleştirilir
MAX_TABLE_CHUNK_SIZE = 5000     # tablolar bu limiti aşarsa bölünür


@dataclass
class DocumentChunk:
    """Tek bir doküman parçası."""
    chunk_id: str
    doc_id: str
    text: str
    chunk_index: int
    page_numbers: list[int] = field(default_factory=list)
    section_title: Optional[str] = None
    ata_reference: Optional[str] = None
    has_table: bool = False
    has_warning: bool = False
    has_caution: bool = False
    has_figure_ref: bool = False
    token_estimate: int = 0

    def __post_init__(self):
        self.token_estimate = len(self.text) // 4  # yaklaşık token sayısı


# ── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Karakter sayısından yaklaşık token sayısı tahmin et."""
    return len(text) // 4


def _find_ata_sections(text: str) -> list[tuple[int, str, str]]:
    """Metindeki ATA bölüm başlıklarının pozisyonlarını bul.

    Returns:
        list of (pozisyon, ata_ref, satır_metni)
    """
    sections = []
    for m in ATA_HEADING_RE.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        line_text = text[line_start:line_end].strip()
        sections.append((m.start(), m.group(1), line_text))
    return sections


def _find_procedure_boundaries(text: str) -> list[int]:
    """Prosedür sınır anahtar kelimelerinin pozisyonlarını bul."""
    boundaries = []
    for keyword in PROCEDURE_BOUNDARY_KEYWORDS:
        pattern = re.compile(
            rf'^\s*{re.escape(keyword)}\s*[:\.\n]',
            re.MULTILINE | re.IGNORECASE,
        )
        for m in pattern.finditer(text):
            boundaries.append(m.start())
    return sorted(set(boundaries))


def _find_warning_caution_blocks(text: str) -> list[tuple[int, int]]:
    """WARNING/CAUTION bloklarının başlangıç ve bitiş pozisyonlarını bul.

    Blok, WARNING/CAUTION başlığından sonraki boş satıra kadar devam eder.
    """
    blocks = []
    for m in WARNING_CAUTION_RE.finditer(text):
        start = m.start()
        # Blok sonunu bul: iki ardışık yeni satır veya metin sonu
        end_match = re.search(r'\n\s*\n', text[m.end():])
        if end_match:
            end = m.end() + end_match.end()
        else:
            end = len(text)
        blocks.append((start, end))
    return blocks


def _is_inside_block(pos: int, blocks: list[tuple[int, int]]) -> bool:
    """Verilen pozisyon herhangi bir bloğun içinde mi?"""
    return any(start <= pos < end for start, end in blocks)


def _split_recursive(
    text: str,
    max_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Metni recursive olarak parçala — paragraf > cümle > karakter sınırları."""
    if len(text) <= max_size:
        return [text] if text.strip() else []

    # Paragraf sınırlarından böl
    paragraphs = re.split(r'\n\s*\n', text)
    if len(paragraphs) > 1:
        return _merge_splits(paragraphs, max_size, overlap)

    # Cümle sınırlarından böl
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) > 1:
        return _merge_splits(sentences, max_size, overlap)

    # Karakter sınırından böl (son çare)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_size, len(text))
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def _merge_splits(
    parts: list[str],
    max_size: int,
    overlap: int,
) -> list[str]:
    """Küçük parçaları max_size'a kadar birleştir, overlap ile örtüşme sağla."""
    chunks = []
    current = ""

    for part in parts:
        candidate = (current + "\n\n" + part).strip() if current else part.strip()
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(part) > max_size:
                # Parça tek başına bile büyükse recursive böl
                sub_chunks = _split_recursive(part, max_size, overlap)
                chunks.extend(sub_chunks)
                current = ""
            else:
                # Overlap: önceki chunk'un son kısmını al
                if chunks and overlap > 0:
                    prev = chunks[-1]
                    overlap_text = prev[-overlap:] if len(prev) > overlap else prev
                    current = overlap_text + "\n\n" + part
                else:
                    current = part

    if current.strip():
        chunks.append(current.strip())

    return chunks


# ── Ana Chunk Fonksiyonu ──────────────────────────────────────────────────────

def chunk_document(
    doc: ProcessedDocument,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """ProcessedDocument'ı akıllı parçalara böl.

    Strateji:
    1. ATA bölüm başlıkları varsa, her bölümü ayrı işle
    2. Bölüm içinde prosedür sınırlarına göre böl
    3. WARNING/CAUTION bloklarını koruyarak recursive böl
    4. Tabloları ayrı chunk olarak ekle
    """
    chunks: list[DocumentChunk] = []
    chunk_idx = 0

    # Sayfa-metin eşleştirmesi (hangi metin hangi sayfada)
    page_text_ranges = _build_page_ranges(doc)

    # ATA bölümlerine göre böl
    sections = _split_by_ata_sections(doc.full_text)

    for section in sections:
        section_text = section["text"]
        ata_ref = section.get("ata_ref")
        section_title = section.get("title")

        if not section_text.strip():
            continue

        # WARNING/CAUTION bloklarını bul
        wc_blocks = _find_warning_caution_blocks(section_text)

        # Bölümü alt parçalara böl
        sub_parts = _split_section(section_text, chunk_size, chunk_overlap, wc_blocks)

        for part_text in sub_parts:
            if not part_text.strip() or len(part_text.strip()) < MIN_CHUNK_SIZE:
                continue

            page_nums = _find_pages_for_text(part_text, page_text_ranges)
            has_warning = bool(re.search(r'\bWARNING\b|\bUYARI\b', part_text, re.IGNORECASE))
            has_caution = bool(re.search(r'\bCAUTION\b|\bDİKKAT\b', part_text, re.IGNORECASE))
            has_figure = bool(re.search(r'\bFig(?:ure|ür)?\b|\bŞekil\b', part_text, re.IGNORECASE))

            chunk = DocumentChunk(
                chunk_id=f"{doc.doc_id}_chunk_{chunk_idx:04d}",
                doc_id=doc.doc_id,
                text=part_text.strip(),
                chunk_index=chunk_idx,
                page_numbers=page_nums,
                section_title=section_title,
                ata_reference=ata_ref,
                has_table=False,
                has_warning=has_warning,
                has_caution=has_caution,
                has_figure_ref=has_figure,
            )
            chunks.append(chunk)
            chunk_idx += 1

    # Tabloları ayrı chunk olarak ekle
    for table_md in doc.tables_markdown:
        if not table_md.strip():
            continue
        if len(table_md) > MAX_TABLE_CHUNK_SIZE:
            # Çok büyük tabloları satır bazında böl
            table_chunks = _split_large_table(table_md, chunk_size)
        else:
            table_chunks = [table_md]

        for tc in table_chunks:
            chunk = DocumentChunk(
                chunk_id=f"{doc.doc_id}_table_{chunk_idx:04d}",
                doc_id=doc.doc_id,
                text=tc.strip(),
                chunk_index=chunk_idx,
                page_numbers=[],
                section_title=None,
                ata_reference=None,
                has_table=True,
                has_warning=False,
                has_caution=False,
                has_figure_ref=False,
            )
            chunks.append(chunk)
            chunk_idx += 1

    return chunks


def _split_by_ata_sections(text: str) -> list[dict]:
    """Metni ATA bölüm başlıklarına göre böl."""
    ata_positions = _find_ata_sections(text)

    if not ata_positions:
        return [{"text": text, "ata_ref": None, "title": None}]

    sections = []
    for i, (pos, ata_ref, title) in enumerate(ata_positions):
        end = ata_positions[i + 1][0] if i + 1 < len(ata_positions) else len(text)
        section_text = text[pos:end]
        sections.append({
            "text": section_text,
            "ata_ref": ata_ref,
            "title": title,
        })

    # ATA başlığı öncesi metin varsa ekle
    if ata_positions and ata_positions[0][0] > 0:
        pre_text = text[:ata_positions[0][0]]
        if pre_text.strip():
            sections.insert(0, {"text": pre_text, "ata_ref": None, "title": None})

    return sections


def _split_section(
    text: str,
    chunk_size: int,
    overlap: int,
    wc_blocks: list[tuple[int, int]],
) -> list[str]:
    """Bir bölümü prosedür sınırları ve WARNING korumasıyla böl."""
    if len(text) <= chunk_size:
        return [text]

    # Prosedür sınırlarını bul
    boundaries = _find_procedure_boundaries(text)

    if boundaries:
        parts = []
        prev = 0
        for b in boundaries:
            if b > prev and not _is_inside_block(b, wc_blocks):
                parts.append(text[prev:b])
                prev = b
        parts.append(text[prev:])

        # Parçaları birleştir/böl
        result = []
        for part in parts:
            if len(part) <= chunk_size:
                result.append(part)
            else:
                result.extend(_split_recursive(part, chunk_size, overlap))
        return result

    return _split_recursive(text, chunk_size, overlap)


def _split_large_table(table_md: str, chunk_size: int) -> list[str]:
    """Büyük tabloyu header'ı koruyarak böl."""
    lines = table_md.split("\n")
    if len(lines) < 3:
        return [table_md]

    header = "\n".join(lines[:2])  # başlık + ayırıcı
    chunks = []
    current = header

    for line in lines[2:]:
        candidate = current + "\n" + line
        if len(candidate) > chunk_size and current != header:
            chunks.append(current)
            current = header + "\n" + line
        else:
            current = candidate

    if current.strip() and current != header:
        chunks.append(current)

    return chunks if chunks else [table_md]


def _build_page_ranges(doc: ProcessedDocument) -> list[tuple[str, int]]:
    """Her sayfanın metnini ve sayfa numarasını eşleştir."""
    return [(page.text, page.page_number) for page in doc.pages if page.text.strip()]


def _find_pages_for_text(
    chunk_text: str,
    page_ranges: list[tuple[str, int]],
) -> list[int]:
    """Chunk metninin hangi sayfalarda geçtiğini bul."""
    pages = []
    # Chunk'ın ilk 100 karakterini arayarak sayfa eşleştir
    search_text = chunk_text[:100].strip()
    if not search_text:
        return pages

    for page_text, page_num in page_ranges:
        if search_text in page_text:
            pages.append(page_num)
            break

    # Bulunamazsa son 100 karaktere de bak
    if not pages:
        search_text = chunk_text[-100:].strip()
        for page_text, page_num in page_ranges:
            if search_text in page_text:
                pages.append(page_num)
                break

    return pages
