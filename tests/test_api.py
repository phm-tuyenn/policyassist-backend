import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from api import app


class PolicyAssistApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def test_health_reports_loaded_corpus(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["chunks"], 374)
        self.assertEqual(response.json()["retrieval"], "bm25")
        self.assertEqual(
            self.client.app.state.data_dir,
            Path(__file__).resolve().parents[1] / "data",
        )

    def test_homepage_serves_api_documentation_and_playground(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Thử hỏi đáp", response.text)
        self.assertIn('fetch("/ask"', response.text)
        self.assertIn('href="/docs"', response.text)

    def test_ask_returns_answer_and_citation(self) -> None:
        response = self.client.post(
            "/ask",
            json={"question": "Theo Data Pack, chứng từ kế toán được hiểu là gì?"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["abstain"])
        self.assertIn("LAW01 – Điều 3 khoản 3", body["citations"])
        self.assertIn("LAW01_C001", body["retrieved_chunk_ids"])
        self.assertEqual(body["reference_date"], "2026-10-17")

    def test_ask_abstains_on_missing_company_record(self) -> None:
        response = self.client.post(
            "/ask",
            json={"question": "Mã số thuế chính thức của Công ty Cổ phần Nova Việt là bao nhiêu?"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["abstain"])
        self.assertEqual(body["citations"], [])

    def test_ask_rejects_invalid_top_k(self) -> None:
        response = self.client.post(
            "/ask",
            json={"question": "Chứng từ kế toán là gì?", "top_k": 11},
        )
        self.assertEqual(response.status_code, 422)

    def test_malformed_json_returns_actionable_error(self) -> None:
        response = self.client.post(
            "/ask",
            content='{"question": "Chứng từ kế toán là gì?", reference_date: "2026-10-17"}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("JSON.stringify(data)", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
