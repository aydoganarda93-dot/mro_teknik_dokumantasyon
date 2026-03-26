"""RAG motoru — Retrieval Augmented Generation ile teknik dokümantasyon Q&A.

Pipeline:
1. Sorgu ön-işleme (ATA ref, part no, doc type tespiti)
2. Hibrit arama (semantik + metadata filtre)
3. Reranking (LLM ile top-10 → top-3)
4. Yanıt üretimi (LLM, kaynak referanslı)

Desteklenen provider'lar:
- "anthropic" : Anthropic Claude (ücretli, ANTHROPIC_API_KEY gerekli)
- "groq"      : Groq ücretsiz API (GROQ_API_KEY gerekli — groq.com)
- "ollama"    : Tamamen lokal/ücretsiz (Ollama kurulu olmalı)
"""
import os
import re
from typing import Optional, Callable

from mro.mro_domain import (
    ATA_SECTION_RE,
    PART_NUMBER_PATTERNS,
    DOC_TYPES,
)
from mro.vector_store import MROVectorStore

# ── Sistem Promptu ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Sen bir havacılık MRO (Bakım, Onarım, Revizyon) teknik dokümantasyon uzmanısın.
Verilen kaynak belgelere dayanarak soruları yanıtla.

Kurallar:
- SADECE verilen kaynaklardaki bilgilere dayanarak yanıt ver. Bilmediğin şeyi uydurma.
- Her bilgi için kaynak referansı belirt: [DOC_ID, Sayfa X]
- WARNING ve CAUTION uyarılarını her zaman **kalın** olarak vurgula
- Part numaralarını tam olarak yaz, kısaltma yapma
- ATA bölüm numaralarını referans olarak kullan (örn: ATA 32-10-01)
- Emin olmadığında "Bu bilgi mevcut kaynaklarda bulunamadı" de
- Yanıtlarını yapılandırılmış ve okunabilir tut (başlıklar, maddeler kullan)
- Hem Türkçe hem İngilizce sorulara yanıt verebilirsin, sorunun dilinde yanıtla"""

RERANK_PROMPT = """Aşağıdaki kullanıcı sorusuna en alakalı kaynak belgelerini seç.
Her belge için 1-10 arası bir alakalılık puanı ver.

Kullanıcı sorusu: {query}

Belgeler:
{documents}

Yanıtını şu JSON formatında ver:
[{{"index": 0, "score": 8}}, {{"index": 1, "score": 3}}, ...]

