import type { ReactNode } from "react";
import {
  AlertCircle,
  LoaderCircle,
  ArrowUpRight,
  Store,
  ChevronDown,
} from "lucide-react";
import type { Business } from "../types";
export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <Store size={26} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-notice" role="alert">
      <AlertCircle size={19} />
      <span>{message}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
export function Loading({ label }: { label: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="animate-spin" size={22} />
      {label}
    </div>
  );
}
export function MetricCard({
  label,
  value,
  note,
  featured = false,
  negative = false,
}: {
  label: string;
  value: string;
  note: string;
  featured?: boolean;
  negative?: boolean;
}) {
  return (
    <article className={`metric ${featured ? "metric-featured" : ""}`}>
      <div className="metric-label">
        {label}
        <ArrowUpRight size={16} aria-hidden="true" />
      </div>
      <div className={`metric-value ${negative ? "negative" : ""}`}>
        {value}
      </div>
      <p>{note}</p>
    </article>
  );
}
export const businessName = (business: Business) =>
  [business.first_name, business.last_name].filter(Boolean).join(" ") ||
  `Business ${business._id.slice(-6)}`;
export function BusinessSelector({
  businesses,
  selected,
  onChange,
  disabled,
}: {
  businesses: Business[];
  selected: string;
  onChange: (id: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="business-selector">
      <Store size={19} aria-hidden="true" />
      <label className="sr-only" htmlFor="business">
        Select a business
      </label>
      <select
        id="business"
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        {!businesses.length && (
          <option value="">No businesses available</option>
        )}
        {businesses.map((b) => (
          <option key={b._id} value={b._id}>
            {businessName(b)}
          </option>
        ))}
      </select>
      <ChevronDown size={15} aria-hidden="true" />
    </div>
  );
}
