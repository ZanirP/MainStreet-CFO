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
        }

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
