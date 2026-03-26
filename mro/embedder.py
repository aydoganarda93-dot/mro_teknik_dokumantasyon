"""Embedding üretimi — Lokal (sentence-transformers) veya Voyage AI.

Varsayılan: all-MiniLM-L6-v2 (lokal, ücretsiz, 384-boyutlu vektörler).
Opsiyonel: Voyage AI voyage-3 (1024-boyutlu, teknik dokümanlar için optimize).
"""
import os
from typing import Optional

_st_model = None  # lazy-load sentence-transformers modeli


def _get_local_model():
    """sentence-transformers modelini lazy-load et."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _st_model


def embed_texts_local(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Lokal sentence-transformers ile embedding üret."""
    model = _get_local_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return embeddings.tolist()


def embed_texts_voyage(
    texts: list[str],
    api_key: Optional[str] = None,
    model: str = "voyage-3",
) -> list[list[float]]:
    """Voyage AI API ile embedding üret."""
    import voyageai

    key = api_key or os.environ.get("VOYAGE_API_KEY", "")
    if not key:
        raise ValueError("VOYAGE_API_KEY gerekli. .env dosyasına ekleyin.")

    client = voyageai.Client(api_key=key)
    result = client.embed(texts, model=model, input_type="document")
    return result.embeddings


def embed_query_local(query: str) -> list[float]:
    """Tek bir sorguyu lokal model ile embed et."""
    return embed_texts_local([query])[0]


def embed_query_voyage(
    query: str,
    api_key: Optional[str] = None,
    model: str = "voyage-3",
) -> list[float]:
    """Tek bir sorguyu Voyage AI ile embed et."""
    import voyageai

    key = api_key or os.environ.get("VOYAGE_API_KEY", "")
    if not key:
        raise ValueError("VOYAGE_API_KEY gerekli.")

    client = voyageai.Client(api_key=key)
    result = client.embed([query], model=model, input_type="query")
    return result.embeddings[0]


class Embedder:
    """Birleşik embedding arayüzü — config'e göre lokal veya Voyage kullanır."""

    def __init__(self, mode: str = "local", voyage_api_key: str = ""):
        """
        Args:
            mode: "local" veya "voyage"
            voyage_api_key: Voyage AI API anahtarı (mode="voyage" ise gerekli)
        """
        self.mode = mode
        self.voyage_api_key = voyage_api_key

        if mode == "local":
            # Modeli önceden yükle
            _get_local_model()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Doküman metinlerini embed et."""
        if self.mode == "voyage":
            return embed_texts_voyage(texts, self.voyage_api_key)
        return embed_texts_local(texts)

    def embed_query(self, query: str) -> list[float]:
        """Tek bir sorguyu embed et."""
        if self.mode == "voyage":
            return embed_query_voyage(query, self.voyage_api_key)
        return embed_query_local(query)

    @property
    def dimension(self) -> int:
        """Embedding boyutu."""
        if self.mode == "voyage":
            return 1024
        return 384
