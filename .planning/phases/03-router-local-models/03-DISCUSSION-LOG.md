# Phase 3: Router + Local Models - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-09
**Phase:** 3-router-local-models
**Areas discussed:** Streaming & wire format, Tool surface definition, Probe strategy
**Note:** Relay deferred entirely — user specified "assume direct connection" and relay is v1.1.

---

## Streaming & Wire Format

| Option | Description | Selected |
|--------|-------------|----------|
| /v1/chat/completions (OpenAI SSE) | Same endpoint shape as LM Studio | ✓ |
| /api/chat (native Ollama NDJSON) | Richer metadata, separate parser needed | |

**User's choice:** /v1/chat/completions — unifies Ollama and LM Studio behind one client

| Option | Description | Selected |
|--------|-------------|----------|
| Single LocalModelClient, swap base_url | One client, config sets URL per backend | ✓ |
| Separate OllamaClient and LmStudioClient | Two thin clients, shared interface | |
| Abstract base class | More extensible, more code | |

**User's choice:** Single client, configurable base_url

| Option | Description | Selected |
|--------|-------------|----------|
| response.aiter_lines() | Correct line-boundary handling, no extra dep | ✓ |
| response.aiter_bytes() + manual buffer | More control, same correctness | |
| httpx-sse library | Extra dependency for no gain | |

**User's choice:** aiter_lines()

---

## Tool Surface Definition

| Option | Description | Selected |
|--------|-------------|----------|
| No tools in Phase 3 | Registry infrastructure exists, zero tools registered | ✓ |
| Read-only knowledge base tools | read_wiki_page, list_wiki_pages | |
| A few utility tools | read_file, search_knowledge, get_status | |

**User's choice:** No tools at all in Phase 3

| Option | Description | Selected |
|--------|-------------|----------|
| Parameter name guard only | Reject tools with param named 'name' (Ollama bug) | ✓ |
| Full schema validation + capability tier tagging | More work, right for v1.2 | |
| Just a stub class | No enforcement | |

**User's choice:** Parameter name guard only (bakes in TODO-001 mitigation)

| Option | Description | Selected |
|--------|-------------|----------|
| Strip _model field only | Only harness-internal field in Message | ✓ |
| Strip all fields starting with _ | Future-proof, over-engineered now | |
| Allowlist approach | Safest, most brittle | |

**User's choice:** Strip _model only

---

## Probe Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| TCP connect to probe_host:443, timeout 3s | No root required, tests real network path | ✓ |
| HTTP HEAD to https://probe_host | Catches captive portals, more overhead | |
| DNS resolution | Cheapest, misses routing failures | |

**User's choice:** TCP connect, port 443 → fallback 80

| Option | Description | Selected |
|--------|-------------|----------|
| N-of-M: 2 consecutive for state change | Simple, predictable | ✓ |
| Time-based: ignore changes within 10s | Can delay real reconnect | |
| No debounce | Fine for stable network, risky on marginal link | |

**User's choice:** N-of-M, confirm_count = 2

| Option | Description | Selected |
|--------|-------------|----------|
| Probe maintains is_connected; router reads directly | Simple, no subscription | ✓ |
| Router subscribes to EventBus | Decoupled, more code | |
| Router calls probe.check() inline | Blocks event loop | |

**User's choice:** Probe caches state, router reads probe.is_connected

---

## Relay

**User's decision:** Relay deferred. Phase 3 assumes direct local connection only. No relay stub, no relay code path. `NotImplementedError` on cloud branch. Relay is v1.1.

## Claude's Discretion

- Chunk buffering for TUI rendering (defer to Phase 5 if flickering observed)
- Retry/backoff for transient Ollama errors
- Default value of is_connected before first probe check

## Deferred Ideas

- Relay / cloud routing (v1.1)
- Phase-based routing policy (v1.1)
- Tool call round-trip bench tests (Phase 4)
