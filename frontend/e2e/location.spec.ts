import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const fixture = JSON.parse(readFileSync(new URL("../src/testfixtures/location.json", import.meta.url), "utf8"));
for (const width of [1440, 390]) {
  test(`Arbor expansion, funding comparison and CFO context at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 950 });
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    let projections = 0;
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
      let data: unknown = fixture.analysis;
      if (path === "/businesses")
        data = [{ _id: "arbor", first_name: "Arbor", last_name: "Coffee Co." }];
      if (path.endsWith("/scenarios/location")) {
        projections++;
        expect(request.postDataJSON()).toEqual(fixture.result.inputs);
        data = fixture.result;
      }
      if (path.endsWith("/cfo/ask")) {
        expect(request.postDataJSON()).toEqual({
          question: "What's the biggest risk with this expansion?",
          location_inputs: fixture.result.inputs,
        });
        data = {
          answer:
            "Opening liquidity and the sales ramp matter. These financing terms are hypothetical.",
          status: "answered",
          facts: [],
          context: {},
        };
      }
      await route.fulfill({
        json: data,
        headers: { "Access-Control-Allow-Origin": "*" },
      });
    });
    await page.goto("/");
    await page.getByLabel("Plan a decision").selectOption("open_location");
    await expect(page.getByLabel(/Monthly rent/)).toHaveValue("3200");
    await expect(page.getByLabel(/Opening \/ buildout cost/)).toHaveValue("");
    for (const [name, value] of Object.entries(fixture.result.inputs)) {
      const input = page.locator(`#location-${name}`);
      if (await input.count()) await input.fill(String(value));
    }
    await page
      .getByRole("checkbox", { name: "Use hypothetical financing" })
      .check();
    for (const name of [
      "financing_amount",
      "annual_interest_percent",
      "financing_term_months",
    ] as const)
      await page
        .locator(`#location-${name}`)
        .fill(String(fixture.result.inputs[name]));
    await page
      .getByRole("button", { name: "Project another location" })
      .click();
    await expect(
      page.getByText("Combined mature monthly cash flow"),
    ).toBeVisible();
    await expect(
      page.getByText("Cash-funded expansion", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.locator(".location-workflow .projection-chart .recharts-surface"),
    ).toHaveCount(2);
    await expect(
      page.getByRole("heading", { name: "Expansion decision limits" }).first(),
    ).toBeVisible();
    await page
      .getByRole("button", {
        name: "What's the biggest risk with this expansion?",
      })
      .click();
    await expect(
      page.getByText(
        "Opening liquidity and the sales ramp matter. These financing terms are hypothetical.",
      ),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.getByLabel(/Monthly rent/).fill("4000");
    await expect(page.locator(".cfo-answer")).toHaveCount(0);
    await expect(
      page.locator(".location-workflow .projection-chart"),
    ).toHaveCount(0);
    expect(projections).toBe(1);
    expect(errors).toEqual([]);
  });
}
