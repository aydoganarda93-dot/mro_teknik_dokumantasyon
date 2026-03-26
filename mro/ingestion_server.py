"""FastAPI ingestion server — n8n ve GUI entegrasyonu için HTTP API.

Endpoints:
- POST /process    — Tek PDF işle, chunk'la, embed et, ChromaDB'ye kaydet
- POST /search     — RAG sorgusu çalıştır
- GET  /stats      — İndekslenmiş doküman istatistikleri
- GET  /documents  — Doküman listesi
- DELETE /documents/{doc_id} — Doküman sil
- GET  /health     — Sağlık kontrolü

Çalıştırma:
    cd D:\\mro_teknik_dokumantasyon
    python -m uvicorn mro.ingestion_server:app --host 0.0.0.0 --port 8100
"""
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# .env dosyasını yükle (uvicorn doğrudan başlatıldığında ortam değişkenleri okunmaz)
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Proje kök dizinini sys.path'e ekle
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mro.pdf_processor import process_pdf, process_pdf_cached
from mro.chunker import chunk_document
from mro.metadata_extractor import extract_all_metadata, extract_document_summary
from mro.embedder import Embedder
from mro.vector_store import MROVectorStore
from mro.rag_engine import RAGEngine

# ── Konfigürasyon ─────────────────────────────────────────────────────────────

MRO_DOCS_DIR = os.environ.get("MRO_DOCS_DIR", r"D:\mro_docs")
CHROMA_DIR = os.path.join(MRO_DOCS_DIR, "chroma_db")
CACHE_DIR = os.path.join(MRO_DOCS_DIR, "cache")
INGESTION_LOG = os.path.join(MRO_DOCS_DIR, "ingestion_log.json")
INBOX_DIR = os.path.join(MRO_DOCS_DIR, "inbox")
PROCESSED_DIR = os.path.join(MRO_DOCS_DIR, "processed")
FAILED_DIR = os.path.join(MRO_DOCS_DIR, "failed")

EMBEDDING_MODE = os.environ.get("EMBEDDING_MODE", "local")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")

# LLM Provider — "groq" (ücretsiz bulut) | "ollama" (lokal) | "anthropic"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")
LLM_API_KEY = os.environ.get(
    "GROQ_API_KEY" if LLM_PROVIDER == "groq" else "ANTHROPIC_API_KEY", ""
)
LLM_MODEL = os.environ.get("LLM_MODEL", "")  # boşsa provider varsayılanı kullanılır

# Dizinleri oluştur
for d in [MRO_DOCS_DIR, CHROMA_DIR, CACHE_DIR, INBOX_DIR, PROCESSED_DIR, FAILED_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)

# ── Singleton bileşenler ──────────────────────────────────────────────────────

_embedder: Optional[Embedder] = None
_vector_store: Optional[MROVectorStore] = None
_rag_engine: Optional[RAGEngine] = None


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder(mode=EMBEDDING_MODE, voyage_api_key=VOYAGE_API_KEY)
    return _embedder


def _get_vector_store() -> MROVectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = MROVectorStore(CHROMA_DIR, _get_embedder())
    return _vector_store


def _get_rag_engine() -> RAGEngine:
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine(
            vector_store=_get_vector_store(),
            provider=LLM_PROVIDER,
            api_key=LLM_API_KEY,
            model=LLM_MODEL,
        )
    return _rag_engine


# ── Ingestion Log ─────────────────────────────────────────────────────────────

