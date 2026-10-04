"""Independent expansion arithmetic, API read-only behavior and CFO provenance."""
import copy
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from backend.app import app, get_nessie_service, get_cfo_assistant
from backend.services.financial_analyzer import FinancialAnalyzer
from backend.services.scenario_engine import ScenarioEngine
from backend.services.cfo_assistant import CFOAssistant
from scripts.seed_nessie import BUSINESSES, build_plan, analyze_plan
from test_seed_nessie import MemoryNessie


def history(cash=10000):
    return FinancialAnalyzer().analyze_business(
        accounts=[{"balance": cash}], loans=[],
        deposits=[{"amount": 10000, "transaction_date": "2026-09-01"}],
        purchases=[{"amount": 8000, "purchase_date": "2026-09-01", "description": "Unclassified invoice"}])


def inputs(**changes):
    return dict(upfront_cost=4000, monthly_revenue=6000, rent=1000, payroll=1500,
                utilities=250, inventory=750, other=500, ramp_months=3, months=4,
                financing_amount=0, annual_interest_percent=0, financing_term_months=2,
                stress_test=True, **{}) | changes


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.engine = ScenarioEngine()

    def test_cash_upfront_ramp_and_break_even(self):
        source = history()
        original = copy.deepcopy(source)
        result = self.engine.simulate_location(source, **inputs())
        self.assertEqual(source, original)
        self.assertEqual(result["incremental_monthly_operating_cost"], 4000)
        self.assertEqual(result["cash_funding_amount"], 4000)
        self.assertEqual([row["scenario"] for row in result["cash_projection"]], [6000, 8000, 12000, 16000])
        self.assertEqual([row["additional_revenue"] for row in result["monthly_operations"]], [2000, 4000, 6000, 6000])
        self.assertEqual(result["breaking_point"]["cash_after_decision"], 6000)
        self.assertEqual(result["breaking_point"]["location_standalone_break_even_revenue"], 4000)
        self.assertEqual(result["breaking_point"]["minimum_additional_revenue_for_business_break_even"], 2000)
        self.assertEqual(result["breaking_point"]["mature_revenue_downside_percent"], 66.66)
        self.assertFalse(result["breaking_point"]["negative_within_horizon"])
        self.assertIsNone(result["breaking_point"]["cash_runway_months"])
        self.assertIsNone(result["breaking_point"]["minimum_mature_revenue_preserving_buffer"])
        self.assertEqual(result["stress_test"]["baseline_monthly_cash_flow"], 200)
        self.assertEqual(result["stress_test"]["cash_projection"][0]["scenario"], 3600)

    def test_zero_interest_financing_preserves_opening_cash_and_stops_at_term(self):
        result = self.engine.simulate_location(history(), **inputs(financing_amount=4000))
        self.assertEqual(result["hypothetical_financing"]["monthly_payment"], 2000)
        self.assertEqual(result["hypothetical_financing"]["total_interest_over_entered_term"], 0)
        self.assertEqual([row["scenario"] for row in result["cash_projection"]], [8000, 8000, 12000, 16000])
        self.assertEqual([row["hypothetical_debt_payment"] for row in result["monthly_operations"]], [2000,2000,0,0])
        self.assertEqual([row["cash_funded"] for row in result["cash_projection"]], [6000,8000,12000,16000])
        self.assertEqual(result["breaking_point"]["cash_after_decision"], 10000)
        self.assertEqual(result["projected_monthly_cash_flow"], 4000)
        self.assertEqual(result["breaking_point"]["minimum_additional_revenue_for_business_break_even"], 2000)
        self.assertEqual(result["breaking_point"]["additional_revenue_break_even_while_financing_active"], 4000)

    def test_amortization_known_payment_and_existing_debt_not_counted_twice(self):
        data = analyze_plan(BUSINESSES["arbor"], build_plan("arbor"))
        result = self.engine.simulate_location(data, **inputs(upfront_cost=30000, financing_amount=28000,
            annual_interest_percent=8, financing_term_months=60, monthly_revenue=20000))
        self.assertEqual(result["baseline_monthly_cash_flow"], -100)
        self.assertEqual(result["debt_assumptions"]["fixed_linked_monthly_payment"], 1200)
        self.assertEqual(result["hypothetical_financing"]["monthly_payment"], 567.74)
        self.assertEqual(result["hypothetical_financing"]["total_interest_over_entered_term"], 6064.34)
        self.assertEqual(result["breaking_point"]["cash_after_decision"], 7000)
        self.assertEqual(result["monthly_operations"][0]["combined_cash_flow"], 1998.93)
        # Current stress: 22900*.9 - (21800*1.1 + fixed 1200) = -4570.
        self.assertEqual(result["stress_test"]["baseline_monthly_cash_flow"], -4570)
        self.assertEqual(result["stress_test"]["monthly_operations"][0]["hypothetical_debt_payment"], 567.74)

    def test_negative_opening_and_mid_ramp_trough_survive_later_recovery(self):
        opening = self.engine.simulate_location(history(), **inputs(upfront_cost=11000))
        self.assertTrue(opening["breaking_point"]["negative_immediately"])
        self.assertEqual(opening["breaking_point"]["first_negative_month_index"], 0)
        self.assertEqual(opening["breaking_point"]["cash_runway_months"], 0)
        result = self.engine.simulate_location(history(1000), **inputs(upfront_cost=0, monthly_revenue=12000, rent=6000))
        self.assertEqual([row["scenario"] for row in result["cash_projection"]], [-2000,-1000,4000,9000])
        self.assertTrue(result["breaking_point"]["negative_within_horizon"])
        self.assertEqual(result["breaking_point"]["minimum_cash_balance_within_horizon"], -2000)
        self.assertEqual(result["breaking_point"]["first_negative_month"], "2026-10")
        self.assertEqual(result["breaking_point"]["cash_runway_months"], 0.33)
        zero = self.engine.simulate_location(history(0), **inputs(upfront_cost=0))
        self.assertFalse(zero["breaking_point"]["negative_within_horizon"])

    def test_buffer_threshold_solves_all_ramp_months_and_never_claims_infinity(self):
        result = self.engine.simulate_location(history(30000), **inputs())
        # At cash=26000, buffer=12000, fixed baseline 2000 and cost 4000,
        # even zero additional revenue preserves the buffer for this horizon.
        self.assertEqual(result["breaking_point"]["minimum_mature_revenue_preserving_buffer"], 0)
        required = self.engine.simulate_location(history(16000), **inputs(monthly_revenue=0))
        self.assertEqual(required["breaking_point"]["minimum_mature_revenue_preserving_buffer"], 6000)
        at_limit = self.engine.simulate_location(history(16000), **inputs(monthly_revenue=6000))
        self.assertTrue(at_limit["breaking_point"]["buffer_preserved_through_horizon"])
        below = self.engine.simulate_location(history(16000), **inputs(monthly_revenue=5999))
        self.assertFalse(below["breaking_point"]["buffer_preserved_through_horizon"])
        long_ramp = self.engine.simulate_location(history(), **inputs(ramp_months=12))
        self.assertLess(long_ramp["monthly_operations"][-1]["ramp_percent"], 100)

    def test_missing_categories_and_unknown_debt_are_not_invented(self):
        data = history()
        estimates = data["location_estimates"]
        self.assertIsNone(estimates["costs"]["rent"]["amount"])
        self.assertIsNone(estimates["costs"]["payroll"]["amount"])
        self.assertEqual(estimates["costs"]["other"]["amount"], 8000)
        data = FinancialAnalyzer().analyze_business()
        self.assertIsNone(data["location_estimates"]["monthly_revenue"])
        with self.assertRaises(ValueError): self.engine.simulate_location(data, **inputs())
        for key in BUSINESSES:
            actual = analyze_plan(BUSINESSES[key], build_plan(key))
            total = sum(value["amount"] or 0 for value in actual["location_estimates"]["costs"].values())
            self.assertEqual(total, sum(BUSINESSES[key]["expenses"])/5-BUSINESSES[key]["loan"]["monthly_payment"])
        self.assertIsNotNone(CFOAssistant.build_context(history(), "Open another store?", {"kind": "location"})[1])

    def test_cost_estimates_exclude_only_verified_same_account_debt_payments(self):
        bills = [{"nickname":"Debt payment: Equipment", "payment_amount":1200, "status":"completed",
                  "payment_date":"2026-09-01", "_source_account_id":scope} for scope in ("a","b")]
        bills.append({"nickname":"Debt payment: Equipment", "payment_amount":1200, "status":"recurring", "_source_account_id":"a"})
        data = FinancialAnalyzer().analyze_business(
            deposits=[{"amount":10000,"transaction_date":"2026-09-01"}], bills=bills,
            loans=[{"description":"Equipment", "status":"active", "amount":12000,
                    "monthly_payment":1200,"_source_account_id":"a"}])
        self.assertEqual(data["location_estimates"]["costs"]["other"]["amount"],1200)

    def test_invalid_inputs(self):
        for changes in (dict(upfront_cost=-1), dict(financing_amount=4001), dict(months=0),
            dict(ramp_months=True), dict(ramp_months=1.5), dict(financing_term_months=0),
            dict(annual_interest_percent=101), dict(payroll=float('nan')), dict(monthly_revenue=True),
            dict(stress_test=1), dict(upfront_cost=1e20)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.engine.simulate_location(history(), **inputs(**changes))

    def test_api_and_cfo_recompute_inputs_without_writes_and_keep_fact_provenance(self):
        service = MemoryNessie()
        from scripts.seed_nessie import seed
        with patch("builtins.print"): ids=seed(service,selected=["arbor"])
        before = copy.deepcopy(service.writes)
        app.dependency_overrides[get_nessie_service] = lambda: service
        self.addCleanup(app.dependency_overrides.clear)
        assistant = Mock()
        assistant.ask.return_value={"answer":"Grounded", "status":"answered", "facts":[], "context":{}}
        app.dependency_overrides[get_cfo_assistant] = lambda: assistant
        with TestClient(app) as client:
            path=f"/businesses/{ids['arbor']}"
            projection=client.post(path+"/scenarios/location",json=inputs())
            self.assertEqual(projection.status_code,200)
            response=client.post(path+"/cfo/ask",json={"question":"Can I afford expansion?", "location_inputs":inputs()})
            self.assertEqual(response.status_code,200)
            self.assertEqual(assistant.ask.call_args.kwargs["location_scenario"], projection.json())
            self.assertEqual(service.writes,before)
            self.assertEqual(client.post(path+"/scenarios/location",json=inputs(rent=None)).status_code,422)
            self.assertEqual(client.post(path+"/scenarios/location",json=inputs(financing_amount=9999)).status_code,422)
        with patch.dict("os.environ", {"GEMINI_API_KEY":"test-only"}): cfo=CFOAssistant()
        def generate(instruction,data,schema):
            fact=next(f for f in data["facts"] if f["label"].endswith("cash_after_decision") and f["source"]=="projection")
            return {"answer":f"Projected opening cash is [[{fact['id']}]]. Financing is hypothetical."}
        source=analyze_plan(BUSINESSES['arbor'],build_plan('arbor'))
        with patch.object(cfo,"_generate",side_effect=generate): result=cfo.ask(source,"Expansion risk?",location_scenario=projection.json())
        self.assertEqual(result["context"]["existing_debt"],source["debt"])
        self.assertEqual(result["context"]["scenario_assumptions"]["location_inputs"],projection.json()["inputs"])
        self.assertNotIn("inputs",result["context"]["projection"])
        self.assertEqual(result["facts"][0]["source"],"projection")

if __name__ == '__main__': unittest.main()
