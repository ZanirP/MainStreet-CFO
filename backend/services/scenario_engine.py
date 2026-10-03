"""Deterministic what-if projections from FinancialAnalyzer output."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping


class ScenarioEngine:
    """Project wages only; no assumed taxes, benefits, growth, or hiring revenue."""

    def simulate_hire(
        self, current_analysis: Mapping[str, Any], hourly_wage: float,
        hours_per_week: float, months: int = 6,
    ) -> dict[str, Any]:
        """Average the supplied monthly history and project after its latest month.

        Both paths start from summary.cash_balance. The first entry is the
        end-of-month balance after one month of cash flow. Missing history is
        rejected; explicit zero-valued history is valid. No system clock is used.
        """
        wage = self._amount(hourly_wage, "hourly_wage")
        hours = self._amount(hours_per_week, "hours_per_week")
        if wage < 0 or hours < 0:
            raise ValueError("hourly_wage and hours_per_week must be nonnegative")
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
        # Keep full decimal precision until presentation, avoiding cumulative penny drift.
        added_cost = wage * hours * 52 / 12
        scenario_flow = baseline - added_cost
        try:
            return {
                "scenario": "hire_employee",
                "inputs": {"hourly_wage": float(wage), "hours_per_week": float(hours), "months": months},
                "monthly_added_cost": self._number(added_cost),
                "baseline_monthly_cash_flow": self._number(baseline),
                "projected_monthly_cash_flow": self._number(scenario_flow),
                "cash_projection": self._projection(cash, baseline, scenario_flow, last_month, months),
            }
        except (InvalidOperation, OverflowError):
            raise ValueError("Financial values exceed the supported numeric range") from None

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
            raise ValueError("Monthly financial history is required to simulate hiring")
        first, last = min(calendar), max(calendar)
        net = sum(revenue.values(), Decimal(0)) - sum(expenses.values(), Decimal(0))
        return net / (last - first + 1), last

    @staticmethod
    def _number(value: Decimal) -> float:
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _projection(
        self, cash: Decimal, baseline: Decimal, scenario: Decimal, last_month: int, months: int,
    ) -> list[dict[str, Any]]:
        result = []
        for offset in range(1, months + 1):
            year, month = divmod(last_month + offset, 12)
            result.append({
                "month": f"{year:04d}-{month + 1:02d}",
                "baseline": self._number(cash + baseline * offset),
                "scenario": self._number(cash + scenario * offset),
            })
        return result
