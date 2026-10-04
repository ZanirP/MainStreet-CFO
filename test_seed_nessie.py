"""Three raw demo footprints, safe seeding, and CFO context; no live HTTP calls."""
import contextlib
import copy
from datetime import date
import io
import unittest
from unittest.mock import patch

from backend.app import app, get_nessie_service
from backend.services.cfo_assistant import CFOAssistant
from backend.services.financial_analyzer import FinancialAnalyzer
from backend.services.nessie_service import NessieServiceError
from backend.services.scenario_engine import ScenarioEngine
from fastapi.testclient import TestClient
from scripts.seed_nessie import (
    BUSINESSES, MONTH_NUMBERS, SeedError, account_name, analyze_plan, build_plan,
    customer_payload, main, opening_cash, seed,
    validate_cfo,
)


class MemoryNessie:
    """Test-only API double; supports snapshot or posting-based balance semantics."""
    def __init__(self, ledger=False):
        self.customers, self.merchants, self.accounts, self.transactions = [], [], {}, {}
        self.writes = []
        self.ledger = ledger
        self.serial = 0
        self.fail_purchase = False
        self.fail_delete = False

    def _id(self):
        self.serial += 1
        return f"{self.serial:024x}"

    def _created(self, resource):
        return {"code": 201, "objectCreated": copy.deepcopy(resource)}

    def get_customers(self):
        return copy.deepcopy(self.customers)

    def get_merchants(self):
        return copy.deepcopy(self.merchants)

    def create_merchant(self, payload):
        self.writes.append(("merchant", copy.deepcopy(payload)))
        merchant = {"_id": self._id(), **payload}
        self.merchants.append(merchant)
        return self._created(merchant)

    def create_customer(self, payload):
        self.writes.append(("customer", copy.deepcopy(payload)))
        customer = {"_id": self._id(), **payload}
        self.customers.append(customer)
        return self._created(customer)

    def get_customer_accounts(self, customer_id):
        return copy.deepcopy([a for a in self.accounts.values() if a["customer_id"] == customer_id])

    def create_account(self, customer_id, payload):
        self.writes.append(("account", copy.deepcopy(payload)))
        account = {"_id": self._id(), "customer_id": customer_id, **payload}
        self.accounts[account["_id"]] = account
        self.transactions[account["_id"]] = {"deposits": [], "purchases": [], "bills": [], "loans": []}
        return self._created(account)

    def delete_account(self, account_id):
        self.writes.append(("delete", account_id))
        if not self.fail_delete:
            del self.accounts[account_id]
            del self.transactions[account_id]
        return None

    def get_account(self, account_id):
        return copy.deepcopy(self.accounts[account_id])

    def get_deposits(self, account_id):
        return copy.deepcopy(self.transactions[account_id]["deposits"])

    def get_purchases(self, account_id):
        return copy.deepcopy(self.transactions[account_id]["purchases"])

    def get_bills(self, account_id):
        return copy.deepcopy(self.transactions[account_id]["bills"])

    def get_loans(self, account_id):
        return copy.deepcopy(self.transactions[account_id]["loans"])

    def create_loan(self, account_id, payload):
        return self._post(account_id, "loans", payload)

    def _post(self, account_id, kind, payload):
        self.writes.append((kind, copy.deepcopy(payload)))
        if kind == "purchases":
            if self.fail_purchase:
                raise NessieServiceError("Nessie returned HTTP 400", 400)
            assert payload["merchant_id"] in {m["_id"] for m in self.merchants}
            assert "_merchant_name" not in payload
        fields = {"deposits": {"medium", "transaction_date", "status", "amount", "description"},
                  "purchases": {"medium", "purchase_date", "status", "amount", "description", "merchant_id"},
                  "bills": {"status", "payee", "nickname", "payment_date", "payment_amount", "recurring_date"},
                  "loans": {"type", "status", "credit_score", "monthly_payment", "amount", "description"}}
        assert set(payload) <= fields[kind]
        record = {"_id": self._id(), **copy.deepcopy(payload)}
        self.transactions[account_id][kind].append(record)
        if self.ledger and payload["status"] == "completed":
            change = payload["amount"] if kind == "deposits" else -payload.get("amount", payload.get("payment_amount"))
            self.accounts[account_id]["balance"] += change
            assert self.accounts[account_id]["balance"] >= 0, "Chronological history overdraws the account"
        return self._created(record)

    def create_deposit(self, account_id, payload):
        return self._post(account_id, "deposits", payload)

    def create_purchase(self, account_id, payload):
        return self._post(account_id, "purchases", payload)

    def create_bill(self, account_id, payload):
        return self._post(account_id, "bills", payload)


