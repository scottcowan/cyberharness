---
gsd_roadmap_version: 1.0
milestone: v1.0
milestone_name: Client Harness
granularity: standard
total_phases: 6
total_requirements: 21
coverage: 21/21
last_updated: 2026-07-08
---

# Roadmap: cyberharness v1.0 — Client Harness

**Goal:** Deliver the Cyberdeck client harness end-to-end — foundation, session persistence, local model router, benchmark suite, TUI, and a queue stub — so a user can hold a durable conversation with a local leader model on a Jetson Nano 8GB.

**Granularity:** Standard (6 phases derived from requirement categories + dependency ordering).

## Phases

- [ ] **Phase 1: Foundation & Scaffold** — Installable project, typed config, workspace directories, mode toggle
- [ ] **Phase 2: Session Manager** — Durable, resumable per-session conversation history
- [ ] **Phase 3: Router + Local Models** — Streaming turns to Ollama or LM Studio via a stateless router
- [ ] **Phase 4: Model Evaluation** — Bench candidate models on-device; store and surface results
- [ ] **Phase 5: TUI** — Chat + artifact surface, status bar, model selector, connectivity indicator
- [ ] **Phase 6: Queue Stub & Integration** — Queue envelope writer wired into the assembled harness

## Phase Details

### Phase 1: Foundation & Scaffold
**Goal**: A user on aarch64 Linux can install cyberharness with uv, and the harness boots into a validated config and initialized workspace.
**Depends on**: Nothing (first phase)
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-04
**Success Criteria** (what must be TRUE):
  1. User runs a single uv-based install command on aarch64 Linux and gets a working `cyberharness` entry point
  2. On first run, `~/.cyberharness/{sessions,queue,workspace,bench}/` are created and `config.toml` is loaded (env vars override; secrets never in TOML)
  3. A typo or missing required field in `config.toml` fails fast at startup with a clear pydantic error, not on first turn
  4. User can set mode (All Local / Wait for Online) in config and toggle it at runtime; the active mode is observable
**Plans**: TBD

### Phase 2: Session Manager
**Goal**: A user can hold a continuous, prolonged conversation with the harness whose history survives crashes, power loss, and restarts.
**Depends on**: Phase 1
**Requirements**: SESS-01, SESS-02, SESS-03
**Success Criteria** (what must be TRUE):
  1. Conversation history accumulates across the whole session (not reset per phase) and is retrievable in order
  2. After every turn, the on-disk session file is atomically replaced; killing the process mid-turn never leaves a corrupt or partial session
  3. On startup, if an in-progress session exists, the user is prompted to resume or start fresh, and their choice is honoured
  4. A second harness instance cannot corrupt a session that another instance owns (filelock enforced)
**Plans**: TBD

### Phase 3: Router + Local Models
**Goal**: Every conversation turn streams from a local model (Ollama or LM Studio) through a stateless router, with an explicitly minimal tool surface.
**Depends on**: Phase 2
**Requirements**: ROUT-01, ROUT-02, ROUT-03, ROUT-04, ROUT-05
**Success Criteria** (what must be TRUE):
  1. A connectivity probe runs on the configured interval and emits debounced connected/disconnected events to subscribers
  2. Every turn in v1.0 dispatches to a local backend; the relay path exists as a stub but is never invoked in normal use
  3. User can point the harness at a local Ollama instance and receive streaming tokens, with the model warmed via `keep_alive=-1`
  4. User can point the harness at a local LM Studio instance via a configurable OpenAI-compatible base URL and receive streaming tokens
  5. The local leader model's tool surface is explicit and minimal — no arbitrary shell, no arbitrary file I/O — enforced in code, not by convention
**Plans**: TBD

