# Architecture Research

**Domain:** Connectivity-aware Python AI harness (CLI/TUI, async event-driven, durable session state)
**Researched:** 2026-07-07
**Confidence:** HIGH for asyncio/Textual/httpx patterns (well-established); MEDIUM for crash-safety recipe (multiple valid approaches, one recommended); MEDIUM for probe/queue implementation choices.

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                         │
│  ┌──────────────────────┐         ┌───────────────────────────┐  │
│  │  Textual TUI (App)   │         │  Click CLI (headless)     │  │
│  │  - session pane      │         │  - one-shot phase run     │  │
│  │  - status bar        │◄────────┤  - queue inspect / drain  │  │
│  │  - queue widget      │  shared │  - config edit            │  │
│  └──────────┬───────────┘  core   └──────────────┬────────────┘  │
│             │                                     │               │
├─────────────┴─────────────────────────────────────┴───────────────┤
│                     Application / Orchestration                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  PhaseRunner (asyncio.Task per phase invocation)          │    │
│  │   - owns one Session                                      │    │
│  │   - calls Router.route() per turn                         │    │
│  │   - subscribes to probe events                            │    │
│  │   - on complete → summarise → enqueue if cloud phase      │    │
│  └───────┬─────────────┬────────────────────────┬────────────┘    │
│          │             │                        │                 │
│  ┌───────▼──────┐ ┌────▼─────────┐  ┌──────────▼────────┐        │
│  │   Router     │ │ SessionMgr   │  │  QueueManager      │        │
│  │  (stateless) │ │ (per-phase)  │  │  (background task) │        │
│  └───┬──────┬───┘ └──────┬───────┘  └─────────┬──────────┘        │
│      │      │            │                    │                   │
├──────┼──────┼────────────┼────────────────────┼───────────────────┤
│      │      │       Core Services (async)     │                   │
│  ┌───▼──┐ ┌─▼─────┐ ┌────▼────────┐ ┌────────▼─────────┐         │
│  │Ollama│ │Claude │ │  Probe       │ │  EventBus         │         │
│  │client│ │client │ │(interval task)│ │(asyncio queues)  │         │
│  └──┬───┘ └───┬───┘ └──────┬───────┘ └──────────────────┘         │
│     │        │             │                                       │
├─────┼────────┼─────────────┼───────────────────────────────────────┤
│     │        │        Persistence (async I/O)                     │
│  ┌──▼────────▼──┐ ┌────────▼────────┐ ┌─────────────────────┐    │
│  │  HTTP (httpx)│ │ FS (aiofiles +  │ │ Config (tomllib +   │    │
│  │  streaming   │ │  atomic replace)│ │  Pydantic model)    │    │
│  └──────────────┘ └─────────────────┘ └─────────────────────┘    │
├───────────────────────────────────────────────────────────────────┤
│                        External Endpoints                          │
│  localhost:11434 (Ollama)  •  api.anthropic.com  •  probe host    │
│  ~/.cyberharness/sessions/  •  ~/.cyberharness/queue/             │
└───────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| `PhaseRunner` | Drives one phase invocation end-to-end. One `asyncio.Task` per active phase. | Plain async class; no framework needed. |
| `Session` | Owns messages + model_log for one phase. Serialises to disk after every turn. | Pydantic model + atomic write helper. |
| `SessionStore` | Loads/persists sessions, tracks active vs abandoned. | Directory-per-instance; file lock per session id. |
| `Router` | Stateless: `(phase, messages) -> AsyncIterator[str]`. Picks Ollama vs Claude vs enqueue. | Pure function of connectivity state + config. |
| `OllamaClient` / `ClaudeClient` | Streaming HTTP calls. Same OpenAI messages shape. | `httpx.AsyncClient` with SSE/chunked response iteration. |
| `Probe` | Background task; connectivity checks every N seconds; emits events. | `asyncio.create_task` loop, `dnspython` async resolver + optional HEAD request. |
| `EventBus` | Fan-out of `connected` / `disconnected` events to N subscribers. | Small pub/sub over `asyncio.Queue` per subscriber. |
| `QueueManager` | Watches `~/.cyberharness/queue/`, drains on `connected`, retries with backoff. | Startup scan + subscribe to events; no filesystem watcher needed. |
| `Summariser` | Runs local Ollama call to compress discuss history → context doc. | Reuses `OllamaClient`; templated prompt. |
| `TUI` (Textual) | Presentation only. Reads from stores, posts intents. No business logic. | Textual `App`; workers for long-running I/O. |
| `CLI` (Click) | Headless entry points; shares the same core services. | Click group with `asyncio.run()` per command. |

