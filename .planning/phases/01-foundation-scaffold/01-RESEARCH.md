# Phase 1: Foundation & Scaffold — Research

**Researched:** 2026-07-08
**Domain:** Python project scaffolding — uv monorepo workspace, pydantic-settings TOML config, Textual first-run wizard, Typer CLI dispatch, ARM64 packaging
**Confidence:** HIGH (uv workspace, pydantic-settings, Textual screens, Typer callbacks) / MEDIUM (`uv tool install` semantics for a workspace member — documented mechanics work, but user-facing install command needs local validation on aarch64)

## Summary

Phase 1 delivers a monorepo scaffold rooted at `/`, with `packages/client/` hosting the installable `cyberharness` package (`src/cyberharness/` layout), stub `packages/server/` and `packages/workspace/` members declared in a top-level uv workspace, a `pydantic-settings` `Config` model that reads `~/.cyberharness/config.toml` (env vars override; `CYBERHARNESS_CONFIG` overrides the path), an idempotent workspace-directory initialiser under `~/.cyberharness/`, a Typer CLI whose default (no subcommand) invocation launches a Textual `App`, and a first-run Textual wizard that collects three inputs and writes `config.toml` before the main TUI mounts.

All load-bearing libraries are pure-Python or ship aarch64 wheels; no build-from-source is expected on Jetson if Python 3.11 is installed via `uv python install 3.11`. The `TomlConfigSettingsSource` (pydantic-settings v2.14) is the correct primitive for the TOML+env layering: TOML values populate defaults, env vars override without further code. Textual's `push_screen(..., callback)` pattern (or `push_screen_wait` from a worker) is the standard multi-step wizard idiom. Typer's `@app.callback(invoke_without_command=True)` with `ctx.invoked_subcommand is None` is the standard way to dispatch to a default action when the user runs `cyberharness` bare.

**Primary recommendation:** Follow the STACK.md/ARCHITECTURE.md skeleton verbatim for `packages/client/src/cyberharness/{config.py, paths.py, events.py, errors.py}` + component subdirs; wire the CLI entry point as `cyberharness = "cyberharness.cli:app"`; make the Typer top-level callback launch the Textual `App` when `ctx.invoked_subcommand is None`; and treat directory init and config validation as unconditional startup steps (fail fast on config, silently create dirs).

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `packages/` subdirectory from day one. Monorepo layout: `packages/client/`, `packages/server/` (stub), `packages/workspace/` (stub). Phase 1 builds `packages/client/` only.
- **D-02:** `src/cyberharness/` layout inside `packages/client/` — i.e., `packages/client/src/cyberharness/`.
- **D-03:** Single package with component subdirs: `probe/`, `router/`, `session/`, `queue/`, `tui/`, `cli/`. No sub-packages.
- **D-04:** Python 3.11 minimum, installed via `uv python install 3.11` on Jetson.
- **D-05:** Minimal `config.toml` with four sections only:
  ```toml
  [models]
  local_url = "http://localhost:11434"
  local_model = "llama3.2:3b-instruct-q4_K_M"

  [routing]
  mode = "local"  # "local" | "online"

  [probe]
  interval_seconds = 30
  probe_host = "1.1.1.1"

  [paths]
  data_dir = "~/.cyberharness"
  ```
- **D-06:** Config path is always `~/.cyberharness/config.toml`. `CYBERHARNESS_CONFIG` env var overrides for testing. **No `--config` CLI flag.**
- **D-07:** Missing `config.toml` on first run triggers a Textual TUI wizard (3 questions: Ollama URL, mode, data dir). Wizard writes config, creates dirs, then launches main TUI.
- **D-08:** pydantic-settings loads config (TOML + env override). Secrets always via env, never in TOML.
- **D-09:** First-run sequence: detect no `config.toml` → run wizard → write `config.toml` → create workspace dirs → launch main TUI. Subsequent runs skip the wizard.
- **D-10:** Workspace init is idempotent — silently create missing dirs on every startup: `sessions/`, `queue/`, `workspace/`, `bench/`, `knowledge/wiki/`, `knowledge/refs/`.
- **D-11:** Partial workspace is silently repaired; no init command required.
- **D-12a:** `knowledge/wiki/` and `knowledge/refs/` are both created on first run but start empty.
- **D-12:** `cyberharness` with no subcommand launches the Textual TUI.
- **D-13:** Typer for subcommand dispatch; Textual for the main UI. Entry point: `cyberharness = "cyberharness.cli:app"`.
- **D-14:** Phase 1 registers these subcommands (stubs acceptable for later-phase logic):
  - `cyberharness init` — run the setup wizard manually (also auto-triggers on first run)
  - `cyberharness config show` / `config set <key> <value>`
  - `cyberharness status`
  - `cyberharness probe`
  - `cyberharness bench` — stub only
- **D-15:** Mode toggle at runtime via TUI slash command `/mode local` / `/mode online`; updates `config.toml` on disk so it persists.
- **D-16..D-18:** Knowledge base directory layout only; wiki access + CLAUDE.md integration are v1.1/Phase 5 concerns. Phase 1 only creates the dirs.

### Claude's Discretion

- Logging setup (stdlib `logging` + `RichHandler` is the recommended default from STACK.md).
- `__version__` placement and version string format.
- Error message formatting (use Rich markup for colour; keep messages actionable).
- Whether `cyberharness probe` in Phase 1 is a real TCP check or a stub (implement real check if straightforward).

### Deferred Ideas (OUT OF SCOPE)

- **TODO-001** (Ollama tool-use parser bugs) — belongs in Phase 3 (`router/tools`). Not Phase 1.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONF-01 | User can scaffold and install via `uv` with a single command on aarch64 Linux | uv workspace layout, `uv tool install` from local path, aarch64 wheel audit below |
| CONF-02 | Config loaded from `~/.cyberharness/config.toml` with env var override (secrets stay out of TOML) | `pydantic-settings` v2.14 `TomlConfigSettingsSource` + env source in `settings_customise_sources` |
| CONF-03 | Workspace directory structure defined and initialised on first run (`sessions/`, `queue/`, `workspace/`, `bench/`, `knowledge/wiki/`, `knowledge/refs/`) | `pathlib.Path.mkdir(parents=True, exist_ok=True)` idempotent pattern |
| CONF-04 | User can switch between All Local and Wait for Online mode from config and at runtime | `[routing].mode` field in Config; TUI `/mode` slash command rewrites TOML atomically |

## Project Constraints (from CLAUDE.md)

