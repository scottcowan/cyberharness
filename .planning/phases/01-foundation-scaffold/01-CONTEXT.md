# Phase 1: Foundation & Scaffold - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers an installable Python project scaffold for cyberharness: monorepo layout with `packages/client/` as the active package, typed pydantic-settings config loaded from `~/.cyberharness/config.toml`, idempotent workspace directory initialization, a Typer CLI with Phase 1 subcommands, and a first-run TUI wizard. Nothing connects to Ollama, a router, or any model in this phase — this is pure scaffolding that downstream phases build on.

</domain>

<decisions>
## Implementation Decisions

### Repository & Package Structure
- **D-01:** `packages/` subdirectory from day one — monorepo layout anticipating `packages/client/`, `packages/server/` (stub), `packages/workspace/` (stub). Phase 1 builds `packages/client/` only.
- **D-02:** `src/cyberharness/` layout within `packages/client/` — i.e., `packages/client/src/cyberharness/`. Prevents accidental root imports, cleaner for uv + hatchling.
- **D-03:** Single package with component subdirs: `probe/`, `router/`, `session/`, `queue/`, `tui/`, `cli/`. No separate installable sub-packages yet.
- **D-04:** Python 3.11 minimum — install via `uv python install 3.11` on Jetson (bypasses JetPack 6's 3.10 default). Gets `TaskGroup`, `tomllib`, better asyncio.

### Config Schema
- **D-05:** Minimal `config.toml` for v1 — four sections only:
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
- **D-06:** Config lives at `~/.cyberharness/config.toml` always. Override with `CYBERHARNESS_CONFIG` env var for testing. No `--config` CLI flag.
- **D-07:** Missing `config.toml` on first run triggers the TUI setup wizard (not an error). The wizard asks 3 questions: Ollama URL, mode (All Local / Wait for Online), data directory. Writes config and creates workspace dirs, then launches TUI.
- **D-08:** pydantic-settings loads config — TOML file + env var override. Secrets (future API keys) always via env var, never in TOML.

### First-Run Behavior
- **D-09:** First-run sequence: detect no `config.toml` → run Textual TUI wizard (3 questions) → write `config.toml` → create workspace dirs → launch main TUI. Subsequent runs skip the wizard.
- **D-10:** Workspace initialization is idempotent — on every startup, silently create any missing dirs under `data_dir/`: `sessions/`, `queue/`, `workspace/`, `bench/`, `knowledge/`. No prompt, no error, no warning.
- **D-11:** Partial workspace (e.g., missing `bench/`) is silently repaired. No init command required.
- **D-12a:** `knowledge/` directory has two subdirs: `knowledge/wiki/` (project wiki, mirrors codebase structure) and `knowledge/refs/` (ingested external reference docs). Both are created on first run but start empty.

### CLI Entry Point
- **D-12:** `cyberharness` with no subcommand launches the Textual TUI (the primary surface).
- **D-13:** Typer for subcommand dispatch; Textual for the main UI. Entry point: `cyberharness = "cyberharness.cli:app"` in `pyproject.toml`.
- **D-14:** Phase 1 registers these subcommands (stubs are fine for commands whose logic ships later):
  - `cyberharness init` — run the setup wizard manually (also auto-triggers on first run)
  - `cyberharness config show` / `cyberharness config set <key> <value>` — view/edit config
  - `cyberharness status` — print workspace paths, config loaded, mode, version
  - `cyberharness probe` — run one connectivity check and print result
  - `cyberharness bench` — stub (Phase 4 logic); prints "Bench not yet implemented"
- **D-15:** Mode toggle at runtime via TUI slash command: `/mode local` and `/mode online`. Updates config and takes effect immediately without restart.

### Knowledge Base & CLAUDE.md
- **D-16:** Knowledge base lives at `~/.cyberharness/knowledge/` with two subdirs:
  - `knowledge/wiki/` — project wiki, mirrors the monorepo package structure (e.g., `wiki/packages/client/session/`, `wiki/packages/client/router/`). Each module/component gets a companion markdown file explaining its design.
  - `knowledge/refs/` — ingested external reference docs (API specs, crawled docs, etc.) stored as markdown for offline access.
- **D-17:** CLAUDE.md integration — each meta-harness (Cursor, Claude Code, etc.) is configured to read the workspace CLAUDE.md at its server-side path. No symlinks. The cyberharness server config maps each harness to its CLAUDE.md path. (v1.1 concern — Phase 1 just creates the `knowledge/` dir structure.)
- **D-18:** Wiki is accessible two ways in the TUI (Phase 5 concern, capture here as design intent):
  1. Via chat — user says "open the client session manager page" and the local model opens it in the artifact surface.
  2. Via direct navigation — a file browser / navigation mode in the artifact surface for browsing `knowledge/wiki/`.
  Both open the same markdown renderer in the artifact side surface.

### Claude's Discretion
- Logging setup (stdlib `logging` with `RichHandler` is the recommendation from research — implement as appropriate)
- `__version__` placement and version string format
- Error message formatting — use Rich markup for color, keep messages actionable
- Whether `cyberharness probe` in Phase 1 is a real TCP check or a stub (implement real check if straightforward, stub if blocked on Phase 3 probe component)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Decisions
- `.planning/PROJECT.md` — language, TUI, protocol, platform constraints (ARM64/Jetson)
- `.planning/REQUIREMENTS.md` — CONF-01 through CONF-04 (this phase's requirements)
- `.planning/ROADMAP.md` — Phase 1 success criteria (4 criteria), phase dependencies

### Research
- `.planning/research/STACK.md` — recommended deps with versions, ARM64 wheel compatibility, pyproject.toml skeleton
- `.planning/research/ARCHITECTURE.md` — recommended package structure, `paths.py` / `config.py` / `events.py` / `errors.py` layout, startup shape
- `.planning/research/PITFALLS.md` — ARM64 wheel gaps (Pitfall 10), secrets management (Pitfall 9)
- `.planning/research/SUMMARY.md` — executive summary, stack decisions rationale

### No external specs
No external ADRs or specs beyond the above. All decisions captured in this file.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None yet — greenfield project. `docs/architecture.md` and `docs/session-design.md` describe the intended architecture but no code exists.

### Established Patterns
- Architecture doc (`docs/architecture.md`) defines the file layout for `config.py`, `paths.py`, `events.py`, `errors.py` — follow it.
- Session design doc (`docs/session-design.md`) defines the `~/.cyberharness/` directory structure — implement exactly this.

### Integration Points
- Phase 1 output (`config.py`, `paths.py`, pyproject.toml) is the foundation that every subsequent phase imports from. Get types and config schema right here.
- Phase 2 (Session Manager) imports `Config` and `Paths` from Phase 1.
- Phase 3 (Router) imports `Config` and `EventBus` from Phase 1.

</code_context>

<specifics>
## Specific Ideas

- Monorepo layout with `packages/` anticipates `packages/server/` and `packages/workspace/` being added in v1.1 and v1.3 respectively.
- TUI first-run wizard is a Textual screen, not a plain `input()` loop — keeps it consistent with the rest of the UI.
- `/mode local` and `/mode online` slash commands in the TUI should update `config.toml` on disk so the mode persists across restarts.
- `cyberharness bench` is a registered subcommand stub in Phase 1 — this prevents the CLI from being restructured when Phase 4 adds the real bench logic.

</specifics>

<deferred>
## Deferred Ideas

- **Reviewed Todo: TODO-001 (Ollama tool use parser bugs)** — area is `router/tools`, belongs in Phase 3. Not in scope for Phase 1 scaffolding.

</deferred>

---

*Phase: 1-foundation-scaffold*
*Context gathered: 2026-07-08*