---

## Recommended Project Structure

```
cyberharness/
├── pyproject.toml
├── src/cyberharness/
│   ├── __init__.py
│   ├── config.py               # Pydantic Settings, load ~/.cyberharness/config.toml
│   ├── paths.py                # XDG-ish path helpers (~/.cyberharness/*)
│   ├── events.py               # EventBus, event dataclasses
│   ├── errors.py               # Domain exceptions (RouterError, QueueFull, ...)
│   │
│   ├── probe/
│   │   ├── __init__.py
│   │   ├── probe.py            # async run loop, emits events
│   │   └── strategies.py       # DNS, HTTP HEAD, Reticulum (future)
│   │
│   ├── router/
│   │   ├── __init__.py
│   │   ├── router.py           # route(phase, messages) -> AsyncIterator
│   │   ├── ollama.py           # OllamaClient (httpx)
│   │   └── claude.py           # ClaudeClient (httpx)
│   │
│   ├── session/
│   │   ├── __init__.py
│   │   ├── models.py           # Message, ModelCall, Session (Pydantic)
│   │   ├── store.py            # SessionStore: load/save/lock/atomic write
│   │   ├── state.py            # SessionState enum + transitions
│   │   └── summarise.py        # discuss -> context_doc
│   │
│   ├── queue/
│   │   ├── __init__.py
│   │   ├── envelope.py         # QueueEnvelope Pydantic model
│   │   └── manager.py          # scan, drain, retry with backoff
│   │
│   ├── phases/
│   │   ├── __init__.py
│   │   ├── runner.py           # PhaseRunner: owns one phase run
│   │   ├── registry.py         # phase → routing policy
│   │   └── hooks.py            # GSD phase-hook adapters
│   │
│   ├── tui/
│   │   ├── __init__.py
│   │   ├── app.py              # Textual App entry
│   │   ├── screens/
│   │   │   ├── session.py      # main chat screen
│   │   │   └── queue.py        # queue inspector
│   │   └── widgets/
│   │       ├── status.py       # connectivity indicator
│   │       └── stream.py       # streaming response widget
│   │
│   └── cli/
│       ├── __init__.py
│       └── main.py             # Click group: run, queue, session, config
│
└── tests/
    ├── unit/                   # router, session, queue in isolation
    ├── integration/            # probe + router + queue with mocked endpoints
    └── e2e/                    # full phase run against Ollama fixture
```

### Structure Rationale

- **`router/`, `session/`, `queue/`, `probe/` as sibling packages, not layered subdirs.** They are peers connected by events; not a strict hierarchy. Mirrors the four bullet-points in `README.md`.
- **`phases/` sits above the core primitives.** It's the only place that knows the harness workflow; everything below is a reusable service.
- **`tui/` and `cli/` are leaves — they depend on core, core never imports them.** Enables headless testing and lets the CLI ship first (Phase 1) before Textual (later phase).
- **`events.py` is intentionally at the top level.** Both probe (producer) and queue/tui (consumers) need it; making it a peer avoids a circular import.
- **Config is Pydantic-modelled, not raw dict.** Cyberdeck runs unattended; a typo in the TOML should fail fast at startup, not on first offline turn.

---

## Async Event Loop Architecture

### One Loop, Many Tasks

Everything runs on a single asyncio event loop. No threads except (a) Textual's compositor which it manages internally, and (b) any sync library wrapped via `asyncio.to_thread`.

