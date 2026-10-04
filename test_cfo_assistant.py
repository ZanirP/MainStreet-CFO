"""Deterministic context, grounding, and secret-free Gemini failures."""
import copy
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient

from backend.app import app, get_cfo_assistant, get_nessie_service
from backend.services.cfo_assistant import CFOAssistant, CFOAssistantError
from backend.services.financial_analyzer import FinancialAnalyzer


def analysis():
    return FinancialAnalyzer().analyze_business(
        accounts=[{"balance": 24000}],
        deposits=[{"amount": 11000, "transaction_date": "2026-10-01"}],
        purchases=[{"amount": 4000, "purchase_date": "2026-10-01"}],
    )


def intent(kind="hire", **inputs):
    return {"kind": kind, "hourly_wage": None, "hours_per_week": None,
            "amount": None, "months": None, **inputs}


class CFOTests(unittest.TestCase):
    def setUp(self):
        config = patch.dict("os.environ", {"GEMINI_API_KEY": "test-secret", "GEMINI_MODEL": "gemini-3.5-flash-lite"})
        config.start()
        self.addCleanup(config.stop)
        self.assistant = CFOAssistant()

    def test_hire_context_and_drop_threshold(self):
        source = analysis()
        original = copy.deepcopy(source)
        context, error = self.assistant.build_context(source, "Hire at $20 for 30 hours", intent(hourly_wage=20, hours_per_week=30))
        self.assertIsNone(error)
        self.assertEqual(source, original)
        self.assertEqual(context["scenario"]["monthly_added_cost"], 2600)
        self.assertEqual(context["scenario"]["cash_projection"][-1]["scenario"], 50400)
        self.assertEqual(context["revenue_drop_limit"]["monthly_revenue_drop_amount"], 4400)
        self.assertEqual(context["revenue_drop_limit"]["monthly_revenue_drop_percent"], 40)
        self.assertIn("breaking_point", context["scenario"]["stress_test"])
        self.assertTrue(context["assumptions"]["default_projection_months"])

    def test_projection_and_one_time_context(self):
        for kind in ("equipment", "withdrawal", "projection"):
            inputs = intent(kind, amount=10000 if kind != "projection" else None, months=6)
            context, error = self.assistant.build_context(analysis(), "10000 after six months", inputs)
            self.assertIsNone(error)
            result = context["projection" if kind == "projection" else "scenario"]
            self.assertEqual(result["cash_projection"][-1]["scenario"], 66000 if kind == "projection" else 56000)
            self.assertFalse(context["assumptions"]["default_projection_months"])

    def test_dated_monthly_net_and_margin_zero_revenue_and_missing_series(self):
        source = {"monthly_revenue": [{"month": "2026-05", "amount": 100}, {"month": "2026-07", "amount": 0}],
                  "monthly_expenses": [{"month": "2026-05", "amount": 40}, {"month": "2026-06", "amount": 50}]}
        original = copy.deepcopy(source)
        rows = CFOAssistant._monthly_performance(source)
        self.assertEqual([row["net_cash_flow"] for row in rows], [60, -50, 0])
        self.assertEqual([row["margin_percent"] for row in rows], [60, None, None])
        self.assertEqual(source, original)
        self.assertEqual(CFOAssistant._monthly_performance({"monthly_revenue": None}), [])

    def test_missing_unsupported_and_unverified_inputs(self):
        for source, question, inputs in (
            (analysis(), "hire", intent()),
            (analysis(), "$20 for 30 hours", intent(hourly_wage=25, hours_per_week=30)),
            (analysis(), "taxes", intent("unsupported")),
            (analysis(), "-20 for 30 hours", intent(hourly_wage=-20, hours_per_week=30)),
            (analysis(), "0 months", intent("projection", months=0)),
            (analysis(), "121 months", intent("projection", months=121)),
            (FinancialAnalyzer().analyze_business(), "cash", intent("general")),
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(self.assistant.build_context(source, question, inputs)[1])

    def test_grounding_rejects_invented_values(self):
        facts = [{"id": "f0", "value": 24000, "label": "cash", "source": "historical"}]
        answer, used = self.assistant._ground_answer("Cash is $[[f0]].", facts)
        self.assertEqual(answer, "Cash is $24,000.00.")
        self.assertEqual(used, facts)
        for text in (None, "", "Cash is 9000", "Cash is [[f999]]", "[[f0]] will double", "[[f0]] lasts three months"):
            with self.assertRaises(CFOAssistantError):
                self.assistant._ground_answer(text, facts)

    def test_signal_fact_display_preserves_explicit_units(self):
        facts = self.assistant._facts({"signals": [
            {"value": -2.04, "unit": "percent"},
            {"value": 5.96, "unit": "percentage_points"},
            {"value": 0.3, "unit": "months"},
        ]})
        self.assertEqual([f["display"] for f in facts], ["-2.04%", "5.96 percentage points", "0.3 months"])

    def test_full_service_flow(self):
        def generate(instruction, data, schema):
            if "kind" in schema["properties"]:
                return intent("general")
            cash = next(f for f in data["facts"] if f["label"] == "historical.summary.cash_balance")
            return {"answer": f"Your historical cash balance is [[{cash['id']}]]."}
        with patch.object(self.assistant, "_generate", side_effect=generate):
            result = self.assistant.ask(analysis(), "What is my cash balance?")
            self.assertIn("24,000.00", result["answer"])
            self.assertEqual(result["facts"][0]["source"], "historical")
        for question in (" ", "a" * 2001):
            with self.assertRaises(ValueError):
                self.assistant.ask(analysis(), question)

    def test_invalid_answer_has_one_bounded_correction(self):
        with patch.object(self.assistant, "_generate", side_effect=[
            intent("general"), {"answer": "Cash is $999999."},
            {"answer": "Historical cash is [[f3]]."},
        ]) as generate:
            result = self.assistant.ask(analysis(), "What is my cash?")
            self.assertIn("24,000", result["answer"])
            self.assertEqual(generate.call_count, 3)
        with patch.object(self.assistant, "_generate", side_effect=[
            intent("general"), {"answer": "Cash is $999999."}, {"answer": "Cash is $999999."},
        ]) as generate:
            with self.assertRaises(CFOAssistantError):
                self.assistant.ask(analysis(), "What is my cash?")
            self.assertEqual(generate.call_count, 3)

    def test_http_failures_and_malformed_generation_are_sanitized(self):
        with patch("backend.services.cfo_assistant.requests.post", side_effect=requests.Timeout("test-secret")):
            with self.assertRaises(CFOAssistantError) as caught:
                self.assistant._generate("", {}, {})
            self.assertNotIn("test-secret", str(caught.exception))
        for body in ({}, {"candidates": []}, {"candidates": ["invalid"]},
                     {"candidates": [{"finishReason": "STOP", "content": {"parts": ["invalid"]}}]},
                     {"candidates": [{"finishReason": "MAX_TOKENS"}]}):
            with patch("backend.services.cfo_assistant.requests.post", return_value=Mock(status_code=200, json=lambda: body)):
                with self.assertRaises(CFOAssistantError):
                    self.assistant._generate("", {}, {})
        with patch("backend.services.cfo_assistant.requests.post", return_value=Mock(status_code=429)):
            with self.assertRaises(CFOAssistantError) as caught:
                self.assistant._generate("", {}, {})
            self.assertEqual(caught.exception.status_code, 503)

    def test_gemini_request_contract_keeps_secret_in_header(self):
        response = Mock(status_code=200, json=lambda: {"candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": '{"answer":"ok"}'}]},
        }]})
        with patch("backend.services.cfo_assistant.requests.post", return_value=response) as post:
            self.assertEqual(self.assistant._generate("instructions", {"question": "Cash?"}, {}), {"answer": "ok"})
        args, kwargs = post.call_args
        self.assertNotIn("test-secret", args[0])
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "test-secret")
        self.assertNotIn("test-secret", str(kwargs["json"]))
        self.assertEqual(kwargs["json"]["generationConfig"]["responseMimeType"], "application/json")
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            with self.assertRaises(CFOAssistantError) as caught:
                CFOAssistant()
            self.assertEqual(caught.exception.status_code, 503)

    def test_endpoint_reuses_analysis_and_validates(self):
        service = Mock()
        service.get_customer_accounts.return_value = [{"_id": "a", "balance": 24000}]
        service.get_deposits.return_value = [{"amount": 11000, "transaction_date": "2026-10-01"}]
        service.get_purchases.return_value = []
        service.get_bills.return_value = []
        service.get_loans.return_value = []
        assistant = Mock()
        assistant.ask.return_value = {"answer": "Grounded answer", "status": "answered", "facts": [], "context": {}}
        app.dependency_overrides[get_nessie_service] = lambda: service
        app.dependency_overrides[get_cfo_assistant] = lambda: assistant
        self.addCleanup(app.dependency_overrides.clear)
        with TestClient(app) as client:
            response = client.post("/businesses/c/cfo/ask", json={"question": "Cash?"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(assistant.ask.call_args.args[0]["summary"]["cash_balance"], 24000)
            for question in ("", " ", "x" * 2001, 123):
                self.assertEqual(client.post("/businesses/c/cfo/ask", json={"question": question}).status_code, 422)
            assistant.ask.side_effect = CFOAssistantError("CFO temporarily unavailable", 503)
            self.assertEqual(client.post("/businesses/c/cfo/ask", json={"question": "Cash?"}).status_code, 503)
            self.assertEqual(client.get("/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
