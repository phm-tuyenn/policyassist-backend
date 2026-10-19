from datetime import date
from typing import Any


def parse_optional_date(value: str | None, field_name: str, record_id: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Ngày không hợp lệ ở {field_name} của {record_id}: {value}") from exc


def is_effective(chunk: dict[str, Any], reference_date: date) -> bool:
    metadata = chunk["document_metadata"]
    start_text = chunk.get("effective_from") or metadata.get("effective_date")
    end_text = chunk.get("effective_to") or metadata.get("expiry_date")
    start = parse_optional_date(start_text, "effective_from", chunk["chunk_id"])
    end = parse_optional_date(end_text, "effective_to", chunk["chunk_id"])
    if start and reference_date < start:
        return False
    if end and reference_date > end:
        return False
    return True


def filter_effective_chunks(
    chunks: list[dict[str, Any]], reference_date: date
) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if is_effective(chunk, reference_date)]
