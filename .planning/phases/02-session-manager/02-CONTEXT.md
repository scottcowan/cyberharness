# Phase 2: Session Manager - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 delivers a durable local session store for the cyberharness client: pydantic models for Message and Session, per-turn atomic JSON writes to `~/.cyberharness/sessions/<workspace_id>/<uuid>.json`, filelock for cross-process safety, automatic archiving of completed/abandoned sessions, and a Textual ResumeScreen on startup that lets the user pick from interrupted sessions or start fresh.

**Scope constraint:** This phase manages local Ollama/LM Studio conversation sessions ONLY. Remote/cloud sessions are managed server-side by the remote agent (like Claude Code manages its own context). The local session manager does not handle cloud handoff, summarisation for cloud, or relay envelopes — those are v1.1 concerns.

</domain>

<decisions>
## Implementation Decisions

### Session Identity & Naming
- **D-01:** Session files are named `<uuid>.json` — UUID is the stable on-disk key. Human-readable title is metadata inside the file.
- **D-02:** Session title is auto-generated from the first exchange (after first assistant response). Local Ollama generates a 3–5 word title asynchronously — does not block the turn. Until the title is generated, the session shows as "Untitled session".
- **D-03:** File layout: `~/.cyberharness/sessions/<workspace_id>/active/<uuid>.json` for live sessions; `~/.cyberharness/sessions/<workspace_id>/archive/<uuid>.json` for completed/abandoned.

### Session Storage & File Format
- **D-04:** Single `<uuid>.json` file always — rewrite full file atomically every turn (write-tmp → fsync → os.replace). At ~1MB, log a warning but keep working. No format split in Phase 2.
- **D-05:** Completed or abandoned sessions are moved to `archive/` immediately (on session.complete() / session.abandon()). Active dir only contains live sessions — keeps startup scan fast.
- **D-06:** Atomic write pattern: `path.with_suffix('.tmp')` → write → `os.fsync()` → `os.replace(tmp, path)`. The `.tmp` file is ignored on startup scan (pattern: skip `*.tmp` files).
- **D-07:** User turn is persisted to disk BEFORE the model call. If the process dies mid-stream, the user's message is never lost.

### Session Scope
- **D-08:** Sessions are workspace-scoped: `sessions/<workspace_id>/active/<uuid>.json`. In Phase 2 (no real workspaces yet), use `"default"` as the workspace_id.
- **D-09:** One active session per TUI instance. A second `cyberharness` instance gets its own session — filelock (`<uuid>.lock` beside the JSON) prevents two instances from corrupting the same file.
- **D-10:** Session history accumulates across the full conversation (not per-phase). This is a continuous chat, not a per-GSD-phase session.

### Session State Machine
- **D-11:** States: `active` → `complete` | `abandoned`. (`draining` and `queued` states exist in the design doc but are v1.1 — the relay path is a stub in Phase 2.)
- **D-12:** On startup: scan `sessions/<workspace_id>/active/` for all `.json` files (exclude `.tmp`, `.lock`). Try `filelock.acquire(nonblocking=True)` on each. Acquired = this process can offer to resume. Locked-by-other = another live instance owns it, skip.

### Resume UX
- **D-13:** Resume prompt appears as a Textual `ResumeScreen` (ModalScreen) before MainScreen launches — consistent with the WizardScreen pattern from Phase 1.
- **D-14:** Each interrupted session shown as: `"[N] <title> (<turn_count> turns, <time_ago>)"` e.g. `"[1] Refactor session module (12 turns, 2 hours ago)"`.
- **D-15:** If multiple interrupted sessions exist, list all ordered most-recent-first. User picks by number, or selects "Start fresh". "Start fresh" abandons all listed sessions (marks state=abandoned, moves to archive/).
- **D-16:** If zero interrupted sessions: skip ResumeScreen entirely, go straight to MainScreen with a new empty session.
- **D-17:** If exactly one interrupted session: still show ResumeScreen — don't auto-resume without asking.

### Session Pydantic Models
- **D-18:** Core models in `session/models.py`:
  - `Message`: role (Literal["user","assistant","system"]), content (str), timestamp, `_model` (str | None — harness metadata, stripped before any API call)
  - `ModelCall`: model_id, tokens_in, tokens_out, latency_ms, timestamp (audit log per turn)
  - `Session`: id (UUID), workspace_id (str), title (str | None), state (Literal["active","complete","abandoned"]), messages (list[Message]), model_log (list[ModelCall]), created_at, updated_at
