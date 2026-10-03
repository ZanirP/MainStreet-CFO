"""Seed Arbor Coffee's May–September 2026 history using NessieService.

Run from the repository root: python scripts/seed_nessie.py
Use --dry-run to preview the deterministic plan without API access or a key.
"""

import argparse
from pathlib import Path
import sys
from typing import Any

# Support the requested direct-file invocation from any working directory.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from backend.services.nessie_service import NessieService, NessieServiceError

CUSTOMER = {
    "first_name": "Arbor", "last_name": "Coffee Co.",
    "address": {"street_number": "123", "street_name": "Demo Grove Lane",
                "city": "Ann Arbor", "state": "MI", "zip": "48104"},
}
ACCOUNT_NAME = "Arbor Coffee Co. - Demo Operating Checking"
MERCHANT_NAME = "MainStreet Demo Coffee Shop Suppliers"
CASH_BALANCE = 26000
MONTHS = [(5, 22000, 17000), (6, 23500, 17800), (7, 25000, 18500),
          (8, 26500, 19500), (9, 28000, 20500)]
# Existing staff payroll explains a realistic labor-intensive coffee shop's costs.
OBLIGATIONS = [
    ("Rent", "Demo Grove Properties", 3600, 1),
    ("Utilities", "Demo Michigan Utilities", 650, 10),
    ("Internet", "Demo Business Internet", 100, 12),
    ("Insurance", "Demo Business Insurance", 350, 15),
    ("Software / POS", "Demo Coffee POS", 200, 20),
    ("Existing staff payroll", "Arbor Coffee Payroll", 8500, 28),
]
SUPPLIES = [("Coffee beans", 35), ("Milk and dairy", 15),
            ("Cups and packaging", 10), ("Bakery inventory", 20),
            ("Cleaning supplies", 5), ("Equipment maintenance", 8),
            ("Other operating supplies", 7)]


class SeedError(RuntimeError):
    """A safe seed failure without upstream response bodies."""


def build_plan() -> dict[str, list[dict[str, Any]]]:
    """Exactly match monthly targets with integer-dollar, dated records."""
    deposits, purchases, bills = [], [], []
    fixed_cost = sum(amount for _, _, amount, _ in OBLIGATIONS)
    for month, revenue, expenses in MONTHS:
        prefix = f"2026-{month:02d}"
        catering = revenue // 10
        weekly_total = revenue - catering
        for week, day in enumerate((5, 12, 19, 26)):
            amount = weekly_total // 4 + (1 if week < weekly_total % 4 else 0)
            deposits.append({"medium": "balance", "transaction_date": f"{prefix}-{day:02d}",
                             "status": "completed", "amount": amount,
                             "description": f"Arbor Coffee weekly card sales - week {week + 1}"})
        deposits.append({"medium": "balance", "transaction_date": f"{prefix}-28",
                         "status": "completed", "amount": catering,
                         "description": "Arbor Coffee catering and office coffee orders"})
        budget = expenses - fixed_cost
        allocated = 0
        for index, (description, weight) in enumerate(SUPPLIES):
            amount = budget * weight // 100 if index < len(SUPPLIES) - 1 else budget - allocated
            allocated += amount
            purchases.append({"medium": "balance", "purchase_date": f"{prefix}-{index + 18:02d}",
                              "status": "completed", "amount": amount,
                              "description": description})
    for nickname, payee, amount, day in OBLIGATIONS:
        bills.append({"status": "recurring", "payee": payee, "nickname": nickname,
                      "payment_date": f"2026-10-{day:02d}", "recurring_date": day,
                      "payment_amount": amount})
    return {"deposits": deposits, "purchases": purchases, "bills": bills}


def records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise SeedError("Unexpected Nessie list response; stopped to avoid duplicate creation")
    return value


def is_arbor(customer: dict[str, Any]) -> bool:
    name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}"
    return " ".join(name.casefold().split()).rstrip('.') == "arbor coffee co"


def accepted(response: Any) -> Any:
    # Some APIs wrap an error code in an otherwise successful HTTP response.
    if isinstance(response, dict) and isinstance(response.get("code"), int) and response["code"] >= 400:
        raise SeedError(f"Nessie rejected the operation (code {response['code']})")
    return response


def created_id(response: Any) -> str | None:
    accepted(response)
    if isinstance(response, dict):
        resource = response.get("objectCreated", response)
        if isinstance(resource, dict):
            value = resource.get("_id")
            if isinstance(value, str) and value.strip():
                return value
    return None


