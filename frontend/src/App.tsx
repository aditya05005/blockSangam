import React, { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

type ValidationIssue = { code: string; message: string; task_ids?: string[]; candidate_ids?: string[]; block_id?: string | null };
type ScheduleEntry = {
  candidate_id: string; task_id: string; department: string; section: string; line: string; task_type: string;
  start_time: string; end_time: string; duration_minutes: number; mandatory: boolean; priority: number; priority_band: string;
  priority_source: string; priority_confidence: number; priority_factors: string[]; priority_model_version: string;
  ml_priority_score: number | null;
  resource_ids: string[]; slot_id: string; latest_finish: string; requires_traffic_block: boolean;
  requires_power_isolation: boolean; requires_snt_disconnection: boolean;
};
type Unscheduled = { task_id: string; department: string; criticality: number; due_date: string; reason_code: string; explanation: string };
type ScheduleResponse = {
  status: string; validation_status: string;
  summary: { tasks_considered: number; tasks_scheduled: number; candidates_generated: number; candidates_selected: number; joint_blocks: number };
  solver: { status: string; message: string; objective_value: number; solve_time_seconds: number; unscheduled_mandatory_task_ids: string[] };
  schedule_entries: ScheduleEntry[]; unscheduled: Unscheduled[];
  blocks: { block_id: string; section: string; line: string; start_time: string; end_time: string; task_ids: string[] }[];
  validation: { errors: ValidationIssue[]; warnings: ValidationIssue[] }; advisory: string;
};
type WorkflowState = {
  health: "checking" | "online" | "offline";
  importStatus?: string;
  snapshotId?: string;
  snapshotCreatedAt?: string;
  sourceHashes?: Record<string, string>;
  planId?: string;
  planStatus?: string;
  planningMode?: "weekly" | "monthly";
  metrics?: Record<string, number>;
  baselineMetrics?: Record<string, number>;
  persistedUnscheduled?: number;
  scenarioCount?: number;
  message?: string;
};
type Role = "COA" | "ENGINEERING" | "SNT" | "TRD";
type Session = { role: Role; username: string; display_name: string };
type FeedbackItem = { feedback_id: number; plan_id: string | null; sender_role: Role; recipient_role: Role; department: Exclude<Role,"COA">; task_id: string | null; message: string; status: "OPEN" | "UNDER_REVIEW" | "CHANGES_REQUESTED" | "RESOLVED"; parent_id: number | null; created_at: string };

const scenarios = [
  { value: "base", label: "Base forecast", hint: "Reference operating plan" },
  { value: "missing_corridor", label: "Missing capacity", hint: "Corridor availability test" },
  { value: "resource_unavailable", label: "Resource outage", hint: "Team availability test" },
  { value: "locked_commitment", label: "Locked commitment", hint: "Protected block conflict" },
  { value: "stressed_goods", label: "Stressed goods", hint: "Higher freight demand" },
  { value: "competing_maintenance", label: "Competing work", hint: "Department conflict test" },
] as const;

type Page = "overview" | "plan" | "blocks" | "exceptions" | "validation" | "whatif" | "engineering" | "snt" | "trd" | "feedback" | "settings";
const pageCopy: Record<Page, { eyebrow: string; title: string; description: string }> = {
  overview: { eyebrow: "Planning workspace", title: "Good morning, Planner.", description: "Coordinate safer maintenance windows across Engineering, S&T and TRD." },
  plan: { eyebrow: "Planning workspace / Plan studio", title: "Plan Studio", description: "Inspect every scheduled work package across the corridor and its assigned window." },
  blocks: { eyebrow: "Planning workspace / Joint blocks", title: "Joint Block Register", description: "Review coordinated possessions and the departmental work combined inside them." },
  exceptions: { eyebrow: "Planning workspace / Exceptions", title: "Exceptions & Explanations", description: "Understand every task the engine could not place and the constraint responsible." },
  validation: { eyebrow: "Planning workspace / Validation", title: "Constraint Validation", description: "Review independent assurance results and solver evidence for the active plan." },
  whatif: { eyebrow: "Planning workspace / What-If Lab", title: "What-If Simulation Lab", description: "Test operational changes through the real CP-SAT pipeline without modifying the base dataset." },
  engineering: { eyebrow: "Department workspace", title: "Engineering Control Desk", description: "Civil and track work packages, possessions, readiness and coordination feedback in one view." },
  snt: { eyebrow: "Department workspace", title: "S&T Control Desk", description: "Signal and telecommunication work, disconnections and coordinated block requirements." },
  trd: { eyebrow: "Department workspace", title: "TRD Control Desk", description: "Traction distribution work, power isolations and block coordination for the active plan." },
  feedback: { eyebrow: "Department workspace / Coordination", title: "Feedback & Change Requests", description: "Send plan changes to COA, review responses and track every coordination decision." },
  settings: { eyebrow: "System / Runtime status", title: "System Status", description: "Verify the local planning engine, data sources, solver capabilities and available scenarios." },
};

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    calendar: <><path d="M6 2v4M18 2v4M3 9h18"/><rect x="3" y="4" width="18" height="17" rx="2"/></>,
    layers: <><path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 17l9 5 9-5"/></>,
    alert: <><path d="M10.3 3.5 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.5a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></>,
    chart: <><path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
    download: <><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></>, play: <path d="m8 5 11 7-11 7V5Z"/>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>, check: <path d="m5 12 4 4L19 6"/>,
    train: <><rect x="5" y="2" width="14" height="16" rx="3"/><path d="M8 22l2-4h4l2 4M8 7h8M8 12h.01M16 12h.01"/></>, chevron: <path d="m9 18 6-6-6-6"/>,
  };
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

