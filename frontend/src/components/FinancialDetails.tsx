import {
  ArrowDownLeft,
  Check,
  CircleAlert,
  HeartPulse,
  ReceiptText,
} from "lucide-react";
import type { Analysis } from "../types";
import { currency, dateLabel, percent } from "../format";
import { EmptyState } from "./Shared";
export function ExpenseBreakdown({ analysis }: { analysis: Analysis }) {
  const entries = Object.entries(analysis.expense_breakdown);
  const scale = entries.reduce(
    (total, [, amount]) => total + Math.abs(amount),
    0,
  );
  return (
    <section className="panel" id="expenses">
      <div className="panel-heading">
        <div>
          <h2>Where your money goes</h2>
          <p>Expenses by source</p>
        </div>
        <ReceiptText size={20} className="muted" />
      </div>
      {!entries.length ? (
        <EmptyState title="No expenses yet">
          Completed purchases and bills will appear here.
        </EmptyState>
      ) : (
        <div className="breakdown">
          {entries.map(([category, amount], i) => (
            <div key={category}>
              <div className="breakdown-label">
                <span>
                  <i className={`dot ${i % 2 ? "amber" : "green"}`} />
                  {category}
                </span>
                <strong>{currency(amount)}</strong>
              </div>
              <div className="bar-track">
                <div
                  className={i % 2 ? "bar-amber" : "bar-green"}
                  style={{
                    width: `${scale ? (Math.abs(amount) / scale) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          ))}
          <p className="footnote">
            Grouped by source. Credits reduce total expenses.
          </p>
        </div>
      )}
    </section>
  );
}
export function FinancialHealth({ analysis }: { analysis: Analysis }) {
  const h = analysis.health;
  const checks = [
    {
      good: h.positive_cash_flow,
      title: h.positive_cash_flow
        ? "More coming in than going out"
        : h.expenses_exceed_revenue
          ? "Expenses are outpacing revenue"
          : "Cash flow is balanced",
      text: `Net cash flow is ${currency(analysis.summary.net_cash_flow)} across available records.`,
    },
    {
      good: h.has_cash_reserve,
      title: h.has_cash_reserve ? "Cash on hand" : "No positive cash reserve",
      text: `${currency(analysis.summary.cash_balance)} in your cash accounts.`,
    },
    {
      good: h.can_cover_upcoming_bills,
      title: h.can_cover_upcoming_bills
        ? "Listed bills are covered by cash"
        : "Listed bills exceed your cash",
      text: `${currency(h.upcoming_bill_total)} in pending and recurring obligations.`,
    },
  ];
  return (
    <section className="panel health-panel" id="health">
      <div className="panel-heading">
        <div>
          <h2>A pulse on your business</h2>
          <p>Signals from your current financial data</p>
        </div>
        <HeartPulse size={21} className="muted" />
      </div>
      <div className="health-list">
        {checks.map((c) => (
          <div className="health-item" key={c.title}>
            <span className={`health-icon ${c.good ? "good" : "caution"}`}>
              {c.good ? <Check size={16} /> : <CircleAlert size={16} />}
            </span>
            <div>
              <h3>{c.title}</h3>
              <p>{c.text}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="trend-strip">
        <span>Latest monthly change</span>
        <div>
          <span>
            Revenue{" "}
            <strong>{percent(analysis.trends.revenue_change_percent)}</strong>
          </span>
          <span>
            Expenses{" "}
            <strong>{percent(analysis.trends.expense_change_percent)}</strong>
          </span>
        </div>
        <p className="footnote">
          Compared with the prior month. “—” means growth from zero is
          undefined.
        </p>
      </div>
    </section>
  );
}
export function ExpenseList({ analysis }: { analysis: Analysis }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Largest expenses</h2>
          <p>Your biggest individual outflows</p>
        </div>
        <span className="small-tag">
          Top {analysis.largest_expenses.length}
        </span>
      </div>
      {!analysis.largest_expenses.length ? (
        <EmptyState title="Nothing to list yet">
          Positive completed expenses appear here.
        </EmptyState>
      ) : (
        <div className="transaction-list">
          {analysis.largest_expenses.map((e, i) => (
            <div className="transaction" key={`${e.id}-${i}`}>
              <span className="transaction-icon">
                <ArrowDownLeft size={18} />
              </span>
              <div>
                <h3>{e.description || e.category}</h3>
                <p>
                  {e.category} · {dateLabel(e.date)}
                </p>
              </div>
              <strong>{currency(e.amount)}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
export function UpcomingBills({ analysis }: { analysis: Analysis }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>On the horizon</h2>
          <p>Pending and recurring bills</p>
        </div>
        <span className="small-tag">
          {analysis.recurring_bills.length} bills
        </span>
      </div>
      {!analysis.recurring_bills.length ? (
        <EmptyState title="No bills on the horizon">
          Pending and recurring bills will appear here.
        </EmptyState>
      ) : (
        <div className="transaction-list">
          {analysis.recurring_bills.map((b, i) => (
            <div className="transaction" key={`${b.id}-${i}`}>
              <span className="transaction-icon">
                <ReceiptText size={18} />
              </span>
              <div>
                <h3>{b.nickname || b.payee || "Bill"}</h3>
                <p>
                  {dateLabel(b.payment_date)}{" "}
                  <span className="bill-status">
                    {b.status === "recurring" ? "Recurring" : "Pending"}
                  </span>
                </p>
              </div>
              <strong>{currency(b.payment_amount)}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
