import { Landmark } from "lucide-react";
import type { Analysis } from "../types";
import { currency } from "../format";
import { EmptyState } from "./Shared";

export default function DebtOverview({ analysis }: { analysis: Analysis }) {
  const debt = analysis.debt;
  const money = (value: number | null) =>
    value === null ? "Unavailable" : currency(value);
  return (
    <section className="panel debt-panel" aria-label="Existing debt">
      <div className="panel-heading">
        <div>
          <h2>Existing debt</h2>
          <p>Loan obligations alongside your operating cash flow</p>
        </div>
        <Landmark size={20} className="muted" />
      </div>
      {!debt?.data_available ? (
        <EmptyState title="Debt data unavailable">
          Missing loan information does not mean the business is debt-free.
        </EmptyState>
      ) : (
        <>
          {!debt.complete && (
            <p className="footnote">
              Some amounts or loan statuses are unresolved. Known totals below
              may be incomplete.
            </p>
          )}
          {!debt.loans.length ? (
            <EmptyState title="No loans reported">
              Nessie returned no loans for these accounts. Debt held elsewhere
              is not included.
            </EmptyState>
          ) : (
            <>
              <div className="scenario-metrics">
                <div>
                  <span>Reported active loan amounts</span>
                  <strong>{money(debt.reported_active_loan_amount)}</strong>
                </div>
                <div>
                  <span>Known monthly payments</span>
                  <strong>{money(debt.monthly_payment_total)}</strong>
                </div>
                <div>
                  <span>Cash-flow payment coverage</span>
                  <strong>
                    {debt.payment_coverage_ratio === null
                      ? "Unavailable"
                      : `${debt.payment_coverage_ratio.toFixed(2)}×`}
                  </strong>
                </div>
                <div>
                  <span>Average flow after linked payments</span>
                  <strong>
                    {money(debt.average_monthly_cash_flow_after_linked_payments)}
                  </strong>
                </div>
              </div>
              <div className="transaction-list">
                {debt.loans.map((loan, index) => (
                  <div className="transaction" key={loan.id ?? index}>
                    <span className="transaction-icon">
                      <Landmark size={18} />
                    </span>
                    <div>
                      <h3>{loan.description || "Loan"}</h3>
                      <p>
                        {loan.status || "Status unavailable"} · Reported amount{" "}
                        {money(loan.reported_loan_amount)} ·{" "}
                        {loan.payment_link_verified
                          ? "Payment linked to bills"
                          : "Payment inclusion unverified"}
                      </p>
                    </div>
                    <strong>
                      {money(loan.monthly_payment)}
                      <small> / month</small>
                    </strong>
                  </div>
                ))}
              </div>
              <p className="footnote">
                Coverage compares average cash flow before linked payments with
                monthly loan payments. It is available only when all active
                payments are linked. Reported loan amounts are not verified
                remaining balances; interest cost, APR and payoff terms are
                unavailable.
              </p>
              <p className="footnote">
                {debt.all_active_payments_linked
                  ? "Linked payments are already counted in cash expenses. Projections replace their historical average with the current monthly amount, once."
                  : "Unlinked payments may already be in cash expenses. Their inclusion cannot be verified, so projections do not deduct them again."}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
