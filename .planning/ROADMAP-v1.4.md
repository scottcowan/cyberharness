---
gsd_roadmap_version: 1.0
milestone: v1.4
milestone_name: GSD Phase Integration
granularity: standard
total_phases: 4
phase_range: 23–26
last_updated: 2026-07-08
---

# Roadmap: cyberharness v1.4 — GSD Phase Integration

**Goal:** All GSD workflow phases (discuss, spec, plan, execute, verify) route through the cyberharness — local model for offline phases, remote model for cloud phases, queue if offline. Sessions persist across the full phase lifecycle; context docs are summarised and confirmed before cloud handoff; CLAUDE.md is injected from the server-side workspace.

**Continues from:** v1.3 Phase 22

---

## Phases

- [ ] **Phase 23: GSD Phase Hooks** — Adapter layer translating GSD phase invocations into harness route() calls; phase routing policy
- [ ] **Phase 24: Context Doc Handoff** — Session summariser, user confirm/edit UX, context doc written to .planning/, injected as cloud system context
- [ ] **Phase 25: Phase Progress TUI** — Phase lifecycle in artifact surface, context doc preview, phase history browser
- [ ] **Phase 26: CLAUDE.md Integration & E2E** — Server-side CLAUDE.md injected into cloud phases; full GSD discuss→plan→execute loop verified

---

## Phase Details

### Phase 23: GSD Phase Hooks
**Goal:** GSD phase invocations (`/gsd-discuss`, `/gsd-plan`, etc.) are intercepted by the harness and routed to the correct local or remote model, with offline queueing for cloud phases.
**Depends on:** v1.3 complete
**Requirements:** GSD-01, GSD-02, GSD-04
**Success Criteria:**
  1. `phases/hooks.py` adapter translates GSD phase invocations into `router.route(phase, messages)` calls — GSD does not need to know about harness internals
  2. Phase routing policy enforced: `discuss`, `spec`, `explore` → local model (always available); `plan`, `execute`, `verify` → remote model via server relay
  3. If a cloud phase is invoked while offline, it is queued as a workflow item (`required_model_class: remote-standard`) and the user is notified: "Plan phase queued — will run when server is available"
  4. Each GSD phase gets its own session — session id, phase name, and start time recorded; prior phase's context doc is available as input
  5. GSD slash commands available from the harness TUI: `/gsd-discuss [N]`, `/gsd-plan [N]`, `/gsd-execute [N]`, `/gsd-verify [N]` — these invoke the hooks directly from the chat pane

### Phase 24: Context Doc Handoff
**Goal:** When a local phase (discuss, spec) completes, the session is summarised into a structured context doc; the user confirms or edits it before it is passed to the next (cloud) phase.
**Depends on:** Phase 23
**Requirements:** GSD-03, GSD-05, GSD-06
**Success Criteria:**
  1. On discuss/spec phase completion, the summariser produces a structured context doc: `## Phase Goal`, `## Key Decisions`, `## Open Questions`, `## Constraints`, `## Relevant Context`
  2. User is shown the context doc in the artifact surface and must confirm (or edit) before it is enqueued for the cloud phase — this step cannot be bypassed
  3. Confirmed context doc is written to `.planning/<phase>/context.md` in the active workspace
  4. Cloud phase session is initialised with the context doc as the system message — the raw discuss history is never sent to the cloud model
  5. If the user edits the context doc, the edited version (not the summarised version) is what gets sent — user's edits take precedence

### Phase 25: Phase Progress TUI
**Goal:** Users can see where they are in the GSD phase lifecycle, review prior phase outputs, and navigate between phases without leaving the TUI.
**Depends on:** Phase 24
**Requirements:** TUI-12, TUI-13, TUI-14
**Success Criteria:**
  1. Artifact surface shows the current phase lifecycle: phase name, which model is handling it, turn count, time elapsed
  2. On phase completion, context doc preview appears in the artifact surface before the user confirms handoff to the next phase
  3. User can browse phase history: list of completed phases with model used, turn count, context doc excerpt
  4. Phase transition (e.g., discuss complete → plan queued) is visible as a distinct event in both the chat pane and the artifact surface
  5. User can re-open a prior phase's context doc from the history view and copy or re-run it

### Phase 26: CLAUDE.md Integration & E2E
**Goal:** Cloud phases are initialised with the server-side CLAUDE.md injected as system context; the full GSD discuss→plan→execute loop runs end-to-end through the harness.
**Depends on:** Phase 25
**Requirements:** GSD-07, INTG-03
**Success Criteria:**
  1. Server-side workspace CLAUDE.md is fetched at the start of each cloud phase session and injected before the context doc in the system message
  2. If both a local and server-side CLAUDE.md exist, server-side takes precedence for cloud phases; local CLAUDE.md is used for local phases
  3. Full GSD loop verified end-to-end: `/gsd-discuss 1` (local) → context doc confirmed → `/gsd-plan 1` queued (remote) → drains through server relay → PLAN.md written to `.planning/` → `/gsd-execute 1` invoked
  4. The loop survives an offline interruption: plan phase queued while offline, drains on reconnect, execution continues
  5. All v1.0–v1.3 functionality is unaffected; a user not using GSD sees no change in behavior

---

## Ordering Rationale

- Phase 23 (hooks) before Phase 24 (context docs) — hooks must route phases before summarisation/handoff can be tested
- Phase 24 (context docs) before Phase 25 (TUI) — TUI surfaces the context doc preview produced by Phase 24
- Phase 26 (CLAUDE.md + E2E) last — CLAUDE.md injection is a configuration concern that wraps the full flow; E2E is the milestone acceptance test

---

## Full Milestone Arc Summary

| Milestone | Phases | Core capability |
|-----------|--------|----------------|
| v1.0 | 1–6 | Local harness: Ollama/LM Studio, sessions, bench, TUI |
| v1.1 | 7–12 | Same-network server: mDNS, workspaces, relay, files, graph |
| v1.2 | 13–17 | Dynamic tool surface: capability eval, tiered tools, ACP |
| v1.3 | 18–22 | Workflow engine: YAML/Python workflows, model-class queue |
| v1.4 | 23–26 | GSD integration: phase hooks, context doc handoff, CLAUDE.md |

**Total phases across all milestones:** 26

---

*Roadmap created: 2026-07-08*
