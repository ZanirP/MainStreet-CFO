"""Debt calculations and projection integration, without network calls."""
import copy
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app import app, get_nessie_service
from backend.services.cfo_assistant import CFOAssistant
from backend.services.financial_analyzer import FinancialAnalyzer
from backend.services.nessie_service import NessieService, NessieServiceError
from backend.services.scenario_engine import ScenarioEngine
from scripts.seed_nessie import BUSINESSES, SeedError, analyze_plan, build_plan, seed
from test_seed_nessie import MemoryNessie


def loan(**changes):
    return {"_id": "loan-a", "type": "business", "status": "active", "amount": 48000,
            "monthly_payment": 1200, "description": "Buildout", "credit_score": 700,
            "creation_date": "2026-07-01", **changes}


def financial_records():
    return {"accounts": [{"type": "Checking", "balance": 5000}],
            "deposits": [{"amount": 10000, "transaction_date": f"2026-{month}-05"} for month in ("06", "07")],
            "purchases": [{"amount": 7000, "purchase_date": f"2026-{month}-10"} for month in ("06", "07")],
            "bills": [{"nickname": "Debt payment: Buildout", "payment_amount": 1000,
                       "payment_date": f"2026-{month}-15", "status": "completed"} for month in ("06", "07")] +
                      [{"nickname": "Debt payment: Buildout", "payment_amount": 1200, "status": "recurring"}],
            "loans": [loan()]}


class DebtAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = FinancialAnalyzer()
        self.engine = ScenarioEngine()

    def test_principal_is_not_an_expense_and_payments_are_replaced_once(self):
        records = financial_records()
        original = copy.deepcopy(records)
        analysis = self.analyzer.analyze_business(**records)
        self.assertEqual(records, original)
        self.assertEqual(analysis["summary"]["expenses"], 16000)
        self.assertEqual(analysis["debt"]["reported_active_loan_amount"], 48000)
        self.assertEqual(analysis["debt"]["forecast_expense_adjustment"], 200)
        self.assertEqual(analysis["debt"]["payment_coverage_ratio"], 2.5)
        self.assertEqual(analysis["debt"]["conservative_obligation_exposure"], 1200)
        for missing in ("outstanding_balance", "apr", "remaining_term_months"):
            self.assertIsNone(analysis["debt"]["loans"][0][missing])
        result = self.engine.simulate_hire(analysis, 18, 30, stress_test=True)
        self.assertEqual(result["baseline_monthly_cash_flow"], 1800)
        self.assertEqual(result["projected_monthly_cash_flow"], -540)
        self.assertEqual(result["cash_projection"][-1]["scenario"], 1760)
        self.assertEqual(result["breaking_point"]["minimum_monthly_revenue"], 10540)
        self.assertEqual(result["breaking_point"]["maximum_monthly_employee_cost"], 1800)
        self.assertEqual(result["breaking_point"]["maximum_hourly_wage"], 13.84)
        stress = result["stress_test"]
        self.assertEqual(stress["assumptions"]["stressed_monthly_expenses"], 8900)
        self.assertEqual(stress["baseline_monthly_cash_flow"], 100)
        self.assertEqual(stress["breaking_point"]["first_negative_month_index"], 3)
        for simulate in (self.engine.simulate_equipment, self.engine.simulate_withdrawal):
            one_time = simulate(analysis, 1000, stress_test=True)
            self.assertEqual(one_time["baseline_monthly_cash_flow"], 1800)
            self.assertEqual(one_time["cash_projection"][-1]["scenario"], 14800)
            self.assertEqual(one_time["breaking_point"]["cash_buffer_amount"], 8200)

    def test_unlinked_payments_are_unknown_not_deducted_again(self):
        records = financial_records()
        for bill in records["bills"]:
            bill["nickname"] = "Lender payment"  # Amounts/names alone aren't a link.
        data = self.analyzer.analyze_business(**records)
        self.assertIsNone(data["debt"]["payment_coverage_ratio"])
        self.assertFalse(data["debt"]["all_active_payments_linked"])
        self.assertEqual(data["debt"]["forecast_expense_adjustment"], 0)
        self.assertEqual(self.engine.simulate_hire(data, 0, 0)["baseline_monthly_cash_flow"], 2000)

    def test_missing_and_invalid_debt_is_not_reported_as_debt_free(self):
        self.assertFalse(self.analyzer.analyze_business()["debt"]["data_available"])
        self.assertIsNone(self.analyzer.analyze_business()["debt"]["monthly_payment_total"])
        empty = self.analyzer.analyze_business(loans=[])["debt"]
        self.assertTrue(empty["complete"])
        self.assertEqual(empty["active_loan_count"], 0)
        for value in (None, -1, True, "bad", float("inf"), "NaN"):
            with self.subTest(value=value):
                debt = self.analyzer.analyze_business(loans=[loan(monthly_payment=value)])["debt"]
                self.assertFalse(debt["complete"])
                self.assertIsNone(debt["loans"][0]["monthly_payment"])
                self.assertIsNone(debt["monthly_payment_total"])
                self.assertIsNone(debt["payment_coverage_ratio"])
        for status in (None, "pending", "unknown"):
            self.assertFalse(self.analyzer.analyze_business(loans=[loan(status=status)])["debt"]["complete"])
        invalid_amount = self.analyzer.analyze_business(loans=[loan(amount="bad")])["debt"]
        self.assertIsNone(invalid_amount["reported_active_loan_amount"])
        closed = self.analyzer.analyze_business(loans=[loan(status="closed")])["debt"]
        self.assertTrue(closed["complete"])
        self.assertEqual(closed["monthly_payment_total"], 0)

    def test_ambiguous_links_and_cross_account_bills_are_not_matched(self):
        records = financial_records()
        records["loans"].append(loan(_id="loan-b"))
        data = self.analyzer.analyze_business(**records)
        self.assertEqual(data["debt"]["forecast_expense_adjustment"], 0)
        self.assertFalse(data["debt"]["all_active_payments_linked"])
        records["loans"] = [loan(_source_account_id="a")]
        for bill in records["bills"]:
            bill["_source_account_id"] = "b"
        self.assertEqual(self.analyzer.analyze_business(**records)["debt"]["linked_monthly_payment"], 0)

    def test_new_linked_payment_without_historical_payment_is_counted_once(self):
        records = financial_records()
        records["bills"] = records["bills"][-1:]
        data = self.analyzer.analyze_business(**records)
        self.assertEqual(data["summary"]["expenses"], 14000)
        self.assertEqual(data["debt"]["forecast_expense_adjustment"], 1200)
        self.assertEqual(self.engine.simulate_hire(data, 0, 0)["baseline_monthly_cash_flow"], 1800)

    def test_seed_debt_context_distinguishes_businesses_without_named_rules(self):
        coverage, latest, recent_coverage = [], [], []
        for key, business in BUSINESSES.items():
            data = analyze_plan(business, build_plan(key))
            context, clarification = CFOAssistant.build_context(data, "Is my current debt manageable?", {"kind": "general"})
            self.assertIsNone(clarification)
            self.assertEqual(context["existing_debt"], data["debt"])
            self.assertNotIn("credit_score", str(context))
            self.assertNotIn(business["name"], str(context["existing_debt"]["basis"]))
            facts = CFOAssistant._facts(context)
            payment_facts = [f for f in facts if f["label"] == "existing_debt.monthly_payment_total"]
            self.assertEqual(payment_facts[0]["source"], "historical")
            coverage.append(data["debt"]["payment_coverage_ratio"])
            latest.append(data["debt"]["latest_monthly_cash_flow"])
            recent_coverage.append(data["debt"]["latest_payment_coverage_ratio"])
            self.assertEqual(data["debt"]["forecast_expense_adjustment"], 0)
        self.assertEqual(coverage, [0.92, 0.89, 19.33])
        self.assertEqual(recent_coverage, [2.25, -1.78, 21.0])
        self.assertEqual(latest, [1500, -5000, 12000])

    def test_cfo_can_explain_current_debt_without_inventing_history(self):
        data = self.analyzer.analyze_business(loans=[loan()])
        context, clarification = CFOAssistant.build_context(data, "How much is my loan costing me?", {"kind": "general"})
        self.assertIsNone(clarification)
        self.assertIsNone(context["existing_debt"]["average_monthly_cash_flow_after_linked_payments"])
        self.assertIsNotNone(CFOAssistant.build_context(data, "Cash after six months?", {"kind": "projection"})[1])

    def test_seed_loans_verified_and_changes_require_explicit_replacement(self):
        service = MemoryNessie()
        with patch("builtins.print"):
            ids = seed(service)
        before = len(service.writes)
        with patch("builtins.print"):
            self.assertEqual(seed(service), ids)
        self.assertEqual(len(service.writes), before)
        account = service.get_customer_accounts(ids["arbor"])[0]
        service.transactions[account["_id"]]["loans"][0]["monthly_payment"] += 1
        with patch("builtins.print"), self.assertRaises(SeedError):
            seed(service)
        self.assertEqual(len(service.writes), before)
        with patch("builtins.print"):
            self.assertEqual(seed(service, replace_existing=True), ids)
        self.assertEqual(len(service.customers), 3)

    def test_v2_migration_retains_customer_and_requires_replacement(self):
        service = MemoryNessie()
        with patch("builtins.print"):
            ids = seed(service, selected=["arbor"])
        account = service.get_customer_accounts(ids["arbor"])[0]
        service.accounts[account["_id"]]["nickname"] = "Arbor Coffee Co. - Demo Operating Checking (May-Sep 2026 v2)"
        before = len(service.writes)
        with patch("builtins.print"), self.assertRaisesRegex(SeedError, "legacy"):
            seed(service, selected=["arbor"])
        self.assertEqual(len(service.writes), before)
        with patch("builtins.print"):
            self.assertEqual(seed(service, selected=["arbor"], replace_existing=True), ids)
        self.assertEqual(len(service.customers), 1)

    def test_loan_creation_rejection_reports_partial_account_and_never_appends(self):
        service = MemoryNessie()
        with patch.object(service, "create_loan", side_effect=NessieServiceError("secret-key", 400)):
            with patch("builtins.print"), self.assertRaisesRegex(SeedError, "failed creating loans") as error:
                seed(service, selected=["arbor"])
        self.assertNotIn("secret-key", str(error.exception))
        self.assertEqual(len(service.customers), 1)
        before = len(service.writes)
        with patch("builtins.print"), self.assertRaises(SeedError):
            seed(service, selected=["arbor"])
        self.assertEqual(len(service.writes), before)

    def test_api_loads_loans_and_fails_closed_on_unavailable_debt(self):
        service = Mock(spec=NessieService)
        service.get_customer_accounts.return_value = [{"_id": "a", "type": "Checking", "balance": 5000}]
        source = financial_records()
        for kind in ("deposits", "purchases", "bills", "loans"):
            getattr(service, f"get_{kind}").return_value = source[kind]
        app.dependency_overrides[get_nessie_service] = lambda: service
        self.addCleanup(app.dependency_overrides.clear)
        with TestClient(app) as client:
            result = client.post("/businesses/c/scenarios/hire", json={"hourly_wage": 18, "hours_per_week": 30})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["baseline_monthly_cash_flow"], 1800)
            service.get_loans.assert_called_once_with("a")
            for error in (["invalid"], None):
                service.get_loans.return_value = error
                self.assertEqual(client.get("/businesses/c/analysis").status_code, 502)
            service.get_loans.side_effect = NessieServiceError("secret", 500)
            result = client.get("/businesses/c/analysis")
            self.assertEqual(result.status_code, 502)
            self.assertNotIn("secret", result.text)


if __name__ == "__main__":
    unittest.main()