class SeedNessieTests(unittest.TestCase):
    def quiet_seed(self, service, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return seed(service, **kwargs)

    def test_exact_monthly_targets_and_opening_cash(self):
        expected_nets = {"arbor": [-3000, -1500, 500, 2000, 1500],
                         "market": [4000, 2000, 0, -2000, -5000],
                         "arcade": [11000, 9000, 12000, 11000, 12000]}
        expected_counts = {"arbor": (30, 75, 42), "market": (30, 51, 42), "arcade": (40, 44, 48)}
        for key, business in BUSINESSES.items():
            with self.subTest(business=key):
                plan = build_plan(key)
                analysis = analyze_plan(business, plan)
                self.assertEqual(tuple(len(plan[k]) for k in ("deposits", "purchases", "bills")), expected_counts[key])
                self.assertEqual(analysis["summary"]["cash_balance"], business["cash"])
                for index, month in enumerate(MONTH_NUMBERS):
                    self.assertEqual(analysis["monthly_revenue"][index], {"month": f"2026-{month:02d}", "amount": business["revenue"][index]})
                    self.assertEqual(analysis["monthly_expenses"][index], {"month": f"2026-{month:02d}", "amount": business["expenses"][index]})
                    self.assertEqual(business["revenue"][index] - business["expenses"][index], expected_nets[key][index])
                self.assertEqual(opening_cash(business) + sum(expected_nets[key]), business["cash"])
                self.assertEqual(len(analysis["recurring_bills"]), len(business["bills"]) + 1)
                self.assertEqual(len([b for b in plan["bills"] if b["status"] == "completed"]), 5 * (len(business["bills"]) + 1))
                for kind, items in plan.items():
                    for item in items:
                        if kind == "loans":
                            self.assertNotIn("creation_date", item)
                            continue
                        day = item.get("transaction_date") or item.get("purchase_date") or item["payment_date"]
                        date.fromisoformat(day)
                        self.assertGreater(item.get("amount", item.get("payment_amount")), 0)

    def test_composition_varies_and_explains_events_and_cost_growth(self):
        arbor, market, arcade = [build_plan(key) for key in BUSINESSES]
        self.assertTrue(any("Espresso-machine pump repair" in p["description"] and p["amount"] == 1750 for p in arbor["purchases"]))
        self.assertTrue(any("motherboard replacement" in p["description"] and p["amount"] == 2400 for p in arcade["purchases"]))
        wholesale = [sum(p["amount"] for p in market["purchases"] if p["description"].startswith("Wholesale grocery") and p["purchase_date"].startswith(f"2026-{month:02d}")) for month in MONTH_NUMBERS]
        self.assertEqual(wholesale, [21000, 21600, 22200, 22700, 23500])
        utilities = [b["payment_amount"] for b in market["bills"] if b["status"] == "completed" and b["nickname"] == "Utilities / refrigeration"]
        self.assertEqual(utilities, [1200, 1400, 1600, 1800, 2200])
        for plan in (arbor, market, arcade):
            for month in MONTH_NUMBERS:
                monthly = [d for d in plan["deposits"] if d["transaction_date"].startswith(f"2026-{month:02d}")]
                self.assertGreaterEqual(len(monthly), 6)
                self.assertGreater(len({d["amount"] for d in monthly}), 2)
        # Waste disposal is an actual cash payment, not double-counted spoiled stock.
        self.assertTrue(any("spoiled-stock disposal" in p["description"] for p in market["purchases"]))

    def test_derived_signals_projections_and_breaking_points_are_distinct(self):
        analyses = {key: analyze_plan(b, build_plan(key)) for key, b in BUSINESSES.items()}
        for key in ("arbor", "market"):
            signals = {s["id"]: s for s in analyses[key]["signals"]}
            self.assertEqual(signals["cash_coverage"]["level"], "caution")
            self.assertEqual(signals["recurring_obligations"]["level"], "caution")
        self.assertLess(analyses["market"]["trends"]["revenue_change_percent"], 0)
        self.assertGreater(analyses["arbor"]["trends"]["revenue_change_percent"], 0)
        self.assertFalse(analyses["market"]["health"]["positive_cash_flow"])
        arcade_signals = {s["id"]: s for s in analyses["arcade"]["signals"]}
        self.assertEqual(arcade_signals["cash_coverage"]["value"], 2.67)
        self.assertNotEqual(arcade_signals["expense_growth"]["level"], "caution")
        engine = ScenarioEngine()
        for key, final_cash in (("arbor", -5640), ("market", -240), ("arcade", 136960)):
            hire = engine.simulate_hire(analyses[key], 18, 30, stress_test=True)
            self.assertEqual(hire["cash_projection"][-1]["scenario"], final_cash)
            self.assertEqual(hire["breaking_point"]["negative_within_horizon"], key != "arcade")
            equipment = engine.simulate_equipment(analyses[key], 10000)
            self.assertEqual(equipment["breaking_point"]["buffer_preserved_through_horizon"], key == "arcade")

    def test_cfo_context_exposes_recent_results_without_hardcoded_conclusions(self):
        question = "What is my biggest financial risk right now?"
        contexts = {}
        for key, business in BUSINESSES.items():
            analysis = analyze_plan(business, build_plan(key))
            context, error = CFOAssistant.build_context(analysis, question, {"kind": "general"})
            self.assertIsNone(error)
            contexts[key] = context
            self.assertEqual(context["historical"]["summary"], analysis["summary"])
            self.assertEqual(context["monthly_performance"][-1]["net_cash_flow"], business["revenue"][-1] - business["expenses"][-1])
            facts = CFOAssistant._facts(context)
            self.assertTrue(any(f["label"].endswith("net_cash_flow") and f["value"] == context["monthly_performance"][-1]["net_cash_flow"] for f in facts))
        self.assertEqual([contexts[k]["monthly_performance"][-1]["net_cash_flow"] for k in BUSINESSES], [1500, -5000, 12000])
        self.assertLess(contexts["market"]["monthly_performance"][-1]["margin_percent"], contexts["market"]["monthly_performance"][0]["margin_percent"])
        self.assertTrue(any("Wholesale grocery" in e["description"] for e in contexts["market"]["largest_expenses"]))

    def test_seeds_valid_contracts_then_reruns_without_writes(self):
        service = MemoryNessie()
        ids = self.quiet_seed(service)
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(service.customers), 3)
        self.assertEqual(len(service.accounts), 3)
        merchant_names = [m["name"] for m in service.merchants]
        self.assertEqual(len(merchant_names), len(set(merchant_names)))
        writes = len(service.writes)
        self.assertEqual(self.quiet_seed(service), ids)
        self.assertEqual(self.quiet_seed(service, replace_existing=True), ids)
        self.assertEqual(len(service.writes), writes)

    def test_ledger_semantics_and_wrong_mode_fail_readback(self):
        ledger = MemoryNessie(ledger=True)
        self.quiet_seed(ledger, balance_mode="ledger")
        self.assertEqual(sorted(a["balance"] for a in ledger.accounts.values()), [9000, 15000, 85000])
        self.assertEqual([payload["balance"] for kind, payload in ledger.writes if kind == "account"], [9500, 16000, 30000])
        service = MemoryNessie(ledger=True)
        with self.assertRaisesRegex(SeedError, "balance verification failed"):
            self.quiet_seed(service, selected=["arbor"])
        self.assertEqual(len(service.customers), 1)

    def test_reuse_legacy_customer_and_explicit_replace_only_demo_account(self):
        service = MemoryNessie()
        empty_id = service.create_customer(customer_payload(BUSINESSES["arbor"]))["objectCreated"]["_id"]
        customer_id = service.create_customer(customer_payload(BUSINESSES["arbor"]))["objectCreated"]["_id"]
        old_id = service.create_account(customer_id, {"type": "Checking", "nickname": "Arbor Coffee Co. - Demo Operating Checking", "balance": 26000})["objectCreated"]["_id"]
        before = len(service.writes)
        with self.assertRaisesRegex(SeedError, "legacy demo account"):
            self.quiet_seed(service)
        self.assertEqual(len(service.writes), before)
        ids = self.quiet_seed(service, replace_existing=True)
        self.assertEqual(ids["arbor"], customer_id)
        self.assertEqual(len(service.customers), 4)  # Pre-existing empty duplicate is preserved.
        self.assertEqual(service.get_customer_accounts(empty_id), [])
        self.assertNotIn(old_id, service.accounts)
        self.assertEqual(sum(kind == "delete" for kind, _ in service.writes), 1)

    def test_partial_failure_refuses_append_then_rebuilds(self):
        service = MemoryNessie()
        service.fail_purchase = True
        with self.assertRaisesRegex(SeedError, "purchases record"):
            self.quiet_seed(service, selected=["arbor"])
        self.assertEqual(len(service.customers), 1)
        before = len(service.writes)
        service.fail_purchase = False
        with self.assertRaisesRegex(SeedError, "partial, changed"):
            self.quiet_seed(service, selected=["arbor"])
        self.assertEqual(len(service.writes), before)
        self.quiet_seed(service, selected=["arbor"], replace_existing=True)
        self.assertEqual(len(service.customers), 1)
        self.assertEqual(len(service.accounts), 1)

    def test_rejected_envelopes_and_missing_ids_stop_without_secret_leaks(self):
        service = MemoryNessie()
        with patch.object(service, "create_merchant", return_value={"code": 400, "message": "secret-key"}):
            with self.assertRaisesRegex(SeedError, "code 400") as caught:
                self.quiet_seed(service)
        self.assertNotIn("secret-key", str(caught.exception))
        self.assertEqual(service.customers, [])
        with patch.object(service, "create_customer", return_value={"code": 201}):
            with self.assertRaisesRegex(SeedError, "customer ID"):
                self.quiet_seed(service)
        self.assertEqual(service.accounts, {})

    def test_cfo_validation_uses_actual_records_and_continues_other_businesses(self):
        from backend.services.cfo_assistant import CFOAssistantError
        service = MemoryNessie()
        ids = self.quiet_seed(service)
        captured = []
        def ask(analysis, question):
            captured.append((analysis["summary"]["cash_balance"], question))
            if analysis["summary"]["cash_balance"] == 15000:
                raise CFOAssistantError("Temporarily unavailable", 503)
            return {"answer": "Test-only explanation"}
        with patch("backend.services.cfo_assistant.CFOAssistant") as assistant:
            assistant.return_value.ask.side_effect = ask
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertFalse(validate_cfo(service, ids))
        self.assertEqual([row[0] for row in captured], [9000, 15000, 85000])
        self.assertEqual({row[1] for row in captured}, {"Is my current debt manageable?"})

    def test_completed_monthly_bills_have_readable_supported_schedules(self):
        for key in BUSINESSES:
            plan = build_plan(key)
            for bill in plan["bills"]:
                self.assertEqual(bill["recurring_date"], int(bill["payment_date"][-2:]))
                self.assertNotIn("upcoming_payment_date", bill)  # Generated by Nessie, not POST-supported.
            analysis = analyze_plan(BUSINESSES[key], plan)
            self.assertEqual([row["amount"] for row in analysis["monthly_expenses"]], list(BUSINESSES[key]["expenses"]))
            self.assertTrue(all(b["status"] == "recurring" for b in analysis["recurring_bills"]))

    def test_known_unreadable_existing_bills_require_flag_then_replace_once(self):
        service = MemoryNessie()
        ids = self.quiet_seed(service, selected=["arbor"])
        old_account_id = next(iter(service.accounts))
        old_reader = service.get_bills
        def get_bills(account_id):
            if account_id == old_account_id:
                raise NessieServiceError("Sanitized bill schema defect", 400,
                                         reason="bill_readback_missing_schedule")
            return old_reader(account_id)
        before = len(service.writes)
        with patch.object(service, "get_bills", side_effect=get_bills):
            with self.assertRaisesRegex(SeedError, "cannot be read"):
                self.quiet_seed(service, selected=["arbor"])
            self.assertEqual(len(service.writes), before)
            self.assertEqual(self.quiet_seed(service, selected=["arbor"], replace_existing=True), ids)
            self.assertNotIn(old_account_id, service.accounts)
            self.assertEqual(len(service.customers), 1)
            self.assertEqual(sum(kind == "delete" for kind, _ in service.writes), 1)
            before = len(service.writes)
            self.assertEqual(self.quiet_seed(service, selected=["arbor"], replace_existing=True), ids)
            self.assertEqual(len(service.writes), before)

    def test_unrelated_verification_http_errors_never_trigger_replacement_or_cfo(self):
        service = MemoryNessie()
        self.quiet_seed(service, selected=["arbor"])
        for status in (400, 401, 429, 500):
            before = len(service.writes)
            with patch.object(service, "get_bills", side_effect=NessieServiceError("API failure", status)):
                with self.assertRaises(NessieServiceError):
                    self.quiet_seed(service, selected=["arbor"], replace_existing=True)
            self.assertEqual(len(service.writes), before)
            self.assertEqual(len(service.accounts), 1)
        # CLI invokes CFO only once seed() has verified every selected business.
        with patch("scripts.seed_nessie.NessieService", return_value=service), \
             patch("scripts.seed_nessie.seed", side_effect=NessieServiceError("GET /accounts/{id}/bills failed", 400)), \
             patch("scripts.seed_nessie.validate_cfo") as cfo, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--replace-existing", "--validate-cfo"]), 1)
        cfo.assert_not_called()

    def test_unrelated_accounts_wrong_addresses_and_ambiguous_customers_are_protected(self):
        for violation in ("account", "address", "duplicate"):
            service = MemoryNessie()
            customer = customer_payload(BUSINESSES["arbor"])
            if violation == "address":
                customer["address"]["street_name"] = "Different Street"
            customer_id = service.create_customer(customer)["objectCreated"]["_id"]
            if violation in ("account", "duplicate"):
                service.create_account(customer_id, {"nickname": "Personal checking" if violation == "account" else account_name(BUSINESSES["arbor"]), "balance": 1})
            if violation == "duplicate":
                other = service.create_customer(customer)["objectCreated"]["_id"]
                service.create_account(other, {"nickname": account_name(BUSINESSES["arbor"]), "balance": 1})
            before = len(service.writes)
            with self.assertRaises(SeedError):
                self.quiet_seed(service, replace_existing=True)
            self.assertEqual(len(service.writes), before)

    def test_wrong_dates_statuses_amounts_and_failed_deletion_are_not_accepted(self):
        for field, value in (("status", "pending"), ("transaction_date", "2026-01-01"), ("amount", 1)):
            service = MemoryNessie()
            self.quiet_seed(service, selected=["arbor"])
            account_id = next(iter(service.accounts))
            service.transactions[account_id]["deposits"][0][field] = value
            before = len(service.writes)
            with self.assertRaisesRegex(SeedError, "partial, changed"):
                self.quiet_seed(service, selected=["arbor"])
            self.assertEqual(len(service.writes), before)
            service.fail_delete = True
            with self.assertRaisesRegex(SeedError, "deletion could not be verified"):
                self.quiet_seed(service, selected=["arbor"], replace_existing=True)
            self.assertEqual(len(service.accounts), 1)

    def test_dry_run_never_calls_services_even_with_other_flags(self):
        with patch("scripts.seed_nessie.NessieService") as nessie, patch("requests.request") as request, patch("requests.post") as post, patch("scripts.seed_nessie.load_dotenv") as env:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--dry-run", "--replace-existing", "--validate-cfo"]), 0)
            for mock in (nessie, request, post, env):
                mock.assert_not_called()
            for business in BUSINESSES.values():
                self.assertIn(business["name"], output.getvalue())
            self.assertIn("Economic opening cash", output.getvalue())
            self.assertIn("current cash target", output.getvalue())

    def test_fastapi_analysis_uses_seeded_raw_records(self):
        service = MemoryNessie()
        ids = self.quiet_seed(service)
        app.dependency_overrides[get_nessie_service] = lambda: service
        self.addCleanup(app.dependency_overrides.clear)
        with TestClient(app) as client:
            for key, customer_id in ids.items():
                response = client.get(f"/businesses/{customer_id}/analysis")
                self.assertEqual(response.status_code, 200)
                actual = response.json()
                expected = analyze_plan(BUSINESSES[key], build_plan(key))
                for field in ("summary", "monthly_revenue", "monthly_expenses", "signals", "health"):
                    self.assertEqual(actual[field], expected[field])


if __name__ == "__main__":
    unittest.main()