const formatTime = (value: string) => new Date(value).toLocaleString([], { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
const shortTime = (value: string) => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const deptClass = (value: string) => value.toLowerCase().replace("&", "");
const formatDuration = (value: string | number) => {
  const minutes = typeof value === "number" ? value : Number.parseInt(value, 10);
  if (!Number.isFinite(minutes)) return value;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `${hours}h${remainder ? ` ${remainder}m` : ""}`;
};

export default function App() {
  const [session, setSession] = useState<Session | null>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("blocksangam-session") || "null");
      if (saved?.role === "BDMS") return { ...saved, role: "COA", username: "coa", display_name: "COA (Control Office Application)" };
      return saved;
    } catch { return null; }
  });
  const [scenario, setScenario] = useState("base");
  const [result, setResult] = useState<ScheduleResponse | null>(null);
  const [selected, setSelected] = useState<ScheduleEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState<"timeline" | "table">("timeline");
  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [planningMode, setPlanningMode] = useState<"weekly" | "monthly">("weekly");
  const [workflow, setWorkflow] = useState<WorkflowState>({ health: "checking" });
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const scenarioPicker = useRef<HTMLDivElement>(null);
  const departmentPlanStarted = useRef(false);
  const [page, setPage] = useState<Page>(() => {
    const hash = window.location.hash.slice(1) as Page;
    return hash in pageCopy ? hash : "overview";
  });

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.slice(1) as Page;
      if (hash in pageCopy) setPage(hash);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => { if (session) loadFeedback(session.role); }, [session]);

  useEffect(() => {
    if (!session || session.role === "COA") return;
    const ownPage = session.role.toLowerCase() as Page;
    if (page !== ownPage && page !== "feedback") { window.location.hash = ownPage; setPage(ownPage); }
  }, [session, page]);

  useEffect(() => {
    if (!session || session.role === "COA") return;
    const resetHorizontalPosition = () => {
      document.documentElement.scrollLeft = 0;
      document.body.scrollLeft = 0;
      window.scrollTo({ left: 0, top: window.scrollY, behavior: "instant" });
    };
    resetHorizontalPosition();
    window.addEventListener("resize", resetHorizontalPosition);
    return () => window.removeEventListener("resize", resetHorizontalPosition);
  }, [session, page]);

  async function loadFeedback(role: Role) {
    const response = await fetch(`/api/feedback?role=${role}`);
    if (response.ok) setFeedback((await response.json()).items ?? []);
  }

  async function sendFeedback(payload: Omit<FeedbackItem, "feedback_id" | "created_at" | "status">) {
    const response = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail?.message ?? body?.detail ?? "Feedback could not be sent.");
    }
    if (session) await loadFeedback(session.role);
  }

  async function updateFeedback(feedbackId: number, status: FeedbackItem["status"]) {
    const response = await fetch(`/api/feedback/${feedbackId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    if (response.ok && session) await loadFeedback(session.role);
  }

  useEffect(() => {
    Promise.all([fetch("/api/health"), fetch("/api/scenarios")]).then(async ([healthResponse, scenarioResponse]) => {
      if (!healthResponse.ok) throw new Error("Backend health check failed");
      const catalog = scenarioResponse.ok ? await scenarioResponse.json() : { scenarios: [] };
      setWorkflow((current) => ({ ...current, health: "online", scenarioCount: catalog.scenarios?.length ?? 0 }));
    }).catch(() => setWorkflow((current) => ({ ...current, health: "offline", message: "The FastAPI service is not reachable." })));
  }, []);

  useEffect(() => {
    const closePicker = (event: MouseEvent) => {
      if (!scenarioPicker.current?.contains(event.target as Node)) setScenarioOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setScenarioOpen(false); };
    document.addEventListener("mousedown", closePicker);
    document.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("mousedown", closePicker); document.removeEventListener("keydown", closeOnEscape); };
  }, []);

  async function generateSchedule() {
    setBusy(true); setError("");
    try {
      const forecast = scenario === "stressed_goods" ? "stressed" : "base";
      const [response, validationResponse] = await Promise.all([
        fetch("/api/schedule", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario, max_solve_time: 10 }) }),
        fetch("/api/imports/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ forecast }) }),
      ]);
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail?.message ?? body.detail ?? "The scheduling request failed.");
      setResult(body); setSelected(body.schedule_entries[0] ?? null);
      const validation = validationResponse.ok ? await validationResponse.json() : null;
      setWorkflow((current) => ({ ...current, importStatus: validation?.status ?? "UNAVAILABLE", planningMode, message: undefined }));
      if (scenario === "base" || scenario === "stressed_goods") await persistPlanningRun(forecast);
      else setWorkflow((current) => ({ ...current, snapshotId: undefined, planId: undefined, metrics: undefined, baselineMetrics: undefined, planStatus: undefined, message: "Constraint stress scenario executed through the stateless CP-SAT pipeline." }));
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The scheduling request failed."); }
    finally { setBusy(false); }
  }

  async function persistPlanningRun(forecast: string) {
    setWorkflowBusy(true);
    try {
      const snapshotResponse = await fetch("/api/snapshots", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ forecast }) });
      const snapshot = await snapshotResponse.json();
      if (!snapshotResponse.ok) throw new Error(snapshot.detail?.message ?? snapshot.detail ?? "Snapshot creation failed.");
      const snapshotRead = await fetch(`/api/snapshots/${snapshot.snapshot_id}`);
      const confirmedSnapshot = snapshotRead.ok ? await snapshotRead.json() : snapshot;
      const planResponse = await fetch("/api/plans/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ snapshot_id: snapshot.snapshot_id, planning_mode: planningMode, max_solve_time: 10 }) });
      const plan = await planResponse.json();
      if (!planResponse.ok) throw new Error(plan.detail ?? "Persisted plan run failed.");
      const [savedPlanResponse, metricsResponse, unscheduledResponse] = await Promise.all([fetch(`/api/plans/${plan.plan_id}`), fetch(`/api/plans/${plan.plan_id}/metrics`), fetch(`/api/plans/${plan.plan_id}/unscheduled`)]);
      const savedPlan = savedPlanResponse.ok ? await savedPlanResponse.json() : plan;
      const metrics = metricsResponse.ok ? await metricsResponse.json() : {};
      const unscheduled = unscheduledResponse.ok ? await unscheduledResponse.json() : { items: [] };
      setWorkflow((current) => ({ ...current, snapshotId: confirmedSnapshot.snapshot_id, snapshotCreatedAt: confirmedSnapshot.created_at, sourceHashes: confirmedSnapshot.source_hashes, planId: savedPlan.plan_id, planStatus: savedPlan.status, planningMode: savedPlan.planning_mode, metrics: metrics.metrics, baselineMetrics: metrics.baseline_metrics, persistedUnscheduled: unscheduled.items?.length ?? 0, message: "Immutable snapshot and persisted CP-SAT plan are ready for review." }));
    } catch (workflowError) {
      setWorkflow((current) => ({ ...current, message: workflowError instanceof Error ? workflowError.message : "The persisted workflow failed." }));
    } finally { setWorkflowBusy(false); }
  }

  async function changePlanStatus(status: string) {
    if (!workflow.planId) return;
    const response = await fetch(`/api/plans/${workflow.planId}/status`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    if (response.ok) setWorkflow((current) => ({ ...current, planStatus: status, message: `Plan moved to ${status.replaceAll("_", " ")}.` }));
  }

  async function replanWithStress() {
    if (!workflow.planId) return;
    setWorkflowBusy(true);
    try {
      const replanResponse = await fetch(`/api/plans/${workflow.planId}/replan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ forecast: "stressed", planning_mode: planningMode, max_solve_time: 10 }) });
      const replanned = await replanResponse.json();
      if (!replanResponse.ok) throw new Error(replanned.detail ?? "Replanning failed.");
      const [scheduleResponse, metricsResponse] = await Promise.all([fetch("/api/schedule", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario: "stressed_goods", max_solve_time: 10 }) }), fetch(`/api/plans/${replanned.plan_id}/metrics`)]);
      const schedule = await scheduleResponse.json(); const metrics = metricsResponse.ok ? await metricsResponse.json() : {};
      if (scheduleResponse.ok) { setResult(schedule); setSelected(schedule.schedule_entries[0] ?? null); setScenario("stressed_goods"); }
      setWorkflow((current) => ({ ...current, planId: replanned.plan_id, snapshotId: replanned.snapshot_id, planStatus: replanned.status, metrics: metrics.metrics, baselineMetrics: metrics.baseline_metrics, message: "A new stressed-forecast plan version was created; the previous plan was not modified." }));
    } catch (replanError) { setWorkflow((current) => ({ ...current, message: replanError instanceof Error ? replanError.message : "Replanning failed." })); }
    finally { setWorkflowBusy(false); }
  }

  async function downloadBackendCsv() {
    if (!workflow.planId) return;
    const response = await fetch(`/api/plans/${workflow.planId}/export?format=csv`);
    if (!response.ok) return;
    const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a"); link.href = url; link.download = `${workflow.planId}.csv`; link.click(); URL.revokeObjectURL(url);
  }

  const departmentResult = (department?: Exclude<Role,"COA">) => {
    if (!result || !department) return result;
    const schedule_entries = result.schedule_entries.filter((entry) => entry.department === department);
    const ids = new Set(schedule_entries.map((entry) => entry.task_id));
    const blocks = result.blocks.filter((block) => block.task_ids.some((id) => ids.has(id))).map((block) => ({ ...block, task_ids: block.task_ids.filter((id) => ids.has(id)) }));
    const unscheduled = result.unscheduled.filter((item) => item.department === department);
    return { ...result, schedule_entries, blocks, unscheduled, summary: { ...result.summary, tasks_considered: schedule_entries.length + unscheduled.length, tasks_scheduled: schedule_entries.length, candidates_selected: schedule_entries.length, joint_blocks: blocks.length } };
  };

  async function createPdf(department?: Exclude<Role,"COA">) {
    const payload = departmentResult(department);
    if (!payload) return null;
    const response = await fetch("/api/reports/plan.pdf", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) { setWorkflow((current) => ({ ...current, message: "PDF export could not be generated." })); return null; }
    return response.blob();
  }

  useEffect(() => {
    if (session?.role === "COA" || workflow.health !== "online" || result || busy || departmentPlanStarted.current) return;
    departmentPlanStarted.current = true;
    void generateSchedule();
  }, [session, workflow.health, result, busy]);

  async function downloadPdf(department?: Exclude<Role,"COA">) {
    if (!result) return;
    const blob = await createPdf(department); if (!blob) return;
    const filename = `${workflow.planId ?? `blocksangam-${scenario}-schedule`}${department ? `-${department.toLowerCase()}` : ""}.pdf`;
    const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
  }

  const timeline = useMemo(() => {
    if (!result?.schedule_entries.length) return null;
    const starts = result.schedule_entries.map((item) => new Date(item.start_time).getTime());
    const ends = result.schedule_entries.map((item) => new Date(item.end_time).getTime());
    return { start: Math.min(...starts), end: Math.max(...ends) };
  }, [result]);
  const scenarioMeta = scenarios.find((item) => item.value === scenario)!;
  const valid = result?.validation_status === "VALID";

  if (!session) return <LoginScreen onLogin={(next) => { localStorage.setItem("blocksangam-session", JSON.stringify(next)); setSession(next); const target = next.role === "COA" ? "overview" : next.role.toLowerCase(); window.location.hash = target; setPage(target as Page); }}/>

  const departmentPage = session.role === "COA" ? (page === "engineering" ? "ENGINEERING" : page === "snt" ? "SNT" : page === "trd" ? "TRD" : null) : session.role;
  const isDepartmentView = Boolean(departmentPage);

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand-mark"><span className="brand-icon brand-logo"><img src="/blocksangam-logo.png" alt="BlockSangam railway logo" /></span><div><strong>BlockSangam</strong><small>Planning console</small></div></div>
      <nav aria-label="Primary navigation">{session.role === "COA" ? <><p className="nav-label">COA (Control Office Application)</p><NavLink page="overview" current={page} icon="grid">COA dashboard</NavLink><NavLink page="plan" current={page} icon="calendar">Plan studio<span>01</span></NavLink><NavLink page="blocks" current={page} icon="layers">Joint blocks</NavLink><NavLink page="exceptions" current={page} icon="alert">Exceptions{result?.unscheduled.length ? <b>{result.unscheduled.length}</b> : null}</NavLink><NavLink page="validation" current={page} icon="chart">Validation</NavLink><NavLink page="whatif" current={page} icon="settings">What-If Lab</NavLink><p className="nav-label secondary-label">System</p><NavLink page="settings" current={page} icon="chart">System status</NavLink></> : <><p className="nav-label">My department</p><NavLink page={session.role.toLowerCase() as Page} current={page} icon={session.role === "ENGINEERING" ? "train" : session.role === "SNT" ? "chart" : "settings"}>{session.role === "ENGINEERING" ? "Engineering" : session.role === "SNT" ? "S&T" : "TRD"}</NavLink><NavLink page="feedback" current={page} icon="alert">Feedback{feedback.filter((item)=>item.status!=="RESOLVED").length ? <b>{feedback.filter((item)=>item.status!=="RESOLVED").length}</b> : null}</NavLink><div className="department-nav-info"><strong>{session.role === "ENGINEERING" ? "Civil & Track" : session.role === "SNT" ? "Signal & Telecommunication" : "Traction Distribution"}</strong><span>Schedule · Blocks · Feedback</span></div></>}</nav>
      <button className="account-card" onClick={() => { localStorage.removeItem("blocksangam-session"); setSession(null); }}><span>{session.role.slice(0,2)}</span><div><strong>{session.display_name}</strong><small>Sign out</small></div></button>
      <div className={`side-status ${workflow.health}`}><span className="live-dot"/><div><strong>{workflow.health === "online" ? "Local engine online" : workflow.health === "offline" ? "Engine unavailable" : "Checking local engine"}</strong></div></div>
    </aside>
    <main className={`workspace page-${page}`} data-page={page}>
      <div className="ambient ambient-one"/><div className="ambient ambient-two"/>
      <header className="page-header"><div><div className="breadcrumbs"><span>{pageCopy[page].eyebrow}</span></div><h1>{pageCopy[page].title}</h1><p>{pageCopy[page].description}</p></div><div className="header-actions"><div className="engine-pill"><span className="live-dot"/>CP-SAT engine ready</div><button className="export-button" onClick={() => downloadPdf(departmentPage || undefined)} disabled={!result}><Icon name="download"/>Export PDF</button></div></header>
      <section className="run-card"><div className="run-intro"><span className="run-icon"><Icon name="layers"/></span><div><p className="section-kicker">Planning run</p><h2>Build a constraint-verified schedule</h2><p>Choose an operating scenario and let the local engine compose compatible maintenance blocks.</p></div></div><div className="run-controls"><div className="scenario-control" ref={scenarioPicker}><span className="control-label">Forecast scenario</span><button className={`scenario-trigger ${scenarioOpen ? "open" : ""}`} type="button" aria-haspopup="listbox" aria-expanded={scenarioOpen} onClick={() => !busy && setScenarioOpen((open) => !open)} disabled={busy}><span className={`scenario-symbol ${scenario}`}><Icon name={scenario === "base" ? "check" : "alert"} size={15}/></span><span className="scenario-trigger-copy"><strong>{scenarioMeta.label}</strong><small>{scenarioMeta.hint}</small></span><span className="select-chevron"><Icon name="chevron" size={16}/></span></button>{scenarioOpen && <div className="scenario-menu" role="listbox" aria-label="Forecast scenario">{scenarios.map((item, index) => <button type="button" role="option" aria-selected={item.value === scenario} className={item.value === scenario ? "selected" : ""} style={{ "--option-index": index } as React.CSSProperties} key={item.value} onClick={() => { setScenario(item.value); setScenarioOpen(false); }}><span className={`scenario-symbol ${item.value}`}><Icon name={item.value === "base" ? "check" : "alert"} size={14}/></span><span><strong>{item.label}</strong><small>{item.hint}</small></span>{item.value === scenario && <i><Icon name="check" size={14}/></i>}</button>)}</div>}</div><button className="run-button" onClick={generateSchedule} disabled={busy}>{busy ? <span className="spinner"/> : <Icon name="play"/>}{busy ? "Optimizing plan…" : "Run optimizer"}</button></div></section>
      {error && <div className="error-banner"><Icon name="alert"/><div><strong>Planning run failed</strong><p>{error}</p></div></div>}
      <div className="planning-mode-strip"><div><span>Planning horizon</span><p>Persist this run as a precise weekly plan or a broad monthly planning envelope.</p></div><div className="mode-toggle"><button className={planningMode === "weekly" ? "active" : ""} onClick={() => setPlanningMode("weekly")}><Icon name="calendar" size={14}/>Weekly</button><button className={planningMode === "monthly" ? "active" : ""} onClick={() => setPlanningMode("monthly")}><Icon name="layers" size={14}/>Monthly</button></div></div>
      {!result && <section className={`welcome-state ${busy ? "is-busy" : ""}`}><div className="route-graphic"><span>Thane</span><i/><span>Kurla</span><i/><span>Chembur</span><i/><span>Mankhurd</span></div><span className="welcome-icon">{busy ? <span className="spinner large"/> : <Icon name="train" size={28}/>}</span><h2>{busy ? "Solving the Mumbai corridor plan" : "Your Mumbai planning board is ready"}</h2><p>{busy ? "Checking capacity, resources, commitments and train movements. This usually takes only a moment." : "Run the base scenario to generate your first coordinated plan. Every selected block is independently checked before it appears here."}</p>{!busy && <button onClick={generateSchedule}><Icon name="play"/>Generate base plan</button>}</section>}
      {result && <>
        <section className="metric-grid"><Metric icon="calendar" label="Tasks scheduled" value={`${result.summary.tasks_scheduled}`} denominator={`/ ${result.summary.tasks_considered}`} note={`${Math.round(result.summary.tasks_scheduled / Math.max(result.summary.tasks_considered, 1) * 100)}% coverage`} color="indigo"/><Metric icon="layers" label="Joint blocks" value={result.summary.joint_blocks} note="Coordinated windows" color="orange"/><Metric icon="chart" label="Candidates" value={result.summary.candidates_generated} note={`${result.summary.candidates_selected} selected`} color="blue"/><Metric icon={valid ? "check" : "alert"} label="Plan assurance" value={valid ? "Verified" : "Review"} note={`${result.validation.errors.length} hard constraint issues`} color={valid ? "green" : "red"}/></section>
        <section className="planning-layout" id="plan"><div className="board card"><div className="card-heading"><div><p className="section-kicker">Proposed work</p><h2>Corridor planning board</h2><p>{result.schedule_entries.length} work packages across {result.blocks.length} coordinated blocks</p></div><div className="segmented"><button className={view === "timeline" ? "active" : ""} onClick={() => setView("timeline")}>Timeline</button><button className={view === "table" ? "active" : ""} onClick={() => setView("table")}>List</button></div></div><div className="legend"><span className="legend-chip"><i className="engineering"/><b>Engineering</b><small>(Civil &amp; Track)</small></span><span className="legend-chip"><i className="snt"/><b>S&amp;T</b><small>(Signal &amp; Telecommunication)</small></span><span className="legend-chip"><i className="trd"/><b>TRD</b><small>(Traction Distribution)</small></span></div>{view === "timeline" && timeline && <Timeline entries={result.schedule_entries} timeline={timeline} selected={selected} onSelect={setSelected}/>} {view === "table" && <ScheduleTable entries={result.schedule_entries} selected={selected} onSelect={setSelected}/>}</div>
          <aside className="inspector card"><div className="inspector-top"><p className="section-kicker">Work package</p>{selected && <span className={`department-tag ${deptClass(selected.department)}`}>{selected.department}</span>}</div>{selected ? <><div className="task-heading"><div><h2>{selected.task_id}</h2><p>{selected.task_type}</p></div><div className={`priority-orb ${selected.priority_band.toLowerCase()}`}><strong>{Math.round(selected.priority * 100)}</strong><small>priority</small></div></div>{selected.mandatory && <div className="mandatory-note"><Icon name="alert" size={15}/><span><strong>Mandatory work</strong>This task must be included in a valid plan.</span></div>}<PriorityEvidence entry={selected}/><dl className="detail-list"><Detail label="Corridor" value={`${selected.section} · ${selected.line}`} icon="train"/><Detail label="Schedule" value={`${formatTime(selected.start_time)} – ${shortTime(selected.end_time)}`} icon="calendar"/><Detail label="Occupation" value={`${selected.duration_minutes} minutes`} icon="clock"/><Detail label="Resource" value={selected.resource_ids.join(", ") || "None assigned"} icon="settings"/><Detail label="Slot reference" value={selected.slot_id} icon="layers"/></dl><div className="requirements"><p>Protection requirements</p><div><Requirement active={selected.requires_traffic_block}>Traffic block</Requirement><Requirement active={selected.requires_power_isolation}>Power isolation</Requirement><Requirement active={selected.requires_snt_disconnection}>S&amp;T disconnect</Requirement></div></div></> : <p className="empty-copy">Select a work package to inspect its assignment.</p>}</aside></section>
        <section className="lower-grid"><div className="card assurance-card" id="validation"><div className="card-heading compact"><div><p className="section-kicker">Independent validator</p><h2>Plan assurance</h2></div><span className={`assurance-badge ${valid ? "verified" : "invalid"}`}><Icon name={valid ? "check" : "alert"}/>{valid ? "Constraint verified" : "Action required"}</span></div>{result.validation.errors.length === 0 ? <div className="assurance-body"><span className="seal"><Icon name="check" size={25}/></span><div><strong>All hard constraints passed</strong><p>The generated plan independently reconciles task windows, train occupancy, locked work and resource capacity.</p></div></div> : <IssueList items={result.validation.errors}/>} {!!result.validation.warnings.length && <IssueList items={result.validation.warnings} warning/>}<div className="solver-strip"><span><small>Solver status</small><strong>{result.solver.status}</strong></span><span><small>Runtime</small><strong>{result.solver.solve_time_seconds.toFixed(3)}s</strong></span><span><small>Objective</small><strong>{result.solver.objective_value.toFixed(3)}</strong></span></div></div>
          <div className="card exceptions-card" id="exceptions"><div className="card-heading compact"><div><p className="section-kicker">Decision transparency</p><h2>Unscheduled work</h2></div><span className="count-badge">{result.unscheduled.length}</span></div>{result.unscheduled.length ? <div className="exception-list">{result.unscheduled.map((item) => <article key={item.task_id}><span className={`exception-dept ${deptClass(item.department)}`}>{item.department.slice(0, 3)}</span><div><div><strong>{item.task_id}</strong><code>{item.reason_code.replaceAll("_", " ")}</code></div><p>{item.explanation}</p></div></article>)}</div> : <div className="all-scheduled"><Icon name="check"/><div><strong>Every task was placed</strong><p>No unscheduled explanations for this run.</p></div></div>}</div></section>
      </>}
      {result && <BackendWorkflowPanel workflow={workflow} busy={workflowBusy} onStatus={changePlanStatus} onReplan={replanWithStress} onCsv={downloadBackendCsv}/>} 
      {result && <ValidationAudit active={page === "validation"} result={result} workflow={workflow}/>} 
      {result && <JointBlocksPage result={result}/>} 
      {!result && session.role === "COA" && page !== "overview" && page !== "settings" && page !== "whatif" && <NoPlan onRun={() => { window.location.hash = "overview"; setPage("overview"); }}/>} 
      <WhatIfLab active={page === "whatif"} onResult={(simulationResult) => { setResult(simulationResult); setSelected(simulationResult.schedule_entries[0] ?? null); }}/>
      <SystemStatusBanner active={page === "settings"} workflow={workflow} planningMode={planningMode}/>
      <ConfigurationPage active={page === "settings"} scenario={scenario}/>
      {session.role === "COA" && page === "overview" && <FeedbackPanel role="COA" entries={result?.schedule_entries ?? []} items={feedback} planId={workflow.planId} onSend={sendFeedback} onStatus={updateFeedback}/>} 
      {departmentPage && page !== "feedback" && <DepartmentDashboard department={departmentPage} result={result} feedback={feedback} planId={workflow.planId} busy={busy} onGenerate={generateSchedule} onSend={sendFeedback} onStatus={updateFeedback} onExport={() => downloadPdf(departmentPage)}/>} 
      {session.role !== "COA" && page === "feedback" && <section className="department-feedback-page"><FeedbackPanel role={session.role} entries={result?.schedule_entries.filter((entry)=>entry.department===session.role) ?? []} items={feedback.filter((item)=>item.department===session.role)} planId={workflow.planId} onSend={sendFeedback} onStatus={updateFeedback}/></section>}
      <footer><span>BlockSangam · local synthetic-data prototype</span><span>Advisory only — not an operational Indian Railways block grant</span></footer>
    </main>
  </div>;
}

