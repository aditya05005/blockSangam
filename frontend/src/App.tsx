import { useEffect, useMemo, useState } from "react";

type ValidationIssue = {
  code: string;
  message: string;
  task_ids?: string[];
  candidate_ids?: string[];
  block_id?: string | null;
};

type ScheduleEntry = {
  candidate_id: string;
  task_id: string;
  department: string;
  section: string;
  line: string;
  task_type: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  mandatory: boolean;
  priority: number;
  priority_band: string;
  resource_ids: string[];
  slot_id: string;
  latest_finish: string;
  requires_traffic_block: boolean;
  requires_power_isolation: boolean;
  requires_snt_disconnection: boolean;
};

type Unscheduled = {
  task_id: string;
  department: string;
  criticality: number;
  due_date: string;
  reason_code: string;
  explanation: string;
};

type ScheduleResponse = {
  status: string;
  validation_status: string;
  summary: {
    tasks_considered: number;
    tasks_scheduled: number;
    candidates_generated: number;
    candidates_selected: number;
    joint_blocks: number;
  };
  solver: {
    status: string;
    message: string;
    objective_value: number;
    solve_time_seconds: number;
    unscheduled_mandatory_task_ids: string[];
  };
  schedule_entries: ScheduleEntry[];
  unscheduled: Unscheduled[];
  blocks: { block_id: string; section: string; line: string; start_time: string; end_time: string; task_ids: string[] }[];
  validation: { errors: ValidationIssue[]; warnings: ValidationIssue[] };
  advisory: string;
};

const emptyResult: ScheduleResponse | null = null;

const scenarioOptions = [
  ["base", "Base synthetic forecast"],
  ["missing_corridor", "Missing corridor capacity"],
  ["resource_unavailable", "Resource unavailable"],
  ["locked_commitment", "Locked commitment conflict"],
  ["stressed_goods", "Stressed goods forecast"],
  ["competing_maintenance", "Competing maintenance"],
  ["corridor_closure", "Corridor closure"],
] as const;

type ScenarioOptions = {
  corridor_slots: { id: string; label: string }[];
  resources: { id: string; label: string }[];
  corridors: { section: string; line: string; label: string }[];
};

