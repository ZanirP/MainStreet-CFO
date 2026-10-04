import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import DebtOverview from "./DebtOverview";
import type { Analysis, DebtAnalysis } from "../types";

afterEach(cleanup);
const debt: DebtAnalysis = {
  data_available: true,
  complete: true,
  active_loan_count: 1,
  reported_active_loan_amount: 48000,
  monthly_payment_total: 1200,
  all_active_payments_linked: true,
  payment_coverage_ratio: 0.92,
  cash_to_monthly_payment_ratio: 7.5,
  average_monthly_cash_flow_after_linked_payments: -100,
  forecast_expense_adjustment: 0,
  basis: "Linked payments counted once.",
  limitations: "APR unavailable.",
  loans: [
    {
      id: "loan-a",
      type: "business",
      status: "active",
      description: "Demo buildout equipment",
      reported_loan_amount: 48000,
      monthly_payment: 1200,
      included_in_obligations: true,
      payment_link_verified: true,
    },
  ],
};
const analysis = (value?: DebtAnalysis) => ({ debt: value }) as Analysis;

it("shows reported debt and cash payments with explicit missing-term limitations", () => {
  render(<DebtOverview analysis={analysis(debt)} />);
  expect(screen.getByRole("region", { name: "Existing debt" })).toBeTruthy();
  expect(screen.getByText("Demo buildout equipment")).toBeTruthy();
  expect(screen.getByText("0.92×")).toBeTruthy();
  expect(screen.getByText(/not verified remaining balances/)).toBeTruthy();
  expect(screen.getByText(/Linked payments are already counted/)).toBeTruthy();
});

it("distinguishes unavailable debt from verified empty loan results", () => {
  const { rerender } = render(<DebtOverview analysis={analysis()} />);
  expect(screen.getByText("Debt data unavailable")).toBeTruthy();
  expect(
    screen.getByText(/does not mean the business is debt-free/),
  ).toBeTruthy();
  rerender(
    <DebtOverview
      analysis={analysis({
        ...debt,
        active_loan_count: 0,
        loans: [],
        monthly_payment_total: 0,
        reported_active_loan_amount: 0,
      })}
    />,
  );
  expect(screen.getByText("No loans reported")).toBeTruthy();
  expect(screen.queryByText("Debt data unavailable")).toBeNull();
});

it("flags incomplete values and unverified payment inclusion without showing a fabricated zero", () => {
  render(
    <DebtOverview
      analysis={analysis({
        ...debt,
        complete: false,
        all_active_payments_linked: false,
        monthly_payment_total: null,
        payment_coverage_ratio: null,
        loans: [
          {
            ...debt.loans[0],
            monthly_payment: null,
            payment_link_verified: false,
          },
        ],
      })}
    />,
  );
  expect(screen.getByText(/Known totals below may be incomplete/)).toBeTruthy();
  expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  expect(screen.getByText(/projections do not deduct them again/)).toBeTruthy();
  expect(screen.queryByText("$0.00")).toBeNull();
});
