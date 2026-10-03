"""Verify the demo plan and seeding orchestration without touching Nessie."""
import contextlib
import io
import unittest
from unittest.mock import Mock

from backend.services.financial_analyzer import FinancialAnalyzer
from backend.services.nessie_service import NessieService, NessieServiceError
from backend.services.scenario_engine import ScenarioEngine
from scripts.seed_nessie import CUSTOMER, MONTHS, SeedError, build_plan, seed


class SeedNessieTests(unittest.TestCase):
    def service(self):
        service = Mock(spec=NessieService)
        service.get_customers.return_value = []
        service.get_merchants.return_value = [{"_id": "merchant-existing", "name": "Real API merchant"}]
        service.create_customer.return_value = {"code": 201, "objectCreated": {"_id": "customer-created"}}
        service.create_account.return_value = {"code": 201, "objectCreated": {"_id": "account-created"}}
        service.get_account.return_value = {"balance": 26000}
        for method in (service.create_deposit, service.create_purchase, service.create_bill):
            method.return_value = {"code": 201}
        return service

    def test_financial_story_and_projection(self):
        plan = build_plan()
        self.assertEqual(len(plan["deposits"]), 25)
        self.assertEqual(len(plan["purchases"]), 35)
        self.assertEqual(len(plan["bills"]), 36)
        analysis = FinancialAnalyzer().analyze_business(
            accounts=[{"type": "Checking", "balance": 26000}], **plan)
        for index, (month, revenue, expenses) in enumerate(MONTHS):
            self.assertEqual(analysis["monthly_revenue"][index], {"month": f"2026-{month:02d}", "amount": revenue})
            self.assertEqual(analysis["monthly_expenses"][index], {"month": f"2026-{month:02d}", "amount": expenses})
        result = ScenarioEngine().simulate_hire(analysis, 18, 30)
        self.assertEqual(result["baseline_monthly_cash_flow"], 6340)
        self.assertEqual(result["projected_monthly_cash_flow"], 4000)
        self.assertGreater(result["cash_projection"][-1]["scenario"], 26000)
        self.assertEqual(len(analysis["recurring_bills"]), 6)

    def test_seeds_with_actual_merchant_and_valid_payloads(self):
        service = self.service()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(seed(service), "customer-created")
        service.create_customer.assert_called_once_with(CUSTOMER)
        self.assertEqual(service.create_account.call_args.args[1]["balance"], 26000)
        self.assertEqual(service.create_deposit.call_count, 25)
        self.assertEqual(service.create_purchase.call_count, 35)
        self.assertEqual(service.create_bill.call_count, 36)
        for call in service.create_purchase.call_args_list:
            self.assertEqual(call.args[1]["merchant_id"], "merchant-existing")
        service.create_merchant.assert_not_called()
        self.assertIn("Seeding complete", output.getvalue())
        self.assertTrue(output.getvalue().rstrip().endswith("Customer ID: customer-created"))

    def test_duplicate_business_stops_before_writes(self):
        service = self.service()
        service.get_customers.return_value = [{"_id": "existing", "first_name": "ARBOR", "last_name": "Coffee Co."}]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(seed(service), "existing")
        service.create_customer.assert_not_called()
        service.get_merchants.assert_not_called()
        service.create_account.assert_not_called()

    def test_creates_merchant_when_none_available(self):
        service = self.service()
        service.get_merchants.return_value = []
        service.create_merchant.return_value = {"objectCreated": {"_id": "new-merchant"}}
        with contextlib.redirect_stdout(io.StringIO()):
            seed(service)
        service.create_merchant.assert_called_once()
        self.assertEqual(service.create_purchase.call_args.args[1]["merchant_id"], "new-merchant")

    def test_rejected_payload_stops_and_reports_position(self):
        service = self.service()
        service.create_purchase.side_effect = NessieServiceError("Nessie returned HTTP 400", 400)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(SeedError, "purchases record 1"):
            seed(service)
        service.create_bill.assert_not_called()

    def test_bad_envelope_and_missing_id(self):
        service = self.service()
        service.create_customer.return_value = {"code": 400}
        with self.assertRaisesRegex(SeedError, "code 400"):
            seed(service)
        service.create_account.assert_not_called()
        service.create_customer.return_value = "Customer created"
        with self.assertRaisesRegex(SeedError, "customer ID"):
            seed(service)

    def test_reports_balance_side_effects_instead_of_false_success(self):
        service = self.service()
        service.get_account.return_value = {"balance": 57700}
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(SeedError, "balance verification failed"):
            seed(service)


if __name__ == "__main__":
    unittest.main()
