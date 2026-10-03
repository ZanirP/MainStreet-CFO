import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import DecisionLimits from "./DecisionLimits";
import type { BreakingPoint } from "../types";

afterEach(cleanup);
const limits: BreakingPoint = {
  basis: "Constant historical average monthly cash flow.",
  cash_after_decision: 1000,
  monthly_cash_flow_nonnegative: false,
  cash_runway_months: 10,
  runway_basis: "Time to zero at constant monthly burn.",
  negative_immediately: false,
  first_negative_month_index: 11,
  first_negative_month: "2027-11",
  negative_within_horizon: false,
  minimum_cash_balance_within_horizon: 0,
  projection_months: 10,
  minimum_monthly_revenue: 6340,
  maximum_monthly_employee_cost: 7000,
  maximum_hourly_wage: 53.84,
  can_sustain_employee_cost: false,
};

it("shows hire thresholds and distinguishes zero cash from a later shortfall", () => {
  render(<DecisionLimits limits={limits} kind="hire_employee" />);
  expect(screen.getByText("$6,340.00")).toBeTruthy();
  expect(screen.getByText("$53.84 / hour")).toBeTruthy();
  expect(screen.getByText(/month 11; beyond selected horizon/)).toBeTruthy();
  expect(
    screen.getByText(/Cash stays nonnegative through this horizon/),
  ).toBeTruthy();
  expect(
    screen.getByText(/Entered wages result in negative monthly cash flow/),
  ).toBeTruthy();
});

it("explains an unbounded zero-hours wage and nondepleting cash", () => {
  render(
    <DecisionLimits
      kind="hire_employee"
      limits={{
        ...limits,
        maximum_hourly_wage: null,
        cash_runway_months: null,
        first_negative_month_index: null,
        first_negative_month: null,
      }}
    />,
  );
  expect(screen.getByText("No ceiling at zero hours")).toBeTruthy();
  expect(screen.getByText("No depletion in this model")).toBeTruthy();
});

it("shows immediate one-time shortfalls and labels the buffer assumption in stress limits", () => {
  render(
    <DecisionLimits
      kind="owner_withdrawal"
      stressCase
      limits={{
        ...limits,
        negative_immediately: true,
        negative_within_horizon: true,
        first_negative_month_index: 0,
        first_negative_month: null,
        cash_runway_months: 0,
        maximum_one_time_amount_preserving_buffer: null,
        cash_buffer_amount: 4000,
        cash_buffer_assumption:
          "Illustrative one-month operating expense buffer.",
        buffer_preserved_through_horizon: false,
      }}
    />,
  );
  expect(screen.getByText("Stress-case decision limits")).toBeTruthy();
  expect(screen.getByText("Buffer not achievable")).toBeTruthy();
  expect(
    screen.getByText("Immediately, before monthly cash flow"),
  ).toBeTruthy();
  expect(
    screen.getByText("Illustrative one-month operating expense buffer."),
  ).toBeTruthy();
  expect(
    screen.getByText(/Cash becomes negative within this horizon/),
  ).toBeTruthy();
});