No `./CLAUDE.md` in the repo at research time. No project-specific overrides beyond what CONTEXT.md, ARCHITECTURE.md, STACK.md and PITFALLS.md already impose.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Package install / workspace resolution | Build/Packaging (uv + hatchling) | — | Owns dependency graph and console-script entry point. |
| Config load + validation | Application core (`config.py`) | — | Single fail-fast checkpoint at startup, imported by every downstream module. |
| Filesystem workspace init | Application core (`paths.py`) | — | Pure `pathlib`; no framework surface. Called by the app entry after config loads. |
| First-run wizard | TUI (Textual `App`) | Application core (writes `config.toml`) | Wizard is a UI concern; persistence is a core concern. Kept separate so wizard can be tested by mocking the writer. |
| CLI subcommand dispatch | CLI (`cli/main.py` — Typer) | TUI (default action) | Typer owns argv parsing; when no subcommand is invoked it hands off to the Textual app. |
| Runtime mode toggle | TUI (slash command handler) | Application core (config writer) | Command handler is UI; TOML rewrite is core. |

## Standard Stack

Versions verified against pypi.org on 2026-07-08.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Runtime | `tomllib` (stdlib), `TaskGroup`, better asyncio semantics. Installed on Jetson via `uv python install 3.11`. [CITED: docs.astral.sh/uv] |
| uv | latest (0.5+) | Dependency + venv + workspace + tool install | Fast resolver, native workspace support, aarch64 binaries. [VERIFIED: docs.astral.sh/uv/concepts/projects/workspaces/] |
| hatchling | latest | PEP 517 build backend | Zero-config for pure-Python with `[project.scripts]`. Recommended by STACK.md. [CITED: STACK.md] |
| pydantic | 2.13.4 | Typed models (Config, downstream Session/Envelope) | Rust core, aarch64 wheels since 2.0. [VERIFIED: npm registry — pypi.org/project/pydantic] |
| pydantic-settings | 2.14.2 | Layered config: env > TOML > defaults | Ships `TomlConfigSettingsSource`; standard idiom for the exact pattern D-08 requires. [VERIFIED: pypi.org/project/pydantic-settings] [CITED: pydantic.dev/docs/validation/latest/api/pydantic_settings/] |
| typer | 0.26.8 | CLI subcommand dispatch | Type-hint-driven Click wrapper; `invoke_without_command` plus `ctx.invoked_subcommand is None` gives the "bare command → TUI" behaviour D-12 requires. [VERIFIED: pypi.org/project/typer] [CITED: typer.tiangolo.com/tutorial/commands/context/] |
| textual | 8.2.8 | TUI (wizard + main app) | Multi-screen stack via `push_screen(..., callback)` and `dismiss(result)`; async-native so it runs on the same loop as later-phase probe/router. [VERIFIED: pypi.org/project/textual] [CITED: textual.textualize.io/guide/screens/] |
| rich | 15.0.0 | Log formatting, markdown rendering | `RichHandler` is the STACK.md logging pick; also renders markdown inline in Textual. [VERIFIED: pypi.org/project/rich] |

### Supporting (Phase 1 uses only what CLI/wizard/config need — deps declared but not exercised in Phase 1 are still installed so downstream phases don't touch pyproject.toml again)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | 0.28.1 | Async HTTP client | Phase 1: only used by `cyberharness probe` if we implement the real check; otherwise imported by Phase 2+. [VERIFIED: pypi.org/project/httpx] |
| aiofiles | 25.1.0 | Non-blocking file writes | Phase 2+ session writes. Declared now to freeze deps. [VERIFIED: pypi.org/project/aiofiles] |
| watchfiles | 1.2.0 | Queue file watching | Phase 6. Rust-backed with aarch64 manylinux wheels. [VERIFIED: pypi.org/project/watchfiles] |
| tenacity | 9.1.4 | Retry / backoff | Phase 4+. [VERIFIED: pypi.org/project/tenacity] |
| pyyaml | 6.0.3 | YAML for workflow specs | Phase 4+. libyaml wheel builds on aarch64. [VERIFIED: pypi.org/project/pyyaml] |
| filelock | 3.29.7 | Cross-process session lock | Phase 2+. Pure Python. [VERIFIED: pypi.org/project/filelock] |
| tomli | 2.4+ | TOML fallback for py<3.11 | Optional dependency guarded by `python_version<'3.11'` — with D-04 pinning 3.11 minimum, this is redundant and can be omitted; keep as belt-and-braces per STACK.md skeleton. [CITED: STACK.md] |

### Dev deps (Phase 1 wants tests + type checking green from day one)

| Library | Version | Purpose |
|---------|---------|---------|
| pytest | ^8 | Test runner |
| pytest-asyncio | ^0.24 | Async test support (Phase 2+ mostly; harmless to install now) |
| ruff | ^0.7 | Lint + format |
| mypy | ^1.11 | Type check |
| textual-dev | ^1.7 | `textual console` for TUI debugging |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pydantic-settings TOML source | Roll own `tomllib.load` + manual merge | ~15 lines of code, but loses layered priority + env override for free. Not worth it. |
| Typer | Click directly | Click is fine; Typer is Click + type hints, cleaner for this size. STACK.md picks Typer. |
| Textual for wizard | `questionary` / `rich.prompt` for CLI-style questions | Simpler, but breaks D-07 (wizard must be TUI-consistent). Rejected. |
| uv workspace | Single flat package (no `packages/`) | Simpler now, but D-01 mandates monorepo. Doing it now avoids a later rearrange. |
| hatchling | setuptools / poetry-core | hatchling is uv's default recommendation and needs no config for pure-Python. |

**Installation (single-command target per CONF-01):**

```bash
# On aarch64 Linux (Jetson JetPack 6 or generic Ubuntu 22.04)
curl -LsSf https://astral.sh/uv/install.sh | sh    # install uv
uv python install 3.11                              # get 3.11 without touching system Python
git clone <repo> && cd cyberharness
uv sync                                             # resolves workspace, creates .venv, installs deps
uv run cyberharness                                 # launches TUI (or wizard on first run)
```

For the "installed console script on PATH" ergonomic, either:
- `uv tool install --from packages/client cyberharness` (verify behavior on Jetson — see Assumption A1)
- or document `uv run cyberharness` as the canonical invocation (removes the tool-install question entirely, at the cost of requiring the checkout to be present).

**Recommendation:** Ship `uv run cyberharness` as the documented Phase 1 install path. A `uv tool install` recipe can be added in a later phase once we confirm the workspace-member semantics on a real Jetson.

### Version verification (2026-07-08)

All package versions above were pulled from `pypi.org/pypi/<name>/json` on 2026-07-08. No package resolved to a version older than 30 days without a well-known stable track. Pydantic 2.13 and pydantic-settings 2.14 are current majors.

## Package Legitimacy Audit

slopcheck was not available in the researcher environment. All packages listed above are cross-checked against pypi.org's public metadata AND are the same names referenced in the pre-existing `.planning/research/STACK.md` (project-locked list). Every one has a long track record and a public source repository. None are new/low-download.