function Metric({ icon, label, value, denominator, note, color }: { icon: string; label: string; value: string | number; denominator?: string; note: string; color: string }) { const displayValue = label === "Total occupation" ? formatDuration(value) : value; return <article className="metric-card"><span className={`metric-icon ${color}`}><Icon name={icon}/></span><div><p>{label}</p><strong>{displayValue}<small>{denominator}</small></strong><span>{note}</span></div></article>; }
function NavLink({ page, current, icon, children }: { page: Page; current: Page; icon: string; children: ReactNode }) { return <a className={`nav-item ${current === page ? "active" : ""}`} href={`#${page}`}><Icon name={icon}/>{children}</a>; }

function LoginScreen({ onLogin }: { onLogin: (session: Session) => void }) {
  const [username, setUsername] = useState("coa"); const [password, setPassword] = useState("blocksangam"); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event: React.FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) }); const body = await response.json(); if (!response.ok) throw new Error(body.detail ?? "Login failed"); onLogin(body); } catch (reason) { setError(reason instanceof Error ? reason.message : "Login failed"); } finally { setBusy(false); } }
  const accounts = [{id:"coa",label:"COA",copy:"Control Office Application"},{id:"engineering",label:"Engineering",copy:"Civil & Track"},{id:"snt",label:"S&T",copy:"Signal & Telecommunication"},{id:"trd",label:"TRD",copy:"Traction Distribution"}];
  return <main className="login-shell"><section className="login-story"><div className="login-brand"><img src="/blocksangam-logo.png" alt="BlockSangam"/><span><strong>BlockSangam</strong><small>Unified railway block planning</small></span></div><div><p className="section-kicker">Secure coordination workspace</p><h1>One verified plan.<br/>Four accountable teams.</h1><p>Plan, review and coordinate Mumbai maintenance blocks with department-specific access and a shared feedback trail.</p></div><div className="login-route"><span>COA</span><i/><span>ENG</span><i/><span>S&amp;T</span><i/><span>TRD</span></div></section><section className="login-panel"><form onSubmit={submit}><p className="section-kicker">Welcome back</p><h2>Sign in to your control desk</h2><p>Select your team, then use its account credentials.</p><div className="role-picker">{accounts.map((account)=><button type="button" className={username===account.id?"active":""} onClick={()=>setUsername(account.id)} key={account.id}><strong>{account.label}</strong><small>{account.copy}</small></button>)}</div><label>Username<input value={username} onChange={(event)=>setUsername(event.target.value)} autoComplete="username"/></label><label>Password<input type="password" value={password} onChange={(event)=>setPassword(event.target.value)} autoComplete="current-password"/></label>{error&&<div className="login-error"><Icon name="alert"/>{error}</div>}<button className="login-button" disabled={busy}>{busy?<span className="spinner"/>:<Icon name="chevron"/>}{busy?"Signing in…":"Open dashboard"}</button><small className="demo-note">Demo password: <code>blocksangam</code> · Change per-role passwords with backend environment variables.</small></form></section></main>;
}

