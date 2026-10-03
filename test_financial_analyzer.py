"""Offline financial calculations using Nessie-shaped records."""
import copy
import json
import unittest
from datetime import date

from backend.services.financial_analyzer import FinancialAnalyzer


class FinancialAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = FinancialAnalyzer()

    def test_complete_analysis(self):
        data = {
            "accounts": [{"type": "Checking", "balance": 200},
                         {"type": "Savings", "balance": 300},
                         {"type": "Credit Card", "balance": 900}],
            "deposits": [{"amount": 100, "transaction_date": "2026-01-01", "status": "completed"},
                         {"amount": 150, "transaction_date": "2026-02-01", "status": "completed"}],
            "purchases": [{"_id": "p", "amount": 20, "purchase_date": "2026-01-02"},
                          {"amount": 30, "purchase_date": "2026-02-02"}],
            "bills": [{"_id": "paid", "payment_amount": 10, "payment_date": "2026-02-03", "status": "completed"},
                      {"payment_amount": 40, "status": "recurring", "recurring_date": 15,
                       "upcoming_payment_date": "2026-03-15", "payee": "Utilities"}],
        }
        original = copy.deepcopy(data)
        result = self.analyzer.analyze_business(**data, as_of=date(2026, 3, 1))
        self.assertEqual(result["summary"], {"revenue": 250, "expenses": 60,
                         "net_cash_flow": 190, "cash_balance": 500, "margin": 76})
        self.assertEqual(result["expense_breakdown"], {"Bills": 10, "Purchases": 50})
        self.assertEqual([e["amount"] for e in result["largest_expenses"]], [30, 20, 10])
        self.assertEqual(result["monthly_expenses"], [{"month": "2026-01", "amount": 20},
                                                    {"month": "2026-02", "amount": 40}])
        self.assertEqual(result["trends"], {"revenue_change_percent": 50, "expense_change_percent": 100})
        self.assertEqual(result["recurring_bills"][0]["payment_date"], "2026-03-15")
        self.assertTrue(result["health"]["can_cover_upcoming_bills"])
        self.assertEqual(result["health"]["bill_coverage_ratio"], 12.5)
        self.assertEqual(data, original)
        self.assertEqual(result, self.analyzer.analyze_business(**data, as_of=date(2026, 3, 1)))
        json.dumps(result, allow_nan=False)

    def test_empty_and_zero_revenue(self):
        result = self.analyzer.analyze_business()
        self.assertEqual(result["summary"], dict.fromkeys(
            ("revenue", "expenses", "net_cash_flow", "cash_balance", "margin"), 0))
        self.assertEqual(result["monthly_revenue"], [])
        self.assertEqual(result["expense_breakdown"], {})
        self.assertIsNone(result["health"]["bill_coverage_ratio"])
        loss = self.analyzer.analyze_business(purchases=[{"amount": 10}])
        self.assertEqual(loss["summary"]["net_cash_flow"], -10)
        self.assertEqual(loss["summary"]["margin"], 0)
        self.assertTrue(loss["health"]["expenses_exceed_revenue"])

    def test_statuses_and_upcoming_dates(self):
        bills = [
            {"status": "cancelled", "payment_amount": 999},
            {"status": "pending", "payment_amount": 20, "payment_date": "2026-01-01"},
            {"status": "pending", "payment_amount": 30, "upcoming_payment_date": "2026-04-01"},
            {"status": "recurring", "payment_amount": 40, "payment_date": "2026-01-01"},
            {"status": "pending", "payment_amount": 50},
        ]
        result = self.analyzer.analyze_business(
            bills=bills, deposits=[{"amount": 999, "status": "pending"}],
            purchases=[{"amount": 999, "status": "cancelled"}], as_of=date(2026, 3, 1))
        self.assertEqual(result["summary"]["expenses"], 0)
        self.assertEqual(result["summary"]["revenue"], 0)
        self.assertEqual(len(result["recurring_bills"]), 3)
        self.assertEqual(result["health"]["upcoming_bill_total"], 120)
        self.assertFalse(result["health"]["can_cover_upcoming_bills"])

    def test_invalid_fields_and_decimal_sums(self):
        result = self.analyzer.analyze_business(
            accounts=[{}, {"balance": "bad"}, {"balance": "10.25"}],
            deposits=[None, {}, {"amount": "NaN"}, {"amount": "Infinity"},
                      {"amount": "0.1", "transaction_date": "invalid"}, {"amount": "0.2"}],
            purchases=[{"amount": 5}, {"amount": -2}], largest_expenses_limit=1)
        self.assertEqual(result["summary"]["revenue"], 0.3)
        self.assertEqual(result["summary"]["expenses"], 3)
        self.assertEqual(result["summary"]["cash_balance"], 10.25)
        self.assertEqual(result["monthly_revenue"], [])
        self.assertEqual(len(result["largest_expenses"]), 1)
        json.dumps(result, allow_nan=False)

    def test_calendar_gaps_and_zero_baseline(self):
        result = self.analyzer.analyze_business(deposits=[
            {"amount": 10, "transaction_date": "2025-12-01"},
            {"amount": 20, "transaction_date": "2026-02-01"}])
        self.assertEqual(result["monthly_revenue"], [
            {"month": "2025-12", "amount": 10}, {"month": "2026-01", "amount": 0},
            {"month": "2026-02", "amount": 20}])
        self.assertIsNone(result["trends"]["revenue_change_percent"])
        self.assertEqual(result["trends"]["expense_change_percent"], 0)
        result = self.analyzer.analyze_business(
            deposits=[{"amount": 10, "transaction_date": "2026-01-01"}],
            purchases=[{"amount": 5, "purchase_date": "2026-02-01"}])
        self.assertEqual(result["trends"]["revenue_change_percent"], -100)

    def test_explainable_signals_and_coverage(self):
        result = self.analyzer.analyze_business(
            accounts=[{"balance": 300}],
            deposits=[{"amount": 1000, "transaction_date": "2026-09-01"}, {"amount": 1100, "transaction_date": "2026-10-01"}],
            purchases=[{"amount": 500, "purchase_date": "2026-09-02"}, {"amount": 700, "purchase_date": "2026-10-02"}],
            bills=[{"status": "recurring", "payment_amount": 150}, {"status": "pending", "payment_amount": 999}])
        signals = {item["id"]: item for item in result["signals"]}
        self.assertEqual(signals["revenue_trend"]["value"], 10)
        self.assertEqual(signals["expenses_trend"]["value"], 40)
        self.assertEqual(signals["expense_growth"]["level"], "caution")
        self.assertEqual(signals["expense_growth"]["value"], 30)
        self.assertEqual(signals["recurring_obligations"]["value"], 50)
        self.assertEqual(signals["cash_coverage"]["value"], 0.5)
        self.assertEqual(signals["cash_coverage"]["level"], "caution")
        self.assertEqual(result["signals"][0]["level"], "caution")
        self.assertTrue(all(item["explanation"] for item in result["signals"]))

    def test_signals_missing_data_do_not_claim_growth(self):
        signals = {item["id"]: item for item in self.analyzer.analyze_business()["signals"]}
        self.assertTrue(all(item["value"] is None for item in signals.values()))
        self.assertTrue(all(item["level"] == "neutral" for item in signals.values()))
        result = self.analyzer.analyze_business(deposits=[{"amount": 100, "transaction_date": "2026-10-01"}])
        self.assertIsNone(next(item for item in result["signals"] if item["id"] == "revenue_trend")["value"])


if __name__ == "__main__":
    unittest.main()
