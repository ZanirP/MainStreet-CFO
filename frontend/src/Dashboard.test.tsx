// Test-only fixtures. Production always retrieves data from FastAPI.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Dashboard from "./Dashboard";
import type { Analysis, HireResult } from "./types";
vi.mock("./components/Charts", () => ({
  CashFlowChart: () => <div aria-label="Monthly revenue and expenses chart" />,
  ScenarioProjectionChart: ({ result }: { result: HireResult }) => (
    <div>
      {result.cash_projection.map((r) => (
        <div key={r.month}>
          {r.month} baseline {r.baseline} scenario {r.scenario}
        </div>
      ))}
    </div>
  ),
}));
const analysis: Analysis = {
  summary: {
    revenue: 10000,
    expenses: 3000,
    net_cash_flow: 7000,
    cash_balance: 24000,
    margin: 70,
  },
  expense_breakdown: { Purchases: 3000 },
  largest_expenses: [],
  monthly_revenue: [{ month: "2026-10", amount: 10000 }],
  monthly_expenses: [{ month: "2026-10", amount: 3000 }],
  trends: { revenue_change_percent: null, expense_change_percent: 0 },
  recurring_bills: [],
  health: {
    has_revenue: true,
    positive_cash_flow: true,
    expenses_exceed_revenue: false,
    has_cash_reserve: true,
    upcoming_bill_total: 0,
    can_cover_upcoming_bills: true,
    bill_coverage_ratio: null,
  },
};
const scenario: HireResult = {
  scenario: "hire_employee",
  inputs: { hourly_wage: 18, hours_per_week: 30, months: 6 },
  monthly_added_cost: 2340,
  baseline_monthly_cash_flow: 7000,
  projected_monthly_cash_flow: 4660,
  cash_projection: [{ month: "2026-11", baseline: 31000, scenario: 28660 }],
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function setup() {
  fetchMock.mockImplementation(async (url, options) => {
    const path = String(url);
    if (path.endsWith("/businesses"))
      return json([
        { _id: "arbor", first_name: "Arbor Coffee Co." },
        { _id: "arcade", first_name: "Arcade" },
      ]);
    if (options?.method === "POST") return json(scenario);
    return json(
      path.includes("/arcade/")
        ? { ...analysis, summary: { ...analysis.summary, cash_balance: 9000 } }
        : analysis,
    );
  });
}
describe("dashboard vertical slice", () => {
  it("loads analysis, posts edited inputs, displays projections, and clears results on business change", async () => {
    setup();
    const user = userEvent.setup();
    render(<Dashboard />);
    expect(await screen.findByText("$24,000.00")).toBeTruthy();
    await user.clear(screen.getByLabelText("Hourly wage"));
    await user.type(screen.getByLabelText("Hourly wage"), "20");
    await user.click(
      screen.getByRole("button", { name: "See the cash impact" }),
    );
    expect(
      await screen.findByText("2026-11 baseline 31000 scenario 28660"),
    ).toBeTruthy();
    const call = fetchMock.mock.calls.find(
      ([, options]) => options?.method === "POST",
    )!;
    expect(call[0]).toBe(
      "http://localhost:8000/businesses/arbor/scenarios/hire",
    );
    expect(JSON.parse(String(call[1]?.body))).toEqual({
      hourly_wage: 20,
      hours_per_week: 30,
      months: 6,
    });
    expect(call[1]?.headers).toEqual({ "Content-Type": "application/json" });
    await user.selectOptions(
      screen.getByLabelText("Select a business"),
      "arcade",
    );
    expect(await screen.findByText("$9,000.00")).toBeTruthy();
    expect(
      screen.queryByText("2026-11 baseline 31000 scenario 28660"),
    ).toBeNull();
  });
  it("shows empty businesses without fake results", async () => {
    fetchMock.mockResolvedValue(json([]));
    render(<Dashboard />);
    expect(await screen.findByText("Let’s start with a business")).toBeTruthy();
    expect(screen.queryByText("Cash on hand")).toBeNull();
  });
  it("shows network errors and supports retry", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    render(<Dashboard />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("$24,000.00")).toBeTruthy();
  });
  it("disables submission while running and shows backend errors", async () => {
    setup();
    render(<Dashboard />);
    await screen.findByText("$24,000.00");
    let resolve: (response: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "See the cash impact" }),
    );
    expect(
      (screen.getByRole("button", { name: "Simulating…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    resolve(
      json(
        { detail: "Monthly financial history is required to simulate hiring" },
        422,
      ),
    );
    expect(
      await screen.findByText(
        "Monthly financial history is required to simulate hiring",
      ),
    ).toBeTruthy();
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "See the cash impact",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
  });
  it("posts one-time scenarios and reuses projected balances", async () => {
    setup();
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("$24,000.00");
    for (const [kind, route, label] of [
      ["equipment_purchase", "equipment", "Equipment purchase amount"],
      ["owner_withdrawal", "withdrawal", "Withdrawal amount"],
    ]) {
      await user.selectOptions(screen.getByLabelText("Plan a decision"), kind);
      expect(
        screen.queryByText("2026-11 baseline 31000 scenario 26000"),
      ).toBeNull();
      await user.clear(screen.getByLabelText(label));
      await user.type(screen.getByLabelText(label), "5000");
      fetchMock.mockResolvedValueOnce(
        json({
          ...scenario,
          scenario: kind,
          inputs: { amount: 5000, months: 6 },
          one_time_cost: 5000,
          monthly_added_cost: 0,
          projected_monthly_cash_flow: 7000,
          cash_projection: [
            { month: "2026-11", baseline: 31000, scenario: 26000 },
          ],
        }),
      );
      await user.click(
        screen.getByRole("button", { name: "See the cash impact" }),
      );
      expect(
        await screen.findByText("2026-11 baseline 31000 scenario 26000"),
      ).toBeTruthy();
      const call = fetchMock.mock.calls.at(-1)!;
      expect(call[0]).toBe(
        `http://localhost:8000/businesses/arbor/scenarios/${route}`,
      );
      expect(JSON.parse(String(call[1]?.body))).toEqual({
        amount: 5000,
        months: 6,
      });
      expect(screen.getAllByText("One-time cash reduction")[1]).toBeTruthy();
    }
  });
});