function DepartmentDashboard({ department, result, feedback, planId, busy, onGenerate, onSend, onStatus, onExport }: { department: Exclude<Role,"COA">; result: ScheduleResponse | null; feedback: FeedbackItem[]; planId?: string; busy: boolean; onGenerate: ()=>void; onSend: (payload: Omit<FeedbackItem,"feedback_id"|"created_at"|"status">)=>Promise<void>; onStatus: (id:number,status:FeedbackItem["status"])=>Promise<void>; onExport:()=>void }) {
  if (!result) return <section className="department-empty"><span><Icon name="train" size={30}/></span><h2>No active plan is available</h2><p>Generate the coordinated plan to load this department's assigned work, joint blocks and review queue.</p><button onClick={onGenerate} disabled={busy}><Icon name="play"/>{busy?"Generating plan…":"Generate active plan"}</button></section>;
  const entries=result.schedule_entries.filter((entry)=>entry.department===department); const taskIds=new Set(entries.map((entry)=>entry.task_id)); const blocks=result.blocks.filter((block)=>block.task_ids.some((id)=>taskIds.has(id))); const mandatory=entries.filter((entry)=>entry.mandatory).length; const occupation=entries.reduce((sum,entry)=>sum+entry.duration_minutes,0); const name=department==="ENGINEERING"?"Engineering (Civil & Track)":department==="SNT"?"S&T (Signal & Telecommunication)":"TRD (Traction Distribution)";
  return <section className={`department-dashboard ${department.toLowerCase()}`}><div className="department-hero"><div><span className="department-emblem"><Icon name={department==="ENGINEERING"?"train":department==="SNT"?"chart":"settings"} size={28}/></span><div><p className="section-kicker">Live departmental plan</p><h2>{name}</h2><p>{entries.length} scheduled packages are ready for departmental review and coordination.</p></div></div><div><button onClick={onExport}><Icon name="download"/>Download team PDF</button></div></div><div className="department-metrics"><Metric icon="calendar" label="Assigned work" value={entries.length} note="Scheduled packages" color="indigo"/><Metric icon="layers" label="Joint blocks" value={blocks.length} note="Shared possessions" color="orange"/><Metric icon="alert" label="Mandatory" value={mandatory} note="Must be accommodated" color="red"/><Metric icon="clock" label="Total occupation" value={occupation} note="Combined work time" color="blue"/></div><div className="department-grid"><div className="card department-register"><div className="card-heading"><div><p className="section-kicker">Department work register</p><h2>Assignments requiring your review</h2><p>Confirmed timing, corridor, protection and resource information from the active plan.</p></div></div><ScheduleTable entries={entries} selected={null} onSelect={()=>{}}/></div><FeedbackPanel role={department} entries={entries} items={feedback.filter((item)=>item.department===department)} planId={planId} onSend={onSend} onStatus={onStatus}/></div></section>;
}

