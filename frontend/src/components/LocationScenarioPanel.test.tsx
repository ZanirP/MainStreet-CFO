// Contract fixture generated from the deterministic backend and demo raw records.
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { api } from "../api";
import LocationScenarioPanel from "./LocationScenarioPanel";
import AskCFO from "./AskCFO";
import fixture from "../testfixtures/location.json";
import type { Analysis, LocationResult } from "../types";
vi.mock("../api", () => ({ api: { location: vi.fn(), askCFO: vi.fn() } }));
vi.mock("./Charts", () => ({
  ScenarioProjectionChart: () => (
    <div aria-label="Expansion projection chart" />
  ),
}));
const analysis = fixture.analysis as Analysis;
const result = fixture.result as LocationResult;
beforeEach(() => {
  vi.mocked(api.location).mockReset();
  vi.mocked(api.askCFO).mockReset();
});
afterEach(cleanup);

it("prefills only supported history and leaves opening cost for the user", () => {
  render(
    <LocationScenarioPanel
      businessId="arbor"
      analysis={analysis}
      onChangeScenario={vi.fn()}
    />,
  );
  expect(
    (screen.getByLabelText(/Monthly rent/) as HTMLInputElement).value,
  ).toBe("3200");
  expect(
    (
      screen.getByLabelText(
        /Mature additional monthly revenue/,
      ) as HTMLInputElement
    ).value,
  ).toBe("22900");
  expect(
    (screen.getByLabelText(/Opening \/ buildout cost/) as HTMLInputElement)
      .value,
  ).toBe("");
  expect(
    screen.getByText(/starting assumption, not guaranteed new sales/),
  ).toBeTruthy();
});

it("does not turn missing categories into fabricated zero costs", () => {
  render(
    <LocationScenarioPanel businessId="empty" onChangeScenario={vi.fn()} />,
  );
  expect(
    (screen.getByLabelText(/Monthly rent/) as HTMLInputElement).value,
  ).toBe("");
  expect(screen.getAllByText(/No matching historical category/).length).toBe(5);
});

it("submits explicit hypothetical terms, shows limits and clears stale CFO context on editing", async () => {
  vi.mocked(api.location).mockResolvedValue(result);
  const onResult = vi.fn();
  render(
    <LocationScenarioPanel
      businessId="arbor"
      analysis={analysis}
      onChangeScenario={vi.fn()}
      onResult={onResult}
    />,
  );
  for (const [name, value] of Object.entries(result.inputs)) {
    const element = document.getElementById(`location-${name}`);
    if (element)
      fireEvent.change(element, { target: { value: String(value) } });
  }
  fireEvent.click(
    screen.getByRole("checkbox", { name: "Use hypothetical financing" }),
  );
  for (const name of [
    "financing_amount",
    "annual_interest_percent",
    "financing_term_months",
  ] as const) {
    fireEvent.change(document.getElementById(`location-${name}`)!, {
      target: { value: String(result.inputs[name]) },
    });
  }
  fireEvent.click(
    screen.getByRole("button", { name: "Project another location" }),
  );
  await waitFor(() =>
    expect(api.location).toHaveBeenCalledWith(
      "arbor",
      result.inputs,
      expect.any(AbortSignal),
    ),
  );
  expect(
    await screen.findByText("Combined mature monthly cash flow"),
  ).toBeTruthy();
  expect(screen.getAllByText(/Cash stays nonnegative/).length).toBeGreaterThan(
    0,
  );
  expect(screen.getByText(/Financing preserves/)).toBeTruthy();
  expect(onResult).toHaveBeenLastCalledWith(result.inputs);
  fireEvent.change(screen.getByLabelText(/Monthly rent/), {
    target: { value: "5000" },
  });
  expect(onResult).toHaveBeenLastCalledWith(undefined);
  expect(screen.queryByText("Combined mature monthly cash flow")).toBeNull();
});

it("keeps errors reviewable and disables the form while requesting a projection", async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(api.location).mockImplementation(
    () =>
      new Promise((_, fail) => {
        reject = fail;
      }),
  );
  render(
    <LocationScenarioPanel
      businessId="arbor"
      analysis={analysis}
      onChangeScenario={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText(/Opening \/ buildout cost/), {
    target: { value: "4000" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Project another location" }),
  );
  expect(
    screen
      .getByRole("button", { name: "Projecting expansion…" })
      .hasAttribute("disabled"),
  ).toBe(true);
  reject(new Error("Unable to retrieve financial data"));
  expect(
    await screen.findByText("Unable to retrieve financial data"),
  ).toBeTruthy();
  expect(
    screen
      .getByRole("button", { name: "Project another location" })
      .hasAttribute("disabled"),
  ).toBe(false);
});

it("sends inputs, not browser-calculated results, to Ask Your CFO", async () => {
  vi.mocked(api.askCFO).mockResolvedValue({
    answer: "Expansion is a projection, not a financing offer.",
    status: "answered",
    facts: [],
    context: {},
  });
  render(<AskCFO businessId="arbor" locationInputs={result.inputs} />);
  fireEvent.click(
    screen.getByRole("button", {
      name: /Can I afford to open another location/,
    }),
  );
  expect(
    await screen.findByText(
      "Expansion is a projection, not a financing offer.",
    ),
  ).toBeTruthy();
  expect(api.askCFO).toHaveBeenCalledWith(
    "arbor",
    "Can I afford to open another location?",
    expect.any(AbortSignal),
    result.inputs,
  );
});
