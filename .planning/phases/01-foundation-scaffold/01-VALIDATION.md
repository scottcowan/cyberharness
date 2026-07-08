---
phase: 1
slug: foundation-scaffold
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-08
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | `packages/client/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run --package cyberharness pytest packages/client/tests/unit -x -q` |
| **Full suite command** | `uv run --package cyberharness pytest packages/client/tests -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick unit test command
- **After every plan wave:** Run full suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| config-load | 01 | 1 | CONF-02 | unit | `pytest tests/unit/test_config.py -x -q` | ⬜ pending |
| config-validation | 01 | 1 | CONF-02 | unit | `pytest tests/unit/test_config.py::test_invalid_field -x -q` | ⬜ pending |
| paths-init | 01 | 1 | CONF-03 | unit | `pytest tests/unit/test_paths.py -x -q` | ⬜ pending |
| cli-entry | 01 | 2 | CONF-01 | integration | `cyberharness --help` exits 0 | ⬜ pending |
| mode-toggle | 01 | 2 | CONF-04 | unit | `pytest tests/unit/test_config.py::test_mode_roundtrip -x -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `packages/client/tests/__init__.py`
- [ ] `packages/client/tests/unit/__init__.py`
- [ ] `packages/client/tests/unit/test_config.py` — stubs for CONF-02 config load + validation
- [ ] `packages/client/tests/unit/test_paths.py` — stubs for CONF-03 workspace init
- [ ] `packages/client/tests/conftest.py` — tmp_path fixture for isolated ~/.cyberharness testing
- [ ] pytest + pytest-asyncio in dev deps (`uv add --dev pytest pytest-asyncio`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| TUI wizard runs on first launch (no config.toml) | CONF-02 | Textual TUI requires a terminal | Delete ~/.cyberharness/config.toml, run `cyberharness`, verify wizard appears |
| `/mode local` and `/mode online` visible in TUI | CONF-04 | TUI interaction | Launch TUI, type `/mode online`, verify status bar updates |
| uv install on aarch64 | CONF-01 | Requires Jetson hardware | `uv tool install ./packages/client` on Jetson, verify `cyberharness --help` works |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all test stubs
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
