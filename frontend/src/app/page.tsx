"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Background, Edge, MarkerType, Node, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { normalizeApiBase } from "@/lib/api-base.mjs";

const API_BASE = normalizeApiBase(
  process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_HOST,
);
const TERMINAL = new Set(["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"]);

type Json = Record<string, unknown>;
type EventItem = {
  event_id: string;
  sequence: number;
  type: string;
  timestamp: string;
  actor: string;
  payload: Json;
};
type Contract = {
  id: string;
  version: number;
  objectives: Array<{ id: string; metric: string; target: number; unit: string }>;
  hard_constraints: Array<{ id: string; metric: string; operator: string }>;
  protected_entities: string[];
  forbidden_outcomes: string[];
};
type Validation = { verdict?: string; checks?: Array<{ category?: string; passed?: boolean; detail?: string }> };
type Receipt = {
  plan_id?: string;
  dataset_version?: string;
  before_metrics?: Record<string, number>;
  actual_metrics?: Record<string, number>;
  counts?: Record<string, number>;
  sla_violations?: number;
  capacity_violations?: number;
  evidence_source?: Json;
};
type FleetResult = { final_verdict?: string; receipt?: Receipt; validation?: Validation; repair_count?: number };
type Comparison = {
  same_environment?: boolean;
  dataset_version?: string;
  shared_drift?: Json;
  baseline?: FleetResult;
  invariant?: FleetResult;
  prevented_outcomes?: string[];
  restored_constraint_ids?: string[];
};
type RunSnapshot = {
  run_id: string;
  status: string;
  goal: string;
  repair_count: number;
  llm_call_count: number;
  scenario?: string;
  result?: { comparison?: Comparison; model_calls?: Array<Json> } & Json;
};

const graph = [
  ["intent_compiler", "Intent Compiler", 0, 40],
  ["planner_agent", "Planner", 190, 40],
  ["check_delegation", "Delegation Gate", 380, 40],
  ["repair_task", "Repair", 380, 180],
  ["worker_agent", "Worker", 570, 40],
  ["execute_tool", "Simulator", 760, 40],
  ["validate_result", "Final Validator", 950, 40],
] as const;
const edges: Edge[] = [
  ["intent_compiler", "planner_agent"], ["planner_agent", "check_delegation"],
  ["check_delegation", "worker_agent"], ["check_delegation", "repair_task"],
  ["repair_task", "check_delegation"], ["worker_agent", "execute_tool"],
  ["execute_tool", "validate_result"],
].map(([source, target], index) => ({
  id: `e${index}`, source, target,
  animated: source === "repair_task" || target === "repair_task",
  markerEnd: { type: MarkerType.ArrowClosed },
}));

const actorEvents: Record<string, string[]> = {
  intent_compiler: ["INTENT_COMPILED", "CONTRACT_REGISTERED"],
  planner_agent: ["TASK_PROPOSED", "DEMO_DRIFT_INJECTED"],
  check_delegation: ["DRIFT_DETECTED", "GATE_PASSED", "ACTION_BLOCKED"],
  repair_task: ["REPAIR_ACCEPTED"],
  worker_agent: ["ACTION_PROPOSED"],
  execute_tool: ["TOOL_COMPLETED", "TOOL_TIMED_OUT"],
  validate_result: ["VALIDATION_COMPLETED", "RECEIPT_REJECTED"],
};

