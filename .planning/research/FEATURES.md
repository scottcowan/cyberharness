# Feature Research

**Domain:** Connectivity-aware AI CLI harness (GSD-integrated, Jetson Cyberdeck client)
**Researched:** 2026-07-07
**Confidence:** MEDIUM — HIGH for common CLI patterns from opencode/gemini-cli/llm; MEDIUM for offline-specific UX (few prior art examples for "queue + drain" model in this class of tool)

## Domain Framing

The class of tool is a **local-first, terminal-based AI workflow harness** — the intersection of:
- Coding-agent CLIs (opencode, gemini-cli, Claude Code, aider) — chat TUI, slash commands, session logs
- Multi-provider AI CLIs (Simon Willison's `llm`, LiteLLM) — provider abstraction, aliases, SQLite logs
- Offline-first mobile/mesh apps (Signal offline queue, git offline commits, Syncthing) — enqueue-on-write, drain-on-connect
- Print queue / job spooler UX (CUPS, ffmpeg batch, GNU parallel) — visible queue, retry, status per item

The Cyberdeck context (portable, intermittent WiFi, LoRa fallback) makes "drain UX" load-bearing in a way most AI CLIs never confront — reference projects like opencode assume connectivity.

## Feature Landscape

### Table Stakes (Users Expect These)

Missing any of these makes the tool feel broken or unfinished versus opencode / gemini-cli / Claude Code.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Chat-style TUI with streaming output | Every modern AI CLI (opencode, gemini-cli, aider, Claude Code) streams tokens; batch responses feel dead | MEDIUM | Textual `RichLog` + async streaming worker; requires cooperative cancel on Ctrl-C |
| Slash commands (`/help`, `/quit`, `/clear`, `/model`, `/session`) | Universal CLI convention; opencode, gemini-cli, Claude Code all use it | LOW | Simple prefix parser; keep the list short (≤10) — discoverability via `/help` |
| Session persistence to disk | opencode auto-saves, gemini-cli has "conversation checkpointing", `llm` uses SQLite. Users assume nothing is lost on crash | MEDIUM | Already designed in `docs/session-design.md` (per-turn write, JSON files) |
| Session resume on startup | If a session exists in `active` state, prompt "resume?" — matches gemini-cli checkpointing | LOW | Design already covers this — scan `~/.cyberharness/sessions/` on boot |
| Visible current model in status bar | Users need to know "am I on Ollama or Claude right now" — especially critical here because it changes with connectivity | LOW | Status bar footer widget; updates on router event |
| Connectivity indicator | Non-negotiable when connectivity is a first-class concept — needs to be always visible, not buried in a menu | LOW | Small colored dot in footer (green/yellow/red); reflect probe state |
| Ctrl-C interrupt for in-flight generation | Universal expectation; users assume they can cancel a runaway response | MEDIUM | Requires cooperative cancellation through the streaming reader |
| Message history scrollback | Any chat UI without scroll feels broken | LOW | Textual `RichLog` gives this for free |
| Config file (TOML) for keys, endpoints, models | `~/.cyberharness/config.toml` already in design; standard pattern | LOW | Already scoped |
| Copy-to-clipboard for assistant output | Users constantly copy code from chat responses; opencode and Claude Code both support it | LOW | Textual has clipboard bindings; keybind (e.g. `y` in normal mode, or right-click) |
| Error messages that name the failing subsystem | "Ollama unreachable at localhost:11434" not "Request failed" — critical when there are 3 possible endpoints (Ollama, relay, probe target) | LOW | Structured error types per subsystem |

### Differentiators (Competitive Advantage)

These are where cyberharness competes with opencode/gemini-cli. They align with the **Core Value**: "Context and work survive any connectivity transition."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Visible queue with per-item status** | The single most differentiating feature. Users see `plan-abc123 [queued, waiting for online]` and know their work is safe. No other AI CLI in this class does this | MEDIUM | Textual `DataTable` or list widget; reads `~/.cyberharness/queue/*.json`; reactive to file changes. Show: id, phase, enqueued time, attempts, status |
| **"Wait for Online" mode with explicit UX** | User opts in to "I want cloud output; queue and notify me on reconnect." Different from "All Local" mode which never queues. Removes surprise | MEDIUM | Mode toggle in status bar; when enqueuing, TUI shows toast: `Queued for online — 2 items pending drain` |
| **Automatic drain with progress feedback** | On reconnect: `Draining queue (2/5): plan-abc123 → Claude API...` with per-item outcome. Not silent | MEDIUM | Progress bar or scrolling status line; queue manager emits drain events the TUI subscribes to |
| **Phase-boundary model switch (not mid-turn)** | Predictable behavior — the model doesn't swap under you mid-conversation. Documented in `docs/architecture.md` as a design principle | LOW | Already in router design; surface it in `/model` output |
| **All Local mode** | Guaranteed offline operation — never attempt cloud, never queue. Useful for airgapped or LoRa-only sessions | LOW | Config flag + mode indicator; router short-circuits to Ollama |
| **Handoff summarisation before cloud** | Cheap local Ollama summary before sending to Claude — cuts cloud token cost meaningfully. Design already covers this | MEDIUM | Design in `docs/session-design.md`; UX: show user the summary before it's queued, allow edit |
| **YAML workflow definitions + code escape hatch** | Simple workflows in YAML (declarative), complex ones in Python. Matches `Constraints` in PROJECT.md. Rare in this space — `llm` has templates but not full workflows | HIGH | Workflow schema: `model_class` (local/cloud), `work_type`, `phase`, `prompts`. Escape hatch: `type: python` pointing at a callable |
| **Model call log per turn** (`_model` metadata) | Users can look back and see "this turn was Ollama, that turn was Claude" — trust and auditability. Already in `docs/session-design.md` | LOW | Already designed; surface in TUI as a subtle badge next to each assistant message |
| **Relay client with OpenAI-compatible protocol** | Because Ollama and Claude both speak OpenAI messages format, the relay only needs endpoint + auth swap. Enables future meta-harness aggregation | MEDIUM | HTTP client with pluggable auth; stub in v1.0 |
| **Reticulum/mesh fallback awareness** | Cyberdeck has LoRa via RNode. Probe should recognize `rnsh` reachability, not just WiFi. Almost no other tool considers this | HIGH | Multi-tier probe: WiFi first, then mesh; distinguish "cloud-reachable" from "mesh-reachable" |

### Anti-Features (Commonly Requested, Often Problematic)

Explicitly out — document to prevent scope creep.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Auto model-switching mid-turn on reconnect | "Wouldn't it be smart to upgrade to Claude the moment we get signal?" | Breaks session coherence — half a response in Llama voice, half in Claude voice. Confuses the model, confuses the user. Design already forbids this | Switch only at phase boundaries (already the design) |
| Real-time streaming to multiple simultaneous clients | Feels modern, "collab" | Single-user tool per PROJECT.md scope. Adds sync/CRDT complexity for zero core-value gain | Already in Out of Scope in PROJECT.md |
| Rich in-TUI markdown rendering with images/embeds | "It should look like ChatGPT" | Textual can do rich text, but images/tables in a Cyberdeck terminal are wasted pixels; adds rendering cost, hides raw output users want to copy | Plain markdown with syntax-highlighted code fences only |
| Inline code execution ("run this snippet") | Every AI coding tool does this now | Massively expands scope, sandbox concerns, orthogonal to "connectivity-aware routing" thesis. Cyberharness is a router+session tool, not an agent runner | Copy/paste output; user runs code in their own shell |
| Per-turn model override in the TUI (`/model claude` for one message) | Users want fine-grained control | Undermines the phase-based routing invariant — the whole premise is that phase determines model. Ad-hoc override defeats "predictable token cost" | Global mode toggle (All Local / Auto / Wait for Online); phase-config edits go through config file |
| Multi-tenant / OAuth / accounts | "What if two people share a Cyberdeck" | Explicitly out per PROJECT.md; single-user tool | Already in Out of Scope |
| Automatic retry with escalating prompts on model failure | "If Ollama gives a bad answer, ask Claude" | Doubles cost, opaque to user, undermines "phase = model" invariant. Failure should be visible | Show the failure, let user re-invoke |
| Web UI mirror | "So I can review sessions from my laptop" | Textual has web serve, but that's a second surface to maintain and secures the sessions dir over HTTP | Session JSON files are already inspectable — user can `cat`/`jq` them |
| Session merging or branching | "Fork this conversation at turn N" | Powerful but complicates the state model dramatically; premature. `llm` has branching and it's used by ~1% of users | Manually copy the session JSON; add branching only if a user asks twice |
| Auto-summarisation of long sessions to fit context window | Common in Claude Code / opencode for long contexts | Different problem — the harness's summarisation is at phase boundaries for cost, not for context window. Adding mid-session compaction couples session state to model context limits | If local models hit context limits, that's a workflow-design problem — split into smaller phases |
| GUI installer / auto-updater | "Easy setup" | Cyberdeck is a hacker device; users are comfortable with `pip install`. Auto-updates in a portable offline tool are actively harmful | `pip install cyberharness` + manual `pip install -U` |
| Cloud-side session storage / sync | "Access my sessions from another machine" | Contradicts core value (local-first). Sessions belong on the device that captured them | Sessions are files — users can `rsync` if they want |

## Feature Dependencies

```
Chat TUI (Textual)
    └── requires ─> Streaming client (Ollama / relay)
            └── requires ─> Router
                    └── requires ─> Session Manager
                            └── requires ─> Config

Router
    ├── requires ─> Probe (to know online/offline)
    └── requires ─> Queue Manager (to enqueue when offline+cloud-phase)

Queue Manager
    ├── requires ─> Probe (subscribes to connected event)
    ├── requires ─> Relay Client (to actually drain)
    └── enhances ─> Session Manager (marks queued sessions)

Wait for Online Mode ─── requires ─> Queue Manager + Probe
All Local Mode      ─── requires ─> Router (short-circuit branch)

Workflow Queue (YAML)
    ├── requires ─> Router (workflows call route())
    └── enhances ─> Session Manager (workflows produce sessions)

Handoff Summarisation ─── requires ─> Local Ollama endpoint + Session Manager

Relay Client
    ├── requires ─> Config (endpoint, auth)
    └── enhances ─> Router (adds cloud branch)

Reticulum/Mesh Probe ─── enhances ─> Probe (extends "connected" definition)
```

### Dependency Notes

- **TUI depends on almost everything working end-to-end**: without router+session+probe, the TUI has nothing to render. Build these in parallel but the TUI is the last integration surface — mock the router in early TUI iterations.
- **Queue Manager cross-cuts probe, router, session, relay**: it's the second-most integrative component after the TUI. Get its file format nailed down early so other components can write envelopes independently.
- **Probe is a leaf dependency**: nothing depends on it except router+queue. Build it first — it unblocks everything else.
- **Workflow Queue and Relay Client are independent tracks**: could be built in parallel by different phases.
- **All Local mode should be the default during early development**: it eliminates the queue+relay dependency chain so router+session+TUI can be validated end-to-end without cloud plumbing.

## MVP Definition

### Launch With (v1.0)

Per PROJECT.md's "Current Milestone: v1.0 Client Harness" — the target features. This MVP is deliberately client-only; the relay client is a stub.

- [ ] **Python chat TUI (Textual)** — chat log, input field, status bar with connectivity + model indicator. Essential; nothing works without a surface.
- [ ] **Connectivity probe** — interval check, `connected`/`disconnected` events. Enables offline detection.
- [ ] **Model router** — phase + connectivity → Ollama or relay. The core primitive; everything routes through it.
- [ ] **Session manager** — per-phase, persisted per turn, resumable on startup. Enables the "context survives" core value.
- [ ] **Queue manager** — JSON envelopes on disk, FIFO drain on reconnect. The differentiator; without it "Wait for Online" is impossible.
- [ ] **All Local mode + Wait for Online mode** — explicit modes visible in the TUI. Sets user expectations.
- [ ] **Relay client stub (OpenAI-compatible HTTP)** — just enough to make the cloud path exercisable; the real relay ships in a later milestone.
- [ ] **Slash commands: `/help`, `/quit`, `/clear`, `/session`, `/model`, `/queue`** — bare minimum for a usable TUI.
- [ ] **Config file** (`~/.cyberharness/config.toml`) — endpoints, models, probe interval, mode default.
- [ ] **Streaming output with Ctrl-C cancel** — universal expectation.

### Add After Validation (v1.x)

- [ ] **Workflow queue (YAML + code)** — add once users have real workflows they want to codify. Depends on the router being stable.
- [ ] **Handoff summarisation** — add when cloud token costs become a real complaint or when discuss sessions grow long.
- [ ] **Reticulum / mesh probe tier** — add when LoRa hardware is regularly in use and WiFi-only probe misses reachability.
- [ ] **Copy-to-clipboard keybind** — quality-of-life; ship when a user asks.
- [ ] **Session search / filter** — once >20 sessions exist and finding one is painful.
- [ ] **Queue item retry with backoff visible in TUI** — currently drain is FIFO with implicit retry; expose the retry count when it matters.

### Future Consideration (v2+)

- [ ] **Remote Server (workspace provisioning, sandboxed workspace, file browser, aggregated relay endpoint)** — the entire remote side of PROJECT.md; deliberately deferred to a subsequent milestone.
- [ ] **Meta-harness aggregation** (Cursor, Claude Code as relay backends) — explicitly out of v1.0 scope per PROJECT.md.
- [ ] **Multi-Cyberdeck sync** — if the tool spreads to multiple devices per user, some session sync story may be needed. Not now.
- [ ] **Voice input / TTS output** — Cyberdeck has hardware for it; interesting but orthogonal.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Chat TUI (Textual) | HIGH | MEDIUM | P1 |
| Connectivity probe | HIGH | LOW | P1 |
| Model router | HIGH | LOW | P1 |
| Session manager (persist + resume) | HIGH | MEDIUM | P1 |
| Queue manager + visible queue | HIGH | MEDIUM | P1 |
| All Local / Wait for Online modes | HIGH | LOW | P1 |
| Relay client stub | MEDIUM | LOW | P1 |
| Slash commands (core set) | HIGH | LOW | P1 |
| Streaming with Ctrl-C | HIGH | MEDIUM | P1 |
| Config file | HIGH | LOW | P1 |
| Status bar (connectivity + model) | HIGH | LOW | P1 |
| Model call log per turn | MEDIUM | LOW | P1 |
| Workflow queue (YAML + code) | MEDIUM | HIGH | P2 |
| Handoff summarisation | MEDIUM | MEDIUM | P2 |
| Copy-to-clipboard | MEDIUM | LOW | P2 |
| Session search | MEDIUM | MEDIUM | P3 |
| Reticulum mesh probe tier | MEDIUM | HIGH | P3 |
| Remote server | HIGH | HIGH | v2+ (next milestone) |

**Priority key:** P1 = must have for v1.0 launch • P2 = should have during v1.x • P3 = defer until validated need

## Competitor Feature Analysis

| Feature | opencode | gemini-cli | `llm` (Simon Willison) | Cyberharness Approach |
|---------|----------|------------|------------------------|----------------------|
| Session persistence | Auto-saved per session dir | Conversation checkpointing (`/chat`) | SQLite log, browsable via `llm logs` | JSON file per session, per-turn write, resumable on startup — matches gemini-cli semantics with a simpler storage model |
| Model switching | Provider config via Zen/config; agent switching via Tab (build/plan) | `-m` flag; auto Flash vs Pro by tier | `-m <alias>`; per-invocation | **Phase determines model, not user command.** Removes decision fatigue; makes routing predictable |
| TUI style | Chat + agent tab, plan mode, `/undo`, `/redo`, `@` file fuzzy find | Interactive terminal, streamed responses, slash commands | Non-interactive by default; chat mode via `llm chat` | Textual chat TUI with status bar (connectivity + model); slash commands for control; no agent-tab metaphor (phases are the abstraction) |
| Offline behavior | Not designed for offline | Not designed for offline | Works offline via `llm-ollama` plugin, no queueing | **First-class**: probe + queue + drain + modes. This is the entire differentiator |
| Multi-provider | OpenCode Zen curated selection + custom providers | Google-only | Plugin per provider, unified interface | Two-endpoint model (Ollama local, relay cloud) — deliberately narrow. Relay is the aggregation point (future) |
| Workflow definition | Custom commands via config | Custom reusable slash commands; GEMINI.md for project context | Templates + fragments | YAML workflows with code escape hatch — more structured than slash commands, less code than Python-native |
| Cost/token awareness | Not prominent | Tier-based routing (Flash cheaper) | Log inspection | **Handoff summarisation** to cut cloud tokens; model-call log per turn for post-hoc auditing |
| Session sharing | `/share` uploads to opencode.ai | Not native | Manual export | Not planned — sessions are local files (anti-feature: cloud-side session storage) |

## Complexity Assessment for v1.0

**Well-understood (low risk):**
- Textual chat TUI — mature framework, many examples (Toad is directly relevant prior art)
- Ollama client — OpenAI-compatible, well-documented
- JSON file session persistence — trivial
- Config TOML parsing — trivial
- Slash command parser — trivial

**Medium risk:**
- Probe subsystem — has to be reliable and cheap; needs careful event debouncing (network flaps shouldn't spam events)
- Streaming + Ctrl-C interrupt — requires cooperative cancellation through async worker; Textual worker patterns help
- Queue drain UX — showing progress across N items while streaming the current one, without confusing the user
- Session resume prompt — edge cases around partial writes, corrupted JSON, multiple active sessions

**Higher risk / warrants deeper research in later phases:**
- Workflow YAML schema — needs to be expressive enough for real workflows but not turn into a DSL. Recommend deferring to v1.1 and shipping v1.0 with hardcoded phase behavior only.
- Relay client protocol details — auth handshake, error semantics, streaming over HTTP. Stub for v1.0; real design in the Remote Server milestone.
- Reticulum mesh probe integration — depends on `rnsh` behavior when the mesh is partitioned; deferred.

## Sources

- opencode: https://github.com/sst/opencode and https://opencode.ai/docs (confirmed features: agent tab, plan mode, `/undo`/`/redo`, `@` fuzzy find, `/share`, `/init`) — MEDIUM confidence, limited detail from summary
- gemini-cli: https://github.com/google-gemini/gemini-cli (confirmed: conversation checkpointing, `-m` flag, streamed responses, custom slash commands, GEMINI.md context) — MEDIUM confidence
- Simon Willison's `llm`: https://github.com/simonw/llm (confirmed: SQLite logs, plugin architecture, model aliases, `llm-ollama` for offline) — HIGH confidence, well-documented tool
- Textual framework: https://textual.textualize.io — HIGH confidence (mature, widely-used); Toad (AI coding TUI on Textual) confirms this class of tool is viable in the framework
- Cyberharness design docs: `docs/architecture.md`, `docs/session-design.md`, `.planning/PROJECT.md` — HIGH confidence (project's own source of truth)
- Domain analogues (not directly researched here, drawn from general knowledge): CUPS print queue, Signal offline queue, git offline commit model — inform the "visible queue with drain" pattern

**Verification note:** No prior art was found for a coding-agent CLI that treats "queue + drain + explicit online-wait mode" as first-class. This is genuinely differentiating for cyberharness, but also means the UX must be designed rather than copied. Flagging for phase-level UX research when the queue TUI is being implemented.

---
*Feature research for: connectivity-aware AI CLI harness (Jetson Cyberdeck client, v1.0)*
*Researched: 2026-07-07*
