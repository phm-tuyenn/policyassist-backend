import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import sys

from policyassist.data import load_corpus, read_csv
from policyassist.retrieval import RetrievalEngine


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = APP_DIR.parent


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Đánh giá Recall@5 từ answer key")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--answer-key",
        type=Path,
        default=DEFAULT_DATA_DIR / "05_answer_sample" / "answer_key_sample.csv",
    )
    parser.add_argument("--retrieval", choices=("bm25", "hybrid"), default="bm25")
    parser.add_argument("--embedding-model", default="intfloat/multilingual-e5-base")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    chunks, _ = load_corpus(args.data_dir)
    rows = read_csv(args.answer_key)
    required = {"question_id", "question_text", "reference_date", "relevant_chunk_ids"}
    if not rows or required - set(rows[0]):
        raise ValueError(f"Answer key thiếu cột: {', '.join(sorted(required - set(rows[0] if rows else [])))}")
    engine = RetrievalEngine(chunks, args.retrieval, args.embedding_model)
    evaluated = 0
    hits_at_k = 0
    per_question = []
    behaviors = Counter(row.get("expected_behavior", "") for row in rows)
    for row in rows:
        expected = {item for item in row["relevant_chunk_ids"].split(";") if item}
        if not expected:
            continue
        retrieved, _ = engine.retrieve(
            row["question_text"],
            date.fromisoformat(row["reference_date"]),
            top_k=args.top_k,
        )
        retrieved_ids = {hit.chunk["chunk_id"] for hit in retrieved}
        found = bool(expected & retrieved_ids)
        evaluated += 1
        hits_at_k += int(found)
        per_question.append((row["question_id"], found, expected & retrieved_ids))
    if evaluated == 0:
        raise ValueError("Không có câu hỏi nào có relevant_chunk_ids để đánh giá")
    print(f"Recall@{args.top_k}: {hits_at_k}/{evaluated} = {hits_at_k / evaluated:.3f}")
    print(f"Câu hỏi theo expected_behavior: {dict(behaviors)}")
    for question_id, found, matched in per_question:
        if not found:
            print(f"MISS {question_id}: không tìm thấy chunk tham chiếu ở top-{args.top_k}")
        elif len(matched) > 1:
            print(f"HIT  {question_id}: {', '.join(sorted(matched))}")


if __name__ == "__main__":
    main()
