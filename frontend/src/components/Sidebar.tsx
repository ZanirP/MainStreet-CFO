import {
  ChartNoAxesCombined,
  LayoutDashboard,
  ReceiptText,
  HeartPulse,
  Sparkles,
  ArrowUpRight,
} from "lucide-react";
export default function Sidebar() {
  return (
    <aside className="sidebar">
      <a className="brand" href="#overview">
        <span className="brand-mark">
          <ChartNoAxesCombined size={23} />
        </span>
        <span>
          MainStreet<span className="brand-sub">CFO</span>
        </span>
      </a>
      <div className="nav-label">YOUR WORKSPACE</div>
      <nav aria-label="Main navigation">
        <a href="#overview" className="nav-link nav-primary">
          <LayoutDashboard size={18} />
          Overview
        </a>
        <a href="#expenses" className="nav-link">
          <ReceiptText size={18} />
          Expenses
        </a>
        <a href="#health" className="nav-link">
          <HeartPulse size={18} />
          Financial health
        </a>
        <a href="#what-if" className="nav-link">
          <Sparkles size={18} />
          What if?<span className="nav-badge">NEW</span>
        </a>
      </nav>
      <div className="sidebar-note">
        <div className="note-icon">
          <Sparkles size={19} />
        </div>
        <h3>
          Your next move,
          <br />
          with a clearer view.
        </h3>
        <p>See how hiring could change your business’s cash.</p>
        <a href="#what-if">
          Explore a scenario <ArrowUpRight size={16} />
        </a>
      </div>
      <div className="sidebar-footer">
        <div className="avatar">MS</div>
        <div>
          Small business workspace<span>Built for your next chapter</span>
        </div>
      </div>
    </aside>
  );
}