```python
# Simplified startup shape (cli/main.py or tui/app.py)
async def main():
    config = Config.load()
    bus    = EventBus()
    store  = SessionStore(config.paths.sessions)
    queue  = QueueManager(config.paths.queue, bus)
    probe  = Probe(config.probe, bus)
    router = Router(config, bus)          # subscribes to bus for connectivity

    async with asyncio.TaskGroup() as tg:
        tg.create_task(probe.run(), name="probe")
        tg.create_task(queue.run(), name="queue-drainer")
        tg.create_task(run_ui(config, bus, store, router, queue), name="ui")
```

**Why `TaskGroup` (3.11+):** structured concurrency. If any background task raises, all get cancelled and the shutdown is clean. Manual `create_task` without a group leaks tasks on crash.

### Event Flow

```
   Probe (interval task)
        │
        │ emits ConnectedEvent / DisconnectedEvent
        ▼
   EventBus (asyncio.Queue fan-out)
        │
        ├──► QueueManager: on Connected, drain()
        ├──► Router:       flips internal `is_online` flag
        └──► TUI:          updates status widget
```

The `EventBus` is deliberately trivial — a set of subscriber `asyncio.Queue`s. No pub/sub library needed; adding one (aiohttp bus, redis) is a premature dependency at this scale.

### Streaming Turn Lifecycle

```
user submits input in TUI
        │
        ▼
  PhaseRunner.submit(text)                # in-flight guard: one turn at a time per phase
        │
        ├─► session.add_turn(user)        # persist BEFORE the model call
        │
        ├─► async for chunk in router.route(phase, session.messages):
        │       tui.post_message(StreamChunk(chunk))     # non-blocking
        │
        ├─► session.add_turn(assistant, model=...)      # persist after
        │
        └─► session.save()                # atomic replace
```

**Critical:** the user turn is persisted *before* the router call. If the model call or the process crashes mid-stream, the user's message is not lost on resume.

### Textual + asyncio: The Seam That Bites

Textual's `App.run_async()` is already an asyncio coroutine; it owns the event loop. Rules that avoid the common pitfalls:

1. **Long-running I/O uses `@work(thread=False)` or plain `asyncio.create_task`.** Never call blocking libraries directly in an event handler — it freezes the compositor.
2. **Cross-task communication is via `App.post_message` or `App.call_from_thread`.** Widgets should not `await` the router directly; the PhaseRunner streams chunks by posting messages to a widget.
3. **The background tasks (probe, queue) are owned by the `App`, not the widgets.** Use `App.on_mount` to spawn them and cancel in `App.on_unmount`. Widgets subscribe to events via message posting.
4. **CLI mode reuses the same core.** `PhaseRunner` must be usable without Textual — it takes an `AsyncIterator` sink, not a widget reference.

---

## Session State Machine

```
             create()
                │
                ▼
        ┌──────────────┐
        │    ACTIVE    │◄────────────┐
        └───┬──────┬───┘             │
            │      │                 │
   complete()      abandon()   resume()
            │      │                 │
            ▼      ▼                 │
       DRAINING  ABANDONED           │
            │                        │
   summarise + enqueue?              │
            │                        │
     ┌──────┴──────┐                 │
     │             │                 │
     ▼             ▼                 │
   QUEUED    COMPLETE                │
     │                               │
     │ (cloud drain success)         │
     ▼                               │
  COMPLETE                           │
                                     │
   ── on startup, ACTIVE sessions ──┘
```

### State Definitions

| State | Meaning | On-disk marker |
|-------|---------|----------------|
| `active` | Currently taking turns; process may hold it | file exists, `state: active`, optional `<id>.lock` |
| `draining` | Phase completed; summarisation in progress | `state: draining` |
| `queued` | Handed off to cloud queue; awaiting drain | `state: queued`, envelope in `queue/` |
| `complete` | Terminal success; context_doc written to `.planning/` | `state: complete` |
| `abandoned` | User declined resume, or crash-abandoned on second startup | `state: abandoned` |

### Transition Rules

