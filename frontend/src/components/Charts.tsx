import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
} from "recharts";
import type { Analysis, ScenarioResult } from "../types";
import { scenarioLabel } from "../types";
import { currency, compactCurrency, monthLabel } from "../format";
import { EmptyState } from "./Shared";
const tooltipStyle = {
  borderRadius: 12,
  border: "1px solid #e4e8e2",
  fontSize: 12,
  boxShadow: "0 8px 24px #163d3410",
};
const moneyTooltip = (value: unknown) => currency(Number(value));
export function CashFlowChart({ analysis }: { analysis: Analysis }) {
  const rows = new Map<
    string,
    { month: string; revenue: number; expenses: number }
  >();
  analysis.monthly_revenue.forEach((r) =>
    rows.set(r.month, { month: r.month, revenue: r.amount, expenses: 0 }),
  );
  analysis.monthly_expenses.forEach((r) =>
    rows.set(r.month, {
      ...(rows.get(r.month) || { month: r.month, revenue: 0 }),
      expenses: r.amount,
    }),
  );
  const data = [...rows.values()].sort((a, b) =>
    a.month.localeCompare(b.month),
  );
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Money in. Money out.</h2>
          <p>Monthly revenue and expenses</p>
        </div>
        <div className="legend">
          <span>
            <i className="dot green" />
            Revenue
          </span>
          <span>
            <i className="dot amber" />
            Expenses
          </span>
        </div>
      </div>
      {!data.length ? (
        <EmptyState title="Your story starts with a transaction">
          Monthly charts appear when dated financial records are available.
        </EmptyState>
      ) : (
        <>
          <div
            className="chart"
            role="img"
            aria-label="Monthly revenue and expenses chart"
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={data}
                margin={{ left: 0, right: 12, top: 15, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2b7660" stopOpacity={0.16} />
                    <stop offset="100%" stopColor="#2b7660" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#edf0eb" />
                <XAxis
                  dataKey="month"
                  tickFormatter={monthLabel}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 11, fill: "#7b857c" }}
                  minTickGap={25}
                  dy={10}
                />
                <YAxis
                  tickFormatter={compactCurrency}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 11, fill: "#7b857c" }}
                  width={65}
                />
                <Tooltip
                  formatter={moneyTooltip}
                  labelFormatter={(v) => monthLabel(String(v))}
                  contentStyle={tooltipStyle}
                />
                <Area
                  type="monotone"
                  dataKey="revenue"
                  name="Revenue"
                  stroke="#2b7660"
                  fill="url(#revenueFill)"
                  strokeWidth={2.5}
                  dot={data.length === 1}
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="expenses"
                  name="Expenses"
                  stroke="#c19148"
                  fill="transparent"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={data.length === 1}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <details className="chart-data">
            <summary>View monthly figures</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Revenue</th>
                    <th>Expenses</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((r) => (
                    <tr key={r.month}>
                      <td>{monthLabel(r.month)}</td>
                      <td>{currency(r.revenue)}</td>
                      <td>{currency(r.expenses)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
export function ScenarioProjectionChart({
  result,
  stressCase = false,
}: {
  result: ScenarioResult;
  stressCase?: boolean;
}) {
  const label = `${stressCase ? "Stressed · " : ""}${scenarioLabel(result.scenario)}`;
  const baselineLabel = stressCase ? "Stressed baseline" : "Baseline";
  return (
    <>
      <div className="panel-heading projection-heading">
        <div>
          <h3>Your cash, with and without this decision</h3>
          <p>Projected end-of-month cash balance</p>
        </div>
        <div className="legend">
          <span>
            <i className="dot green" />
            {baselineLabel}
          </span>
          <span>
            <i className="dot violet" />
            {label}
          </span>
        </div>
      </div>
      <div
        className="chart projection-chart"
        role="img"
        aria-label={`Projected baseline cash balance compared with ${label.toLowerCase()}`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={result.cash_projection}
            margin={{ left: 0, right: 14, top: 15, bottom: 0 }}
          >
            <CartesianGrid vertical={false} stroke="#edf0eb" />
            <XAxis
              dataKey="month"
              tickFormatter={monthLabel}
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11 }}
              minTickGap={25}
              dy={8}
            />
            <YAxis
              tickFormatter={compactCurrency}
              width={65}
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11 }}
            />
            <Tooltip
              formatter={moneyTooltip}
              labelFormatter={(v) => monthLabel(String(v))}
              contentStyle={tooltipStyle}
            />
            <ReferenceLine y={0} stroke="#a4ada6" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="baseline"
              name={baselineLabel}
              stroke="#2b7660"
              strokeWidth={2.5}
              strokeDasharray="6 4"
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="scenario"
              name={label}
              stroke="#8270b3"
              strokeWidth={3}
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details className="chart-data">
        <summary>View projection figures</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>{baselineLabel}</th>
                <th>{label}</th>
              </tr>
            </thead>
            <tbody>
              {result.cash_projection.map((r) => (
                <tr key={r.month}>
                  <td>{monthLabel(r.month)}</td>
                  <td>{currency(r.baseline)}</td>
                  <td>{currency(r.scenario)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
