export interface Business {
  _id: string;
  first_name?: string;
  last_name?: string;
}
export interface MonthlyAmount {
  month: string;
  amount: number;
}
export interface FinancialSignal {
  id: string;
  level: "positive" | "caution" | "neutral";
  title: string;
  explanation: string;
  value: number | null;
  unit: string;
}
export interface BreakingPoint {
  basis: string;
  cash_after_decision: number;
  monthly_cash_flow_nonnegative: boolean;
  cash_runway_months: number | null;
  runway_basis: string;
  negative_immediately: boolean;
  first_negative_month_index: number | null;
  first_negative_month: string | null;
  negative_within_horizon: boolean;
  minimum_cash_balance_within_horizon: number;
  projection_months: number;
  minimum_monthly_revenue?: number;
  maximum_monthly_employee_cost?: number | null;
  maximum_hourly_wage?: number | null;
  hourly_wage_basis?: string;
  can_sustain_employee_cost?: boolean;
  cash_buffer_amount?: number;
  cash_buffer_assumption?: string;
  maximum_one_time_amount_preserving_buffer?: number | null;
  maximum_one_time_amount_preserving_initial_buffer?: number | null;
  buffer_preserved_through_horizon?: boolean;
}
export interface StressCase {
  breaking_point?: BreakingPoint;
  assumptions: {
    revenue_reduction_percent: number;
    expense_increase_percent: number;
    basis: string;
    average_monthly_revenue: number;
    average_monthly_expenses: number;
    stressed_monthly_revenue: number;
    stressed_monthly_expenses: number;
  };
  baseline_monthly_cash_flow: number;
  projected_monthly_cash_flow: number;
  cash_projection: { month: string; baseline: number; scenario: number }[];
}
export interface Analysis {
  signals?: FinancialSignal[];
  summary: {
    revenue: number;
    expenses: number;
    net_cash_flow: number;
    cash_balance: number;
    margin: number;
  };
  expense_breakdown: Record<string, number>;
  largest_expenses: {
    id: string | null;
    description: string;
    category: string;
    amount: number;
    date: string | null;
  }[];
  monthly_revenue: MonthlyAmount[];
  monthly_expenses: MonthlyAmount[];
  trends: {
    revenue_change_percent: number | null;
    expense_change_percent: number | null;
  };
  recurring_bills: {
    id: string | null;
    payee: string | null;
    nickname: string | null;
    status: string;
    payment_amount: number;
    payment_date: string | null;
    recurring_date: number | null;
  }[];
  health: {
    has_revenue: boolean;
    positive_cash_flow: boolean;
    expenses_exceed_revenue: boolean;
    has_cash_reserve: boolean;
    upcoming_bill_total: number;
    can_cover_upcoming_bills: boolean;
    bill_coverage_ratio: number | null;
  };
}
export interface HireInputs {
  stress_test?: boolean;
  hourly_wage: number;
  hours_per_week: number;
  months: number;
}
export interface HireResult {
  breaking_point?: BreakingPoint;
  stress_test?: StressCase;
  scenario: "hire_employee";
  inputs: HireInputs;
  monthly_added_cost: number;
  baseline_monthly_cash_flow: number;
  projected_monthly_cash_flow: number;
  cash_projection: { month: string; baseline: number; scenario: number }[];
}

export type ScenarioKind =
  "hire_employee" | "equipment_purchase" | "owner_withdrawal";
export interface OneTimeInputs {
  stress_test?: boolean;
  amount: number;
  months: number;
}
export interface OneTimeResult {
  breaking_point?: BreakingPoint;
  stress_test?: StressCase;
  scenario: "equipment_purchase" | "owner_withdrawal";
  inputs: OneTimeInputs;
  one_time_cost: number;
  monthly_added_cost: number;
  baseline_monthly_cash_flow: number;
  projected_monthly_cash_flow: number;
  cash_projection: { month: string; baseline: number; scenario: number }[];
}
export type ScenarioResult = HireResult | OneTimeResult;
export const scenarioLabel = (kind: ScenarioKind) =>
  kind === "hire_employee"
    ? "After hiring"
    : kind === "equipment_purchase"
      ? "After equipment purchase"
      : "After withdrawal";

export interface CFOAnswer {
  answer: string;
  status: "answered" | "needs_information";
  facts: {
    id: string;
    label: string;
    display?: string;
    value: string | number;
    source: "historical" | "projection" | "scenario";
  }[];
  context: Record<string, unknown>;
}
