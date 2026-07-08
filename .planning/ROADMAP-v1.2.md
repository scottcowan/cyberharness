---
gsd_roadmap_version: 1.0
milestone: v1.2
milestone_name: Dynamic Tool Surface + ACP
granularity: standard
total_phases: 5
phase_range: 13–17
last_updated: 2026-07-08
---

# Roadmap: cyberharness v1.2 — Dynamic Tool Surface + ACP

**Goal:** The local leader model's tool surface expands dynamically when a server-connected remote model is available, scaled to what that model can demonstrably handle. Remote agents are delegated work via ACP internally.

**Architecture principle:** Local model stays leader. Tools are offered based on evaluated capability — not assumed. Harness enforces tier boundaries in code, not convention.

**Continues from:** v1.1 Phase 12

---

## Phases

- [ ] **Phase 13: Tool Registry** — Define and enforce the tiered tool surface; Ollama bug guards baked in
- [ ] **Phase 14: Capability Evaluator** — Evaluate remote models on connection; assign and store capability tier
- [ ] **Phase 15: Dynamic Dispatch** — Router expands tool surface based on active tier; tier enforced at call time
- [ ] **Phase 16: ACP Internal Delegation** — Local leader dispatches tasks to named server-side agents via ACP
- [ ] **Phase 17: TUI Tool Surface** — Tool tier indicator, capability report, tool call events in artifact surface

---

## Phase Details

### Phase 13: Tool Registry
**Goal:** A centralized tool registry defines every tool with its minimum capability tier, validates schemas at registration, and enforces Ollama parser bug guards at the definition layer.
**Depends on:** v1.1 complete
**Requirements:** TOOL-01, TOOL-02, TOOL-03
**Success Criteria:**
  1. Tool registry validates all tool schemas at startup — a tool with a parameter named `name` is rejected with a clear error (Ollama bug guard)
  2. Each tool is tagged with a minimum capability tier (`basic`, `standard`, `extended`); `get_tools_for_tier(tier)` returns the correct filtered list
  3. OllamaClient always injects `think: false` when any tools are present in the request — verified by unit test
  4. Tool response validator rejects malformed tool calls (missing function name, malformed arguments) before execution — a bad parse never silently proceeds
  5. Minimum Ollama version check (≥ 0.30.12) runs at startup; warning surfaced if below

### Phase 14: Capability Evaluator
**Goal:** When a remote model becomes available (server connected), the harness automatically evaluates it across three dimensions and assigns a capability tier that gates tool access.
**Depends on:** Phase 13
**Requirements:** CAP-01, CAP-02, CAP-03
**Success Criteria:**
  1. On server connection, capability eval runs automatically against the remote model — no user action required
  2. Eval covers three dimensions: context window size (from model metadata), tool-use reliability (structured output round-trip), reasoning quality (small benchmark prompt with expected answer)
  3. Eval result is stored in `~/.cyberharness/bench/<model_id>.capability.json` and reused until model version changes
  4. User can view the full capability report from the TUI and manually override the assigned tier
  5. Eval completes in under 30 seconds for any model; progress shown in TUI during eval

### Phase 15: Dynamic Dispatch
**Goal:** The router presents the correct tool surface to each model based on its tier, enforces boundaries at call time, and degrades gracefully if a model exceeds its tier.
**Depends on:** Phase 14
**Requirements:** TOOL-04, TOOL-05, ROUT-06
**Success Criteria:**
  1. Router passes only the tools permitted for the active model's tier in every request — never passes extended-tier tools to a basic-tier model
  2. If a model attempts to call a tool outside its tier (e.g., via prompt injection), the harness rejects the call and surfaces a clear error rather than executing
  3. Destructive tools (file write, shell execution) require explicit user confirmation before execution — auto-execute is off by default, configurable
  4. If a model's tool call behavior degrades mid-session (repeated parse failures), harness automatically downgrades its tier and notifies the user
  5. All Local mode bypasses tier checks — local model keeps its minimal tool surface regardless

### Phase 16: ACP Internal Delegation
**Goal:** The local leader model can dispatch named tasks to server-side agents via ACP, receive streamed results, and present them in the artifact surface — without the user needing to know ACP exists.
**Depends on:** Phase 15
**Requirements:** ACP-01, ACP-02, ACP-03
**Success Criteria:**
  1. `POST /v1/agents/{agent_id}/tasks` dispatches a task to a named server-side agent and returns an SSE stream of results
  2. Local leader model can trigger an ACP delegation via a tool call (`delegate_to_agent`) — the harness translates this to an ACP request transparently
  3. ACP task results stream into the artifact surface alongside the main conversation — clearly attributed to the remote agent
  4. If the server is offline when a delegation is attempted, the task is queued like any other cloud work and drains on reconnect
  5. ACP is internal only — the user-facing interface remains OpenAI-compatible throughout; ACP is never exposed in the TUI as a concept

### Phase 17: TUI Tool Surface
**Goal:** Users can see which tools are available, what tier they're on, and what tool calls the model is making — all in the TUI without leaving the chat flow.
**Depends on:** Phase 16
**Requirements:** TUI-06, TUI-07, TUI-08
**Success Criteria:**
  1. Status bar shows active capability tier and a count of available tools (e.g., `tier:standard  12 tools`)
  2. Tool call events appear in the artifact surface as they happen — tool name, arguments, result — not buried in the chat pane
  3. User can open the capability report from the model selector; report shows eval scores, assigned tier, and override control
  4. Confirmation prompt appears before destructive tool calls (file write, shell) — prompt shows the exact call about to execute; user approves or rejects

---

## Ordering Rationale

- Phase 13 (registry + guards) before Phase 14 (eval) — eval exercises the tool round-trip; guards must be in place first
- Phase 14 (eval) before Phase 15 (dispatch) — dispatch uses the tier assigned by eval
- Phase 15 (dispatch) before Phase 16 (ACP) — ACP delegation is an extended-tier capability; tier enforcement must exist first
- Phase 17 (TUI) last — surfaces what the previous phases built; keeps TUI as a consumer throughout

---

*Roadmap created: 2026-07-08*
