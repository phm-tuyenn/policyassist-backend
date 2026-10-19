import json
import os
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .retrieval import RetrievalHit


class GeneratedAnswer(BaseModel):
    answer: str = Field(min_length=1)
    supporting_chunk_ids: list[str]


def _extractive_answer(hits: list[RetrievalHit]) -> GeneratedAnswer:
    snippets = []
    supporting_ids = []
    for hit in hits:
        chunk = hit.chunk
        snippets.append(f"{chunk['chunk_text'].strip()} ({chunk['citation_label']})")
        supporting_ids.append(chunk["chunk_id"])
    return GeneratedAnswer(
        answer=" ".join(snippets),
        supporting_chunk_ids=supporting_ids,
    )


def _llm_answer(
    question: str,
    hits: list[RetrievalHit],
    model: str,
) -> GeneratedAnswer:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "LLM cần openai. Cài dependencies bằng: "
            "python -m pip install -r requirements-optional.txt"
        ) from exc
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Đã bật --llm nhưng chưa đặt biến môi trường OPENAI_API_KEY")

    client = OpenAI(api_key=api_key, base_url=os.environ.get("OPENAI_BASE_URL"))
    evidence = [
        {
            "chunk_id": hit.chunk["chunk_id"],
            "source_type": hit.chunk["source_type"],
            "document_title": hit.chunk["document_title"],
            "citation_label": hit.chunk["citation_label"],
            "content_type": hit.chunk.get("content_type", ""),
            "text": hit.chunk["chunk_text"],
        }
        for hit in hits
    ]
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Trả lời bằng tiếng Việt chỉ dựa trên evidence JSON. "
                    "Không suy đoán hoặc bổ sung kiến thức ngoài nguồn. "
                    "Không trình bày NORMALIZED_SUMMARY như nguyên văn pháp luật. "
                    "Trả về JSON có answer và supporting_chunk_ids; "
                    "supporting_chunk_ids chỉ gồm chunk_id thực sự hỗ trợ câu trả lời. "
                    "Nếu evidence không đủ, answer phải là "
                    "'Không đủ căn cứ trong Data Pack để xác định thông tin này.' "
                    "và supporting_chunk_ids là mảng rỗng."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"question": question, "evidence": evidence},
                    ensure_ascii=False,
                ),
            },
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM trả về nội dung rỗng")
    try:
        answer = GeneratedAnswer.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError(f"LLM trả về JSON không đúng schema: {content}") from exc
    allowed_ids = {hit.chunk["chunk_id"] for hit in hits}
    invalid_ids = set(answer.supporting_chunk_ids) - allowed_ids
    if invalid_ids:
        raise ValueError(f"LLM tham chiếu chunk không được truy xuất: {sorted(invalid_ids)}")
    if len(set(answer.supporting_chunk_ids)) != len(answer.supporting_chunk_ids):
        raise ValueError("LLM trả về supporting_chunk_ids bị trùng")
    return answer


def generate_answer(
    question: str,
    hits: list[RetrievalHit],
    use_llm: bool = False,
    model: str = "gpt-4o-mini",
) -> GeneratedAnswer:
    if not hits:
        return GeneratedAnswer(
            answer="Không đủ căn cứ trong Data Pack để xác định thông tin này.",
            supporting_chunk_ids=[],
        )
    return _llm_answer(question, hits, model) if use_llm else _extractive_answer(hits)


def validate_supporting_citations(
    answer: GeneratedAnswer,
    hits: list[RetrievalHit],
) -> list[str]:
    chunk_by_id = {hit.chunk["chunk_id"]: hit.chunk for hit in hits}
    unknown = set(answer.supporting_chunk_ids) - set(chunk_by_id)
    if unknown:
        raise ValueError(f"Chunk hỗ trợ không thuộc kết quả retrieval: {sorted(unknown)}")
    return list(dict.fromkeys(
        chunk_by_id[chunk_id]["citation_label"]
        for chunk_id in answer.supporting_chunk_ids
    ))
