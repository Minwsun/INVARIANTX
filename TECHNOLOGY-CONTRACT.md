# INVARIANT Technology Contract v2

Status: **Frozen**  
Effective date: **2026-08-12**

## North Star

> Agents are free to change HOW they achieve the goal, but INVARIANT prevents them from changing WHAT the human actually wanted.

INVARIANT is a runtime layer that preserves, verifies, and repairs human intent across autonomous multi-agent execution. Logistics is a demo use case, not the product boundary.

## Mandatory Stack

| Area | Technology |
| --- | --- |
| Languages | Python + TypeScript |
| Default AI model | `gemini-3.5-flash-lite` |
| Escalation AI model | `gemini-3.5-flash` |
| Agent framework | Google ADK 2.x |
| Orchestration | ADK Graph Workflow |
| Communication | Typed Events / JSON |
| Contract | Immutable Pydantic `IntentContract` |
| Policy | Deterministic Python first; Gemini semantic fallback |
| Tools | ADK Function Tools; all side effects gated |
| State | ADK Session State |
| Persistence | Firestore |
| Backend | FastAPI |
| Frontend | Next.js + TypeScript |
| Graph UI | React Flow / XYFlow |
| Realtime | Server-Sent Events (SSE) |
| Google Cloud infrastructure | Firestore |
| Compute hosting | Render Free |
| Tests | pytest |
| Backend runtime | Render Native Python |
| Frontend hosting | Render Static Site |
| Deployment | Render Blueprint + GitHub |
| Container | None |

## Runtime Rules

1. The runtime uses one Intent Compiler and four logical agents: Planner, Worker, Repair, and Validator.
2. Agents exchange typed JSON objects through runtime-managed events and state. Agent-to-agent prose is prohibited.
3. The Intent Contract is immutable. Agents have read-only access. A user-authorized change creates a new version.
4. Every material delegation passes the Delegation Gate.
5. Every side-effecting tool call passes the Action Gate.
6. Deterministic Python checks run before any semantic model check.
7. Gemini is used only when semantics cannot be resolved deterministically.
8. Repair output is never trusted implicitly; every repair is checked again.
9. Missing contract data, stale approval, gate failure, or altered tool arguments fail closed.
10. Large data belongs in Firestore or artifacts, not prompts or session state.

## Model Budget

- Flash-Lite is always attempted before Flash.
- Normal run target: at most 3 LLM calls.
- Absolute run limit: at most 5 LLM calls.
- Semantic-call input target: fewer than 1,000 tokens.
- Semantic-call output target: fewer than 150 tokens.
- Each call records model, role, input tokens, output tokens, latency, cache status, confidence, and escalation reason.
- Reaching the call limit blocks optional reasoning and returns the safest valid terminal result.

## MVP Deployment Boundary

```text
Browser
   |
   v
Render
   |
   +-- FastAPI
   +-- ADK Runtime
   +-- INVARIANT Runtime
   |
   +-- Gemini API
   +-- Firestore
```

The MVP is one Render backend service plus one Render frontend service. Firestore remains the required Google Cloud infrastructure. It does not use Kubernetes, Pub/Sub, Redis, SQL databases, vector databases, message brokers, or additional agent frameworks.

## Prohibited Additions

Do not add LangGraph, CrewAI, AutoGen, LangChain Agents, OpenAI Agents SDK, non-Gemini model providers, MongoDB, PostgreSQL, Redis, Pinecone, RabbitMQ, Kafka, GKE, or extra microservices without an approved Technology Contract revision.

## Change Control

Changing a frozen choice requires an Architecture Decision Record containing:

1. The concrete technical limitation.
2. Evidence that the current stack cannot meet the requirement.
3. The smallest proposed change.
4. Dependency, security, cost, and migration impact.
5. Rollback steps.

An approved change increments this contract version. Convenience, preference, and speculative scale are not sufficient reasons.
