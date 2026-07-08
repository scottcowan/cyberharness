---
phase: 2
slug: session-manager
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-08
---

# Phase 2 — Validation Strategy

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (inherited from Phase 1) |
| **Quick run command** | `uv run --package cyberharness pytest packages/client/tests/unit/session -x -q` |
| **Full suite command** | `uv run --package cyberharness pytest packages/client/tests -q` |
| **Estimated runtime** | ~5 seconds |

---

## Per-Task Verification Map

| Task | Requirement | Test Type | Automated Command | Status |
|------|-------------|-----------|-------------------|--------|
| Session models | SESS-01 | unit | `pytest tests/unit/session/test_models.py -x -q` | ⬜ |
| `_model` alias roundtrip | SESS-01 | unit | `pytest tests/unit/session/test_models.py::test_model_alias_roundtrip -x -q` | ⬜ |
| Atomic write | SESS-02 | unit | `pytest tests/unit/session/test_store.py::test_atomic_write -x -q` | ⬜ |
| Crash mid-write | SESS-02 | unit | `pytest tests/unit/session/test_store.py::test_no_corrupt_on_kill -x -q` | ⬜ |
| filelock cross-process | SESS-02 | unit | `pytest tests/unit/session/test_store.py::test_filelock_blocks_second_instance -x -q` | ⬜ |
| Resume prompt | SESS-03 | unit | `pytest tests/unit/session/test_resume.py -x -q` | ⬜ |
| Archive on complete | SESS-02 | unit | `pytest tests/unit/session/test_store.py::test_archive_on_complete -x -q` | ⬜ |

---

## Wave 0 Requirements

- [ ] `packages/client/tests/unit/session/__init__.py`
- [ ] `packages/client/tests/unit/session/test_models.py` — Message, ModelCall, Session stubs; `_model` alias roundtrip
- [ ] `packages/client/tests/unit/session/test_store.py` — atomic write, filelock, archive stubs
- [ ] `packages/client/tests/unit/session/test_resume.py` — ResumeScreen result parsing stubs
- [ ] `packages/client/tests/unit/session/test_manager.py` — startup scan, session lifecycle stubs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ResumeScreen displays correctly in TUI | SESS-03 | Textual TUI requires a terminal | Run `cyberharness`, interrupt mid-session (Ctrl+C), re-run — verify ResumeScreen appears with session title/turns/time |
| Auto-title appears after first exchange | SESS-01 | Requires running Ollama (stubbed in Phase 2) | Phase 3 acceptance test |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 stubs
- [ ] `_model` alias roundtrip test present
- [ ] filelock cross-process test present
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
