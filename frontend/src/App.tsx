import { useEffect, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bolt,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Gauge,
  Leaf,
  LogOut,
  Menu,
  Radio,
  Settings2,
  ShieldCheck,
  Sparkles,
  Waves,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = {
  time: string;
  consumed: number;
  renewable: number;
  emissions: number;
};

type Overview = {
  tenant: string;
  source: "live" | "demo";
  updated_at: string;
  totals: {
    consumed_kwh: number;
    renewable_kwh: number;
    matched_kwh: number;
    emissions_kgco2: number;
  };
  points: Point[];
};

const demoPoints: Point[] = [
  { time: "00:00", consumed: 31, renewable: 13, emissions: 9 },
  { time: "04:00", consumed: 27, renewable: 17, emissions: 5 },
  { time: "08:00", consumed: 58, renewable: 25, emissions: 16 },
  { time: "12:00", consumed: 74, renewable: 61, emissions: 7 },
  { time: "16:00", consumed: 68, renewable: 48, emissions: 10 },
  { time: "20:00", consumed: 51, renewable: 24, emissions: 14 },
  { time: "23:45", consumed: 38, renewable: 15, emissions: 11 },
];

const demoOverview: Overview = {
  tenant: "Northstar Metals",
  source: "demo",
  updated_at: new Date().toISOString(),
  totals: {
    consumed_kwh: 1384,
    renewable_kwh: 824,
    matched_kwh: 716,
    emissions_kgco2: 334,
  },
  points: demoPoints,
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8001";
const TOKEN_KEY = "mrv_access_token";
const TENANT_KEY = "mrv_tenant_id";

function formatNumber(value: number, digits = 0) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

function MetricCard({
  label,
  value,
  unit,
  delta,
  positive = true,
  icon,
  accent,
}: {
  label: string;
  value: string;
  unit: string;
  delta: string;
  positive?: boolean;
  icon: React.ReactNode;
  accent: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-card__top">
        <span className="metric-card__label">{label}</span>
        <span className="metric-card__icon" style={{ color: accent, background: `${accent}16` }}>
          {icon}
        </span>
      </div>
      <div className="metric-card__value">
        {value}<span>{unit}</span>
      </div>
      <div className={`metric-card__delta ${positive ? "is-positive" : "is-negative"}`}>
        {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
        {delta} <span>vs last period</span>
      </div>
    </article>
  );
}

function App() {
  const [overview, setOverview] = useState<Overview>(demoOverview);
  const [token, setToken] = useState(() => window.localStorage.getItem(TOKEN_KEY));
  const [tenantId, setTenantId] = useState(() => window.localStorage.getItem(TENANT_KEY));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [isRegistering, setIsRegistering] = useState(false);
  const [authError, setAuthError] = useState("");
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [range, setRange] = useState("Today");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);

  async function loadOverview(authToken = token, workspaceId = tenantId) {
    if (!authToken) return;
    setIsRefreshing(true);
    try {
      const query = workspaceId ? `?tenant_id=${encodeURIComponent(workspaceId)}` : "";
      const response = await fetch(`${API_URL}/v1/dashboard/overview${query}`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (response.status === 401) {
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(TENANT_KEY);
        setToken(null);
        setTenantId(null);
        setAuthError("Your session expired. Sign in again.");
        return;
      }
      if (!response.ok) throw new Error("No live overview available");
      const data = (await response.json()) as Overview;
      setOverview({ ...data, source: "live" });
    } catch {
      setOverview((current) => ({ ...current, source: "demo", updated_at: new Date().toISOString() }));
    } finally {
      setTimeout(() => setIsRefreshing(false), 400);
    }
  }

  async function submitAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");
    setIsAuthenticating(true);
    try {
      const response = await fetch(
        `${API_URL}/v1/auth/${isRegistering ? "register" : "login"}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            isRegistering
              ? { email, password, tenant_name: tenantName }
              : { email, password },
          ),
        },
      );
      const result = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(result.detail) ? result.detail.join(" ") : result.detail;
        throw new Error(detail ?? "Could not sign in.");
      }

      const accessToken = result.access_token as string;
      let workspaceId = result.tenant?.id as string | undefined;
      if (!workspaceId) {
        const tenantsResponse = await fetch(`${API_URL}/v1/tenants`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!tenantsResponse.ok) throw new Error("Could not load your workspaces.");
        const tenants = (await tenantsResponse.json()) as Array<{ id: string }>;
        workspaceId = tenants[0]?.id;
      }
      if (!workspaceId) throw new Error("Your account has no workspace yet.");

      window.localStorage.setItem(TOKEN_KEY, accessToken);
      window.localStorage.setItem(TENANT_KEY, workspaceId);
      setTenantId(workspaceId);
      setToken(accessToken);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Could not sign in.");
    } finally {
      setIsAuthenticating(false);
    }
  }

  function signOut() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(TENANT_KEY);
    setToken(null);
    setTenantId(null);
    setOverview(demoOverview);
  }

  useEffect(() => {
    if (token) void loadOverview(token, tenantId);
  }, [token, tenantId]);

  if (!token) {
    return (
      <main className="auth-page">
        <form className="auth-card" onSubmit={(event) => void submitAuth(event)}>
          <div className="brand auth-brand">
            <div className="brand__mark"><Leaf size={19} strokeWidth={2.5} /></div>
            <div><strong>mrv</strong><span>command center</span></div>
          </div>
          <p className="eyebrow">Predictive Green Energy Engine</p>
          <h1>{isRegistering ? "Create your workspace" : "Welcome back"}</h1>
          <p className="auth-description">
            {isRegistering
              ? "Start tracking interval energy, renewable matching, and carbon emissions."
              : "Sign in to view your energy and carbon data."}
          </p>
          <label htmlFor="auth-email">Email</label>
          <input
            id="auth-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            autoComplete={isRegistering ? "new-password" : "current-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={isRegistering ? 12 : 1}
            required
          />
          {isRegistering && (
            <>
              <label htmlFor="tenant-name">Workspace name</label>
              <input
                id="tenant-name"
                value={tenantName}
                onChange={(event) => setTenantName(event.target.value)}
                maxLength={255}
                required
              />
            </>
          )}
          {authError && <p className="auth-error" role="alert">{authError}</p>}
          <button className="primary-button auth-submit" type="submit" disabled={isAuthenticating}>
            {isAuthenticating ? "Please wait…" : isRegistering ? "Create account" : "Sign in"}
          </button>
          <button
            className="auth-switch"
            type="button"
            onClick={() => {
              setIsRegistering(!isRegistering);
              setAuthError("");
            }}
          >
            {isRegistering ? "Already have an account? Sign in" : "New here? Create a workspace"}
          </button>
        </form>
      </main>
    );
  }

  const { totals } = overview;
  const renewableShare = totals.consumed_kwh ? (totals.matched_kwh / totals.consumed_kwh) * 100 : 0;
  const lastUpdated = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(
    new Date(overview.updated_at),
  );

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar--open" : ""}`}>
        <div className="brand">
          <div className="brand__mark"><Leaf size={19} strokeWidth={2.5} /></div>
          <div><strong>mrv</strong><span>command center</span></div>
        </div>
        <div className="workspace-switcher">
          <div className="workspace-avatar">NM</div>
          <div><span>Workspace</span><strong>{overview.tenant}</strong></div>
          <ChevronDown size={15} />
        </div>
        <nav className="nav-list" aria-label="Main navigation">
          <p className="nav-list__eyebrow">Monitor</p>
          <a className="nav-item nav-item--active" href="#overview"><Gauge size={17} />Overview</a>
          <a className="nav-item" href="#energy"><Bolt size={17} />Energy flows</a>
          <a className="nav-item" href="#reports"><BarChart3 size={17} />Reports <span className="nav-badge">3</span></a>
          <p className="nav-list__eyebrow">Manage</p>
          <a className="nav-item" href="#meters"><Radio size={17} />Meters <span className="nav-status-dot" /></a>
          <a className="nav-item" href="#compliance"><ShieldCheck size={17} />Compliance</a>
          <a className="nav-item" href="#settings"><Settings2 size={17} />Settings</a>
        </nav>
        <div className="sidebar__bottom">
          <div className="help-card"><CircleHelp size={18} /><div><strong>Need a hand?</strong><span>Talk to your energy analyst</span></div></div>
          <div className="user-row"><div className="user-avatar">JD</div><div><strong>Jordan Davis</strong><span>Administrator</span></div><ChevronDown size={15} /></div>
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileNav(!mobileNav)}><Menu size={20} /></button>
          <div className="breadcrumbs"><span>Workspace</span><span>/</span><strong>Overview</strong></div>
          <div className="topbar__actions"><div className="live-pill"><span className="pulse-dot" />Live monitoring</div><button className="icon-button" aria-label="Notifications"><Bell size={18} /><span className="notification-dot" /></button><button className="icon-button" aria-label="Sign out" onClick={signOut}><LogOut size={18} /></button><div className="topbar-avatar">JD</div></div>
        </header>

        <div className="page-content">
          <section className="page-heading">
            <div><div className="eyebrow"><Activity size={14} /> Operational view</div><h1>Good morning, Jordan</h1><p>Here is the carbon and energy picture across your facility network.</p></div>
            <div className="heading-actions"><button className="date-control"><CalendarDays size={16} />{range}<ChevronDown size={14} /></button><button className="primary-button" onClick={() => void loadOverview()}><Sparkles size={16} />{isRefreshing ? "Refreshing" : "Refresh data"}</button></div>
          </section>

          <div className="notice-bar"><div className="notice-bar__message"><span className="notice-icon"><CheckCircle2 size={16} /></span><span><strong>Temporal matching is on track.</strong> {formatNumber(renewableShare, 1)}% of consumption is matched with renewable energy today.</span></div><span className="notice-bar__updated">Updated {lastUpdated}</span></div>

          <section className="metrics-grid" aria-label="Key metrics">
            <MetricCard label="Energy consumed" value={formatNumber(totals.consumed_kwh)} unit=" kWh" delta="8.4%" icon={<Bolt size={18} />} accent="#e9a23b" />
            <MetricCard label="Renewable matched" value={formatNumber(totals.matched_kwh)} unit=" kWh" delta="12.7%" icon={<Leaf size={18} />} accent="#1ea675" />
            <MetricCard label="Grid emissions" value={formatNumber(totals.emissions_kgco2)} unit=" kgCO₂e" delta="18.2%" positive={false} icon={<Waves size={18} />} accent="#3c91b7" />
            <MetricCard label="Matching coverage" value={formatNumber(renewableShare, 1)} unit="%" delta="4.8%" icon={<ShieldCheck size={18} />} accent="#c46952" />
          </section>

          <section className="dashboard-grid">
            <article className="panel chart-panel" id="energy">
              <div className="panel__header"><div><span className="panel__kicker">Energy intelligence</span><h2>Consumption vs renewable supply</h2></div><div className="chart-legend"><span><i className="legend-dot legend-dot--consumed" />Consumed</span><span><i className="legend-dot legend-dot--renewable" />Renewable</span></div></div>
              <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={overview.points} margin={{ top: 12, right: 8, left: -18, bottom: 0 }}><defs><linearGradient id="consumedFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#d87852" stopOpacity={0.32} /><stop offset="100%" stopColor="#d87852" stopOpacity={0.02} /></linearGradient><linearGradient id="renewableFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2caf80" stopOpacity={0.28} /><stop offset="100%" stopColor="#2caf80" stopOpacity={0.02} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#dbe4df" strokeDasharray="3 3" /><XAxis dataKey="time" tickLine={false} axisLine={false} tick={{ fill: "#82918b", fontSize: 11 }} /><YAxis tickLine={false} axisLine={false} tick={{ fill: "#82918b", fontSize: 11 }} /><Tooltip contentStyle={{ border: "1px solid #dbe4df", borderRadius: 10, boxShadow: "0 8px 24px #163b2c18", fontSize: 12 }} /><Area type="monotone" dataKey="consumed" stroke="#d87852" strokeWidth={2.5} fill="url(#consumedFill)" /><Area type="monotone" dataKey="renewable" stroke="#2caf80" strokeWidth={2.5} fill="url(#renewableFill)" /></AreaChart></ResponsiveContainer></div>
              <div className="chart-footer"><span><span className="foot-dot foot-dot--good" />15-minute interval matching active</span><span>Source: {overview.source === "live" ? "live meter data" : "demo workspace data"}</span></div>
            </article>

            <article className="panel compliance-panel" id="compliance">
              <div className="panel__header"><div><span className="panel__kicker">Regulatory readiness</span><h2>Compliance pulse</h2></div><ShieldCheck size={19} className="panel__header-icon" /></div>
              <div className="readiness-score"><div className="score-ring"><div><strong>86</strong><span>/ 100</span></div></div><div><strong>Strong position</strong><p>Three evidence checks need attention before month end.</p></div></div>
              <div className="check-list"><div className="check-row"><span className="check-row__icon check-row__icon--done"><CheckCircle2 size={15} /></span><div><strong>Energy provenance</strong><span>Verified through 06 Sep</span></div><span className="check-state">Ready</span></div><div className="check-row"><span className="check-row__icon check-row__icon--done"><CheckCircle2 size={15} /></span><div><strong>Temporal matching</strong><span>15-minute granularity</span></div><span className="check-state">Ready</span></div><div className="check-row"><span className="check-row__icon check-row__icon--warn"><span>!</span></span><div><strong>Grid factor evidence</strong><span>Factor expires in 24 days</span></div><span className="check-state check-state--warn">Review</span></div></div>
              <button className="text-button">Open compliance workspace <ArrowUpRight size={15} /></button>
            </article>
          </section>

          <section className="bottom-grid" id="meters">
            <article className="panel meter-panel"><div className="panel__header"><div><span className="panel__kicker">Connected assets</span><h2>Meter network</h2></div><button className="ghost-button">View all <ArrowUpRight size={15} /></button></div><div className="meter-summary"><div><strong>12</strong><span>Active meters</span></div><div><strong>99.4%</strong><span>Data quality</span></div><div><strong>Live</strong><span>Last heartbeat</span></div></div><div className="meter-bars"><span style={{ height: "46%" }} /><span style={{ height: "65%" }} /><span style={{ height: "54%" }} /><span style={{ height: "81%" }} /><span style={{ height: "72%" }} /><span style={{ height: "92%" }} /><span style={{ height: "68%" }} /><span style={{ height: "88%" }} /><span style={{ height: "76%" }} /><span style={{ height: "96%" }} /><span style={{ height: "83%" }} /><span style={{ height: "91%" }} /></div></article>
            <article className="panel activity-panel"><div className="panel__header"><div><span className="panel__kicker">Recent activity</span><h2>Evidence trail</h2></div><button className="icon-button" aria-label="Activity options"><Settings2 size={17} /></button></div><div className="activity-list"><div className="activity-item"><span className="activity-item__icon activity-item__icon--green"><CheckCircle2 size={15} /></span><div><strong>Daily evidence package generated</strong><span>Scope 2 · 06 Sep 2026</span></div><time>09:42</time></div><div className="activity-item"><span className="activity-item__icon activity-item__icon--blue"><Radio size={15} /></span><div><strong>New meter interval received</strong><span>Plant 01 / Main feed</span></div><time>09:38</time></div><div className="activity-item"><span className="activity-item__icon activity-item__icon--orange"><Bell size={15} /></span><div><strong>Grid factor review scheduled</strong><span>Compliance workflow</span></div><time>Yesterday</time></div></div></article>
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