def _load_log() -> list:
    try:
        with open(INGESTION_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_log(log: list):
    with open(INGESTION_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _add_log_entry(entry: dict):
    log = _load_log()
    log.append(entry)
    _save_log(log)


# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="MRO Teknik Dokümantasyon API",
    description="Havacılık MRO PDF analizi ve RAG sorgu API'si",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response modelleri ────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    pdf_path: str
    move_to_processed: bool = True


class ProcessResponse(BaseModel):
    status: str
    doc_id: str
    doc_type: Optional[str]
    total_pages: int
    chunks_count: int
    message: str
    revision: Optional[str] = None
    effectivity: Optional[str] = None
    ata_chapters: list[str] = []
    part_numbers_count: int = 0
    sb_count: int = 0
    ad_count: int = 0
    table_count: int = 0


class SearchRequest(BaseModel):
    query: str
    doc_type: Optional[str] = None
    top_k: int = 5


class SearchResponse(BaseModel):
    answer: str
    sources: list[dict]
    query_analysis: dict


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Sağlık kontrolü."""
    return {
        "status": "ok",
        "embedding_mode": EMBEDDING_MODE,
        "chroma_dir": CHROMA_DIR,
        "docs_dir": MRO_DOCS_DIR,
    }


@app.post("/process", response_model=ProcessResponse)
def process_document(req: ProcessRequest):
    """Tek PDF dosyasını işle ve indeksle."""
    pdf_path = Path(req.pdf_path)

    if not pdf_path.exists():
        raise HTTPException(404, f"PDF bulunamadı: {pdf_path}")

    if not pdf_path.suffix.lower() == ".pdf":
        raise HTTPException(400, "Sadece PDF dosyaları destekleniyor.")

    try:
        # 1. PDF işle
        doc = process_pdf_cached(str(pdf_path), CACHE_DIR)

        # 2. Chunk'la
        chunks = chunk_document(doc)

        if not chunks:
            raise HTTPException(400, "PDF'den metin çıkarılamadı (taranmış veya boş olabilir).")

        # 3. Metadata çıkar
        metadatas = extract_all_metadata(chunks, doc)

        # 4. Vektör deposuna ekle
        store = _get_vector_store()
        added = store.add_chunks(chunks, metadatas, doc.doc_type)

        # 5. Log'a kaydet
        summary = extract_document_summary(doc)
        summary["ingested_at"] = datetime.now().isoformat()
        summary["chunks_count"] = added
        _add_log_entry(summary)

        # 6. İşleneni taşı
        if req.move_to_processed:
            dest = Path(PROCESSED_DIR) / pdf_path.name
            if dest.exists():
                dest = Path(PROCESSED_DIR) / f"{pdf_path.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{pdf_path.suffix}"
            shutil.move(str(pdf_path), str(dest))

        return ProcessResponse(
            status="success",
            doc_id=doc.doc_id,
            doc_type=doc.doc_type,
            total_pages=doc.total_pages,
            chunks_count=added,
            message=f"Başarıyla işlendi: {added} chunk indekslendi.",
            revision=summary.get("revision") or None,
            effectivity=summary.get("effectivity") or None,
            ata_chapters=summary.get("ata_chapters", []),
            part_numbers_count=summary.get("part_numbers_count", 0),
            sb_count=len(summary.get("sb_references", [])),
            ad_count=len(summary.get("ad_references", [])),
            table_count=summary.get("table_count", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        # Hatalı dosyayı failed'a taşı
        try:
            if req.move_to_processed:
                shutil.move(str(pdf_path), str(Path(FAILED_DIR) / pdf_path.name))
        except Exception:
            pass

        _add_log_entry({
            "source_file": str(pdf_path),
            "status": "failed",
            "error": str(e),
            "ingested_at": datetime.now().isoformat(),
        })
        raise HTTPException(500, f"İşleme hatası: {e}")


@app.post("/search", response_model=SearchResponse)
def search_documents(req: SearchRequest):
    """RAG sorgusu çalıştır."""
    if not req.query.strip():
        raise HTTPException(400, "Sorgu boş olamaz.")

    try:
        engine = _get_rag_engine()
        result = engine.query(req.query)
        return SearchResponse(**result)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Sorgu hatası: {e}")


@app.get("/stats")
def get_stats():
    """Vektör deposu istatistikleri."""
    store = _get_vector_store()
    stats = store.get_stats()
    log = _load_log()
    stats["ingestion_log_count"] = len(log)
    stats["last_ingestion"] = log[-1].get("ingested_at", "") if log else ""
    return stats


@app.get("/documents")
def list_documents():
    """İndekslenmiş doküman listesi."""
    store = _get_vector_store()
    return {"documents": store.list_documents()}


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """Dokümanı vektör deposundan sil."""
    store = _get_vector_store()
    deleted = store.delete_document(doc_id)
    if deleted == 0:
        raise HTTPException(404, f"Doküman bulunamadı: {doc_id}")
    return {"status": "deleted", "doc_id": doc_id, "chunks_deleted": deleted}


@app.get("/log")
def get_ingestion_log():
    """İşleme geçmişi."""
    return {"log": _load_log()}


@app.post("/batch")
def process_batch():
    """inbox klasöründeki tüm PDF'leri işle."""
    inbox = Path(INBOX_DIR)
    pdfs = list(inbox.glob("*.pdf")) + list(inbox.glob("*.PDF"))

    if not pdfs:
        return {"status": "empty", "message": "inbox klasöründe PDF bulunamadı."}

    results = []
    for pdf in pdfs:
        try:
            resp = process_document(ProcessRequest(pdf_path=str(pdf)))
            results.append({"file": pdf.name, "status": "success", "doc_id": resp.doc_id, "chunks": resp.chunks_count})
        except Exception as e:
            results.append({"file": pdf.name, "status": "failed", "error": str(e)})

    success = sum(1 for r in results if r["status"] == "success")
    return {
        "status": "completed",
        "total": len(results),
        "success": success,
        "failed": len(results) - success,
        "results": results,
    }
