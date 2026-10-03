"""API wiring checks; Nessie requests are mocked."""
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app import app, get_nessie_service
from backend.services.nessie_service import NessieService, NessieServiceError


class AppTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock(spec=NessieService)
        app.dependency_overrides[get_nessie_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_health_without_api_key(self):
        app.dependency_overrides.clear()
        with patch("backend.app.NessieService", side_effect=ValueError("secret")):
            self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
            response = self.client.get("/businesses")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("secret", response.text)

    def test_businesses(self):
        self.service.get_customers.return_value = [{"_id": "c", "first_name": "Shop"}]
        response = self.client.get("/businesses")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.service.get_customers.return_value)
        self.service.get_customers.assert_called_once_with()

    def test_analysis_aggregates_all_accounts(self):
        accounts = [{"_id": "a", "type": "Checking", "balance": 100},
                    {"_id": "b", "type": "Credit Card", "balance": 500}]
        self.service.get_customer_accounts.return_value = accounts
        self.service.get_deposits.side_effect = [[{"amount": 50}], [{"amount": 25}]]
        self.service.get_purchases.side_effect = [[{"amount": 10}], [{"amount": 20}]]
        self.service.get_bills.side_effect = [[], [{"payment_amount": 5}]]
        response = self.client.get("/businesses/c/analysis")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], {
            "revenue": 75, "expenses": 35, "net_cash_flow": 40,
            "cash_balance": 100, "margin": 53.33})
        self.service.get_customer_accounts.assert_called_once_with("c")
        for method in (self.service.get_deposits, self.service.get_purchases, self.service.get_bills):
            self.assertEqual([call.args for call in method.call_args_list], [("a",), ("b",)])

    def test_empty_accounts(self):
        self.service.get_customer_accounts.return_value = []
        response = self.client.get("/businesses/c/analysis")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["revenue"], 0)
        self.service.get_deposits.assert_not_called()

    def test_sanitized_errors(self):
        for upstream, expected in [(404, 404), (429, 503), (401, 502), (500, 502), (None, 502)]:
            with self.subTest(upstream=upstream):
                self.service.get_customers.side_effect = NessieServiceError("key=secret", upstream)
                response = self.client.get("/businesses")
                self.assertEqual(response.status_code, expected)
                self.assertNotIn("secret", response.text)
        self.service.get_customer_accounts.return_value = [{"_id": "a"}]
        self.service.get_deposits.side_effect = NessieServiceError("secret", 500)
        response = self.client.get("/businesses/c/analysis")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret", response.text)
        self.service.get_purchases.assert_not_called()

    def test_malformed_upstream_data(self):
        for accounts in ({"error": "secret"}, [{"balance": 10}], [None]):
            self.service.get_customer_accounts.return_value = accounts
            response = self.client.get("/businesses/c/analysis")
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("secret", response.text)

    def test_cors(self):
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            response = self.client.options("/businesses", headers={
                "Origin": origin, "Access-Control-Request-Method": "GET"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)
        response = self.client.options("/businesses", headers={
            "Origin": "https://example.com", "Access-Control-Request-Method": "GET"})
        self.assertEqual(response.status_code, 400)

    def test_hire_scenario(self):
        self.service.get_customer_accounts.return_value = [{"_id": "a", "balance": 24000}]
        self.service.get_deposits.return_value = [{"amount": 10000, "transaction_date": "2026-10-01"}]
        self.service.get_purchases.return_value = [{"amount": 3000, "purchase_date": "2026-10-02"}]
        self.service.get_bills.return_value = []
        response = self.client.post("/businesses/c/scenarios/hire", json={"hourly_wage": 18, "hours_per_week": 30})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["monthly_added_cost"], 2340)
        self.assertEqual(response.json()["cash_projection"][0],
                         {"month": "2026-11", "baseline": 31000, "scenario": 28660})
        self.assertEqual(len(response.json()["cash_projection"]), 6)
        self.service.get_customer_accounts.assert_called_once_with("c")

    def test_hire_input_validation(self):
        for field, value in [("hourly_wage", -1), ("hours_per_week", -1),
                             ("months", 0), ("months", -1), ("months", 1.5),
                             ("months", True), ("hourly_wage", True),
                             ("hourly_wage", "NaN"), ("hours_per_week", None)]:
            payload = {"hourly_wage": 18, "hours_per_week": 30, "months": 6, field: value}
            with self.subTest(field=field, value=value):
                response = self.client.post("/businesses/c/scenarios/hire", json=payload)
                self.assertEqual(response.status_code, 422)
        self.service.get_customer_accounts.assert_not_called()

    def test_hire_missing_history_and_nessie_failure(self):
        self.service.get_customer_accounts.return_value = []
        response = self.client.post("/businesses/c/scenarios/hire", json={"hourly_wage": 18, "hours_per_week": 30})
        self.assertEqual(response.status_code, 422)
        self.assertIn("history", response.json()["detail"])
        self.service.get_customer_accounts.side_effect = NessieServiceError("key=secret", 500)
        response = self.client.post("/businesses/c/scenarios/hire", json={"hourly_wage": 18, "hours_per_week": 30})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret", response.text)

    def test_hire_cors_preflight(self):
        response = self.client.options("/businesses/c/scenarios/hire", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")


if __name__ == "__main__":
    unittest.main()
