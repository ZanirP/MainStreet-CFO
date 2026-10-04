"""Deterministic financial metrics from supplied records, with no API dependencies."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

Record = Mapping[str, Any]
Records = Sequence[Record] | None
ZERO = Decimal("0")


class FinancialAnalyzer:
    """Cash-flow proxy: deposits are treated as revenue, not accounting profit.

    Completed and status-less transactions count toward realized totals. Pending,
    cancelled, and recurring obligations do not. Categories are source-based
    because the supplied contracts contain no category field. Inputs are not mutated.
    """

    def analyze_business(
        self,
        accounts: Records = None,
        deposits: Records = None,
        purchases: Records = None,
        bills: Records = None,
        loans: Records = None,
        *,
        as_of: date | None = None,
        largest_expenses_limit: int = 5,
    ) -> dict[str, Any]:
        """Analyze flat lists from GET responses, aggregated across supplied accounts.

        Without as_of, all pending/recurring bills are listed; with it, dated
        one-time bills before that date are excluded. No current-clock dependency.
        Missing/invalid amounts count as zero; invalid dates are omitted from
        monthly series but their amounts remain in totals. Cash excludes credit
        cards; accounts with missing type are included as a fallback.
        """
        accounts, deposits, purchases, bills = map(
            self._records, (accounts, deposits, purchases, bills)
        )
        revenue_entries = self._transactions(deposits, "amount", "transaction_date", "Deposits")
        expenses = self._transactions(purchases, "amount", "purchase_date", "Purchases")
        expenses += self._transactions(bills, "payment_amount", "payment_date", "Bills")
        revenue = self._total(revenue_entries)
        expense_total = self._total(expenses)
        net = revenue - expense_total
        cash = self._cash_balance(accounts)
        monthly_revenue, monthly_expenses = self._monthly_series(revenue_entries, expenses)
        recurring = self._upcoming_bills(bills, as_of)
        debt = self._debt(loans, bills, monthly_revenue, monthly_expenses, cash)
        return {
            "summary": {
                "revenue": self._number(revenue),
                "expenses": self._number(expense_total),
                "net_cash_flow": self._number(net),
                "cash_balance": self._number(cash),
                "margin": self._number(net / revenue * 100) if revenue else 0.0,
            },
            "expense_breakdown": self._expense_breakdown(expenses),
            "largest_expenses": self._largest_expenses(expenses, largest_expenses_limit),
            "monthly_revenue": monthly_revenue,
            "monthly_expenses": monthly_expenses,
            "trends": {
                "revenue_change_percent": self._monthly_change(monthly_revenue),
                "expense_change_percent": self._monthly_change(monthly_expenses),
            },
            "recurring_bills": recurring,
            "health": self._health(revenue, expense_total, cash, recurring),
            "signals": sorted(self._signals(monthly_revenue, monthly_expenses, cash, recurring)
                              + self._debt_signals(debt), key=lambda signal: signal["level"] != "caution"),
            "debt": debt,
            "location_estimates": self._location_estimates(revenue_entries, expenses, monthly_revenue, debt, bills, loans),
        }

    def _location_estimates(self, revenue, expenses, months, debt, bills, loans) -> dict[str, Any]:
        """Description-based starting estimates, not Nessie category fields or quotes.

        Unclassified cash expenses go to other; absent categories stay unknown.
        Only explicitly linked debt payments are excluded from expansion costs.
        """
        groups = {name: [] for name in ("rent", "payroll", "utilities", "inventory", "other")}
        linked_scopes = {(f"Debt payment: {raw.get('description')}", raw.get("_source_account_id"))
                         for raw, row in zip(self._records(loans), debt["loans"]) if row["payment_link_verified"]}
        paid_bills = iter(bill for bill in bills if self._status(bill) in ("", "completed"))
        for entry in expenses:
            source_bill = next(paid_bills) if entry["category"] == "Bills" else None
            linked = source_bill is not None and (entry["description"], source_bill.get("_source_account_id")) in linked_scopes
            if not entry["date"] or linked:
                continue
            description = entry["description"].lower()
            category = next((name for name, words in (
                ("rent", ("rent",)), ("payroll", ("payroll", "salary", "wages")),
                ("utilities", ("utilities", "electric", "water bill")),
                ("inventory", ("inventory", "coffee beans", "milk", "dairy", "cups", "packaging", "redemption prizes")),
            ) if any(word in description for word in words)), "other")
            groups[category].append(entry)
        count = len(months)
        return {"basis": "Full dated calendar averages; gaps count as zero. Categories use explicit description keywords, not Nessie category fields. Other includes insurance, software, internet, maintenance and unmatched expenses. Linked existing loan payments are excluded; unlinked payments may remain. These are current-business references, not new-location costs or guaranteed revenue.",
                "months_of_history": count,
                "monthly_revenue": self._number(self._total([entry for entry in revenue if entry["date"]]) / count) if count else None,
                "costs": {name: {"amount": self._number(self._total(entries) / count) if count and entries else None,
                                  "source_descriptions": sorted({row["description"] for row in entries})[:8]}
                          for name, entries in groups.items()}}

    def _debt(self, loans: Records, bills: Sequence[Record], revenue: list[dict[str, Any]],
              expenses: list[dict[str, Any]], cash: Decimal) -> dict[str, Any]:
        """Never infer payment inclusion from matching amounts or lender names.

        An application convention links a bill nickname exactly to
        'Debt payment: <unique loan description>' on the same supplied account.
        Only a matching recurring bill with the stated payment verifies an ongoing
        link. Nessie itself has no loan/bill foreign key. Unlinked payments remain
        visible obligations, but do not get subtracted again from historical flow.
        """
        raw = self._records(loans)
        rows, linked_history = [], defaultdict(lambda: ZERO)
        payments, reported, linked_payments = ZERO, ZERO, ZERO
        complete = loans is not None and len(raw) == len(loans)
        for loan in raw:
            status = self._status(loan)
            active = status == "active"  # Explicit application interpretation, not underwriting.
            inactive = status in ("closed", "paid", "paid off", "cancelled", "canceled")
            description = loan.get("description")
            scope = loan.get("_source_account_id")
            unique = isinstance(description, str) and bool(description.strip()) and sum(
                other.get("description") == description and other.get("_source_account_id") == scope
                for other in raw) == 1
            related = [bill for bill in bills if unique and bill.get("_source_account_id") == scope
                       and bill.get("nickname") == f"Debt payment: {description}"]
            payment = self._loan_amount(loan.get("monthly_payment"))
            amount = self._loan_amount(loan.get("amount"))
            recurring = [bill for bill in related if self._status(bill) == "recurring"]
            linked = active and payment is not None and len(recurring) == 1 and self._loan_amount(recurring[0].get("payment_amount")) == payment
            if active:
                payments += payment or ZERO
                reported += amount or ZERO
                complete = complete and payment is not None and amount is not None
            elif not inactive:
                complete = False
            if linked:
                linked_payments += payment
                for bill in related:
                    paid_date = self._date(bill.get("payment_date"))
                    paid_amount = self._loan_amount(bill.get("payment_amount"))
                    if self._status(bill) in ("", "completed") and paid_date and paid_amount is not None:
                        linked_history[paid_date.strftime("%Y-%m")] += paid_amount
            rows.append({"id": loan.get("_id"), "type": loan.get("type"), "status": status or None,
                         "description": description, "creation_date": loan.get("creation_date"),
                         "reported_loan_amount": self._number(amount) if amount is not None else None,
                         "monthly_payment": self._number(payment) if payment is not None else None,
                         "included_in_obligations": active, "payment_link_verified": linked,
                         "outstanding_balance": None, "apr": None, "remaining_term_months": None})
        months = [row["month"] for row in expenses]
        historical = sum((linked_history[month] for month in months), ZERO) / len(months) if months else ZERO
        avg_expenses = sum((self._amount(row["amount"]) for row in expenses), ZERO) / len(expenses) if expenses else None
        avg_revenue = sum((self._amount(row["amount"]) for row in revenue), ZERO) / len(revenue) if revenue else None
        # Replacement changes only explicitly linked payments, never principal.
        adjustment = linked_payments - historical if months else ZERO
        average_flow = avg_revenue - avg_expenses - adjustment if avg_revenue is not None and avg_expenses is not None else None
        latest_flow = self._amount(revenue[-1]["amount"]) - self._amount(expenses[-1]["amount"]) if revenue and expenses else None
        all_linked = complete and all(row["payment_link_verified"] for row in rows if row["included_in_obligations"])
        coverage = (average_flow + payments) / payments if all_linked and average_flow is not None and payments > 0 else None
        latest_pre_debt = latest_flow + linked_history[months[-1]] if latest_flow is not None and months else None
        latest_coverage = latest_pre_debt / payments if all_linked and latest_pre_debt is not None and payments > 0 else None
        # Listed bills are counted once; only unlinked active payments are added.
        listed = sum((self._amount(bill.get("payment_amount")) for bill in bills
                      if self._status(bill) in ("pending", "recurring")), ZERO)
        obligations = listed + payments - linked_payments
        return {"data_available": loans is not None, "complete": complete, "loans": rows,
                "active_loan_count": sum(row["included_in_obligations"] for row in rows),
                "reported_active_loan_amount": self._number(reported) if complete else None,
                "monthly_payment_total": self._number(payments) if complete else None,
                "all_active_payments_linked": all_linked,
                "linked_monthly_payment": self._number(linked_payments),
                "historical_average_linked_payment": self._number(historical),
                "forecast_expense_adjustment": self._number(adjustment),
                "average_monthly_cash_flow_after_linked_payments": self._number(average_flow) if average_flow is not None else None,
                "latest_monthly_cash_flow": self._number(latest_flow) if latest_flow is not None else None,
                "payment_coverage_ratio": self._number(coverage) if coverage is not None else None,
                "payment_coverage_basis": "Average and latest payment coverage use cash flow BEFORE linked loan payments divided by current monthly LOAN payments only. They do not use cash flow after payments or cover all operating bills. This is cash-flow coverage, not lender DSCR or underwriting.",
                "latest_payment_coverage_ratio": self._number(latest_coverage) if latest_coverage is not None else None,
                "latest_monthly_cash_flow_after_linked_payments": self._number(latest_pre_debt - linked_payments) if latest_pre_debt is not None and all_linked else None,
                "cash_to_monthly_payment_ratio": self._number(max(cash, ZERO) / payments) if complete and payments > 0 else None,
                "conservative_obligation_exposure": self._number(obligations),
                "cash_covers_conservative_obligation_exposure": cash >= obligations,
                "basis": "Active means status 'active'; closed/paid/cancelled loans are excluded, other statuses are unresolved. Totals of known active values may be incomplete. Linked loan payments replace their historical average in projections; unlinked payment inclusion is unknown and historical cash flow is unchanged. Conservative exposure sums bills once plus unlinked active monthly payments; these may overlap with untagged bills and schedules may differ, so this is not a verified total payable.",
                "limitations": "Reported loan amount is not a verified outstanding balance. APR, interest cost, remaining term and amortization are unavailable. Payments stay constant throughout projections as an explicit assumption; no approval or new borrowing is inferred."}

    @staticmethod
    def _loan_amount(value: Any) -> Decimal | None:
        """Unknown or malformed loan figures must not silently become debt-free."""
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            return None
        try:
            amount = Decimal(str(value))
            return amount if amount.is_finite() and amount >= 0 else None
        except InvalidOperation:
            return None

    def _debt_signals(self, debt: dict[str, Any]) -> list[dict[str, Any]]:
        if not debt["data_available"] or not debt["complete"]:
            return [{"id": "debt_data", "level": "neutral", "title": "Debt information is incomplete",
                     "explanation": "Missing loan values or unresolved statuses cannot be treated as zero debt. Payment coverage is unavailable.",
                     "value": None, "unit": "ratio"}]
        if not debt["active_loan_count"]:
            return [{"id": "debt_payments", "level": "neutral", "title": "No active loans reported",
                     "explanation": "The supplied Nessie records contain no active loans; this does not rule out debt outside these accounts.",
                     "value": 0, "unit": "currency"}]
        coverage = debt["payment_coverage_ratio"]
        latest = debt["latest_monthly_cash_flow"]
        caution = coverage is not None and coverage < 1 or latest is not None and latest < 0
        return [{"id": "debt_payments", "level": "caution" if caution else "neutral",
                 "title": "Debt payments compete with cash" if caution else "Existing monthly debt obligation",
                 "explanation": f"Known active loan payments total ${debt['monthly_payment_total']:,.2f}/month. " +
                 (f"Average cash flow before linked debt payments covers them {coverage:.2f} times; after linked payments it is ${debt['average_monthly_cash_flow_after_linked_payments']:,.2f}/month. " if coverage is not None else "Coverage is unavailable without positive payments and dated history. " if debt["all_active_payments_linked"] else "Historical payment inclusion is unverified; no extra payment is deducted from projections. ") +
                 (f"The latest month's realized net cash flow is ${latest:,.2f}. " if latest is not None else "") +
                 "Payment amounts include unknown principal/interest portions; this is cash-flow coverage, not lender underwriting.",
                 "value": coverage, "unit": "ratio"}]

    @staticmethod
    def _records(records: Records) -> list[Record]:
        return [record for record in (records or []) if isinstance(record, Mapping)]

    @staticmethod
    def _amount(value: Any) -> Decimal:
        try:
            amount = Decimal(str(value))
            return amount if amount.is_finite() else ZERO
        except (InvalidOperation, ValueError, TypeError):
            return ZERO

    @staticmethod
    def _number(value: Decimal) -> float:
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _date(value: Any) -> date | None:
        if isinstance(value, date):
            return date(value.year, value.month, value.day)
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                pass
        return None

    @staticmethod
    def _status(record: Record) -> str:
        return str(record.get("status") or "").strip().lower()

    def _transactions(
        self, records: Sequence[Record], amount_field: str, date_field: str, category: str
    ) -> list[dict[str, Any]]:
        entries = []
        for record in records:
            if self._status(record) not in ("", "completed"):
                continue
            entries.append({
                "id": record.get("_id"),
                "description": record.get("description") or record.get("nickname") or record.get("payee") or "",
                "category": category,
                "amount": self._amount(record.get(amount_field)),
                "date": self._date(record.get(date_field)),
            })
        return entries

    @staticmethod
    def _total(entries: Sequence[dict[str, Any]]) -> Decimal:
        return sum((entry["amount"] for entry in entries), ZERO)

    def _cash_balance(self, accounts: Sequence[Record]) -> Decimal:
        return sum((self._amount(account.get("balance")) for account in accounts
                    if account.get("type") in (None, "", "Checking", "Savings")), ZERO)

    def _expense_breakdown(self, expenses: Sequence[dict[str, Any]]) -> dict[str, float]:
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for expense in expenses:
            totals[expense["category"]] += expense["amount"]
        return {category: self._number(amount) for category, amount in sorted(totals.items())}

    def _largest_expenses(self, expenses: Sequence[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        # Stable ties preserve supplied order; credits/refunds are not large expenses.
        ranked = sorted((entry for entry in expenses if entry["amount"] > 0),
                        key=lambda entry: entry["amount"], reverse=True)
        return [{**entry, "amount": self._number(entry["amount"]),
                 "date": entry["date"].isoformat() if entry["date"] else None}
                for entry in ranked[:max(0, limit)]]

    def _monthly_series(
        self, revenue: Sequence[dict[str, Any]], expenses: Sequence[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        grouped = []
        for entries in (revenue, expenses):
            totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
            for entry in entries:
                if entry["date"]:
                    totals[entry["date"].strftime("%Y-%m")] += entry["amount"]
            grouped.append(totals)
        months = sorted(set(grouped[0]) | set(grouped[1]))
        if not months:
            return [], []
        # Fill calendar gaps so a trend compares adjacent months, not distant data points.
        year, month = map(int, months[0].split("-"))
        calendar = []
        while f"{year:04d}-{month:02d}" <= months[-1]:
            calendar.append(f"{year:04d}-{month:02d}")
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        series = [[{"month": month, "amount": self._number(totals.get(month, ZERO))}
                   for month in calendar] for totals in grouped]
        return series[0], series[1]

    def _monthly_change(self, series: Sequence[dict[str, Any]]) -> float | None:
        """Latest supplied calendar month vs previous; growth from zero is undefined."""
        if len(series) < 2:
            return 0.0
        previous = self._amount(series[-2]["amount"])
        current = self._amount(series[-1]["amount"])
        if not previous:
            return 0.0 if not current else None
        return self._number((current - previous) / abs(previous) * 100)

    def _upcoming_bills(self, bills: Sequence[Record], as_of: date | None) -> list[dict[str, Any]]:
        result = []
        for bill in bills:
            status = self._status(bill)
            if status not in ("pending", "recurring"):
                continue
            due = self._date(bill.get("upcoming_payment_date")) or self._date(bill.get("payment_date"))
            if as_of and due and due < as_of and status != "recurring":
                continue
            result.append({
                "id": bill.get("_id"), "payee": bill.get("payee"),
                "nickname": bill.get("nickname"), "status": status,
                "payment_amount": self._number(self._amount(bill.get("payment_amount"))),
                "payment_date": due.isoformat() if due else None,
                "recurring_date": bill.get("recurring_date"),
            })
        return sorted(result, key=lambda bill: (bill["payment_date"] is None, bill["payment_date"] or ""))

    def _health(
        self, revenue: Decimal, expenses: Decimal, cash: Decimal,
        bills: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        """Simple descriptive flags, without industry thresholds or financial advice."""
        obligations = sum((self._amount(bill["payment_amount"]) for bill in bills), ZERO)
        return {
            "has_revenue": revenue > 0,
            "positive_cash_flow": revenue - expenses > 0,
            "expenses_exceed_revenue": expenses > revenue,
            "has_cash_reserve": cash > 0,
            "upcoming_bill_total": self._number(obligations),
            "can_cover_upcoming_bills": cash >= obligations,
            "bill_coverage_ratio": self._number(cash / obligations) if obligations > 0 else None,
        }

    def _signals(self, revenue: Sequence[dict[str, Any]], expenses: Sequence[dict[str, Any]],
                 cash: Decimal, bills: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Explain observed trends and coverage; missing evidence is never a positive signal."""
        signals = []
        changes = {}
        for name, series in (("revenue", revenue), ("expenses", expenses)):
            change = self._monthly_change(series) if len(series) >= 2 else None
            changes[name] = change
            title = f"{name.capitalize()} trend unavailable"
            explanation = "At least two dated calendar months and a nonzero prior baseline are needed for a percentage comparison."
            level = "neutral"
            if change is not None:
                direction = "growing" if change > 0 else "declining" if change < 0 else "stable"
                title = f"{name.capitalize()} is {direction}"
                explanation = f"{series[-1]['month']} vs {series[-2]['month']}: {change:+.2f}%. Calendar gaps count as zero; the latest month may be partial."
                level = "positive" if (name == "revenue" and change > 0) or (name == "expenses" and change < 0) else "caution" if change != 0 else "neutral"
            signals.append({"id": f"{name}_trend", "level": level, "title": title,
                            "explanation": explanation, "value": change, "unit": "percent"})
        rev_change, exp_change = changes["revenue"], changes["expenses"]
        comparable = rev_change is not None and exp_change is not None
        faster = comparable and exp_change > 0 and exp_change > rev_change
        signals.append({"id": "expense_growth", "level": "caution" if faster else "neutral",
                        "title": "Expenses are growing faster than revenue" if faster else "Expense growth comparison" if comparable else "Growth comparison unavailable",
                        "explanation": f"Revenue changed {rev_change:+.2f}% and expenses changed {exp_change:+.2f}% over the same latest two months." if comparable else "Both monthly percentage changes are needed to compare growth.",
                        "value": round(exp_change - rev_change, 2) if comparable else None, "unit": "percentage_points"})
        obligations = sum((self._amount(bill["payment_amount"]) for bill in bills if bill["status"] == "recurring"), ZERO)
        ratio = self._number(obligations / cash * 100) if cash > 0 else None
        signals.append({"id": "recurring_obligations", "level": "caution" if obligations > max(cash, ZERO) else "neutral",
                        "title": "Recurring obligations relative to cash",
                        "explanation": f"Listed recurring bills total ${self._number(obligations):,.2f}; cash is ${self._number(cash):,.2f}. " + (f"That is {ratio:.2f}% of cash." if ratio is not None else "A percentage is unavailable without positive cash.") + " This sums listed bills once, not an inferred payment schedule.",
                        "value": ratio, "unit": "percent"})
        average = sum((self._amount(row["amount"]) for row in expenses), ZERO) / len(expenses) if expenses else ZERO
        coverage = self._number(max(cash, ZERO) / average) if average > 0 else None
        signals.append({"id": "cash_coverage", "level": "caution" if coverage is not None and coverage < 1 else "neutral",
                        "title": "Cash coverage of average expenses",
                        "explanation": f"Average dated monthly expenses are ${self._number(average):,.2f}. " + (f"Cash covers {coverage:.2f} months at that spending level, assuming no new revenue." if coverage is not None else "Coverage is unavailable without positive average dated expenses.") + " This is a coverage measure, not a runway forecast.",
                        "value": coverage, "unit": "months"})
        return sorted(signals, key=lambda signal: signal["level"] != "caution")
