import { useEffect, useState } from "react";
import { ArrowUpRight, CalendarDays, RefreshCw } from "lucide-react";
import { api } from "./api";
import type { Analysis, Business } from "./types";
import { currency, monthLabel, percent } from "./format";
import Sidebar from "./components/Sidebar";
import {
  BusinessSelector,
  businessName,
  EmptyState,
  ErrorNotice,
  Loading,
  MetricCard,
} from "./components/Shared";
import { CashFlowChart } from "./components/Charts";
import {
  ExpenseBreakdown,
  ExpenseList,
  FinancialHealth,
  UpcomingBills,
} from "./components/FinancialDetails";
import ScenarioPanel from "./components/ScenarioPanel";

export default function Dashboard() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [selected, setSelected] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [businessLoading, setBusinessLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [businessError, setBusinessError] = useState("");
  const [error, setError] = useState("");
  const [businessVersion, setBusinessVersion] = useState(0);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setBusinessLoading(true);
    setBusinessError("");
    api
      .businesses(controller.signal)
      .then((list) => {
        if (controller.signal.aborted) return;
        setBusinesses(list);
        setSelected((current) =>
          list.some((b) => b._id === current) ? current : list[0]?._id || "",
        );
      })
      .catch((e) => {
        if (!controller.signal.aborted) setBusinessError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusinessLoading(false);
      });
    return () => controller.abort();
  }, [businessVersion]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setLoading(true);
    setAnalysis(null);
    setError("");
    api
      .analysis(selected, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setAnalysis(data);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [selected, version]);
  function changeBusiness(id: string) {
    setAnalysis(null);
    setError("");
    setSelected(id);
  }
  const business = businesses.find((b) => b._id === selected);
  const months = analysis?.monthly_revenue || [];
  const period = months.length
    ? `${monthLabel(months[0].month)} — ${monthLabel(months[months.length - 1].month)}`
    : "Available history";
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to dashboard
      </a>
      <Sidebar />
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span> <strong>Overview</strong>
          </div>
          <div className="topbar-right">
            <span className="prototype-label">
              <i className="dot green" />
              Local prototype
            </span>
            <span className="avatar header-avatar">MS</span>
          </div>
        </header>
        <main id="main">
          <div className="page-heading" id="overview">
            <div>
              <span className="eyebrow">YOUR BUSINESS, IN BALANCE</span>
              <h1>
                A clearer picture.
                <br className="mobile-break" /> A confident next step.
              </h1>
              <p>Your finances and your next decision, all in one place.</p>
            </div>
            <BusinessSelector
              businesses={businesses}
              selected={selected}
              onChange={changeBusiness}
              disabled={businessLoading || !businesses.length}
            />
          </div>
          {businessLoading ? (
            <Loading label="Finding your businesses…" />
          ) : businessError ? (
            <ErrorNotice
              message={businessError}
              retry={() => setBusinessVersion((v) => v + 1)}
            />
          ) : !businesses.length ? (
            <section className="panel">
              <EmptyState title="Let’s start with a business">
                No customers are available yet. Add a business through your
                backend data setup, then refresh.
              </EmptyState>
              <button
                className="secondary-button empty-refresh"
                onClick={() => setBusinessVersion((v) => v + 1)}
              >
                <RefreshCw size={16} />
                Refresh businesses
              </button>
            </section>
          ) : (
            <>
              <div className="overview-heading">
                <h2>
                  {business ? businessName(business) : "Business"}{" "}
                  <span>Financial overview</span>
                </h2>
                <div className="period">
                  <CalendarDays size={15} />
                  {period}
                  <button
                    aria-label="Refresh analysis"
                    className="icon-button"
                    disabled={loading}
                    onClick={() => {
                      setAnalysis(null);
                      setVersion((v) => v + 1);
                    }}
                  >
                    <RefreshCw
                      size={15}
                      className={loading ? "animate-spin" : ""}
                    />
                  </button>
                </div>
              </div>
              {loading || (!analysis && !error) ? (
                <div className="dashboard-loading">
                  <Loading label="Bringing your finances into focus…" />
                  <div className="skeleton-grid" aria-hidden="true">
                    {[0, 1, 2, 3, 4].map((i) => (
                      <div key={i} className="skeleton" />
                    ))}
                  </div>
                </div>
              ) : error ? (
                <ErrorNotice
                  message={error}
                  retry={() => setVersion((v) => v + 1)}
                />
              ) : (
                analysis && (
                  <>
                    <div className="metrics-grid">
                      <MetricCard
                        label="Cash on hand"
                        value={currency(analysis.summary.cash_balance)}
                        note="Across cash accounts"
                        featured
                      />
                      <MetricCard
                        label="Revenue"
                        value={currency(analysis.summary.revenue)}
                        note="Completed deposits"
                      />
                      <MetricCard
                        label="Expenses"
                        value={currency(analysis.summary.expenses)}
                        note="Purchases & paid bills"
                      />
                      <MetricCard
                        label="Net cash flow"
                        value={currency(analysis.summary.net_cash_flow)}
                        note="Revenue minus expenses"
                        negative={analysis.summary.net_cash_flow < 0}
                      />
                      <MetricCard
                        label="Cash-flow margin"
                        value={percent(analysis.summary.margin)}
                        note="Net cash flow ÷ revenue"
                        negative={analysis.summary.margin < 0}
                      />
                    </div>
                    <p className="overview-note">
                      Totals reflect all available records. Monthly charts use
                      dated transactions.
                    </p>
                    <div className="main-grid">
                      <CashFlowChart analysis={analysis} />
                      <FinancialHealth analysis={analysis} />
                    </div>
                    <div className="details-grid">
                      <ExpenseBreakdown analysis={analysis} />
                      <ExpenseList analysis={analysis} />
                      <UpcomingBills analysis={analysis} />
                    </div>
                    <div className="decision-link">
                      <span>
                        <span className="tiny-spark">✦</span> What’s your next
                        big move?
                      </span>
                      <a href="#what-if">
                        Explore the cash impact of hiring{" "}
                        <ArrowUpRight size={16} />
                      </a>
                    </div>
                    <ScenarioPanel
                      key={`${selected}-${version}`}
                      businessId={selected}
                    />
                  </>
                )
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              MainStreet CFO <span className="footer-dot">·</span> A little
              clarity goes a long way.
            </span>
            <span>Built for small business.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
