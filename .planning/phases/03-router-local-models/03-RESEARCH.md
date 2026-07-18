# Phase 3: Router + Local Models - Research

**Researched:** 2026-07-09
**Domain:** async HTTP streaming to local OpenAI-compatible LLM servers (Ollama / LM Studio); asyncio-based TCP connectivity probe with debounced event fan-out
**Confidence:** HIGH (httpx streaming, asyncio TCP, Ollama /v1 compatibility — well-documented); MEDIUM (Ollama /api/version schema, keep_alive-in-v1-body semantics — verified from official docs but Ollama's OpenAI-compat surface has known quirks)

## Summary

Phase 3 wraps two well-understood primitives — `httpx.AsyncClient` streaming SSE and `asyncio.open_connection` — behind a stateless `Router.route(messages)` interface that dispatches to a single `LocalModelClient` for all turns in v1.0. The cloud branch is a `NotImplementedError` stub. The tricky parts are all guards, not novel engineering: strip `_model` before wire send, strip `[DONE]` from SSE, debounce probe transitions (N-of-M with `confirm_count=2`), and inject `think: false` / reject `name`-parameter tools as pre-baked defences against known Ollama parser bugs (TODO-001).

The OpenAI-compat endpoint on Ollama (`/v1/chat/completions`) is intentionally the shared path with LM Studio: one `LocalModelClient`, configurable `base_url`, one `httpx.AsyncClient` scoped to process lifetime. Warm-up is a fire-and-forget POST with `keep_alive: -1` at startup; version check hits `/api/version` (Ollama-native) and warns on `< 0.30.12`. Model discovery uses `/v1/models` (works on both Ollama and LM Studio; Ollama's `/api/tags` is a native alternative used only if `/v1/models` is missing).

**Primary recommendation:** Build the streaming pipeline around `client.stream("POST", url, json=payload)` + `response.aiter_lines()` with an explicit line filter (strip `data: `, skip empty, break on `[DONE]`, `json.loads` the rest, yield `delta["choices"][0]["delta"].get("content", "")`). Wrap the probe in a `while True: await asyncio.sleep(interval)` loop guarded by `asyncio.wait_for(open_connection(...), timeout=3)`. Publish `ConnectedEvent` / `DisconnectedEvent` on debounced transitions only, via the existing Phase 1 `EventBus`.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Router & Wire Format**
- **D-01:** `async def route(messages: list[Message]) -> AsyncIterator[str]`. No `phase` parameter in v1.0 — all turns go to the same local backend.
- **D-02:** Use Ollama's `/v1/chat/completions` OpenAI-compatible endpoint — same shape as LM Studio. One `LocalModelClient` handles both; config sets `local_url` per backend.
- **D-03:** No separate `LmStudioClient`. Single `LocalModelClient` with configurable `base_url`, `model`, optional headers.
- **D-04:** SSE parsing via `response.aiter_lines()`. Strip `data: ` prefix, parse JSON delta, yield `delta["choices"][0]["delta"]["content"]`. Skip `[DONE]` sentinel and lines without `data:` prefix.
- **D-05:** One `httpx.AsyncClient` per `LocalModelClient`, scoped to process lifetime. Created at startup; closed on shutdown.
- **D-06:** Ollama model warm-up on startup: POST `/v1/chat/completions` with `{"keep_alive": -1, "messages": [], "stream": false}`. Non-blocking — background task.

**Tool Registry & Guards (from TODO-001)**
- **D-07:** Zero tools registered in Phase 3. Registry is infrastructure only.
- **D-08:** Tool registry validates at registration: reject any tool whose parameters include a key named `"name"` (Ollama bug #16932 guard). Raise `ToolRegistrationError`.
- **D-09:** `to_wire(messages)` strips `_model` from every Message before any HTTP send. Single choke point.
- **D-10:** `LocalModelClient` always injects `"stream": true`. Always injects `"think": false` when any tools present (even though Phase 3 has none).
- **D-11:** Ollama version check at startup: GET `/api/version`, parse semver, warn if `< 0.30.12`. Non-blocking warning.

**Connectivity Probe**
- **D-12:** TCP connect to `config.probe.probe_host:443`, timeout 3s. `asyncio.open_connection(host, 443)`. Fallback to port 80 if 443 times out. No ICMP.
- **D-13:** Probe runs as a background task in the `TaskGroup` (Phase 1). Interval from `config.probe.interval_seconds` (default 30).
- **D-14:** Debounce N-of-M with `confirm_count = 2`. Transitions require 2 consecutive samples.
- **D-15:** Probe maintains `probe.is_connected: bool`. Router reads `probe.is_connected` directly.
- **D-16:** Probe publishes `ConnectedEvent` / `DisconnectedEvent` to the EventBus. Dataclasses with `timestamp: float`.

**Phase Routing (v1.0 local-only)**
- **D-17:** `route()` always dispatches to `LocalModelClient`. Phase registry scaffolded; cloud branch raises `NotImplementedError("relay not yet implemented")`.
- **D-18:** "All Local" mode ignores `probe.is_connected`. "Wait for Online" mode reads it (but still routes local in Phase 3).

### Claude's Discretion
- Chunk buffering (50ms debounce) before yielding — default is per-token; implement only if TUI flickering observed in Phase 5.
- Retry/backoff behaviour for transient Ollama connection errors (e.g., model still loading).
- Default value of `probe.is_connected` on startup before first check completes.

### Deferred Ideas (OUT OF SCOPE)
- Relay / cloud routing — v1.1.
- Phase-based routing policy (discuss → local, plan → relay) — scaffolded but stub only.
- Tool call round-trip bench tests — Phase 4.
- Chunk buffering for TUI rendering — defer to Phase 5.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ROUT-01 | Connectivity probe runs on configurable interval, emits debounced connected/disconnected events | `asyncio.open_connection` + `asyncio.wait_for` for TCP probe; N-of-M debounce state machine; EventBus fan-out from Phase 1. See Architecture Patterns § Probe and Common Pitfalls § Flap. |
| ROUT-02 | Router dispatches to local model for all turns in v1.0; relay path stubbed | Stateless `route()` returning `AsyncIterator[str]`; cloud branch raises `NotImplementedError`. See Code Examples § Router Dispatch. |
| ROUT-03 | User connects to local Ollama with full streaming and `keep_alive=-1` warm-up | httpx `client.stream("POST", ...)` + `response.aiter_lines()`; warm-up as fire-and-forget task. See Code Examples § LocalModelClient.stream and § Warm-up. |
| ROUT-04 | User connects to LM Studio via configurable OpenAI-compatible base URL | Same `LocalModelClient` with different `base_url`. LM Studio implements `/v1/chat/completions` and `/v1/models` (verified — official docs). See Standard Stack § Ecosystem. |
| ROUT-05 | Local leader model has minimal, explicitly-defined tool surface — no arbitrary shell/file access | Tool registry with validation guards (D-08, D-10). Zero tools registered in Phase 3 — infrastructure only. See Architecture Patterns § Tool Registry. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Streaming chat with local model | Backend (client-side HTTP consumer) | — | Router owns the wire path; TUI is downstream consumer of the AsyncIterator. |
| Wire sanitisation (`to_wire`, strip `_model`) | Router | Session (owns Message model) | Single choke point at the HTTP boundary — never trust callers to strip. |
| Tool registry validation | Router / Tools sub-module | — | Registration-time validation; no runtime cost. |
| TCP connectivity probe | Probe (background task, peer to Router) | — | Independent producer; publishes to EventBus, doesn't call Router. |
| Connected/disconnected event fan-out | EventBus (Phase 1 primitive) | — | Existing async-queue-per-subscriber pattern; Router/TUI/QueueManager subscribe. |
| `probe.is_connected` cache | Probe | Router (reader only) | Probe owns state; Router reads directly per D-15 (avoids Router subscribing). |
| Model warm-up | LocalModelClient (startup) | — | Fire-and-forget task; not on the request path. |
| Model discovery (`list_models()`) | LocalModelClient | — | Exposed for Phase 4 bench suite. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | ^0.28 (0.28.1 current) | Async HTTP client for `/v1/chat/completions` and `/api/version` | Native async, streaming via `aiter_lines()` / `aiter_bytes()`, HTTP/2, one connection pool per client. Already pinned in Phase 1. `[VERIFIED: STACK.md § HTTP + Model APIs; python-httpx.org/quickstart#streaming-responses]` |
| `asyncio` (stdlib) | 3.11+ | Event loop, `TaskGroup`, `open_connection`, `wait_for`, cancellation | Everything runs on one loop. `TaskGroup` is the sanctioned way to spawn the probe alongside TUI. `[VERIFIED: docs.python.org/3.11/library/asyncio-task.html#task-groups]` |
| `pydantic` | ^2.13 | `Config`, `Message`, event dataclasses (or `@dataclass` for events) | Already in Phase 1/2. `[VERIFIED: STACK.md]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `json` | — | Parse SSE `data:` payloads and `/api/version` response | httpx doesn't auto-decode SSE JSON; parse per-line. `json.loads` is fine — chunks are small. |
| stdlib `dataclasses` | — | `ConnectedEvent`, `DisconnectedEvent` per D-16 | Zero-cost, no validation overhead. Pydantic would be overkill for two-field timestamp dataclasses. |
| stdlib `logging` | — | Probe transition logs (`INFO probe: connected` / `disconnected`) | Matches Phase 1 logging setup; `RichHandler` for TUI-friendly output. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw httpx SSE parse | `httpx-sse` | Adds a dep for a 15-line parser; OpenAI's SSE format is trivially handled with `aiter_lines()` + prefix strip. Rejected. |
| Raw httpx | `openai` SDK (`AsyncOpenAI`) | Adds a dep + its own retry/streaming abstraction; wire format is already OpenAI-compat; STACK.md explicitly deferred it. Rejected. |
| stdlib `dataclasses` for events | Pydantic BaseModel | No I/O for events (never JSON-serialised on the wire); dataclass is lighter. |
| `asyncio.open_connection` for TCP probe | httpx HEAD to a URL | ARCHITECTURE.md § Anti-Patterns explicitly prefers TCP: no HTTP overhead, no DNS complications, no captive-portal false positives on a probe host by IP. Also aligned with D-12. |
| N-of-M debounce | EWMA / hysteresis timer | PITFALLS.md Pitfall 4 recommends N-of-M as the simple robust choice; already codified in D-14. |

**Installation:** No new packages — all deps land in Phase 1's `pyproject.toml`.

**Version verification (2026-07-09):**
- `httpx` 0.28.1 — `[VERIFIED: pypi.org/project/httpx/]` released Dec 2024; `client.stream()` context manager and `aiter_lines()` unchanged since 0.24.
- `asyncio.TaskGroup` — `[VERIFIED: docs.python.org/3.11/library/asyncio-task.html#asyncio.TaskGroup]` added in 3.11.
- Ollama `/v1/chat/completions` — `[VERIFIED: github.com/ollama/ollama/blob/main/docs/openai.md]` official OpenAI-compat doc.
- LM Studio OpenAI-compat — `[CITED: lmstudio.ai/docs/api/openai-api]` implements `/v1/chat/completions`, `/v1/models`, streaming.

## Package Legitimacy Audit

Phase 3 introduces **no new external packages**. All runtime deps (`httpx`, `pydantic`, stdlib) are already vetted in Phase 1's `pyproject.toml`. Legitimacy audit deferred — nothing to install.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| (none — reuses Phase 1 deps) | — | — | — | — | — | — |

**Packages removed:** none. **Packages flagged:** none.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌──────────────────────────┐
                    │      TUI / CLI caller     │
                    └────────────┬─────────────┘
                                 │  await router.route(messages)
                                 ▼
                    ┌──────────────────────────┐
                    │       Router             │
                    │   (stateless dispatch)   │
                    │                          │
                    │   reads probe.is_connected
                    │   reads config.routing.mode
                    │                          │
                    │   phase_registry.policy_for()
                    │      │                   │
                    │      ├─ local → LocalModelClient
                    │      └─ cloud → NotImplementedError
                    └──────────────┬───────────┘
                                   │  async for chunk in ...
                                   ▼
                    ┌──────────────────────────┐
                    │   LocalModelClient       │
                    │   (one httpx.AsyncClient)│
                    │                          │
                    │   to_wire(messages)      │───► strips _model
                    │   inject stream:true     │
                    │   inject think:false     │───► only if tools present
                    │   POST /v1/chat/completions
                    │   aiter_lines → SSE parse│
                    │   yield delta content    │
                    └────────┬─────────────────┘
                             │
                             ▼
                    ┌──────────────────────────┐
                    │  Ollama or LM Studio     │
                    │  localhost:11434 or :1234│
                    └──────────────────────────┘

    ─── independent producer ──────────────────────────────

    ┌──────────────────────────┐
    │   Probe (bg task)        │  interval = config.probe.interval_seconds
    │                          │
    │   asyncio.open_connection│──► TCP :443 (fallback :80)
    │   asyncio.wait_for 3s    │
    │                          │
    │   N-of-M debounce (2/2)  │
    │   updates is_connected   │
    │                          │
    │   on transition:         │
    │      bus.publish(...)    │──► ConnectedEvent / DisconnectedEvent
    └──────────────────────────┘         │
                                         ▼
                              ┌────────────────────┐
                              │   EventBus (Phase1)│
                              │   fan-out to subs  │
                              └─────────┬──────────┘
                                        │
                          ┌─────────────┼─────────────┐
                          ▼             ▼             ▼
                     QueueMgr        Router        TUI status
                     (Phase 6)    (reads only)    (Phase 5)
```

### Recommended Project Structure

```
packages/client/src/cyberharness/
├── router/
│   ├── __init__.py           # exports Router, LocalModelClient
│   ├── router.py             # Router.route() — stateless dispatch
│   ├── local_client.py       # LocalModelClient (streaming, warm-up, version check, list_models)
│   ├── wire.py               # to_wire(messages) — strips _model, produces list[dict]
│   ├── registry.py           # phase_registry: policy_for(phase) → "local" | "cloud"
│   └── errors.py             # RouterError, RelayNotImplementedError, ToolRegistrationError
│
├── tools/
│   ├── __init__.py
│   └── registry.py           # ToolRegistry with D-08 name-param guard
│
└── probe/
    ├── __init__.py
    ├── probe.py              # Probe class: run(), is_connected, transition detection
    └── strategies.py         # tcp_probe(host, port, timeout) helper (leaves room for future DNS/HTTP)
```

### Pattern 1: httpx Streaming SSE (locked by D-04, D-05)

**What:** One `httpx.AsyncClient` per `LocalModelClient`, use `client.stream("POST", url, json=payload)` as an async context manager, iterate `response.aiter_lines()`, strip `data: ` prefix, break on `[DONE]`, `json.loads` remaining, yield delta content.

**When to use:** Every request to `/v1/chat/completions`. Non-streaming calls (warm-up, version check, list_models) use plain `client.post()` / `client.get()`.

**Example:**
```python
# Source: python-httpx.org/async — client.stream is documented as an async context manager
async with self.client.stream("POST", f"{self.base_url}/v1/chat/completions", json=payload) as response:
    response.raise_for_status()
    async for line in response.aiter_lines():
        if not line or not line.startswith("data: "):
            continue
        payload_str = line.removeprefix("data: ")
        if payload_str == "[DONE]":
            break
        try:
            chunk = json.loads(payload_str)
        except json.JSONDecodeError:
            log.warning("skip malformed SSE line", extra={"line": payload_str[:200]})
            continue
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        content = delta.get("content")
        if content:
            yield content
```

**Key notes:**
- `aiter_lines()` handles line buffering across TCP chunks — this is the fix for PITFALLS.md Pitfall 5 (fragmented SSE frames). `[VERIFIED: python-httpx.org/quickstart/#streaming-responses]`
- `response.raise_for_status()` inside the context manager surfaces 5xx before we start iterating.
- `str.removeprefix("data: ")` (3.9+) is safer than slicing — no-op if the prefix is absent.
- Empty lines (`""`) between SSE frames are expected and skipped by the `if not line` guard.

### Pattern 2: TCP Probe with Timeout + Cleanup

**What:** `asyncio.open_connection(host, port)` returns `(reader, writer)`. Wrap in `asyncio.wait_for(..., timeout=3)`. Close in a `finally` block: `writer.close(); await writer.wait_closed()`.

**When to use:** Every probe interval tick.

**Example:**
```python
# Source: docs.python.org/3/library/asyncio-stream.html
async def tcp_probe(host: str, port: int, timeout: float) -> bool:
    writer = None
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        return True
    except (asyncio.TimeoutError, OSError):
        return False
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass  # best-effort cleanup — connection may already be reset
```

**Key notes:**
- `writer.wait_closed()` may itself raise if the peer RST'd; swallow — the probe result is already known.
- Fallback to port 80 is a second call if port 443 times out (per D-12). Only try 80 on a 443 timeout, not on other exceptions (e.g., connection refused is a real "up but no service").

### Pattern 3: N-of-M Debounce State Machine

**What:** Maintain `success_count` and `failure_count`. On each probe: increment the matching counter, reset the other. Transition state only when counter reaches `confirm_count` (2).

**When to use:** Every probe result — before publishing an event or updating `is_connected`.

**Example:**
```python
# Source: PITFALLS.md Pitfall 4 recommendation, encoded as a small state machine
class DebounceGate:
    def __init__(self, confirm_count: int = 2, initial: bool = False):
        self.state = initial
        self.confirm = confirm_count
        self.success_count = 0
        self.failure_count = 0

    def observe(self, ok: bool) -> bool | None:
        """Return the new state if it transitioned; None otherwise."""
        if ok:
            self.success_count += 1
            self.failure_count = 0
            if not self.state and self.success_count >= self.confirm:
                self.state = True
                return True
        else:
            self.failure_count += 1
            self.success_count = 0
            if self.state and self.failure_count >= self.confirm:
                self.state = False
                return False
        return None
```

**Key notes:**
- Discretion point (D-14 corollary): default `initial=False`. Router in "All Local" mode ignores it anyway; "Wait for Online" mode gets an accurate first reading within `2 * interval_seconds` seconds.

### Pattern 4: EventBus Fan-Out (from Phase 1)

**What:** Probe calls `await bus.publish(ConnectedEvent(timestamp=time.time()))`. Bus pushes to each subscriber's `asyncio.Queue`. Publish is non-blocking (or blocks only briefly on `Queue.put`).

**When to use:** On every debounced state transition — never on every probe sample.

**Example:**
```python
# Source: ARCHITECTURE.md § EventBus — asyncio.Queue per subscriber
transition = self.gate.observe(ok)
if transition is True:
    log.info("probe: connected")
    await self.bus.publish(ConnectedEvent(timestamp=time.time()))
elif transition is False:
    log.info("probe: disconnected")
    await self.bus.publish(DisconnectedEvent(timestamp=time.time()))
```

**Key notes:**
- Publisher never `await`s a subscriber's handler — the bus is fire-and-forget from the probe's perspective. Router reads `probe.is_connected` directly per D-15, so Router isn't a subscriber.

### Anti-Patterns to Avoid

- **Creating a new `httpx.AsyncClient` per request** — blows connection pooling, adds TLS handshake to every call. (ARCHITECTURE.md Anti-Pattern 2, D-05.)
- **Reading `probe.is_connected` inside the middle of a stream** — the flag can change mid-turn. Read once at the start of `route()` and commit to that path for the whole stream.
- **Blocking the loop with sync HTTP or sync `socket.connect`** — use `asyncio.open_connection`, never `socket.create_connection` in the loop. (PITFALLS.md Pitfall 1.)
- **Passing raw `Message` dicts with `_model` to `client.post`** — always route through `to_wire()`. (PITFALLS.md Pitfall 2, D-09.)
- **Assuming SSE frames == TCP chunks** — always use `aiter_lines()`, never parse `aiter_bytes()` chunks directly. (PITFALLS.md Pitfall 5.)
- **Emitting events on every probe sample** — only on debounced transitions. (D-14, D-16.)
- **Enqueueing on probe failure** — no relay in Phase 3, so probe state is informational only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE line reassembly across TCP chunks | Byte-buffer + `\n\n` splitter | `response.aiter_lines()` from httpx | httpx already does this correctly. Rolling your own is Pitfall 5. |
| Async HTTP connection pooling | Manual socket management | `httpx.AsyncClient` | HTTP/1.1 keep-alive, HTTP/2 multiplexing, TLS session reuse — all free. |
| TCP timeout | `signal.alarm` or a manual timer task | `asyncio.wait_for` | Cancellation is composable with the rest of the loop. |
| Debounce | Sliding-window average, timers, EWMA | 20-line N-of-M state machine | We only need "state = ok for 2 samples in a row." Anything more is overfitting. |
| OpenAI-compat JSON schema validation | Hand-rolled dict access | `chunk["choices"][0]["delta"].get("content")` | Provider variations exist (LM Studio may omit `content` on tool-only deltas); tolerant dict access is enough. |
| Semver comparison for Ollama version | Regex + manual tuple compare | `packaging.version.Version` (stdlib-adjacent via pydantic dep tree) or a 5-line tuple parse | Ollama's `/api/version` returns `{"version": "0.30.12"}` — a `tuple(int(p) for p in v.split("."))` works and needs no new dep. |
| Retry on transient Ollama loading errors | Custom retry loop | `tenacity` (already in STACK.md if needed) | Discretion — the CONTEXT.md says exact retry behaviour is Claude's discretion. Prefer no retry for streaming (surface the error to the user) but tenacity is available if we add retries. |

**Key insight:** The whole phase is a thin wrapper. Every "novel" piece (SSE parse, TCP probe, debounce, event fan-out) already has a canonical stdlib or httpx form.

## Common Pitfalls

### Pitfall 1: SSE parsing that fragments on real networks
**What goes wrong:** Parsing `aiter_bytes()` chunks as JSON directly. On real TCP, one SSE frame arrives split across two chunks (or two frames concatenated in one).
**Why it happens:** localhost testing is chunk-aligned; the real world isn't.
**How to avoid:** `aiter_lines()` always, never `aiter_bytes()` for line-oriented protocols. `[CITED: PITFALLS.md § Pitfall 5]`
**Warning signs:** Intermittent `JSONDecodeError`; last tokens missing on cellular but fine on WiFi.

### Pitfall 2: `_model` leaking to the wire
**What goes wrong:** Ollama silently accepts it; LM Studio and OpenAI-compat proxies may 400 or bill it as content.
**Why it happens:** Session model stores `_model` per D-18 (Phase 2). Devs forget the strip step.
**How to avoid:** `to_wire(messages)` is the single choke point (D-09). Unit test asserts no `_`-prefixed keys survive.
**Warning signs:** 400 errors on the first LM Studio integration test; unexpected token counts.

### Pitfall 3: Connectivity flap without debounce
**What goes wrong:** On marginal networks, rapid probe toggling triggers repeated event fan-out; downstream subscribers (QueueMgr later, Router-status displays) thrash.
**Why it happens:** Naive edge trigger with no debounce.
**How to avoid:** N-of-M gate with `confirm_count=2` (D-14). Only publish on transitions the gate confirms.
**Warning signs:** Log spam of "probe: connected" / "probe: disconnected" every interval.

### Pitfall 4: Cold-start silence on first message
**What goes wrong:** Ollama takes 15-45s to load the model into VRAM on first `/v1/chat/completions`. User sees a frozen UI.
**Why it happens:** Cold start; model evicted after `keep_alive` default of 5 min.
**How to avoid:** Warm-up POST on startup with `keep_alive: -1` (D-06). Empty `messages: []` and `stream: false` — the call returns almost immediately with a "no messages" error but the *side effect* of loading the model is what we want. Fire-and-forget (`asyncio.create_task`) — don't block startup.
**Warning signs:** First turn slow, subsequent turns fast. `[CITED: PITFALLS.md § Pitfall 7]`
**Note on `keep_alive: -1`:** The Ollama OpenAI-compat endpoint accepts non-standard fields in the request body — `keep_alive` is one such Ollama extension. `[VERIFIED: github.com/ollama/ollama/blob/main/docs/openai.md — the doc explicitly lists supported extensions including keep_alive]`

### Pitfall 5: Empty `messages: []` warm-up may error
**What goes wrong:** Depending on Ollama version, empty messages may reject with 400. Warm-up fails but the model still loads (side effect).
**How to avoid:** Wrap warm-up in `try/except httpx.HTTPStatusError` — log at DEBUG, don't crash. Alternative: send `{"messages": [{"role": "user", "content": "."}], "stream": false, "keep_alive": -1, "max_tokens": 1}` — a real 1-token call that guarantees load. Discretion call; the 1-token variant is safer.

### Pitfall 6: `writer.wait_closed()` hanging on RST
**What goes wrong:** After a TCP probe against a firewalled port that RSTs, `writer.wait_closed()` can hang or raise.
**How to avoid:** Wrap `wait_closed()` in its own `try/except` inside the `finally`; probe result is already known before cleanup.

### Pitfall 7: `/api/version` missing on LM Studio
**What goes wrong:** LM Studio doesn't implement `/api/version` — it's an Ollama-native endpoint. Version check crashes.
**How to avoid:** Catch `httpx.HTTPStatusError` (404) and `httpx.RequestError`, log DEBUG, skip. Version check is Ollama-only advisory (D-11). Detect backend by probing `/api/version` at startup — presence = Ollama, absence = LM Studio or unknown. `[VERIFIED: lmstudio.ai/docs/api — no /api/version endpoint listed]`

### Pitfall 8: Reading `probe.is_connected` mid-stream
**What goes wrong:** Value can flip between chunks; behaviour ambiguous.
**How to avoid:** Router reads once at `route()` entry (D-15) and commits to that dispatch. The stream itself never re-checks connectivity.

### Pitfall 9: `list_models()` differences between Ollama and LM Studio
**What goes wrong:** `/v1/models` returns different `id` conventions (Ollama: `llama3.2:3b-instruct-q4_K_M`; LM Studio: model path or slug). Downstream (Phase 4 bench) needs a stable id.
**How to avoid:** Return raw model ids as-is; document the format quirks. Phase 4 already has to handle the difference by design. `[VERIFIED: github.com/ollama/ollama/blob/main/docs/openai.md § /v1/models]`

### Pitfall 10: NotImplementedError inside an AsyncIterator
**What goes wrong:** Raising `NotImplementedError` inside an `async def` that's declared to return `AsyncIterator[str]` — if the function has no `yield`, it's not a generator, and the caller's `async for` never runs (returns immediately with no exception).
**How to avoid:** Structure the cloud stub as a plain `raise` at the top of `route()` (before any `yield`), or make it a helper `_route_cloud` that raises immediately. The `raise` fires when the coroutine is called, not when iteration starts. Explicitly test: `with pytest.raises(NotImplementedError): async for _ in router.route(msgs): ...`.

## Runtime State Inventory

Phase 3 is a **greenfield** addition (no rename/refactor of prior state). Section omitted.

## Code Examples

### LocalModelClient — full skeleton
```python
# Source: composition of D-02, D-04, D-05, D-06, D-09, D-10, D-11, D-12 (part-Ollama), plus PITFALLS.md § 5, § 7
import asyncio
import json
import time
import logging
from typing import AsyncIterator, Optional

import httpx

log = logging.getLogger(__name__)

class LocalModelClient:
    def __init__(self, base_url: str, model: str, tools: Optional[list] = None, headers: Optional[dict] = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.tools = tools or []
        # One client, process lifetime. httpx handles pooling.
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers or {},
            timeout=httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0),
        )

    async def close(self) -> None:
        await self.client.aclose()

    def _build_payload(self, wire_messages: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "messages": wire_messages,
            "stream": True,  # D-10: always inject
        }
        if self.tools:
            payload["tools"] = self.tools
            payload["think"] = False  # D-10: Ollama parser bug guard (TODO-001 §2)
        return payload

    async def stream(self, wire_messages: list[dict]) -> AsyncIterator[str]:
        payload = self._build_payload(wire_messages)
        async with self.client.stream("POST", "/v1/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ")
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    log.warning("skip malformed SSE line", extra={"snippet": data[:200]})
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                content = choices[0].get("delta", {}).get("content")
                if content:
                    yield content

    async def warm_up(self) -> None:
        """Fire-and-forget: preload model into VRAM. keep_alive=-1 pins it."""
        try:
            await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "."}],
                    "stream": False,
                    "max_tokens": 1,
                    "keep_alive": -1,  # Ollama extension; LM Studio ignores unknown fields silently.
                },
                timeout=60.0,  # warm-up may take long on cold VRAM
            )
        except httpx.HTTPError as e:
            log.debug("warm-up failed (non-fatal): %s", e)

    async def check_version(self) -> None:
        """Ollama-only advisory. LM Studio has no /api/version — log and skip."""
        try:
            r = await self.client.get("/api/version", timeout=3.0)
            r.raise_for_status()
        except httpx.HTTPError:
            log.debug("no /api/version — probably LM Studio")
            return
        version_str = r.json().get("version", "0.0.0")
        try:
            parts = tuple(int(p) for p in version_str.split(".")[:3])
            if parts < (0, 30, 12):
                log.warning(
                    "ollama %s < 0.30.12 — brace-detection tool-call bug present. TODO-001 §3.",
                    version_str,
                )
        except ValueError:
            log.debug("unparseable ollama version: %s", version_str)

    async def list_models(self) -> list[dict]:
        """Returns list of {id, ...} dicts. Uses /v1/models for portability."""
        r = await self.client.get("/v1/models", timeout=5.0)
        r.raise_for_status()
        return r.json().get("data", [])
```

### Router — full skeleton
```python
# Source: D-01, D-15, D-17, D-18, Pitfall 10
from typing import AsyncIterator

from ..probe import Probe
from ..config import Config
from ..session.models import Message
from .local_client import LocalModelClient
from .wire import to_wire
from .errors import RelayNotImplementedError

class Router:
    def __init__(self, config: Config, local: LocalModelClient, probe: Probe):
        self.config = config
        self.local = local
        self.probe = probe

    async def route(self, messages: list[Message]) -> AsyncIterator[str]:
        wire_messages = to_wire(messages)  # D-09: single choke point
        # D-17/D-18: in v1.0 always local. "Wait for Online" mode reads is_connected
        # but still routes local until relay ships.
        policy = "local"  # phase_registry stub — hardcoded for Phase 3
        if policy == "cloud":
            raise RelayNotImplementedError("relay not yet implemented")
        async for chunk in self.local.stream(wire_messages):
            yield chunk
```

### to_wire — sanitiser
```python
# Source: D-09
from ..session.models import Message

WIRE_ALLOWED = {"role", "content", "name", "tool_calls", "tool_call_id"}

def to_wire(messages: list[Message]) -> list[dict]:
    """Strip _model and any other harness-internal fields.
    Returns a fresh list of dicts safe to send to any OpenAI-compat endpoint."""
    out = []
    for m in messages:
        raw = m.model_dump(exclude_none=True) if hasattr(m, "model_dump") else dict(m)
        out.append({k: v for k, v in raw.items() if k in WIRE_ALLOWED})
    return out
```

### Probe — full skeleton
```python
# Source: D-12, D-13, D-14, D-15, D-16 + Pattern 2 + Pattern 3
import asyncio
import time
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

@dataclass
class ConnectedEvent:
    timestamp: float

@dataclass
class DisconnectedEvent:
    timestamp: float

async def tcp_probe(host: str, port: int, timeout: float) -> bool:
    writer = None
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        return True
    except (asyncio.TimeoutError, OSError):
        return False
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

class Probe:
    def __init__(self, config, bus, initial: bool = False):
        self.host = config.probe.probe_host
        self.interval = config.probe.interval_seconds
        self.confirm = getattr(config.probe, "confirm_count", 2)
        self.bus = bus
        self.is_connected = initial
        self._success = 0
        self._failure = 0

    async def _check_once(self) -> bool:
        ok = await tcp_probe(self.host, 443, timeout=3.0)
        if not ok:
            ok = await tcp_probe(self.host, 80, timeout=3.0)  # D-12 fallback
        return ok

    def _observe(self, ok: bool) -> bool | None:
        if ok:
            self._success += 1
            self._failure = 0
            if not self.is_connected and self._success >= self.confirm:
                self.is_connected = True
                return True
        else:
            self._failure += 1
            self._success = 0
            if self.is_connected and self._failure >= self.confirm:
                self.is_connected = False
                return False
        return None

    async def run(self) -> None:
        while True:
            try:
                ok = await self._check_once()
                transition = self._observe(ok)
                if transition is True:
                    log.info("probe: connected")
                    await self.bus.publish(ConnectedEvent(timestamp=time.time()))
                elif transition is False:
                    log.info("probe: disconnected")
                    await self.bus.publish(DisconnectedEvent(timestamp=time.time()))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("probe iteration failed")
            await asyncio.sleep(self.interval)
```

### Tool registry with name-param guard (D-08)
```python
# Source: D-08, TODO-001 §1
class ToolRegistrationError(ValueError):
    pass

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, tool: dict) -> None:
        params = tool.get("function", {}).get("parameters", {}).get("properties", {})
        if "name" in params:
            raise ToolRegistrationError(
                f"tool {tool.get('function', {}).get('name', '?')} has parameter 'name' — "
                "Ollama bug #16932 silently drops tool calls with this key. Rename to "
                "'value', 'query', 'text', etc."
            )
        self._tools[tool["function"]["name"]] = tool

    def all(self) -> list[dict]:
        return list(self._tools.values())
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ollama's `/api/chat` NDJSON stream | Ollama's `/v1/chat/completions` OpenAI-compat SSE | Ollama 0.1.16+ (2024) | One code path shared with LM Studio and future relay. Chosen per D-02. `[VERIFIED: github.com/ollama/ollama/blob/main/docs/openai.md]` |
| `openai` SDK for OpenAI-compat endpoints | Raw `httpx` streaming | STACK.md deferred SDK | 40-line wrapper, no dep bloat. |
| ICMP `ping` for connectivity | TCP connect probe | STACK.md § Connectivity Probe | No root/capability requirements on Linux. |
| Global `AsyncClient` shared across services | One client per service | ARCHITECTURE.md Anti-Pattern 2 | Different timeouts, base URLs, headers per service. |

**Deprecated/outdated:**
- `requests`, sync `ollama` Python client — sync, blocks event loop. Never use in this codebase.
- `aiter_bytes()` for SSE — use `aiter_lines()`. `[VERIFIED: PITFALLS.md § Pitfall 5]`

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Ollama's `/v1/chat/completions` accepts `keep_alive` in the request body (not just the native `/api/chat`) | Pitfall 4, Warm-up code example | Warm-up would fail to pin the model; model would still load as side effect on first real call. Documented in Ollama's OpenAI-compat notes but LM Studio behaviour is untested — LM Studio silently ignores unknown fields per OpenAI convention, which is safe. |
| A2 | `writer.wait_closed()` may hang or raise on RST; swallow in `finally` | Pitfall 6 | If wrong, we're just being cautious with a working call — no downside. |
| A3 | LM Studio has no `/api/version` endpoint | Pitfall 7, `check_version` code | If wrong, we'd log DEBUG unnecessarily. Verified against lmstudio.ai/docs/api which lists OpenAI-compat routes only. |
| A4 | `/v1/models` works on both Ollama and LM Studio and returns `{"data": [...]}` | `list_models` code | LM Studio and Ollama both document this endpoint; format is OpenAI standard. Low risk. |
| A5 | `packaging.version` is available (pydantic transitive) | Version check code | Sidestepped by using tuple parse instead — no extra dep needed. |
| A6 | `httpx.Timeout(read=None)` allows indefinite streaming reads without triggering a read timeout | LocalModelClient init | Verified in httpx docs — `None` means no timeout. Alternative is a large finite read timeout (e.g., 600s). |

**Nothing in this table blocks the phase — all A-items are graceful-degradation cases with clear fallbacks.**

## Open Questions

1. **Should warm-up send `messages: []` or a real 1-token call?**
   - What we know: `keep_alive: -1` is the load-and-pin signal; both variants trigger it.
   - What's unclear: whether some Ollama versions reject empty messages arrays with 400 before doing the load.
   - Recommendation: use the 1-token variant (`[{"role":"user","content":"."}], max_tokens:1`) — costs ~2 tokens of local inference for guaranteed load. Wrap in try/except regardless.

2. **What is `probe.is_connected` before the first check completes?**
   - What we know: CONTEXT.md flags this as Claude's discretion.
   - What's unclear: whether TUI status bar (Phase 5) needs a distinct "unknown" state.
   - Recommendation: default `False`. Router in "All Local" mode ignores it; "Wait for Online" mode gets an accurate reading within `2 * interval_seconds` (≤ 60s default). Distinct "unknown" is unnecessary UI complexity for v1.0.

3. **Retry behaviour on `httpx.ConnectError` from LocalModelClient?**
   - What we know: Discretion per CONTEXT.md.
   - What's unclear: whether Ollama in the middle of a swap/upgrade merits an inline retry.
   - Recommendation: no automatic retry in Phase 3 — surface the error to the caller. The user sees "connection refused" immediately rather than a mysterious 30s hang. Add tenacity-based retry only if operator feedback demands it.

## Environment Availability

| Dependency | Required By | Available (aarch64/dev) | Version | Fallback |
|------------|-------------|-------------------------|---------|----------|
| `httpx` | LocalModelClient, warm-up, version check, list_models | ✓ (Phase 1) | ^0.28 | — |
| Python 3.11+ | `TaskGroup`, `str.removeprefix` | ✓ (Phase 1) | ≥3.11 | — |
| Ollama running at `local_url` | Actual streaming | ✗ at build time | 0.30.12+ recommended | Client tolerates absence: warm-up fails at DEBUG log, first real `route()` call raises `httpx.ConnectError` — user-visible. |
| LM Studio at `local_url` | Alternative backend | ✗ at build time | Any current | Same OpenAI-compat surface; same tolerance. |
| Network reachability to `probe_host` | Probe truthful signal | ✗ deterministic | — | Probe returns False on all failures; N-of-M eventually settles disconnected. No crash. |

**Missing dependencies with no fallback:** none — Phase 3 tolerates all runtime absences with graceful error surfaces.

**Missing dependencies with fallback:** Ollama absent → user gets a clear `httpx.ConnectError` on first turn (Phase 5 TUI is responsible for the actionable error UX per PITFALLS.md § UX). LM Studio absent → same.

## Validation Architecture

*Config file `.planning/config.json` not present — treating `workflow.nyquist_validation` as enabled (default).*

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` + `pytest-asyncio` (Phase 1 dev deps) |
| Config file | `packages/client/pyproject.toml` (Phase 1 `[tool.pytest.ini_options]`) or `pytest.ini` |
| Quick run command | `pytest packages/client/tests/router -x --tb=short` |
| Full suite command | `pytest packages/client/tests -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ROUT-01 | Probe emits ConnectedEvent after 2 consecutive successful TCP probes | unit | `pytest packages/client/tests/probe/test_probe.py::test_debounce_connected -x` | ❌ Wave 0 |
| ROUT-01 | Probe emits DisconnectedEvent after 2 consecutive failed TCP probes | unit | `pytest packages/client/tests/probe/test_probe.py::test_debounce_disconnected -x` | ❌ Wave 0 |
| ROUT-01 | Probe interval honoured; interval-driven publish rate | unit | `pytest packages/client/tests/probe/test_probe.py::test_interval -x` | ❌ Wave 0 |
| ROUT-01 | Probe falls back to port 80 when 443 times out | unit | `pytest packages/client/tests/probe/test_probe.py::test_port_fallback -x` | ❌ Wave 0 |
| ROUT-02 | Router dispatches to LocalModelClient always in v1.0 | unit | `pytest packages/client/tests/router/test_router.py::test_dispatch_local -x` | ❌ Wave 0 |
| ROUT-02 | Router.route() raises NotImplementedError on cloud policy (via forced stub) | unit | `pytest packages/client/tests/router/test_router.py::test_cloud_stub_raises -x` | ❌ Wave 0 |
| ROUT-03 | LocalModelClient streams tokens via aiter_lines and strips `data: ` | unit | `pytest packages/client/tests/router/test_local_client.py::test_stream_parses_sse -x` | ❌ Wave 0 |
| ROUT-03 | LocalModelClient handles `[DONE]` sentinel | unit | `pytest packages/client/tests/router/test_local_client.py::test_stream_done_sentinel -x` | ❌ Wave 0 |
| ROUT-03 | LocalModelClient handles fragmented SSE chunks (respx-injected) | unit | `pytest packages/client/tests/router/test_local_client.py::test_stream_fragmented -x` | ❌ Wave 0 |
| ROUT-03 | Warm-up POSTs with `keep_alive: -1` (mocked) | unit | `pytest packages/client/tests/router/test_local_client.py::test_warm_up_keep_alive -x` | ❌ Wave 0 |
| ROUT-03 | Version check warns below 0.30.12 (caplog) | unit | `pytest packages/client/tests/router/test_local_client.py::test_version_warn -x` | ❌ Wave 0 |
| ROUT-03 | Version check tolerates missing /api/version (LM Studio) | unit | `pytest packages/client/tests/router/test_local_client.py::test_version_missing_ok -x` | ❌ Wave 0 |
| ROUT-04 | LocalModelClient works against LM Studio base_url with same code path | integration (mocked base_url) | `pytest packages/client/tests/router/test_local_client.py::test_lmstudio_base_url -x` | ❌ Wave 0 |
| ROUT-05 | `to_wire()` strips `_model` from every message | unit | `pytest packages/client/tests/router/test_wire.py::test_strips_model_field -x` | ❌ Wave 0 |
| ROUT-05 | Tool registry rejects `name` parameter | unit | `pytest packages/client/tests/tools/test_registry.py::test_rejects_name_param -x` | ❌ Wave 0 |
| ROUT-05 | `think: false` injected when tools present | unit | `pytest packages/client/tests/router/test_local_client.py::test_think_false_with_tools -x` | ❌ Wave 0 |
| ROUT-05 | Zero tools registered by default in Phase 3 | unit | `pytest packages/client/tests/tools/test_registry.py::test_empty_by_default -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest packages/client/tests/router -x --tb=short` (subsecond on unit tests with respx)
- **Per wave merge:** `pytest packages/client/tests -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `packages/client/tests/probe/test_probe.py` — probe debounce, interval, port fallback (ROUT-01)
- [ ] `packages/client/tests/router/test_router.py` — dispatch, cloud stub (ROUT-02)
- [ ] `packages/client/tests/router/test_local_client.py` — streaming, warm-up, version, tools (ROUT-03, ROUT-04, ROUT-05)
- [ ] `packages/client/tests/router/test_wire.py` — sanitiser (ROUT-05)
- [ ] `packages/client/tests/tools/test_registry.py` — registration guards (ROUT-05)
- [ ] `packages/client/tests/conftest.py` — shared fixtures: `respx_mock`, fake `EventBus`, fake `Config`
- [ ] dev dep install: `uv add --dev respx` — httpx-native mock library (well maintained, aarch64-clean; standard httpx testing tool). Verify slop status before install.

## Security Domain

`security_enforcement` config not explicitly false — including this section.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local endpoints have no auth in v1.0; LM Studio and Ollama bind localhost. Relay auth is v1.1. |
| V3 Session Management | no | No user sessions on the wire. Filesystem session state is Phase 2's concern. |
| V4 Access Control | no | Single-user tool; no multi-tenancy. |
| V5 Input Validation | yes | `to_wire()` acts as an allowlist filter (only `WIRE_ALLOWED` keys pass). Config validated via pydantic (Phase 1). |
| V6 Cryptography | no | No crypto in Phase 3 — no keys, no signed payloads. HTTPS to relay is v1.1. |
| V10 Malicious Code | yes | Tool registry validates registration to prevent bug-triggering shapes. |

### Known Threat Patterns for Python asyncio + httpx + local LLM

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via message content | Tampering | Out of scope for Phase 3 (no tool execution in this phase); relevant when tools are added in v1.2. |
| SSRF via user-supplied `base_url` in config | Tampering / Info Disclosure | Config comes from local TOML file, not user input at runtime. Pydantic-validated. `follow_redirects=False` on httpx client (implicit — httpx does not follow redirects by default on stream requests). |
| Loop-blocking DoS via sync I/O in async context | Denial of Service | httpx async client only; `asyncio.open_connection` for probe; no `socket`/`requests`. Enforced by convention + PITFALLS.md § 1. |
| Log leaks of prompt content | Info Disclosure | `to_wire` never logged at INFO; log DEBUG only when explicitly enabled. No keys involved in Phase 3 (all local). |
| Ollama tool-call parser bugs (TODO-001) | Tampering / DoS | D-08/D-10 registry guards + `think: false` injection. |

## Sources

### Primary (HIGH confidence)
- Ollama OpenAI-compatibility docs — `github.com/ollama/ollama/blob/main/docs/openai.md` — confirms `/v1/chat/completions`, `/v1/models`, `keep_alive` extension in body.
- LM Studio API docs — `lmstudio.ai/docs/api/openai-api` — confirms `/v1/chat/completions`, `/v1/models`, streaming; no `/api/version`.
- httpx docs — `python-httpx.org/quickstart/#streaming-responses` and `python-httpx.org/async` — confirms `client.stream()` context manager, `aiter_lines()` line buffering.
- Python asyncio docs — `docs.python.org/3.11/library/asyncio-stream.html` (`open_connection`) and `docs.python.org/3.11/library/asyncio-task.html` (`wait_for`, `TaskGroup`).
- `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` — project canonical research.
- `.planning/todos/pending/TODO-001-ollama-tool-bugs.md` — enumerated Ollama tool-call parser bugs and required guards.

### Secondary (MEDIUM confidence)
- Prior Phase CONTEXT.md files (01, 02) — locked decisions on Config, Paths, EventBus, Message model.

### Tertiary (LOW confidence)
- None used — no unverified WebSearch findings in this research.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every dep already vetted in Phase 1 STACK.md; no new dependencies.
- Architecture: HIGH — patterns from ARCHITECTURE.md, all locked by CONTEXT.md decisions.
- Pitfalls: HIGH — inherit from PITFALLS.md § 1, 2, 4, 5, 7, 11 + TODO-001; a few new Phase-3-specific ones (Pitfall 5 empty-messages warm-up, Pitfall 10 NotImplementedError-in-async-generator) flagged with rationale.
- Ollama `/v1` body extensions (`keep_alive`): MEDIUM — documented, but Ollama's OpenAI-compat surface has historical quirks per PITFALLS.md § Integration Gotchas. A1 flags this.
- LM Studio behaviour: MEDIUM — verified against docs but not against a live instance in this research pass.

**Research date:** 2026-07-09
**Valid until:** 2026-08-09 (30 days — httpx/asyncio stable; Ollama moves faster so re-check `/api/version` and OpenAI-compat quirks if this phase slips beyond 4 weeks).