Sadece JSON döndür, başka bir şey yazma."""


class QueryAnalysis:
    """Sorgu ön-işleme sonuçları."""

    def __init__(self, query: str):
        self.original_query = query
        self.ata_references: list[str] = []
        self.part_numbers: list[str] = []
        self.doc_type: Optional[str] = None
        self.is_specific = False  # belirli bir bölüm/parça sorgusu mu

    def get_where_filter(self) -> Optional[dict]:
        """ChromaDB where filtresi oluştur."""
        filters = []

        if self.ata_references:
            chapter = self.ata_references[0].split("-")[0]
            filters.append({"ata_chapter": chapter})

        if self.part_numbers:
            filters.append({"part_numbers": {"$contains": self.part_numbers[0]}})

        if not filters:
            return None
        if len(filters) == 1:
            return filters[0]
        return {"$and": filters}


def analyze_query(query: str) -> QueryAnalysis:
    """Sorguyu ön-işle: ATA referans, parça no, doküman tipi tespit et."""
    analysis = QueryAnalysis(query)

    # ATA referansları
    for m in ATA_SECTION_RE.finditer(query):
        analysis.ata_references.append(m.group(0))

    # Parça numaraları
    for pattern in PART_NUMBER_PATTERNS:
        for m in pattern.finditer(query):
            pn = m.group(1) if pattern.groups else m.group(0)
            if len(pn) >= 4:
                analysis.part_numbers.append(pn)

    # Doküman tipi
    upper = query.upper()
    for dtype in DOC_TYPES:
        if dtype in upper:
            analysis.doc_type = dtype
            break

    analysis.is_specific = bool(analysis.ata_references or analysis.part_numbers)
    return analysis


# ── Provider Varsayılanları ───────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "anthropic": {
        "model": "claude-sonnet-4-6",
        "base_url": None,
        "env_key": "ANTHROPIC_API_KEY",
    },
    "groq": {
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
    },
    "ollama": {
        "model": "deepseek-r1:8b",
        "base_url": "http://localhost:11434/v1",
        "env_key": None,  # API key gerektirmez
    },
}


def _build_openai_client(provider: str, api_key: str):
    """Groq veya Ollama için openai kütüphanesiyle istemci oluştur."""
    from openai import OpenAI
    cfg = PROVIDER_DEFAULTS[provider]
    return OpenAI(
        api_key=api_key or "ollama",  # Ollama için dummy key yeterli
        base_url=cfg["base_url"],
    )


class RAGEngine:
    """Tam RAG pipeline: arama + reranking + yanıt üretimi.

    provider seçenekleri: "anthropic" | "groq" | "ollama"
    """

    def __init__(
        self,
        vector_store: MROVectorStore,
        provider: str = "ollama",
        api_key: str = "",
        model: str = "",
        rerank_top_k: int = 3,
        retrieval_top_k: int = 10,
    ):
        self.vector_store = vector_store
        self.provider = provider.lower()
        self.rerank_top_k = rerank_top_k
        self.retrieval_top_k = retrieval_top_k

        cfg = PROVIDER_DEFAULTS.get(self.provider, PROVIDER_DEFAULTS["ollama"])

        # Model: önce parametre, sonra env, sonra default
        self.model = model or os.environ.get("LLM_MODEL", "") or cfg["model"]

        # API key
        env_key = cfg.get("env_key")
        if env_key:
            self.api_key = api_key or os.environ.get(env_key, "")
        else:
            self.api_key = ""  # Ollama key istemez

        # İstemci oluştur
        if self.provider == "anthropic":
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY gerekli.")
            import anthropic as _anthropic
            self._client = _anthropic.Anthropic(api_key=self.api_key)
        elif self.provider in ("groq", "ollama"):
            if self.provider == "groq" and not self.api_key:
                raise ValueError("GROQ_API_KEY gerekli. groq.com'dan ücretsiz alın.")
            self._client = _build_openai_client(self.provider, self.api_key)
        else:
            raise ValueError(f"Desteklenmeyen provider: {self.provider}. Seçenekler: anthropic, groq, ollama")

    def query(
        self,
        question: str,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """Tam RAG sorgusu çalıştır.

        Args:
            question: Kullanıcı sorusu
            on_token: Streaming token callback (opsiyonel)

        Returns:
            {
                "answer": str,
                "sources": [{"doc_id", "page", "text_preview", "ata_ref"}],
                "query_analysis": {...},
            }
        """
        # 1. Sorgu analizi
        analysis = analyze_query(question)

        # 2. Vektör arama
        where_filter = analysis.get_where_filter()
        search_results = self.vector_store.search(
            query=question,
            doc_type=analysis.doc_type,
            top_k=self.retrieval_top_k,
            where_filter=where_filter,
        )

        if not search_results:
            # Filtre olmadan tekrar dene
            search_results = self.vector_store.search(
                query=question,
                top_k=self.retrieval_top_k,
            )

        if not search_results:
            return {
                "answer": "Bu soru için mevcut kaynaklarda herhangi bir bilgi bulunamadı. "
                          "Lütfen ilgili teknik dokümanların sisteme yüklendiğinden emin olun.",
                "sources": [],
                "query_analysis": {
                    "ata_refs": analysis.ata_references,
                    "part_numbers": analysis.part_numbers,
                    "doc_type": analysis.doc_type,
                },
            }

        # 3. Reranking (sonuç sayısı yeterliyse)
        if len(search_results) > self.rerank_top_k:
            ranked = self._rerank(question, search_results)
        else:
            ranked = search_results

        # 4. Bağlam oluştur
        context = self._build_context(ranked)
        sources = self._extract_sources(ranked)

        # 5. Yanıt üret
        answer = self._generate_answer(question, context, on_token)

        return {
            "answer": answer,
            "sources": sources,
            "query_analysis": {
                "ata_refs": analysis.ata_references,
                "part_numbers": analysis.part_numbers,
                "doc_type": analysis.doc_type,
            },
        }

    def _llm_call(self, messages: list[dict], max_tokens: int = 500) -> str:
        """Provider'dan bağımsız LLM çağrısı — kısa/yapılandırılmış çıktı için."""
        try:
            if self.provider == "anthropic":
                system = messages[0]["content"] if messages[0]["role"] == "system" else ""
                user_msgs = [m for m in messages if m["role"] != "system"]
                resp = self._client.messages.create(
                    model=self.model, max_tokens=max_tokens, temperature=0,
                    system=system, messages=user_msgs,
                )
                return resp.content[0].text
            else:  # groq / ollama — openai uyumlu
                resp = self._client.chat.completions.create(
                    model=self.model, max_tokens=max_tokens, temperature=0,
                    messages=messages,
                )
                return resp.choices[0].message.content or ""
        except Exception as e:
            return ""

    def _rerank(self, query: str, results: list[dict]) -> list[dict]:
        """LLM ile sonuçları yeniden sırala."""
        docs_text = ""
        for i, r in enumerate(results):
            preview = r["text"][:300].replace("\n", " ")
            meta = r.get("metadata", {})
            docs_text += f"\n[{i}] DOC: {meta.get('doc_id', '?')} | ATA: {meta.get('ata_section', '?')} | Sayfa: {meta.get('page_numbers', '?')}\n{preview}\n"

        try:
            text = self._llm_call([
                {"role": "user", "content": RERANK_PROMPT.format(query=query, documents=docs_text)},
            ], max_tokens=500)

            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            if json_match:
                import json
                scores = json.loads(json_match.group())
                scored = []
                for item in scores:
                    idx = item.get("index", 0)
                    score = item.get("score", 0)
                    if 0 <= idx < len(results):
                        scored.append((score, results[idx]))
                scored.sort(key=lambda x: x[0], reverse=True)
                return [s[1] for s in scored[:self.rerank_top_k]]
        except Exception:
            pass

        return results[:self.rerank_top_k]

    def _build_context(self, results: list[dict]) -> str:
        """Arama sonuçlarından LLM bağlamı oluştur."""
        parts = []
        for i, r in enumerate(results):
            meta = r.get("metadata", {})
            header = (
                f"--- KAYNAK {i + 1} ---\n"
                f"Doküman: {meta.get('doc_id', 'Bilinmiyor')}\n"
                f"Tip: {meta.get('doc_type', '?')} | "
                f"ATA: {meta.get('ata_section', '?')} | "
                f"Sayfa: {meta.get('page_numbers', '?')}\n"
                f"Dosya: {meta.get('source_file', '?')}\n"
                f"---"
            )
            parts.append(f"{header}\n{r['text']}")
        return "\n\n".join(parts)

    def _extract_sources(self, results: list[dict]) -> list[dict]:
        """Sonuçlardan kaynak referans listesi oluştur."""
        sources = []
        for r in results:
            meta = r.get("metadata", {})
            sources.append({
                "doc_id": meta.get("doc_id", ""),
                "page": meta.get("page_numbers", ""),
                "ata_ref": meta.get("ata_section", ""),
                "doc_type": meta.get("doc_type", ""),
                "text_preview": r["text"][:150] + "..." if len(r["text"]) > 150 else r["text"],
                "distance": r.get("distance", 0),
            })
        return sources

    def _generate_answer(
        self,
        question: str,
        context: str,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """LLM ile kaynak referanslı yanıt üret (provider-agnostic)."""
        user_message = (
            f"Aşağıdaki kaynak belgelerine dayanarak soruyu yanıtla.\n\n"
            f"KAYNAKLAR:\n{context}\n\n"
            f"SORU: {question}"
        )

        if self.provider == "anthropic":
            if on_token:
                answer_parts = []
                with self._client.messages.stream(
                    model=self.model, max_tokens=4096, temperature=0,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                ) as stream:
                    for text in stream.text_stream:
                        answer_parts.append(text)
                        on_token(text)
                return "".join(answer_parts)
            else:
                resp = self._client.messages.create(
                    model=self.model, max_tokens=4096, temperature=0,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                )
                return resp.content[0].text

        else:  # groq / ollama — openai uyumlu
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
            if on_token:
                answer_parts = []
                stream = self._client.chat.completions.create(
                    model=self.model, max_tokens=4096, temperature=0,
                    messages=messages, stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        answer_parts.append(delta)
                        on_token(delta)
                return "".join(answer_parts)
            else:
                resp = self._client.chat.completions.create(
                    model=self.model, max_tokens=4096, temperature=0,
                    messages=messages,
                )
                return resp.choices[0].message.content or ""