function formatTime(value: string) {
  return new Date(value).toLocaleString([], { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function App() {
  const [scenario, setScenario] = useState("base");
  const [result, setResult] = useState<ScheduleResponse | null>(emptyResult);
  const [selected, setSelected] = useState<ScheduleEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [simulation, setSimulation] = useState<any>(null);
  const [options, setOptions] = useState<ScenarioOptions>({ corridor_slots: [], resources: [], corridors: [] });
  const [removeSlot, setRemoveSlot] = useState("");
  const [unavailableResource, setUnavailableResource] = useState("");
  const [goodsForecast, setGoodsForecast] = useState<"base" | "stressed">("base");
  const [closureEnabled, setClosureEnabled] = useState(false);
  const [closure, setClosure] = useState({ section: "B-C", line: "UP", start_time: "2026-08-28T02:00", end_time: "2026-08-28T04:00" });
  const [taskEnabled, setTaskEnabled] = useState(false);
  const [task, setTask] = useState({ task_id: "SCN-NEW-001", department: "ENGINEERING", section: "B-C", line: "UP", task_type: "Additional Maintenance", duration_minutes: 30, earliest_start: "2026-08-28T02:00", latest_finish: "2026-08-28T04:00" });

  useEffect(() => {
    fetch("/api/scenario-options")
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Scenario inputs are unavailable. Restart the backend.")))
      .then(setOptions)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Scenario inputs are unavailable."));
  }, []);

  async function generateSchedule() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario, max_solve_time: 10 }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail?.message ?? body.detail ?? "The scheduling request failed.");
      setResult(body);
      setSelected(body.schedule_entries[0] ?? null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The scheduling request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runSimulation() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/scenarios/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          max_solve_time: 10,
          goods_forecast: goodsForecast,
          remove_corridor_slot_ids: removeSlot ? [removeSlot] : [],
          unavailable_resource_ids: unavailableResource ? [unavailableResource] : [],
          corridor_closure: closureEnabled ? closure : null,
          add_optional_task: taskEnabled ? task : null,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail?.message ?? body.detail ?? "The simulation request failed.");
      setSimulation(body);
      setResult(body.scenario_result);
      setSelected(body.scenario_result.schedule_entries[0] ?? null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The simulation request failed.");
    } finally {
      setBusy(false);
    }
  }

  function downloadJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `blocksangam-${scenario}-schedule.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  const timeline = useMemo(() => {
    if (!result?.schedule_entries.length) return null;
    const starts = result.schedule_entries.map((item) => new Date(item.start_time).getTime());
    const ends = result.schedule_entries.map((item) => new Date(item.end_time).getTime());
    return { start: Math.min(...starts), end: Math.max(...ends) };
  }, [result]);

  const activeChanges = [
    removeSlot && `Remove ${removeSlot}`,
    unavailableResource && `Unavailable ${unavailableResource}`,
    goodsForecast === "stressed" && "Use stressed goods forecast",
    closureEnabled && `Close ${closure.section} ${closure.line}`,
    taskEnabled && `Add ${task.task_id}`,
  ].filter(Boolean) as string[];

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">RAILWAY MAINTENANCE PLANNING</p>
          <h1>BlockSangam</h1>
          <p className="subtitle">Integrated Railway Block Planning</p>
        </div>
        <div className="advisory">SIH prototype · advisory only<br />not an operational block grant</div>
      </header>

      <section className="control-panel panel">
        <div>
          <label htmlFor="scenario">Saved test scenario</label>
          <select id="scenario" value={scenario} onChange={(event) => setScenario(event.target.value)} disabled={busy}>
            {scenarioOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <button className="primary" onClick={generateSchedule} disabled={busy}>{busy ? "Solving…" : "Generate Schedule"}</button>
        <span className="muted">Configure changes below to simulate</span>
        <button className="secondary" onClick={downloadJson} disabled={!result}>Export JSON</button>
      </section>

      <section className="what-if panel">
        <div className="what-if-header"><div><p className="eyebrow">PLANNING EXPERIMENT</p><h2>What-If Simulation</h2><p>Test a change against the current plan without altering the base dataset.</p></div><button className="secondary" onClick={generateSchedule} disabled={busy}>View base plan</button></div>
        <div className="simulation-steps"><span><b>1</b> Current plan<br /><small>Base synthetic snapshot</small></span><span><b>2</b> Scenario changes<br /><small>Choose any combination</small></span><span><b>3</b> Constraint check<br /><small>Pipeline + Phase 8 validation</small></span></div>
        <div className="scenario-heading"><strong>Scenario changes</strong><span>{activeChanges.length ? `${activeChanges.length} selected` : "No changes selected"}</span></div>
        <div className="what-if-grid">
          <label>Remove corridor slot<select value={removeSlot} onChange={(event) => setRemoveSlot(event.target.value)} disabled={busy}><option value="">No slot removed</option>{options.corridor_slots.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          <label>Make resource unavailable<select value={unavailableResource} onChange={(event) => setUnavailableResource(event.target.value)} disabled={busy}><option value="">No resource removed</option>{options.resources.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          <label>Goods demand<select value={goodsForecast} onChange={(event) => setGoodsForecast(event.target.value as "base" | "stressed")} disabled={busy}><option value="base">Base forecast</option><option value="stressed">Stressed forecast (existing data)</option></select></label>
        </div>
        <div className="selected-changes">{activeChanges.length ? activeChanges.map((change) => <span key={change}>{change}</span>) : <span className="empty-change">Select a change to start the experiment</span>}</div>
        <div className="change-toggle"><label><input type="checkbox" checked={closureEnabled} onChange={(event) => setClosureEnabled(event.target.checked)} /> Block corridor</label>{closureEnabled && <div className="what-if-grid compact"><label>Corridor<select value={`${closure.section}|${closure.line}`} onChange={(event) => { const [section, line] = event.target.value.split("|"); setClosure({ ...closure, section, line }); }}>{options.corridors.map((item) => <option key={`${item.section}-${item.line}`} value={`${item.section}|${item.line}`}>{item.label}</option>)}</select></label><label>Start<input type="datetime-local" value={closure.start_time} onChange={(event) => setClosure({ ...closure, start_time: event.target.value })} /></label><label>End<input type="datetime-local" value={closure.end_time} onChange={(event) => setClosure({ ...closure, end_time: event.target.value })} /></label></div>}</div>
        <div className="change-toggle"><label><input type="checkbox" checked={taskEnabled} onChange={(event) => setTaskEnabled(event.target.checked)} /> Add optional maintenance task</label>{taskEnabled && <div className="what-if-grid compact"><label>Task ID<input value={task.task_id} onChange={(event) => setTask({ ...task, task_id: event.target.value })} /></label><label>Department<select value={task.department} onChange={(event) => setTask({ ...task, department: event.target.value })}><option>ENGINEERING</option><option>SNT</option><option>TRD</option></select></label><label>Corridor<select value={`${task.section}|${task.line}`} onChange={(event) => { const [section, line] = event.target.value.split("|"); setTask({ ...task, section, line }); }}>{options.corridors.map((item) => <option key={`${item.section}-${item.line}`} value={`${item.section}|${item.line}`}>{item.label}</option>)}</select></label><label>Task type<input value={task.task_type} onChange={(event) => setTask({ ...task, task_type: event.target.value })} /></label><label>Duration (min)<input type="number" min="1" value={task.duration_minutes} onChange={(event) => setTask({ ...task, duration_minutes: Number(event.target.value) })} /></label><label>Earliest start<input type="datetime-local" value={task.earliest_start} onChange={(event) => setTask({ ...task, earliest_start: event.target.value })} /></label><label>Latest finish<input type="datetime-local" value={task.latest_finish} onChange={(event) => setTask({ ...task, latest_finish: event.target.value })} /></label></div>}</div>
        <div className="what-if-actions"><button className="primary" onClick={runSimulation} disabled={busy}>{busy ? "Simulating…" : "Simulate"}</button><button className="secondary" onClick={downloadJson} disabled={!result}>Export result JSON</button></div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      {simulation && <section className="panel comparison-panel"><div className="section-heading"><div><p className="eyebrow">PHASE 12</p><h2>Base vs What-If</h2></div><span className="muted">{simulation.scenario_result.scenario.name}</span></div><div className="comparison-grid"><div><strong>BASE</strong><p>{simulation.comparison.base.status}</p><span>{simulation.comparison.base.tasks_scheduled} tasks Â· {simulation.comparison.base.joint_blocks} blocks</span></div><div><strong>WHAT-IF</strong><p>{simulation.comparison.scenario.status}</p><span>{simulation.comparison.scenario.tasks_scheduled} tasks Â· {simulation.comparison.scenario.joint_blocks} blocks</span></div></div><div className="impact-line"><strong>Affected tasks:</strong> {simulation.comparison.impact.tasks_moved.concat(simulation.comparison.impact.newly_unscheduled).join(", ") || "None"}<span> Â· Candidates {simulation.comparison.impact.candidate_delta >= 0 ? "+" : ""}{simulation.comparison.impact.candidate_delta}</span></div></section>}

      {!result && !busy && <section className="empty panel"><span className="signal">01</span><div><h2>Ready for review</h2><p>Choose a synthetic forecast and generate a constraint-checked schedule from the existing CP-SAT pipeline.</p></div></section>}
      {busy && <section className="empty panel"><div className="spinner" /><div><h2>Running BlockSangam</h2><p>Generating candidates, solving constraints, composing blocks, and validating the result.</p></div></section>}

      {result && <>
        <section className="summary-grid">
          <SummaryCard label="Tasks" value={`${result.summary.tasks_scheduled}/${result.summary.tasks_considered}`} detail="scheduled / considered" />
          <SummaryCard label="Candidates" value={`${result.summary.candidates_selected}/${result.summary.candidates_generated}`} detail="selected / generated" />
          <SummaryCard label="Joint blocks" value={result.summary.joint_blocks} detail="coordinated windows" />
          <SummaryCard label="Validation" value={result.validation_status} detail={`${result.validation.errors.length} hard issues`} tone={result.validation_status === "VALID" ? "good" : "bad"} />
        </section>

        <section className="content-grid">
          <div className="main-column">
            <section className="panel">
              <div className="section-heading"><div><p className="eyebrow">PROPOSED WORK</p><h2>Schedule entries</h2></div><span className={`status-pill ${result.validation_status === "VALID" ? "good" : "bad"}`}>{result.status}</span></div>
              <div className="table-wrap"><table><thead><tr><th>Task</th><th>Department</th><th>Corridor</th><th>Window</th><th>Priority</th><th>Status</th></tr></thead><tbody>
                {result.schedule_entries.map((entry) => <tr key={entry.candidate_id} className={selected?.candidate_id === entry.candidate_id ? "selected-row" : ""} onClick={() => setSelected(entry)}><td><strong>{entry.task_id}</strong><small>{entry.task_type}</small></td><td><span className={`dept ${entry.department.toLowerCase()}`}>{entry.department}</span></td><td>{entry.section} · {entry.line}</td><td>{formatTime(entry.start_time)}<small>to {formatTime(entry.end_time)}</small></td><td><strong>{entry.priority.toFixed(3)}</strong><small>{entry.priority_band}</small></td><td><span className="scheduled-dot" /> Scheduled</td></tr>)}
              </tbody></table></div>
              {!!result.unscheduled.length && <div className="unscheduled"><h3>Unscheduled explanations</h3>{result.unscheduled.map((item) => <div className="unscheduled-item" key={item.task_id}><strong>{item.task_id}</strong><span>{item.reason_code}</span><p>{item.explanation}</p></div>)}</div>}
            </section>

            <section className="panel">
              <div className="section-heading"><div><p className="eyebrow">TIME AND CORRIDOR</p><h2>Planning timeline</h2></div><span className="muted">{result.blocks.length} blocks</span></div>
              {timeline && <div className="timeline"><div className="timeline-axis"><span>{formatTime(new Date(timeline.start).toISOString())}</span><span>{formatTime(new Date(timeline.end).toISOString())}</span></div>{result.schedule_entries.map((entry) => { const left = ((new Date(entry.start_time).getTime() - timeline.start) / (timeline.end - timeline.start || 1)) * 100; const width = ((new Date(entry.end_time).getTime() - new Date(entry.start_time).getTime()) / (timeline.end - timeline.start || 1)) * 100; return <button key={`bar-${entry.candidate_id}`} className={`timeline-row ${entry.department.toLowerCase()}`} onClick={() => setSelected(entry)}><span className="timeline-label">{entry.section} {entry.line}<small>{entry.task_id}</small></span><span className="track"><span className="bar" style={{ left: `${left}%`, width: `${Math.max(width, 2)}%` }}>{entry.task_id}</span></span></button>; })}</div>}
            </section>
          </div>

          <aside className="side-column">
            <section className="panel detail-panel"><p className="eyebrow">TASK DETAIL</p>{selected ? <><h2>{selected.task_id}</h2><p className="detail-title">{selected.task_type}</p><dl><Detail label="Department" value={selected.department} /><Detail label="Corridor" value={`${selected.section} · ${selected.line}`} /><Detail label="Scheduled" value={`${formatTime(selected.start_time)} – ${formatTime(selected.end_time)}`} /><Detail label="Duration" value={`${selected.duration_minutes} minutes`} /><Detail label="Priority" value={`${selected.priority.toFixed(3)} · ${selected.priority_band}`} /><Detail label="Resources" value={selected.resource_ids.join(", ") || "None listed"} /><Detail label="Corridor slot" value={selected.slot_id} /><Detail label="Due" value={formatTime(selected.latest_finish)} /></dl><div className="requirements"><p>Requirements</p><span className={selected.requires_traffic_block ? "active" : ""}>Traffic block</span><span className={selected.requires_power_isolation ? "active" : ""}>Power isolation</span><span className={selected.requires_snt_disconnection ? "active" : ""}>S&T disconnection</span></div></> : <p className="muted">Select a schedule entry to inspect its actual task and assignment details.</p>}</section>
            <section className="panel validation-panel"><div className="section-heading"><div><p className="eyebrow">PHASE 8</p><h2>Independent validation</h2></div><span className={`checkmark ${result.validation_status === "VALID" ? "good" : "bad"}`}>{result.validation_status === "VALID" ? "✓" : "!"}</span></div>{result.validation.errors.length === 0 ? <p className="validation-good">No hard-constraint violations reported by the independent validator.</p> : <div>{result.validation.errors.map((issue, index) => <div className="issue" key={`${issue.code}-${index}`}><strong>{issue.code}</strong><p>{issue.message}</p></div>)}</div>}{result.validation.warnings.map((issue, index) => <div className="issue warning" key={`warning-${index}`}><strong>{issue.code}</strong><p>{issue.message}</p></div>)}</section>
            <section className="panel solver-panel"><p className="eyebrow">SOLVER</p><div className="solver-line"><span>Status</span><strong>{result.solver.status}</strong></div><div className="solver-line"><span>Runtime</span><strong>{result.solver.solve_time_seconds.toFixed(3)}s</strong></div><p className="solver-message">{result.solver.message}</p></section>
          </aside>
        </section>
      </>}
      <footer>BlockSangam · synthetic data · {result?.advisory ?? "Constraint-based maintenance review"}</footer>
    </main>
  );
}

function SummaryCard({ label, value, detail, tone = "" }: { label: string; value: string | number; detail: string; tone?: string }) {
  return <div className={`summary-card ${tone}`}><p>{label}</p><strong>{value}</strong><span>{detail}</span></div>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="detail-row"><dt>{label}</dt><dd>{value}</dd></div>;
}

export default App;
