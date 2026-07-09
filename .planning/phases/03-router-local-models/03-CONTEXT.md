# Phase 3: Router + Local Models - Context

**Gathered:** 2026-07-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 delivers a stateless router that streams every conversation turn to a local model (Ollama or LM Studio) via httpx, plus a connectivity probe that runs on an interval and publishes debounced connected/disconnected events to the EventBus.

**No relay in Phase 3.** The relay path is removed entirely — Phase 3 assumes direct local connection only. Relay is v1.1.

**No tools in Phase 3.** The tool registry infrastructure is created but zero tools are registered. Tools are added in v1.2.

</domain>

<decisions>
## Implementation Decisions

### Router & Wire Format
- **D-01:** Router interface: `async def route(messages: list[Message]) -> AsyncIterator[str]`. Phase removes the `phase` parameter — in v1.0 local-only mode, all turns go to the same local backend regardless of phase. Phase-based routing is v1.1+.
- **D-02:** Use Ollama's `/v1/chat/completions` OpenAI-compatible endpoint — same endpoint shape as LM Studio. One client (`LocalModelClient`) handles both; config sets `local_url` per backend.
- **D-03:** No separate `LmStudioClient`. A single `LocalModelClient` with configurable `base_url`, `model`, and optional headers covers both Ollama and LM Studio.
- **D-04:** SSE parsing via `response.aiter_lines()` — strip `data: ` prefix, parse JSON delta, yield `delta["choices"][0]["delta"]["content"]`. Skip `[DONE]` sentinel and lines without `data:` prefix.
- **D-05:** One `httpx.AsyncClient` instance per `LocalModelClient`, scoped to the process lifetime. Created at startup; closed on shutdown. Never create a new client per request.
- **D-06:** Ollama model warm-up on startup: POST `/v1/chat/completions` with `{"keep_alive": -1, "messages": [], "stream": false}` to pin the model in VRAM. Non-blocking — run as a background task; chat can start before warm-up completes.

