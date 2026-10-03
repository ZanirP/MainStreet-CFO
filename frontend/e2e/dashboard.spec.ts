import { test, expect } from "@playwright/test";
import type { BreakingPoint } from "../src/types";
const decisionLimits: BreakingPoint = {
  basis: "Constant historical monthly averages.",
  cash_after_decision: 24000,
  monthly_cash_flow_nonnegative: true,
  cash_runway_months: null,
  runway_basis: "Constant monthly cash flow; no depletion.",
  negative_immediately: false,
  first_negative_month_index: null,
  first_negative_month: null,
  negative_within_horizon: false,
  minimum_cash_balance_within_horizon: 24000,
  projection_months: 6,
};
// Backend-shaped fixtures remain in tests; no production demo-data fallback.
const analysis = {
  summary: {
    revenue: 66000,
    expenses: 24000,
    net_cash_flow: 42000,
    cash_balance: 24000,
    margin: 63.64,
  },
  monthly_revenue: Array.from({ length: 6 }, (_, i) => ({
    month: `2026-${String(i + 5).padStart(2, "0")}`,
    amount: 8000 + i * 1200,
  })),
  monthly_expenses: Array.from({ length: 6 }, (_, i) => ({
    month: `2026-${String(i + 5).padStart(2, "0")}`,
    amount: 3000 + i * 400,
  })),
  expense_breakdown: { Purchases: 18000, Bills: 6000 },
  largest_expenses: [
    {
      id: "p1",
      description: "Coffee & supplies",
      category: "Purchases",
      amount: 1400,
      date: "2026-10-01",
    },
    {
      id: "b1",
      description: "Shop rent",
      category: "Bills",
      amount: 1200,
      date: "2026-10-02",
    },
  ],
  recurring_bills: [
    {
      id: "b2",
      payee: "Property owner",
      nickname: "Monthly rent",
      status: "recurring",
      payment_amount: 1200,
      payment_date: "2026-11-01",
      recurring_date: 1,
    },
  ],
  trends: { revenue_change_percent: 20, expense_change_percent: 5 },
  health: {
    has_revenue: true,
    positive_cash_flow: true,
    expenses_exceed_revenue: false,
    has_cash_reserve: true,
    upcoming_bill_total: 1200,
    can_cover_upcoming_bills: true,
    bill_coverage_ratio: 20,
  },
};
for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 390, height: 844 },
]) {
  test(`dashboard and hire projection at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("http://localhost:8000/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (request.method() === "OPTIONS")
        return route.fulfill({
          status: 200,
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Allow-Methods": "GET,POST",
          },
        });
      let data: unknown = analysis;
      if (path.endsWith("/cfo/ask")) {
        expect(request.postDataJSON()).toEqual({
          question: "How much cash should I have after six months?",
        });
        data = {
          answer:
            "Projected cash is $66,000.00 under constant historical cash flow, not a guarantee.",
          status: "answered",
          context: {},
          facts: [
            {
              id: "f0",
              label: "projection.cash_projection[5].scenario",
              value: 66000,
              source: "projection",
            },
          ],
        };
      }
      if (path === "/businesses")
        data = [
          { _id: "arbor", first_name: "Arbor Coffee Co." },
          { _id: "arcade", first_name: "Arcade" },
        ];
      if (path.endsWith("/scenarios/hire")) {
        expect(request.postDataJSON()).toEqual({
          hourly_wage: 18,
          hours_per_week: 30,
          months: 6,
        });
        data = {
          scenario: "hire_employee",
          inputs: request.postDataJSON(),
          monthly_added_cost: 2340,
          baseline_monthly_cash_flow: 7000,
          projected_monthly_cash_flow: 4660,
          breaking_point: {
            ...decisionLimits,
            minimum_monthly_revenue: 6340,
            maximum_monthly_employee_cost: 7000,
            maximum_hourly_wage: 53.84,
            can_sustain_employee_cost: true,
          },
          cash_projection: Array.from({ length: 6 }, (_, i) => ({
            month: i < 2 ? `2026-${11 + i}` : `2027-0${i - 1}`,
            baseline: 24000 + 7000 * (i + 1),
            scenario: 24000 + 4660 * (i + 1),
          })),
        };
      }
      if (
        path.endsWith("/scenarios/equipment") ||
        path.endsWith("/scenarios/withdrawal")
      ) {
        expect(request.postDataJSON()).toEqual({
          amount: 5000,
          months: 6,
          ...(request.postDataJSON().stress_test ? { stress_test: true } : {}),
        });
        data = {
          scenario: path.endsWith("equipment")
            ? "equipment_purchase"
            : "owner_withdrawal",
          inputs: request.postDataJSON(),
          one_time_cost: 5000,
          monthly_added_cost: 0,
          baseline_monthly_cash_flow: 7000,
          projected_monthly_cash_flow: 7000,
          breaking_point: {
            ...decisionLimits,
            cash_after_decision: 19000,
            minimum_cash_balance_within_horizon: 19000,
            maximum_one_time_amount_preserving_buffer: 20000,
            cash_buffer_amount: 4000,
            cash_buffer_assumption:
              "Assumed buffer: one month of average operating expenses.",
            buffer_preserved_through_horizon: true,
          },
          cash_projection: Array.from({ length: 6 }, (_, i) => ({
            month: i < 2 ? `2026-${11 + i}` : `2027-0${i - 1}`,
            baseline: 24000 + 7000 * (i + 1),
            scenario: 19000 + 7000 * (i + 1),
          })),
        };
      }
      if (request.method() === "POST" && request.postDataJSON().stress_test) {
        data = {
          ...(data as object),
          stress_test: {
            assumptions: {
              revenue_reduction_percent: 10,
              expense_increase_percent: 10,
              basis: "Historical calendar average; scenario costs unchanged.",
              average_monthly_revenue: 11000,
              average_monthly_expenses: 4000,
              stressed_monthly_revenue: 9900,
              stressed_monthly_expenses: 4400,
            },
            baseline_monthly_cash_flow: 5500,
            projected_monthly_cash_flow: 5500,
            breaking_point: {
              ...decisionLimits,
              cash_after_decision: 19000,
              minimum_cash_balance_within_horizon: 19000,
              maximum_one_time_amount_preserving_buffer: 19600,
              cash_buffer_amount: 4400,
              cash_buffer_assumption:
                "Assumed buffer: one month of stressed operating expenses.",
              buffer_preserved_through_horizon: true,
            },
            cash_projection: Array.from({ length: 6 }, (_, i) => ({
              month: i < 2 ? `2026-${11 + i}` : `2027-0${i - 1}`,
              baseline: 24000 + 5500 * (i + 1),
              scenario: 19000 + 5500 * (i + 1),
            })),
          },
        };
      }
      await route.fulfill({
        json: data,
        headers: { "Access-Control-Allow-Origin": "*" },
      });
    });
    await page.goto("/");
    await expect(
      page.locator(".metric-featured").getByText("$24,000.00", { exact: true }),
    ).toBeVisible();
    await expect(page.locator(".recharts-surface").first()).toBeVisible();
    await page.getByRole("button", { name: "See the cash impact" }).click();
    await expect(page.getByText("$2,340.00", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Breaking Point", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("$53.84 / hour", { exact: true }),
    ).toBeVisible();
    await expect(
      page.locator(".projection-chart .recharts-surface"),
    ).toBeVisible();
    await page.locator(".projection-chart").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `/tmp/mainstreet-${viewport.width}.png`,
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    for (const kind of ["equipment_purchase", "owner_withdrawal"]) {
      await page.getByLabel("Plan a decision").selectOption(kind);
      await expect(page.locator(".projection-chart")).toHaveCount(0);
      await page.getByRole("button", { name: "See the cash impact" }).click();
      await expect(
        page
          .locator(".scenario-metrics")
          .getByText("$5,000.00", { exact: true }),
      ).toBeVisible();
      await expect(
        page.locator(".projection-chart .recharts-surface"),
      ).toBeVisible();
      await expect(page.locator(".projection-takeaway")).toContainText(
        "$61,000.00",
      );
      await expect(page.locator(".decision-limits")).toContainText(
        "$20,000.00",
      );
    }
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "See the cash impact" }).click();
    await expect(
      page.getByText("Conservative stress case", { exact: true }),
    ).toBeVisible();
    await expect(
      page.locator(".projection-chart .recharts-surface"),
    ).toHaveCount(2);
    await expect(
      page.getByText("Stressed baseline", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Stress-case decision limits" }),
    ).toBeVisible();
    await expect(page.locator(".decision-limits").last()).toContainText(
      "$19,600.00",
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("button", {
        name: "How much cash should I have after six months?",
      })
      .click();
    await expect(
      page.getByText(
        "Projected cash is $66,000.00 under constant historical cash flow, not a guarantee.",
      ),
    ).toBeVisible();
    await expect(page.locator(".cfo-source-tags")).toContainText("Projection");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.getByLabel("Select a business").selectOption("arcade");
    await expect(page.locator(".cfo-answer")).toHaveCount(0);
    await expect(
      page.getByText("A little planning. A lot more clarity."),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
}
