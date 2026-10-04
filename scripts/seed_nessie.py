"""Seed three contrasting May–September 2026 demo businesses through NessieService.

Preview: .venv/bin/python scripts/seed_nessie.py --dry-run
Seed:    .venv/bin/python scripts/seed_nessie.py
Use --replace-existing to rebuild only recognized demo operating accounts.
"""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from backend.services.financial_analyzer import FinancialAnalyzer
from backend.services.nessie_service import NessieService, NessieServiceError
from backend.services.scenario_engine import ScenarioEngine

MONTH_NUMBERS = (5, 6, 7, 8, 9)
VERSION = "May-Sep 2026 v3 debt"

# Numbers represent actual invoice/payment composition, not labels or conclusions.
# Series align with May, June, July, August and September respectively.
BUSINESSES = {
    "arbor": {
        "loan": {"type": "business", "status": "active", "credit_score": 700, "monthly_payment": 1200,
                 "amount": 48000, "description": "Demo Arbor startup buildout and espresso equipment"},
        "name": "Arbor Coffee Co.", "first_name": "Arbor", "last_name": "Coffee Co.",
        "street_number": "123", "street_name": "Demo Grove Lane", "cash": 9000,
        "revenue": (18500, 20500, 23000, 25500, 27000),
        "expenses": (21500, 22000, 22500, 23500, 25500),
        "bills": [
            ("Rent", "Demo Grove Properties", (3200,) * 5, 1),
            ("Staff payroll", "Arbor Coffee Payroll", (10000, 10200, 10400, 10800, 11200), 28),
            ("Utilities", "Demo Michigan Utilities", (650, 700, 800, 900, 1050), 10),
            ("Internet", "Demo Business Internet", (100,) * 5, 12),
            ("Insurance", "Demo Business Insurance", (350,) * 5, 15),
            ("POS / software", "Demo Coffee POS", (200,) * 5, 20),
        ],
        "purchases": [
            ("Coffee beans", "Demo Great Lakes Coffee Roasters", (2200, 2450, 2700, 3000, 3300), 2),
            ("Milk and dairy", "Demo Washtenaw Dairy Supply", (1000, 1050, 1200, 1250, 1250), 4),
            ("Bakery inventory", "Demo Grove Bakery Wholesale", (1500, 1500, 1650, 1650, 1550), 4),
            ("Cups and packaging", "Demo EcoCup Packaging", (850, 950, 1000, 1100, 1050), 2),
            ("Cleaning supplies", "Demo Michigan Janitorial Supply", (250, 250, 280, 300, 300), 1),
            ("Equipment maintenance", "Demo Espresso ServiceWorks", (800, 450, 220, 350, 1750), 1),
            ("Other operating supplies", "Demo Arbor Operating Supply", (400, 600, 400, 300, 200), 1),
        ],
    },
    "market": {
        "loan": {"type": "business", "status": "active", "credit_score": 700, "monthly_payment": 1800,
                 "amount": 90000, "description": "Demo Market store fixtures and refrigeration"},
        "name": "MainStreet Market", "first_name": "MainStreet", "last_name": "Market",
        "street_number": "245", "street_name": "Demo Maple Street", "cash": 15000,
        "revenue": (52000, 51000, 50000, 49000, 48000),
        "expenses": (48000, 49000, 50000, 51000, 53000),
        "bills": [
            ("Rent", "Demo Maple Retail Properties", (4000,) * 5, 1),
            ("Staff payroll", "MainStreet Market Payroll", (10000, 10000, 10200, 10300, 10500), 28),
            ("Utilities / refrigeration", "Demo Michigan Utilities", (1200, 1400, 1600, 1800, 2200), 10),
            ("Insurance", "Demo Business Insurance", (600,) * 5, 15),
            ("POS / software", "Demo Market POS", (350,) * 5, 20),
            ("Internet", "Demo Business Internet", (150,) * 5, 12),
        ],
        "purchases": [
            ("Wholesale grocery inventory", "Demo Midwest Grocery Wholesale", (21000, 21600, 22200, 22700, 23500), 2),
            ("Produce inventory", "Demo Michigan Produce Co.", (5000, 4900, 4800, 4700, 4600), 4),
            ("Refrigerated and frozen inventory", "Demo Great Lakes Cold Storage", (4800, 4900, 5000, 5200, 5500), 2),
            ("Cleaning and sanitation", "Demo Michigan Janitorial Supply", (500, 550, 600, 650, 700), 1),
            # An actual cash service expense; do not count lost inventory value twice.
            ("Waste collection and spoiled-stock disposal", "Demo Neighborhood Waste Services", (400, 550, 500, 550, 650), 1),
            ("Refrigeration maintenance", "Demo Cold Room Services", (0, 0, 0, 0, 250), 1),
        ],
    },
    "arcade": {
        "loan": {"type": "business", "status": "active", "credit_score": 700, "monthly_payment": 600,
                 "amount": 18000, "description": "Demo Pixel Palace arcade cabinet equipment"},
        "name": "Pixel Palace Arcade", "first_name": "Pixel Palace", "last_name": "Arcade",
        "street_number": "380", "street_name": "Demo Liberty Court", "cash": 85000,
        "revenue": (42000, 40000, 44000, 43000, 45000),
        "expenses": (31000, 31000, 32000, 32000, 33000),
        "bills": [
            ("Rent", "Demo Liberty Entertainment Properties", (6000,) * 5, 1),
            ("Staff payroll", "Pixel Palace Payroll", (14500, 14500, 15000, 15000, 15500), 28),
            ("Utilities", "Demo Michigan Utilities", (2300, 2250, 2450, 2400, 2600), 10),
            ("Game / software licensing", "Demo Arcade Licensing", (1200, 1250, 1300, 1300, 1350), 18),
            ("Insurance", "Demo Business Insurance", (750,) * 5, 15),
            ("POS / software", "Demo Arcade POS", (250,) * 5, 20),
            ("Internet", "Demo Business Internet", (200,) * 5, 12),
        ],
        "purchases": [
            ("Concessions inventory", "Demo Concession Supply", (2300, 2200, 2400, 2300, 2500), 4),
            ("Machine maintenance", "Demo GameTech Repair", (1800, 1900, 2400, 1950, 1950), 1),
            ("Redemption prizes", "Demo Prize Wholesale", (1000, 1100, 900, 1100, 1150), 2),
            ("Cleaning supplies", "Demo Michigan Janitorial Supply", (400, 450, 350, 400, 450), 1),
            ("Other operating supplies", "Demo Arcade Operating Supply", (300, 150, 0, 350, 300), 1),
        ],
    },
}


