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
            ("get_customer", ("c",), "GET", "/customers/c"),
            ("get_customer_accounts", ("c",), "GET", "/customers/c/accounts"),
            ("get_account", ("a",), "GET", "/accounts/a"),
            ("get_purchases", ("a",), "GET", "/accounts/a/purchases"),
            ("get_deposits", ("a",), "GET", "/accounts/a/deposits"),
            ("get_bills", ("a",), "GET", "/accounts/a/bills"),
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


if __name__ == "__main__":
    unittest.main()
