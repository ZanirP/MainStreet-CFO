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
  location_estimates?: LocationEstimates;
  debt?: DebtAnalysis;
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
  debt_assumptions?: DebtAssumptions;
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
  "hire_employee" | "equipment_purchase" | "owner_withdrawal" | "open_location";
export interface OneTimeInputs {
  stress_test?: boolean;
  amount: number;
  months: number;
}
export interface OneTimeResult {
  debt_assumptions?: DebtAssumptions;
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
      : kind === "open_location"
        ? "After opening"
        : "After withdrawal";

export interface LocationEstimates {
  basis: string;
  months_of_history: number;
  monthly_revenue: number | null;
  costs: Record<
    "rent" | "payroll" | "utilities" | "inventory" | "other",
    { amount: number | null; source_descriptions: string[] }
  >;
}
export interface LocationInputs {
  upfront_cost: number;
  monthly_revenue: number;
  rent: number;
  payroll: number;
  utilities: number;
  inventory: number;
  other: number;
  ramp_months: number;
  months: number;
  financing_amount: number;
  annual_interest_percent: number;
  financing_term_months: number;
  stress_test: boolean;
}
export interface LocationCase {
  monthly_added_cost: number;
  incremental_monthly_operating_cost: number;
  baseline_monthly_cash_flow: number;
  projected_monthly_cash_flow: number;
  cash_projection: {
    month: string;
    baseline: number;
    scenario: number;
    cash_funded?: number;
  }[];
  breaking_point: BreakingPoint & {
    minimum_cash_month: string;
    minimum_mature_revenue_preserving_buffer: number | null;
    buffer_revenue_requirement_unavailable_reason: string | null;
    location_standalone_break_even_revenue: number;
    minimum_additional_revenue_for_business_break_even: number;
    mature_revenue_downside_percent: number | null;
    break_even_basis: string;
  };
  monthly_operations: {
    month: string;
    ramp_percent: number;
    additional_revenue: number;
    operating_cost: number;
    hypothetical_debt_payment: number;
    combined_cash_flow: number;
  }[];
}
export interface LocationResult extends LocationCase {
  scenario: "open_location";
  cash_funding_amount: number;
  inputs: LocationInputs;
  assumptions: { basis: string; financing: string };
  hypothetical_financing: {
    amount: number;
    monthly_payment: number;
    total_interest_over_entered_term: number;
    annual_interest_percent: number;
    term_months: number;
  };
  funding_comparison: {
    cash_funded: LocationCase;
    selected_funding: { minimum_cash: number; ending_cash: number };
  };
  stress_test?: LocationCase & { assumptions: { basis: string } };
}

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

export interface DebtAssumptions {
  forecast_expense_adjustment: number;
  fixed_linked_monthly_payment: number;
  historical_average_linked_payment: number;
  all_active_payments_linked: boolean;
  basis: string;
}
export interface DebtAnalysis {
  data_available: boolean;
  complete: boolean;
  active_loan_count: number;
  reported_active_loan_amount: number | null;
  monthly_payment_total: number | null;
  all_active_payments_linked: boolean;
  payment_coverage_ratio: number | null;
  cash_to_monthly_payment_ratio: number | null;
  average_monthly_cash_flow_after_linked_payments: number | null;
  forecast_expense_adjustment: number;
  basis: string;
  limitations: string;
  loans: {
    id: string | null;
    type: string | null;
    status: string | null;
    description: string | null;
    reported_loan_amount: number | null;
    monthly_payment: number | null;
    included_in_obligations: boolean;
    payment_link_verified: boolean;
  }[];
}
