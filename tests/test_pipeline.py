import csv
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policyassist.data import load_corpus, write_submission
from policyassist.abstention import TAX_ID_QUESTION, missing_record_evidence
from policyassist.retrieval import RetrievalEngine
from policyassist.versioning import filter_effective_chunks


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT


class PolicyAssistPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chunks, _ = load_corpus(DATA_DIR)

    def test_corpus_and_citation_map_are_consistent(self) -> None:
        self.assertEqual(len(self.chunks), 374)
        self.assertTrue(all(chunk["citation_label"] for chunk in self.chunks))

    def test_version_filter_excludes_future_and_expired_chunks(self) -> None:
        as_of_2025 = filter_effective_chunks(self.chunks, date(2025, 5, 15))
        as_of_2026 = filter_effective_chunks(self.chunks, date(2026, 8, 15))
        historical = {chunk["document_id"] for chunk in as_of_2025}
        current = {chunk["document_id"] for chunk in as_of_2026}
        self.assertIn("LAW04", historical)
        self.assertNotIn("LAW10", historical)
        self.assertNotIn("LAW04", current)
        self.assertIn("LAW10", current)

    def test_bm25_retrieves_expected_concept_with_citation(self) -> None:
        engine = RetrievalEngine(self.chunks, mode="bm25")
        hits, confidence = engine.retrieve(
            "Theo Data Pack, chứng từ kế toán được hiểu là gì?",
            date(2026, 10, 17),
            top_k=5,
        )
        self.assertGreater(confidence, 0)
        self.assertTrue(hits)
        self.assertEqual(hits[0].chunk["chunk_id"], "LAW01_C001")
        self.assertIn("LAW01 – Điều 3 khoản 3", hits[0].chunk["citation_label"])

    def test_missing_specific_company_records_are_abstained(self) -> None:
        engine = RetrievalEngine(self.chunks, mode="bm25")
        requests = [
            ("Mã số thuế chính thức của Công ty Cổ phần Nova Việt là bao nhiêu?", "2026-10-17"),
            ("Nhà cung cấp dịch vụ hóa đơn điện tử cụ thể mà Nova Việt đang ký hợp đồng là công ty nào?", "2026-10-17"),
            ("Nova Việt có đang bị cơ quan thuế thanh tra tại thời điểm 17/10/2026 hay không?", "2026-10-17"),
            ("Tỷ giá USD/VND mà Nova Việt sử dụng để hạch toán một giao dịch ngày 17/10/2026 là bao nhiêu?", "2026-10-17"),
        ]
        for question, reference_date in requests:
            with self.subTest(question=question):
                hits, _ = engine.retrieve(question, date.fromisoformat(reference_date), top_k=5)
                self.assertTrue(missing_record_evidence(question, hits))

    def test_tax_id_procedure_question_is_not_misclassified_as_record_lookup(self) -> None:
        question = (
            "Nếu hóa đơn điện tử đã lập bị sai mã số thuế, số tiền hoặc thuế suất "
            "thì phương án xử lý hiện hành là gì?"
        )
        self.assertIsNone(TAX_ID_QUESTION.search(question))

    def test_submission_has_exact_required_columns_and_csv_encoding(self) -> None:
        import tempfile

        row = {
            "question_id": "Q001",
            "answer": "Trả lời có dấu tiếng Việt.",
            "retrieved_document_ids": "LAW01",
            "retrieved_chunk_ids": "LAW01_C001",
            "citations": "LAW01 – Điều 3 khoản 3",
            "confidence": 0.9,
            "abstain": "FALSE",
            "latency_ms": 10,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "submission.csv"
            write_submission(path, [row])
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                result = list(csv.DictReader(file))
            self.assertEqual(list(result[0]), list(row))
            self.assertEqual(result[0]["answer"], row["answer"])


if __name__ == "__main__":
    unittest.main()
