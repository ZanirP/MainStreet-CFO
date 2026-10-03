export interface Business {
  _id: string;
  first_name?: string;
  last_name?: string;
}
export interface MonthlyAmount {
  month: string;
  amount: number;
}
export interface Analysis {
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
  hourly_wage: number;
  hours_per_week: number;
  months: number;
}
export interface HireResult {
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
  amount: number;
  months: number;
}
export interface OneTimeResult {
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
