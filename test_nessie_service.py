"""Offline contract and credential-safety checks: python -m unittest test_nessie_service."""
import os
import traceback
import unittest
from unittest.mock import Mock, patch

import requests
from backend.services.nessie_service import NessieService, NessieServiceError


class NessieServiceTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"NESSIE_API_KEY": "test-secret"})
        env.start()
        self.addCleanup(env.stop)
        self.service = NessieService()

    @patch("backend.services.nessie_service.requests.request")
    def test_routes_auth_and_json(self, request):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True}
        request.return_value = response
        payload = {"nickname": "demo"}
        cases = [
            ("get_customers", (), "GET", "/customers"),
            ("get_merchants", (), "GET", "/merchants"),
            ("create_merchant", (payload,), "POST", "/merchants"),
            ("get_customer", ("c",), "GET", "/customers/c"),
            ("get_customer_accounts", ("c",), "GET", "/customers/c/accounts"),
            ("get_account", ("a",), "GET", "/accounts/a"),
            ("delete_account", ("a",), "DELETE", "/accounts/a"),
            ("get_purchases", ("a",), "GET", "/accounts/a/purchases"),
            ("get_deposits", ("a",), "GET", "/accounts/a/deposits"),
            ("get_bills", ("a",), "GET", "/accounts/a/bills"),
            ("get_loans", ("a",), "GET", "/accounts/a/loans"),
            ("create_loan", ("a", payload), "POST", "/accounts/a/loans"),
            ("create_customer", (payload,), "POST", "/customers"),
            ("create_account", ("c", payload), "POST", "/customers/c/accounts"),
            ("create_purchase", ("a", payload), "POST", "/accounts/a/purchases"),
            ("create_deposit", ("a", payload), "POST", "/accounts/a/deposits"),
            ("create_bill", ("a", payload), "POST", "/accounts/a/bills"),
        ]
        for name, args, verb, path in cases:
            with self.subTest(name=name):
                response.status_code = 201 if verb == "POST" else 200
                self.assertEqual(getattr(self.service, name)(*args), {"ok": True})
                request.assert_called_with(
                    verb, self.service.BASE_URL + path,
                    params={"key": "test-secret"},
                    json=payload if verb == "POST" else None,
                    timeout=15, allow_redirects=False,
                )

    @patch("backend.services.nessie_service.requests.request")
    def test_loan_json_contract_is_preserved(self, request):
        loan = {"_id": "a" * 24, "type": "business", "status": "active",
                "creation_date": "2026-10-03", "credit_score": 700,
                "monthly_payment": 1200, "amount": 48000, "description": "Demo equipment"}
        response = Mock(status_code=200)
        response.json.return_value = [loan]
        request.return_value = response
        self.assertEqual(self.service.get_loans("account/id"), [loan])
        self.assertEqual(request.call_args.args[1], self.service.BASE_URL + "/accounts/account%2Fid/loans")
        payload = {key: value for key, value in loan.items() if key not in ("_id", "creation_date")}
        response.status_code = 201
        response.json.return_value = {"code": 201, "message": "Loan created"}
        self.assertEqual(self.service.create_loan("a", payload)["code"], 201)
        self.assertEqual(request.call_args.kwargs["json"], payload)

    @patch("backend.services.nessie_service.requests.request")
    def test_bill_readback_error_has_safe_route_and_narrow_reason(self, request):
        response = Mock(status_code=400)
        response.json.return_value = (
            "2 validation errors for Bill\nrecurring_date\n"
            "  field required (type=value_error.missing)\nupcoming_payment_date\n"
            "  field required (type=value_error.missing)"
        )
        request.return_value = response
        with self.assertRaises(NessieServiceError) as caught:
            self.service.get_bills("test-secret")
        error = caught.exception
        self.assertEqual(error.method, "GET")
        self.assertEqual(error.path, "/accounts/{id}/bills")
        self.assertEqual(error.reason, "bill_readback_missing_schedule")
        self.assertIn("GET /accounts/{id}/bills", str(error))
        self.assertNotIn("test-secret", str(error))
        self.assertNotIn("value_error", str(error))
        # The same body from a different request, or a different 400, cannot
        # authorize the seed's specific recovery path.
        with self.assertRaises(NessieServiceError) as caught:
            self.service.get_loans("a")
        self.assertIsNone(caught.exception.reason)
        response.json.return_value = "Invalid account or API key: test-secret"
        with self.assertRaises(NessieServiceError) as caught:
            self.service.get_bills("a")
        self.assertIsNone(caught.exception.reason)
        self.assertNotIn("test-secret", str(caught.exception))

    @patch("backend.services.nessie_service.requests.request")
    def test_failures_are_sanitized(self, request):
        for status in (302, 400, 401, 404, 429, 500):
            request.return_value = Mock(status_code=status, text="test-secret")
            with self.assertRaises(NessieServiceError) as caught:
                self.service.get_customers()
            self.assertEqual(caught.exception.status_code, status)
            self.assertNotIn("test-secret", str(caught.exception))
        for error in (requests.ConnectionError("url?key=test-secret"), requests.Timeout("test-secret")):
            request.side_effect = error
            try:
                self.service.get_customers()
            except NessieServiceError:
                self.assertNotIn("test-secret", traceback.format_exc())
            else:
                self.fail("Expected sanitized network failure")
        request.side_effect = None
        request.return_value = Mock(status_code=200)
        request.return_value.json.side_effect = ValueError("test-secret")
        with self.assertRaisesRegex(NessieServiceError, "invalid JSON"):
            self.service.get_customers()

    def test_missing_key_and_empty_id(self):
        with patch.dict(os.environ, {"NESSIE_API_KEY": ""}):
            with self.assertRaises(ValueError):
                NessieService()
        with self.assertRaises(ValueError):
            self.service.get_customer("")

    @patch("backend.services.nessie_service.requests.request")
    def test_account_delete_accepts_success_without_a_json_body(self, request):
        for status in (200, 204):
            response = Mock(status_code=status, content=b"")
            request.return_value = response
            self.assertIsNone(self.service.delete_account("demo-account"))
            response.json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
