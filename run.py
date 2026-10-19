import argparse
import sys
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any

from policyassist.abstention import missing_record_evidence
from policyassist.answering import generate_answer, validate_supporting_citations
from policyassist.data import load_corpus, load_questions, write_submission
from policyassist.retrieval import RetrievalEngine


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = APP_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chạy pipeline hỏi-đáp PolicyAssist AI")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_DATA_DIR / "04_questions" / "questions_sample.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=APP_DIR / "output" / "submission.csv",
    )
    parser.add_argument("--retrieval", choices=("bm25", "hybrid"), default="bm25")
    parser.add_argument(
        "--embedding-model",
        default="intfloat/multilingual-e5-base",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-confidence", type=float, default=0.18)
    parser.add_argument("--default-reference-date", type=date.fromisoformat, default=date(2026, 10, 17))
    parser.add_argument("--llm", action="store_true", help="Bật LLM qua OpenAI-compatible API")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()
    if not 0 <= args.min_confidence <= 1:
        parser.error("--min-confidence phải nằm trong khoảng 0..1")
    if args.top_k < 1:
        parser.error("--top-k phải lớn hơn 0")
    return args


def _question_date(value: str, default: date, question_id: str) -> date:
    if not value.strip():
        return default
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"reference_date không hợp lệ ở {question_id}: {value}") from exc


def process_question(
    row: dict[str, str],
    engine: RetrievalEngine,
    args: argparse.Namespace,
) -> dict[str, Any]:
    started = perf_counter()
    reference_date = _question_date(
        row.get("reference_date", ""),
        args.default_reference_date,
        row["question_id"],
    )
    hits, confidence = engine.retrieve(
        row["question_text"],
        reference_date,
        top_k=args.top_k,
    )
    abstain = (
        not hits
        or confidence < args.min_confidence
        or missing_record_evidence(row["question_text"], hits)
    )
    if abstain:
        answer_text = "Không đủ căn cứ trong Data Pack để xác định thông tin này."
        supporting_hits = []
        citations: list[str] = []
        document_ids: list[str] = []
        chunk_ids: list[str] = []
        if not hits:
            confidence = 0.0
    else:
        answer = generate_answer(
            row["question_text"],
            hits,
            use_llm=args.llm,
            model=args.model,
        )
        hit_by_id = {hit.chunk["chunk_id"]: hit for hit in hits}
        supporting_hits = [hit_by_id[chunk_id] for chunk_id in answer.supporting_chunk_ids]
        citations = validate_supporting_citations(answer, supporting_hits)
        if args.llm and not supporting_hits:
            abstain = True
            answer_text = "Không đủ căn cứ trong Data Pack để xác định thông tin này."
            citations = []
            document_ids = []
            chunk_ids = []
        else:
            answer_text = answer.answer
            document_ids = list(dict.fromkeys(hit.chunk["document_id"] for hit in supporting_hits))
            chunk_ids = [hit.chunk["chunk_id"] for hit in supporting_hits]

    latency_ms = round((perf_counter() - started) * 1000)
    return {
        "question_id": row["question_id"],
        "answer": answer_text,
        "retrieved_document_ids": ";".join(document_ids),
        "retrieved_chunk_ids": ";".join(chunk_ids),
        "citations": ";".join(citations),
        "confidence": round(confidence, 4),
        "abstain": "TRUE" if abstain else "FALSE",
        "latency_ms": latency_ms,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    chunks, _ = load_corpus(args.data_dir)
    questions = load_questions(args.questions)
    if len({row["question_id"] for row in questions}) != len(questions):
        raise ValueError(f"Tệp câu hỏi có question_id trùng lặp: {args.questions}")
    engine = RetrievalEngine(
        chunks,
        mode=args.retrieval,
        embedding_model=args.embedding_model,
    )
    results = [process_question(row, engine, args) for row in questions]
    write_submission(args.output, results)
    abstentions = sum(row["abstain"] == "TRUE" for row in results)
    print(
        f"Đã xử lý {len(results)} câu hỏi; ABSTAIN={abstentions}; "
        f"đã ghi {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