- **`active → draining`** is atomic on disk: write session with new state, then start summariser task. If the process dies mid-summarise, next startup sees `draining` and re-runs summarisation (idempotent — summarise is a pure function of messages).
- **`draining → queued`** is the enqueue step. Ordering matters: **write envelope first, then flip session state**. If the process dies between, the envelope is orphaned but drainable (its own id lets us dedupe against `session_id`).
- **`queued → complete`** only after cloud drain succeeds. Envelope is deleted first, then session state flips. Same reasoning as above.
- **Resume prompt only fires for `active` and `draining`.** `queued` sessions drain silently (`session-design.md`).

### Concurrency Guard

At most one `PhaseRunner` per session id at a time. Enforced by a per-file lock (`filelock` library — cross-platform, works on macOS/Linux/Jetson). The lock file lives next to the session json: `~/.cyberharness/sessions/<id>.lock`.

---

## Workflow → Queue Mapping

A workflow definition is the pair `(phase, routing policy)` in `config.toml`. The mapping to queue items is:

```
Local phase (discuss/spec/explore):
    session stays in-process; never queued.
    on complete → summarise → if next declared phase is cloud, enqueue.

Cloud phase (plan/execute/verify) while offline:
    router returns queued-ack; envelope written; session state = queued.

Cloud phase while online:
    router calls Claude directly; no queue involved.
```

### Envelope shape (already defined in `docs/architecture.md`)

Add two harness-only fields for crash safety:

```json
{
  "id": "uuid",
  "phase": "plan",
  "session_id": "uuid",
  "context_doc": "...",
  "enqueued_at": "2026-07-07T16:00:00Z",
  "attempts": 0,
  "last_attempt_at": null,
  "next_retry_at": null
}
```

`next_retry_at` is what the drainer respects for backoff — cheaper than a per-envelope timer task.

### Router Dispatch (pseudo)

```python
async def route(phase, messages) -> AsyncIterator[str]:
    policy = phase_registry.policy_for(phase)     # local | cloud
    if policy == "local" or not connectivity.is_online():
        async for chunk in ollama.stream(messages): yield chunk
        return
    if policy == "cloud" and connectivity.is_online():
        async for chunk in claude.stream(messages): yield chunk
        return
    # cloud phase, offline
    envelope = await queue.enqueue(phase, messages)
    yield f"[queued: {envelope.id}]"
```

Router is stateless w.r.t. sessions — it only reads connectivity + config. Keeps it testable.

---

## Local ↔ Relay Seam

The remote server (sandboxed workspace: git, auth, MCP, networking) is reached only through the **relay client**, which lives on the cloud-phase side of the queue. The seam is at the queue drain point, not inside individual model calls.

```
┌──────────────────────── LOCAL (Jetson Cyberdeck) ─────────────────────────┐
│                                                                            │
│   discuss/spec/explore ──► Ollama (localhost:11434)                        │
│                              │                                             │
│                              ▼                                             │
│                       Summariser (also Ollama)                             │
│                              │                                             │
│                              ▼                                             │
│                       QueueEnvelope written                                │
│                              │                                             │
│  ─── seam ───────────────────┼───────────────────────────────────────────  │
│                              ▼                                             │
│   RelayClient (httpx) ──► HTTPS ──► Remote sandbox workspace               │
│     - drains envelopes       │       - git, auth, MCP tools               │
│     - streams Claude turns   │       - Claude API originates here?         │
│     - writes .planning/*     │         (open question — see below)         │
└──────────────────────────────┴─────────────────────────────────────────────┘
```

### Where Claude actually gets called — decide early

`docs/architecture.md` shows the harness calling `api.anthropic.com` directly. The new milestone context says the remote sandbox has "auth, MCP, networking." Two viable placements:

| Option | Claude client lives | Trade-off |
|--------|---------------------|-----------|
| **A. Direct from Jetson** | in `router/claude.py`, keys on-device | Simpler; fewer hops; but keys on the deck and no shared MCP tools. |
| **B. Via relay** | `RelayClient` posts envelope to sandbox; sandbox calls Claude | Central key store; MCP tools available server-side; matches the "sandboxed workspace" framing. |

