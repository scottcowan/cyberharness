---
gsd_roadmap_version: 1.0
milestone: v1.3
milestone_name: Workflow Engine
granularity: standard
total_phases: 5
phase_range: 18–22
last_updated: 2026-07-08
---

# Roadmap: cyberharness v1.3 — Workflow Engine

**Goal:** Users define workflows — as YAML configs or Python classes — that describe sequences of steps, the model class required at each step, and the conditions for advancing. The harness queues work by model class and waits for the right model to become available.

**Continues from:** v1.2 Phase 17

---

## Phases

- [ ] **Phase 18: Workflow Schema & Loader** — YAML schema, Python decorator escape hatch, validation, built-in templates
- [ ] **Phase 19: Model Class Routing** — Router understands model classes; queue manager matches items to available classes
- [ ] **Phase 20: Workflow Runner** — Executes workflow steps in order; handles cross-class boundaries; manages state between steps
- [ ] **Phase 21: Workflow TUI Surface** — Queue panel, workflow inspector, pause/resume/cancel, run history
- [ ] **Phase 22: Built-in Templates & E2E** — Ship `gsd-discuss`, `gsd-plan`, `code-review`, `summarise-session`; full workflow verified end-to-end

---

## Phase Details

### Phase 18: Workflow Schema & Loader
**Goal:** Users can write a YAML workflow file and have the harness load, validate, and register it at startup — or define workflows in Python for complex logic.
**Depends on:** v1.2 complete
**Requirements:** WF-01, WF-02, WF-03
**Success Criteria:**
  1. A valid YAML workflow file in `~/.cyberharness/workflows/` is loaded, validated against the pydantic schema, and registered at startup — a malformed file fails fast with a clear error and the line number
  2. YAML schema supports: `name`, `description`, `steps[]` (each with `prompt`, `model_class`, `tools[]`, `condition`, `on_complete`), `on_error`
  3. Python escape hatch: a class decorated with `@workflow` in `~/.cyberharness/workflows/*.py` is loaded and registered alongside YAML workflows; both appear in the same registry
  4. Model class tags validated at load time: `local-fast`, `local-quality`, `remote-sonnet`, `remote-opus`, `remote-extended` are the valid values; unknown tags are rejected
  5. `cyberharness workflows list` shows all registered workflows with name, model classes required, and step count

### Phase 19: Model Class Routing
**Goal:** The router and queue manager understand model classes — not just individual model names — so work can be queued for "any remote-standard model" rather than a specific model.
**Depends on:** Phase 18
**Requirements:** WF-04, ROUT-07, ROUT-08
**Success Criteria:**
  1. Config maps model class tags to concrete models: `local-fast = "llama3.2:3b-q4"`, `remote-sonnet = "claude-sonnet-5"`, `remote-opus = "claude-opus-4-8"` (via server relay)
  2. Queue items carry a `required_model_class` field; queue manager dispatches to the first available model of that class
  3. If the required model class is unavailable (e.g., server offline for `remote-sonnet`), the item waits — harness notifies user: "Waiting for remote-standard model — connect to server to proceed"
  4. User can list what model classes are currently available from the TUI status bar (e.g., `local-fast ✓  local-quality ✓  remote-standard ✗`)
  5. "Wait for [model class]" mode: harness can be told to hold and notify when a specific class becomes available, rather than erroring

### Phase 20: Workflow Runner
**Goal:** The workflow runner executes steps in order, handles model class transitions between steps, persists state so a workflow survives restarts, and surfaces results from each step before the next begins.
**Depends on:** Phase 19
**Requirements:** WF-05, WF-06, WF-07
**Success Criteria:**
  1. Workflow runner executes steps sequentially; each step's output is available to the next step's prompt as `{{prev_output}}`
  2. A workflow that spans model classes (e.g., step 1 `local-fast` → step 2 `remote-sonnet`) transitions correctly — step 1 result is summarised and passed as context to step 2
  3. Workflow state is persisted after every step completion (`~/.cyberharness/workflows/history/<run_id>.json`); a harness restart resumes from the last completed step
  4. Step `condition` field: if a Python expression or model-evaluated condition is false, the runner skips to `on_complete` or a named step
  5. A failed step (model error, tool failure, timeout) triggers `on_error` behavior: retry N times, skip, or abort — never silently proceeds

### Phase 21: Workflow TUI Surface
**Goal:** Users can see all queued and running workflows, inspect step state, and control (pause, resume, cancel) any workflow from the TUI.
**Depends on:** Phase 20
**Requirements:** TUI-09, TUI-10, TUI-11
**Success Criteria:**
  1. Workflow queue panel shows each item: workflow name, current step, required model class, status (waiting / running / complete / failed), time queued
  2. User can select a workflow item to inspect its full state: all step outputs so far, current prompt, next model class needed
  3. User can pause, resume, or cancel any in-progress or waiting workflow from the panel — cancellation is confirmed before executing
  4. Completed workflow runs are visible in history; user can re-run a workflow from history with the same inputs
  5. "Waiting for model class" items are visually distinguished from actively running items; ETA shown where estimable

### Phase 22: Built-in Templates & E2E
**Goal:** Ship four built-in workflow templates; verify a multi-step, multi-class workflow runs end-to-end.
**Depends on:** Phase 21
**Requirements:** WF-08, WF-09
**Success Criteria:**
  1. `gsd-discuss` workflow template ships and runs: one step, `local-fast`, runs a GSD-style discussion session and writes output to `.planning/`
  2. `gsd-plan` workflow template: one step, `remote-sonnet`, takes a context doc as input and produces a PLAN.md
  3. `code-review` workflow template: one step, `remote-sonnet`, reviews a git diff and produces a structured review
  4. `summarise-session` workflow template: one step, `local-quality`, compresses a long session into a context doc
  5. Full multi-step workflow verified: `gsd-discuss` (local-fast) → `gsd-plan` (remote-standard) — runs end-to-end across model classes; context doc handoff correct; result lands in `.planning/`

---

## Ordering Rationale

- Phase 18 (schema) before Phase 19 (class routing) — routing config references model class tags defined in the schema
- Phase 19 (class routing) before Phase 20 (runner) — runner dispatches steps using the class router
- Phase 20 (runner) before Phase 21 (TUI) — TUI surfaces runner state; state must exist first
- Phase 22 (templates + E2E) last — validates everything with real workflow content; templates are the acceptance test

---

*Roadmap created: 2026-07-08*
