import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowRight,
  LoaderCircle,
  Sparkles,
  UserRoundPlus,
} from "lucide-react";
import { api } from "../api";
import type { HireInputs, HireResult } from "../types";
import { currency, monthLabel } from "../format";
import { ErrorNotice } from "./Shared";
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
export default function ScenarioPanel({ businessId }: { businessId: string }) {
  const [result, setResult] = useState<HireResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [edited, setEdited] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function simulate(inputs: HireInputs) {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError("");
    setResult(null);
    setEdited(false);
    try {
      const next = await api.hire(businessId, inputs, request.signal);
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
  const last = result?.cash_projection.at(-1);
  return (
    <section className="scenario-panel" id="what-if">
      <div className="scenario-intro">
        <div>
          <span className="eyebrow">
            <Sparkles size={14} /> A CLEARER VIEW OF YOUR NEXT MOVE
          </span>
          <h2>What if you grew your team?</h2>
          <p>Put a number on your next decision before you make it.</p>
        </div>
        <span className="scenario-badge">What if?</span>
      </div>
      <div className="scenario-workspace">
        <div className="scenario-form-panel">
          <div className="scenario-choice">
            <span className="hire-icon">
              <UserRoundPlus size={21} />
            </span>
            <div>
              <h3>Hire an Employee</h3>
              <p>Explore the impact of a new team member.</p>
            </div>
            <span className="small-tag">Selected</span>
          </div>
          <HireEmployeeForm
            busy={busy}
            onSubmit={simulate}
            onEdit={() => setEdited(true)}
          />
          <p className="footnote">
            Wages only. Taxes, benefits, and potential revenue growth aren’t
            included.
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
                  ? "Calculating your baseline and hiring projection."
                  : "Enter the employee details to compare your projected cash with and without a new hire."}
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
                  <span>Added monthly cost</span>
                  <strong>{currency(result.monthly_added_cost)}</strong>
                </div>
                <div>
                  <span>Baseline cash flow</span>
                  <strong>{currency(result.baseline_monthly_cash_flow)}</strong>
                  <small>per month</small>
                </div>
                <div>
                  <span>After hiring</span>
                  <strong>
                    {currency(result.projected_monthly_cash_flow)}
                  </strong>
                  <small>per month</small>
                </div>
                <div>
                  <span>Monthly difference</span>
                  <strong className="negative">
                    {currency(
                      result.projected_monthly_cash_flow -
                        result.baseline_monthly_cash_flow,
                    )}
                  </strong>
                </div>
              </div>
              <ScenarioProjectionChart result={result} />
              {last && (
                <div className="projection-takeaway">
                  By {monthLabel(last.month)}, projected cash after hiring is{" "}
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