- **D-19:** `Session.model_dump_json()` is the serialisation path — pydantic v2 handles UUID/datetime serialisation. No custom JSON encoder needed.

### Claude's Discretion
- filelock library choice (`filelock` from STACK.md is the recommendation)
- Whether `time_ago` in resume prompt uses a simple "2 hours ago" humanisation or absolute timestamp
- Whether to store `first_message_excerpt` in session metadata for faster resume display (avoids reading full message list)
- aiofiles vs synchronous write + asyncio.to_thread for the atomic write helper

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design Docs
- `docs/session-design.md` — canonical session lifecycle, state machine, file layout, summarisation design (note: summarisation is v1.1 scope, not Phase 2)
- `docs/architecture.md` — SessionStore, SessionMgr component responsibilities, ordering invariants

### Phase 1 Foundation (this phase builds on)
- `.planning/phases/01-foundation-scaffold/01-CONTEXT.md` — Paths layout (D-03 defines sessions/ dir), Config model, atomic write pattern
- `.planning/phases/01-foundation-scaffold/01-RESEARCH.md` — Stack versions, aiofiles pattern, filelock

### Project
- `.planning/REQUIREMENTS.md` — SESS-01, SESS-02, SESS-03 definitions
- `.planning/ROADMAP.md` — Phase 2 success criteria (4 criteria), depends on Phase 1
- `.planning/research/ARCHITECTURE.md` — Session state machine diagram, ordering invariants (persist user turn BEFORE model call, etc.)
- `.planning/research/PITFALLS.md` — Pitfall 3 (torn session JSON), Pitfall 8 (unbounded sessions dir)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1 — not yet built, but planned)
- `packages/client/src/cyberharness/config.py` — `Config` model; `Paths` gives the `sessions_dir` path
- `packages/client/src/cyberharness/paths.py` — `Paths.sessions_dir` → `~/.cyberharness/sessions/`; atomic write helper
- `packages/client/src/cyberharness/tui/screens/` — WizardScreen pattern to follow for ResumeScreen

### Established Patterns (from Phase 1 CONTEXT.md)
- Atomic write: write to `.tmp`, fsync, `os.replace` — same pattern used for config writes in Phase 1
- Textual ModalScreen pattern: `push_screen(screen, callback)` + `screen.dismiss(result)` — WizardScreen is the reference
- pydantic v2 `model_dump_json()` for serialisation

### Integration Points
- Phase 2 output (`session/models.py`, `session/store.py`) is consumed by Phase 3 (Router adds turns to the session) and Phase 5 (TUI renders session history)
- `Paths.sessions_dir` from Phase 1 is the root — Phase 2 adds `active/` and `archive/` subdirs under `sessions/<workspace_id>/`
- ResumeScreen hooks into the boot sequence in `tui/app.py` — Phase 1 built the WizardScreen boot hook; Phase 2 adds a second optional screen before MainScreen

</code_context>

<specifics>
## Specific Ideas

- Scope is explicitly LOCAL sessions only — the session-design.md doc describes summarisation and cloud handoff, but those are v1.1. Phase 2 only implements active/complete/abandoned states; draining/queued are stubs.
- `sessions/<workspace_id>/active/` subdir keeps startup scan fast even with many archived sessions — scan only `active/`, archive is never scanned at startup.
- The auto-title generation is async and non-blocking. A `title_pending: true` field in the session JSON signals the title hasn't been set yet. After first assistant response, spawn a background Ollama call with a short title-generation prompt; when it returns, update the session file.

</specifics>

<deferred>
## Deferred Ideas

- **Summarisation before cloud handoff** — session-design.md describes this but it's v1.1 (relay). Not in Phase 2 scope.
- **`draining` and `queued` session states** — only needed when the relay is connected. Phase 2 stubs these as valid state values but never transitions into them.
- **Session search / filtering** — future; sessions are small enough that scanning `active/` is fine for v1.0.
- **TODO-001 (Ollama tool use parser bugs)** — router/tools concern, belongs in Phase 3. Not in scope here.
- **Session export** — future; users may want to export conversation history as markdown.

</deferred>

---

*Phase: 2-session-manager*
*Context gathered: 2026-07-08*
