import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type {
  Analysis,
  LocationInputs,
  LocationResult,
  LocationCase,
  ScenarioKind,
} from "../types";
import { currency, monthLabel, percent } from "../format";
import { ErrorNotice } from "./Shared";
import { ScenarioProjectionChart } from "./Charts";

export function LocationLimits({ result }: { result: LocationCase }) {
  const limits = result.breaking_point;
  return (
    <section className="decision-limits" aria-label="Expansion decision limits">
      <h3>Expansion decision limits</h3>
      <div className="scenario-metrics">
        <div>
          <span>New location cash-flow break-even / month</span>
          <strong>
            {currency(limits.location_standalone_break_even_revenue)}
          </strong>
        </div>
        <div>
          <span>Additional revenue for combined break-even</span>
          <strong>
            {currency(
              limits.minimum_additional_revenue_for_business_break_even,
            )}
          </strong>
        </div>
        <div>
          <span>Mature revenue downside to monthly break-even</span>
          <strong>{percent(limits.mature_revenue_downside_percent)}</strong>
        </div>
        <div>
          <span>Illustrative combined cash buffer</span>
          <strong>{currency(limits.cash_buffer_amount ?? 0)}</strong>
        </div>
      </div>
      <p>
        {limits.negative_immediately
          ? "Cash becomes negative at opening."
          : limits.negative_within_horizon
            ? `Cash first becomes negative in ${monthLabel(limits.first_negative_month!)}.`
            : "Cash stays nonnegative within this projection horizon."}
      </p>
      <p>
        Lowest cash: {currency(limits.minimum_cash_balance_within_horizon)} at{" "}
        {limits.minimum_cash_month === "opening"
          ? "opening"
          : monthLabel(limits.minimum_cash_month)}
        .{" "}
        {limits.cash_runway_months === null
          ? "No depletion observed within this horizon; this does not mean unlimited runway."
          : `Estimated first depletion: ${limits.cash_runway_months} months after opening, assuming uniform cash flow within each month.`}
      </p>
      <p className="footnote">
        {limits.break_even_basis} Downside tolerance is for mature monthly cash
        flow, not opening/ramp liquidity.
      </p>
      <p className="footnote">
        {limits.cash_buffer_assumption}{" "}
        {limits.buffer_preserved_through_horizon
          ? "This projection preserves the buffer."
          : "This projection does not preserve the buffer."}
      </p>
      <p className="footnote">
        {limits.minimum_mature_revenue_preserving_buffer === null
          ? limits.buffer_revenue_requirement_unavailable_reason
          : `At least ${currency(limits.minimum_mature_revenue_preserving_buffer)} of mature monthly revenue is needed to preserve this buffer throughout the ramp and horizon.`}
      </p>
    </section>
  );
}

