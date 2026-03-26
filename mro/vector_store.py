"""ChromaDB vektör depolama — Doküman chunk'larını indeksle ve ara.

Collection yapısı: Doküman tipi başına ayrı collection (mro_cmm, mro_srm, vb.)
Fallback: mro_general (tipi bilinmeyen dokümanlar)
"""
import json
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from mro.chunker import DocumentChunk
from mro.embedder import Embedder
from mro.metadata_extractor import ChunkMetadata

# Collection isimleri
COLLECTION_MAP = {
    "CMM": "mro_cmm",
    "SRM": "mro_srm",
    "IPC": "mro_ipc",
    "AMM": "mro_amm",
    "SB":  "mro_sb",
    "AD":  "mro_ad",
    "TSM": "mro_tsm",
    "WDM": "mro_wdm",
}
DEFAULT_COLLECTION = "mro_general"


class MROVectorStore:
    """ChromaDB tabanlı MRO vektör deposu."""

    def __init__(self, persist_dir: str, embedder: Embedder):
        """
        Args:
            persist_dir: ChromaDB veritabanı dizini (D:\\mro_docs\\chroma_db)
            embedder: Embedding üretici
        """
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder

        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

        # Collection'ları oluştur/al
        self._collections: dict[str, chromadb.Collection] = {}
        for name in list(COLLECTION_MAP.values()) + [DEFAULT_COLLECTION]:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )

    def _get_collection(self, doc_type: Optional[str]) -> chromadb.Collection:
        """Doküman tipine göre collection döndür."""
        col_name = COLLECTION_MAP.get(doc_type or "", DEFAULT_COLLECTION)
        return self._collections[col_name]

    def add_chunks(
        self,
        chunks: list[DocumentChunk],
        metadatas: list[ChunkMetadata],
        doc_type: Optional[str] = None,
        batch_size: int = 50,
    ) -> int:
        """Chunk'ları vektör deposuna ekle.

        Returns:
            Eklenen chunk sayısı
        """
        if not chunks:
            return 0

        collection = self._get_collection(doc_type)
        total_added = 0

        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_meta = metadatas[i:i + batch_size]

            texts = [c.text for c in batch_chunks]
            ids = [c.chunk_id for c in batch_chunks]
            metas = [m.to_dict() for m in batch_meta]

            # Embedding üret
            embeddings = self.embedder.embed_documents(texts)

            # ChromaDB'ye ekle
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metas,
            )
            total_added += len(batch_chunks)

        return total_added

    def search(
        self,
        query: str,
        doc_type: Optional[str] = None,
        top_k: int = 10,
        where_filter: Optional[dict] = None,
    ) -> list[dict]:
        """Semantik arama yap.

        Args:
            query: Arama sorgusu
            doc_type: Belirli bir doküman tipinde ara (None = tüm collection'lar)
            top_k: Döndürülecek maksimum sonuç
            where_filter: ChromaDB metadata filtresi

        Returns:
            Sonuç listesi: [{"id", "text", "metadata", "distance"}, ...]
        """
        query_embedding = self.embedder.embed_query(query)

        if doc_type:
            collections = [self._get_collection(doc_type)]
        else:
            collections = list(self._collections.values())

        all_results = []

        for collection in collections:
            if collection.count() == 0:
                continue

            kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": min(top_k, collection.count()),
            }
            if where_filter:
                kwargs["where"] = where_filter

            try:
                results = collection.query(**kwargs)
            except Exception:
                continue

            if not results or not results["ids"] or not results["ids"][0]:
                continue

            for j in range(len(results["ids"][0])):
                all_results.append({
                    "id": results["ids"][0][j],
                    "text": results["documents"][0][j] if results["documents"] else "",
                    "metadata": results["metadatas"][0][j] if results["metadatas"] else {},
                    "distance": results["distances"][0][j] if results["distances"] else 1.0,
                })

        # Mesafeye göre sırala ve top_k'ya kırp
        all_results.sort(key=lambda r: r["distance"])
        return all_results[:top_k]

    def search_by_part_number(self, part_number: str, top_k: int = 10) -> list[dict]:
        """Parça numarasına göre metadata filtreli arama."""
        return self.search(
            query=f"part number {part_number}",
            top_k=top_k,
            where_filter={"part_numbers": {"$contains": part_number}},
        )

    def search_by_ata(
        self,
        ata_chapter: str,
        query: str = "",
        top_k: int = 10,
    ) -> list[dict]:
        """ATA bölüm numarasına göre filtreli arama."""
        search_query = query or f"ATA {ata_chapter}"
        return self.search(
            query=search_query,
            top_k=top_k,
            where_filter={"ata_chapter": ata_chapter},
        )

    def delete_document(self, doc_id: str) -> int:
        """Bir dokümanın tüm chunk'larını sil.

        Returns:
            Silinen chunk sayısı
        """
        total_deleted = 0
        for collection in self._collections.values():
            try:
                results = collection.get(where={"doc_id": doc_id})
                if results["ids"]:
                    collection.delete(ids=results["ids"])
                    total_deleted += len(results["ids"])
            except Exception:
                continue
        return total_deleted

    def get_stats(self) -> dict:
        """Vektör deposu istatistikleri."""
        stats = {"total_chunks": 0, "collections": {}}
        for name, col in self._collections.items():
            count = col.count()
            stats["collections"][name] = count
            stats["total_chunks"] += count
        return stats

    def get_document_ids(self) -> list[str]:
        """Tüm benzersiz doküman ID'lerini döndür."""
        doc_ids: set[str] = set()
        for collection in self._collections.values():
            try:
                results = collection.get(include=["metadatas"])
                for meta in results.get("metadatas", []):
                    if meta and meta.get("doc_id"):
                        doc_ids.add(meta["doc_id"])
            except Exception:
                continue
        return sorted(doc_ids)

    def list_documents(self) -> list[dict]:
        """İndekslenmiş dokümanların özet listesini döndür."""
        doc_map: dict[str, dict] = {}
        for col_name, collection in self._collections.items():
            try:
                results = collection.get(include=["metadatas"])
                for meta in results.get("metadatas", []):
                    if not meta:
                        continue
                    did = meta.get("doc_id", "")
                    if did and did not in doc_map:
                        doc_map[did] = {
                            "doc_id": did,
                            "doc_type": meta.get("doc_type", ""),
                            "source_file": meta.get("source_file", ""),
                            "ata_chapter": meta.get("ata_chapter", ""),
                            "revision": meta.get("revision", ""),
                            "collection": col_name,
                            "chunk_count": 0,
                        }
                    if did:
                        doc_map[did]["chunk_count"] += 1
            except Exception:
                continue
        return list(doc_map.values())
