# Phase 1: Foundation & Scaffold - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-08
**Phase:** 1-foundation-scaffold
**Areas discussed:** Package structure, Config schema, CLI entry point, First-run behavior

---

## Package Structure

| Option | Description | Selected |
|--------|-------------|----------|
| src/ layout | Standard modern Python layout — prevents accidental imports from project root | ✓ |
| Flat layout | Simpler, one less directory level | |

**User's choice:** src/cyberharness/ layout

| Option | Description | Selected |
|--------|-------------|----------|
| Single package, subdirs per component | src/cyberharness/ with probe/, router/, session/, etc. | ✓ |
| Split client/server from day one | Separate installable packages in monorepo | |

**User's choice:** Single package with component subdirs

| Option | Description | Selected |
|--------|-------------|----------|
| packages/ subdirectory from day one | Monorepo layout: packages/client/, packages/server/ stub, packages/workspace/ stub | ✓ |
| Root package now, extract later | Ship as root package for v1.0, extract to packages/ in v1.1 | |
| Single repo, not a monorepo | Separate repos when server work starts | |

**User's choice:** packages/ from day one — anticipates server, meta-harnesses, workspace packages
**Notes:** User specifically asked to think about how the server, meta-harnesses, workspaces, and client fit into a monorepo. The packages/ layout was the answer.

| Option | Description | Selected |
|--------|-------------|----------|
| 3.11 minimum | Gets TaskGroup, tomllib; install via uv on Jetson | ✓ |
| 3.10 minimum | Ships on JetPack 6 without extra setup | |
| 3.12 minimum | Latest stable | |

**User's choice:** 3.11 minimum

---

## Config Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: models + routing + probe + paths | 4 sections, sensible defaults | ✓ |
| Full schema upfront | All sections including [ui], [logging], [bench] | |
| Just mode + paths | Only what Phase 1 actually uses | |

**User's choice:** Minimal — models + routing + probe + paths

| Option | Description | Selected |
|--------|-------------|----------|
| ~/.cyberharness/config.toml always | Simple, predictable, CYBERHARNESS_CONFIG override for testing | ✓ |
| XDG: ~/.config/cyberharness/ | Follows XDG spec | |
| Configurable via --config flag | Multiple profiles possible | |

**User's choice:** Fixed path at ~/.cyberharness/config.toml

| Option | Description | Selected |
|--------|-------------|----------|
| Generate default config.toml | Write commented template and continue | |
| Error with instructions | Print error, suggest 'cyberharness init' | |
| Run in safe defaults | File is optional, all config has defaults | |
| TUI wizard | First-run wizard collects 3 questions and writes config | ✓ |

**User's choice:** TUI wizard — freeform response "tui wizard"

| Option | Description | Selected |
|--------|-------------|----------|
| 3 questions: Ollama URL, mode, data dir | Fast, sensible defaults offered | ✓ |
| Full setup: Ollama URL, mode, data dir, probe interval, model name | Covers everything upfront | |
| Just confirm defaults | Show defaults, ask y/n | |

**User's choice:** 3 questions: Ollama URL, mode (All Local/Wait Online), data dir

---

## CLI Entry Point

| Option | Description | Selected |
|--------|-------------|----------|
| Launch the TUI | cyberharness alone starts chat TUI | ✓ |
| Show help | Print usage/help | |
| Show status | Health check | |

**User's choice:** Launch the TUI

**Subcommands for Phase 1 (multi-select):**
- cyberharness init ✓
- cyberharness config ✓
- cyberharness status ✓
- cyberharness probe ✓
- benchmark/evals ✓ (as stub)

**User's choice:** All five, including bench as a stub

| Option | Description | Selected |
|--------|-------------|----------|
| Typer for subcommands, Textual for main UI | Typer dispatches; cyberharness alone launches Textual App | ✓ |
| Textual handles everything | All commands through Textual | |
| Click directly | No Typer wrapper | |

**User's choice:** Typer + Textual

---

## First-Run Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Detect no config → wizard → write config → create dirs → launch TUI | Full setup in one shot | ✓ |
| Detect no config → wizard → write config → exit | Init separate from launch | |
| init is always manual | User must run cyberharness init before first use | |

**User's choice:** Auto-detect → wizard → write config → create dirs → launch TUI

| Option | Description | Selected |
|--------|-------------|----------|
| Silently create missing dirs | Idempotent — always ensures all 4 dirs exist | ✓ |
| Warn and create | Print what was created | |
| Error and ask user to re-run init | Strict repair required | |

**User's choice:** Silent idempotent creation

| Option | Description | Selected |
|--------|-------------|----------|
| Slash command: /mode local or /mode online | Natural for chat TUI | ✓ |
| Keyboard shortcut on status bar | Click/key on mode indicator | |
| cyberharness config set only | Mode changes require CLI command + restart | |

**User's choice:** /mode slash commands in TUI

---

## Claude's Discretion

- Logging setup (stdlib logging + RichHandler)
- `__version__` placement
- Error message formatting (Rich markup recommended)
- Whether cyberharness probe in Phase 1 is a real TCP check or stub

## Deferred Ideas

- TODO-001 (Ollama tool use parser bugs) — area is router/tools, belongs in Phase 3