**Recommendation: B.** The milestone brief explicitly puts auth and MCP on the remote side. Making the local harness never touch `api.anthropic.com` directly is what makes the sandbox worth having. This means:

- `router/claude.py` renames to `router/relay.py` — same interface (streaming AsyncIterator), different endpoint.
- Envelopes are POSTed to the relay; the relay's HTTP response is a server-sent event stream of Claude chunks (plus MCP tool-call events).
- The seam is a single relay contract (envelope in, SSE out); everything upstream of the queue is local; everything downstream is remote.

### Contract at the seam (proposed)

```
POST /v1/phase-runs
  body: QueueEnvelope
  response: text/event-stream
    event: chunk    data: {"delta": "..."}
    event: tool     data: {"name": "...", ...}    # MCP tool call surfaced
    event: done     data: {"session_id": "...", "artifacts": [...]}
```

Local harness treats tool events as informational (log + display); it does not execute them.

---

## Data Flow

### Offline discuss turn

```
user text
    │
    ▼
TUI widget ── post_message ──► PhaseRunner
    │
    ▼
session.add_turn(user) + session.save()          [durable]
    │
    ▼
router.route(discuss, messages)  ─► OllamaClient.stream(httpx SSE)
    │
    ▼ chunks
TUI widget renders + PhaseRunner buffers
    │
    ▼ (stream ends)
session.add_turn(assistant, _model=ollama)
session.save()                                    [durable]
```

### Reconnect → cloud drain

```
Probe: HTTP HEAD to probe_host succeeds
    │
    ▼
bus.publish(ConnectedEvent)
    │
    ├──► Router.is_online = True
    └──► QueueManager.on_connected()
              │
              ▼
          scan queue/ ordered by enqueued_at
              │
              ▼
          for each envelope:
              relay.stream(envelope) ── SSE ──► TUI queue widget
              on 200: delete envelope; session.state = complete
              on 5xx: attempts += 1; schedule next_retry_at (exp backoff, jitter)
              on 4xx: mark envelope failed; surface to user
```

### Crash + resume

```
process starts
    │
    ▼
SessionStore.scan_active() → [session_a, session_b]
    │
    ▼
for each: try filelock.acquire(nonblocking)
    ├── acquired → prompt user "Resume <phase>?"
    │    y → PhaseRunner.attach(session)
    │    n → session.state = abandoned; save
    └── locked-by-other → skip (another instance owns it)
    │
    ▼
QueueManager.scan() → drain envelopes not owned by other locks
```

---

## Persistence & Crash Safety

### Atomic Writes

Every session and envelope write follows:

```python
def atomic_write_json(path: Path, obj: BaseModel) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(obj.model_dump_json(indent=2))
    os.replace(tmp, path)          # atomic on POSIX
```

`aiofiles` for the write itself; `os.replace` is a fast sync syscall — running it directly in the loop is fine.

### File Layout

```
~/.cyberharness/
├── config.toml
├── sessions/
│   ├── <uuid>.json               # session state + messages
│   ├── <uuid>.lock               # filelock; presence = live owner
│   └── <uuid>.json.tmp           # transient; ignore on scan
├── queue/
│   ├── <uuid>.json               # envelope
│   └── <uuid>.json.tmp           # transient
└── logs/
    └── cyberharness.log          # structlog JSON lines
```

### Ordering Invariants (the ones that matter)

1. **Before a model call:** user turn is persisted.
2. **Before enqueue-and-flip:** envelope file is written; session state flip is the second step.
3. **Before delete-on-drain:** the cloud response is fully received; delete envelope; then flip session state to `complete`.

Everything else is best-effort. These three keep the system replayable.

---

## Scaling Considerations

This is single-user desktop software on a Jetson. "Scale" means "does it survive weeks of unattended use," not "handle 10k users."

| Scale | Adjustments |
|-------|-------------|
| Normal use (dozens of sessions, hundreds of envelopes) | Directory scan is fine; no index needed. |
| Long-lived deck (thousands of old sessions) | Add a `sessions/archive/` subdir; move `complete`/`abandoned` older than N days. Startup scans only the live dir. |
| Very long conversations (megabyte-scale message history) | Split session file: `<id>.json` (metadata) + `<id>.messages.jsonl` (append-only). Avoids rewriting the whole history every turn. Introduce only when a session exceeds ~1 MB. |

