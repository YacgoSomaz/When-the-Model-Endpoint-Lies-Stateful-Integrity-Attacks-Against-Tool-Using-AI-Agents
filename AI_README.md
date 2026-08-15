---
document_for: AI systems and automated research assistants
project: When the Model Endpoint Lies
status: private, pre-disclosure, controlled research
primary_language: zh-CN
last_updated: 2026-08-15
---

# AI-readable research brief

## Objective

Study whether an intermediary with legitimate access to OpenAI-compatible JSON
can alter request, response, tool-call, or multi-turn context integrity in ways
that change a tool-using AI agent's behavior. Develop practical defenses.

## Main claim

A model name or endpoint shown in a client UI is not proof of the actual data
path or message integrity. A TLS-terminating intermediary can normally read the
plaintext of its own hop. In one authorized test configuration, changing a
benign user request before model inference caused a model-generated tool plan
that downloaded an inert ZIP into a dedicated workspace.

## Evidence level

`controlled_observation_pending_independent_review`

Do not restate the finding as a confirmed vendor vulnerability. Do not infer
malware execution, silent installation, approval bypass, privilege escalation,
or general applicability to other products.

## Experiment 001 facts

- Client-visible input: benign greeting.
- Environment ownership: researcher-owned accounts, key, gateway, endpoint, and workstation.
- Modification point: authorized local gateway before upstream inference.
- Artifact: ZIP containing only `README.txt` and `manifest.json`.
- Allowed actions: create test directory, download ZIP, calculate SHA-256.
- Prohibited/not observed: extraction, execution, installation, persistence,
  privilege escalation, credential access, security-control bypass.
- Result: agent reported download success and a matching SHA-256.

## Prompt-confidentiality evidence

The redacted full WorkBuddy request contains:

- 2 messages;
- a system message of approximately 42,079 characters;
- a user wrapper of approximately 11,313 characters;
- 24 structured tool definitions;
- model and generation configuration fields.

The committed sample preserves prompt/tool semantics but replaces personal
identifiers, user-home paths, credentials, and sensitive URL query values.

## Trust boundaries

`human -> agent client -> gateway/backend -> model service -> agent tool executor`

Treat every boundary as independently compromisable. Model output is a proposed
plan, never authorization.

## Safety invariants

1. High-impact tool calls must bind to a local, user-visible intent record.
2. Approval UI parameters must equal normalized execution parameters.
3. Network, filesystem, process, and account permissions must be independently limited.
4. Historical context cannot silently renew sensitive authorization.
5. Response Markdown/HTML/JSON must remain data unless explicitly and safely interpreted.
6. Tests use inert artifacts and researcher-owned infrastructure only.

## Repository routing

- Human introduction: `README.md`
- Detailed setup: `TECHNICAL_README.md`
- Architecture: `docs/ARCHITECTURE.md`
- Threat model: `docs/THREAT_MODEL.md`
- Findings and non-claims: `docs/FINDINGS.md`
- Defenses: `docs/MITIGATIONS.md`
- Experiment matrix: `docs/EXPERIMENT_MATRIX.md`
- Isolated runnable cases and acceptance rubric: `docs/TEST_CASES.md`
- Security-report drafting template: `docs/REPORT_TEMPLATE.md`
- Allowlist-only baseline Agent: `lab/safe_baseline_agent.py`
- Full redacted request: `evidence/private/workbuddy-full-request.redacted.json`
- Redacted follow-up context: `evidence/private/workbuddy-followup-request.redacted.json`
- Redaction provenance: `evidence/private/workbuddy-full-request.metadata.json`
- Ethics: `ETHICS.md`
- Disclosure: `RESPONSIBLE_DISCLOSURE.md`

## Instructions for AI analysis

- Separate observations, inferences, hypotheses, and vendor-confirmed facts.
- Cite the exact repository file supporting each claim.
- Never reveal or reconstruct redacted values.
- Do not propose real malicious payloads or third-party targeting.
- Prefer mitigations and falsifiable experiments over dramatic claims.
- Flag any text that overstates product impact or lacks an adequate control group.