### Phase 4: Model Evaluation
**Goal**: A user can benchmark candidate Jetson Nano 8GB models and pick the active model informed by measured performance.
**Depends on**: Phase 3
**Requirements**: MODL-01, MODL-02, MODL-03, MODL-04
**Success Criteria** (what must be TRUE):
  1. User can list every available local model (Ollama + LM Studio) and select the active one at runtime
  2. `cyberharness bench <model>` runs and reports tokens/sec, estimated VRAM usage, and a quality score
  3. The bench suite covers the ~12 candidate models targeted at Jetson Nano 8GB (incl. Llama 3.2 3B Q4, Llama 3.1 8B Q4, Phi-3 mini 3.8B, Gemma 2 2B Q4, Mistral 7B Q3, Qwen 2.5 3B)
  4. Bench results are written to `~/.cyberharness/bench/` and are readable by the model selection surface
**Plans**: TBD

### Phase 5: TUI
**Goal**: A user on an ultrawide Cyberdeck display has a streaming chat interface with an artifact side surface, live status, and a model selector.
**Depends on**: Phase 4
**Requirements**: TUI-01, TUI-02, TUI-03, TUI-04, TUI-05
**Success Criteria** (what must be TRUE):
  1. User sees a streaming chat pane with scrollable full history; tokens render in real time without stalling the compositor
  2. An artifact side panel (ultrawide-optimized, A2A-style) slides in for diffs, code blocks, structured output, and model details
  3. Status bar always shows current model name, online/offline state, active mode (All Local / Wait for Online), and VRAM usage
  4. User can open a model selector and switch the active local model; the selector surfaces bench results where present
  5. Connectivity state is visually unambiguous at all times — online and offline are distinguishable at a glance
**Plans**: TBD
**UI hint**: yes

### Phase 6: Queue Stub & Integration
**Goal**: The queue directory exists and can hold well-formed envelopes, and the full v1.0 harness (foundation → session → router → bench → TUI → queue) is wired end-to-end.
**Depends on**: Phase 5
**Requirements**: QUEU-01
**Success Criteria** (what must be TRUE):
  1. On startup the queue manager ensures `~/.cyberharness/queue/` exists and writes well-formed `QueueEnvelope` files atomically
  2. Drain behaviour is intentionally inert in v1.0 — envelopes accumulate; no relay call is attempted; this is verifiable by inspection
  3. The assembled harness (install → configure → resume/start session → chat via local model → open artifact surface → switch model → write a queue envelope) runs end-to-end on a Jetson Nano 8GB without regressions from prior phases
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Scaffold | 0/0 | Not started | - |
| 2. Session Manager | 0/0 | Not started | - |
| 3. Router + Local Models | 0/0 | Not started | - |
| 4. Model Evaluation | 0/0 | Not started | - |
| 5. TUI | 0/0 | Not started | - |
| 6. Queue Stub & Integration | 0/0 | Not started | - |

## Coverage

- v1.0 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0

| Category | Requirements | Phase |
|----------|--------------|-------|
| Foundation & Configuration | CONF-01, CONF-02, CONF-03, CONF-04 | Phase 1 |
| Session & Conversation | SESS-01, SESS-02, SESS-03 | Phase 2 |
| Model Routing & Connectivity | ROUT-01, ROUT-02, ROUT-03, ROUT-04, ROUT-05 | Phase 3 |
| Model Selection & Evaluation | MODL-01, MODL-02, MODL-03, MODL-04 | Phase 4 |
| TUI | TUI-01, TUI-02, TUI-03, TUI-04, TUI-05 | Phase 5 |
| Queue (Stub) | QUEU-01 | Phase 6 |

## Ordering Rationale

- Phase 1 is prerequisite for everything (config, paths, install).
- Phase 2 precedes Phase 3: the router streams into a session it does not own — sessions must exist and be durable first.
- Phase 3 precedes Phase 4: `cyberharness bench` exercises the real local backends through the router.
- Phase 4 precedes Phase 5: the TUI's model selector surfaces bench results — the data must exist to render.
- Phase 5 comes last among user-facing work: TUI is a consumer of every core service; building it late means the core is already proven.
- Phase 6 (queue stub) is kept separate rather than merged into Phase 5 to preserve a clean integration/verification boundary for the assembled harness; it is small and could collapse into Phase 5 if execution shows it is trivial.

---
*Roadmap created: 2026-07-08*
