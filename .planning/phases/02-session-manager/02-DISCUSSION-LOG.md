# Phase 2: Session Manager - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-08
**Phase:** 2-session-manager
**Areas discussed:** Session identity & naming, Long conversation handling, Multiple sessions, Resume UX

---

## Session Identity & Naming

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-generated title from first message | Local Ollama generates 3-5 word title after first exchange | ✓ |
| User names it at start | Prompt for name, default to timestamp | |
| Timestamp + UUID only | No title, no summarisation cost | |

**User's choice:** Auto-generated title after first assistant response

| Option | Description | Selected |
|--------|-------------|----------|
| `<uuid>.json` | UUID is stable key, title is metadata inside | ✓ |
| `<timestamp>-<slug>.json` | Human-readable on disk | |
| Sequential: 001.json | Simple counter | |

**User's choice:** `<uuid>.json`

| Option | Description | Selected |
|--------|-------------|----------|
| After first assistant response | Async, non-blocking | ✓ |
| After 3 turns | More context, later | |
| Immediately from first user message | String truncation, instant | |

**User's choice:** After first assistant response (async, non-blocking)

---

## Long Conversation Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Single JSON always, warn at ~1MB | Simple, grep-friendly | ✓ |
| Split at threshold: metadata + messages.jsonl | No full rewrite on large sessions | |
| Always append-only from start | Consistent, never rewrite | |

**User's choice:** Single JSON always
**Notes:** User clarified that Phase 2 is local sessions only. Remote/cloud sessions are managed by the server-side agent (like Claude Code manages its own context). No cloud handoff logic in Phase 2.

| Option | Description | Selected |
|--------|-------------|----------|
| Archive complete/abandoned after 30 days | Background cleanup | |
| Never auto-archive | User manages | |
| Archive immediately on complete/abandon | Active dir only has live sessions | ✓ |

**User's choice:** Archive immediately on complete/abandon

---

## Multiple Sessions

| Option | Description | Selected |
|--------|-------------|----------|
| One active session per TUI instance | filelock prevents cross-instance corruption | ✓ |
| Multiple named sessions, switchable in TUI | Like browser tabs | |
| One global session always | Simplest | |

**User's choice:** One active session per TUI instance

| Option | Description | Selected |
|--------|-------------|----------|
| Workspace-scoped: sessions/<workspace_id>/ | Default "default" workspace in Phase 2 | ✓ |
| Global session pool | Simpler for Phase 2 | |
| Optional workspace tag | Not structurally isolated | |

**User's choice:** Workspace-scoped (workspace_id = "default" in Phase 2)

---

## Resume UX

| Option | Description | Selected |
|--------|-------------|----------|
| Title + turn count + time since last turn | "Resume: Refactor session module (12 turns, 2h ago)?" | ✓ |
| Title + first message excerpt | Good memory jog | |
| Full session list if multiple interrupted | Show numbered list | |

**User's choice:** Title + turn count + time since last turn

| Option | Description | Selected |
|--------|-------------|----------|
| Show all interrupted sessions, pick one or start fresh | Most-recent-first list | ✓ |
| Auto-resume most recent | No prompt if only one | |
| One at a time, most recent first | Prompt for each | |

**User's choice:** Show all, pick one or start fresh

| Option | Description | Selected |
|--------|-------------|----------|
| Textual ResumeScreen (ModalScreen) before MainScreen | Consistent with WizardScreen pattern | ✓ |
| Inline in chat pane as first message | | |
| CLI output before TUI launches | | |

**User's choice:** Textual ResumeScreen

---

## Claude's Discretion

- filelock library (filelock recommended from STACK.md)
- time_ago humanisation format ("2 hours ago" vs absolute timestamp)
- Whether to store first_message_excerpt for faster resume display
- aiofiles vs asyncio.to_thread for atomic write helper

## Deferred Ideas

- Summarisation before cloud handoff (v1.1)
- draining/queued session states (v1.1)
- Session search/filtering (future)
- Session export (future)
