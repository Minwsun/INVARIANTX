# Security Policy

## Scope

INVARIANTX is an experimental intent-integrity runtime. It reduces agent drift; it does not replace authorization, IAM, sandboxing, human approval, or domain-specific safety controls.

## Security Boundaries

- Intent contracts are immutable to agents.
- Every side-effecting tool call must pass the deterministic action gate.
- Semantic model verdicts never bypass deterministic constraints.
- Firestore is server-only; browser rules deny direct access.
- Gemini and Google Cloud credentials use Render secrets.
- Render authenticates to Firestore with a least-privilege service account.
- Typed events form the audit trail; secrets and raw credentials must never enter events.

## Deployment Requirements

- Never commit `.env` files, API keys, service-account JSON, or generated credentials.
- Restrict backend CORS to the deployed frontend origin.
- Grant the Render service account only `roles/datastore.user`.
- Rotate and revoke service-account keys after exposure or team changes.
- Keep `apply_plan` and future destructive tools gated and idempotent where possible.
- Review Firestore retention and personal-data handling before real workloads.

## Reporting

Do not open a public issue for an exploitable vulnerability. Report privately to the repository owner through GitHub Security Advisories.

Include affected commit, reproduction steps, impact, and suggested mitigation. No guaranteed response SLA currently exists.