function FeedbackPanel({ role, entries, items, planId, onSend, onStatus }: { role: Role; entries: ScheduleEntry[]; items: FeedbackItem[]; planId?: string; onSend:(payload:Omit<FeedbackItem,"feedback_id"|"created_at"|"status">)=>Promise<void>; onStatus:(id:number,status:FeedbackItem["status"])=>Promise<void> }) {
  const [department,setDepartment]=useState<Exclude<Role,"COA">>(role==="COA"?"ENGINEERING":role); const [taskId,setTaskId]=useState(""); const [message,setMessage]=useState(""); const [replyTo,setReplyTo]=useState<number|null>(null); const [busy,setBusy]=useState(false); const [sendError,setSendError]=useState(""); const filteredEntries=role==="COA"?entries.filter((entry)=>entry.department===department):entries;
  async function submit(event:React.FormEvent){event.preventDefault();if(!message.trim())return;setBusy(true);setSendError("");try{await onSend({plan_id:planId??null,sender_role:role,recipient_role:role==="COA"?department:"COA",department:role==="COA"?department:role,task_id:taskId||null,message:message.trim(),parent_id:replyTo});setMessage("");setReplyTo(null)}catch(reason){setSendError(reason instanceof Error?reason.message:"Feedback could not be sent.")}finally{setBusy(false)}}
  const departmentOptions=[{value:"ENGINEERING",label:"Engineering",detail:"Civil & Track"},{value:"SNT",label:"S&T",detail:"Signal & Telecommunication"},{value:"TRD",label:"TRD",detail:"Traction Distribution"}];
  const taskOptions=[{value:"",label:"General coordination",detail:"Not linked to one work package"},...filteredEntries.map((entry)=>({value:entry.task_id,label:`${entry.task_id} · ${entry.task_type}`,detail:`${entry.section} · ${entry.line}`}))];
  return <section className={`feedback-panel card ${role==="COA"?"coa-feedback":""}`}><div className="feedback-heading"><div><p className="section-kicker">Two-way coordination</p><h2>{role==="COA"?"Department feedback desk":"Feedback to COA"}</h2><p>{role==="COA"?"Reply to change requests or issue a new departmental instruction.":"Request a plan change and track the COA response."}</p></div><span>{items.filter((item)=>item.status!=="RESOLVED").length} open</span></div><form className="feedback-compose" onSubmit={submit}>{role==="COA"&&<FeedbackSelect label="Department" value={department} options={departmentOptions} onChange={(value)=>{setDepartment(value as Exclude<Role,"COA">);setTaskId("")}}/>}<FeedbackSelect label="Work package" value={taskId} options={taskOptions} onChange={setTaskId}/><label className="message-field">{replyTo?`Replying to #${replyTo}`:"Message"}<textarea value={message} onChange={(event)=>setMessage(event.target.value)} placeholder={role==="COA"?"Send an instruction, clarification or response…":"Describe the change required and why…"}/></label>{sendError&&<div className="feedback-send-error"><Icon name="alert" size={17}/>{sendError}</div>}<button disabled={busy||!message.trim()}><Icon name="chevron"/>{busy?"Sending…":replyTo?"Send reply":"Send feedback"}</button></form><div className="feedback-list">{items.length===0?<div className="feedback-zero"><Icon name="check"/><span><strong>No feedback yet</strong><small>The coordination trail will appear here.</small></span></div>:items.map((item)=><article key={item.feedback_id}><div className="feedback-meta"><span className={`feedback-role ${item.sender_role.toLowerCase()}`}>{item.sender_role}</span><strong>{item.sender_role} → {item.recipient_role}</strong><time>{new Date(item.created_at).toLocaleString()}</time></div><p>{item.message}</p><div className="feedback-footer"><span>{item.task_id??"General"}</span><b className={item.status.toLowerCase()}>{item.status.replaceAll("_"," ")}</b><button onClick={()=>{setDepartment(item.department);setTaskId(item.task_id??"");setReplyTo(item.feedback_id)}}>Reply</button>{item.status!=="RESOLVED"&&<button onClick={()=>onStatus(item.feedback_id,role==="COA"?"UNDER_REVIEW":"RESOLVED")}>{role==="COA"?"Review":"Resolve"}</button>}{role==="COA"&&item.status==="UNDER_REVIEW"&&<button onClick={()=>onStatus(item.feedback_id,"RESOLVED")}>Mark resolved</button>}</div></article>)}</div></section>;
}