class SeedError(RuntimeError):
    """Safe seeding failure without upstream response bodies or credentials."""


def split_amount(total: int, count: int, offset: int) -> list[int]:
    """Uneven integer-dollar installments, exactly preserving an invoice total."""
    weights = (19, 27, 23, 31) if count == 4 else (47, 53) if count == 2 else (14, 18, 17, 16, 19, 16) if count == 6 else (100,)
    rotated = weights[offset % count:] + weights[:offset % count]
    amounts = [total * weight // sum(rotated) for weight in rotated[:-1]]
    return amounts + [total - sum(amounts)]


def customer_payload(business: dict[str, Any]) -> dict[str, Any]:
    return {"first_name": business["first_name"], "last_name": business["last_name"],
            "address": {"street_number": business["street_number"], "street_name": business["street_name"],
                        "city": "Ann Arbor", "state": "MI", "zip": "48104"}}


def account_name(business: dict[str, Any]) -> str:
    return f"{business['name']} - Demo Operating Checking ({VERSION})"


def opening_cash(business: dict[str, Any]) -> int:
    return business["cash"] - sum(r - e for r, e in zip(business["revenue"], business["expenses"]))


def build_plan(business_key: str = "arbor") -> dict[str, list[dict[str, Any]]]:
    """Generate valid payloads; purchase merchant names are resolved before posting.

    Historical bills are completed payments; October recurring records are
    obligations only and must not be counted again in realized expenses.
    Historical monthly obligations include their real recurrence day: Nessie's
    live Bill read model otherwise rejects missing recurring/upcoming date fields
    even though BillCreate accepts the POST. Nessie generates the upcoming date.
    """
    business = BUSINESSES[business_key]
    deposits, purchases, bills = [], [], []
    for index, month in enumerate(MONTH_NUMBERS):
        prefix = f"2026-{month:02d}"
        revenue = business["revenue"][index]
        if business_key == "arbor":
            catering = (1500, 2200, 2600, 3400, 3600)[index]
            streams = [("Weekly card sales", revenue - catering, 4, (5, 12, 19, 26)),
                       ("Catering / office coffee orders", catering, 2, (10, 24))]
        elif business_key == "market":
            streams = [("Grocery card-sales settlement", revenue, 6, (5, 10, 15, 20, 25, 30))]
        else:
            events, concessions = (6500, 5500, 7000, 6500, 7500)[index], (3500, 3500, 3700, 3600, 3900)[index]
            streams = [("Arcade admissions and card reloads", revenue - events - concessions, 4, (5, 12, 19, 26)),
                       ("Parties and events", events, 2, (14, 27)),
                       ("Concessions sales settlement", concessions, 2, (13, 28))]
        for description, total, count, days in streams:
            for part, (amount, day) in enumerate(zip(split_amount(total, count, index), days), 1):
                deposits.append({"medium": "balance", "transaction_date": f"{prefix}-{day:02d}",
                                 "status": "completed", "amount": amount,
                                 "description": f"{business['name']}: {description} / settlement {part}"})
        for category_index, (description, merchant, amounts, count) in enumerate(business["purchases"]):
            total = amounts[index]
            if not total:
                continue
            if business_key == "arbor" and description == "Equipment maintenance" and month == 9:
                description = "Espresso-machine pump repair and service"
            if business_key == "arcade" and description == "Machine maintenance" and month == 7:
                description = "Arcade cabinet motherboard replacement and repair"
            days = (4, 11, 18, 25) if count == 4 else (9, 23) if count == 2 else (16 + category_index,)
            for part, (amount, day) in enumerate(zip(split_amount(total, count, index + category_index), days), 1):
                purchases.append({"medium": "balance", "purchase_date": f"{prefix}-{day:02d}",
                                  "status": "completed", "amount": amount,
                                  "description": f"{description} / invoice {part}", "_merchant_name": merchant})
        for nickname, payee, amounts, day in business["bills"]:
            # Reclassify part of the old operating budget into debt payments,
            # preserving every month's total cash expenses and final cash.
            payment = amounts[index] - (business["loan"]["monthly_payment"] if nickname == "Staff payroll" else 0)
            bills.append({"status": "completed", "payee": payee, "nickname": nickname,
                          "payment_date": f"{prefix}-{day:02d}", "recurring_date": day,
                          "payment_amount": payment})
        bills.append({"status": "completed", "payee": "Demo Business Equipment Finance",
                      "nickname": f"Debt payment: {business['loan']['description']}",
                      "payment_date": f"{prefix}-27", "recurring_date": 27,
                      "payment_amount": business["loan"]["monthly_payment"]})
    for nickname, payee, amounts, day in business["bills"]:
        bills.append({"status": "recurring", "payee": payee, "nickname": nickname,
                      "payment_date": f"2026-10-{day:02d}", "recurring_date": day,
                      "payment_amount": amounts[-1] - (business["loan"]["monthly_payment"] if nickname == "Staff payroll" else 0)})
    bills.append({"status": "recurring", "payee": "Demo Business Equipment Finance",
                  "nickname": f"Debt payment: {business['loan']['description']}", "payment_date": "2026-10-27",
                  "recurring_date": 27, "payment_amount": business["loan"]["monthly_payment"]})
    return {"deposits": deposits, "purchases": purchases, "bills": bills, "loans": [dict(business["loan"])]}


def records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise SeedError("Unexpected Nessie list response; stopped to avoid duplicates")
    return value


def accepted(response: Any) -> Any:
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


def normalized_name(customer: dict[str, Any]) -> str:
    return " ".join(f"{customer.get('first_name', '')} {customer.get('last_name', '')}".casefold().split()).rstrip('.')


def read_plan(service: NessieService, account_id: str) -> dict[str, list[dict[str, Any]]]:
    return {"deposits": records(service.get_deposits(account_id)),
            "purchases": records(service.get_purchases(account_id)),
            "bills": records(service.get_bills(account_id)),
            "loans": records(service.get_loans(account_id))}


def same_records(actual: list[dict[str, Any]], expected: list[dict[str, Any]]) -> bool:
    """Compare only contract fields, ignoring server IDs and scheduling metadata."""
    fields = set().union(*(item.keys() for item in expected)) if expected else set()
    def signature(item):
        return tuple((field, item.get(field))
                     for field in sorted(fields))
    try:
        return Counter(signature(item) for item in actual) == Counter(signature(item) for item in expected)
    except TypeError:
        return False  # Unexpected nested contract values are not a verified match.


def cash_amount(account: Any) -> Decimal:
    try:
        if not isinstance(account, dict) or isinstance(account.get("balance"), bool):
            raise ValueError
        amount = Decimal(str(account.get("balance")))
        if not amount.is_finite():
            raise ValueError
        return amount
    except (InvalidOperation, ValueError):
        raise SeedError("Could not verify the account's current cash balance") from None


def resolve_merchants(service: NessieService, plans: dict[str, Any]) -> dict[str, str]:
    existing = records(service.get_merchants())
    merchant_ids = {}
    names = sorted({item["_merchant_name"] for plan in plans.values() for item in plan["purchases"]})
    for name in names:
        matches = [merchant for merchant in existing if merchant.get("name") == name]
        if len(matches) > 1:
            raise SeedError(f"Multiple merchants named {name}; inspect before seeding")
        merchant_id = require_id(matches[0].get("_id"), "merchant") if matches else created_id(service.create_merchant({"name": name}))
        if not merchant_id:
            # Some Nessie responses return only an acknowledgement.
            matches = [item for item in records(service.get_merchants()) if item.get("name") == name]
            if len(matches) == 1:
                merchant_id = matches[0].get("_id")
        merchant_ids[name] = require_id(merchant_id, "merchant")
    return merchant_ids


def resolved_plan(plan: dict[str, Any], merchant_ids: dict[str, str]) -> dict[str, Any]:
    return {kind: [{**{key: value for key, value in item.items() if key != "_merchant_name"},
                    **({"merchant_id": merchant_ids[item["_merchant_name"]]} if kind == "purchases" else {})}
                  for item in items] for kind, items in plan.items()}


def preflight(service: NessieService, selected: list[str]) -> dict[str, tuple[str | None, dict[str, Any] | None]]:
    """Identify existing customers/accounts before writes; never touch unrelated accounts.

    Earlier script versions accidentally left an empty duplicate Arbor customer.
    Reuse the single populated customer and leave that empty duplicate untouched.
    Multiple populated matches are ambiguous and must be resolved manually.
    """
    customers = records(service.get_customers())
    result = {}
    for key in selected:
        business = BUSINESSES[key]
        matches = [customer for customer in customers if normalized_name(customer) == business["name"].casefold().rstrip('.')]
        candidates = []
        for customer in matches:
            expected_address = customer_payload(business)["address"]
            address = customer.get("address")
            if not isinstance(address, dict) or any(str(address.get(field, "")).strip().casefold() != value.casefold()
                                                    for field, value in expected_address.items()):
                raise SeedError(f"{business['name']}: matching name has a different address; ownership cannot be established")
            customer_id = require_id(customer.get("_id"), "customer")
            accounts = records(service.get_customer_accounts(customer_id))
            known = {account_name(business), f"{business['name']} - Demo Operating Checking",
                     f"{business['name']} - Demo Operating Checking (May-Sep 2026 v2)"}
            if any(account.get("nickname") not in known for account in accounts):
                raise SeedError(f"{business['name']} has accounts outside this seed's ownership; stopped")
            if len(accounts) > 1:
                raise SeedError(f"{business['name']} has multiple operating accounts; inspect before seeding")
            candidates.append((customer_id, accounts[0] if accounts else None))
        populated = [item for item in candidates if item[1] is not None]
        if len(populated) > 1:
            raise SeedError(f"Multiple populated customers named {business['name']}; stopped to avoid duplicates")
        if len(candidates) > 1:
            print(f"{business['name']}: existing empty duplicate customer(s) left untouched; no new customer will be created.")
        result[key] = populated[0] if populated else sorted(candidates, key=lambda item: item[0])[0] if candidates else (None, None)
    return result


def analyze_plan(business: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    analysis = FinancialAnalyzer().analyze_business(accounts=[{"type": "Checking", "balance": business["cash"]}], **plan)
    for field, targets in (("monthly_revenue", business["revenue"]), ("monthly_expenses", business["expenses"])):
        expected = [{"month": f"2026-{month:02d}", "amount": amount} for month, amount in zip(MONTH_NUMBERS, targets)]
        if analysis[field] != expected:
            raise SeedError(f"{business['name']}: generated plan does not match {field} targets; stopped before API writes")
    return analysis


def verify(service: NessieService, business: dict[str, Any], account_id: str,
           expected: dict[str, Any]) -> dict[str, Any]:
    actual = read_plan(service, account_id)
    if any(not same_records(actual[kind], expected[kind]) for kind in expected):
        raise SeedError(f"{business['name']}: returned records differ from the plan (including status/date/amount). Inspect before rerunning; partial data is not considered complete.")
    account = service.get_account(account_id)
    if cash_amount(account) != business["cash"]:
        raise SeedError(f"{business['name']}: balance verification failed. Expected ${business['cash']:,}; historical postings changed the balance. Check --balance-mode before explicitly replacing this demo account.")
    return FinancialAnalyzer().analyze_business(accounts=[account], **actual)


def seed(service: NessieService, *, selected: list[str] | None = None,
         replace_existing: bool = False, balance_mode: str = "snapshot") -> dict[str, str]:
    """Create once or verify existing data. Partial/mismatched accounts need explicit replacement.

    Snapshot mode uses Nessie's observed unchanged historical-posting balance.
    Ledger mode starts from cash minus historical net. Both require exact final
    balance and read-back verification; there is no artificial balancing deposit.
    """
    selected = list(BUSINESSES) if selected is None else list(dict.fromkeys(selected))
    if not selected or any(key not in BUSINESSES for key in selected):
        raise SeedError("Choose one or more supported demo businesses")
    if balance_mode not in ("snapshot", "ledger"):
        raise SeedError("balance_mode must be snapshot or ledger")
    plans = {key: build_plan(key) for key in selected}
    for key, plan in plans.items():
        analyze_plan(BUSINESSES[key], plan)
    existing = preflight(service, selected)
    # Refuse obvious legacy accounts before creating merchants or other businesses.
    if not replace_existing:
        for key, (_, account) in existing.items():
            if account is not None and account.get("nickname") != account_name(BUSINESSES[key]):
                raise SeedError(f"{BUSINESSES[key]['name']}: legacy demo account exists. Use --replace-existing to rebuild only that demo account, without creating a duplicate customer.")
    merchant_ids = resolve_merchants(service, plans)
    plans = {key: resolved_plan(plan, merchant_ids) for key, plan in plans.items()}
    # Check every existing account before any account deletion/customer creation.
    complete = set()
    for key, (_, account) in existing.items():
        if account is None:
            continue
        account_id = require_id(account.get("_id"), "account")
        try:
            if account.get("nickname") != account_name(BUSINESSES[key]):
                raise SeedError("Legacy plan")
            verify(service, BUSINESSES[key], account_id, plans[key])
            complete.add(key)
        except NessieServiceError as exc:
            if exc.reason != "bill_readback_missing_schedule":
                raise  # Network/auth/rate limits and unrelated errors never trigger replacement.
            if not replace_existing:
                raise SeedError(f"{BUSINESSES[key]['name']}: existing bills were accepted by Nessie but cannot be read because schedule fields are missing. No records changed. Use --replace-existing to rebuild only this recognized demo account with valid monthly bill schedules.") from None
            print(f"{BUSINESSES[key]['name']}: confirmed bills readback schema defect; explicit replacement requested for this owned demo account.")
        except SeedError:
            if not replace_existing:
                raise SeedError(f"{BUSINESSES[key]['name']}: demo data is partial, changed, or has a different balance. No transactions will be appended. Use --replace-existing to rebuild this demo account.") from None
    customer_ids = {}
    for key in selected:
        business = BUSINESSES[key]
        customer_id, account = existing[key]
        if key in complete:
            print(f"{business['name']}: existing dataset verified; no records created.")
            customer_ids[key] = customer_id
            continue
        if account is not None:
            account_id = require_id(account.get("_id"), "account")
            accepted(service.delete_account(account_id))
            # Do not create a second account if deletion was not effective.
            if records(service.get_customer_accounts(customer_id)):
                raise SeedError(f"{business['name']}: demo account deletion could not be verified; stopped")
            print(f"{business['name']}: old demo account removed; rebuilding under the same customer.")
        if customer_id is None:
            customer_id = created_id(service.create_customer(customer_payload(business)))
            if not customer_id:
                matches = [c for c in records(service.get_customers()) if normalized_name(c) == business["name"].casefold().rstrip('.')]
                customer_id = matches[0].get("_id") if len(matches) == 1 else None
            customer_id = require_id(customer_id, "customer")
            print(f"{business['name']}: customer created ({customer_id}).", flush=True)
        else:
            print(f"{business['name']}: reusing customer ({customer_id}).", flush=True)
        initial = business["cash"] if balance_mode == "snapshot" else opening_cash(business)
        account_id = created_id(service.create_account(customer_id, {
            "type": "Checking", "nickname": account_name(business), "rewards": 0, "balance": initial,
        }))
        if not account_id:
            matches = [a for a in records(service.get_customer_accounts(customer_id)) if a.get("nickname") == account_name(business)]
            account_id = matches[0].get("_id") if len(matches) == 1 else None
        account_id = require_id(account_id, "account")
        print(f"{business['name']}: account created ({account_id}); API opening balance ${initial:,} [{balance_mode}].", flush=True)
        methods = {"deposits": service.create_deposit, "purchases": service.create_purchase,
                   "bills": service.create_bill, "loans": service.create_loan}
        operations = [(kind, index, item) for kind, items in plans[key].items() for index, item in enumerate(items, 1)]
        operations.sort(key=lambda op: (op[2].get("transaction_date") or op[2].get("purchase_date") or op[2].get("payment_date") or "", op[0]))
        for kind, index, item in operations:
            try:
                accepted(methods[kind](account_id, item))
            except (NessieServiceError, SeedError):
                raise SeedError(f"{business['name']}: failed creating {kind} record {index}. Partial demo account remains; rerun will refuse to append. Inspect the payload/response status and use --replace-existing only when ready to rebuild.") from None
        for kind, items in plans[key].items():
            print(f"{business['name']}: {kind} created: {len(items)}.")
        print(f"{business['name']}: verifying returned transactions, bills, loans and final account balance.", flush=True)
        verify(service, business, account_id, plans[key])
        customer_ids[key] = customer_id
        print(f"{business['name']}: raw records and final cash verified (${business['cash']:,}).", flush=True)
    print("Seeding complete. Customer IDs:")
    for key, customer_id in customer_ids.items():
        print(f"  {BUSINESSES[key]['name']}: {customer_id}")
    return customer_ids


def preview(selected: list[str], balance_mode: str) -> None:
    print("Deterministic demo plan — no Nessie or Gemini API requests.")
    for key in selected:
        business, plan = BUSINESSES[key], build_plan(key)
        analysis = analyze_plan(business, plan)
        print(f"\n{business['name']}")
        print(f"  Economic opening cash: ${opening_cash(business):,}; current cash target: ${business['cash']:,}")
        initial = business["cash"] if balance_mode == "snapshot" else opening_cash(business)
        print(f"  Account creation balance [{balance_mode}]: ${initial:,}")
        for index, month in enumerate(MONTH_NUMBERS):
            revenue, expenses = business["revenue"][index], business["expenses"][index]
            print(f"  2026-{month:02d}: revenue ${revenue:,}; expenses ${expenses:,}; net ${revenue - expenses:+,}")
        for label, _, amounts, _ in (*business["bills"], *business["purchases"]):
            if label == "Staff payroll":
                amounts = tuple(value - business["loan"]["monthly_payment"] for value in amounts)
            print(f"    {label}: " + " / ".join(f"${value:,}" for value in amounts))
        loan = business["loan"]
        print(f"  Existing loan: {loan['description']}; reported loan amount ${loan['amount']:,}; monthly payment ${loan['monthly_payment']:,} (already in expenses).")
        print("  Loan APR, outstanding balance and remaining term unavailable; required credit_score is synthetic demo metadata, not underwriting.")
        print("  Records: " + ", ".join(f"{kind}={len(items)}" for kind, items in plan.items()))
        recurring = sum(bill["payment_amount"] for bill in plan["bills"] if bill["status"] == "recurring")
        print(f"  October recurring obligations (not realized expenses): ${recurring:,}")
        for signal in analysis["signals"]:
            print(f"  [{signal['level']}] {signal['title']}: {signal['value']} {signal['unit']}")
        hire = ScenarioEngine().simulate_hire(analysis, 18, 30)
        print(f"  $18 × 30h hire: monthly cash flow ${hire['projected_monthly_cash_flow']:,.2f}; six-month cash ${hire['cash_projection'][-1]['scenario']:,.2f}")
    print("\nSnapshot mode: historical POSTs must leave cash unchanged. Ledger mode: completed postings must apply their net to economic opening cash.")
    print("Every real seed verifies exact returned records and final cash. No balancing revenue/expense records are added.")


def validate_cfo(service: NessieService, customer_ids: dict[str, str]) -> bool:
    """Opt-in live explanation using real read-back data, never scripted answers."""
    from backend.services.cfo_assistant import CFOAssistant, CFOAssistantError
    assistant = CFOAssistant()
    question = "Is my current debt manageable?"
    success = True
    for key, customer_id in customer_ids.items():
        accounts = records(service.get_customer_accounts(customer_id))
        aggregate = {"deposits": [], "purchases": [], "bills": [], "loans": []}
        for account in accounts:
            for kind, items in read_plan(service, require_id(account.get("_id"), "account")).items():
                aggregate[kind].extend(items)
        analysis = FinancialAnalyzer().analyze_business(accounts=accounts, **aggregate)
        try:
            result = assistant.ask(analysis, question)
            print(f"\n{BUSINESSES[key]['name']} — {question}\n{result['answer']}")
        except CFOAssistantError as exc:
            print(f"{BUSINESSES[key]['name']}: CFO validation unavailable: {exc}", file=sys.stderr)
            success = False
    return success


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview all figures without API access")
    parser.add_argument("--business", choices=list(BUSINESSES), help="Limit to one business; default is all three")
    parser.add_argument("--replace-existing", action="store_true", help="Rebuild mismatched recognized demo accounts, preserving their customers")
    parser.add_argument("--balance-mode", choices=("snapshot", "ledger"), default="snapshot", help="snapshot matches observed Nessie behavior; ledger compensates if postings change cash")
    parser.add_argument("--validate-cfo", action="store_true", help="After verification, ask Gemini the same debt-manageability question for each business")
    args = parser.parse_args(argv)
    selected = [args.business] if args.business else list(BUSINESSES)
    if args.dry_run:
        preview(selected, args.balance_mode)
        return 0
    load_dotenv(ROOT / ".env")
    try:
        service = NessieService()
        customer_ids = seed(service, selected=selected, replace_existing=args.replace_existing, balance_mode=args.balance_mode)
        if args.validate_cfo:
            from backend.services.cfo_assistant import CFOAssistantError
            try:
                if not validate_cfo(service, customer_ids):
                    return 1
            except (CFOAssistantError, NessieServiceError, SeedError) as exc:
                print(f"Seeding succeeded, but CFO validation was unavailable: {exc}", file=sys.stderr)
                return 1
    except (NessieServiceError, SeedError) as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1
    except ValueError:
        print("Seed failed: check NESSIE_API_KEY and the supported seed configuration", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
