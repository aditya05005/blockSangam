import React, { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

type ValidationIssue = { code: string; message: string; task_ids?: string[]; candidate_ids?: string[]; block_id?: string | null };
type ScheduleEntry = {
  candidate_id: string; task_id: string; department: string; section: string; line: string; task_type: string;
  start_time: string; end_time: string; duration_minutes: number; mandatory: boolean; priority: number; priority_band: string;
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

const scenarios = [
  { value: "base", label: "Base forecast", hint: "Reference operating plan" },
  { value: "missing_corridor", label: "Missing capacity", hint: "Corridor availability test" },
  { value: "resource_unavailable", label: "Resource outage", hint: "Team availability test" },
  { value: "locked_commitment", label: "Locked commitment", hint: "Protected block conflict" },
  { value: "stressed_goods", label: "Stressed goods", hint: "Higher freight demand" },
  { value: "competing_maintenance", label: "Competing work", hint: "Department conflict test" },
] as const;

type Page = "overview" | "plan" | "blocks" | "exceptions" | "validation" | "settings";
const pageCopy: Record<Page, { eyebrow: string; title: string; description: string }> = {
  overview: { eyebrow: "Planning workspace", title: "Good morning, Planner.", description: "Coordinate safer maintenance windows across Engineering, S&T and TRD." },
  plan: { eyebrow: "Planning workspace / Plan studio", title: "Plan Studio", description: "Inspect every scheduled work package across the corridor and its assigned window." },
  blocks: { eyebrow: "Planning workspace / Joint blocks", title: "Joint Block Register", description: "Review coordinated possessions and the departmental work combined inside them." },
  exceptions: { eyebrow: "Planning workspace / Exceptions", title: "Exceptions & Explanations", description: "Understand every task the engine could not place and the constraint responsible." },
  validation: { eyebrow: "Planning workspace / Validation", title: "Constraint Validation", description: "Review independent assurance results and solver evidence for the active plan." },
  settings: { eyebrow: "System / Configuration", title: "Planning Configuration", description: "Inspect available scenarios, engine boundaries, and prototype operating assumptions." },
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
  const scenarioPicker = useRef<HTMLDivElement>(null);
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

  async function downloadJson() {
    if (!result) return;
    let blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    let filename = `blocksangam-${scenario}-schedule.json`;
    if (workflow.planId) {
      const response = await fetch(`/api/plans/${workflow.planId}/export?format=json`);
      if (response.ok) { blob = await response.blob(); filename = `${workflow.planId}.json`; }
    }
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

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand-mark"><span className="brand-icon brand-logo"><img src="/blocksangam-logo.png" alt="BlockSangam railway logo" /></span><div><strong>BlockSangam</strong><small>Planning console</small></div></div>
      <nav aria-label="Primary navigation"><p className="nav-label">Workspace</p><NavLink page="overview" current={page} icon="grid">Overview</NavLink><NavLink page="plan" current={page} icon="calendar">Plan studio<span>01</span></NavLink><NavLink page="blocks" current={page} icon="layers">Joint blocks</NavLink><NavLink page="exceptions" current={page} icon="alert">Exceptions{result?.unscheduled.length ? <b>{result.unscheduled.length}</b> : null}</NavLink><NavLink page="validation" current={page} icon="chart">Validation</NavLink><p className="nav-label secondary-label">System</p><NavLink page="settings" current={page} icon="settings">Configuration</NavLink></nav>
      <div className={`side-status ${workflow.health}`}><span className="live-dot"/><div><strong>{workflow.health === "online" ? "Local engine online" : workflow.health === "offline" ? "Engine unavailable" : "Checking local engine"}</strong><small>{workflow.scenarioCount ? `${workflow.scenarioCount} scenarios · synthetic v1.0` : "Connecting to FastAPI…"}</small></div></div>
    </aside>
    <main className={`workspace page-${page}`} data-page={page}>
      <div className="ambient ambient-one"/><div className="ambient ambient-two"/>
      <header className="page-header"><div><div className="breadcrumbs"><span>{pageCopy[page].eyebrow}</span></div><h1>{pageCopy[page].title}</h1><p>{pageCopy[page].description}</p></div><div className="header-actions"><div className="engine-pill"><span className="live-dot"/>CP-SAT engine ready</div><button className="export-button" onClick={downloadJson} disabled={!result}><Icon name="download"/>Export plan</button></div></header>
      <section className="run-card"><div className="run-intro"><span className="run-icon"><Icon name="layers"/></span><div><p className="section-kicker">Planning run</p><h2>Build a constraint-verified schedule</h2><p>Choose an operating scenario and let the local engine compose compatible maintenance blocks.</p></div></div><div className="run-controls"><div className="scenario-control" ref={scenarioPicker}><span className="control-label">Forecast scenario</span><button className={`scenario-trigger ${scenarioOpen ? "open" : ""}`} type="button" aria-haspopup="listbox" aria-expanded={scenarioOpen} onClick={() => !busy && setScenarioOpen((open) => !open)} disabled={busy}><span className={`scenario-symbol ${scenario}`}><Icon name={scenario === "base" ? "check" : "alert"} size={15}/></span><span className="scenario-trigger-copy"><strong>{scenarioMeta.label}</strong><small>{scenarioMeta.hint}</small></span><span className="select-chevron"><Icon name="chevron" size={16}/></span></button>{scenarioOpen && <div className="scenario-menu" role="listbox" aria-label="Forecast scenario">{scenarios.map((item, index) => <button type="button" role="option" aria-selected={item.value === scenario} className={item.value === scenario ? "selected" : ""} style={{ "--option-index": index } as React.CSSProperties} key={item.value} onClick={() => { setScenario(item.value); setScenarioOpen(false); }}><span className={`scenario-symbol ${item.value}`}><Icon name={item.value === "base" ? "check" : "alert"} size={14}/></span><span><strong>{item.label}</strong><small>{item.hint}</small></span>{item.value === scenario && <i><Icon name="check" size={14}/></i>}</button>)}</div>}</div><button className="run-button" onClick={generateSchedule} disabled={busy}>{busy ? <span className="spinner"/> : <Icon name="play"/>}{busy ? "Optimizing plan…" : "Run optimizer"}</button></div></section>
      {error && <div className="error-banner"><Icon name="alert"/><div><strong>Planning run failed</strong><p>{error}</p></div></div>}
      <div className="planning-mode-strip"><div><span>Planning horizon</span><p>Persist this run as a precise weekly plan or a broad monthly planning envelope.</p></div><div className="mode-toggle"><button className={planningMode === "weekly" ? "active" : ""} onClick={() => setPlanningMode("weekly")}><Icon name="calendar" size={14}/>Weekly</button><button className={planningMode === "monthly" ? "active" : ""} onClick={() => setPlanningMode("monthly")}><Icon name="layers" size={14}/>Monthly</button></div></div>
      {!result && <section className={`welcome-state ${busy ? "is-busy" : ""}`}><div className="route-graphic"><span>A</span><i/><span>B</span><i/><span>C</span><i/><span>D</span></div><span className="welcome-icon">{busy ? <span className="spinner large"/> : <Icon name="train" size={28}/>}</span><h2>{busy ? "Solving the corridor plan" : "Your planning board is ready"}</h2><p>{busy ? "Checking capacity, resources, commitments and train movements. This usually takes only a moment." : "Run the base scenario to generate your first coordinated plan. Every selected block is independently checked before it appears here."}</p>{!busy && <button onClick={generateSchedule}><Icon name="play"/>Generate base plan</button>}</section>}
      {result && <>
        <section className="metric-grid"><Metric icon="calendar" label="Tasks scheduled" value={`${result.summary.tasks_scheduled}`} denominator={`/ ${result.summary.tasks_considered}`} note={`${Math.round(result.summary.tasks_scheduled / Math.max(result.summary.tasks_considered, 1) * 100)}% coverage`} color="indigo"/><Metric icon="layers" label="Joint blocks" value={result.summary.joint_blocks} note="Coordinated windows" color="orange"/><Metric icon="chart" label="Candidates" value={result.summary.candidates_generated} note={`${result.summary.candidates_selected} selected`} color="blue"/><Metric icon={valid ? "check" : "alert"} label="Plan assurance" value={valid ? "Verified" : "Review"} note={`${result.validation.errors.length} hard constraint issues`} color={valid ? "green" : "red"}/></section>
        <section className="planning-layout" id="plan"><div className="board card"><div className="card-heading"><div><p className="section-kicker">Proposed work</p><h2>Corridor planning board</h2><p>{result.schedule_entries.length} work packages across {result.blocks.length} coordinated blocks</p></div><div className="segmented"><button className={view === "timeline" ? "active" : ""} onClick={() => setView("timeline")}>Timeline</button><button className={view === "table" ? "active" : ""} onClick={() => setView("table")}>List</button></div></div><div className="legend"><span><i className="engineering"/>Engineering</span><span><i className="snt"/>S&amp;T</span><span><i className="trd"/>TRD</span><span className="legend-note"><Icon name="clock" size={14}/>All times shown locally</span></div>{view === "timeline" && timeline && <Timeline entries={result.schedule_entries} timeline={timeline} selected={selected} onSelect={setSelected}/>} {view === "table" && <ScheduleTable entries={result.schedule_entries} selected={selected} onSelect={setSelected}/>}</div>
          <aside className="inspector card"><div className="inspector-top"><p className="section-kicker">Work package</p>{selected && <span className={`department-tag ${deptClass(selected.department)}`}>{selected.department}</span>}</div>{selected ? <><div className="task-heading"><div><h2>{selected.task_id}</h2><p>{selected.task_type}</p></div><div className={`priority-orb ${selected.priority_band.toLowerCase()}`}><strong>{Math.round(selected.priority * 100)}</strong><small>priority</small></div></div>{selected.mandatory && <div className="mandatory-note"><Icon name="alert" size={15}/><span><strong>Mandatory work</strong>This task must be included in a valid plan.</span></div>}<dl className="detail-list"><Detail label="Corridor" value={`${selected.section} · ${selected.line}`} icon="train"/><Detail label="Schedule" value={`${formatTime(selected.start_time)} – ${shortTime(selected.end_time)}`} icon="calendar"/><Detail label="Occupation" value={`${selected.duration_minutes} minutes`} icon="clock"/><Detail label="Resource" value={selected.resource_ids.join(", ") || "None assigned"} icon="settings"/><Detail label="Slot reference" value={selected.slot_id} icon="layers"/></dl><div className="requirements"><p>Protection requirements</p><div><Requirement active={selected.requires_traffic_block}>Traffic block</Requirement><Requirement active={selected.requires_power_isolation}>Power isolation</Requirement><Requirement active={selected.requires_snt_disconnection}>S&amp;T disconnect</Requirement></div></div></> : <p className="empty-copy">Select a work package to inspect its assignment.</p>}</aside></section>
        <section className="lower-grid"><div className="card assurance-card" id="validation"><div className="card-heading compact"><div><p className="section-kicker">Independent validator</p><h2>Plan assurance</h2></div><span className={`assurance-badge ${valid ? "verified" : "invalid"}`}><Icon name={valid ? "check" : "alert"}/>{valid ? "Constraint verified" : "Action required"}</span></div>{result.validation.errors.length === 0 ? <div className="assurance-body"><span className="seal"><Icon name="check" size={25}/></span><div><strong>All hard constraints passed</strong><p>The generated plan independently reconciles task windows, train occupancy, locked work and resource capacity.</p></div></div> : <IssueList items={result.validation.errors}/>} {!!result.validation.warnings.length && <IssueList items={result.validation.warnings} warning/>}<div className="solver-strip"><span><small>Solver status</small><strong>{result.solver.status}</strong></span><span><small>Runtime</small><strong>{result.solver.solve_time_seconds.toFixed(3)}s</strong></span><span><small>Objective</small><strong>{result.solver.objective_value.toFixed(3)}</strong></span></div></div>
          <div className="card exceptions-card" id="exceptions"><div className="card-heading compact"><div><p className="section-kicker">Decision transparency</p><h2>Unscheduled work</h2></div><span className="count-badge">{result.unscheduled.length}</span></div>{result.unscheduled.length ? <div className="exception-list">{result.unscheduled.map((item) => <article key={item.task_id}><span className={`exception-dept ${deptClass(item.department)}`}>{item.department.slice(0, 3)}</span><div><div><strong>{item.task_id}</strong><code>{item.reason_code.replaceAll("_", " ")}</code></div><p>{item.explanation}</p></div></article>)}</div> : <div className="all-scheduled"><Icon name="check"/><div><strong>Every task was placed</strong><p>No unscheduled explanations for this run.</p></div></div>}</div></section>
      </>}
      {result && <BackendWorkflowPanel workflow={workflow} busy={workflowBusy} onStatus={changePlanStatus} onReplan={replanWithStress} onCsv={downloadBackendCsv}/>} 
      {result && <JointBlocksPage result={result}/>} 
      {!result && page !== "overview" && page !== "settings" && <NoPlan onRun={() => { window.location.hash = "overview"; setPage("overview"); }}/>} 
      <ConfigurationPage active={page === "settings"} scenario={scenario}/>
      <footer><span>BlockSangam · local synthetic-data prototype</span><span>Advisory only — not an operational Indian Railways block grant</span></footer>
    </main>
  </div>;
}

function Metric({ icon, label, value, denominator, note, color }: { icon: string; label: string; value: string | number; denominator?: string; note: string; color: string }) { const displayValue = label === "Total occupation" ? formatDuration(value) : value; return <article className="metric-card"><span className={`metric-icon ${color}`}><Icon name={icon}/></span><div><p>{label}</p><strong>{displayValue}<small>{denominator}</small></strong><span>{note}</span></div></article>; }
function NavLink({ page, current, icon, children }: { page: Page; current: Page; icon: string; children: ReactNode }) { return <a className={`nav-item ${current === page ? "active" : ""}`} href={`#${page}`}><Icon name={icon}/>{children}</a>; }
function BackendWorkflowPanel({ workflow, busy, onStatus, onReplan, onCsv }: { workflow: WorkflowState; busy: boolean; onStatus: (status: string) => void; onReplan: () => void; onCsv: () => void }) { const metrics = workflow.metrics ?? {}; const baseline = workflow.baselineMetrics ?? {}; return <section className="backend-workflow"><div className="workflow-heading"><div><p className="section-kicker">Backend orchestration</p><h2>End-to-end planning evidence</h2><p>Every stage below is returned by FastAPI and the persisted CP-SAT workflow.</p></div><span className={`backend-state ${workflow.planId ? "ready" : "stateless"}`}><i/>{busy ? "Processing" : workflow.planId ? "Persisted plan" : "Stateless scenario"}</span></div><div className="workflow-rail"><WorkflowStep icon="check" label="API health" value={workflow.health}/><WorkflowStep icon="chart" label="Input validation" value={workflow.importStatus ?? "Pending"}/><WorkflowStep icon="layers" label="Immutable snapshot" value={workflow.snapshotId ? "Created" : "Not created"}/><WorkflowStep icon="settings" label="CP-SAT plan" value={workflow.planId ? "Solved & saved" : "Not persisted"}/><WorkflowStep icon="check" label="Independent validation" value={workflow.metrics ? `${metrics.hard_constraint_violations ?? 0} violations` : "Pending"}/></div>{workflow.planId && <><div className="plan-identifiers"><span><small>Snapshot ID</small><strong>{workflow.snapshotId}</strong></span><span><small>Plan ID</small><strong>{workflow.planId}</strong></span><span><small>Mode</small><strong>{workflow.planningMode}</strong></span><span><small>Review status</small><strong>{workflow.planStatus}</strong></span></div><div className="metric-comparison"><Comparison label="Tasks scheduled" baseline={baseline.tasks_scheduled} optimized={metrics.tasks_scheduled}/><Comparison label="Joint blocks" baseline={baseline.joint_blocks_created} optimized={metrics.joint_blocks_created}/><Comparison label="Block minutes" baseline={baseline.traffic_block_minutes} optimized={metrics.traffic_block_minutes}/><Comparison label="Mobilizations avoided" baseline={baseline.mobilizations_avoided} optimized={metrics.mobilizations_avoided}/><Comparison label="Resource utilization" baseline={baseline.resource_utilization} optimized={metrics.resource_utilization} suffix="%"/><Comparison label="Plan stability" baseline={baseline.plan_stability_percentage} optimized={metrics.plan_stability_percentage} suffix="%"/></div><div className="workflow-actions"><button onClick={() => onStatus("UNDER_REVIEW")} disabled={busy || workflow.planStatus === "UNDER_REVIEW"}><Icon name="alert"/>Send to review</button><button onClick={() => onStatus("APPROVED_FOR_DEMO")} disabled={busy || workflow.planStatus === "APPROVED_FOR_DEMO"}><Icon name="check"/>Approve for demo</button><button onClick={onReplan} disabled={busy}><Icon name="chart"/>Replan stressed forecast</button><button onClick={onCsv} disabled={busy}><Icon name="download"/>Export backend CSV</button></div></>}{workflow.message && <p className="workflow-message">{workflow.message}</p>}</section>; }
function WorkflowStep({ icon, label, value }: { icon: string; label: string; value: string }) { const complete = !["Pending", "Not created", "Not persisted", "offline"].includes(value); return <div className={complete ? "complete" : ""}><span><Icon name={icon} size={15}/></span><small>{label}</small><strong>{value}</strong></div>; }
function Comparison({ label, baseline, optimized, suffix = "" }: { label: string; baseline?: number; optimized?: number; suffix?: string }) { return <article><p>{label}</p><span><small>Baseline</small><strong>{baseline == null ? "—" : `${Math.round(baseline * 100) / 100}${suffix}`}</strong></span><i>→</i><span><small>Optimized</small><strong>{optimized == null ? "—" : `${Math.round(optimized * 100) / 100}${suffix}`}</strong></span></article>; }
function NoPlan({ onRun }: { onRun: () => void }) { return <section className="no-plan card"><span><Icon name="layers" size={26}/></span><h2>No active planning run</h2><p>Generate a schedule from Overview first. The result will remain available while you move between every workspace.</p><button onClick={onRun}><Icon name="play"/>Go to Overview</button></section>; }
function JointBlocksPage({ result }: { result: ScheduleResponse }) { return <section className="blocks-page"><div className="blocks-summary"><Metric icon="layers" label="Joint blocks" value={result.blocks.length} note="Coordinated possessions" color="orange"/><Metric icon="calendar" label="Work packages" value={result.blocks.reduce((sum, block) => sum + block.task_ids.length, 0)} note="Tasks inside blocks" color="indigo"/><Metric icon="clock" label="Total occupation" value={`${result.blocks.reduce((sum, block) => sum + Math.round((new Date(block.end_time).getTime() - new Date(block.start_time).getTime()) / 60000), 0)}m`} note="Combined block time" color="blue"/></div><div className="block-register card"><div className="card-heading"><div><p className="section-kicker">Coordinated possessions</p><h2>Active joint block register</h2><p>Each block preserves its individual departmental work packages.</p></div><span className="assurance-badge verified"><Icon name="check"/>Advisory plan</span></div><div className="block-list">{result.blocks.map((block, index) => { const entries = result.schedule_entries.filter((entry) => block.task_ids.includes(entry.task_id)); const minutes = Math.round((new Date(block.end_time).getTime() - new Date(block.start_time).getTime()) / 60000); return <article key={block.block_id}><div className="block-index"><span>JB</span><strong>{String(index + 1).padStart(2, "0")}</strong></div><div className="block-main"><div><code>{block.block_id}</code><h3>{block.section} · {block.line}</h3><p><Icon name="calendar" size={14}/>{formatTime(block.start_time)} – {shortTime(block.end_time)}<span>·</span>{minutes} minutes</p></div><div className="package-row">{entries.map((entry) => <span className={`package-chip ${deptClass(entry.department)}`} key={entry.task_id}><i/>{entry.task_id}<small>{entry.department}</small></span>)}</div></div><div className="coordination-value"><strong>{block.task_ids.length}</strong><small>work<br/>packages</small></div></article>; })}</div></div></section>; }
function ConfigurationPage({ active, scenario }: { active: boolean; scenario: string }) { if (!active) return null; return <section className="configuration-page"><div className="config-grid"><article className="card config-card"><span className="config-icon indigo"><Icon name="settings"/></span><div><p className="section-kicker">Optimization engine</p><h2>CP-SAT scheduling</h2><p>Deterministic constraint optimization with a ten-second maximum solve time and explainable priority scoring.</p><dl><div><dt>Execution</dt><dd>Local only</dd></div><div><dt>Schedule generation</dt><dd>OR-Tools CP-SAT</dd></div><div><dt>Independent validation</dt><dd>Enabled</dd></div><div><dt>Operational authority</dt><dd>Advisory only</dd></div></dl></div></article><article className="card config-card"><span className="config-icon orange"><Icon name="calendar"/></span><div><p className="section-kicker">Active setup</p><h2>Scenario configuration</h2><p>The selected scenario changes synthetic inputs without changing the planning rules.</p><dl><div><dt>Current scenario</dt><dd>{scenarios.find((item) => item.value === scenario)?.label}</dd></div><div><dt>Data source</dt><dd>Synthetic CSV fixtures</dd></div><div><dt>Departments</dt><dd>Engineering · S&amp;T · TRD</dd></div><div><dt>Plan export</dt><dd>JSON</dd></div></dl></div></article></div><div className="card scenario-catalog"><div className="card-heading"><div><p className="section-kicker">Demonstration catalog</p><h2>Available planning scenarios</h2><p>Purpose-built cases for validating planning behavior and explanations.</p></div></div><div className="scenario-grid">{scenarios.map((item) => <article className={item.value === scenario ? "selected" : ""} key={item.value}><span><Icon name={item.value === "base" ? "check" : "alert"}/></span><div><strong>{item.label}</strong><p>{item.hint}</p><code>{item.value}</code></div></article>)}</div></div></section>; }
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
function Requirement({ active, children }: { active: boolean; children: ReactNode }) { return <span className={active ? "active" : ""}><Icon name={active ? "check" : "alert"} size={13}/>{children}</span>; }
function IssueList({ items, warning = false }: { items: ValidationIssue[]; warning?: boolean }) { return <div className={`issue-list ${warning ? "warning" : ""}`}>{items.map((item, index) => <article key={`${item.code}-${index}`}><Icon name="alert"/><div><strong>{item.code.replaceAll("_", " ")}</strong><p>{item.message}</p></div></article>)}</div>; }
