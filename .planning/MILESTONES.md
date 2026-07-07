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
- TUI workspace provisioning flow (GSD-style) — new workspace setup from the Cyberdeck
- Workspace config stored server-side: git repos/worktrees, .env/auth keys, SSH keys, CLAUDE.md, MCP config
- Optional networking tools in the workspace sandbox: Tailscale, AWS CLI, gh CLI
- `POST /workspaces` → provisions a new workspace; `GET /workspaces` → lists existing

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

**Phases:** ~6 phases (Phases 7–12), continuing from v1.0
**Key dependencies:** v1.0 queue stub activates; relay client in client harness wires up

**Open decisions:**
- mDNS library choice for Python server (zeroconf vs python-mdns)
- Cert management UX (auto-generated vs Let's Encrypt for Tailscale domain)
- Workspace isolation model (Docker vs venv vs bare directory)

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
- Tool registry: each tool tagged with minimum capability tier required
- **Basic tier** (always available): file read (workspace files only), workspace tree listing
- **Standard tier**: file write (workspace files), git status/diff/log, run tests
- **Extended tier**: arbitrary shell in workspace sandbox, MCP tool calls, multi-step plans
- Tool surface presented to the model reflects the evaluated tier; harness enforces boundaries

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
- Model class tags: `local-fast` (3B local), `local-quality` (7B local), `remote-standard`, `remote-extended`
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
- `gsd-discuss` — discuss phase template (local-fast model)
- `gsd-plan` — plan phase template (remote-standard model)
- `code-review` — review a diff (remote-standard)
- `summarise-session` — compress long session (local-quality)

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
