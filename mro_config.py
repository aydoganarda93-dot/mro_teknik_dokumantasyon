"""MRO yapılandırması — config.py deseniyle (.env > JSON > defaults)."""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

_env_path = BASE_DIR / ".env"
load_dotenv(_env_path)

MRO_CONFIG_PATH = BASE_DIR / "mro_config.json"

MRO_DEFAULTS = {
    "mro_docs_dir": r"D:\mro_docs",
    "embedding_mode": "local",
    "voyage_api_key": "",
    # LLM Provider: "groq" (ücretsiz bulut) | "ollama" (lokal) | "anthropic"
    "llm_provider": "groq",
    "llm_model": "",           # boşsa provider varsayılanı: groq→llama-3.3-70b, ollama→deepseek-r1:8b
    "groq_api_key": "",        # groq.com'dan ücretsiz alın
    "anthropic_api_key": "",   # ücretli — Anthropic kullanmak isteyenler için
    "chunk_size": 1500,
    "chunk_overlap": 200,
    "retrieval_top_k": 10,
    "rerank_top_k": 3,
    "ingestion_server_port": 8100,
    "ingestion_server_host": "0.0.0.0",
}


def load() -> dict:
    """MRO config yükle. .env > mro_config.json > defaults."""
    saved = {}
    if MRO_CONFIG_PATH.exists():
        try:
            with open(MRO_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            pass

    cfg = {**MRO_DEFAULTS, **saved}

    # Ortam değişkenleri her şeyin üstüne yazır
    if os.environ.get("MRO_DOCS_DIR"):
        cfg["mro_docs_dir"] = os.environ["MRO_DOCS_DIR"]
    if os.environ.get("EMBEDDING_MODE"):
        cfg["embedding_mode"] = os.environ["EMBEDDING_MODE"]
    if os.environ.get("VOYAGE_API_KEY"):
        cfg["voyage_api_key"] = os.environ["VOYAGE_API_KEY"]
    if os.environ.get("LLM_PROVIDER"):
        cfg["llm_provider"] = os.environ["LLM_PROVIDER"]
    if os.environ.get("LLM_MODEL"):
        cfg["llm_model"] = os.environ["LLM_MODEL"]
    if os.environ.get("GROQ_API_KEY"):
        cfg["groq_api_key"] = os.environ["GROQ_API_KEY"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        cfg["anthropic_api_key"] = os.environ["ANTHROPIC_API_KEY"]
    if os.environ.get("MRO_INGESTION_PORT"):
        try:
            cfg["ingestion_server_port"] = int(os.environ["MRO_INGESTION_PORT"])
        except ValueError:
            pass

    return cfg


def save(data: dict) -> None:
    """MRO config kaydet."""
    merged = {**load(), **data}
    with open(MRO_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


def get_anthropic_key() -> str:
    """Anthropic API anahtarını döndür."""
    key = load().get("anthropic_api_key", "").strip()
    if not key:
        raise ValueError("ANTHROPIC_API_KEY bulunamadı. .env dosyasına veya MRO Ayarlarına girin.")
    return key
