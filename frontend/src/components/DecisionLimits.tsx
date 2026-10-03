import { CircleAlert, Scale } from "lucide-react";
import type { BreakingPoint, ScenarioKind } from "../types";
import { currency, monthLabel } from "../format";

export default function DecisionLimits({
  limits,
  kind,
  stressCase = false,
}: {
  limits: BreakingPoint;
  kind: ScenarioKind;
  stressCase?: boolean;
}) {
  const firstNegative = limits.negative_immediately
    ? "Immediately, before monthly cash flow"
    : limits.first_negative_month_index === null
      ? "Not reached under constant cash flow"
      : `${limits.first_negative_month ? monthLabel(limits.first_negative_month) : `Month ${limits.first_negative_month_index}`} (month ${limits.first_negative_month_index}${limits.first_negative_month_index > limits.projection_months ? "; beyond selected horizon" : ""})`;
  const wageLimit =
    limits.maximum_hourly_wage === null ||
    limits.maximum_hourly_wage === undefined
      ? limits.maximum_monthly_employee_cost === null
        ? "No feasible wage"
        : "No ceiling at zero hours"
      : `${currency(limits.maximum_hourly_wage)} / hour`;
  return (
    <section
      className="decision-limits"
      aria-label={stressCase ? "Stress-case breaking point" : "Breaking point"}
    >
      <div className="limits-heading">
        <h3>
          <Scale size={16} />
          {stressCase ? "Stress-case decision limits" : "Breaking Point"}
        </h3>
        <span className="small-tag">Model thresholds</span>
      </div>
      <p className="footnote">{limits.basis}</p>
      <dl className="limits-grid">
        {kind === "hire_employee" ? (
          <>
            <div>
              <dt>Monthly revenue to break even after hiring</dt>
              <dd>{currency(limits.minimum_monthly_revenue ?? 0)}</dd>
            </div>
            <div>
              <dt>Maximum employee cost at break even</dt>
              <dd>
                {limits.maximum_monthly_employee_cost == null
                  ? "Already cash-flow negative"
                  : `${currency(limits.maximum_monthly_employee_cost)} / month`}
              </dd>
            </div>
            <div>
              <dt>Maximum wage at your entered hours</dt>
              <dd>{wageLimit}</dd>
            </div>
          </>
        ) : (
          <>
            <div>
              <dt>
                Maximum{" "}
                {kind === "equipment_purchase" ? "purchase" : "withdrawal"}{" "}
                preserving the buffer throughout the horizon
              </dt>
              <dd>
                {limits.maximum_one_time_amount_preserving_buffer == null
                  ? "Buffer not achievable"
                  : currency(limits.maximum_one_time_amount_preserving_buffer)}
              </dd>
            </div>
            <div>
              <dt>Assumed cash buffer</dt>
              <dd>{currency(limits.cash_buffer_amount ?? 0)}</dd>
            </div>
            <div>
              <dt>Cash immediately after the decision</dt>
              <dd>{currency(limits.cash_after_decision)}</dd>
            </div>
          </>
        )}
        <div>
          <dt>Cash runway at constant net monthly burn</dt>
          <dd>
            {limits.cash_runway_months === null
              ? "No depletion in this model"
              : `≈ ${limits.cash_runway_months} months`}
          </dd>
        </div>
        <div>
          <dt>First negative cash point</dt>
          <dd>{firstNegative}</dd>
        </div>
        <div>
          <dt>Minimum cash through the selected horizon</dt>
          <dd>{currency(limits.minimum_cash_balance_within_horizon)}</dd>
        </div>
      </dl>
      <p
        className={`limits-status ${limits.negative_within_horizon ? "negative" : ""}`}
      >
        <CircleAlert size={15} />
        {limits.negative_within_horizon
          ? "Cash becomes negative within this horizon, including an immediate shortfall."
          : "Cash stays nonnegative through this horizon under the model."}
      </p>
      {kind === "hire_employee" ? (
        <>
          <p className="footnote">{limits.hourly_wage_basis}</p>
          <p className="footnote">
            {limits.can_sustain_employee_cost
              ? "Entered wages preserve nonnegative monthly cash flow."
              : "Entered wages result in negative monthly cash flow, even if cash reserves last through the horizon."}{" "}
            Wage ceilings are rounded down; required revenue is rounded up.
          </p>
        </>
      ) : (
        <>
          <p className="footnote">{limits.cash_buffer_assumption}</p>
          <p className="footnote">
            {limits.buffer_preserved_through_horizon
              ? "This decision preserves the assumed buffer throughout the horizon."
              : "This decision falls below the assumed buffer at the start or within the horizon."}{" "}
            Maximum amounts are rounded down.
          </p>
        </>
      )}
      <p className="footnote">
        {limits.runway_basis} Zero cash is not counted as negative. These are
        decision limits, not financial advice.
      </p>
    </section>
  );
}
