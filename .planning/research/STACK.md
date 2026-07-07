# Technology Stack

**Project:** cyberharness v1.0
**Researched:** 2026-07-07
**Target platform:** NVIDIA Jetson (ARM64/aarch64, JetPack 6, Ubuntu 22.04, Python 3.10+)
**Deployment:** single-user CLI on a Cyberdeck; local Ollama sidecar; occasional cloud relay

## Recommended Stack

### Core Runtime

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11 (min 3.10) | Language | Ships on JetPack 6/Ubuntu 22.04 (3.10 default) or via `deadsnakes`/`uv` for 3.11. 3.11 gives faster asyncio and better `TaskGroup`/`ExceptionGroup` semantics used by the probe/queue loop. Avoid 3.12+ only because some Jetson-adjacent wheels (torch etc.) still lag; the harness itself is pure-Python so 3.12 also works. |
| asyncio (stdlib) | — | Async runtime | Router streams tokens, probe runs on interval, queue watches filesystem, TUI needs a loop — all concurrent, all I/O bound. Use a single event loop with `asyncio.TaskGroup` for the probe + queue drainer + TUI. No need for `trio`/`anyio` — Textual and httpx are asyncio-native. |

### TUI / CLI

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Textual | ^8.2 (8.2.8 current) | Chat-style TUI | Full async framework, streams tokens into a `RichLog` cheaply, screen/modal system fits phase-boundary prompts ("Resume session?"), and it runs the same event loop as the router. Pure-Python + Rich, no C deps — clean ARM64 install. |
| Rich | ^15.0 (transitive, pinned by Textual) | Markdown rendering, syntax highlight | Model output is markdown-heavy; Rich renders inline in Textual without extra work. Also useful for non-TUI `--headless` diagnostic output. |
| Typer | ^0.26 | CLI entry point / subcommands | Thin `click` wrapper; declarative subcommands (`cyberharness chat`, `cyberharness queue`, `cyberharness config`, `cyberharness probe`). Plays well with `uv`-installed console scripts. |