| Package | Registry | Age | Downloads (weekly, approx.) | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| textual | PyPI | 4+ yrs | ~1.5M | github.com/Textualize/textual | (unavailable) | Approved |
| rich | PyPI | 6+ yrs | ~120M | github.com/Textualize/rich | (unavailable) | Approved |
| typer | PyPI | 5+ yrs | ~30M | github.com/tiangolo/typer | (unavailable) | Approved |
| httpx | PyPI | 6+ yrs | ~85M | github.com/encode/httpx | (unavailable) | Approved |
| pydantic | PyPI | 8+ yrs | ~300M | github.com/pydantic/pydantic | (unavailable) | Approved |
| pydantic-settings | PyPI | 3+ yrs | ~40M | github.com/pydantic/pydantic-settings | (unavailable) | Approved |
| aiofiles | PyPI | 8+ yrs | ~40M | github.com/Tinche/aiofiles | (unavailable) | Approved |
| watchfiles | PyPI | 4+ yrs | ~25M | github.com/samuelcolvin/watchfiles | (unavailable) | Approved |
| tenacity | PyPI | 10+ yrs | ~65M | github.com/jd/tenacity | (unavailable) | Approved |
| pyyaml | PyPI | 15+ yrs | ~350M | github.com/yaml/pyyaml | (unavailable) | Approved |
| filelock | PyPI | 10+ yrs | ~90M | github.com/tox-dev/filelock | (unavailable) | Approved |
| hatchling | PyPI | 4+ yrs | ~60M | github.com/pypa/hatch | (unavailable) | Approved |
| uv | Astral (curl installer, not pypi runtime dep) | 2+ yrs | — | github.com/astral-sh/uv | (unavailable) | Approved (via official Astral installer) |

Packages removed due to slopcheck [SLOP] verdict: none.
Packages flagged as suspicious [SUS]: none.

Because slopcheck itself was unavailable, all rows above are strictly speaking `[ASSUMED]` in the letter of the protocol. In practice, every one is on the project-locked STACK.md and every one has an established public GitHub source repository. Planner should still run `slopcheck install ...` at execution time as an inexpensive extra check.

## Architecture Patterns

### System Architecture Diagram

```
                     ┌────────────────────────────────────┐
   user runs         │  Typer entrypoint  cli.app         │
   `cyberharness`    │  (packages/client/src/cyberharness │
      ──────────────►│         /cli/main.py)              │
                     └────────────┬───────────────────────┘
                                  │
                    ┌─────────────┴───────────────┐
                    │  @app.callback(invoke_      │
                    │      without_command=True)  │
                    │  ctx.invoked_subcommand?    │
                    └──┬────────────────────┬─────┘
                       │ None                │ (init | config | status | probe | bench)
                       ▼                     ▼
        ┌──────────────────────────┐   ┌──────────────────────┐
        │   default_action()       │   │  subcommand handler  │
        │                          │   │  (each imports       │
        │  1. Config.load_or_None  │   │   Config + Paths)    │
        │  2. if not found:        │   └──────────────────────┘
        │        run wizard        │
        │  3. Paths.ensure_dirs()  │
        │  4. Launch main TUI      │
        └──────────┬───────────────┘
                   │
                   ▼
        ┌─────────────────────────────────────────────────────┐
        │  cyberharness.tui.app.CyberharnessApp (Textual App) │
        │                                                     │
        │  on_mount:                                          │
        │    - if wizard_needed: push_screen(WizardScreen,    │
        │                        callback=self._on_wizard)    │
        │    - else: push_screen(MainScreen)                  │
        │                                                     │
        │  slash-command handler:                             │
        │    /mode local | /mode online → rewrite config.toml │
        └─────────────────────────────────────────────────────┘

Core services referenced by CLI + TUI (Phase 1 scope):

┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
│ config.py  │   │ paths.py   │   │ events.py  │   │ errors.py  │
│ (pydantic- │   │ (pathlib   │   │ (EventBus  │   │ (domain    │
│ settings + │   │ Paths obj) │   │ scaffold — │   │ exceptions)│
│  tomllib)  │   │            │   │ used P2+)  │   │            │
└────────────┘   └────────────┘   └────────────┘   └────────────┘
```

### Recommended Project Structure

Follows ARCHITECTURE.md, updated for the monorepo D-01/D-02 layout.

```
/                                       # repo root == workspace root
├── pyproject.toml                      # [tool.uv.workspace] members = ["packages/*"]
├── uv.lock                             # single lockfile for the whole workspace
├── README.md
├── docs/
│   ├── architecture.md
│   └── session-design.md
├── .planning/                          # planning artifacts (existing)
└── packages/
    ├── client/
    │   ├── pyproject.toml              # name = "cyberharness"; [project.scripts]
    │   ├── src/cyberharness/
    │   │   ├── __init__.py             # __version__ = "0.1.0"
    │   │   ├── config.py               # Config(BaseSettings) + TomlConfigSettingsSource
    │   │   ├── paths.py                # Paths dataclass + ensure_workspace()
    │   │   ├── events.py               # EventBus scaffold (used from Phase 3)
    │   │   ├── errors.py               # ConfigError, WorkspaceError, ...
    │   │   ├── logging.py              # setup_logging() with RichHandler
    │   │   ├── probe/                  # (stub for Phase 1: single-shot TCP check)
    │   │   │   ├── __init__.py
    │   │   │   └── check.py
    │   │   ├── router/                 # empty package (Phase 3)
    │   │   │   └── __init__.py
    │   │   ├── session/                # empty (Phase 2)
    │   │   │   └── __init__.py
    │   │   ├── queue/                  # empty (Phase 6)
    │   │   │   └── __init__.py
    │   │   ├── tui/
    │   │   │   ├── __init__.py
    │   │   │   ├── app.py              # CyberharnessApp Textual App
    │   │   │   ├── screens/
    │   │   │   │   ├── __init__.py
    │   │   │   │   ├── wizard.py       # WizardScreen (3 questions)
    │   │   │   │   └── main.py         # MainScreen stub — placeholder for Phase 5
    │   │   │   └── commands.py         # /mode local | /mode online handler
    │   │   └── cli/
    │   │       ├── __init__.py
    │   │       └── main.py             # Typer app + subcommands
    │   └── tests/
    │       ├── test_config.py
    │       ├── test_paths.py
    │       ├── test_cli_smoke.py
    │       └── test_wizard.py
    ├── server/
    │   ├── pyproject.toml              # name = "cyberharness-server"; empty package
    │   └── src/cyberharness_server/__init__.py
    └── workspace/
        ├── pyproject.toml              # name = "cyberharness-workspace"; empty
        └── src/cyberharness_workspace/__init__.py
```

### Pattern 1: uv Workspace Root

