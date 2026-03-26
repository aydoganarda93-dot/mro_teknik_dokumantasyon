"""n8n MRO webhook istemcisi — n8n_client.py deseniyle.

Masaüstü uygulamasından ingestion server'a ve n8n workflow'larına bağlanır.
"""
import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

try:
    import urllib.request as urllib_req
    import urllib.error as urllib_err
except ImportError:
    pass

N8N_BASE = os.environ.get("N8N_BASE_URL", "http://localhost:5678")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
INGESTION_SERVER = os.environ.get("MRO_INGESTION_SERVER", "http://localhost:8100")

MRO_DOCS_DIR = Path(os.environ.get("MRO_DOCS_DIR", r"D:\mro_docs"))
INGESTION_LOG = MRO_DOCS_DIR / "ingestion_log.json"

INGEST_WEBHOOK_URL = f"{N8N_BASE}/webhook/mro-ingest"
BATCH_WEBHOOK_URL = f"{N8N_BASE}/webhook/mro-batch"


def _api_request(url: str, method: str = "GET", body: Optional[dict] = None, timeout: int = 300) -> dict:
    """HTTP istek gönder ve JSON yanıt döndür."""
    data = json.dumps(body).encode() if body else None
    req = urllib_req.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib_req.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib_err.HTTPError as e:
        return {"error": e.read().decode(), "status": e.code}
    except Exception as e:
        return {"error": str(e)}


def is_ingestion_server_running() -> bool:
    """Ingestion server çalışıyor mu?"""
    try:
        req = urllib_req.Request(f"{INGESTION_SERVER}/health")
        with urllib_req.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def get_stats() -> dict:
    """Vektör deposu istatistiklerini al."""
    return _api_request(f"{INGESTION_SERVER}/stats")


def get_documents() -> list:
    """İndekslenmiş doküman listesini al."""
    result = _api_request(f"{INGESTION_SERVER}/documents")
    return result.get("documents", [])


def process_pdf(
    pdf_path: str,
    on_result: Optional[Callable[[dict], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """Tek PDF'yi ingestion server üzerinden işle (thread'de çalışır)."""

    def _run():
        result = _api_request(
            f"{INGESTION_SERVER}/process",
            method="POST",
            body={"pdf_path": pdf_path, "move_to_processed": True},
        )
        if "error" in result:
            if on_error:
                on_error(result["error"])
        else:
            if on_result:
                on_result(result)

    threading.Thread(target=_run, daemon=True).start()


def search_query(
    query: str,
    doc_type: Optional[str] = None,
    top_k: int = 5,
    on_result: Optional[Callable[[dict], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """RAG sorgusu çalıştır (thread'de çalışır)."""

    def _run():
        body = {"query": query, "top_k": top_k}
        if doc_type:
            body["doc_type"] = doc_type

        try:
            result = _api_request(
                f"{INGESTION_SERVER}/search",
                method="POST",
                body=body,
                timeout=120,
            )
            if "error" in result:
                if on_error:
                    on_error(result["error"])
            else:
                if on_result:
                    on_result(result)
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_run, daemon=True).start()


def delete_document(
    doc_id: str,
    on_result: Optional[Callable[[dict], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """Dokümanı sil (thread'de çalışır)."""

    def _run():
        result = _api_request(
            f"{INGESTION_SERVER}/documents/{doc_id}",
            method="DELETE",
        )
        if "error" in result:
            if on_error:
                on_error(result["error"])
        else:
            if on_result:
                on_result(result)

    threading.Thread(target=_run, daemon=True).start()


def trigger_batch_processing(
    on_result: Optional[Callable[[dict], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """inbox klasöründeki tüm PDF'leri toplu işle (thread'de çalışır)."""

    def _run():
        result = _api_request(
            f"{INGESTION_SERVER}/batch",
            method="POST",
            timeout=600,
        )
        if "error" in result:
            if on_error:
                on_error(result["error"])
        else:
            if on_result:
                on_result(result)

    threading.Thread(target=_run, daemon=True).start()


def load_ingestion_log() -> list:
    """ingestion_log.json'dan işleme geçmişini oku."""
    try:
        with open(INGESTION_LOG, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def open_docs_folder() -> None:
    """MRO docs klasörünü Windows Explorer'da aç."""
    import subprocess
    try:
        subprocess.Popen(["explorer", str(MRO_DOCS_DIR)])
    except Exception:
        pass


def open_inbox_folder() -> None:
    """inbox klasörünü aç."""
    import subprocess
    try:
        subprocess.Popen(["explorer", str(MRO_DOCS_DIR / "inbox")])
    except Exception:
        pass
