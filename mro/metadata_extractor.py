"""Metadata çıkarma — Her chunk için zengin metadata üretir.

Chunk ve doküman seviyesinde ATA bölüm, parça numarası, doküman tipi,
SB/AD referansları ve effectivity bilgilerini çıkarır.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional

from mro.chunker import DocumentChunk
from mro.mro_domain import (
    extract_ata_sections,
    extract_part_numbers,
    extract_sb_references,
    extract_ad_references,
    extract_revision,
    extract_effectivity,
    get_ata_chapter_name,
    detect_doc_type,
)
from mro.pdf_processor import ProcessedDocument


@dataclass
class ChunkMetadata:
    """Tek bir chunk için zengin metadata."""
    chunk_id: str
    doc_id: str
    doc_type: Optional[str] = None
    ata_chapter: Optional[str] = None
    ata_section: Optional[str] = None
    ata_subject: Optional[str] = None
    ata_chapter_name: Optional[str] = None
    section_title: Optional[str] = None
    part_numbers: list[str] = field(default_factory=list)
    sb_references: list[str] = field(default_factory=list)
    ad_references: list[str] = field(default_factory=list)
    revision: Optional[str] = None
    effectivity: Optional[str] = None
    page_numbers: list[int] = field(default_factory=list)
    has_table: bool = False
    has_warning: bool = False
    has_caution: bool = False
    has_figure_ref: bool = False
    source_file: Optional[str] = None
    chunk_index: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        # ChromaDB metadata sadece string/int/float/bool destekler
        # Listeleri virgülle ayrılmış string'e çevir
        d["part_numbers"] = ",".join(d["part_numbers"]) if d["part_numbers"] else ""
        d["sb_references"] = ",".join(d["sb_references"]) if d["sb_references"] else ""
        d["ad_references"] = ",".join(d["ad_references"]) if d["ad_references"] else ""
        d["page_numbers"] = ",".join(str(p) for p in d["page_numbers"]) if d["page_numbers"] else ""
        # None değerleri boş string'e çevir (ChromaDB None desteklemez)
        for k, v in d.items():
            if v is None:
                d[k] = ""
        return d

    def to_filter_dict(self) -> dict:
        """ChromaDB where filtresi için uygun dict döndür (boş alanlar hariç)."""
        d = self.to_dict()
        return {k: v for k, v in d.items() if v and v != "" and k not in ("chunk_id", "chunk_index")}


def extract_chunk_metadata(
    chunk: DocumentChunk,
    doc: ProcessedDocument,
) -> ChunkMetadata:
    """Chunk ve doküman bilgilerinden zengin metadata çıkar."""

    # ATA bilgilerini chunk metninden çıkar
    ata_sections = extract_ata_sections(chunk.text)
    ata_chapter = None
    ata_section = None
    ata_subject = None

    if chunk.ata_reference:
        parts = chunk.ata_reference.split("-")
        ata_chapter = parts[0] if len(parts) >= 1 else None
        ata_section = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else None
        ata_subject = chunk.ata_reference if len(parts) >= 3 else None
    elif ata_sections:
        first = ata_sections[0]
        ata_chapter = first["chapter"]
        ata_section = first["section"]
        ata_subject = first["subject"]

    # Parça numaraları
    part_numbers = extract_part_numbers(chunk.text)

    # SB/AD referansları
    sb_refs = extract_sb_references(chunk.text)
    ad_refs = extract_ad_references(chunk.text)

    return ChunkMetadata(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        doc_type=doc.doc_type or "",
        ata_chapter=ata_chapter,
        ata_section=ata_section,
        ata_subject=ata_subject,
        ata_chapter_name=get_ata_chapter_name(ata_chapter) if ata_chapter else None,
        section_title=chunk.section_title,
        part_numbers=part_numbers,
        sb_references=sb_refs,
        ad_references=ad_refs,
        revision=doc.revision,
        effectivity=doc.effectivity,
        page_numbers=chunk.page_numbers,
        has_table=chunk.has_table,
        has_warning=chunk.has_warning,
        has_caution=chunk.has_caution,
        has_figure_ref=chunk.has_figure_ref,
        source_file=doc.source_file,
        chunk_index=chunk.chunk_index,
    )


def extract_all_metadata(
    chunks: list[DocumentChunk],
    doc: ProcessedDocument,
) -> list[ChunkMetadata]:
    """Tüm chunk'lar için metadata çıkar."""
    return [extract_chunk_metadata(chunk, doc) for chunk in chunks]


def extract_document_summary(doc: ProcessedDocument) -> dict:
    """Doküman seviyesinde özet metadata üret (ingestion log için)."""
    all_parts = extract_part_numbers(doc.full_text[:20000])  # ilk 20k karakter
    all_sbs = extract_sb_references(doc.full_text)
    all_ads = extract_ad_references(doc.full_text)
    ata_sections = extract_ata_sections(doc.full_text[:10000])

    # Benzersiz ATA bölümleri
    unique_chapters = sorted(set(s["chapter"] for s in ata_sections))
    unique_sections = sorted(set(s["section"] for s in ata_sections))

    return {
        "doc_id": doc.doc_id,
        "source_file": doc.source_file,
        "doc_type": doc.doc_type,
        "revision": doc.revision,
        "effectivity": doc.effectivity,
        "total_pages": doc.total_pages,
        "ata_chapters": unique_chapters,
        "ata_sections": unique_sections,
        "part_numbers_count": len(all_parts),
        "part_numbers_sample": all_parts[:10],
        "sb_references": all_sbs,
        "ad_references": all_ads,
        "table_count": len(doc.tables_markdown),
    }
