import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowRight,
  LoaderCircle,
  Sparkles,
  UserRoundPlus,
} from "lucide-react";
import { api } from "../api";
import type {
  HireInputs,
  ScenarioResult,
  ScenarioKind,
  OneTimeInputs,
} from "../types";
import { scenarioLabel } from "../types";
import { currency, monthLabel } from "../format";
import { ErrorNotice } from "./Shared";
import DecisionLimits from "./DecisionLimits";
import { ScenarioProjectionChart } from "./Charts";
export function HireEmployeeForm({
  busy,
  onSubmit,
  onEdit,
}: {
  busy: boolean;
  onSubmit: (inputs: HireInputs) => void;
  onEdit: () => void;
}) {
  const [wage, setWage] = useState("18");
  const [hours, setHours] = useState("30");
  const [months, setMonths] = useState("6");
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    onSubmit({
      hourly_wage: Number(wage),
      hours_per_week: Number(hours),
      months: Number(months),
    });
  }
  return (
    <form onSubmit={submit} className="hire-form">
      <fieldset disabled={busy}>
        <legend className="sr-only">Employee details</legend>
        <label htmlFor="wage">
          Hourly wage
          <div className="input-wrap">
            <span>$</span>
            <input
              id="wage"
              aria-label="Hourly wage"
              type="number"
              min="0"
              step="0.01"
              required
              value={wage}
              onChange={(e) => {
                setWage(e.target.value);
                onEdit();
              }}
            />
            <span>/ hour</span>
          </div>
        </label>
        <label htmlFor="hours">
          Hours per week
          <div className="input-wrap">
            <input
              id="hours"
              aria-label="Hours per week"
              type="number"
              min="0"
              step="0.5"
              required
              value={hours}
              onChange={(e) => {
                setHours(e.target.value);
                onEdit();
              }}
            />
            <span>hours</span>
          </div>
        </label>
        <label htmlFor="months">
          Projection period
          <select
            id="months"
            value={months}
            onChange={(e) => {
              setMonths(e.target.value);
              onEdit();
            }}
          >
            {[1, 3, 6, 12, 24].map((n) => (
              <option key={n} value={n}>
                {n} {n === 1 ? "month" : "months"}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={busy} className="primary-button">
          {busy ? (
            <>
              <LoaderCircle size={17} className="animate-spin" />
              Simulating…
            </>
          ) : (
            <>
              See the cash impact
              <ArrowRight size={17} />
            </>
          )}
        </button>
      </fieldset>
    </form>
  );
}
function OneTimeForm({
  busy,
  kind,
  onSubmit,
  onEdit,
}: {
  busy: boolean;
  kind: ScenarioKind;
  onSubmit: (inputs: OneTimeInputs) => void;
  onEdit: () => void;
}) {
  const [amount, setAmount] = useState("5000");
  const [months, setMonths] = useState("6");
  const label =
    kind === "equipment_purchase"
      ? "Equipment purchase amount"
      : "Withdrawal amount";
  return (
    <form
      className="hire-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ amount: Number(amount), months: Number(months) });
      }}
    >
      <fieldset disabled={busy}>
        <legend className="sr-only">One-time cash reduction</legend>
        <label htmlFor="amount">
          {label}
          <div className="input-wrap">
            <span>$</span>
            <input
              id="amount"
              aria-label={label}
              type="number"
              min="0"
              step="0.01"
              required
              value={amount}
              onChange={(e) => {
                setAmount(e.target.value);
                onEdit();
              }}
            />
          </div>
        </label>
        <label htmlFor="months">
          Projection period
          <select
            id="months"
            value={months}
            onChange={(e) => {
              setMonths(e.target.value);
              onEdit();
            }}
          >
            {[1, 3, 6, 12, 24].map((n) => (
              <option key={n} value={n}>
                {n} {n === 1 ? "month" : "months"}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={busy} className="primary-button">
          {busy ? (
            <>
              <LoaderCircle size={17} className="animate-spin" />
              Simulating…
            </>
          ) : (
            <>
              See the cash impact
              <ArrowRight size={17} />
            </>
          )}
        </button>
      </fieldset>
    </form>
  );
}
export default function ScenarioPanel({ businessId }: { businessId: string }) {
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [kind, setKind] = useState<ScenarioKind>("hire_employee");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stress, setStress] = useState(false);
  const [edited, setEdited] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function simulate(inputs: HireInputs | OneTimeInputs) {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError("");
    setResult(null);
    setEdited(false);
    const requestInputs = stress ? { ...inputs, stress_test: true } : inputs;
    try {
      const next =
        kind === "hire_employee"
          ? await api.hire(
              businessId,
              requestInputs as HireInputs,
              request.signal,
            )
          : await api[
              kind === "equipment_purchase" ? "equipment" : "withdrawal"
            ](businessId, requestInputs as OneTimeInputs, request.signal);
      if (!request.signal.aborted) setResult(next);
    } catch (e) {
      if (!request.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Unable to run this projection.",
        );
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }
  function changeScenario(next: ScenarioKind) {
    controller.current?.abort();
    setBusy(false);
    setResult(null);
    setError("");
    setEdited(false);
    setKind(next);
  }
  const title =
    kind === "hire_employee"
      ? "Hire an Employee"
      : kind === "equipment_purchase"
        ? "Equipment Purchase"
        : "Owner Withdrawal";
  const label = result ? scenarioLabel(result.scenario) : scenarioLabel(kind);
  const last = result?.cash_projection.at(-1);
  return (
    <section className="scenario-panel" id="what-if">
      <div className="scenario-intro">
        <div>
          <span className="eyebrow">
            <Sparkles size={14} /> A CLEARER VIEW OF YOUR NEXT MOVE
          </span>
          <h2>What if you made your next move?</h2>
          <p>Put a number on your next decision before you make it.</p>
        </div>
        <span className="scenario-badge">What if?</span>
      </div>
      <div className="scenario-workspace">
        <div className="scenario-form-panel">
          <label className="scenario-select-label" htmlFor="scenario">
            Plan a decision
          </label>
          <select
            className="scenario-select"
            id="scenario"
            value={kind}
            onChange={(e) => changeScenario(e.target.value as ScenarioKind)}
          >
            <option value="hire_employee">Hire an Employee</option>
            <option value="equipment_purchase">Equipment Purchase</option>
            <option value="owner_withdrawal">Owner Withdrawal</option>
          </select>
          <div className="scenario-choice">
            <span className="hire-icon">
              <UserRoundPlus size={21} />
            </span>
            <div>
              <h3>{title}</h3>
              <p>
                {kind === "hire_employee"
                  ? "Explore the impact of a new team member."
                  : "Explore a one-time reduction in cash."}
              </p>
            </div>
            <span className="small-tag">Selected</span>
          </div>
          {kind === "hire_employee" ? (
            <HireEmployeeForm
              busy={busy}
              onSubmit={simulate}
              onEdit={() => setEdited(true)}
            />
          ) : (
            <OneTimeForm
              key={kind}
              kind={kind}
              busy={busy}
              onSubmit={simulate}
              onEdit={() => setEdited(true)}
            />
          )}
          <label className="stress-option">
            <input
              type="checkbox"
              checked={stress}
              disabled={busy}
              onChange={(e) => {
                setStress(e.target.checked);
                setEdited(true);
              }}
            />
            <span>
              Include a conservative stress test
              <small>10% lower revenue · 10% higher expenses</small>
            </span>
          </label>
          <p className="footnote">
            {kind === "hire_employee"
              ? "Wages only. Taxes, benefits, and potential revenue growth aren’t included."
              : "The amount is deducted once at the start. Ongoing operating cash flow stays unchanged."}
          </p>
        </div>
        <div className="scenario-results" aria-live="polite" aria-busy={busy}>
          {error && <ErrorNotice message={error} />}{" "}
          {!result && !error && (
            <div className="scenario-placeholder">
              <div className="projection-illustration" aria-hidden="true">
                <svg viewBox="0 0 280 120">
                  <path
                    d="M10 100H270M10 65H270M10 30H270"
                    stroke="#e3e9df"
                    strokeDasharray="4 5"
                  />
                  <path
                    d="M12 94L66 78L118 61L172 46L226 27L267 13"
                    fill="none"
                    stroke="#4b8164"
                    strokeWidth="3"
                    strokeDasharray="6 4"
                  />
                  <path
                    d="M12 94L66 86L118 81L172 74L226 65L267 60"
                    fill="none"
                    stroke="#8270b3"
                    strokeWidth="3"
                  />
                </svg>
              </div>
              <h3>
                {busy
                  ? "Mapping your next chapter…"
                  : "A little planning. A lot more clarity."}
              </h3>
              <p>
                {busy
                  ? "Calculating your baseline and scenario projection."
                  : "Enter your scenario details to compare the impact on projected cash."}
              </p>
              {!busy && (
                <span className="small-tag">
                  Illustration · Run a scenario for your figures
                </span>
              )}
            </div>
          )}
          {result && (
            <>
              {edited && (
                <p className="stale-note">
                  Inputs changed. Run the projection again to update these
                  results.
                </p>
              )}
              <div className="scenario-metrics">
                <div>
                  <span>
                    {result.scenario === "hire_employee"
                      ? "Added monthly cost"
                      : "One-time cash reduction"}
                  </span>
                  <strong>
                    {currency(
                      result.scenario === "hire_employee"
                        ? result.monthly_added_cost
                        : result.one_time_cost,
                    )}
                  </strong>
                </div>
                <div>
                  <span>Baseline cash flow</span>
                  <strong>{currency(result.baseline_monthly_cash_flow)}</strong>
                  <small>per month</small>
                </div>
                <div>
                  <span>{label}</span>
                  <strong>
                    {currency(result.projected_monthly_cash_flow)}
                  </strong>
                  <small>per month</small>
                </div>
                <div>
                  <span>
                    {result.scenario === "hire_employee"
                      ? "Monthly difference"
                      : "Cash balance difference"}
                  </span>
                  <strong className="negative">
                    {currency(
                      result.scenario === "hire_employee"
                        ? result.projected_monthly_cash_flow -
                            result.baseline_monthly_cash_flow
                        : -result.one_time_cost,
                    )}
                  </strong>
                </div>
              </div>
              <ScenarioProjectionChart result={result} />
              {result.breaking_point && (
                <DecisionLimits
                  limits={result.breaking_point}
                  kind={result.scenario}
                />
              )}
              {result.stress_test && (
                <section className="stress-result">
                  <h3>Conservative stress case</h3>
                  <p className="footnote">
                    Positive average revenue reduced by{" "}
                    {result.stress_test.assumptions.revenue_reduction_percent}%;
                    positive average expenses increased by{" "}
                    {result.stress_test.assumptions.expense_increase_percent}%.{" "}
                    {result.stress_test.assumptions.basis}
                  </p>
                  <p className="stress-figures">
                    Revenue:{" "}
                    {currency(
                      result.stress_test.assumptions.average_monthly_revenue,
                    )}{" "}
                    →{" "}
                    {currency(
                      result.stress_test.assumptions.stressed_monthly_revenue,
                    )}{" "}
                    / month.
                    <br />
                    Expenses:{" "}
                    {currency(
                      result.stress_test.assumptions.average_monthly_expenses,
                    )}{" "}
                    →{" "}
                    {currency(
                      result.stress_test.assumptions.stressed_monthly_expenses,
                    )}{" "}
                    / month.
                  </p>
                  <p className="stress-figures">
                    Stressed baseline cash flow:{" "}
                    <strong>
                      {currency(result.stress_test.baseline_monthly_cash_flow)}
                    </strong>{" "}
                    / month. With this decision:{" "}
                    <strong>
                      {currency(result.stress_test.projected_monthly_cash_flow)}
                    </strong>{" "}
                    / month.
                  </p>
                  <ScenarioProjectionChart
                    result={{ ...result, ...result.stress_test }}
                    stressCase
                  />
                  {result.stress_test.breaking_point && (
                    <DecisionLimits
                      limits={result.stress_test.breaking_point}
                      kind={result.scenario}
                      stressCase
                    />
                  )}
                </section>
              )}

              {last && (
                <div className="projection-takeaway">
                  By {monthLabel(last.month)}, projected cash{" "}
                  {label.toLowerCase()} is{" "}
                  <strong>{currency(last.scenario)}</strong>, compared with{" "}
                  <strong>{currency(last.baseline)}</strong> at baseline.
                </div>
              )}
              <p className="footnote">
                Projection based on average historical cash flow, starting after
                the latest recorded month. Results aren’t guaranteed and aren’t
                financial advice.
              </p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
