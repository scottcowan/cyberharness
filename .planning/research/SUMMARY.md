# Project Research Summary

**Project:** cyberharness v1.0 — Connectivity-aware AI Harness
**Domain:** Offline-first Python CLI/TUI AI harness for embedded hardware (Jetson Cyberdeck)
**Researched:** 2026-07-07
**Confidence:** HIGH for stack/architecture; MEDIUM for queue-drain UX (no direct prior art)

---

## Executive Summary

cyberharness is a connectivity-aware AI harness for the Jetson Cyberdeck. The local Ollama model is the **leader** — it orchestrates all work, has a deliberately minimal tool surface, and delegates to remote agents/models via ACP (Agent Communication Protocol) when online. Session state lives in the harness, not the model, so context survives model switches, reboots, and offline periods.

The recommended architecture is a Python asyncio application with Textual TUI, using httpx as the single HTTP client for both local Ollama and the remote relay (both expose an OpenAI-compatible interface). Sessions are persisted to disk as JSON after every turn with atomic writes. Work that requires a remote model is queued as named workflow envelopes and drained on reconnect. The relay server (a sandboxed workspace) is a separate milestone; v1.0 delivers the client harness with a relay stub.

The key design insight — local model as leader with low tool surface, ACP for remote control — means the harness is fundamentally different from tools like opencode or Claude Code. It doesn't give the model a large tool surface to operate on files directly. Instead, the local model orchestrates via ACP: it decides what work to queue, when to hand off to a remote agent, and how to compose the results. The harness is the coordination layer; ACP is the delegation mechanism.

---

## Key Findings

### Recommended Stack