### First bottlenecks to expect

1. **Startup scan time** on a Jetson if `sessions/` has thousands of files. Fix with archive dir.
2. **JSON rewrite cost per turn** on long histories. Fix with append-only messages log.
3. **Textual repaint under fast streaming**. Fix by batching chunks (flush at 50ms or newline boundary), not by rendering every token.

---

## Anti-Patterns

### 1. Watching the queue directory with a filesystem watcher

**What people do:** `watchdog` observer to detect new envelopes.
**Why it's wrong:** envelopes are only ever produced by this same process. There's no external writer. Adds a dependency and a callback thread for nothing.
**Instead:** Enqueue is a direct call; drain triggers on `ConnectedEvent` and on retry timers. Filesystem is durable storage, not a message bus.

### 2. Sharing an `httpx.AsyncClient` across a mix of Ollama and Claude calls

**What people do:** one global `AsyncClient()`.
**Why it's wrong:** different base URLs, timeouts (local is fast, cloud is slow), and auth; connection pool tuning differs. A single misconfigured timeout hurts both.
**Instead:** One client per external service, held by `OllamaClient` / `ClaudeClient` for the process lifetime. Close in shutdown.

### 3. Running the Textual app and CLI as two codepaths

**What people do:** duplicate route/persist logic in `cli/` and `tui/` because the async-vs-sync feel differs.
**Why it's wrong:** business logic drift; a bug fixed in one is missed in the other.
**Instead:** All logic lives in core packages returning async iterators; `cli/` uses `asyncio.run` + prints chunks; `tui/` posts chunks as messages. Two thin adapters, one core.

### 4. Reading connectivity state synchronously via `probe.is_online` from inside a turn

**What people do:** query the probe object at the start of each router call.
**Why it's wrong:** race with the interval; also couples router to probe implementation.
**Instead:** Router subscribes to `EventBus` and maintains its own boolean. Route decisions read that flag. Probe is a producer only.

### 5. Committing the summarisation step to the *cloud* model

**What people do:** "we'll just have Claude summarise on the other side."
**Why it's wrong:** defeats the token-cost point in `session-design.md`. Also requires connectivity to hand off, which contradicts the offline-first design.
**Instead:** Summarise locally with Ollama at phase completion. Envelope carries the context_doc, not the raw messages.

### 6. Using `asyncio.Lock` for cross-process session ownership

**What people do:** an in-memory lock in `SessionStore`.
**Why it's wrong:** two harness invocations (CLI + TUI, or a stale process) both think they own the session and corrupt the file.
**Instead:** `filelock.FileLock` — OS-level, cross-process, auto-released on process death.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Ollama (`localhost:11434`) | `httpx.AsyncClient` streaming POST to `/api/chat`. | Native SSE-ish streaming; parse newline-delimited JSON. Always available, no queueing. |
| Claude via relay (`https://<relay>/v1/phase-runs`) | `httpx.AsyncClient` streaming; SSE parser. | Auth token from config; retries handled by queue manager, not client. |
| Probe target (`1.1.1.1` or configurable) | Async DNS resolve + optional HTTP HEAD, timeout 3s. | Two-stage: DNS first (cheap), HEAD confirms application-layer. |
| Reticulum / rnsh (future) | Out of scope for v1.0; probe strategy plug-in later. | Design probe as strategy pattern to make this a config change. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Probe → Router / Queue / TUI | `EventBus` (asyncio queue fan-out) | Publisher never awaits subscribers. |
| PhaseRunner → Router | Direct `await` + async iteration | Router is stateless — no bus needed. |
| PhaseRunner → SessionStore | Direct call | Store handles locking/atomic writes internally. |
| Router → QueueManager | Direct `enqueue()` call | Only when routing decides "queue this." |
| QueueManager → Router | Direct call during drain | Router is reused; drain isn't a special path. |
| Core → TUI | `App.post_message` (Textual) | TUI is a consumer; core never imports TUI. |
| Core → CLI | Return values / async iterators | CLI awaits, prints. |
| CLI → Core | `asyncio.run(core_entry())` per command | No shared loop across CLI invocations. |

