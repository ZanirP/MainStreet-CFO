"""Deterministic what-if projections from FinancialAnalyzer output."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING
from typing import Any, Mapping


class ScenarioEngine:
    """Project recurring wages or one-time cash outflows without assumed growth."""

    def simulate_hire(
        self, current_analysis: Mapping[str, Any], hourly_wage: float,
        hours_per_week: float, months: int = 6, *, stress_test: bool = False,
    ) -> dict[str, Any]:
        """Average the supplied monthly history and project after its latest month.

        Both paths start from summary.cash_balance. The first entry is the
        end-of-month balance after one month of cash flow. Missing history is
        rejected; explicit zero-valued history is valid. No system clock is used.
        """
        if not isinstance(stress_test, bool):
            raise ValueError("stress_test must be a boolean")
        wage = self._amount(hourly_wage, "hourly_wage")
        hours = self._amount(hours_per_week, "hours_per_week")
        if wage < 0 or hours < 0:
            raise ValueError("hourly_wage and hours_per_week must be nonnegative")
        cash, baseline, last_month = self._projection_context(current_analysis, months)
        # Keep full decimal precision until presentation, avoiding cumulative penny drift.
        added_cost = wage * hours * 52 / 12
        scenario_flow = baseline - added_cost
        try:
            result = {
                "scenario": "hire_employee",
                "inputs": {"hourly_wage": float(wage), "hours_per_week": float(hours), "months": months},
                "monthly_added_cost": self._number(added_cost),
                "baseline_monthly_cash_flow": self._number(baseline),
                "projected_monthly_cash_flow": self._number(scenario_flow),
                "cash_projection": self._projection(cash, baseline, scenario_flow, last_month, months),
            }
            avg_revenue, avg_expenses = self._monthly_averages(current_analysis)
            result["breaking_point"] = self._decision_limits(
                cash, avg_revenue, avg_expenses, last_month, months,
                monthly_cost=added_cost, hours_per_week=hours,
            )
            if stress_test:
                result["stress_test"] = self._stress_case(current_analysis, cash, last_month, months, added_cost, hours_per_week=hours)
            return result
        except (InvalidOperation, OverflowError):
            raise ValueError("Financial values exceed the supported numeric range") from None

    def simulate_equipment(self, current_analysis: Mapping[str, Any], amount: float,
                           months: int = 6, *, stress_test: bool = False) -> dict[str, Any]:
        """Pay for equipment once, before the first projected month's cash flow."""
        return self._simulate_one_time(current_analysis, amount, months, "equipment_purchase", stress_test)

    def simulate_withdrawal(self, current_analysis: Mapping[str, Any], amount: float,
                            months: int = 6, *, stress_test: bool = False) -> dict[str, Any]:
        """Withdraw owner cash once; ongoing operating cash flow stays unchanged."""
        return self._simulate_one_time(current_analysis, amount, months, "owner_withdrawal", stress_test)

    def _simulate_one_time(self, current_analysis: Mapping[str, Any], amount: float,
                           months: int, scenario: str, stress_test: bool = False) -> dict[str, Any]:
        if not isinstance(stress_test, bool):
            raise ValueError("stress_test must be a boolean")
        cost = self._amount(amount, "amount")
        if cost < 0:
            raise ValueError("amount must be nonnegative")
        cash, baseline, last_month = self._projection_context(current_analysis, months)
        try:
            result = {
                "scenario": scenario,
                "inputs": {"amount": float(cost), "months": months},
                "one_time_cost": self._number(cost),
                "monthly_added_cost": 0.0,
                "baseline_monthly_cash_flow": self._number(baseline),
                "projected_monthly_cash_flow": self._number(baseline),
                "cash_projection": self._projection(
                    cash, baseline, baseline, last_month, months, upfront_cost=cost
                ),
            }
            avg_revenue, avg_expenses = self._monthly_averages(current_analysis)
            result["breaking_point"] = self._decision_limits(
                cash, avg_revenue, avg_expenses, last_month, months, upfront_cost=cost,
            )
            if stress_test:
                result["stress_test"] = self._stress_case(current_analysis, cash, last_month, months, upfront_cost=cost)
            return result
        except (InvalidOperation, OverflowError):
            raise ValueError("Financial values exceed the supported numeric range") from None

    def _projection_context(self, current_analysis: Mapping[str, Any], months: int
                            ) -> tuple[Decimal, Decimal, int]:
        if isinstance(months, bool) or not isinstance(months, int) or months <= 0:
            raise ValueError("months must be a positive integer")
        if not isinstance(current_analysis, Mapping):
            raise ValueError("Financial analysis is required")
        summary = current_analysis.get("summary")
        if not isinstance(summary, Mapping):
            raise ValueError("Financial analysis must contain summary.cash_balance")
        cash = self._amount(summary.get("cash_balance"), "cash_balance")
        baseline, last_month = self._baseline(current_analysis)
        if last_month + months > 9999 * 12 + 11:
            raise ValueError("Projection extends beyond the supported calendar")
        return cash, baseline, last_month

    @staticmethod
    def _amount(value: Any, field: str) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError(f"{field} must be a finite number")
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError(f"{field} must be a finite number")
        return amount

    def _monthly_amounts(self, entries: Any, field: str) -> dict[int, Decimal]:
        if not isinstance(entries, list):
            raise ValueError(f"Financial analysis must contain {field}")
        result = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError(f"Invalid entry in {field}")
            month = entry.get("month")
            if (not isinstance(month, str) or len(month) != 7 or month[4] != "-"
                    or not month[:4].isascii() or not month[:4].isdigit()
                    or not month[5:].isascii() or not month[5:].isdigit()):
                raise ValueError(f"Invalid month in {field}; expected YYYY-MM")
            try:
                year, month_number = int(month[:4]), int(month[5:])
            except ValueError:
                raise ValueError(f"Invalid month in {field}; expected YYYY-MM") from None
            if not 1 <= year <= 9999 or not 1 <= month_number <= 12:
                raise ValueError(f"Invalid month in {field}; expected YYYY-MM")
            index = year * 12 + month_number - 1
            if index in result:
                raise ValueError(f"Duplicate month in {field}")
            result[index] = self._amount(entry.get("amount"), f"{field}.amount")
        return result

    def _baseline(self, analysis: Mapping[str, Any]) -> tuple[Decimal, int]:
        """Mean net flow across the full calendar span, counting missing months as zero."""
        revenue = self._monthly_amounts(analysis.get("monthly_revenue"), "monthly_revenue")
        expenses = self._monthly_amounts(analysis.get("monthly_expenses"), "monthly_expenses")
        calendar = revenue.keys() | expenses.keys()
        if not calendar:
            raise ValueError("Monthly financial history is required to simulate a scenario")
        first, last = min(calendar), max(calendar)
        avg_revenue, avg_expenses = self._monthly_averages(analysis)
        return avg_revenue - avg_expenses, last

    def _monthly_averages(self, analysis: Mapping[str, Any]) -> tuple[Decimal, Decimal]:
        revenue = self._monthly_amounts(analysis.get("monthly_revenue"), "monthly_revenue")
        expenses = self._monthly_amounts(analysis.get("monthly_expenses"), "monthly_expenses")
        calendar = revenue.keys() | expenses.keys()
        if not calendar:
            raise ValueError("Monthly financial history is required to simulate a scenario")
        count = max(calendar) - min(calendar) + 1
        return (sum(revenue.values(), Decimal(0)) / count,
                sum(expenses.values(), Decimal(0)) / count)

    def _stress_case(self, analysis: Mapping[str, Any], cash: Decimal, last_month: int,
                     months: int, monthly_cost: Decimal = Decimal(0),
                     upfront_cost: Decimal = Decimal(0),
                     hours_per_week: Decimal | None = None) -> dict[str, Any]:
        """Reduce positive average revenue 10%, increase positive average expenses 10%.

        Signed credits/refunds retain their original value; changes never improve
        the baseline. Hiring wages and one-time outflows are unchanged.
        """
        avg_revenue, avg_expenses = self._monthly_averages(analysis)
        stressed_revenue = avg_revenue - max(avg_revenue, Decimal(0)) * Decimal("0.10")
        stressed_expenses = avg_expenses + max(avg_expenses, Decimal(0)) * Decimal("0.10")
        baseline = stressed_revenue - stressed_expenses
        return {
            "assumptions": {"revenue_reduction_percent": 10, "expense_increase_percent": 10,
                "basis": "Full historical calendar average; gaps count as zero. Percent changes apply only to positive averages. Scenario costs remain unchanged.",
                "average_monthly_revenue": self._number(avg_revenue),
                "average_monthly_expenses": self._number(avg_expenses),
                "stressed_monthly_revenue": self._number(stressed_revenue),
                "stressed_monthly_expenses": self._number(stressed_expenses)},
            "baseline_monthly_cash_flow": self._number(baseline),
            "projected_monthly_cash_flow": self._number(baseline - monthly_cost),
            "cash_projection": self._projection(cash, baseline, baseline - monthly_cost,
                                                 last_month, months, upfront_cost=upfront_cost),
            "breaking_point": self._decision_limits(
                cash, stressed_revenue, stressed_expenses, last_month, months,
                monthly_cost=monthly_cost, upfront_cost=upfront_cost, hours_per_week=hours_per_week,
            ),
        }

    def _decision_limits(
        self, cash: Decimal, revenue: Decimal, expenses: Decimal, last_month: int,
        months: int, *, monthly_cost: Decimal = Decimal(0),
        upfront_cost: Decimal = Decimal(0), hours_per_week: Decimal | None = None,
    ) -> dict[str, Any]:
        """Solve the same constant-flow cash equation used by _projection.

        Runway is time to zero under uniform monthly burn. The first negative
        end-of-month balance is floor(cash / burn) + 1: zero is not negative.
        An upfront shortfall counts as immediately negative even if revenue later
        restores cash. No date is invented for that instant (month index zero).
        """
        starting_cash = cash - upfront_cost
        baseline = revenue - expenses
        flow = baseline - monthly_cost
        immediate = starting_cash < 0
        runway = Decimal(0)
        first_negative = None
        if immediate:
            first_negative = 0
        elif flow < 0:
            runway = starting_cash / -flow
            first_negative = int(runway.to_integral_value(rounding=ROUND_FLOOR)) + 1
        else:
            runway = None
        first_date = None
        if first_negative is not None and first_negative > 0:
            year, month = divmod(last_month + first_negative, 12)
            if year <= 9999:
                first_date = f"{year:04d}-{month + 1:02d}"
        minimum_cash = starting_cash + min(Decimal(0), flow * months)
        limits = {
            "basis": "Constant historical average monthly cash flow; calendar gaps count as zero. Limits are model thresholds, not guarantees of safety.",
            "cash_after_decision": self._number(starting_cash),
            "monthly_cash_flow_nonnegative": flow >= 0,
            "cash_runway_months": self._number(runway) if runway is not None else None,
            "runway_basis": "Time to zero at constant net monthly burn. Null means cash does not deplete under this model; zero means no reserve before a loss or an immediate shortfall.",
            "negative_immediately": immediate,
            "first_negative_month_index": first_negative,
            "first_negative_month": first_date,
            "negative_within_horizon": first_negative is not None and first_negative <= months,
            "minimum_cash_balance_within_horizon": self._number(minimum_cash),
            "projection_months": months,
        }
        if hours_per_week is not None:
            # A negative baseline cannot sustain even zero additional employee cost.
            capacity = baseline if baseline >= 0 else None
            hourly_cap = capacity * 12 / (hours_per_week * 52) if capacity is not None and hours_per_week > 0 else None
            limits.update({
                "minimum_monthly_revenue": self._limit_number(max(Decimal(0), expenses + monthly_cost), ROUND_CEILING),
                "maximum_monthly_employee_cost": self._limit_number(capacity) if capacity is not None else None,
                "maximum_hourly_wage": self._limit_number(hourly_cap) if hourly_cap is not None else None,
                "hourly_wage_basis": "At entered weekly hours, using 52 / 12 weeks per month. Null means no feasible cost at a negative baseline, or no wage ceiling at zero hours.",
                "can_sustain_employee_cost": capacity is not None and monthly_cost <= capacity,
            })
        else:
            # Explicit policy assumption: keep one month of average operating expenses.
            buffer = max(Decimal(0), expenses)
            initial_capacity = cash - buffer
            horizon_capacity = cash + min(Decimal(0), baseline * months) - buffer
            limits.update({
                "cash_buffer_amount": self._limit_number(buffer, ROUND_CEILING),
                "cash_buffer_assumption": "Keep one month of positive average operating expenses from the decision instant through every projected month. This is an illustrative buffer assumption, not a universal safety rule.",
                "maximum_one_time_amount_preserving_buffer": self._limit_number(horizon_capacity) if horizon_capacity >= 0 else None,
                "maximum_one_time_amount_preserving_initial_buffer": self._limit_number(initial_capacity) if initial_capacity >= 0 else None,
                "buffer_preserved_through_horizon": minimum_cash >= buffer,
            })
        return limits

    @staticmethod
    def _limit_number(value: Decimal, rounding=ROUND_FLOOR) -> float:
        """Round ceilings down and required minima up to avoid overstating capacity."""
        return float(value.quantize(Decimal("0.01"), rounding=rounding))

    @staticmethod
    def _number(value: Decimal) -> float:
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _projection(
        self, cash: Decimal, baseline: Decimal, scenario: Decimal, last_month: int, months: int,
        *, upfront_cost: Decimal = Decimal(0),
    ) -> list[dict[str, Any]]:
        result = []
        for offset in range(1, months + 1):
            year, month = divmod(last_month + offset, 12)
            result.append({
                "month": f"{year:04d}-{month + 1:02d}",
                "baseline": self._number(cash + baseline * offset),
                "scenario": self._number(cash - upfront_cost + scenario * offset),
            })
        return result