export default function Home() {
  const [goal, setGoal] = useState("Reduce logistics cost by 15% without delaying medical orders.");
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [selected, setSelected] = useState<EventItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const source = useRef<EventSource | null>(null);
  const comparison = run?.result?.comparison;

  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("run_id");
    if (runId) void loadRun(runId, true);
    return () => source.current?.close();
    // Deep-link hydration intentionally runs once; SSE owns later updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadRun(runId: string, connect = false) {
    const response = await fetch(`${API_BASE}/runs/${runId}`);
    if (!response.ok) throw new Error(`Run load failed (${response.status})`);
    const snapshot: RunSnapshot = await response.json();
    setRun(snapshot);
    setGoal(snapshot.goal || goal);
    if (snapshot.status !== "CREATED") {
      const contractResponse = await fetch(`${API_BASE}/runs/${runId}/contract`);
      if (contractResponse.ok) setContract(await contractResponse.json());
    }
    if (connect && !TERMINAL.has(snapshot.status)) connectEvents(runId);
    return snapshot;
  }

  function connectEvents(runId: string) {
    source.current?.close();
    const stream = new EventSource(`${API_BASE}/runs/${runId}/events`);
    source.current = stream;
    stream.onmessage = (message) => consumeEvent(message.data, runId);
    for (const type of ["RUN_CREATED", "RUN_STARTED", "INTENT_COMPILED", "CONTRACT_REGISTERED", "TASK_PROPOSED", "DEMO_DRIFT_INJECTED", "DRIFT_DETECTED", "REPAIR_ACCEPTED", "GATE_PASSED", "ACTION_PROPOSED", "ACTION_REPAIRED", "TOOL_COMPLETED", "VALIDATION_COMPLETED", "RUN_COMPLETED", "RUN_FAILED", "ACTION_BLOCKED", "RECEIPT_REJECTED", "TOOL_TIMED_OUT"]) {
      stream.addEventListener(type, (message) => consumeEvent((message as MessageEvent).data, runId));
    }
  }

  function consumeEvent(raw: string, runId: string) {
    const item = JSON.parse(raw) as EventItem;
    setEvents((current) => current.some((event) => event.event_id === item.event_id) ? current : [...current, item]);
    if (item.type === "CONTRACT_REGISTERED") void fetch(`${API_BASE}/runs/${runId}/contract`).then((response) => response.json()).then(setContract);
    if (["RUN_COMPLETED", "RUN_FAILED"].includes(item.type)) {
      source.current?.close();
      void loadRun(runId);
    }
  }

  async function startCompare(event: FormEvent) {
    event.preventDefault();
    setLoading(true); setError(""); setRun(null); setContract(null); setEvents([]); setSelected(null);
    try {
      const response = await fetch(`${API_BASE}/runs/demo/compare/public`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(`Compare run rejected (${response.status})`);
      const snapshot: RunSnapshot = await response.json();
      setRun(snapshot);
      window.history.replaceState({}, "", `?run_id=${snapshot.run_id}`);
      connectEvents(snapshot.run_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start compare run");
    } finally { setLoading(false); }
  }

  const activeActors = useMemo(() => new Set(events.map((event) => event.actor)), [events]);
  const latestActor = events.at(-1)?.actor;
  const nodes: Node[] = graph.map(([id, label, x, y]) => ({
    id, position: { x, y }, data: { label },
    className: `flow-node ${activeActors.has(id) ? "flow-node--complete" : ""} ${latestActor === id ? "flow-node--active" : ""}`,
  }));

  function inspectActor(actor: string) {
    const allowed = actorEvents[actor] ?? [];
    const found = [...events].reverse().find((event) => allowed.includes(event.type));
    if (found) setSelected(found);
  }

  return (
    <main className="shell">
      <header className="hero">
        <div><p className="eyebrow">Intent integrity proof console</p><h1>What did INVARIANT prevent?</h1></div>
        <div className={`run-state run-state--${run?.status?.toLowerCase() ?? "idle"}`}>{run?.status ?? "READY"}</div>
      </header>

      <form className="intent" onSubmit={startCompare}>
        <div><span>Human intent</span><input value={goal} onChange={(event) => setGoal(event.target.value)} /></div>
        <button disabled={loading}>{loading ? "Starting…" : "Run live comparison"}</button>
      </form>
      {error && <p className="error">{error}</p>}

      <section className="comparison">
        <FleetCard title="Baseline Agent Fleet" tone="danger" fleet={comparison?.baseline} fallback="Ungated planner executes the cheapest plan." />
        <div className="versus">SAME INTENT<br /><strong>VS</strong><br />SAME DATASET</div>
        <FleetCard title="INVARIANT Fleet" tone="success" fleet={comparison?.invariant} fallback="Gate detects drift, repairs delegation, validates evidence." />
      </section>

      <section className="proof-strip">
        <Proof label="Shared corruption" value={comparison ? "MEDICAL_SLA omitted" : "Waiting for compare run"} ok={Boolean(comparison)} />
        <Proof label="Intervention" value={comparison ? `${run?.repair_count ?? 0} constraint restored` : "Gate → Repair → Recheck"} ok={Boolean(comparison)} />
        <Proof label="Prevented outcome" value={comparison?.prevented_outcomes?.join(", ") ?? "Medical orders delayed"} ok={Boolean(comparison)} />
        <Proof label="Final evidence" value={comparison?.invariant?.final_verdict ?? "Not evaluated"} ok={comparison?.invariant?.final_verdict === "INTENT_PRESERVED"} />
      </section>

      <section className="workspace">
        <article className="panel graph-panel">
          <PanelTitle kicker="How it intervened" title="Click any runtime node" detail={`${run?.llm_call_count ?? 0} LLM calls`} />
          <div className="graph-canvas"><ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => inspectActor(node.id)}><Background color="#26344a" gap={24} size={1} /></ReactFlow></div>
        </article>
        <aside className="panel inspector">
          <PanelTitle kicker="Evidence inspector" title={selected?.type.replaceAll("_", " ") ?? "Select a node or event"} detail={selected?.actor ?? "Typed JSON"} />
          {selected ? <Inspector event={selected} /> : <EvidenceSummary contract={contract} comparison={comparison} />}
        </aside>
      </section>

      <section className="panel timeline-panel">
        <PanelTitle kicker="Audit trail" title="Cause → intervention → evidence" detail={`${events.length} events`} />
        <div className="timeline">
          {[...events].reverse().map((event) => <button key={event.event_id} className={`timeline-row timeline-row--${tone(event.type)}`} onClick={() => setSelected(event)}><time>{new Date(event.timestamp).toLocaleTimeString()}</time><span>#{event.sequence}</span><strong>{event.type.replaceAll("_", " ")}</strong><span>{event.actor}</span></button>)}
          {!events.length && <p className="empty">Open a proof run or start a live comparison.</p>}
        </div>
      </section>
    </main>
  );
}

function FleetCard({ title, tone: cardTone, fleet, fallback }: { title: string; tone: string; fleet?: FleetResult; fallback: string }) {
  const receipt = fleet?.receipt;
  const before = receipt?.before_metrics ?? {};
  const after = receipt?.actual_metrics ?? {};
  return <article className={`fleet fleet--${cardTone}`}><header><span>{title}</span><strong>{fleet?.final_verdict ?? "AWAITING PROOF"}</strong></header><p>{fallback}</p><div className="metric-pair"><MetricValue label="Cost" before={before.logistics_cost} after={after.logistics_cost} /><MetricValue label="Medical delay" before={before.delivery_delay} after={after.delivery_delay} /></div><div className="fleet-footer"><span>SLA violations</span><strong>{receipt?.sla_violations ?? "—"}</strong><span>Plan</span><strong>{receipt?.plan_id ?? "—"}</strong></div></article>;
}
function MetricValue({ label, before, after }: { label: string; before?: number; after?: number }) { return <div><span>{label}</span><strong>{after ?? "—"}</strong><small>{before === undefined ? "No receipt" : `before ${before}`}</small></div>; }
function Proof({ label, value, ok }: { label: string; value: string; ok: boolean }) { return <div className={ok ? "proof proof--ok" : "proof"}><span>{label}</span><strong>{ok ? "✓ " : "· "}{value}</strong></div>; }
function PanelTitle({ kicker, title, detail }: { kicker: string; title: string; detail: string }) { return <header className="panel-title"><div><p>{kicker}</p><h2>{title}</h2></div><span>{detail}</span></header>; }
function EvidenceSummary({ contract, comparison }: { contract: Contract | null; comparison?: Comparison }) {
  const validation = comparison?.invariant?.validation;
  const checks = validation?.checks ?? [];
  return <div className="evidence-summary"><h3>Final contract validation</h3>{checks.length ? checks.map((check, index) => <p key={index} className={check.passed ? "check check--pass" : "check check--fail"}><b>{check.passed ? "✓" : "×"}</b><span>{check.category ?? "check"}<small>{check.detail}</small></span></p>) : <><p className="check"><b>·</b><span>{contract?.objectives.length ?? 0} objectives</span></p><p className="check"><b>·</b><span>{contract?.hard_constraints.length ?? 0} hard constraints</span></p><p className="check"><b>·</b><span>{contract?.protected_entities.length ?? 0} protected entities</span></p></>}<strong className="verdict">{validation?.verdict ?? "WAITING"}</strong></div>;
}
function Inspector({ event }: { event: EventItem }) { return <div className="inspector-body"><div className="event-meta"><span>Sequence #{event.sequence}</span><span>{new Date(event.timestamp).toLocaleString()}</span></div><pre>{JSON.stringify(event.payload, null, 2)}</pre></div>; }
function tone(type: string) { if (/DRIFT|BLOCK|FAILED|TIMEOUT|REJECTED/.test(type)) return "danger"; if (/REPAIR/.test(type)) return "repair"; if (/PASSED|COMPLETED/.test(type)) return "success"; return "neutral"; }