def require_id(value: Any, resource: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SeedError(f"Nessie did not return a usable {resource} ID; stopped")
    return value


def find_id(items: list[dict[str, Any]], field: str, value: str) -> str | None:
    matches = [item for item in items if item.get(field) == value]
    return matches[0].get("_id") if len(matches) == 1 else None


def seed(service: NessieService) -> str:
    customers = records(service.get_customers())
    existing = next((customer for customer in customers if is_arbor(customer)), None)
    if existing is not None:
        customer_id = require_id(existing.get("_id"), "customer")
        print(f"Arbor Coffee Co. already exists. Reusing customer: {customer_id}")

        accounts = records(service.get_customer_accounts(customer_id))
        existing_account = next(
            (account for account in accounts if account.get("nickname") == ACCOUNT_NAME),
            None,
        )

        if existing_account is not None:
            account_id = require_id(existing_account.get("_id"), "account")
            print("Demo account already exists; no records were created.")
            print(f"Account ID: {account_id}")
            return customer_id

    # Retrieve actual merchant IDs. Create a minimal supported demo merchant only
    # if none are available; never send made-up IDs in a purchase.
    merchants = records(service.get_merchants())
    merchant_id = find_id(merchants, "name", MERCHANT_NAME)
    if not merchant_id and merchants:
        merchant_id = merchants[0].get("_id")
    if not merchant_id:
        merchant_id = created_id(service.create_merchant({"name": MERCHANT_NAME}))
        if not merchant_id:
            merchant_id = find_id(records(service.get_merchants()), "name", MERCHANT_NAME)
        print("Demo supplier merchant created.")
    merchant_id = require_id(merchant_id, "merchant")

    customer_id = created_id(service.create_customer(CUSTOMER))
    if not customer_id:
        matches = [customer for customer in records(service.get_customers()) if is_arbor(customer)]
        customer_id = matches[0].get("_id") if len(matches) == 1 else None
    customer_id = require_id(customer_id, "customer")
    print(f"Customer created. Customer ID: {customer_id}", flush=True)
    account_id = created_id(service.create_account(customer_id, {
        "type": "Checking", "nickname": ACCOUNT_NAME, "rewards": 0, "balance": CASH_BALANCE,
    }))
    if not account_id:
        account_id = find_id(records(service.get_customer_accounts(customer_id)), "nickname", ACCOUNT_NAME)
    account_id = require_id(account_id, "account")
    print(f"Account created. Account ID: {account_id}", flush=True)

    plan = build_plan()
    for kind, method in (("deposits", service.create_deposit),
                         ("purchases", service.create_purchase), ("bills", service.create_bill)):
        for index, payload in enumerate(plan[kind], start=1):
            body = {**payload, "merchant_id": merchant_id} if kind == "purchases" else payload
            try:
                accepted(method(account_id, body))
            except (NessieServiceError, SeedError) as exc:
                raise SeedError(f"Failed creating {kind} record {index}: {exc}. "
                                "Partial data remains; rerunning will stop at the existing customer.") from None
        print(f"{kind.capitalize()} created: {len(plan[kind])}", flush=True)

    account = service.get_account(account_id)
    if not isinstance(account, dict) or not isinstance(account.get("balance"), (int, float)):
        raise SeedError("Could not verify the current cash balance")
    balance = account["balance"]
    print(f"Current cash balance: ${balance:,.2f}")
    if not 24000 <= balance <= 28000:
        raise SeedError("Historical transactions changed the cash balance outside the demo target. "
                        "Records were created, but balance verification failed; inspect before rerunning.")
    print("Seeding complete.")
    print(f"Customer ID: {customer_id}")
    return customer_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview amounts without any API access")
    args = parser.parse_args()
    if args.dry_run:
        print("Arbor Coffee Co. demo plan (no API requests):")
        for month, revenue, expenses in MONTHS:
            print(f"2026-{month:02d}: revenue ${revenue:,}; expenses ${expenses:,}; net ${revenue - expenses:,}")
        for kind, items in build_plan().items():
            print(f"{kind.capitalize()}: {len(items)}")
        print(f"Account balance at creation: ${CASH_BALANCE:,}")
        return 0
    load_dotenv(ROOT / ".env")
    try:
        seed(NessieService())
    except (NessieServiceError, SeedError) as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1
    except ValueError:
        print("Seed failed: set NESSIE_API_KEY in the root .env file", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
