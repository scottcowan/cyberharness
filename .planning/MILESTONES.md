---
gsd_milestones_version: 1.0
current_milestone: v1.0
last_updated: 2026-07-08
---

# Milestones: cyberharness

## Completed Milestones

*(None yet — v1.0 in progress)*

---

## v1.0 — Client Harness ← CURRENT

**Goal:** Build the Cyberdeck client harness end-to-end — local-first, offline-capable, conversation-persistent, with a benchmarked model selection and a TUI optimized for an ultrawide Cyberdeck display.

**Phases:** 6 (Phases 1–6)
**Requirements:** 21 (CONF, SESS, ROUT, MODL, TUI, QUEU)
**Status:** Planning

**What ships:**
- Python + Textual TUI with chat pane + artifact side surface
- Connectivity probe (online/offline detection)
- Model router → local Ollama / LM Studio only
- Session persistence — continuous conversation, atomic writes, crash-safe, resumable
- Model evaluation suite — ~12 candidate models for Jetson Nano 8GB (SWE-bench subset + custom evals)
- All Local / Wait for Online mode
- Queue manager stub (envelopes written; drain deferred to v1.1)

**What's deferred:**
- Same-network server
- Dynamic tool surface / ACP
- Workflow engine
- GSD phase hooks

---

## v1.1 — Same-Network Server

**Goal:** A Python FastAPI server running on the home network that the Cyberdeck client discovers via mDNS, provisions workspaces on, and connects to for cloud-model access and workspace context.

**Connection:** mDNS/Bonjour local discovery + HTTPS (self-signed cert); Tailscale as fallback/alternative for remote access.

**What ships:**

### Server Core
- FastAPI + uvicorn server installable on a home Linux machine via `uv`
- mDNS advertisement so the Cyberdeck client auto-discovers it on the LAN
- HTTPS with self-signed cert (trust-on-first-connect); configurable external cert
- Auth: shared secret / token in config; no OAuth

### Workspace Provisioning
- **Project/intent object model:** projects are first-class objects; each project contains named intents (observe, develop, hotfix, review) — the TUI workspace picker is two-level: project → intent
- **Project config** (YAML, server-side): repo (bare clone), knowledge base, base CLAUDE.md, base image, SSH keys, MCP config, default secrets, named intents
- **Intent** carries: human-readable description, permission level, path scope, git push patterns, model class, additional CLAUDE.md layers, additional secrets
- TUI provisioning flow: pick project → pick intent → harness provisions sysbox-runc container → session starts with right model, CLAUDE.md, and scope already configured
- **Bare clone + worktrees:** repos stored as bare clones; worktrees added per branch on demand, declared per intent
- **Permission model (least-privilege):** readonly | write | admin; write intents declare scope paths and branch patterns; admin requires explicit TUI approval
- Optional networking tools in workspace containers: Tailscale, AWS CLI, gh CLI
- `POST /workspaces` with `{project, intent}` → provisions container; `GET /projects` → lists projects with available intents

### Secret Store
- Node2-local secret store: SQLite + Fernet encryption (Python `cryptography` library)
- Master key lives outside the server container (node2 env var), injected at server container start
- Secrets tagged with minimum permission level — readonly workspaces only receive `readonly`-tagged secrets at provision time; write credentials never flow into readonly workspaces
- `cyberharness-secrets` CLI on node2: add, rotate, list, delete secrets; never exposes plaintext over the network
- Secrets injected as environment variables into workspace containers at provision time — never written to container filesystem

### OpenAI-Compatible Relay
- Server exposes an OpenAI-compatible endpoint (`/v1/chat/completions`) that proxies to cloud providers (OpenAI, Anthropic)
- Auth keys live on the server, not the Cyberdeck — client never holds cloud API keys
- Queue drain activates: client's QueueManager POSTs envelopes to server; server executes against cloud models; SSE stream back to client

### File & Diff Surface
- `GET /workspaces/{id}/files` — directory tree (excludes .env, secrets)
- `GET /workspaces/{id}/files/{path}` — file contents
- `GET /workspaces/{id}/diff` — git diff output (diff-so-fancy compatible)
- TUI artifact surface renders file tree and diffs received from server

### Knowledge Graph
- Server runs graphify over connected codebases on workspace creation and on demand
- `GET /workspaces/{id}/graph` — returns graph data; TUI surfaces it in the artifact panel

### CLAUDE.md & Meta-Harness Config
- Workspace CLAUDE.md is a **composition** of multiple files concatenated in order — repo conventions first, workspace-specific runbooks and scope constraints after; later files override on conflict
- Example: `[/workspace/repo/CLAUDE.md, /workspace/.workspace/HOTFIX.md]` — the hotfix file adds runbooks ("fix dropped connection bug"), scope constraints ("push only to hotfix/*"), and risk profile without duplicating the repo conventions
- cyberharness server config maps each meta-harness (Cursor, Claude Code, etc.) to the composed CLAUDE.md — each harness reads it at its native config path
- `knowledge/wiki/` (mirrors package structure) and `knowledge/refs/` (ingested external docs) are part of every workspace; served via `GET /workspaces/{id}/knowledge/`

