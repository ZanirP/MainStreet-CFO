"""Offline hiring projection tests."""
import copy
import json
import unittest

from backend.services.financial_analyzer import FinancialAnalyzer
from backend.services.scenario_engine import ScenarioEngine


def analysis(cash=24000):
    return {
        "summary": {"cash_balance": cash},
        "monthly_revenue": [{"month": "2026-09", "amount": 10000},
                            {"month": "2026-10", "amount": 12000}],
        "monthly_expenses": [{"month": "2026-09", "amount": 3000},
                             {"month": "2026-10", "amount": 5000}],
    }


class ScenarioEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = ScenarioEngine()

    def test_hire_example_and_cumulative_balances(self):
        data = analysis()
        original = copy.deepcopy(data)
        result = self.engine.simulate_hire(data, 18, 30)
        self.assertEqual(result["scenario"], "hire_employee")
        self.assertEqual(result["inputs"], {"hourly_wage": 18, "hours_per_week": 30, "months": 6})
        self.assertEqual(result["monthly_added_cost"], 2340)
        self.assertEqual(result["baseline_monthly_cash_flow"], 7000)
        self.assertEqual(result["projected_monthly_cash_flow"], 4660)
        self.assertEqual(result["cash_projection"][0], {"month": "2026-11", "baseline": 31000, "scenario": 28660})
        self.assertEqual(result["cash_projection"][-1], {"month": "2027-04", "baseline": 66000, "scenario": 51960})
        self.assertEqual(len(result["cash_projection"]), 6)
        self.assertEqual(data, original)
        self.assertEqual(result, self.engine.simulate_hire(data, 18, 30))
        json.dumps(result, allow_nan=False)

    def test_average_calendar_gaps_and_unsorted_history(self):
        data = analysis(0)
        data["monthly_revenue"] = [{"month": "2026-03", "amount": 600}, {"month": "2026-01", "amount": 300}]
        data["monthly_expenses"] = [{"month": "2026-02", "amount": 300}]
        result = self.engine.simulate_hire(data, 0, 40, 1)
        self.assertEqual(result["baseline_monthly_cash_flow"], 200)
        self.assertEqual(result["cash_projection"], [{"month": "2026-04", "baseline": 200, "scenario": 200}])

    def test_negative_cash_flow_and_zero_hours(self):
        data = analysis(-50)
        data["monthly_revenue"] = []
        data["monthly_expenses"] = [{"month": "2026-12", "amount": 100}]
        result = self.engine.simulate_hire(data, 18, 0, 2)
        self.assertEqual(result["cash_projection"], [
            {"month": "2027-01", "baseline": -150, "scenario": -150},
            {"month": "2027-02", "baseline": -250, "scenario": -250}])

    def test_full_precision_until_final_rounding(self):
        data = analysis(0)
        data["monthly_revenue"] = [{"month": "2026-10", "amount": 0}]
        data["monthly_expenses"] = []
        result = self.engine.simulate_hire(data, 1, 1, 3)
        self.assertEqual(result["monthly_added_cost"], 4.33)
        self.assertEqual(result["cash_projection"][-1]["scenario"], -13)

    def test_invalid_inputs(self):
        cases = [(-1, 30, 6), (18, -1, 6), (18, 30, 0), (18, 30, -1),
                 (18, 30, 1.5), (18, 30, True), (True, 30, 6),
                 (float("nan"), 30, 6), (18, float("inf"), 6), (None, 30, 6), ("18", 30, 6)]
        for wage, hours, months in cases:
            with self.subTest(wage=wage, hours=hours, months=months):
                with self.assertRaises(ValueError):
                    self.engine.simulate_hire(analysis(), wage, hours, months)

    def test_missing_or_invalid_financial_data(self):
        cases = [None, {}, {"summary": {}}, FinancialAnalyzer().analyze_business()]
        for field, value in [("monthly_revenue", None), ("monthly_expenses", [{}]),
                             ("monthly_revenue", [{"month": "2026-13", "amount": 1}]),
                             ("monthly_revenue", [{"month": "2026-01", "amount": float("nan")}]),
                             ("monthly_revenue", [{"month": "2026-01", "amount": 1}] * 2)]:
            data = analysis()
            data[field] = value
            cases.append(data)
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    self.engine.simulate_hire(data, 18, 30)

    def test_real_analyzer_output(self):
        data = FinancialAnalyzer().analyze_business(
            accounts=[{"type": "Checking", "balance": 1000}],
            deposits=[{"amount": 500, "transaction_date": "2026-10-01"}],
            purchases=[{"amount": 200, "purchase_date": "2026-10-02"}])
        result = self.engine.simulate_hire(data, 10, 12, 1)
        self.assertEqual(result["cash_projection"], [{"month": "2026-11", "baseline": 1300, "scenario": 780}])

    def test_one_time_reductions_apply_once(self):
        for method, kind in [(self.engine.simulate_equipment, "equipment_purchase"),
                             (self.engine.simulate_withdrawal, "owner_withdrawal")]:
            data = analysis()
            original = copy.deepcopy(data)
            result = method(data, 5000, 6)
            self.assertEqual(result["scenario"], kind)
            self.assertEqual(result["one_time_cost"], 5000)
            self.assertEqual(result["monthly_added_cost"], 0)
            self.assertEqual(result["projected_monthly_cash_flow"], 7000)
            self.assertEqual(result["cash_projection"][0], {"month": "2026-11", "baseline": 31000, "scenario": 26000})
            self.assertEqual(result["cash_projection"][-1], {"month": "2027-04", "baseline": 66000, "scenario": 61000})
            for row in result["cash_projection"]:
                self.assertEqual(row["baseline"] - row["scenario"], 5000)
            self.assertEqual(data, original)
            self.assertEqual(result, method(data, 5000, 6))
            json.dumps(result, allow_nan=False)

    def test_one_time_validation_and_zero_cost(self):
        for method in (self.engine.simulate_equipment, self.engine.simulate_withdrawal):
            for amount in (-1, None, True, "5", float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    method(analysis(), amount)
            for months in (0, -1, 1.5, True):
                with self.assertRaises(ValueError):
                    method(analysis(), 1, months)
            for missing in ({}, None, FinancialAnalyzer().analyze_business()):
                with self.assertRaises(ValueError):
                    method(missing, 1)
            result = method(analysis(), 0, 1)
            self.assertEqual(result["cash_projection"][0]["baseline"], result["cash_projection"][0]["scenario"])

    def test_one_time_negative_balances_and_cents(self):
        for method in (self.engine.simulate_equipment, self.engine.simulate_withdrawal):
            result = method(analysis(0), 10000.25, 2)
            self.assertEqual(result["cash_projection"][0]["scenario"], -3000.25)
            self.assertEqual(result["cash_projection"][1]["scenario"], 3999.75)
            data = analysis()
            data["monthly_revenue"] = [{"month": "9999-12", "amount": 1}]
            data["monthly_expenses"] = []
            with self.assertRaises(ValueError):
                method(data, 1)


if __name__ == "__main__":
    unittest.main()