**What:** Root `pyproject.toml` declares the workspace; each member has its own `pyproject.toml`. A single `uv.lock` covers all members.
**When to use:** Now (Phase 1) — sets the shape all downstream phases build on.

```toml
# /pyproject.toml  (workspace root)
[project]
name = "cyberharness-workspace-root"
version = "0.0.0"
requires-python = ">=3.11"
# No user-facing deps here; workspace members carry their own.

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv]
# Dev tooling shared across all members
dev-dependencies = [
  "pytest>=8",
  "pytest-asyncio>=0.24",
  "ruff>=0.7",
  "mypy>=1.11",
  "textual-dev>=1.7",
]
```

```toml
# /packages/client/pyproject.toml
[project]
name = "cyberharness"
version = "0.1.0"
description = "Connectivity-aware AI harness for the Jetson Cyberdeck"
requires-python = ">=3.11"
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
  "filelock>=3.29,<4",
]

[project.scripts]
cyberharness = "cyberharness.cli.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Source: docs.astral.sh/uv/concepts/projects/workspaces/ [CITED]. `uv sync` and `uv run` operate on the workspace root by default; use `--package cyberharness` to target the client from any directory.

### Pattern 2: pydantic-settings with TOML + env override

**What:** `Config(BaseSettings)` with `settings_customise_sources` returning `(init, env, toml)`. Env vars take precedence over TOML values, and TOML values take precedence over defaults.
**When to use:** In `config.py`, called exactly once at startup by `Config.load()`.

```python
# packages/client/src/cyberharness/config.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Literal
from pydantic import Field, HttpUrl
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
    TomlConfigSettingsSource,
)


DEFAULT_CONFIG_PATH = Path.home() / ".cyberharness" / "config.toml"


class ModelsConfig(BaseSettings):
    local_url: str = "http://localhost:11434"
    local_model: str = "llama3.2:3b-instruct-q4_K_M"


class RoutingConfig(BaseSettings):
    mode: Literal["local", "online"] = "local"


class ProbeConfig(BaseSettings):
    interval_seconds: int = Field(default=30, ge=1)
    probe_host: str = "1.1.1.1"


class PathsConfig(BaseSettings):
    data_dir: str = "~/.cyberharness"


class Config(BaseSettings):
    """Root config. Loads from TOML + env; env wins.

    Env var pattern: CYBERHARNESS_MODELS__LOCAL_URL=...  (double underscore for nesting)
    """
    model_config = SettingsConfigDict(
        env_prefix="CYBERHARNESS_",
        env_nested_delimiter="__",
        extra="forbid",  # typo in config.toml → clear pydantic error at startup
    )

    models: ModelsConfig = Field(default_factory=ModelsConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    probe: ProbeConfig = Field(default_factory=ProbeConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        toml_path = Path(
            os.environ.get("CYBERHARNESS_CONFIG", str(DEFAULT_CONFIG_PATH))
        )
        # Priority (leftmost wins): init > env > TOML > defaults
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=toml_path),
        )


def config_exists() -> bool:
    return Path(os.environ.get(
        "CYBERHARNESS_CONFIG", str(DEFAULT_CONFIG_PATH)
    )).is_file()


def load_config() -> Config:
    """Loads and validates. Raises pydantic.ValidationError with a clear
    message on typo / missing required field / bad type."""
    return Config()
```

Source: pydantic.dev/docs/validation/latest/api/pydantic_settings/ — `TomlConfigSettingsSource(settings_cls, toml_file=...)` [CITED]. Priority ordering is per pydantic-settings docs (earlier sources win) [CITED].

### Pattern 3: Idempotent Workspace Initialisation

**What:** `Paths.ensure_workspace()` calls `mkdir(parents=True, exist_ok=True)` for every required subdir. Runs unconditionally on every startup — no "already initialised?" check.
**When to use:** After `Config.load()` succeeds, before the TUI mounts.

```python
# packages/client/src/cyberharness/paths.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

_SUBDIRS = (
    "sessions",
    "queue",
    "workspace",
    "bench",
    "knowledge/wiki",
    "knowledge/refs",
)


