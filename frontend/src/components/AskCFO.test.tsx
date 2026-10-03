import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AskCFO from "./AskCFO";
import { api } from "../api";
vi.mock("../api", () => ({ api: { askCFO: vi.fn() } }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const result = {
  answer:
    "Projected cash is $50,400.00, assuming constant historical cash flow.",
  status: "answered" as const,
  context: {},
  facts: [
    {
      id: "f1",
      label: "scenario.cash_projection[5].scenario",
      value: 50400,
      source: "scenario" as const,
    },
  ],
};
it("submits on Enter and displays grounded answer/source", async () => {
  vi.mocked(api.askCFO).mockResolvedValue(result);
  const user = userEvent.setup();
  render(<AskCFO businessId="arbor" />);
  expect(
    (screen.getByRole("button", { name: "Ask CFO" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  await user.type(
    screen.getByLabelText("What would you like to understand?"),
    "What is projected cash?{Enter}",
  );
  expect(await screen.findByText(result.answer)).toBeTruthy();
  expect(api.askCFO).toHaveBeenCalledWith(
    "arbor",
    "What is projected cash?",
    expect.any(AbortSignal),
  );
  expect(screen.getByText("Scenario & assumptions")).toBeTruthy();
});
it("disables submissions in flight and retries sanitized errors", async () => {
  let reject: (error: Error) => void = () => {};
  vi.mocked(api.askCFO).mockImplementationOnce(
    () =>
      new Promise((_, fail) => {
        reject = fail;
      }),
  );
  const user = userEvent.setup();
  render(<AskCFO businessId="arbor" />);
  await user.click(
    screen.getByRole("button", { name: /What is my biggest financial risk/ }),
  );
  expect(
    (screen.getByRole("button", { name: "Reviewing…" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  reject(new Error("Ask Your CFO is temporarily rate limited."));
  expect(await screen.findByRole("alert")).toBeTruthy();
  vi.mocked(api.askCFO).mockResolvedValue(result);
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText(result.answer)).toBeTruthy();
});
it("aborts an outstanding request on business-section unmount", async () => {
  vi.mocked(api.askCFO).mockImplementation(() => new Promise(() => {}));
  const user = userEvent.setup();
  const { unmount } = render(<AskCFO businessId="arbor" />);
  await user.click(screen.getByRole("button", { name: /Can I afford a/ }));
  await waitFor(() => expect(api.askCFO).toHaveBeenCalled());
  const signal = vi.mocked(api.askCFO).mock.calls[0][2]!;
  unmount();
  expect(signal.aborted).toBe(true);
});
