import { test, expect } from "@playwright/test";
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
          cash_projection: Array.from({ length: 6 }, (_, i) => ({
            month: i < 2 ? `2026-${11 + i}` : `2027-0${i - 1}`,
            baseline: 24000 + 7000 * (i + 1),
            scenario: 24000 + 4660 * (i + 1),
          })),
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
    await page.getByLabel("Select a business").selectOption("arcade");
    await expect(
      page.getByText("A little planning. A lot more clarity."),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
}
