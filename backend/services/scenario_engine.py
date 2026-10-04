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
            result["debt_assumptions"] = self._debt_assumptions(current_analysis)
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
            result["debt_assumptions"] = self._debt_assumptions(current_analysis)
            result["breaking_point"] = self._decision_limits(
                cash, avg_revenue, avg_expenses, last_month, months, upfront_cost=cost,
            )
            if stress_test:
                result["stress_test"] = self._stress_case(current_analysis, cash, last_month, months, upfront_cost=cost)
            return result
        except (InvalidOperation, OverflowError):
            raise ValueError("Financial values exceed the supported numeric range") from None

    def simulate_location(
        self, current_analysis: Mapping[str, Any], upfront_cost: float,
        monthly_revenue: float, rent: float, payroll: float, utilities: float,
        inventory: float, other: float, ramp_months: int = 3, months: int = 6,
        financing_amount: float = 0, annual_interest_percent: float = 0,
        financing_term_months: int = 60, *, stress_test: bool = False,
    ) -> dict[str, Any]:
        """Hypothetical expansion only; no API writes or inferred loan terms.

        Full costs begin immediately. Revenue is mature revenue * min(k/ramp, 1).
        Financing is received at opening and amortizes monthly, starting in month
        one; no fees, balloon payment or tax treatment is assumed.
        """
        if not isinstance(stress_test, bool):
            raise ValueError("stress_test must be a boolean")
        values = {name: self._amount(value, name) for name, value in (
            ("upfront_cost", upfront_cost), ("monthly_revenue", monthly_revenue),
            ("rent", rent), ("payroll", payroll), ("utilities", utilities),
            ("inventory", inventory), ("other", other), ("financing_amount", financing_amount),
            ("annual_interest_percent", annual_interest_percent))}
        if any(value < 0 or value > Decimal("1e12") for value in values.values()):
            raise ValueError("Location costs, revenue and financing inputs must be nonnegative and within the supported numeric range")
        for name, value, maximum in (("ramp_months", ramp_months, 120), ("months", months, 120),
                                     ("financing_term_months", financing_term_months, 360)):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be a positive whole number within the supported horizon")
        if values["financing_amount"] > values["upfront_cost"]:
            raise ValueError("financing_amount cannot exceed upfront_cost")
        if values["annual_interest_percent"] > 100:
            raise ValueError("annual_interest_percent exceeds the supported numeric range")
        cash, baseline, last = self._projection_context(current_analysis, months)
        revenue, expenses = self._monthly_averages(current_analysis)
        cost = sum((values[name] for name in ("rent", "payroll", "utilities", "inventory", "other")), Decimal(0))
        principal = values["financing_amount"]
        rate = values["annual_interest_percent"] / 1200
        payment = principal * rate / (1 - (1 + rate) ** -financing_term_months) if rate else principal / financing_term_months
        inputs = {**{name: float(value) for name, value in values.items()},
                  "ramp_months": ramp_months, "months": months, "financing_term_months": financing_term_months,
                  "stress_test": stress_test}
        result = self._location_case(cash, baseline, expenses, last, months, values["upfront_cost"],
                                     values["monthly_revenue"], cost, ramp_months, principal, payment, financing_term_months)
        cash_case = self._location_case(cash, baseline, expenses, last, months, values["upfront_cost"],
                                        values["monthly_revenue"], cost, ramp_months, Decimal(0), Decimal(0), financing_term_months)
        if principal:
            for row, alternative in zip(result["cash_projection"], cash_case["cash_projection"]):
                row["cash_funded"] = alternative["scenario"]
        result.update({"scenario": "open_location", "inputs": inputs,
                       "one_time_cost": self._number(values["upfront_cost"]),
                       "cash_funding_amount": self._number(values["upfront_cost"] - principal),
                       "debt_assumptions": {**self._debt_assumptions(current_analysis), "basis": "Existing Nessie loan payments are included once in current-business baseline and held fixed in stress. Hypothetical expansion financing is modeled separately, with no real loan creation."},
                       "assumptions": {"basis": "Existing business keeps its full historical average cash flow, with verified debt counted once. New-location costs and mature revenue are user assumptions. All costs start in month one; revenue ramps linearly to full revenue in ramp_months. No cannibalization, seasonality, taxes, inflation, delays or extra working capital is modeled.",
                                       "financing": "Hypothetical fixed-rate fully amortizing loan, funded at opening; monthly payments start immediately and stop after the entered term. No financing fees or approval are assumed.",
                                       "historical_starting_estimates": current_analysis.get("location_estimates")},
                       "funding_comparison": {"cash_funded": cash_case, "selected_funding": {
                           "minimum_cash": result["breaking_point"]["minimum_cash_balance_within_horizon"],
                           "ending_cash": result["cash_projection"][-1]["scenario"]}},
                       "hypothetical_financing": {"amount": self._number(principal), "monthly_payment": self._number(payment),
                           "total_interest_over_entered_term": self._number(max(Decimal(0), payment * financing_term_months - principal)),
                           "annual_interest_percent": float(values["annual_interest_percent"]), "term_months": financing_term_months}})
        if stress_test:
            fixed = self._amount(self._debt_assumptions(current_analysis)["fixed_linked_monthly_payment"], "linked debt")
            stressed_revenue = revenue - max(revenue, Decimal(0)) / 10
            stressed_expenses = expenses + max(expenses - fixed, Decimal(0)) / 10
            stressed = self._location_case(cash, stressed_revenue - stressed_expenses, stressed_expenses, last, months,
                values["upfront_cost"], values["monthly_revenue"] * Decimal("0.9"), cost * Decimal("1.1"),
                ramp_months, principal, payment, financing_term_months)
            stressed["assumptions"] = {"revenue_reduction_percent": 10, "expense_increase_percent": 10,
                "average_monthly_revenue": self._number(revenue), "average_monthly_expenses": self._number(expenses),
                "stressed_monthly_revenue": self._number(stressed_revenue), "stressed_monthly_expenses": self._number(stressed_expenses),
                "basis": "Existing and new-location revenue 10% lower; positive operating expenses 10% higher. Linked existing and hypothetical loan payments, upfront cost and ramp stay fixed."}
            result["stress_test"] = stressed
        return result

    def _location_case(self, cash, baseline, existing_expenses, last, months, upfront, mature,
                       cost, ramp, principal, payment, term) -> dict[str, Any]:
        mature_payment = payment if ramp <= term else Decimal(0)
        ramps = [min(Decimal(k) / ramp, Decimal(1)) for k in range(1, months + 1)]
        payments = [payment if k <= term else Decimal(0) for k in range(1, months + 1)]
        # Multiply before dividing to avoid a separately rounded 1/3 ramp
        # turning an exact break-even boundary into a spurious extra cent.
        sales = [mature * min(k, ramp) / ramp for k in range(1, months + 1)]
        flows = [baseline + sale - cost - paid for sale, paid in zip(sales, payments)]
        start = cash - upfront + principal
        rows = self._projection(cash, baseline, baseline, last, months, upfront_cost=upfront-principal,
                                scenario_flows=flows)
        negative = 0 if start < 0 else next((k for k, row in enumerate(rows, 1) if row["scenario_cash_negative"]), None)
        buffer = max(Decimal(0), existing_expenses + cost + payment)
        # Solve every ramp-month cash inequality. Opening cash below the buffer
        # cannot be repaired by future sales, so the horizon threshold is null.
        required = None
        if start >= buffer:
            required = max(Decimal(0), max((buffer - start - baseline*k + cost*k + sum(payments[:k], Decimal(0))) * ramp /
                         sum(min(j, ramp) for j in range(1,k+1)) for k in range(1, months+1)))
        runway = None
        if negative == 0:
            runway = Decimal(0)
        elif negative is not None:
            previous = start + sum(flows[:negative-1], Decimal(0))
            runway = Decimal(negative-1) + previous / -flows[negative-1]
        minimum = min([start] + [start + sum(flows[:k], Decimal(0)) for k in range(1, months+1)])
        limits = self._decision_limits(cash, baseline + existing_expenses, existing_expenses + cost,
                                      last, months, monthly_cost=payment, upfront_cost=upfront-principal)
        limits.update({"basis": "Exact ramp-month cash trajectory, including opening cash and monthly hypothetical loan payments. No safety guarantee.",
            "cash_after_decision": self._number(start), "cash_runway_months": self._number(runway) if runway is not None else None,
            "runway_basis": "Interpolated first cash depletion within this horizon; null means no depletion observed, not infinite runway. Intra-month timing otherwise unavailable.",
            "negative_immediately": start < 0, "negative_within_horizon": negative is not None,
            "first_negative_month_index": negative,
            "first_negative_month": rows[negative-1]["month"] if negative else None,
            "minimum_cash_balance_within_horizon": self._number(minimum),
            "minimum_cash_month": "opening" if minimum == start else rows[next(k for k in range(months) if start + sum(flows[:k+1], Decimal(0)) == minimum)]["month"],
            "monthly_cash_flow_nonnegative": all(flow >= 0 for flow in flows),
            "cash_buffer_amount": self._limit_number(buffer, ROUND_CEILING),
            "cash_buffer_assumption": "Illustrative reserve: one month of combined average existing cash expenses, new-location expenses and hypothetical debt service; required from opening onward.",
            "buffer_preserved_through_horizon": minimum >= buffer,
            "minimum_mature_revenue_preserving_buffer": self._limit_number(required, ROUND_CEILING) if required is not None else None,
            "buffer_revenue_requirement_unavailable_reason": "Opening cash is already below the illustrative buffer; future revenue cannot fix that instant." if required is None else None,
            "location_standalone_break_even_revenue": self._limit_number(cost + mature_payment, ROUND_CEILING),
            "minimum_additional_revenue_for_business_break_even": self._limit_number(max(Decimal(0), cost + mature_payment - baseline), ROUND_CEILING),
            "additional_revenue_break_even_while_financing_active": self._limit_number(max(Decimal(0), cost + payment - baseline), ROUND_CEILING),
            "break_even_basis": "Cash-flow break-even at the first mature month, using hypothetical payments still due then. If financing ends before maturity, its payment is zero at maturity. Ramp-month liquidity is assessed separately; this is not accounting profit.",
            "mature_revenue_downside_percent": self._limit_number((mature - max(Decimal(0), cost+mature_payment-baseline)) / mature * 100) if mature > 0 and mature >= max(Decimal(0), cost+mature_payment-baseline) else None,
            "maximum_one_time_amount_preserving_buffer": None,
            "maximum_one_time_amount_preserving_initial_buffer": None})
        return {"monthly_added_cost": self._number(cost + payment), "incremental_monthly_operating_cost": self._number(cost),
                "baseline_monthly_cash_flow": self._number(baseline),
                "projected_monthly_cash_flow": self._number(baseline + mature - cost - mature_payment),
                "mature_flow_basis": "Cash flow at the first mature month; hypothetical payments stop after term and may have ended before maturity. Maturity may be outside the selected horizon.",
                "cash_projection": rows, "breaking_point": limits,
                "monthly_operations": [{"month": row["month"], "ramp_percent": self._number(factor*100),
                    "additional_revenue": self._number(sale), "operating_cost": self._number(cost),
                    "hypothetical_debt_payment": self._number(paid), "combined_cash_flow": self._number(flow)}
                    for row, factor, paid, flow, sale in zip(rows, ramps, payments, flows, sales)]}

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
        adjustment = self._debt_assumptions(analysis)["forecast_expense_adjustment"]
        return (sum(revenue.values(), Decimal(0)) / count,
                sum(expenses.values(), Decimal(0)) / count + self._amount(adjustment, "debt.forecast_expense_adjustment"))

    def _debt_assumptions(self, analysis: Mapping[str, Any]) -> dict[str, Any]:
        debt = analysis.get("debt") or {}
        return {"forecast_expense_adjustment": debt.get("forecast_expense_adjustment", 0),
                "fixed_linked_monthly_payment": debt.get("linked_monthly_payment", 0),
                "historical_average_linked_payment": debt.get("historical_average_linked_payment", 0),
                "all_active_payments_linked": debt.get("all_active_payments_linked", False),
                "basis": "Explicitly linked historical debt payments are replaced by their current monthly payment, counted once. Linked payments stay constant for the projection horizon and are not increased by stress. Unlinked payments may already be in expenses; no additional deduction is guessed. No principal, APR, payoff or borrowing is projected."}

    def _stress_case(self, analysis: Mapping[str, Any], cash: Decimal, last_month: int,
                     months: int, monthly_cost: Decimal = Decimal(0),
                     upfront_cost: Decimal = Decimal(0),
                     hours_per_week: Decimal | None = None) -> dict[str, Any]:
        """Reduce positive revenue 10%; increase expenses excluding linked debt 10%.

        Signed credits/refunds retain their original value; changes never improve
        the baseline. Hiring wages and one-time outflows are unchanged.
        """
        avg_revenue, avg_expenses = self._monthly_averages(analysis)
        fixed_debt = self._amount(self._debt_assumptions(analysis)["fixed_linked_monthly_payment"], "debt.linked_monthly_payment")
        stressed_revenue = avg_revenue - max(avg_revenue, Decimal(0)) * Decimal("0.10")
        stressed_expenses = avg_expenses + max(avg_expenses - fixed_debt, Decimal(0)) * Decimal("0.10")
        baseline = stressed_revenue - stressed_expenses
        return {
            "assumptions": {"revenue_reduction_percent": 10, "expense_increase_percent": 10,
                "basis": "Full historical calendar average; gaps count as zero. Revenue falls 10%; positive expenses excluding explicitly linked fixed debt payments rise 10%. Existing linked debt payments and scenario costs remain unchanged.",
                "fixed_monthly_debt_payment": self._number(fixed_debt),
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
            # Explicit policy assumption: keep one month of average cash expenses.
            buffer = max(Decimal(0), expenses)
            initial_capacity = cash - buffer
            horizon_capacity = cash + min(Decimal(0), baseline * months) - buffer
            limits.update({
                "cash_buffer_amount": self._limit_number(buffer, ROUND_CEILING),
                "cash_buffer_assumption": "Keep one month of positive average cash expenses, including linked debt payments, from the decision instant through every projected month. This is an illustrative buffer assumption, not a universal safety rule.",
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
        *, upfront_cost: Decimal = Decimal(0), scenario_flows: list[Decimal] | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        scenario_cash = cash - upfront_cost
        for offset in range(1, months + 1):
            scenario_cash = (scenario_cash + scenario_flows[offset-1] if scenario_flows is not None
                             else cash - upfront_cost + scenario * offset)
            year, month = divmod(last_month + offset, 12)
            result.append({
                "month": f"{year:04d}-{month + 1:02d}",
                "baseline": self._number(cash + baseline * offset),
                "scenario": self._number(scenario_cash),
                **({"scenario_cash_negative": scenario_cash < 0} if scenario_flows is not None else {}),
            })
        return result
