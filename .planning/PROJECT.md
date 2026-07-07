# cyberharness

## What This Is

A connectivity-aware AI harness designed for the Jetson Cyberdeck. It routes GSD workflow phases to local Ollama when offline, queues cloud-required phases as named workflows, and drains to a remote server on reconnect. Session state lives in the harness — not the model — so context survives model switches and reboots.

The remote side is a sandboxed workspace server: provisions git repos/worktrees, manages auth (env keys, SSH, Claude.md, MCP config), exposes an OpenAI-compatible model endpoint that aggregates cloud providers (OpenAI, Anthropic) and meta-harnesses (Cursor, Claude Code), and supports a GSD-style TUI workflow for workspace setup. The Cyberdeck client connects to this relay to run cloud phases within a fully-configured remote workspace.

## Core Value

Context and work survive any connectivity transition — phases run locally when offline and seamlessly drain to the right remote model and workspace when reconnected.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

**Client (Cyberdeck)**
- [ ] Python chat-style TUI (Textual)
- [ ] Connectivity probe — interval check, connected/disconnected events
- [ ] Model router — local Ollama for offline/discuss phases, relay for cloud phases
- [ ] Session manager — per-phase message history, persisted to disk, resumable
- [ ] Workflow queue — YAML-defined workflows with model-class and work-type; code-based escape hatch
- [ ] Modes: All Local and Wait for Online
- [ ] Relay client — OpenAI-compatible HTTP client, auth handshake, routes requests to remote server

**Remote Server**
- [ ] TUI workspace provisioning flow — GSD-style new workspace setup
- [ ] Workspace config: git repos/worktrees, .env/auth keys, SSH keys, CLAUDE.md, MCP config, networking (tailscale, AWS CLI, gh CLI)
- [ ] OpenAI-compatible relay endpoint — aggregates cloud API providers (OpenAI, Anthropic) and meta-harnesses
- [ ] File browser — view sandbox files (excluding .env), lazygit-style diff view (diff-so-fancy)

### Out of Scope

- OAuth / user accounts — single-user tool, no multi-tenancy
- Mobile clients — Cyberdeck-first
- Real-time streaming to multiple connected clients simultaneously
- Relay aggregation of meta-harnesses in v1.0 — API providers only first

## Context

- Built for the Jetson Cyberdeck: https://github.com/scottcowan/jetson-cyberdeck
- GSD workflow system it integrates with: https://github.com/gsd-build
- Reference projects: opencode (https://github.com/anomalyco/opencode), gemini-cli (https://github.com/google-gemini/gemini-cli), earendil pi harness (https://github.com/earendil-works/pi)
- TUI references: lazygit (https://github.com/jesseduffield/lazygit), diff-so-fancy (https://github.com/so-fancy/diff-so-fancy)
- Both Ollama and Claude API are OpenAI messages-format compatible — router swaps endpoint/model, messages array unchanged
- Session state stored in `~/.cyberharness/sessions/`; queue in `~/.cyberharness/queue/`
- Phase routing: discuss/spec/explore → local Ollama; plan/execute/verify → relay (queued if offline)
- Connectivity: primary WiFi/Ethernet; secondary Reticulum mesh (LoRa via RNode) — rnsh to home server

## Constraints

- **Language**: Python — fastest iteration, best AI/LLM SDK support
- **TUI**: Textual — chat-style terminal interface
- **Protocol**: OpenAI messages format — shared between local (Ollama) and remote (relay)
- **Connectivity**: Must degrade gracefully to fully local operation; no hard dependency on cloud
- **Platform**: Jetson Cyberdeck (ARM64 Linux) — avoid dependencies that don't run on Jetson

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python for client | Fastest iteration, richest AI/LLM SDK ecosystem | — Pending |
| Textual for TUI | Chat-style terminal, good for Cyberdeck display | — Pending |
| OpenAI messages format everywhere | Both Ollama and Claude API accept it natively — router just swaps endpoint | — Pending |
| Session switch only at phase boundaries | Keeps session coherent, predictable token cost | — Pending |
| YAML-first workflow definitions with code escape hatch | Simple cases config-driven; complex cases avoid boilerplate | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

## Current Milestone: v1.0 Client Harness

**Goal:** Build the Cyberdeck client harness end-to-end — TUI, probe, router, session manager, workflow queue, and relay client stub — capturing the full remote server vision for subsequent milestones.

**Target features:**
- Python chat-style TUI (Textual)
- Connectivity probe
- Model router (Ollama local + relay client)
- Session manager (persisted, resumable)
- Workflow queue (YAML + code-based workflows)
- All Local / Wait for Online modes
- Relay client (OpenAI-compatible stub)

---
*Last updated: 2026-07-07 after v1.0 milestone start*
