"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { normalizeApiBase } from "@/lib/api-base.mjs";

const API_BASE = normalizeApiBase(
  process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_HOST,
);

const eventTypes = [
  "RUN_CREATED",
  "RUN_STARTED",
  "RUN_CANCEL_REQUESTED",
  "RUN_CANCELLED",
  "RUN_COMPLETED",
  "RUN_FAILED",
  "INTENT_COMPILED",
  "CONTRACT_REGISTERED",
  "TASK_PROPOSED",
  "DEMO_DRIFT_INJECTED",
  "ACTION_PROPOSED",
  "GATE_PASSED",
  "DRIFT_DETECTED",
  "ACTION_BLOCKED",
  "REPAIR_ACCEPTED",
  "TOOL_COMPLETED",
  "VALIDATION_COMPLETED",
  "MODEL_RETRY",
  "MODEL_FAILED",
  "POLICY_ESCALATED",
  "TOOL_TIMED_OUT",
  "RECEIPT_REJECTED",
] as const;

type EventType = (typeof eventTypes)[number];

type InvariantEvent = {
  event_id: string;
  sequence: number;
  type: EventType;
  timestamp: string;
  actor: string;
  payload: Record<string, unknown>;
};

type Contract = {
  id: string;
  version: number;
  objectives: Array<{ id: string; metric: string; target: number; unit: string }>;
  hard_constraints: Array<{ id: string; metric: string; operator: string }>;
  protected_entities: string[];
  forbidden_outcomes: string[];
};

type RunSnapshot = {
  run_id: string;
  status: string;
  repair_count: number;
  llm_call_count: number;
  scenario?: string;
  result?: {
    model_calls?: Array<{
      role: string;
      provider: string;
      model: string;
      attempt: number;
      outcome: string;
      input_tokens: number;
      output_tokens: number;
      latency_ms: number;
    }>;
  };
};

const graphNodes = [
  ["parse_request", "Intent Compiler", 20, 110],
  ["planner_agent", "Planner", 220, 110],
  ["check_delegation", "Delegation Gate", 420, 110],
  ["repair_task", "Repair", 420, 260],
  ["worker_agent", "Worker", 620, 110],
  ["check_action", "Action Gate", 820, 110],
  ["execute_tool", "Tool Executor", 1020, 110],
  ["validate_result", "Validator", 1220, 110],
] as const;

const graphEdges: Edge[] = [
  ["parse_request", "planner_agent"],
  ["planner_agent", "check_delegation"],
  ["check_delegation", "worker_agent"],
  ["check_delegation", "repair_task"],
  ["repair_task", "check_delegation"],
  ["worker_agent", "check_action"],
  ["check_action", "execute_tool"],
  ["execute_tool", "validate_result"],
].map(([source, target], index) => ({
  id: `edge-${index}`,
  source,
  target,
  animated: source === "repair_task" || target === "repair_task",
  markerEnd: { type: MarkerType.ArrowClosed },
  style: { stroke: "#61718c", strokeWidth: 1.5 },
}));

function eventTone(type: EventType) {
  if (["DRIFT_DETECTED", "ACTION_BLOCKED", "MODEL_FAILED", "TOOL_TIMED_OUT", "RECEIPT_REJECTED"].includes(type)) return "danger";
  if (type === "REPAIR_ACCEPTED" || type === "MODEL_RETRY" || type === "POLICY_ESCALATED") return "repair";
  if (type === "RUN_COMPLETED" || type === "GATE_PASSED") return "success";
  return "neutral";
}

