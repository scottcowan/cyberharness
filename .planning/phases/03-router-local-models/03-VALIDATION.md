---
phase: 3
slug: router-local-models
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-09
---

# Phase 3 — Validation Strategy

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio + respx (httpx mock) |
| **Quick run command** | `uv run --package cyberharness pytest packages/client/tests/unit/router packages/client/tests/unit/probe -x -q` |
| **Full suite command** | `uv run --package cyberharness pytest packages/client/tests -q` |
| **Estimated runtime** | ~10 seconds |

---

## Per-Task Verification Map

| Task | Requirement | Test Type | Automated Command | Status |
|------|-------------|-----------|-------------------|--------|
| to_wire() sanitiser | ROUT-02 | unit | `pytest tests/unit/router/test_wire.py -x -q` | ⬜ |
| Tool registry param guard | ROUT-05 | unit | `pytest tests/unit/router/test_tool_registry.py -x -q` | ⬜ |
| LocalModelClient streaming | ROUT-03 | unit | `pytest tests/unit/router/test_local_client.py::test_stream -x -q` | ⬜ |
| SSE [DONE] handling | ROUT-03 | unit | `pytest tests/unit/router/test_local_client.py::test_done_sentinel -x -q` | ⬜ |
| LM Studio base_url swap | ROUT-04 | unit | `pytest tests/unit/router/test_local_client.py::test_lmstudio -x -q` | ⬜ |
| Probe TCP connect | ROUT-01 | unit | `pytest tests/unit/probe/test_probe.py::test_tcp_connect -x -q` | ⬜ |
| Probe debounce N-of-M | ROUT-01 | unit | `pytest tests/unit/probe/test_probe.py::test_debounce -x -q` | ⬜ |
| Probe EventBus publish | ROUT-01 | unit | `pytest tests/unit/probe/test_probe.py::test_event_publish -x -q` | ⬜ |
| Router dispatches to local | ROUT-02 | unit | `pytest tests/unit/router/test_router.py -x -q` | ⬜ |
| Cloud branch raises NotImplementedError | ROUT-02 | unit | `pytest tests/unit/router/test_router.py::test_cloud_not_implemented -x -q` | ⬜ |
| Ollama version check | ROUT-03 | unit | `pytest tests/unit/router/test_local_client.py::test_version_check -x -q` | ⬜ |

---

## Wave 0 Requirements

- [ ] `packages/client/tests/unit/router/__init__.py`
- [ ] `packages/client/tests/unit/router/test_wire.py` — to_wire() strips _model; other fields pass through
- [ ] `packages/client/tests/unit/router/test_tool_registry.py` — rejects "name" param; accepts valid params
- [ ] `packages/client/tests/unit/router/test_local_client.py` — streaming, [DONE] sentinel, LM Studio URL swap, version check stubs
- [ ] `packages/client/tests/unit/router/test_router.py` — dispatches to local; cloud raises NotImplementedError at call time (not first iteration)
- [ ] `packages/client/tests/unit/probe/__init__.py`
- [ ] `packages/client/tests/unit/probe/test_probe.py` — TCP connect, debounce, EventBus publish stubs
- [ ] `respx` added to dev deps: `uv add --dev respx`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Tokens stream visibly in TUI | ROUT-03/04 | Requires running Ollama + TUI | Phase 5 acceptance test |
| Warm-up pins model in VRAM | ROUT-03 | Requires Jetson hardware + `ollama ps` | Run `cyberharness`, check `ollama ps` shows model loaded |
| Status bar shows online/offline | ROUT-01 | TUI interaction | Kill network, observe status bar change within 2 probe intervals |

---

## Validation Sign-Off

- [ ] Wave 0 stubs in RED before implementation
- [ ] NotImplementedError fires at call time test present
- [ ] to_wire() strips _model unit test present
- [ ] Probe debounce test present
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