@dataclass(frozen=True)
class Paths:
    data_dir: Path

    @property
    def config_toml(self) -> Path:
        return self.data_dir / "config.toml"

    @property
    def sessions(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def queue(self) -> Path:
        return self.data_dir / "queue"

    @property
    def bench(self) -> Path:
        return self.data_dir / "bench"

    @property
    def knowledge(self) -> Path:
        return self.data_dir / "knowledge"

    @classmethod
    def from_config(cls, config) -> "Paths":
        return cls(data_dir=Path(config.paths.data_dir).expanduser())

    def ensure_workspace(self) -> None:
        """Idempotent: creates any missing directories, silently repairs partial."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for sub in _SUBDIRS:
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
```

`mkdir(exist_ok=True)` is a single syscall (mkdir returning EEXIST is not an error), so there is no measurable cost vs. pre-checking. Pre-checking is strictly worse because it introduces a TOCTOU race between check and create.

### Pattern 4: Typer bare-command → Textual TUI

**What:** A top-level Typer callback with `invoke_without_command=True` checks `ctx.invoked_subcommand is None` and dispatches to the TUI launcher. Subcommands run their own logic and short-circuit the default.
**When to use:** In `cli/main.py`.

```python
# packages/client/src/cyberharness/cli/main.py
from __future__ import annotations
import typer
from cyberharness.config import config_exists, load_config
from cyberharness.paths import Paths

app = typer.Typer(
    name="cyberharness",
    help="Connectivity-aware AI harness. Run with no arguments to open the TUI.",
    no_args_is_help=False,
)

config_app = typer.Typer(help="View / edit config values.")
app.add_typer(config_app, name="config")


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return  # subcommand takes over
    _launch_tui()


def _launch_tui() -> None:
    from cyberharness.tui.app import CyberharnessApp
    CyberharnessApp(needs_wizard=not config_exists()).run()


@app.command()
def init() -> None:
    """Run the setup wizard manually."""
    from cyberharness.tui.app import CyberharnessApp
    CyberharnessApp(needs_wizard=True, wizard_only=True).run()


@config_app.command("show")
def config_show() -> None:
    cfg = load_config()
    typer.echo(cfg.model_dump_json(indent=2))


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """key is dotted, e.g. 'routing.mode'."""
    # Phase 1 implementation writes back through a small TOML editor helper.
    ...


@app.command()
def status() -> None:
    cfg = load_config()
    paths = Paths.from_config(cfg)
    typer.echo(f"data_dir: {paths.data_dir}")
    typer.echo(f"mode:     {cfg.routing.mode}")
    typer.echo(f"local:    {cfg.models.local_url}")


@app.command()
def probe() -> None:
    """One-shot TCP connectivity check against configured probe host."""
    from cyberharness.probe.check import probe_once
    ok, latency_ms = probe_once()
    typer.echo(f"{'online' if ok else 'offline'} ({latency_ms:.1f} ms)")


@app.command()
def bench() -> None:
    """Stub — real bench logic lands in Phase 4."""
    typer.echo("Bench not yet implemented (Phase 4).")
```

Source: typer.tiangolo.com/tutorial/commands/context/ — `invoke_without_command=True` + `ctx.invoked_subcommand is None` is the sanctioned pattern [CITED].

### Pattern 5: Textual multi-screen wizard

**What:** `WizardScreen` is a `ModalScreen[dict[str, str]]` that walks the user through 3 questions and calls `self.dismiss(result_dict)` on completion. The `App` receives the result via callback and writes `config.toml`.
**When to use:** On first run (no `config.toml`) and on `cyberharness init`.

```python
# packages/client/src/cyberharness/tui/screens/wizard.py
from __future__ import annotations
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class WizardScreen(ModalScreen[dict[str, str]]):
    """Three-question setup wizard.

    Returns a dict on dismiss:
      {"local_url": ..., "mode": "local"|"online", "data_dir": ...}
    """

    CSS = """
    WizardScreen { align: center middle; }
    Vertical { width: 60; height: auto; padding: 1 2; border: round $primary; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._answers: dict[str, str] = {}
        self._step = 0
        self._questions = [
            ("local_url", "Ollama URL:", "http://localhost:11434"),
            ("mode",      "Mode (local/online):", "local"),
            ("data_dir",  "Data directory:", str(Path.home() / ".cyberharness")),
        ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("cyberharness setup", id="title")
            yield Label(self._questions[0][1], id="prompt")
            yield Input(value=self._questions[0][2], id="answer")
            yield Button("Next", id="next", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        answer = self.query_one("#answer", Input).value
        key, _, _ = self._questions[self._step]
        self._answers[key] = answer
        self._step += 1
        if self._step >= len(self._questions):
            self.dismiss(self._answers)
        else:
            key, prompt, default = self._questions[self._step]
            self.query_one("#prompt", Label).update(prompt)
            inp = self.query_one("#answer", Input)
            inp.value = default
            inp.focus()
            if self._step == len(self._questions) - 1:
                event.button.label = "Finish"
```

```python
# packages/client/src/cyberharness/tui/app.py
from textual.app import App
from cyberharness.tui.screens.wizard import WizardScreen
from cyberharness.tui.screens.main import MainScreen
from cyberharness.config import load_config
from cyberharness.paths import Paths


class CyberharnessApp(App):
    def __init__(self, needs_wizard: bool, wizard_only: bool = False) -> None:
        super().__init__()
        self._needs_wizard = needs_wizard
        self._wizard_only = wizard_only

    def on_mount(self) -> None:
        if self._needs_wizard:
            self.push_screen(WizardScreen(), self._on_wizard_done)
        else:
            self._boot_main()

    def _on_wizard_done(self, answers: dict[str, str] | None) -> None:
        if answers is None:
            self.exit(1)
            return
        _write_initial_config(answers)  # writes ~/.cyberharness/config.toml
        if self._wizard_only:
            self.exit(0)
            return
        self._boot_main()

    def _boot_main(self) -> None:
        cfg = load_config()
        Paths.from_config(cfg).ensure_workspace()
        self.push_screen(MainScreen(cfg))
```

Source: textual.textualize.io/guide/screens/ — `push_screen(screen, callback)` + `dismiss(result)` is the documented data-passing pattern [CITED].

### Pattern 6: Slash-command mode toggle that persists

**What:** TUI listens for `/mode local` / `/mode online`; handler rewrites `[routing].mode` in `config.toml` atomically and updates the in-memory `Config`.
**When to use:** In `tui/commands.py`.

```python
# packages/client/src/cyberharness/tui/commands.py
import os
import tomllib
import tempfile
from pathlib import Path

def set_mode(config_path: Path, mode: str) -> None:
    if mode not in ("local", "online"):
        raise ValueError(f"mode must be 'local' or 'online', got {mode!r}")
    data = tomllib.loads(config_path.read_text())
    data.setdefault("routing", {})["mode"] = mode
    # Atomic write — cheap insurance against corrupt config on crash mid-write.
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(_serialise_toml(data))
    os.replace(tmp, config_path)
```

For serialisation, either `tomli-w` (adds a dep) or a small hand-roller that only handles the four sections we own. Given the closed config schema (D-05), a hand-roller is fine and avoids a dep.

### Anti-Patterns to Avoid

- **`if not path.exists(): path.mkdir()`.** Pointless TOCTOU race. Use `mkdir(exist_ok=True)`.
- **Reading config globally at import time.** Import-time IO makes CLI subcommand latency bad and blows up testability. Load lazily inside handlers.
- **Two codepaths for wizard: CLI prompt and TUI screen.** Keep one Textual screen; `cyberharness init` reuses it. Avoids drift.
- **Storing secrets in `config.toml`.** Explicitly forbidden by D-08 and Pitfall 9. Read from env only.
- **A `--config` CLI flag.** Explicitly forbidden by D-06.
- **`asyncio.run()` inside a Textual `on_mount`.** Textual already owns the loop; nested runs deadlock. Use `App.run_worker`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOML + env layered config with priority | Custom merge over `tomllib.load` and `os.environ` | `pydantic-settings.TomlConfigSettingsSource` | Layered priority + nested env names + typed validation for free. |
| CLI subcommand dispatch with type hints | argparse | Typer | Type-hint driven, `invoke_without_command`, well-tested. |
| Multi-screen TUI wizard | Chained `input()` in a thread | Textual `push_screen`/`dismiss` | One-shot dismiss with typed result is much less error-prone than mutable shared state. |
| Idempotent directory tree creation | `if not exists: mkdir` loops | `Path.mkdir(parents=True, exist_ok=True)` | Single syscall, no races, minimal code. |
| Console-script entry point | Wrapper shell scripts | `[project.scripts]` in `pyproject.toml` | Standard PEP 621; hatchling wires it up automatically. |
| Python 3.11 install on Jetson | apt-get + deadsnakes surgery | `uv python install 3.11` | Self-contained aarch64 build in `~/.local/share/uv/`. |
| Cross-platform paths | Manual `~` expansion + string concat | `pathlib.Path` with `expanduser()` | Fewer bugs, portable. |
| Lockfile mgmt | pip-tools + requirements.txt | `uv.lock` | uv writes it and keeps it consistent across workspace members. |

**Key insight:** For Phase 1 there is *almost nothing worth hand-rolling*. The scaffolding is a composition of five well-established libraries; the value is in wiring them correctly, not in writing custom code.

## Runtime State Inventory

Not applicable — Phase 1 is greenfield. No prior installs, no stored data, no running services, no OS registrations. This section is omitted per the researcher instructions ("Omit entirely for greenfield phases"). Left in the outline explicitly so the planner knows the omission is deliberate, not forgotten.

## Common Pitfalls

### Pitfall 1: TOML config typo produces cryptic error

**What goes wrong:** User writes `probe_hostt = "1.1.1.1"` in `config.toml`. Without `extra="forbid"`, pydantic-settings silently ignores the unknown key and uses the default for `probe_host`, and the user's typo never surfaces.
**Why it happens:** Pydantic's default is `extra="ignore"`.
**How to avoid:** Set `extra="forbid"` on `SettingsConfigDict` (shown in Pattern 2 above). This makes a typo raise `ValidationError` at startup with the exact key name.
**Warning signs:** User reports "my config change didn't do anything."

### Pitfall 2: Nested env var override doesn't work

**What goes wrong:** User exports `CYBERHARNESS_MODELS_LOCAL_URL=...` (single underscore) expecting it to override `[models].local_url`. It doesn't — pydantic-settings treats the whole name as a top-level field.
**Why it happens:** Without `env_nested_delimiter`, nested fields aren't reachable by env vars.
**How to avoid:** Set `env_nested_delimiter="__"` (double underscore) — env var is then `CYBERHARNESS_MODELS__LOCAL_URL`. Document this in the README.
**Warning signs:** Env overrides "sometimes" work but not for nested keys.

### Pitfall 3: uv workspace member name collision

**What goes wrong:** Two members declare the same `name` in their `pyproject.toml`, or the client package name shadows a transitive dep.
**Why it happens:** Beginner mistake with workspaces.
**How to avoid:** `cyberharness` for the client, `cyberharness-server` for the server stub, `cyberharness-workspace` for the workspace stub. Never reuse a name.
**Warning signs:** `uv sync` errors with "duplicate project name" or resolves the wrong package.

### Pitfall 4: Textual wizard on first run: how does the TUI show anything before config is loaded?

**What goes wrong:** The natural instinct is to load config in `App.__init__`. If config is missing, we crash before the wizard can render.
**Why it happens:** Boot-order confusion.
**How to avoid:** The CLI entry point decides `needs_wizard = not config_exists()` *before* constructing the App. Config load only happens after the wizard finishes (in `_on_wizard_done → _boot_main`). See Pattern 5.
**Warning signs:** Traceback with `ConfigError: no config.toml` on first run instead of a wizard.

### Pitfall 5: `uv tool install` from a workspace member behaves differently than expected

**What goes wrong:** `uv tool install cyberharness` from a git clone doesn't find the workspace member.
**Why it happens:** `uv tool install` is not documented as workspace-aware; it expects a PyPI name, a git URL, or a local path pointing at a package (not a workspace root).
**How to avoid:** Document `uv run cyberharness` as the canonical Phase 1 invocation. If a global tool install is needed, use `uv tool install ./packages/client` (path form) rather than `uv tool install cyberharness`. See Assumption A1.
**Warning signs:** User reports `error: package `cyberharness` not found`.

### Pitfall 6: Blocking the Textual loop during wizard-completion IO

**What goes wrong:** `_on_wizard_done` synchronously writes `config.toml`, expands `~`, creates workspace dirs, then constructs `Config()` (which reads the TOML). All this on the event loop.
**Why it happens:** These operations are individually cheap, so it "looks fine."
**How to avoid:** For Phase 1 the total work is well under 10ms on any reasonable disk, so sync is fine. If we ever add slower work here (e.g., model pull), wrap in `App.run_worker(thread=True)`. Note the pattern for future phases.
**Warning signs:** Noticeable freeze between "Finish" and main screen mount.

### Pitfall 7: `config set routing.mode online` corrupts the TOML

**What goes wrong:** A naive rewrite serialises TOML in a way that loses comments, reorders sections, or fails on values with special characters.
**Why it happens:** `tomllib` is read-only; `tomli-w` is add-only for writes. Hand-rollers are easy to get wrong.
**How to avoid:** For Phase 1's closed schema (four sections, only scalar values), a hand-rolled writer that emits the four sections in fixed order is safe and dep-free. Use atomic replace (`os.replace`) so a crash mid-write can't corrupt.
**Warning signs:** Config file loses formatting or an unrelated field on `config set`.

### Pitfall 8: `data_dir` from config points somewhere unexpected

**What goes wrong:** User sets `data_dir = "/mnt/ssd/cyberharness"` in `config.toml`, but `~/.cyberharness/config.toml` still exists at the default location. The harness reads the default location for the config itself, then honors `data_dir` for the workspace.
**Why it happens:** Two paths — config file location vs. data dir — that could be conflated.
**How to avoid:** Document that config always lives at `~/.cyberharness/config.toml` (D-06 makes this explicit) and that `[paths].data_dir` only relocates the *workspace subdirs*. If users want to move both, they should symlink `~/.cyberharness/` itself.
**Warning signs:** Confusion in support tickets about which location "moves."

## Code Examples

Concentrated at the top of each Pattern section above. Complete list of production-shape snippets:

- `Config` class with `TomlConfigSettingsSource` + env override → Pattern 2
- `Paths.ensure_workspace()` idempotent init → Pattern 3
- Typer `@app.callback(invoke_without_command=True)` bare→TUI dispatch → Pattern 4
- `WizardScreen` Textual `ModalScreen[dict]` with `dismiss(result)` → Pattern 5
- `CyberharnessApp.on_mount` push_screen with callback → Pattern 5
- Atomic `config.toml` rewrite for `/mode` slash command → Pattern 6

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `setuptools` + `setup.py` | PEP 621 `pyproject.toml` + `hatchling` build backend | 2022+ | Zero-config for pure-Python; no more `setup.py` gotchas. |
| pip + `virtualenv` + `pip-tools` | `uv` (single tool: resolver + venv + lock + tool install) | 2024+ | 10-100x faster, single lockfile, workspace-native. |
| Custom TOML loader per project | `pydantic-settings` `TomlConfigSettingsSource` | pydantic-settings ≥ 2.2 | Layered priority + typed validation for free. |
| `python-dotenv` for config | `pydantic-settings` (dotenv is one of its sources) | 2022+ | Unified layered config. |
| Poetry | uv | 2024+ | Faster, workspace-first, aarch64-clean. |
| `click` directly | `typer` on top of Click | 2020+ | Type-hint declarations; ergonomically nicer. |
| `blessed` / `urwid` | `textual` for async TUIs | 2022+ | Async-native, batteries-included widgets. |

**Deprecated / avoid:**
- `setup.py` — no reason to write one in 2026.
- `requirements.txt` alone (without a lockfile) — use `uv.lock`.
- `pkg_resources` / `distutils` — removed in 3.12; use `importlib.metadata`.
- `dataclasses`-only config with hand-rolled TOML load — pydantic-settings covers this with validation.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `uv tool install ./packages/client` correctly installs a workspace member's console script (`cyberharness`) to `~/.local/bin` on aarch64 Linux. | Installation / Pitfall 5 | Medium — if wrong, we fall back to documented `uv run cyberharness`, which is still a single command and satisfies CONF-01. Recommend planner verify on a real Jetson before writing user-facing install docs. |
| A2 | Every dep listed in the aarch64 audit publishes a manylinux2014_aarch64 wheel for Python 3.11 as of 2026-07-08. Cross-checked against STACK.md (which verified 2026-07-07) — trusting that a day hasn't broken this. | Standard Stack / ARM64 | Low — even a source build for any one of these is possible on Jetson if the wheel is missing; would slow install by minutes only. Planner should include a `checkpoint:human-verify` at first-time Jetson install. |
| A3 | Jetson JetPack 6 has a working C toolchain (build-essential + cargo installed by JetPack or by user), so if a wheel is missing pydantic-core / watchfiles can build from source. If not, we rely purely on wheels. | Environment | Low — same as A2. |
| A4 | `slopcheck` legitimacy verification was not run in this research environment. Every listed package is on the STACK.md project-locked stack and has a public source repo, so risk is low. | Package Legitimacy Audit | Low — planner should still run slopcheck before install as a cheap belt-and-braces check. |
| A5 | Workspace stub members (`packages/server/`, `packages/workspace/`) can be declared with a minimal `pyproject.toml` and an empty `src/<pkg>/__init__.py` without breaking `uv sync`. | Project Structure | Low — uv docs explicitly allow empty packages. Verified against docs.astral.sh/uv. |
| A6 | Textual 8.2.8's `ModalScreen[T]` and `push_screen(screen, callback)` API match the code in Pattern 5 exactly. Signatures verified against the docs page, not against a running Textual 8.2.8 install. | Pattern 5 | Low — Textual has been API-stable on Screens since 3.x. Planner should smoke-test the wizard flow. |
| A7 | Hand-rolled TOML writer for the four-section config is sufficient (no `tomli-w` dep needed). | Pitfall 7 / Pattern 6 | Low — schema is closed and scalar-only. |

## Open Questions

1. **`uv tool install` semantics for a workspace member on aarch64 Linux.**
   - What we know: `uv sync` + `uv run` are documented to work on workspaces; `uv tool install` is documented for PyPI names, git URLs, and (implicitly) local paths.
   - What's unclear: Whether `uv tool install ./packages/client` is the exact right form, and whether it produces a `cyberharness` binary on PATH.
   - Recommendation: Ship `uv run cyberharness` as the documented install path for Phase 1; validate `uv tool install ./packages/client` on a real Jetson in Phase 1 execution as a stretch task.

2. **Should `probe` in Phase 1 be a real TCP check or a stub?**
   - What we know: The check is trivial (`asyncio.open_connection(host, 443)` with timeout).
   - What's unclear: Whether wiring httpx into `probe/` this early conflicts with Phase 3's probe design.
   - Recommendation: Implement a **minimal TCP-connect probe** (no httpx yet) in `probe/check.py` — 20 lines, satisfies D-14 without pre-empting Phase 3's design. Phase 3 replaces it with the full async loop + EventBus.

3. **`config set` writer: hand-roll vs. `tomli-w` dep?**
   - What we know: Schema is closed; scalar values only; comments in `config.toml` are not required to survive rewrites (we generate the file, users don't hand-edit heavily).
   - Recommendation: Hand-roll for Phase 1. If Phase 2+ ever gains complex config sections (nested tables, arrays of tables), pull `tomli-w` in then.

## Environment Availability

Phase 1 targets aarch64 Linux. The install steps assume:

| Dependency | Required By | Available on Jetson JetPack 6 by default? | Fallback |
|------------|------------|----|----------|
| curl | Bootstrap uv install | ✓ | `wget` — Astral install script also works via wget |
| Python (any 3.x) | Bootstrap uv | ✓ (3.10 default) | uv is a static aarch64 binary — no Python needed to install uv |
| Python 3.11 | Runtime | ✗ (3.10 default; installed via `uv python install 3.11`) | — |
| Cargo / rustc | Source-build fallback for `pydantic-core` if wheel missing | Usually not installed | Wheel should be available; if not, `apt install build-essential cargo` |
| git | Clone the repo | ✓ | Download tarball |
| C toolchain (build-essential) | Source-build fallback for any Rust/C dep | Usually available on JetPack | — |

Because this is a research environment on macOS, the audit above is **derived from JetPack 6 documentation, not directly probed on hardware**. Flagging Assumption A3.

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** Cargo/rustc — falls back to prebuilt wheels for pydantic-core / watchfiles; risk is low.

## Validation Architecture

`.planning/config.json` does not exist at research time. Treating `workflow.nyquist_validation` as enabled per default rule.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | none — Wave 0 must create `pyproject.toml` `[tool.pytest.ini_options]` section (or `pytest.ini` at repo root) |
| Quick run command | `uv run pytest -x --ff` |
| Full suite command | `uv run pytest` |

Textual provides `Pilot` for TUI smoke tests via `App.run_test()` — official pattern; ARM64-clean. Use it for wizard smoke tests.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| CONF-01 | `uv sync` resolves; `uv run cyberharness --help` prints | integration (shell) | `uv sync && uv run cyberharness --help` | ❌ Wave 0 |
| CONF-01 | Package importable from installed venv | unit | `uv run pytest packages/client/tests/test_cli_smoke.py -x` | ❌ Wave 0 |
| CONF-02 | Config loads from a temp TOML file (via `CYBERHARNESS_CONFIG`) | unit | `uv run pytest packages/client/tests/test_config.py::test_load_from_toml -x` | ❌ Wave 0 |
| CONF-02 | Env var `CYBERHARNESS_ROUTING__MODE=online` overrides TOML value | unit | `uv run pytest packages/client/tests/test_config.py::test_env_override -x` | ❌ Wave 0 |
| CONF-02 | Typo in config (`extra=forbid`) raises `ValidationError` with clear message | unit | `uv run pytest packages/client/tests/test_config.py::test_typo_rejected -x` | ❌ Wave 0 |
| CONF-02 | Missing required field surfaces field name in error | unit | `uv run pytest packages/client/tests/test_config.py::test_missing_field -x` | ❌ Wave 0 |
| CONF-03 | `Paths.ensure_workspace()` creates all six subdirs from empty state | unit | `uv run pytest packages/client/tests/test_paths.py::test_first_run -x` | ❌ Wave 0 |
| CONF-03 | `Paths.ensure_workspace()` is idempotent — repeated calls no-op | unit | `uv run pytest packages/client/tests/test_paths.py::test_idempotent -x` | ❌ Wave 0 |
| CONF-03 | Partial workspace (some dirs missing) is silently repaired | unit | `uv run pytest packages/client/tests/test_paths.py::test_partial_repair -x` | ❌ Wave 0 |
| CONF-04 | Config `[routing].mode` accepts `"local"` and `"online"` and rejects anything else | unit | `uv run pytest packages/client/tests/test_config.py::test_mode_literal -x` | ❌ Wave 0 |
| CONF-04 | `/mode online` slash command writes `mode = "online"` back to TOML | unit | `uv run pytest packages/client/tests/test_wizard.py::test_mode_toggle_persists -x` | ❌ Wave 0 |
| CONF-04 | After toggle, next `load_config()` reflects new mode | integration | `uv run pytest packages/client/tests/test_wizard.py::test_mode_toggle_reloads -x` | ❌ Wave 0 |
| (wizard) | First-run wizard collects 3 answers and writes valid `config.toml` | integration (Textual Pilot) | `uv run pytest packages/client/tests/test_wizard.py::test_first_run_flow -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -x --ff` (fail-fast, failed-first)
- **Per wave merge:** `uv run pytest` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `/pyproject.toml` — workspace root + shared dev deps
- [ ] `/packages/client/pyproject.toml` — client package + `[project.scripts]`
- [ ] `/packages/server/pyproject.toml` — stub
- [ ] `/packages/workspace/pyproject.toml` — stub
- [ ] `/packages/client/tests/conftest.py` — `tmp_home` fixture that sets `HOME` + `CYBERHARNESS_CONFIG` to a temp dir; auto-clean.
- [ ] `/packages/client/tests/test_config.py` — covers CONF-02, CONF-04 (mode literal)
- [ ] `/packages/client/tests/test_paths.py` — covers CONF-03
- [ ] `/packages/client/tests/test_cli_smoke.py` — covers CONF-01
- [ ] `/packages/client/tests/test_wizard.py` — covers wizard flow + CONF-04 toggle
- [ ] Framework install: dev deps declared in workspace root `[tool.uv]` — `uv sync` installs them.

## Security Domain

`.planning/config.json` not present; default is `security_enforcement` enabled. Phase 1 is scaffolding — the security surface is small but real.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 1 has no auth surface. |
| V3 Session Management | no | Sessions are Phase 2. |
| V4 Access Control | no | Single-user local tool. |
| V5 Input Validation | yes | pydantic-settings validates all config; `[routing].mode` is `Literal["local","online"]`; `probe.interval_seconds` has `ge=1`. |
| V6 Cryptography | no | No crypto in Phase 1. |
| V7 Error Handling & Logging | yes | Config errors surface field names, not raw values (avoid leaking user-typed URLs into logs by default). |
| V8 Data Protection | yes | Enforce `os.umask(0o077)` at startup so any files created under `~/.cyberharness/` are user-only. Config file created with mode 0600. |
| V10 Malicious Code | yes | `slopcheck install ...` before adding any package (project protocol). Pin all deps with upper bounds. |
| V14 Configuration | yes | `extra="forbid"` catches typos; secrets rule (D-08) enforced by schema (no secret fields present). |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Config typo produces silent misconfiguration | Tampering | `extra="forbid"` in `SettingsConfigDict` |
| Secret leaks to disk via config.toml | Information Disclosure | Schema has no secret fields; env-only for future secrets (D-08) |
| World-readable config / workspace on multi-user Jetson | Info Disclosure | `os.umask(0o077)` at startup; explicit `chmod 0600` on config write |
| Race between two harness processes writing config simultaneously | Tampering | Atomic write via `os.replace(tmp, final)` (Pattern 6) |
| Slopsquatted dep sneaks in via `pyproject.toml` | Elevation of Privilege | `slopcheck install` in the plan; pinned upper bounds; audit table |
| Malicious TOML with pathological nesting DoSes startup | DoS | `tomllib` is stdlib; not a known DoS vector for our schema shape |
| User-provided `data_dir` escapes home | Tampering / Info Disclosure | `Path(...).expanduser().resolve()` — accept any absolute path but never follow untrusted symlinks blindly |

## Sources

### Primary (HIGH confidence)

- `.planning/research/STACK.md` — project-locked stack with versions and ARM64 audit (2026-07-07)
- `.planning/research/ARCHITECTURE.md` — package structure, `config.py`/`paths.py`/`events.py`/`errors.py` layout
- `.planning/research/PITFALLS.md` — ARM64 wheel gaps, secrets, atomic writes
- `docs/architecture.md` — canonical config schema and directory layout
- `docs/session-design.md` — `~/.cyberharness/` directory structure
- docs.astral.sh/uv/concepts/projects/workspaces/ — uv workspace mechanics (fetched 2026-07-08)
- pydantic.dev/docs/validation/latest/concepts/pydantic_settings/ — settings customisation (fetched 2026-07-08)
- pydantic.dev/docs/validation/latest/api/pydantic_settings/ — `TomlConfigSettingsSource` API (fetched 2026-07-08)
- textual.textualize.io/guide/screens/ — `push_screen` / `dismiss` / `ModalScreen` (fetched 2026-07-08)
- typer.tiangolo.com/tutorial/commands/context/ — `invoke_without_command` + `ctx.invoked_subcommand` (fetched 2026-07-08)
- pypi.org — version verification for all 11 core+support packages (fetched 2026-07-08)

### Secondary (MEDIUM confidence)

- `uv tool install` behaviour for a workspace member — inferred from docs.astral.sh/uv/guides/tools/, not directly documented for workspace members. Flagged in Assumption A1.

### Tertiary (LOW confidence)

- None used for load-bearing claims. Any LOW-confidence item would have been flagged with `[ASSUMED]`.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — every version verified on PyPI 2026-07-08; matches project-locked STACK.md.
- Config pattern (pydantic-settings + TOML + env): HIGH — pattern is directly documented; code sample follows the API reference.
- Directory init pattern: HIGH — `pathlib.Path.mkdir(exist_ok=True)` is stdlib-standard.
- Typer bare-command dispatch: HIGH — official pattern from Typer docs.
- Textual multi-screen wizard: HIGH for the API pattern; MEDIUM for the exact widget composition (there are stylistic alternatives).
- uv workspace: HIGH for `[tool.uv.workspace] members`; MEDIUM for `uv tool install` from a workspace member (Assumption A1).
- ARM64 packaging: HIGH — every dep verified against STACK.md's aarch64 audit, all pure-Python or with published aarch64 wheels.

**Research date:** 2026-07-08
**Valid until:** ~2026-08-07 (30 days — stable stack). Re-verify uv workspace semantics and Textual API if Phase 1 hasn't started by then.

---
*Phase 1 research complete. Ready for `/gsd-plan-phase` planner.*