### Tool Registry & Guards (from TODO-001)
- **D-07:** Zero tools registered in Phase 3. Tool registry is infrastructure only.
- **D-08:** Tool registry validates at registration time: reject any tool whose parameters include a key named `"name"` (Ollama bug #16932 guard). Raise `ToolRegistrationError` with a clear message.
- **D-09:** `to_wire(messages)` sanitiser strips the `_model` field from every Message before any HTTP send. Single choke point — never send raw Message objects to any API.
- **D-10:** `LocalModelClient` always injects `"stream": true` in the request body. Always injects `"think": false` when any tools are present (Ollama bug guard — even though Phase 3 has no tools, the guard is baked in for when tools are added in v1.2).
- **D-11:** Ollama version check at startup: GET `/api/version`, parse semver, warn if `< 0.30.12` (brace-detection bug). Non-blocking warning — does not prevent startup.

### Connectivity Probe
- **D-12:** Probe checks TCP connect to `config.probe.probe_host:443`, timeout 3s. Implemented as `asyncio.open_connection(host, 443)`. Falls back to port 80 if 443 times out (one extra attempt). No ICMP, no `ping` — requires no root privileges.
- **D-13:** Probe runs as a background `asyncio.Task` in the `TaskGroup` (from Phase 1 architecture). Interval from `config.probe.interval_seconds` (default 30).
- **D-14:** Debounce: N-of-M with `confirm_count = 2`. State changes from disconnected → connected only after 2 consecutive successes. State changes from connected → disconnected only after 2 consecutive failures. Config: `config.probe.confirm_count = 2`.
- **D-15:** Probe maintains `probe.is_connected: bool` (cached from its own EventBus events). Router reads `probe.is_connected` directly on each `route()` call — no subscription needed in the router.
- **D-16:** Probe publishes `ConnectedEvent` / `DisconnectedEvent` to the EventBus (from Phase 1). Events are dataclasses: `@dataclass class ConnectedEvent: timestamp: float` and `@dataclass class DisconnectedEvent: timestamp: float`.

### Phase Routing (v1.0 local-only simplification)
- **D-17:** In Phase 3, `route()` always dispatches to `LocalModelClient` regardless of the `phase` argument. The phase registry (local vs cloud routing policy) is scaffolded but the cloud branch raises `NotImplementedError("relay not yet implemented")`. This keeps the interface stable for v1.1 without adding dead code paths.
- **D-18:** `All Local` mode: always uses local model, ignores `probe.is_connected`.  `Wait for Online` mode (Phase 3 behavior): if `probe.is_connected` is True, route to local (still local-only in Phase 3 — the online path will use the relay in v1.1). Mode read from `config.routing.mode`.

### Folded Todos
- **TODO-001 (Guard against Ollama tool use parser bugs):** Folded into this phase. Guards D-08 (parameter name validation), D-09 (to_wire sanitiser), D-10 (think:false injection), D-11 (version check) implement the required mitigations. The bench suite integration (tool call round-trip tests) is deferred to Phase 4.

### Claude's Discretion
- Whether to buffer chunks before yielding (50ms debounce for TUI rendering) — implement if TUI flickering is observed in Phase 5; default is yield each token immediately
- Exact retry/backoff behavior for transient Ollama connection errors (e.g., model still loading)
- Whether `probe.is_connected` defaults to `True` or `False` on startup before first check completes

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design Docs
- `docs/architecture.md` — Router component spec, EventBus, OllamaClient / ClaudeClient interfaces, `to_wire()` requirement
- `.planning/research/ARCHITECTURE.md` — Router dispatch pseudocode, one-client-per-service rule (Anti-Pattern 2), probe event flow
- `.planning/research/PITFALLS.md` — Pitfall 1 (sync I/O in TUI), Pitfall 2 (`_model` leaking to wire), Pitfall 5 (SSE frame parsing), Pitfall 7 (Ollama cold start), Pitfall 11 (connectivity flap debounce)
- `.planning/research/STACK.md` — httpx ^0.28 streaming API, `aiter_lines()` pattern

### Prior Phase Foundations
- `.planning/phases/01-foundation-scaffold/01-CONTEXT.md` — Config model (local_url, local_model, probe section), EventBus design, paths
- `.planning/phases/02-session-manager/02-CONTEXT.md` — Message model (including _model field), to_wire requirement

### Todos Folded
- `.planning/todos/pending/TODO-001-ollama-tool-bugs.md` — all 5 mitigations implemented in this phase (D-08 through D-11)

### Project
- `.planning/REQUIREMENTS.md` — ROUT-01 through ROUT-05
- `.planning/ROADMAP.md` — Phase 3 success criteria (5 criteria)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (Phase 1 + 2 output — not yet built but planned)
- `packages/client/src/cyberharness/config.py` — `Config.models.local_url`, `Config.models.local_model`, `Config.probe.*`, `Config.routing.mode`
- `packages/client/src/cyberharness/events.py` — `EventBus`, `ConnectedEvent`, `DisconnectedEvent` (Phase 1 scaffold)
- `packages/client/src/cyberharness/session/models.py` — `Message` model (Phase 2); `to_wire()` will strip `_model` field

### Established Patterns (from prior phases)
- `asyncio.to_thread()` for sync I/O (Phase 2 atomic write pattern — same discipline applies here)
- `asyncio.TaskGroup` startup pattern (Phase 1 — probe task joins the group)
- One `httpx.AsyncClient` per external service, held for process lifetime (Phase 1 ARCHITECTURE.md anti-pattern rule)

### Integration Points
- Phase 3 output (`router/router.py`, `router/local_client.py`, `probe/probe.py`) consumed by:
  - Phase 4 (bench: sends requests through LocalModelClient)
  - Phase 5 (TUI: PhaseRunner calls `router.route(messages)` and posts chunks to the chat widget)
  - Phase 2 (SessionMgr calls `router.route()` per turn and stores result in session)

</code_context>

<specifics>
## Specific Ideas

- `LocalModelClient` should expose a `list_models()` method (GET `/v1/models` or `/api/tags` for Ollama) — Phase 4 uses this for the bench suite. Implement the API call in Phase 3 even if Phase 4 is what displays the results.
- Warm-up fires on startup as a fire-and-forget task (not awaited) — same pattern as auto-title in Phase 2.
- The probe `TaskGroup` task should log on each state transition: `INFO probe: connected` / `INFO probe: disconnected` — makes offline debugging on the Cyberdeck much easier.

</specifics>

<deferred>
## Deferred Ideas

- **Relay / cloud routing** — explicitly deferred. Phase 3 raises `NotImplementedError` on the cloud branch. v1.1.
- **Phase-based routing policy** (discuss → local, plan → relay) — scaffolded as `phase_registry` but cloud branch is a stub. v1.1.
- **Tool call round-trip bench tests** — deferred to Phase 4 (bench suite). TODO-001 item 5.
- **Chunk buffering for TUI rendering** — defer until TUI flickering is observed in Phase 5.

</deferred>

---

*Phase: 3-router-local-models*
*Context gathered: 2026-07-09*