**Phases:** ~6 phases (Phases 7–12), continuing from v1.0
**Key dependencies:** v1.0 queue stub activates; relay client in client harness wires up

**Open decisions:**
- mDNS library choice for Python server (zeroconf vs python-mdns)
- Cert management UX (auto-generated vs Let's Encrypt for Tailscale domain)
- Workspace isolation model: **one container per workspace** (preferred — server is itself fully containerised, so nsjail-inside-container requires `--privileged` which negates container security; per-workspace containers via Docker-in-Docker or a sidecar container API is the correct pattern)
- Container runtime for workspace containers: Docker socket mounted into the server container, or a sidecar like `docker:dind`, or a rootless alternative (podman, sysbox-runc for better nested container support)
- Whether workspace containers share a base image with the server container or are independently built

---

## v1.2 — Dynamic Tool Surface + ACP

**Goal:** The local leader model's tool surface dynamically expands when a server is connected, scaled to what the connected model can handle based on capability evaluation. Remote agents are delegated work via ACP internally.

**Architecture principle:** Local model stays leader. Tools are offered — not forced. The harness evaluates the connected remote model's capability (context window, tool-use reliability, reasoning quality) and gates tool surface expansion accordingly.

**What ships:**

### Capability Evaluator
- On server connection, harness runs a lightweight capability eval against the remote model
- Eval dimensions: context window size, tool-use reliability (structured output), reasoning quality (small benchmark)
- Result: a capability tier (basic / standard / extended) stored and used to gate tool availability
- User can view the capability report and override the tier

### Expanded Tool Surface
- Tool registry: each tool tagged with **both** a minimum capability tier (model) AND a minimum workspace permission level — both gates must pass
- **Capability tier** (model): basic / standard / extended — determined by capability eval
- **Workspace permission** (authorization): readonly / write / admin — declared in workspace YAML config
- A model with extended capability in a readonly workspace still cannot write — authorization is independent of capability
- **Basic tier + readonly**: file read, workspace tree listing, git log/diff, run queries
- **Standard tier + write**: file write (within declared scope paths), git commit/push (within declared branch patterns), run tests
- **Extended tier + write**: arbitrary shell inside the workspace container, MCP tool calls
- **Extended tier + admin**: cross-workspace operations, provision/deprovision workspaces
- **Escalation flow**: a write-level action from a readonly workspace surfaces as a TUI confirmation — user approves a scoped, time-limited escalation token rather than re-provisioning the workspace; escalation is logged in the audit trail

### ACP Internal Delegation
- Local leader model can dispatch ACP tasks to remote agents on the server
- ACP used internally between harness components and server-side agents — not exposed as a user-facing protocol
- OpenAI-compatible interface remains the user-facing surface
- `POST /v1/agents/{agent_id}/tasks` — dispatch a task to a named remote agent
- Remote agent streams results back; local harness presents them in the artifact surface

### TUI Updates
- Tool surface indicator in status bar — shows active tier and available tools
- Capability report viewable from model selector
- Tool call events visible in artifact surface (not just chat pane)

**Phases:** ~5 phases (Phases 13–17)
**Key dependencies:** v1.1 server must be running; capability eval needs real remote model access

**Open decisions:**
- ACP spec version to target (track spec development)
- How to handle capability tier downgrade if model behavior degrades mid-session
- Tool call approval UX — auto-execute vs confirm-before-run for destructive tools

---

## v1.3 — Workflow Engine

**Goal:** Users define workflows as YAML configs (or Python classes) that describe a sequence of steps, the model class required at each step, and the conditions for advancing. The harness queues work by workflow type and waits for the right model to become available.

**What ships:**

### Workflow Definition
- YAML workflow schema: name, steps, model_class per step, conditions, on_complete
- Python escape hatch: workflows as classes with a `@workflow` decorator for complex logic
- Model class tags: `local-fast` (3B local), `local-quality` (7B local), `remote-sonnet` (balanced, default for execution), `remote-opus` (highest reasoning, for planning and verification), `remote-extended` (tool-capable tier)
- `~/.cyberharness/workflows/` directory for user-defined workflows

### Workflow Queue
- Work items tagged with required model class at enqueue time
- Queue manager matches items to available models — waits for the right class to come online
- Priority ordering: FIFO within a model class; user can promote items
- "Wait for [model class]" mode — harness notifies when the required model comes online

### Workflow TUI Surface
- Workflow queue visible in a side panel — item, model class required, status, estimated wait
- User can define, inspect, pause, resume, and cancel workflow items from the TUI
- Workflow run history stored in `~/.cyberharness/workflows/history/`

### Built-in Workflow Templates
- `gsd-discuss` — discuss phase template (local-fast model, readonly workspace)
- `gsd-plan` — plan phase template (remote-opus class, planning workspace — readonly)
- `gsd-execute` — execute phase template (remote-sonnet class, execute workspace — write, scoped)
- `gsd-verify` — verify phase template (remote-opus class, verify workspace — readonly)
- `gsd-hotfix` — 3-step hotfix workflow: plan (opus/readonly) → execute (sonnet/write-scoped) → verify (opus/readonly)
- `code-review` — review a diff (remote-opus, readonly)
- `summarise-session` — compress long session (local-quality)

### Cross-Workspace Workflows (Inter-Project Dependencies)
- Workspaces are project-scoped, not company-wide — each project gets its own isolated container, repo, CLAUDE.md, and secrets
- When projects have dependencies, workflows can span workspaces: a step declares `workspace: project-name` to target a specific project's workspace
- **Readonly cross-workspace steps** run silently — no extra approval needed (observer access)
- **Write cross-workspace steps** require `cross_workspace: true` declaration + explicit TUI confirmation before executing
- Step outputs flow between workspaces via `{{prev_output}}` and `{{steps.step-name.output}}` — the workflow runner handles the handoff
- Cross-workspace steps default to readonly even if the target workspace has write permission; write must be explicitly requested
- **ACP as the coordination layer:** each workspace exposes an ACP endpoint; the server registry makes workspaces discoverable to each other; cross-workspace dispatch goes through ACP rather than direct container exec
- Future: workspace addresses can include a server: `workspace: cyberharness-client@node2` — enables cross-server workflows

### Workspace-Model Pairing Pattern
Each workflow step declares both a model class and a workspace type — the two are independent trust gates:
- **Model class** controls capability (can it reason about this task?)
- **Workspace permission** controls authorization (is it allowed to act?)
- Opus-class for planning and verification (judgment); Sonnet-class for execution (throughput, cost)
- A Sonnet-class model in a write workspace still cannot exceed the workspace's declared scope
- An Opus-class model in a readonly workspace cannot mutate anything regardless of capability

**Phases:** ~5 phases (Phases 18–22)
**Key dependencies:** v1.2 dynamic tool surface + ACP delegation; model-class routing in the router

**Open decisions:**
- YAML schema version and validation approach
- How to handle workflow steps that span model class boundaries (local → remote mid-workflow)
- Workflow sharing / community templates

---

## v1.4 — GSD Phase Integration

**Goal:** All GSD workflow phases (discuss, spec, plan, execute, verify) route through the cyberharness, using the appropriate local or remote model, with sessions persistent across the phase lifecycle and context docs summarised before cloud handoff.

**What ships:**

### GSD Phase Hooks
- `phases/hooks.py` adapter — translates GSD phase invocations into harness `route()` calls
- Phase routing policy: discuss/spec/explore → local model; plan/execute/verify → remote model (queue if offline)
- Session created per phase; context persists across phases via `.planning/` context docs
- GSD slash commands available from the TUI: `/gsd-discuss`, `/gsd-plan`, etc.

### Context Doc Handoff
- Session summariser produces a structured context doc (Goal / Decisions / Open Questions / Constraints) at phase completion
- User confirms context doc before it is enqueued for cloud phase
- Context doc written to `.planning/<phase>/context.md` on completion
- Cloud phase session initialised with context doc as system context

### Phase Progress in TUI
- Phase lifecycle visible in the artifact surface: current phase, which model is handling it, session turn count
- Phase completion triggers context doc preview + confirm/edit UX before next phase
- Phase history browseable from the TUI

### CLAUDE.md Integration
- Server-side workspace includes CLAUDE.md; harness reads it and injects as system context for cloud phases
- Local discuss phases use a minimal system prompt; cloud phases get the full CLAUDE.md

**Phases:** ~4 phases (Phases 23–26)
**Key dependencies:** v1.3 workflow engine (phases are workflows); v1.1 server (cloud phases run server-side)

**Open decisions:**
- Whether GSD phase hooks call cyberharness via CLI or are embedded in the harness directly
- Handling multi-model phase sequences (discuss local → plan remote → execute remote) within one GSD session
- CLAUDE.md precedence: local vs server-side when both exist

---

## Future Considerations (No Milestone Yet)

- **Reticulum / LoRa mesh probe** — treat rnsh connection as a connectivity tier; low-bandwidth queued delivery only; needs real-hardware validation
- **Remote relay for internet access** — HTTPS relay for Cyberdeck use outside the home network; Tailscale may make this unnecessary
- **Meta-harness aggregation** — relay aggregating Cursor, Claude Code as backends; complex per-harness adapters
- **Multi-user / team mode** — shared workspace server; session handoff between users
- **Mobile companion** — lightweight status view for the queue; not a full client

---

*Milestones defined: 2026-07-08*
*Last updated: 2026-07-08 after initial milestone planning*
