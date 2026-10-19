import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

from rank_bm25 import BM25Okapi

from .versioning import filter_effective_chunks


TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)
RRF_K = 60
STOPWORDS = {
    "data",
    "pack",
    "theo",
    "được",
    "là",
    "gì",
    "nào",
    "một",
    "các",
    "những",
    "cho",
    "về",
    "của",
    "trong",
    "có",
    "không",
    "thì",
    "và",
    "hoặc",
    "nếu",
    "hãy",
    "xin",
    "cho",
    "biết",
    "giúp",
    "tôi",
    "để",
    "hiện",
    "hành",
    "phương",
    "án",
    "xử",
    "lý",
    "phù",
    "hợp",
    "nêu",
    "nên",
    "nguồn",
    "ưu",
    "tiên",
    "tra",
    "cứu",
    "công",
    "ty",
    "cổ",
    "phần",
    "nova",
    "việt",
}


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text.casefold())
    return [token for token in TOKEN_RE.findall(normalized) if token not in STOPWORDS]


def searchable_text(chunk: dict[str, Any]) -> str:
    fields = (
        "article",
        "clause",
        "heading",
        "topic",
        "subtopic",
        "chunk_text",
    )
    return " ".join(str(chunk.get(field, "")) for field in fields)


@dataclass
class RetrievalHit:
    chunk: dict[str, Any]
    score: float
    bm25_score: float
    cosine_score: float | None


class RetrievalEngine:
    def __init__(
        self,
        chunks: list[dict[str, Any]],
        mode: str = "bm25",
        embedding_model: str = "intfloat/multilingual-e5-base",
    ) -> None:
        if mode not in {"bm25", "hybrid"}:
            raise ValueError("mode phải là 'bm25' hoặc 'hybrid'")
        self.chunks = chunks
        self.mode = mode
        self.documents = [searchable_text(chunk) for chunk in chunks]
        self.tokenized_documents = [tokenize(text) for text in self.documents]
        self.bm25 = BM25Okapi(self.tokenized_documents)
        self.encoder = None
        self.embeddings = None
        self._e5_model = "e5" in embedding_model.casefold()
        if mode == "hybrid":
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "Hybrid retrieval cần sentence-transformers. "
                    "Cài dependencies bằng: python -m pip install -r requirements-optional.txt"
                ) from exc
            import numpy as np

            self.encoder = SentenceTransformer(embedding_model)
            passages = [
                f"passage: {text}" if self._e5_model else text
                for text in self.documents
            ]
            self.embeddings = self.encoder.encode(
                passages,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=True,
            )
            self._numpy = np

    @staticmethod
    def _source_adjustment(chunk: dict[str, Any]) -> float:
        source = chunk.get("source_type", "")
        doc_type = chunk.get("document_type", "")
        if source == "LEGAL":
            return 1.04
        if doc_type == "FAQ":
            return 0.97
        return 1.0

    def retrieve(
        self,
        question: str,
        reference_date: date,
        top_k: int = 5,
    ) -> tuple[list[RetrievalHit], float]:
        if not question.strip():
            raise ValueError("Câu hỏi không được để trống")
        if top_k < 1:
            raise ValueError("top_k phải lớn hơn 0")
        eligible = filter_effective_chunks(self.chunks, reference_date)
        if not eligible:
            return [], 0.0
        eligible_ids = {chunk["chunk_id"] for chunk in eligible}
        query_tokens = tokenize(question)
        normalized_question = unicodedata.normalize("NFC", question.casefold())
        if "là gì" in normalized_question or "được hiểu" in normalized_question:
            query_tokens.extend(("khái", "niệm", "định", "nghĩa"))
        bm25_scores = self.bm25.get_scores(query_tokens)
        valid_indices = [
            index for index, chunk in enumerate(self.chunks)
            if chunk["chunk_id"] in eligible_ids
        ]
        lexical_order = sorted(
            valid_indices, key=lambda index: float(bm25_scores[index]), reverse=True
        )

        dense_scores: dict[int, float] = {}
        if self.mode == "hybrid":
            query = f"query: {question}" if self._e5_model else question
            query_embedding = self.encoder.encode(
                [query], normalize_embeddings=True, convert_to_numpy=True
            )[0]
            similarities = self.embeddings @ query_embedding
            dense_scores = {index: float(similarities[index]) for index in valid_indices}
            dense_order = sorted(valid_indices, key=lambda index: dense_scores[index], reverse=True)
        else:
            dense_order = []

        bm25_order = [i for i in lexical_order if bm25_scores[i] > 0]
        bm25_ranks = {index: rank for rank, index in enumerate(bm25_order, start=1)}
        dense_ranks = {index: rank for rank, index in enumerate(dense_order, start=1)}

        hits: list[RetrievalHit] = []
        for index in valid_indices:
            lexical = float(bm25_scores[index])
            cosine = dense_scores.get(index)
            if self.mode == "bm25":
                fused_score = lexical
            else:
                fused_score = 0.0
                if index in bm25_ranks:
                    fused_score += 1.0 / (RRF_K + bm25_ranks[index])
                if index in dense_ranks:
                    fused_score += 1.0 / (RRF_K + dense_ranks[index])
            fused_score *= self._source_adjustment(self.chunks[index])
            hits.append(RetrievalHit(self.chunks[index], fused_score, lexical, cosine))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        top_hits = hits[:top_k]
        best_lexical = max((hit.bm25_score for hit in hits), default=0.0)
        lexical_evidence = best_lexical / (best_lexical + 3.0) if best_lexical > 0 else 0.0
        question_content = set(tokenize(question))
        content_evidence = set()
        for hit in top_hits[: min(3, len(top_hits))]:
            content_evidence.update(tokenize(hit.chunk["chunk_text"]))
        content_coverage = (
            len(question_content & content_evidence) / len(question_content)
            if question_content
            else 0.0
        )
        if self.mode == "hybrid":
            best_cosine = max(
                (hit.cosine_score for hit in hits if hit.cosine_score is not None),
                default=-1.0,
            )
            dense_evidence = max(0.0, min(1.0, (best_cosine - 0.25) / 0.5))
            confidence = (0.55 * lexical_evidence + 0.45 * dense_evidence) * content_coverage
        else:
            confidence = lexical_evidence * content_coverage
        return top_hits, round(max(0.0, min(1.0, confidence)), 4)