### HTTP + Model APIs

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| httpx | ^0.28 | HTTP client for Ollama + cloud relay | Native async, HTTP/2, streaming responses (`aiter_lines`/`aiter_bytes`) — required for token streaming from both Ollama's `/api/chat` (or `/v1/chat/completions`) and any OpenAI-compatible relay. One client, one connection pool, one timeout policy for both endpoints. |
| openai SDK | **do not use in v1.0** | — | Adds a dep and its own retry/streaming abstractions when the actual wire format on both sides is already OpenAI-compatible and trivially handled by httpx. The architecture notes say "The router swaps endpoint and model name; the messages array is unchanged." — that is exactly a 40-line httpx wrapper. Revisit only if we need tool-calling schemas or function calling before v1.1. |
| anthropic SDK | **do not use in v1.0** | — | The doc says cloud calls go through an OpenAI-compatible relay (or Anthropic's own `/v1/messages` — TBD). If it's the relay: httpx is enough. If we end up calling `api.anthropic.com` directly, the messages format differs (`system` is top-level, no `role: system` in the array) and the SDK becomes worth it — flag for phase-time research. |
| tenacity | ^9.1 | Retry + exponential backoff | Queue-drain retries and probe recovery need bounded exponential backoff with jitter. Writing this by hand is a known source of bugs (unbounded growth, no jitter, race with cancellation). Tenacity's async decorators integrate cleanly. |

### Configuration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `tomllib` (stdlib, 3.11+) | — | Parse `~/.cyberharness/config.toml` | Zero-dep on 3.11+. If we pin 3.10 as minimum, add `tomli` (2.4.1) as a fallback. |
| pydantic | ^2.13 | Typed models for Config, Session, Message, QueueEnvelope | Session serialisation to JSON is the hot path (written after every turn). Pydantic v2's Rust core makes this cheap, and it gives us free validation on load (rejects malformed session files instead of crashing mid-turn). Same models power YAML workflow parsing. |
| pydantic-settings | ^2.14 | Layered config: env vars > TOML > defaults | Wraps pydantic with env/TOML/CLI merging. Keeps secrets (e.g. `CYBERHARNESS_CLOUD_API_KEY`) out of the TOML file and lets the Jetson pull them from `~/.config/cyberharness/env` or systemd EnvironmentFile. |

### Workflow / Phase Definitions

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PyYAML | ^6.0 | Parse GSD phase / workflow YAML | Standard, C-accelerated on ARM64 (libyaml wheel builds fine). Only used at startup — no perf concern. |
| pydantic (reuse) | ^2.13 | Validate parsed YAML into `PhaseSpec` models | Fail fast on malformed workflow files; single source of truth for phase schema. |

### Persistence

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Filesystem JSON (stdlib `json` + pydantic `model_dump_json`) | — | Sessions and queue envelopes | The design is explicit: `~/.cyberharness/sessions/<id>.json` and `~/.cyberharness/queue/*.json`. One writer per session, one file per envelope — no concurrent-writer or query-across-rows problem, so SQLite is over-engineered for v1.0. Also human-readable and grep-friendly on the Cyberdeck, which matters when debugging offline. |
| aiofiles | ^25.1 | Non-blocking session writes | Sessions are written after every turn; sync file I/O would stall the TUI event loop during streaming. `aiofiles` is a thin async wrapper — no C ext, ARM64-clean. |
| watchfiles | ^1.2 | Watch `~/.cyberharness/queue/` for new envelopes | Rust-backed but ships aarch64 manylinux wheels; falls back to polling if the wheel is missing. Cleaner than hand-rolling `inotify` or a polling loop, and gives the queue drainer a proper async iterator. |
| SQLite | **do not use in v1.0** | — | No cross-session queries, no concurrent writers, no reason. Reconsider if we ever want "search my past discuss sessions" — that's v2. |

### Connectivity Probe

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| httpx (reuse) | ^0.28 | Lightweight HTTP HEAD/GET against `probe_host` | Config already implies HTTP-style probe (`probe_host = "1.1.1.1"` — pair with `https://1.1.1.1/cdn-cgi/trace` or a TCP connect). Reusing the same client keeps DNS caching consistent with real routing calls. |
| `asyncio.open_connection` (stdlib) | — | Fallback TCP-connect probe | For pure "is the link up" checks without HTTP overhead. Preferred over subprocess `ping` — `ping` on Jetson needs cap_net_raw or setuid, brittle. |
| **avoid** `icmplib` / raw ICMP | — | — | Requires root or capabilities on Linux. TCP probe to port 443 is as reliable and needs no privileges. |

### CLI Entry Point / Packaging

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| uv | latest (0.5+) | Dependency + venv management, lockfile | Fastest resolver, first-class `pyproject.toml`, produces reproducible `uv.lock`. Runs on aarch64 Linux natively. Replaces pip + pip-tools + virtualenv. |
| Hatchling (via `pyproject.toml`) | latest | Build backend | Default modern backend; zero config for a pure-Python project with a `[project.scripts]` entry. |
| pipx or `uv tool install` | latest | End-user install on the Jetson | `uv tool install cyberharness` (or `pipx install .` from a checkout) gives an isolated venv + a `cyberharness` binary on PATH. No global site-packages contamination. |
| `[project.scripts] cyberharness = "cyberharness.cli:app"` | — | Typer console script | Single entry point; Typer handles subcommand dispatch. |

### Ollama Client — Deliberately Not a Dependency

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `ollama` Python SDK | 0.6.2 | — | Considered and rejected. Ollama exposes an OpenAI-compatible endpoint at `http://localhost:11434/v1/chat/completions`. The router already needs a raw httpx OpenAI-format caller for the cloud side. Using the same code path for both sides is the whole point of the design — adding the SDK would fork it. |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| TUI | Textual | prompt-toolkit | Lower-level, no widgets, we'd rebuild scrollback + modals. Fine for a REPL, wrong for a chat UI with streaming markdown. |
| TUI | Textual | Urwid | Sync-first, older, weaker markdown/streaming story. |
| TUI | Textual | plain `rich` + `input()` | Blocks the event loop; can't stream while user is typing next message. |
| HTTP client | httpx | `requests` | Sync-only. Streaming + concurrent probe/queue require async. |
| HTTP client | httpx | `aiohttp` | Fine, but httpx has cleaner API, HTTP/2, and matches what most OpenAI-compat examples use. |
| API SDK | (none, raw httpx) | `openai` SDK | Extra dep; the wire format is already OpenAI-compatible; retry/streaming trivially replicable. |
| API SDK | (none) | `litellm` | Big dep tree, opinionated routing that duplicates our router. |
| Persistence | JSON files | SQLite | No query patterns justify it in v1.0. |
| Persistence | JSON files | Pickle | Unsafe on load, opaque to grep. |
| Config | TOML + pydantic-settings | `dynaconf` | Heavier, more magic; overkill for one config file. |
| Config | TOML | YAML for config too | YAML for workflows (multi-line, human-edited), TOML for config (structured, typed, less footgun). |
| Retry | tenacity | hand-rolled | Async cancellation + jitter is easy to get wrong. |
| Filesystem watch | watchfiles | polling `os.scandir` | Fine but wastes cycles; watchfiles falls back to it anyway if inotify is unavailable. |
| Filesystem watch | watchfiles | `inotify_simple` | Linux-only, sync API, awkward to bridge into asyncio. |
| CLI framework | Typer | Click directly | Typer is Click + type hints; hints already exist for pydantic models, keeps the codebase uniform. |
| CLI framework | Typer | argparse | Verbose, no auto-help formatting, no completion. |
| Packaging | uv | Poetry | Slower resolver, own lockfile format, less momentum in 2026. |
| Packaging | uv | pip + requirements.txt | No lockfile, no dev/runtime split. |

## ARM64 / Jetson Compatibility

Every dep above either (a) is pure Python or (b) publishes `manylinux2014_aarch64` wheels. Verified:

- **Textual, Rich, Typer, pydantic-settings, PyYAML, tenacity, aiofiles, questionary, tomli, ollama-py** — pure Python.
- **pydantic v2** — Rust core; publishes aarch64 manylinux wheels since 2.0.
- **httpx** — pure Python; `h2` (HTTP/2, optional) is pure Python; `httpcore` pure Python.
- **watchfiles** — Rust core; publishes aarch64 manylinux wheels. Falls back to polling if unavailable.
- **uv** — publishes aarch64 Linux binaries.

Jetson-specific gotchas:

1. **JetPack 6 ships Python 3.10.** If we target 3.11 for `tomllib`/`TaskGroup` niceties, install via `uv python install 3.11` — it drops a self-contained aarch64 build in `~/.local/share/uv/python/`. No apt-get / deadsnakes needed.
2. **Ollama on Jetson** runs fine via the official install script (uses CUDA on-device). The harness talks to it over `localhost:11434` — no coupling.
3. **Filesystem watches on tmpfs**: if `~/.cyberharness/queue/` ends up on tmpfs, inotify still works. If it's on a network mount (unlikely), watchfiles auto-degrades to polling.
4. **No GPU deps in the harness itself.** Inference happens in the Ollama process — the harness is a network client. This keeps `cyberharness` installable in a plain venv with no CUDA setup.

## Deliberate Non-Dependencies (Keep v1.0 Lean)

Do **not** add for v1.0:

- `openai` / `anthropic` / `litellm` SDKs — raw httpx over the OpenAI wire format is enough for both sides.
- `sqlalchemy` / `sqlite` — JSON files are the design.
- `celery` / `rq` / `dramatiq` — the queue is 20 lines of `watchfiles` + `asyncio`. Task queue frameworks assume a broker (redis) we don't have.
- `apscheduler` — probe loop is `while True: await asyncio.sleep(interval)`. Nothing more.
- `structlog` — stdlib `logging` with a `RichHandler` is enough. Add structlog only if we start shipping logs off-device.
- `pytest-asyncio` — yes for tests (dev dep), not runtime.
- `httptools` / `uvloop` — no server component, no need. (uvloop also doesn't help TUI-bound workloads.)
- `pynvml` / GPU telemetry libs — the Cyberdeck may want this, but it belongs in the cyberdeck repo, not the harness.

## Suggested `pyproject.toml` Skeleton

```toml
[project]
name = "cyberharness"
version = "0.1.0"
description = "Connectivity-aware AI harness for the Jetson Cyberdeck"
requires-python = ">=3.10"
dependencies = [
  "textual>=8.2,<9",
  "rich>=15.0,<16",
  "typer>=0.26,<0.27",
  "httpx>=0.28,<0.29",
  "pydantic>=2.13,<3",
  "pydantic-settings>=2.14,<3",
  "pyyaml>=6.0,<7",
  "aiofiles>=25.1,<26",
  "watchfiles>=1.2,<2",
  "tenacity>=9.1,<10",
  "tomli>=2.4; python_version<'3.11'",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.24",
  "ruff>=0.7",
  "mypy>=1.11",
  "textual-dev>=1.7",
]

[project.scripts]
cyberharness = "cyberharness.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## Integration Points

Where each library sits in the architecture from `docs/architecture.md`:

| Component | Primary Libraries |
|-----------|-------------------|
| CLI (`cli/`) | Typer + Textual `App` |
| Chat UI | Textual `RichLog`, `Input`, `Screen` for resume/quit modals |
| Router (`router/`) | httpx `AsyncClient` (one instance, two base URLs) |
| Session (`session/`) | pydantic models + aiofiles for atomic writes; `json.dumps` via `model_dump_json` |
| Queue (`queue/`) | watchfiles `awatch()` + tenacity retry wrapper around router call |
| Probe (`probe/`) | httpx HEAD to `probe_host` or `asyncio.open_connection` fallback; publishes to an `asyncio.Event` / broadcast queue |
| Config | pydantic-settings loading TOML + env; frozen dataclass-style model |
| Phase hooks (`phases/`) | pydantic `PhaseSpec` parsed from YAML; each phase resolves to a `route(phase, messages)` call |
| Persistence layout | `~/.cyberharness/{config.toml, sessions/*.json, queue/*.json}` — no libs beyond stdlib pathlib |

## Sources

- Textual docs (textualize.io) — confirmed async model + `RichLog` streaming; version 8.2.8 current on PyPI as of 2026-07-07 (HIGH).
- httpx docs (python-httpx.org) — streaming + async APIs; 0.28.1 current (HIGH).
- Ollama OpenAI-compatibility docs (github.com/ollama/ollama/blob/main/docs/openai.md) — `/v1/chat/completions` endpoint parity (HIGH).
- pydantic v2 docs + release notes — Rust core, aarch64 wheels since 2.0 (HIGH).
- PyPI metadata pulled 2026-07-07 for all pinned versions (HIGH).
- Jetson JetPack 6 release notes — Ubuntu 22.04 base, Python 3.10 default (HIGH).
- uv docs (docs.astral.sh/uv) — `uv python install`, aarch64 support (HIGH).
- watchfiles PyPI classifiers — aarch64 manylinux wheels (HIGH).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| TUI choice (Textual) | HIGH | Only mature async TUI in Python; used by many streaming-LLM CLIs. |
| HTTP + no SDKs | HIGH | Both endpoints explicitly OpenAI-compatible per architecture doc. |
| Persistence (JSON files) | HIGH | Design already specifies file layout; no query patterns justify SQLite. |
| Config (TOML + pydantic-settings) | HIGH | Matches `config.toml` example in architecture doc. |
| Filesystem watch (watchfiles) | MEDIUM | Works, but a simple polling loop would also do; consider polling if we want to eliminate the Rust dep. |
| ARM64 compatibility | HIGH | All deps have aarch64 wheels or are pure-Python. |
| Cloud endpoint (relay vs Anthropic direct) | MEDIUM | If direct Anthropic, `/v1/messages` differs from OpenAI format — will need thin adapter or the anthropic SDK. Flag for phase-time research when the relay is specified. |
