import type { Analysis, Business, HireInputs, HireResult } from "./types";
const BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        ...options.headers,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new Error(
      "We couldn’t reach the backend. Check that FastAPI is running, then try again.",
    );
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : response.status === 422
          ? "Check your wage, hours, and projection period. Use nonnegative numbers and a whole number of months."
          : "We couldn’t load your financial data. Please try again.";
    throw new Error(message);
  }
  if (data === null)
    throw new Error(
      "The backend returned an empty response. Please try again.",
    );
  return data as T;
}
export const api = {
  businesses: (signal?: AbortSignal) =>
    request<Business[]>("/businesses", { signal }),
  analysis: (id: string, signal?: AbortSignal) =>
    request<Analysis>(`/businesses/${encodeURIComponent(id)}/analysis`, {
      signal,
    }),
  hire: (id: string, inputs: HireInputs, signal?: AbortSignal) =>
    request<HireResult>(
      `/businesses/${encodeURIComponent(id)}/scenarios/hire`,
      { method: "POST", body: JSON.stringify(inputs), signal },
    ),
};
