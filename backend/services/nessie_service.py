"""Nessie API access; verified routes and payloads are documented in README.md."""

import os
from urllib.parse import quote

from dotenv import load_dotenv
import requests

load_dotenv()


class NessieServiceError(RuntimeError):
    """Sanitized failure without credentials or authenticated URLs."""

    def __init__(self, message, status_code=None, *, method=None, path=None, reason=None):
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.path = path
        self.reason = reason


class NessieService:
    BASE_URL = "https://api.nessieisreal.com"

    def __init__(self, timeout=15):
        self._api_key = os.getenv("NESSIE_API_KEY")
        if not self._api_key or not self._api_key.strip():
            raise ValueError("NESSIE_API_KEY must be set in the environment")
        self.timeout = timeout

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A non-empty resource ID is required")
        return quote(value, safe="")

    def _request(self, method, path, payload=None):
        # Report the route with IDs masked, never a URL or credential-bearing query.
        resources = {"customers", "accounts", "merchants", "purchases", "deposits", "bills", "loans"}
        route = "/" + "/".join(part if part in resources else "{id}" for part in path.split("/") if part)
        operation = f"{method} {route}"
        try:
            response = requests.request(
                method, self.BASE_URL + path,
                params={"key": self._api_key}, json=payload,
                timeout=self.timeout, allow_redirects=False,
            )
        except requests.RequestException:
            # requests errors can include the authenticated URL.
            raise NessieServiceError(f"Nessie {operation} failed (network or timeout)",
                                     method=method, path=route) from None
        if not 200 <= response.status_code < 300:
            # Classify only the exact observed server serialization defect. Never
            # expose its body, and never treat an arbitrary 400 as permission to replace.
            reason = None
            if method == "GET" and route == "/accounts/{id}/bills" and response.status_code == 400:
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if isinstance(body, str) and [line.strip() for line in body.splitlines()] == [
                    "2 validation errors for Bill", "recurring_date",
                    "field required (type=value_error.missing)", "upcoming_payment_date",
                    "field required (type=value_error.missing)",
                ]:
                    reason = "bill_readback_missing_schedule"
            raise NessieServiceError(
                f"Nessie {operation} returned HTTP {response.status_code}" +
                (" (bill response is missing required schedule fields)" if reason else ""),
                response.status_code, method=method, path=route, reason=reason,
            )
        if method == "DELETE" and (response.status_code == 204 or response.content == b""):
            return None
        try:
            return response.json()
        except ValueError:
            raise NessieServiceError(f"Nessie {operation} returned invalid JSON",
                                     method=method, path=route) from None

    def get_customers(self):
        return self._request("GET", "/customers")

    def get_merchants(self):
        """GET /merchants, verified against the official OpenAPI specification."""
        return self._request("GET", "/merchants")

    def create_merchant(self, payload):
        """POST /merchants; the documented minimum body contains name."""
        return self._request("POST", "/merchants", payload)

    def get_customer(self, customer_id):
        return self._request("GET", f"/customers/{self._id(customer_id)}")

    def get_customer_accounts(self, customer_id):
        return self._request("GET", f"/customers/{self._id(customer_id)}/accounts")

    def get_account(self, account_id):
        return self._request("GET", f"/accounts/{self._id(account_id)}")

    def delete_account(self, account_id):
        """DELETE /accounts/{id}, verified in the official OpenAPI and SDK.

        Only the seed's explicit replacement mode uses this operation.
        """
        return self._request("DELETE", f"/accounts/{self._id(account_id)}")

    def get_purchases(self, account_id):
        return self._request("GET", f"/accounts/{self._id(account_id)}/purchases")

    def get_deposits(self, account_id):
        return self._request("GET", f"/accounts/{self._id(account_id)}/deposits")

    def get_bills(self, account_id):
        return self._request("GET", f"/accounts/{self._id(account_id)}/bills")

    def get_loans(self, account_id):
        """GET /accounts/{id}/loans, verified in Nessie's official OpenAPI."""
        return self._request("GET", f"/accounts/{self._id(account_id)}/loans")

    def create_loan(self, account_id, payload):
        """LoanCreate: type, status, credit_score, monthly_payment, amount, description.

        creation_date is supplied by Nessie. Amount is not documented as the
        remaining principal; this contract supplies no APR or repayment term.
        """
        return self._request("POST", f"/accounts/{self._id(account_id)}/loans", payload)

    def create_customer(self, payload):
        """Send first_name, last_name, and address (see README)."""
        return self._request("POST", "/customers", payload)

    def create_account(self, customer_id, payload):
        """Send type, nickname, rewards, and balance."""
        return self._request("POST", f"/customers/{self._id(customer_id)}/accounts", payload)

    def create_purchase(self, account_id, payload):
        """Send merchant_id, medium, purchase_date, amount, status, description."""
        return self._request("POST", f"/accounts/{self._id(account_id)}/purchases", payload)

    def create_deposit(self, account_id, payload):
        """Send medium, transaction_date, status, amount, and description."""
        return self._request("POST", f"/accounts/{self._id(account_id)}/deposits", payload)

    def create_bill(self, account_id, payload):
        """Send status, payee, payment_amount, and optional scheduling fields."""
        return self._request("POST", f"/accounts/{self._id(account_id)}/bills", payload)
