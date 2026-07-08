# Requirements: cyberharness

**Defined:** 2026-07-08
**Core Value:** Context and work survive any connectivity transition — the local leader model orchestrates, sessions persist, and cloud work queues for when connectivity arrives.

## v1.0 Requirements

Requirements for initial release: local-first harness with Ollama/LM Studio support, persistent conversation, model evaluation, and a TUI with artifact surface. Remote relay and dynamic tool surface are v1.1.

### Foundation & Configuration

- [ ] **CONF-01**: User can scaffold and install the project via `uv` with a single command on aarch64 Linux
- [ ] **CONF-02**: User's config is loaded from `~/.cyberharness/config.toml` with env var override (secrets stay out of TOML)
- [ ] **CONF-03**: Workspace directory structure is defined and initialized on first run (`sessions/`, `queue/`, `workspace/`, `bench/`, `knowledge/wiki/`, `knowledge/refs/`)
- [ ] **CONF-04**: User can switch between All Local and Wait for Online mode from config and at runtime

### Session & Conversation

- [ ] **SESS-01**: User can hold a continuous, prolonged conversation with the local leader model — history persists across the full session, not just per-phase
- [ ] **SESS-02**: Session is written atomically to disk after every turn — crash or power loss does not corrupt or lose conversation history
- [ ] **SESS-03**: On startup, user is prompted to resume any in-progress session or start fresh

### Model Routing & Connectivity

- [ ] **ROUT-01**: Connectivity probe runs on a configurable interval and emits connected/disconnected events (debounced to prevent flap)
- [ ] **ROUT-02**: Router dispatches to local model (Ollama or LM Studio) for all turns in v1.0 — relay path is stubbed
- [ ] **ROUT-03**: User can connect to local Ollama instance with full streaming and model warm-up (`keep_alive=-1`)
- [ ] **ROUT-04**: User can connect to local LM Studio instance via configurable OpenAI-compatible base URL
- [ ] **ROUT-05**: Local leader model has a minimal, explicitly-defined tool surface — no arbitrary shell or file access

### Model Selection & Evaluation

- [ ] **MODL-01**: User can view all available local models (Ollama + LM Studio) and select the active model at runtime
- [ ] **MODL-02**: User can run `cyberharness bench <model>` to evaluate a model — measures tokens/sec, estimated VRAM usage, and quality score
- [ ] **MODL-03**: Benchmark evaluation suite covers ~12 candidate models for Jetson Nano 8GB (Llama 3.2 3B Q4, Llama 3.1 8B Q4, Phi-3 mini 3.8B, Gemma 2 2B Q4, Mistral 7B Q3, Qwen 2.5 3B, and others)
- [ ] **MODL-04**: Benchmark results are stored in `~/.cyberharness/bench/` and visible in the model selection UI

### TUI

- [ ] **TUI-01**: User sees a streaming chat interface with the local leader model — full conversation history scrollable, tokens stream in real time
- [ ] **TUI-02**: An artifact surface (side panel, ultrawide-optimized) slides in for diffs, code blocks, structured output, and model details — inspired by A2A UI pattern
- [ ] **TUI-03**: Status bar shows current model name, online/offline state, active mode (All Local / Wait for Online), and VRAM usage
- [ ] **TUI-04**: User can open a model selector to pick and switch the active local model; selector shows bench results where available
- [ ] **TUI-05**: Connectivity indicator provides a clear visual distinction between online and offline state at all times
- [ ] **TUI-06**: Wiki viewer in artifact surface — user can open a `knowledge/wiki/` page via chat command ("open the session manager page") or via navigation panel; renders markdown

### Queue (Stub)

- [ ] **QUEU-01**: Queue manager initializes `~/.cyberharness/queue/` and can write envelopes — drain behavior and relay connection activate in v1.1

## v2 Requirements

Deferred to future release.

### Remote Relay & Dynamic Tool Surface

- **RELC-01**: User can connect to a remote relay server via HTTPS — relay exposes an OpenAI-compatible endpoint
- **RELC-02**: Cloud phases (plan, execute, verify) route through the relay when online; queue if offline
- **RELC-03**: Remote model gets an expanded tool surface evaluated against its capability — harness dynamically adjusts tools based on connected model assessment
- **RELC-04**: ACP (Agent Communication Protocol) used to delegate work to remote agents

### Remote Workspace

- **WORK-01**: Remote sandbox workspace includes git repos/worktrees, auth keys, SSH, CLAUDE.md, MCP config
- **WORK-02**: TUI workspace provisioning flow — GSD-style new workspace setup on the remote server
- **WORK-03**: File browser — view sandbox files (excluding .env), diff view (diff-so-fancy style)
- **WORK-04**: Local workspace mirrors remote workspace structure; sync activates when relay connects
- **WORK-05**: Remote server runs graphify over connected codebases

### Knowledge Base

- **KNOW-01**: Wiki viewer in TUI artifact surface — navigate `knowledge/wiki/` (mirrors package structure) via chat command or direct navigation panel
- **KNOW-02**: Reference docs ingestion — fetch and store external docs (API specs, web pages) to `knowledge/refs/` for offline access
- **KNOW-03**: CLAUDE.md auto-injection — meta-harnesses (Cursor, Claude Code, etc.) configured to read the active workspace CLAUDE.md; cyberharness server config maps each harness to its path
- **KNOW-04**: Wiki creation flow — harness can scaffold a wiki page for any module from a template, pre-filled with the module's current structure

### GSD Integration

- **GSD-01**: GSD discuss and spec phases route to local leader model
- **GSD-02**: GSD plan, execute, verify phases route through relay; queue if offline
- **GSD-03**: Session summarisation before cloud handoff — context doc with user confirmation

## Out of Scope

| Feature | Reason |
|---------|--------|
| OAuth / user accounts | Single-user tool; no multi-tenancy needed |
| Mobile clients | Cyberdeck-first; ultrawide TUI assumes a real screen |
| Real-time sync to multiple connected clients | Single device per session |
| openai / anthropic SDK dependencies | Wire format is OpenAI-compatible; raw httpx is the design |
| SQLite session storage | JSON files are the design; no cross-session queries justify SQLite in v1.0 |
| Task queue frameworks (Celery, RQ) | 20-line watchfiles loop; no broker infrastructure |
| GPU telemetry in harness | Belongs in the cyberdeck hardware repo |
| Reticulum / LoRa probe tier | v1.x; needs real-hardware validation |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONF-01 | Phase 1 | Pending |
| CONF-02 | Phase 1 | Pending |
| CONF-03 | Phase 1 | Pending |
| CONF-04 | Phase 1 | Pending |
| SESS-01 | Phase 2 | Pending |
| SESS-02 | Phase 2 | Pending |
| SESS-03 | Phase 2 | Pending |
| ROUT-01 | Phase 3 | Pending |
| ROUT-02 | Phase 3 | Pending |
| ROUT-03 | Phase 3 | Pending |
| ROUT-04 | Phase 3 | Pending |
| ROUT-05 | Phase 3 | Pending |
| MODL-01 | Phase 4 | Pending |
| MODL-02 | Phase 4 | Pending |
| MODL-03 | Phase 4 | Pending |
| MODL-04 | Phase 4 | Pending |
| TUI-01 | Phase 5 | Pending |
| TUI-02 | Phase 5 | Pending |
| TUI-03 | Phase 5 | Pending |
| TUI-04 | Phase 5 | Pending |
| TUI-05 | Phase 5 | Pending |
| QUEU-01 | Phase 6 | Pending |

**Coverage:**
- v1.0 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-08*
*Last updated: 2026-07-08 after initial definition*