export default function Home() {
  const [goal, setGoal] = useState(
    "Reduce logistics cost by 15% without delaying medical orders.",
  );
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [events, setEvents] = useState<InvariantEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const sourceRef = useRef<EventSource | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cursorRef = useRef<string | null>(null);
  const failuresRef = useRef(0);

  useEffect(() => () => disconnectEvents(), []);

  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("run_id");
    if (!runId) return;
    void refreshRun(runId)
      .then(() => connectEvents(runId))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load run"))
      .finally(() => setLoading(false));
    // Deep-link hydration runs once; reconnect owns subsequent lifecycle updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeActors = useMemo(
    () => new Set(events.map((event) => event.actor)),
    [events],
  );
  const latestActor = events.at(-1)?.actor;
  const hasDrift = events.some((event) => event.type === "DRIFT_DETECTED");
  const repaired = events.some((event) => event.type === "REPAIR_ACCEPTED");

  const nodes: Node[] = useMemo(
    () =>
      graphNodes.map(([id, label, x, y]) => ({
        id,
        position: { x, y },
        data: { label },
        className:
          latestActor === id
            ? "flow-node flow-node--active"
            : activeActors.has(id)
              ? "flow-node flow-node--complete"
              : "flow-node",
      })),
    [activeActors, latestActor],
  );

  const integrity = run?.status === "BLOCKED" ? 0 : repaired ? 100 : hasDrift ? 72 : 100;
  const modelCalls = run?.result?.model_calls ?? [];
  const inputTokens = modelCalls.reduce((sum, call) => sum + call.input_tokens, 0);
  const outputTokens = modelCalls.reduce((sum, call) => sum + call.output_tokens, 0);

  async function refreshRun(runId: string) {
    const [runResponse, contractResponse] = await Promise.all([
      fetch(`${API_BASE}/runs/${runId}`),
      fetch(`${API_BASE}/runs/${runId}/contract`),
    ]);
    if (!runResponse.ok) throw new Error("Run not found");
    const snapshot = await runResponse.json() as RunSnapshot;
    setRun(snapshot);
    if (contractResponse.ok) setContract(await contractResponse.json());
    return snapshot;
  }

  function connectEvents(runId: string) {
    sourceRef.current?.close();
    if (reconnectRef.current) clearTimeout(reconnectRef.current);
    const cursor = cursorRef.current;
    const query = cursor ? `?after_event_id=${encodeURIComponent(cursor)}` : "";
    const source = new EventSource(`${API_BASE}/runs/${runId}/events${query}`);
    sourceRef.current = source;

    const receive = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as InvariantEvent;
      setEvents((current) =>
        current.some((item) => item.event_id === event.event_id)
          ? current
          : [...current, event],
      );
      cursorRef.current = event.event_id;
      failuresRef.current = 0;
      setError("");
      if (["RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED"].includes(event.type)) {
        disconnectEvents();
        void refreshRun(runId);
      }
    };

    eventTypes.forEach((type) => source.addEventListener(type, receive as EventListener));
    source.onerror = () => {
      source.close();
      failuresRef.current += 1;
      setError("Event stream disconnected. Recovering from persisted events.");
      if (failuresRef.current >= 3 && !pollingRef.current) {
        pollingRef.current = setInterval(() => {
          void refreshRun(runId).then((snapshot) => {
            if (["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"].includes(snapshot.status)) {
              disconnectEvents();
            }
          });
        }, 5000);
      }
      const delay = [1000, 2000, 4000, 8000, 15000][
        Math.min(failuresRef.current - 1, 4)
      ];
      reconnectRef.current = setTimeout(() => connectEvents(runId), delay);
    };
  }

  function disconnectEvents() {
    sourceRef.current?.close();
    sourceRef.current = null;
    if (reconnectRef.current) clearTimeout(reconnectRef.current);
    reconnectRef.current = null;
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = null;
  }

  async function startRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setEvents([]);
    setContract(null);
    setRun(null);
    disconnectEvents();
    cursorRef.current = null;
    failuresRef.current = 0;
    try {
      const response = await fetch(`${API_BASE}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Unable to create run");
      setRun(body);
      window.history.replaceState(null, "", `?run_id=${encodeURIComponent(body.run_id)}`);
      await refreshRun(body.run_id);
      connectEvents(body.run_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create run");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">IX</span>
          <div>
            <p className="eyebrow">Intent integrity runtime</p>
            <h1>INVARIANT</h1>
          </div>
        </div>
        <div className="integrity" aria-live="polite">
          <span>Integrity</span>
          <strong>{integrity}%</strong>
          <i style={{ width: `${integrity}%` }} />
        </div>
      </header>

      <form className="goal-bar" onSubmit={startRun}>
        <label htmlFor="goal">Human goal</label>
        <input
          id="goal"
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !goal.trim()}>
          {loading ? "Starting…" : "Run workflow"}
        </button>
      </form>

      {error && <p className="error" role="alert">{error}</p>}

      <section className="metrics" aria-label="Run metrics">
        <Metric label="Status" value={run?.status ?? "IDLE"} />
        <Metric label="LLM calls" value={run?.llm_call_count ?? 0} />
        <Metric label="Input tokens" value={inputTokens} />
        <Metric label="Output tokens" value={outputTokens} />
        <Metric label="Drifts" value={events.filter((item) => item.type === "DRIFT_DETECTED").length} />
        <Metric label="Repairs" value={run?.repair_count ?? 0} />
      </section>

      <section className="model-routing" aria-label="Model routing">
        <ModelRoute role="Intent Compiler" model="Gemini 3.5 Flash-Lite" />
        <ModelRoute role="Planner" model="Gemma 4 31B" />
        <ModelRoute role="Worker" model="Gemma 4 31B" />
        <ModelRoute role="Safety Authority" model="Deterministic Python" />
      </section>

      <section className="workspace">
        <article className="panel graph-panel">
          <PanelTitle kicker="Execution" title="Agent workflow" detail={run?.run_id ?? "No active run"} />
          <div className="graph-canvas">
            <ReactFlow nodes={nodes} edges={graphEdges} fitView minZoom={0.55} maxZoom={1.4}>
              <Background color="#26344a" gap={24} size={1} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        </article>

        <aside className="panel contract-panel">
          <PanelTitle kicker="Source of truth" title="Intent Contract" detail={contract ? `${contract.id} · v${contract.version}` : "Waiting"} />
          {contract ? (
            <div className="contract-groups">
              <ContractGroup title="Objectives" items={contract.objectives.map((item) => `${item.metric} · target ${item.unit === "percent" ? item.target : item.target * 100}%`)} />
              <ContractGroup title="Hard invariants" items={contract.hard_constraints.map((item) => `${item.id} · ${item.metric}`)} />
              <ContractGroup title="Protected" items={contract.protected_entities} />
              <ContractGroup title="Forbidden" items={contract.forbidden_outcomes} danger />
            </div>
          ) : (
            <p className="empty">Start a run to compile and inspect intent.</p>
          )}
        </aside>
      </section>

      <section className="panel timeline-panel">
        <PanelTitle kicker="Audit trail" title="Event timeline" detail={`${events.length} events`} />
        <div className="timeline" aria-live="polite">
          {events.length === 0 ? (
            <p className="empty">Runtime events will appear here.</p>
          ) : (
            [...events].reverse().map((event) => (
              <div className={`timeline-row timeline-row--${eventTone(event.type)}`} key={event.event_id}>
                <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
                <span className="event-sequence">#{event.sequence}</span>
                <strong>{event.type.replaceAll("_", " ")}</strong>
                <span>{event.actor}</span>
              </div>
            ))
          )}
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function ModelRoute({ role, model }: { role: string; model: string }) {
  return <div className="model-route"><span>{role}</span><strong>{model}</strong></div>;
}

function PanelTitle({ kicker, title, detail }: { kicker: string; title: string; detail: string }) {
  return <header className="panel-title"><div><p>{kicker}</p><h2>{title}</h2></div><span>{detail}</span></header>;
}

function ContractGroup({ title, items, danger = false }: { title: string; items: string[]; danger?: boolean }) {
  return <section className="contract-group"><h3>{title}</h3>{items.length ? items.map((item) => <p className={danger ? "constraint constraint--danger" : "constraint"} key={item}><span>✓</span>{item}</p>) : <p className="empty">None</p>}</section>;
}