---

## Suggested Build Order

Ordered by dependency and by "what can be tested standalone."

1. **`config.py`, `paths.py`, `events.py`, `errors.py`** — no dependencies; foundation. (1–2 days)
2. **`session/models.py` + `session/store.py`** — session model, atomic writes, filelock. Unit-testable without any network. (2–3 days)
3. **`router/ollama.py`** — streaming httpx client. Test against a local Ollama. (1–2 days)
4. **`router/router.py`** — pure routing logic, mocked clients. Unit tests. (1 day)
5. **`phases/runner.py` + `phases/registry.py`** — turn lifecycle, ties session + router. E2E test: full discuss phase against Ollama. (2 days)
6. **`session/summarise.py`** — reuses Ollama client + phase runner primitives. (1 day)
7. **`queue/envelope.py` + `queue/manager.py`** — enqueue, scan, drain (with a stub relay). (2 days)
8. **`probe/`** — interval task + event emission. Fake probe target in tests. (1–2 days)
9. **`router/relay.py`** — real relay client; drain flow becomes real end-to-end. (2 days, depends on relay spec)
10. **`cli/main.py`** — Click commands. Ships the whole thing headless. Milestone 1 usable here. (2 days)
11. **`phases/hooks.py`** — GSD integration adapter. Small once core is stable. (1 day)
12. **`tui/`** — Textual app. Depends on everything else. (3–5 days)

**Rationale:** the harness is usable at step 10 (CLI) without Textual. That is the shortest path to a testable end-to-end system on the Jetson. Textual is a presentation upgrade, not a prerequisite.

**Parallelisation opportunities:** steps 3 & 8 (Ollama client and probe) are independent; steps 6 & 7 are independent given steps 1–5 are done.

---

## Key Library Choices

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Async HTTP | `httpx.AsyncClient` | Streaming, HTTP/2, first-class async, replaces `aiohttp` for this use case. |
| Config | `pydantic-settings` + `tomllib` | Typed config, fail-fast validation, stdlib TOML parser. |
| Data models | `pydantic` v2 | Session, envelope, message; validation + JSON round-trip. |
| CLI | `click` | Boring, works, subcommand-friendly. `typer` also fine — prefer `click` if we want minimal deps. |
| TUI | `textual` | Async-native, right shape for this app. |
| DNS probe | `dnspython` (async) | Async resolver without pulling `aiohttp`. |
| Cross-process lock | `filelock` | Simple, portable. |
| Logging | `structlog` | Structured JSON logs; needed for post-mortem on an unattended deck. |
| Tests | `pytest`, `pytest-asyncio`, `respx` (httpx mock) | Standard async test stack. |

Everything else (retry backoff, event bus) is small enough to write in-tree without a library.

---

## Sources & Confidence

- **asyncio patterns (TaskGroup, structured concurrency):** Python stdlib docs, 3.11+. HIGH.
- **Textual + asyncio interaction:** Textual documentation on `App.run_async`, `@work`, and message passing. HIGH.
- **httpx streaming for SSE / NDJSON:** httpx documentation on `stream()`. HIGH.
- **filelock cross-process semantics:** `filelock` PyPI documentation. HIGH.
- **Atomic replace on POSIX:** `os.replace` documented as atomic when src and dst are on the same filesystem. HIGH.
- **Ollama streaming API shape:** Ollama HTTP API docs — `/api/chat` returns NDJSON stream. HIGH.
- **Anthropic API streaming (SSE):** Anthropic API docs; noted, but placed behind the relay in this design so the harness doesn't depend on the shape directly. MEDIUM (design choice, not verified against a live relay spec — that spec is a follow-up).
- **Reticulum / rnsh probe strategy:** deferred; noted as future plug-in only.

---

*Architecture research for: connectivity-aware Python AI harness (cyberharness v1.0)*
*Researched: 2026-07-07*