Python 3.11 on Jetson (via `uv python install` to bypass JetPack's 3.10 default). The five load-bearing dependencies are: **Textual** (async TUI), **httpx** (single HTTP client for all endpoints), **pydantic v2** (session/config/envelope models), **pydantic-settings** (TOML + env config), and **aiofiles** (non-blocking session writes). All are pure-Python or ship aarch64 wheels — clean Jetson install.

**Do not add** OpenAI or Anthropic SDKs: both endpoints are OpenAI-compatible at the wire level, and the router already abstracts them. Adding SDKs forks the code path the design exists to unify.

**Core technologies:**
- **Textual ^8.2**: Chat-style TUI, async-native, streaming into `RichLog`, modal screens for resume/phase prompts
- **httpx ^0.28**: One client per endpoint (Ollama, relay), streaming via `aiter_lines`, shared across router + probe
- **pydantic v2 + pydantic-settings**: Session, Message, QueueEnvelope, Config models; fail-fast validation; JSON round-trip
- **aiofiles ^25.1**: Non-blocking per-turn session writes without stalling TUI
- **tenacity ^9.1**: Exponential backoff + jitter for queue drain retries
- **uv**: Packaging, lockfile, `uv python install 3.11` on Jetson

### Expected Features

**Must have (table stakes):**
- Chat-style TUI with streaming token display — users expect this from any AI CLI
- Session persistence and resumption — without this, a power cut loses all work
- Connectivity indicator — users must always know which model is active
- Graceful offline degradation — immediate fallback to Ollama, no hang
- Queue drain notification — user must know when queued work completes

**Should have (cyberharness differentiators):**
- Visible queue with per-envelope status — no direct prior art in AI-CLI space; this is the moat
- All Local / Wait for Online mode toggle — explicit user control over cloud use
- Local model as leader with ACP remote delegation — fundamentally different from opencode/Claude Code
- Per-phase model policy (not per-invocation) — consistent with "phase = routing decision"
- Summarisation before handoff — context doc, not raw messages, travels to relay

**Defer (v1.1+):**
- YAML/code workflow engine — needs real workflows to validate the schema; ship hardcoded phase behavior first
- Remote sandbox server (git, auth, MCP, networking) — separate milestone
- Reticulum/LoRa probe tier — needs real-hardware validation
- File browser / lazygit-style diff — deferred

### Architecture Approach

Single asyncio event loop: probe runs as a background task, emits `connected`/`disconnected` events via an `EventBus`, and the `Router` and `QueueManager` subscribe. `PhaseRunner` drives one phase per `asyncio.Task`, owns a `Session`, and calls `router.route(phase, messages)` per turn. Textual's app loop is the outer container; core packages are presentation-agnostic — the CLI uses them directly via `asyncio.run`.

**Major components:**
1. **Probe** — interval connectivity check (httpx HEAD or asyncio TCP connect); emits events; strategy pattern for future Reticulum tier
2. **Router** — stateless `(phase, messages) → AsyncIterator[str]`; picks Ollama vs relay vs enqueue based on phase policy + connectivity flag
3. **Session + SessionStore** — Pydantic model per phase, atomic JSON writes, filelock for cross-process safety, resume on startup
4. **QueueManager** — scans `~/.cyberharness/queue/`, drains on `ConnectedEvent`, per-envelope retry with exponential backoff + idempotency keys
5. **Summariser** — local Ollama call at phase completion; produces context doc before any cloud handoff
6. **TUI** — Textual app; presentation only; workers for streaming; chat screen + queue screen
7. **RelayClient** — httpx SSE client stub; posts `QueueEnvelope` to remote server; streams response back

### Critical Pitfalls

1. **Sync I/O in the TUI event loop** — any blocking call (sync file write, sync HTTP) freezes Textual. Use `aiofiles`, `httpx.AsyncClient`, and `asyncio.to_thread` for unavoidable blocking. Session writes must be async.
2. **Non-atomic session writes** — Jetson power loss is a real risk. Always `write tmp → fsync → os.replace`. Never overwrite the live session file in place.
3. **Connectivity flap → drain thrash** — debounce the `connected` event (5s), use a single-flight drain lock, and give every envelope an idempotency key. Without this, a flapping link causes repeated API calls and exploding retry counts.
4. **Summarisation drift** — a 3B quant model will paraphrase requirements incorrectly. Show the user the context doc before enqueuing. This is a v1.0 UX requirement, not a nice-to-have.
5. **`_model` metadata leaking to API** — strip the harness-only `_model` field at a single `to_wire()` choke point in the router before any HTTP send. Anthropic returns 400; Ollama silently tolerates it (masking the bug in local dev).

---

## Architectural Directive: Local Model as Leader

**This is the core design decision that differentiates cyberharness from all reference projects.**

The local Ollama model is the **leader**. It orchestrates all work. Its tool surface is deliberately minimal — the harness does not expose a large set of tools for the local model to operate on files, run shell commands, or call APIs directly.

Instead, the local model delegates to remote agents via **ACP (Agent Communication Protocol)**. When a task requires cloud capabilities (planning, execution, complex reasoning), the local model queues an ACP message to a remote agent. The remote server exposes its models and workspace through ACP. The harness is the coordination layer; ACP is the delegation mechanism.

**Implications for architecture:**
- The router's "cloud path" is not "call Claude directly" — it is "post an ACP message to a remote agent and stream the response"
- The relay server eventually exposes its capabilities via ACP, not just an OpenAI-compatible endpoint
- The local model's tool surface in v1.0 is limited to: queue an ACP task, check queue status, summarise session
- `router/relay.py` should be designed as an ACP client, not just an OpenAI proxy

**v1.0 scope:** ACP is the target protocol, but the relay stub can implement it as a simple HTTP envelope format initially. The ACP integration deepens as the remote server is built.

---

## Implications for Roadmap

Suggested phase structure (from research consensus across all 4 researchers):

### Phase 1: Foundation
**Rationale:** Config, paths, event bus, and error types are zero-dependency. Must exist before everything else. Also includes project scaffolding (pyproject.toml, uv setup, package structure).
**Delivers:** `config.py`, `paths.py`, `events.py`, `errors.py`, `pyproject.toml`, `uv.lock`
**Addresses:** All subsequent components depend on this
**Avoids:** Late discovery of ARM64 wheel gaps; config schema drift

### Phase 2: Session Manager
**Rationale:** Standalone — no network dependency. Most critical correctness requirement (atomic writes, filelock, crash safety). Getting this right unblocks everything above it.
**Delivers:** `session/models.py`, `session/store.py`, `session/state.py`, full crash-safety invariants
**Uses:** pydantic v2, aiofiles, filelock
**Implements:** Session persistence architecture; all 3 ordering invariants

### Phase 3: Router + Ollama (Local Path)
**Rationale:** Enables full local end-to-end before any cloud work. Validates the routing pattern with a real model.
**Delivers:** `router/ollama.py`, `router/router.py`, phase registry (local policy), All Local mode working
**Implements:** `to_wire()` sanitiser, NDJSON streaming, `keep_alive=-1` warm-up
**Avoids:** `_model` field leaking to API

### Phase 4: Phase Runner + Summariser
**Rationale:** Ties session + router into a full phase lifecycle. Summarisation must exist before any cloud handoff.
**Delivers:** `phases/runner.py`, `phases/registry.py`, `session/summarise.py`, context doc with user confirmation UX
**Implements:** Turn lifecycle (persist before call), summarisation gate before enqueue

### Phase 5: Probe + Queue + Relay Stub
**Rationale:** Probe triggers queue drain; queue uses relay stub. These three ship together as the "Wait for Online" path.
**Delivers:** `probe/`, `queue/envelope.py`, `queue/manager.py`, `router/relay.py` (stub), drain UX
**Implements:** Debounced connectivity events, single-flight drain lock, idempotency keys, exponential backoff

### Phase 6: CLI + GSD Phase Hooks
**Rationale:** Makes the harness usable headless on the Jetson. CLI is the shortest path to a testable system; GSD hooks make it useful for real workflow phases.
**Delivers:** `cli/main.py` (Click commands), `phases/hooks.py` (GSD adapter)
**Implements:** Milestone 1 CLI-complete state

### Phase 7: TUI (Textual)
**Rationale:** Textual is the presentation layer — depends on everything else working. Building it last means the core is already tested. Chat screen + queue screen + status bar.
**Delivers:** `tui/app.py`, `tui/screens/session.py`, `tui/screens/queue.py`, `tui/widgets/`
**Implements:** Streaming render, modal resume/confirm screens, queue visibility

### Phase Ordering Rationale

- Probe (Phase 5) depends on EventBus (Phase 1) — can't reorder
- Queue drain depends on relay client stub — must ship in same phase
- CLI (Phase 6) depends on core being stable — deliberately after session + runner
- TUI (Phase 7) is last — it's a consumer; all producers must be proven first
- Summarisation (Phase 4) must precede any queue enqueue — ordering is a correctness requirement

### Research Flags

Phases needing deeper research during planning:
- **Phase 5 (Queue/Relay):** ACP protocol spec needs to be defined before implementing `router/relay.py` — what does the relay contract look like?
- **Phase 5 (Queue drain UX):** No AI-CLI prior art. Design the queue TUI surface from scratch.
- **Phase 7 (TUI):** Textual batch-rendering strategy for fast token streams needs a spike.

Phases with standard patterns (can skip research):
- **Phase 1 (Foundation):** pyproject.toml + pydantic-settings is well-documented
- **Phase 2 (Session):** Atomic writes + filelock is a known pattern
- **Phase 3 (Router/Ollama):** httpx streaming against Ollama is documented

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All deps verified against PyPI 2026-07; all ship aarch64 wheels |
| Features | MEDIUM-HIGH | Table stakes well-established; queue drain UX is novel |
| Architecture | HIGH | asyncio/Textual/httpx patterns are well-established; relay seam design is sound |
| Pitfalls | HIGH | Specific to this stack; backed by official docs and known incidents |

**Overall confidence:** HIGH for phases 1–6; MEDIUM for phase 7 (TUI batch rendering) and relay ACP contract

### Gaps to Address

- **ACP protocol spec:** The relay contract (`POST /v1/phase-runs` vs ACP envelope) needs a decision before Phase 5. Recommend a dedicated spike in Phase 5 planning.
- **Claude endpoint placement:** Is `api.anthropic.com` called from the Jetson directly (relay = proxy) or from the remote sandbox (relay = ACP agent)? Architecture recommends B (server-side); confirm before Phase 5.
- **Queue drain UX:** No reference implementation. Will need UX design work during Phase 5 discuss.
- **Summarisation model quality:** 3B quant paraphrase risk — consider user-editable context doc before enqueue, or a confirmation step.

---

## Sources

### Primary (HIGH confidence)
- `docs/architecture.md` — component design, session format, queue envelope shape
- `docs/session-design.md` — session lifecycle, summarisation, resume behavior
- Textual documentation (textualize.io) — async model, RichLog streaming, Worker API
- httpx documentation (python-httpx.org) — streaming, async client, SSE
- pydantic v2 docs — Rust core, aarch64 wheels, model_dump_json
- Ollama OpenAI-compat docs — `/v1/chat/completions` parity verified

### Secondary (MEDIUM confidence)
- opencode, gemini-cli, earendil-works/pi — reference architecture patterns
- lazygit, diff-so-fancy — UX reference for file/diff views (v1.1+)

---

*Research completed: 2026-07-07*
*Ready for roadmap: yes*
