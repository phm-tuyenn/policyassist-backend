import csv
from pathlib import Path
from typing import Any


CHUNK_COLUMNS = {"chunk_id", "document_id", "chunk_text", "source_type"}
DOCUMENT_COLUMNS = {"document_id", "effective_date", "expiry_date"}
CITATION_COLUMNS = {"chunk_id", "citation_label"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp dữ liệu: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _validate_columns(path: Path, rows: list[dict[str, str]], required: set[str]) -> None:
    actual = set(rows[0]) if rows else set()
    missing = sorted(required - actual)
    if missing:
        raise ValueError(f"{path} thiếu các cột bắt buộc: {', '.join(missing)}")


def load_corpus(data_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    chunks_path = data_dir / "03_metadata" / "legal_chunks.csv"
    documents_path = data_dir / "03_metadata" / "document_metadata.csv"
    citations_path = data_dir / "citation_map.csv"
    chunks = read_csv(chunks_path)
    documents = read_csv(documents_path)
    citations = read_csv(citations_path)

    _validate_columns(chunks_path, chunks, CHUNK_COLUMNS)
    _validate_columns(documents_path, documents, DOCUMENT_COLUMNS)
    _validate_columns(citations_path, citations, CITATION_COLUMNS)
    if not chunks:
        raise ValueError(f"Corpus không có chunk nào: {chunks_path}")

    document_by_id = {row["document_id"]: row for row in documents}
    citation_by_chunk = {row["chunk_id"]: row for row in citations}
    if len(document_by_id) != len(documents):
        raise ValueError("document_metadata.csv có document_id trùng lặp")
    if len(citation_by_chunk) != len(citations):
        raise ValueError("citation_map.csv có chunk_id trùng lặp")

    seen_chunk_ids: set[str] = set()
    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        if chunk_id in seen_chunk_ids:
            raise ValueError(f"legal_chunks.csv có chunk_id trùng lặp: {chunk_id}")
        seen_chunk_ids.add(chunk_id)
        document = document_by_id.get(chunk["document_id"])
        if document is None:
            raise ValueError(f"Không tìm thấy metadata cho document_id={chunk['document_id']}")
        citation = citation_by_chunk.get(chunk_id)
        if citation is None:
            raise ValueError(f"Không tìm thấy citation map cho chunk_id={chunk_id}")
        chunk["document_metadata"] = document
        chunk["citation_label"] = chunk.get("citation_label") or citation.get("citation_label", "")
        chunk["canonical_citation"] = citation.get("canonical_citation", "")
        if not chunk["chunk_text"].strip():
            raise ValueError(f"Chunk không có nội dung: {chunk_id}")
        if not chunk["citation_label"]:
            raise ValueError(f"Chunk không có citation_label: {chunk_id}")
    return chunks, document_by_id


def load_questions(path: Path) -> list[dict[str, str]]:
    rows = read_csv(path)
    _validate_columns(path, rows, {"question_id", "question_text", "reference_date"})
    for row in rows:
        if not row["question_id"] or not row["question_text"]:
            raise ValueError(f"Câu hỏi thiếu ID hoặc nội dung trong {path}")
    return rows


def write_submission(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "question_id",
        "answer",
        "retrieved_document_ids",
        "retrieved_chunk_ids",
        "citations",
        "confidence",
        "abstain",
        "latency_ms",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