function FeedbackSelect({label,value,options,onChange}:{label:string;value:string;options:{value:string;label:string;detail?:string}[];onChange:(value:string)=>void}){
  const [open,setOpen]=useState(false); const selected=options.find((option)=>option.value===value)??options[0];
  return <div className={`feedback-select ${open?"open":""}`}><span>{label}</span><button type="button" className="feedback-select-trigger" aria-expanded={open} onClick={()=>setOpen((current)=>!current)}><span><strong>{selected?.label}</strong><small>{selected?.detail}</small></span><Icon name="chevron" size={17}/></button>{open&&<div className="feedback-select-menu" role="listbox">{options.map((option)=><button type="button" role="option" aria-selected={option.value===value} className={option.value===value?"selected":""} key={option.value||"general"} onClick={()=>{onChange(option.value);setOpen(false)}}><span><strong>{option.label}</strong>{option.detail&&<small>{option.detail}</small>}</span>{option.value===value&&<Icon name="check" size={16}/>}</button>)}</div>}</div>;
}
type ScenarioOptions = { corridor_slots: { id: string; label: string }[]; resources: { id: string; label: string }[]; corridors: { section: string; line: string; label: string }[] };
type SimulationResponse = { base: ScheduleResponse & { scenario?: { name: string } }; scenario_result: ScheduleResponse & { scenario: { id: string; name: string; description: string; modifications: string[] } }; comparison: { base: { status: string; validation_status: string; tasks_scheduled: number; candidates_generated: number; joint_blocks: number; objective_value: number }; scenario: { status: string; validation_status: string; tasks_scheduled: number; candidates_generated: number; joint_blocks: number; objective_value: number }; impact: { status_changed: boolean; newly_unscheduled: string[]; newly_scheduled: string[]; tasks_moved: string[]; candidate_delta: number; joint_block_delta: number; objective_delta: number; validation_changed: boolean } } };
function WhatIfLab({ active, onResult }: { active: boolean; onResult: (result: ScheduleResponse) => void }) {
  const [mode, setMode] = useState<"preset" | "custom">("preset");
  const [preset, setPreset] = useState("missing_corridor");
  const [options, setOptions] = useState<ScenarioOptions>({ corridor_slots: [], resources: [], corridors: [] });
  const [removeSlots, setRemoveSlots] = useState<string[]>([]); const [resources, setResources] = useState<string[]>([]);
  const [forecast, setForecast] = useState<"base" | "stressed">("base"); const [closureEnabled, setClosureEnabled] = useState(false); const [taskEnabled, setTaskEnabled] = useState(false);
  const [closure, setClosure] = useState({ section: "Kurla-Chembur", line: "UP", start_time: "2026-08-28T02:00", end_time: "2026-08-28T04:00" });
  const [task, setTask] = useState({ task_id: "SCN-NEW-001", department: "ENGINEERING", section: "Kurla-Chembur", line: "UP", task_type: "Additional maintenance", duration_minutes: 30, earliest_start: "2026-08-28T02:00", latest_finish: "2026-08-28T04:00", criticality: 3, defect_severity: 3, asset_criticality: 3, failure_consequence: 3, requires_power_isolation: false, requires_snt_disconnection: false });
  const [simulation, setSimulation] = useState<SimulationResponse | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  useEffect(() => { if (!active || options.corridors.length) return; fetch("/api/scenario-options").then(async (response) => { if (!response.ok) throw new Error("Scenario options are unavailable."); setOptions(await response.json()); }).catch((reason) => setError(reason.message)); }, [active, options.corridors.length]);
  if (!active) return null;
  const toggle = (value: string, current: string[], setter: (next: string[]) => void) => setter(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  const activeChanges = removeSlots.length + resources.length + (forecast === "stressed" ? 1 : 0) + Number(closureEnabled) + Number(taskEnabled);
  async function run() { setBusy(true); setError(""); try { const response = mode === "preset" ? await fetch(`/api/scenarios/${preset}/simulate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ max_solve_time: 10 }) }) : await fetch("/api/scenarios/simulate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ max_solve_time: 10, goods_forecast: forecast, remove_corridor_slot_ids: removeSlots, unavailable_resource_ids: resources, corridor_closure: closureEnabled ? closure : null, add_optional_task: taskEnabled ? task : null }) }); const body = await response.json(); if (!response.ok) throw new Error(body.detail?.message ?? body.detail ?? "Simulation failed."); setSimulation(body); onResult(body.scenario_result); } catch (reason) { setError(reason instanceof Error ? reason.message : "Simulation failed."); } finally { setBusy(false); } }
  return <section className="whatif-lab"><div className="lab-mode"><button className={mode === "preset" ? "active" : ""} onClick={() => setMode("preset")}><Icon name="layers"/>Preset experiments</button><button className={mode === "custom" ? "active" : ""} onClick={() => setMode("custom")}><Icon name="settings"/>Custom experiment</button></div><div className="lab-flow"><LabStep number="01" title="Base snapshot" copy="Protected synthetic reference"/><LabStep number="02" title="Apply changes" copy={activeChanges ? `${activeChanges} custom changes selected` : mode === "preset" ? "Use a repeatable preset" : "Configure an experiment"}/><LabStep number="03" title="Run CP-SAT" copy="Candidate generation + solver"/><LabStep number="04" title="Compare impact" copy="Assignments and validation"/></div>
    {mode === "preset" ? <div className="preset-grid">{[{id:"missing_corridor",title:"Missing capacity",copy:"Remove the only compatible slot for mandatory work.",icon:"layers"},{id:"resource_unavailable",title:"Resource outage",copy:"Remove Engineering resource availability.",icon:"settings"},{id:"locked_commitment",title:"Locked conflict",copy:"Protect a commitment and move affected work.",icon:"alert"},{id:"stressed_goods",title:"Stressed goods",copy:"Introduce the higher freight forecast.",icon:"train"},{id:"competing_maintenance",title:"Competing work",copy:"Add optional work competing for capacity.",icon:"calendar"},{id:"corridor_closure",title:"Corridor closure",copy:"Lock A-B UP during an active window.",icon:"alert"}].map((item) => <button className={preset === item.id ? "selected" : ""} onClick={() => setPreset(item.id)} key={item.id}><span><Icon name={item.icon}/></span><strong>{item.title}</strong><p>{item.copy}</p>{preset === item.id && <i><Icon name="check" size={14}/></i>}</button>)}</div> : <div className="custom-builder"><BuilderSection title="Network capacity" copy="Remove one or more candidate corridor windows."><div className="choice-grid">{options.corridor_slots.map((item) => <button className={removeSlots.includes(item.id) ? "selected" : ""} onClick={() => toggle(item.id, removeSlots, setRemoveSlots)} key={item.id}><span>{item.id}</span><small>{item.label.replace(`${item.id} — `, "")}</small><Icon name={removeSlots.includes(item.id) ? "check" : "layers"}/></button>)}</div></BuilderSection><BuilderSection title="Resource availability" copy="Temporarily remove teams or machines."><div className="choice-grid resources">{options.resources.map((item) => <button className={resources.includes(item.id) ? "selected" : ""} onClick={() => toggle(item.id, resources, setResources)} key={item.id}><span>{item.id}</span><small>{item.label}</small><Icon name={resources.includes(item.id) ? "check" : "settings"}/></button>)}</div></BuilderSection><BuilderSection title="Forecast and operational changes" copy="Layer closures or additional work over the base plan."><div className="builder-controls"><label>Goods forecast<select value={forecast} onChange={(event) => setForecast(event.target.value as "base" | "stressed")}><option value="base">Base forecast</option><option value="stressed">Stressed forecast</option></select></label><Switch checked={closureEnabled} onChange={setClosureEnabled} label="Temporary corridor closure"/><Switch checked={taskEnabled} onChange={setTaskEnabled} label="Additional optional task"/></div>{closureEnabled && <div className="form-grid"><label>Corridor<select value={`${closure.section}|${closure.line}`} onChange={(event) => { const [section,line]=event.target.value.split("|"); setClosure({...closure,section,line}); }}>{options.corridors.map((item)=><option key={item.label} value={`${item.section}|${item.line}`}>{item.label}</option>)}</select></label><label>Closure starts<input type="datetime-local" value={closure.start_time} onChange={(event)=>setClosure({...closure,start_time:event.target.value})}/></label><label>Closure ends<input type="datetime-local" value={closure.end_time} onChange={(event)=>setClosure({...closure,end_time:event.target.value})}/></label></div>}{taskEnabled && <div className="form-grid task-form"><label>Task ID<input value={task.task_id} onChange={(event)=>setTask({...task,task_id:event.target.value})}/></label><label>Department<select value={task.department} onChange={(event)=>setTask({...task,department:event.target.value})}><option>ENGINEERING</option><option>SNT</option><option>TRD</option></select></label><label>Corridor<select value={`${task.section}|${task.line}`} onChange={(event)=>{const[section,line]=event.target.value.split("|");setTask({...task,section,line});}}>{options.corridors.map((item)=><option key={item.label} value={`${item.section}|${item.line}`}>{item.label}</option>)}</select></label><label>Work type<input value={task.task_type} onChange={(event)=>setTask({...task,task_type:event.target.value})}/></label><label>Duration (minutes)<input type="number" min="1" max="720" value={task.duration_minutes} onChange={(event)=>setTask({...task,duration_minutes:Number(event.target.value)})}/></label><label>Earliest start<input type="datetime-local" value={task.earliest_start} onChange={(event)=>setTask({...task,earliest_start:event.target.value})}/></label><label>Latest finish<input type="datetime-local" value={task.latest_finish} onChange={(event)=>setTask({...task,latest_finish:event.target.value})}/></label></div>}</BuilderSection></div>}
    {error && <div className="lab-error"><Icon name="alert"/><span><strong>Simulation could not run</strong>{error}</span></div>}<div className="lab-actions"><div><strong>{mode === "preset" ? "Repeatable scenario" : `${activeChanges} changes selected`}</strong><span>The base CSV fixtures will remain unchanged.</span></div><button onClick={run} disabled={busy || (mode === "custom" && activeChanges === 0)}>{busy ? <span className="spinner"/> : <Icon name="play"/>}{busy ? "Running CP-SAT…" : "Run simulation"}</button></div>{simulation && <SimulationResults simulation={simulation}/>}</section>;
}
function LabStep({ number, title, copy }: { number: string; title: string; copy: string }) { return <div><span>{number}</span><strong>{title}</strong><small>{copy}</small></div>; }
function BuilderSection({ title, copy, children }: { title: string; copy: string; children: ReactNode }) { return <section><div className="builder-heading"><div><h3>{title}</h3><p>{copy}</p></div></div>{children}</section>; }
function Switch({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) { return <button className={`lab-switch ${checked ? "on" : ""}`} onClick={() => onChange(!checked)}><i><span/></i><strong>{label}</strong></button>; }
function SimulationResults({ simulation }: { simulation: SimulationResponse }) { const impact=simulation.comparison.impact; const base=simulation.comparison.base; const scenario=simulation.comparison.scenario; return <div className="simulation-results"><div className="results-title"><div><p className="section-kicker">Actual solver comparison</p><h2>Base plan vs {simulation.scenario_result.scenario.name}</h2></div><span className={simulation.scenario_result.validation_status === "VALID" ? "valid" : "invalid"}><Icon name={simulation.scenario_result.validation_status === "VALID" ? "check" : "alert"}/>{simulation.scenario_result.validation_status}</span></div><div className="result-scoreboard"><ResultSide label="Base" status={base.status} tasks={base.tasks_scheduled} blocks={base.joint_blocks} candidates={base.candidates_generated} objective={base.objective_value}/><div className="versus">VS</div><ResultSide label="What-if" status={scenario.status} tasks={scenario.tasks_scheduled} blocks={scenario.joint_blocks} candidates={scenario.candidates_generated} objective={scenario.objective_value}/></div><div className="impact-grid"><Impact label="Tasks moved" value={impact.tasks_moved.length} items={impact.tasks_moved}/><Impact label="Newly unscheduled" value={impact.newly_unscheduled.length} items={impact.newly_unscheduled} bad/><Impact label="Newly scheduled" value={impact.newly_scheduled.length} items={impact.newly_scheduled}/></div><div className="modification-list"><strong>Applied modifications</strong>{simulation.scenario_result.scenario.modifications.map((item)=><span key={item}><Icon name="check" size={14}/>{item}</span>)}</div></div>; }
function ResultSide({label,status,tasks,blocks,candidates,objective}:{label:string;status:string;tasks:number;blocks:number;candidates:number;objective:number}){return <article><p>{label}</p><h3>{status}</h3><div><span><strong>{tasks}</strong><small>tasks</small></span><span><strong>{blocks}</strong><small>blocks</small></span><span><strong>{candidates}</strong><small>candidates</small></span><span><strong>{Math.round(objective*1000)/1000}</strong><small>objective</small></span></div></article>}
function Impact({label,value,items,bad=false}:{label:string;value:string|number;items:string[];bad?:boolean}){const visible=items.slice(0,6);return <article className={bad&&Number(value)>0?"bad":""}><div className="impact-heading"><p>{label}</p><strong>{value}</strong></div>{items.length?<div className="impact-tasks">{visible.map((item)=><span key={item}>{item}</span>)}{items.length>visible.length&&<b>+{items.length-visible.length} more</b>}</div>:<small>No affected tasks</small>}</article>}
function SystemStatusBanner({ active, workflow, planningMode }: { active: boolean; workflow: WorkflowState; planningMode: string }) { if (!active) return null; const online = workflow.health === "online"; return <section className="system-status-banner"><div className="system-health"><span className={online ? "online" : workflow.health}><Icon name={online ? "check" : "alert"} size={25}/></span><div><p className="section-kicker">Runtime health</p><h2>{online ? "All local systems operational" : workflow.health === "checking" ? "Checking local services" : "Planning engine unavailable"}</h2><p>{online ? "FastAPI is responding and the frontend can reach the CP-SAT planning service." : "Start the backend service to enable planning and simulation."}</p></div></div><div className="runtime-facts"><span><small>API service</small><strong>{workflow.health}</strong></span><span><small>Scenario definitions</small><strong>{workflow.scenarioCount ?? "—"}</strong></span><span><small>Planning mode</small><strong>{planningMode}</strong></span><span><small>Execution</small><strong>Local / offline</strong></span></div></section>; }
function BackendWorkflowPanel({ workflow, busy, onStatus, onReplan, onCsv }: { workflow: WorkflowState; busy: boolean; onStatus: (status: string) => void; onReplan: () => void; onCsv: () => void }) { const metrics = workflow.metrics ?? {}; const baseline = workflow.baselineMetrics ?? {}; return <section className="backend-workflow"><div className="workflow-heading"><div><p className="section-kicker">Backend orchestration</p><h2>End-to-end planning evidence</h2><p>Every stage below is returned by FastAPI and the persisted CP-SAT workflow.</p></div><span className={`backend-state ${workflow.planId ? "ready" : "stateless"}`}><i/>{busy ? "Processing" : workflow.planId ? "Persisted plan" : "Stateless scenario"}</span></div><div className="workflow-rail"><WorkflowStep icon="check" label="API health" value={workflow.health}/><WorkflowStep icon="chart" label="Input validation" value={workflow.importStatus ?? "Pending"}/><WorkflowStep icon="layers" label="Immutable snapshot" value={workflow.snapshotId ? "Created" : "Not created"}/><WorkflowStep icon="settings" label="CP-SAT plan" value={workflow.planId ? "Solved & saved" : "Not persisted"}/><WorkflowStep icon="check" label="Independent validation" value={workflow.metrics ? `${metrics.hard_constraint_violations ?? 0} violations` : "Pending"}/></div>{workflow.planId && <><div className="plan-identifiers"><span><small>Snapshot ID</small><strong>{workflow.snapshotId}</strong></span><span><small>Plan ID</small><strong>{workflow.planId}</strong></span><span><small>Mode</small><strong>{workflow.planningMode}</strong></span><span><small>Review status</small><strong>{workflow.planStatus}</strong></span></div><div className="metric-comparison"><Comparison label="Tasks scheduled" baseline={baseline.tasks_scheduled} optimized={metrics.tasks_scheduled}/><Comparison label="Joint blocks" baseline={baseline.joint_blocks_created} optimized={metrics.joint_blocks_created}/><Comparison label="Block minutes" baseline={baseline.traffic_block_minutes} optimized={metrics.traffic_block_minutes}/><Comparison label="Mobilizations avoided" baseline={baseline.mobilizations_avoided} optimized={metrics.mobilizations_avoided}/><Comparison label="Resource utilization" baseline={baseline.resource_utilization} optimized={metrics.resource_utilization} suffix="%"/><Comparison label="Plan stability" baseline={baseline.plan_stability_percentage} optimized={metrics.plan_stability_percentage} suffix="%"/></div><div className="workflow-actions"><button onClick={() => onStatus("UNDER_REVIEW")} disabled={busy || workflow.planStatus === "UNDER_REVIEW"}><Icon name="alert"/>Send to review</button><button onClick={() => onStatus("APPROVED_FOR_DEMO")} disabled={busy || workflow.planStatus === "APPROVED_FOR_DEMO"}><Icon name="check"/>Approve for demo</button><button onClick={onReplan} disabled={busy}><Icon name="chart"/>Replan stressed forecast</button><button onClick={onCsv} disabled={busy}><Icon name="download"/>Export backend CSV</button></div></>}{workflow.message && <p className="workflow-message">{workflow.message}</p>}</section>; }
function WorkflowStep({ icon, label, value }: { icon: string; label: string; value: string }) { const complete = !["Pending", "Not created", "Not persisted", "offline"].includes(value); return <div className={complete ? "complete" : ""}><span><Icon name={icon} size={15}/></span><small>{label}</small><strong>{value}</strong></div>; }
function Comparison({ label, baseline, optimized, suffix = "" }: { label: string; baseline?: number; optimized?: number; suffix?: string }) { return <article><p>{label}</p><span><small>Baseline</small><strong>{baseline == null ? "—" : `${Math.round(baseline * 100) / 100}${suffix}`}</strong></span><i>→</i><span><small>Optimized</small><strong>{optimized == null ? "—" : `${Math.round(optimized * 100) / 100}${suffix}`}</strong></span></article>; }
function ValidationAudit({ active, result, workflow }: { active: boolean; result: ScheduleResponse; workflow: WorkflowState }) { if (!active) return null; const taskIds=result.schedule_entries.map((entry)=>entry.task_id); const reconciled=result.summary.tasks_scheduled+result.unscheduled.length; const checks=[{name:"Independent plan validator",pass:result.validation_status==="VALID",evidence:`${result.validation.errors.length} hard errors · ${result.validation.warnings.length} warnings`},{name:"Input reconciliation",pass:reconciled===result.summary.tasks_considered,evidence:`${reconciled} of ${result.summary.tasks_considered} tasks accounted for`},{name:"Mandatory task coverage",pass:result.solver.unscheduled_mandatory_task_ids.length===0,evidence:result.solver.unscheduled_mandatory_task_ids.length?`${result.solver.unscheduled_mandatory_task_ids.join(", ")} missing`:"Every mandatory task handled"},{name:"Unique task assignment",pass:new Set(taskIds).size===taskIds.length,evidence:`${new Set(taskIds).size} unique assignments across ${taskIds.length} entries`},{name:"Valid assignment windows",pass:result.schedule_entries.every((entry)=>new Date(entry.start_time)<new Date(entry.end_time)&&new Date(entry.end_time)<=new Date(entry.latest_finish)),evidence:"Start, end and latest-finish boundaries checked"},{name:"Resource references",pass:result.schedule_entries.every((entry)=>entry.resource_ids.length>0),evidence:`${new Set(result.schedule_entries.flatMap((entry)=>entry.resource_ids)).size} unique resources assigned`},{name:"Solver termination",pass:["OPTIMAL","FEASIBLE"].includes(result.solver.status),evidence:`${result.solver.status} in ${result.solver.solve_time_seconds.toFixed(3)} seconds`},{name:"Snapshot provenance",pass:Boolean(workflow.snapshotId)||!workflow.planId,evidence:workflow.snapshotId??"Stateless scenario run — no snapshot persisted"}]; const passed=checks.filter((check)=>check.pass).length; const allIssues=[...result.validation.errors.map((issue)=>({...issue,severity:"ERROR"})),...result.validation.warnings.map((issue)=>({...issue,severity:"WARNING"}))]; return <section className="validation-audit"><div className="audit-hero"><div className={`audit-score ${passed===checks.length?"passed":"attention"}`}><strong>{passed}/{checks.length}</strong><span>checks passed</span></div><div><p className="section-kicker">Constraint assurance report</p><h2>{passed===checks.length?"Plan integrity confirmed":"Plan requires review"}</h2><p>This report proves plan-wide consistency. Unscheduled-task explanations remain separately available under Exceptions.</p></div><div className="audit-meta"><span><small>Solver</small><strong>{result.solver.status}</strong></span><span><small>Validation</small><strong>{result.validation_status}</strong></span><span><small>Objective</small><strong>{result.solver.objective_value.toFixed(3)}</strong></span></div></div><div className="constraint-ledger"><div className="ledger-heading"><div><p className="section-kicker">Hard-constraint ledger</p><h2>Automated assurance checks</h2></div><span>{checks.length} checks</span></div>{checks.map((check,index)=><article className={check.pass?"pass":"fail"} key={check.name}><span className="check-number">{String(index+1).padStart(2,"0")}</span><span className="check-icon"><Icon name={check.pass?"check":"alert"}/></span><div><strong>{check.name}</strong><p>{check.evidence}</p></div><b>{check.pass?"Passed":"Attention"}</b></article>)}</div><div className="audit-lower"><section className="issue-ledger"><div className="ledger-heading"><div><p className="section-kicker">Validator output</p><h2>Issue ledger</h2></div><span>{allIssues.length} issues</span></div>{allIssues.length?<div>{allIssues.map((issue,index)=><article key={`${issue.code}-${index}`}><span className={issue.severity.toLowerCase()}>{issue.severity}</span><div><strong>{issue.code.replaceAll("_"," ")}</strong><p>{issue.message}</p></div></article>)}</div>:<div className="zero-issues"><span><Icon name="check" size={25}/></span><div><strong>No validator issues</strong><p>The independent validator reported neither errors nor warnings.</p></div></div>}</section><section className="provenance-card"><p className="section-kicker">Reproducibility</p><h2>Plan provenance</h2><dl><div><dt>Snapshot</dt><dd>{workflow.snapshotId??"Stateless run"}</dd></div><div><dt>Plan version</dt><dd>{workflow.planId??"Direct schedule"}</dd></div><div><dt>Planning mode</dt><dd>{workflow.planningMode??"Scenario"}</dd></div><div><dt>CP-SAT runtime</dt><dd>{result.solver.solve_time_seconds.toFixed(3)}s</dd></div><div><dt>Candidates evaluated</dt><dd>{result.summary.candidates_generated}</dd></div><div><dt>Selected assignments</dt><dd>{result.summary.candidates_selected}</dd></div></dl>{workflow.sourceHashes&&<div className="source-hashes"><strong>Source fingerprints</strong>{Object.entries(workflow.sourceHashes).slice(0,4).map(([name,hash])=><span key={name}><small>{name}</small><code>{hash.slice(0,18)}…</code></span>)}</div>}</section></div></section>; }
function NoPlan({ onRun }: { onRun: () => void }) { return <section className="no-plan card"><span><Icon name="layers" size={26}/></span><h2>No active planning run</h2><p>Generate a schedule from Overview first. The result will remain available while you move between every workspace.</p><button onClick={onRun}><Icon name="play"/>Go to Overview</button></section>; }
function JointBlocksPage({ result }: { result: ScheduleResponse }) { return <section className="blocks-page"><div className="blocks-summary"><Metric icon="layers" label="Joint blocks" value={result.blocks.length} note="Coordinated possessions" color="orange"/><Metric icon="calendar" label="Work packages" value={result.blocks.reduce((sum, block) => sum + block.task_ids.length, 0)} note="Tasks inside blocks" color="indigo"/><Metric icon="clock" label="Total occupation" value={`${result.blocks.reduce((sum, block) => sum + Math.round((new Date(block.end_time).getTime() - new Date(block.start_time).getTime()) / 60000), 0)}m`} note="Combined block time" color="blue"/></div><div className="block-register card"><div className="card-heading"><div><p className="section-kicker">Coordinated possessions</p><h2>Active joint block register</h2><p>Each block preserves its individual departmental work packages.</p></div><span className="assurance-badge verified"><Icon name="check"/>Advisory plan</span></div><div className="block-list">{result.blocks.map((block, index) => { const entries = result.schedule_entries.filter((entry) => block.task_ids.includes(entry.task_id)); const minutes = Math.round((new Date(block.end_time).getTime() - new Date(block.start_time).getTime()) / 60000); return <article key={block.block_id}><div className="block-index"><span>JB</span><strong>{String(index + 1).padStart(2, "0")}</strong></div><div className="block-main"><div><code>{block.block_id}</code><h3>{block.section} · {block.line}</h3><p><Icon name="calendar" size={14}/>{formatTime(block.start_time)} – {shortTime(block.end_time)}<span>·</span>{minutes} minutes</p></div><div className="package-row">{entries.map((entry) => <span className={`package-chip ${deptClass(entry.department)}`} key={entry.task_id}><i/>{entry.task_id}<small>{entry.department}</small></span>)}</div></div><div className="coordination-value"><strong>{block.task_ids.length}</strong><small>work<br/>packages</small></div></article>; })}</div></div></section>; }
function ConfigurationPage({ active, scenario }: { active: boolean; scenario: string }) { if (!active) return null; return <section className="configuration-page"><div className="config-grid"><article className="card config-card"><span className="config-icon indigo"><Icon name="settings"/></span><div><p className="section-kicker">Optimization engine</p><h2>CP-SAT scheduling</h2><p>Deterministic constraint optimization with a ten-second maximum solve time and explainable priority scoring.</p><dl><div><dt>Execution</dt><dd>Local only</dd></div><div><dt>Schedule generation</dt><dd>OR-Tools CP-SAT</dd></div><div><dt>Independent validation</dt><dd>Enabled</dd></div><div><dt>Operational authority</dt><dd>Advisory only</dd></div></dl></div></article><article className="card config-card"><span className="config-icon orange"><Icon name="calendar"/></span><div><p className="section-kicker">Active setup</p><h2>Scenario configuration</h2><p>The selected scenario changes synthetic inputs without changing the planning rules.</p><dl><div><dt>Current scenario</dt><dd>{scenarios.find((item) => item.value === scenario)?.label}</dd></div><div><dt>Data source</dt><dd>Synthetic CSV fixtures</dd></div><div><dt>Departments</dt><dd>Engineering · S&amp;T · TRD</dd></div><div><dt>Plan export</dt><dd>Formatted PDF report</dd></div></dl></div></article></div><div className="card scenario-catalog"><div className="card-heading"><div><p className="section-kicker">Demonstration catalog</p><h2>Available planning scenarios</h2><p>Purpose-built cases for validating planning behavior and explanations.</p></div></div><div className="scenario-grid">{scenarios.map((item) => <article className={item.value === scenario ? "selected" : ""} key={item.value}><span><Icon name={item.value === "base" ? "check" : "alert"}/></span><div><strong>{item.label}</strong><p>{item.hint}</p><code>{item.value}</code></div></article>)}</div></div></section>; }
function Timeline({ entries, timeline, selected, onSelect }: { entries: ScheduleEntry[]; timeline: { start: number; end: number }; selected: ScheduleEntry | null; onSelect: (entry: ScheduleEntry) => void }) {
  const ticks = Array.from({ length: 6 }, (_, i) => timeline.start + ((timeline.end - timeline.start) * i / 5));
  const horizonMinutes = Math.max(1, Math.round((timeline.end - timeline.start) / 60000));
  return <div className="gantt">
    <div className="gantt-overview"><div><span className="overview-signal"><Icon name="chart" size={16}/></span><span><strong>Active maintenance horizon</strong><small>{formatTime(new Date(timeline.start).toISOString())} → {formatTime(new Date(timeline.end).toISOString())}</small></span></div><div className="overview-stats"><span><strong>{entries.length}</strong><small>packages</small></span><span><strong>{formatDuration(horizonMinutes)}</strong><small>horizon</small></span></div></div>
    <div className="gantt-axis"><div className="axis-title"><Icon name="clock" size={14}/><span>Corridor / work package</span></div>{ticks.map((tick) => { const date = new Date(tick); return <div className="axis-tick" key={tick}><strong>{date.toLocaleDateString([], { month: "short", day: "2-digit" })}</strong><small>{date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small></div>; })}</div>
    <div className="gantt-body">{entries.map((entry, index) => {
      const left = ((new Date(entry.start_time).getTime() - timeline.start) / (timeline.end - timeline.start || 1)) * 100;
      const rawWidth = ((new Date(entry.end_time).getTime() - new Date(entry.start_time).getTime()) / (timeline.end - timeline.start || 1)) * 100;
      const edge = left > 82 ? "edge-right" : left < 4 ? "edge-left" : "";
      return <button key={entry.candidate_id} className={`gantt-row ${selected?.candidate_id === entry.candidate_id ? "selected" : ""}`} onClick={() => onSelect(entry)} style={{ "--row-index": index } as React.CSSProperties}>
        <span className="gantt-label"><span className={`rail-node ${deptClass(entry.department)}`}><i/></span><span><strong>{entry.section} <b>· {entry.line}</b></strong><small>{entry.task_id}<i/> {entry.department}</small></span></span>
        <span className="gantt-track"><span className="track-grid"/><span className="capacity-line"/><span className={`work-card ${deptClass(entry.department)} ${edge}`} style={{ left: `${left}%`, width: `${Math.max(rawWidth, 4)}%` }}><span className="work-card-main"><b>{entry.task_id}</b><em>{formatDuration(entry.duration_minutes)}</em></span><span className="work-type">{entry.task_type}</span><span className="work-window">{shortTime(entry.start_time)} – {shortTime(entry.end_time)}</span></span></span>
      </button>;
    })}</div>
  </div>;
}
function ScheduleTable({ entries, selected, onSelect }: { entries: ScheduleEntry[]; selected: ScheduleEntry | null; onSelect: (entry: ScheduleEntry) => void }) { return <div className="table-wrap"><table><thead><tr><th>Task</th><th>Department</th><th>Corridor</th><th>Window</th><th>Priority</th></tr></thead><tbody>{entries.map((entry) => <tr key={entry.candidate_id} className={selected?.candidate_id === entry.candidate_id ? "selected" : ""} onClick={() => onSelect(entry)}><td><strong>{entry.task_id}</strong><small>{entry.task_type}</small></td><td><span className={`department-tag ${deptClass(entry.department)}`}>{entry.department}</span></td><td>{entry.section} · {entry.line}</td><td>{formatTime(entry.start_time)}<small>to {formatTime(entry.end_time)}</small></td><td><strong>{Math.round(entry.priority * 100)}</strong><small>{entry.priority_band}</small></td></tr>)}</tbody></table></div>; }
function Detail({ label, value, icon }: { label: string; value: string; icon: string }) { return <div><dt><Icon name={icon} size={16}/>{label}</dt><dd>{value}</dd></div>; }
function PriorityEvidence({ entry }: { entry: ScheduleEntry }) { const score=Math.round(entry.priority*100); return <section className="priority-evidence authoritative"><div className="priority-evidence-head"><div><span><Icon name="settings" size={14}/>Authoritative ML priority</span><strong><em>{score}</em><small>/ 100 predicted outcome risk</small></strong><p>This model score is used directly by CP-SAT to rank feasible work.</p></div></div><div className="confidence-track"><i style={{width:`${score}%`}}/></div><div className="priority-factors">{(entry.priority_factors??[]).map((factor)=><span key={factor}>{factor}</span>)}</div><small>{entry.priority_model_version??"outcome-risk model"} · Operational priority source: ML model.</small></section>; }
function Requirement({ active, children }: { active: boolean; children: ReactNode }) { return <span className={active ? "active" : ""}><Icon name={active ? "check" : "alert"} size={13}/>{children}</span>; }
function IssueList({ items, warning = false }: { items: ValidationIssue[]; warning?: boolean }) { return <div className={`issue-list ${warning ? "warning" : ""}`}>{items.map((item, index) => <article key={`${item.code}-${index}`}><Icon name="alert"/><div><strong>{item.code.replaceAll("_", " ")}</strong><p>{item.message}</p></div></article>)}</div>; }
