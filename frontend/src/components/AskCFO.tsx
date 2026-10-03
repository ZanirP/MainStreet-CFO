import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, MessageCircle, Send } from "lucide-react";
import { api } from "../api";
import type { CFOAnswer } from "../types";

const suggestions = [
  "What is my biggest financial risk right now?",
  "Can I afford to hire someone at $20/hour for 30 hours a week?",
  "Can I afford a $10,000 espresso machine?",
  "How much cash should I have after six months?",
];

export default function AskCFO({ businessId }: { businessId: string }) {
  const [question, setQuestion] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [answer, setAnswer] = useState<CFOAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function ask(text: string) {
    if (!text.trim() || loading) return;
    const request = new AbortController();
    controller.current?.abort();
    controller.current = request;
    setQuestion(text);
    setSubmitted(text.trim());
    setAnswer(null);
    setError("");
    setLoading(true);
    try {
      const result = await api.askCFO(businessId, text.trim(), request.signal);
      if (!request.signal.aborted) setAnswer(result);
    } catch (e) {
      if (!request.signal.aborted)
        setError(e instanceof Error ? e.message : "Please try again.");
    } finally {
      if (!request.signal.aborted) setLoading(false);
    }
  }
  const sources = [...new Set(answer?.facts.map((fact) => fact.source) || [])];
  return (
    <section
      className="panel cfo-panel"
      id="ask-cfo"
      aria-labelledby="cfo-title"
    >
      <div className="cfo-heading">
        <div>
          <span className="eyebrow">CLARITY FOR YOUR NEXT MOVE</span>
          <h2 id="cfo-title">
            <MessageCircle size={22} /> Ask Your CFO
          </h2>
          <p>
            Your numbers, explained. Ask about cash, risks, or a decision you’re
            considering.
          </p>
        </div>
        <span className="small-tag">Powered by Gemini</span>
      </div>
      <div className="cfo-suggestions" aria-label="Suggested CFO questions">
        {suggestions.map((text) => (
          <button
            type="button"
            className="secondary-button"
            key={text}
            disabled={loading}
            onClick={() => void ask(text)}
          >
            {text}
            <ArrowUpRight size={14} />
          </button>
        ))}
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
        className="cfo-form"
      >
        <label htmlFor="cfo-question">What would you like to understand?</label>
        <div className="cfo-input-row">
          <input
            id="cfo-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Can my cash support a new hire?"
            maxLength={2000}
            disabled={loading}
            required
          />
          <button
            className="primary-button"
            disabled={loading || !question.trim()}
            type="submit"
          >
            <Send size={16} />
            {loading ? "Reviewing…" : "Ask CFO"}
          </button>
        </div>
      </form>
      <div aria-live="polite" aria-busy={loading}>
        {loading && (
          <p className="cfo-empty">
            Reviewing your financial history and calculating any projections…
          </p>
        )}
        {error && (
          <div role="alert" className="cfo-error">
            <p>{error}</p>
            <button
              className="secondary-button"
              onClick={() => void ask(submitted)}
            >
              Try again
            </button>
          </div>
        )}
        {answer && (
          <div className="cfo-answer">
            <p className="cfo-question-echo">{submitted}</p>
            <div className="cfo-source-tags">
              {sources.map((source) => (
                <span className="small-tag" key={source}>
                  {source === "historical"
                    ? "Historical data"
                    : source === "projection"
                      ? "Projection"
                      : "Scenario & assumptions"}
                </span>
              ))}
            </div>
            <p className="cfo-answer-text">{answer.answer}</p>
            {answer.facts.length > 0 && (
              <details>
                <summary>Numbers behind this answer</summary>
                <ul>
                  {answer.facts.map((fact) => (
                    <li key={fact.id}>
                      <span>
                        {fact.label.replace(/_/g, " ").replace(/\./g, " › ")}
                      </span>
                      <strong>
                        {fact.display ??
                          (typeof fact.value === "number"
                            ? fact.value.toLocaleString("en-US", {
                                maximumFractionDigits: 2,
                              })
                            : fact.value)}
                      </strong>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
        {!answer && !loading && !error && (
          <p className="cfo-empty">
            Start with a question above, or ask in your own words. Include
            amounts and working hours for a decision.
          </p>
        )}
      </div>
      <p className="footnote">
        Answers use your business’s available data. Projections assume
        historical average cash flow; a default period of six months applies
        unless you specify one. Hiring includes wages only. AI explanations can
        be imperfect and are not financial advice.
      </p>
    </section>
  );
}