export default function LocationScenarioPanel({
  businessId,
  analysis,
  onChangeScenario,
  onResult,
}: {
  businessId: string;
  analysis?: Analysis;
  onChangeScenario: (kind: ScenarioKind) => void;
  onResult?: (inputs: LocationInputs | undefined) => void;
}) {
  const estimates = analysis?.location_estimates;
  const [values, setValues] = useState<Record<string, string>>(() => ({
    upfront_cost: "",
    monthly_revenue: estimates?.monthly_revenue?.toString() ?? "",
    ...Object.fromEntries(
      ["rent", "payroll", "utilities", "inventory", "other"].map((name) => [
        name,
        estimates?.costs[
          name as keyof typeof estimates.costs
        ].amount?.toString() ?? "",
      ]),
    ),
    months: "6",
    ramp_months: "3",
    financing_amount: "",
    annual_interest_percent: "8",
    financing_term_months: "60",
  }));
  const [financed, setFinanced] = useState(false);
  const [stress, setStress] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LocationResult | null>(null);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  function edit(name: string, value: string) {
    setValues((previous) => ({ ...previous, [name]: value }));
    setResult(null);
    setError("");
    onResult?.(undefined);
  }
  const moneyFields = [
    [
      "upfront_cost",
      "Opening / buildout cost",
      "No opening-cost estimate is available from current transactions.",
    ],
    [
      "monthly_revenue",
      "Mature additional monthly revenue",
      estimates?.monthly_revenue !== null &&
      estimates?.monthly_revenue !== undefined
        ? "Prefilled from current-business average sales; a starting assumption, not guaranteed new sales."
        : "Enter your own assumption; dated sales history is unavailable.",
    ],
    ["rent", "Monthly rent", ""],
    ["payroll", "Monthly payroll", ""],
    ["utilities", "Monthly utilities", ""],
    ["inventory", "Monthly inventory / supplies", ""],
    ["other", "Other monthly operating costs", ""],
  ];
  async function simulate(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    setResult(null);
    onResult?.(undefined);
    const abort = new AbortController();
    request.current?.abort();
    request.current = abort;
    const inputs = {
      ...Object.fromEntries(
        moneyFields.map(([name]) => [name, Number(values[name])]),
      ),
      months: Number(values.months),
      ramp_months: Number(values.ramp_months),
      financing_amount: financed ? Number(values.financing_amount) : 0,
      annual_interest_percent: financed
        ? Number(values.annual_interest_percent)
        : 0,
      financing_term_months: financed
        ? Number(values.financing_term_months)
        : 60,
      stress_test: stress,
    } as LocationInputs;
    try {
      const next = await api.location(businessId, inputs, abort.signal);
      if (!abort.signal.aborted) {
        setResult(next);
        onResult?.(inputs);
      }
    } catch (err) {
      if (!abort.signal.aborted)
        setError(
          err instanceof Error ? err.message : "Unable to project expansion.",
        );
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }
  return (
    <section className="scenario-panel location-workflow" id="what-if">
      <div className="scenario-intro">
        <div>
          <span className="eyebrow">PLAN YOUR NEXT CHAPTER</span>
          <h2>Open another location</h2>
          <p>See the cash tradeoff before committing to expansion.</p>
        </div>
        <span className="scenario-badge">What if?</span>
      </div>
      <div className="scenario-workspace">
        <div className="scenario-form-panel">
          <label className="scenario-select-label" htmlFor="scenario">
            Plan a decision
          </label>
          <select
            id="scenario"
            value="open_location"
            onChange={(e) => {
              onResult?.(undefined);
              onChangeScenario(e.target.value as ScenarioKind);
            }}
          >
            <option value="hire_employee">Hire an Employee</option>
            <option value="equipment_purchase">Equipment Purchase</option>
            <option value="owner_withdrawal">Owner Withdrawal</option>
            <option value="open_location">Open Another Location</option>
          </select>
          <details className="location-reference">
            <summary>Where these starting estimates come from</summary>
            <p className="footnote">
              {estimates?.basis ??
                "No category estimates are available. Enter each cost yourself; missing values are not zero."}
            </p>
            {estimates && (
              <p className="footnote">
                {estimates.months_of_history} calendar months of
                current-business history. Explicitly linked existing debt
                payments are excluded from the new-location cost estimates.
              </p>
            )}
            {estimates &&
              Object.entries(estimates.costs).map(([name, source]) => (
                <p className="footnote" key={name}>
                  {name}:{" "}
                  {source.source_descriptions.join(", ") ||
                    "No category evidence"}
                </p>
              ))}
          </details>
          <form onSubmit={simulate} className="hire-form">
            <fieldset disabled={busy}>
              {moneyFields.map(([name, label, note]) => {
                const source =
                  estimates?.costs[name as keyof typeof estimates.costs];
                return (
                  <label key={name} htmlFor={`location-${name}`}>
                    <span>{label}</span>
                    <input
                      id={`location-${name}`}
                      type="number"
                      min="0"
                      max="1000000000000"
                      step="0.01"
                      required
                      value={values[name]}
                      onChange={(e) => edit(name, e.target.value)}
                    />
                    <small className="footnote">
                      {note ||
                        (source?.amount !== null && source?.amount !== undefined
                          ? `Current-business average: ${currency(source.amount)}. Editable new-location assumption. Source descriptions are available above.`
                          : "No matching historical category; enter an assumption (zero only if intentional).")}
                    </small>
                  </label>
                );
              })}
              <div className="form-two-columns">
                <label htmlFor="location-ramp">
                  Months to mature sales
                  <input
                    id="location-ramp"
                    type="number"
                    min="1"
                    max="120"
                    step="1"
                    required
                    value={values.ramp_months}
                    onChange={(e) => edit("ramp_months", e.target.value)}
                  />
                </label>
                <label htmlFor="location-months">
                  Projection months
                  <input
                    id="location-months"
                    type="number"
                    min="1"
                    max="120"
                    step="1"
                    required
                    value={values.months}
                    onChange={(e) => edit("months", e.target.value)}
                  />
                </label>
              </div>
              <p className="footnote">
                Revenue rises linearly: first month is 1 ÷ ramp months of mature
                sales. Full operating costs start immediately. The current
                business keeps its historical average cash flow.
              </p>
              <label className="stress-option">
                <input
                  type="checkbox"
                  checked={financed}
                  onChange={(e) => {
                    setFinanced(e.target.checked);
                    setResult(null);
                    onResult?.(undefined);
                  }}
                />
                <span>Use hypothetical financing</span>
              </label>
              {financed && (
                <div className="location-financing">
                  <p className="footnote">
                    These are your assumed loan terms, not an offer or approval.
                    Financing can cover only the opening cost.
                  </p>
                  {[
                    ["financing_amount", "Hypothetical financed amount"],
                    ["annual_interest_percent", "Assumed annual interest (%)"],
                    ["financing_term_months", "Assumed loan term (months)"],
                  ].map(([name, label]) => (
                    <label key={name} htmlFor={`location-${name}`}>
                      {label}
                      <input
                        id={`location-${name}`}
                        type="number"
                        required
                        min={name === "financing_term_months" ? 1 : 0}
                        max={
                          name === "annual_interest_percent"
                            ? 100
                            : name === "financing_term_months"
                              ? 360
                              : Number(values.upfront_cost)
                        }
                        step={name === "financing_term_months" ? 1 : 0.01}
                        value={values[name]}
                        onChange={(e) => edit(name, e.target.value)}
                      />
                    </label>
                  ))}
                </div>
              )}
              <label className="stress-option">
                <input
                  type="checkbox"
                  checked={stress}
                  onChange={(e) => {
                    setStress(e.target.checked);
                    setResult(null);
                    onResult?.(undefined);
                  }}
                />
                <span>Include weaker-sales stress test</span>
              </label>
              <button className="primary-button" type="submit" disabled={busy}>
                {busy ? "Projecting expansion…" : "Project another location"}
              </button>
            </fieldset>
          </form>
        </div>
        <div className="scenario-results" aria-live="polite" aria-busy={busy}>
          {error && <ErrorNotice message={error} />}
          {!result && !error && (
            <div className="scenario-empty">
              <h3>Growth needs room to breathe</h3>
              <p>
                Adjust the starting assumptions, then compare opening liquidity,
                the sales ramp and the cash-funded alternative. Existing loans
                stay in your current-business baseline; hypothetical financing
                never creates a real loan.
              </p>
            </div>
          )}
          {result && (
            <>
              <div className="scenario-metrics">
                <div>
                  <span>Cash used at opening</span>
                  <strong>{currency(result.cash_funding_amount)}</strong>
                </div>
                <div>
                  <span>New monthly operating costs</span>
                  <strong>
                    {currency(result.incremental_monthly_operating_cost)}
                  </strong>
                </div>
                <div>
                  <span>Hypothetical loan payment</span>
                  <strong>
                    {currency(result.hypothetical_financing.monthly_payment)}
                  </strong>
                </div>
                <div>
                  <span>Combined mature monthly cash flow</span>
                  <strong>
                    {currency(result.projected_monthly_cash_flow)}
                  </strong>
                </div>
              </div>
              <p className="footnote">
                Current-business baseline:{" "}
                {currency(result.baseline_monthly_cash_flow)}/month. Mature flow
                assumes full expected sales and active hypothetical payments;
                early ramp months differ.
              </p>
              <ScenarioProjectionChart result={result} />
              <LocationLimits result={result} />
              {result.inputs.financing_amount > 0 && (
                <div className="projection-takeaway">
                  <p>
                    Financing preserves{" "}
                    {currency(result.inputs.financing_amount)} at opening but
                    adds{" "}
                    {currency(result.hypothetical_financing.monthly_payment)}
                    /month during the entered term. Cash-funded expansion
                    reaches a low of{" "}
                    {currency(
                      result.funding_comparison.cash_funded.breaking_point
                        .minimum_cash_balance_within_horizon,
                    )}
                    ; selected funding reaches{" "}
                    {currency(
                      result.breaking_point.minimum_cash_balance_within_horizon,
                    )}
                    . Assumed total interest over the loan term:{" "}
                    {currency(
                      result.hypothetical_financing
                        .total_interest_over_entered_term,
                    )}
                    . No fees are modeled.
                  </p>
                </div>
              )}
              <details className="chart-data">
                <summary>View the sales ramp and monthly cash flow</summary>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th>Ramp</th>
                        <th>Additional revenue</th>
                        <th>Operating costs</th>
                        <th>Hypothetical payment</th>
                        <th>Combined flow</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.monthly_operations.map((row) => (
                        <tr key={row.month}>
                          <td>{monthLabel(row.month)}</td>
                          <td>{percent(row.ramp_percent)}</td>
                          <td>{currency(row.additional_revenue)}</td>
                          <td>{currency(row.operating_cost)}</td>
                          <td>{currency(row.hypothetical_debt_payment)}</td>
                          <td>{currency(row.combined_cash_flow)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
              {result.stress_test && (
                <section className="stress-result">
                  <h3>Weaker-sales stress case</h3>
                  <p className="footnote">
                    {result.stress_test.assumptions.basis}
                  </p>
                  <ScenarioProjectionChart
                    result={{ ...result, ...result.stress_test }}
                    stressCase
                  />
                  <LocationLimits result={result.stress_test} />
                </section>
              )}
              <p className="footnote">
                {result.assumptions.basis} {result.assumptions.financing}
              </p>
              <a className="secondary-button" href="#ask-cfo">
                Ask the CFO about this expansion ↓
              </a>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
