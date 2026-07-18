# Phase 2: Session Manager - Research

**Researched:** 2026-07-08
**Domain:** Durable local session store (pydantic v2 models, atomic JSON writes, filelock, Textual ModalScreen)
**Confidence:** HIGH for pydantic/atomic write/filelock; MEDIUM for exact aiofiles fsync ergonomics and Textual v8 ModalScreen generic typing (verified via docs, not against installed package)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Session Identity & Naming**
- D-01: Session files are named `<uuid>.json` — UUID is the stable on-disk key. Human-readable title is metadata inside the file.
- D-02: Session title is auto-generated from the first exchange (after first assistant response). Local Ollama generates a 3–5 word title asynchronously — does not block the turn. Until the title is generated, the session shows as "Untitled session".
- D-03: File layout: `~/.cyberharness/sessions/<workspace_id>/active/<uuid>.json` for live sessions; `~/.cyberharness/sessions/<workspace_id>/archive/<uuid>.json` for completed/abandoned.

**Session Storage & File Format**
- D-04: Single `<uuid>.json` file always — rewrite full file atomically every turn (write-tmp → fsync → os.replace). At ~1MB, log a warning but keep working. No format split in Phase 2.
- D-05: Completed or abandoned sessions are moved to `archive/` immediately (on session.complete() / session.abandon()). Active dir only contains live sessions — keeps startup scan fast.
- D-06: Atomic write pattern: `path.with_suffix('.tmp')` → write → `os.fsync()` → `os.replace(tmp, path)`. The `.tmp` file is ignored on startup scan (pattern: skip `*.tmp` files).
- D-07: User turn is persisted to disk BEFORE the model call. If the process dies mid-stream, the user's message is never lost.

**Session Scope**
- D-08: Sessions are workspace-scoped: `sessions/<workspace_id>/active/<uuid>.json`. In Phase 2, use `"default"` as the workspace_id.
- D-09: One active session per TUI instance. Filelock (`<uuid>.lock` beside the JSON) prevents two instances from corrupting the same file.
- D-10: Session history accumulates across the full conversation (not per-phase).

**Session State Machine**
- D-11: States: `active` → `complete` | `abandoned`. (`draining` and `queued` states are v1.1 stubs only.)
- D-12: On startup: scan `sessions/<workspace_id>/active/` for `.json` files (exclude `.tmp`, `.lock`). Try `filelock.acquire(nonblocking=True)`. Acquired = this process can offer to resume. Locked-by-other = skip.

**Resume UX**
- D-13: Resume prompt as Textual `ResumeScreen` (ModalScreen) before MainScreen — consistent with WizardScreen from Phase 1.
- D-14: Each interrupted session shown as `"[N] <title> (<turn_count> turns, <time_ago>)"`.
- D-15: Multiple sessions listed most-recent-first; user picks by number or "Start fresh". "Start fresh" abandons all listed sessions.
- D-16: Zero interrupted sessions: skip ResumeScreen, go straight to MainScreen.
- D-17: Exactly one interrupted session: still show ResumeScreen — don't auto-resume without asking.

**Pydantic Models**
- D-18: Core models in `session/models.py`:
  - `Message`: role (Literal["user","assistant","system"]), content (str), timestamp, `_model` (str | None — harness metadata, stripped before any API call)
  - `ModelCall`: model_id, tokens_in, tokens_out, latency_ms, timestamp
  - `Session`: id (UUID), workspace_id (str), title (str | None), state (Literal["active","complete","abandoned"]), messages (list[Message]), model_log (list[ModelCall]), created_at, updated_at
- D-19: `Session.model_dump_json()` is the serialisation path — pydantic v2 handles UUID/datetime natively.

### Claude's Discretion
- filelock library choice (`filelock` from STACK.md is recommended)
- Whether `time_ago` uses "2 hours ago" humanisation or absolute timestamp
- Whether to store `first_message_excerpt` in session metadata for faster resume display
- aiofiles vs sync-write + asyncio.to_thread for the atomic write helper

### Deferred Ideas (OUT OF SCOPE)
- Summarisation before cloud handoff (v1.1)
- `draining` and `queued` state transitions (v1.1)
- Session search / filtering
- TODO-001 (Ollama tool use parser bugs — Phase 3)
- Session export
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SESS-01 | User can hold a continuous, prolonged conversation with the local leader model — history persists across the full session, not just per-phase | Pydantic `Session` model with `messages: list[Message]` accumulating across turns (D-18, D-10); `SessionStore.append_message()` + `save()` on every turn |
| SESS-02 | Session is written atomically to disk after every turn — crash or power loss does not corrupt or lose conversation history | Atomic write pattern: write `.tmp` → `os.fsync()` → `os.replace()` (D-06); `_model` metadata preserved via pydantic serialisation; user turn persisted BEFORE model call (D-07) |
| SESS-03 | On startup, user is prompted to resume any in-progress session or start fresh | `SessionStore.scan_active()` returns lockable sessions; Textual `ResumeScreen(ModalScreen)` with numbered choices (D-13/14/15); zero sessions skips screen (D-16); one session still asks (D-17) |
</phase_requirements>

## Summary

Phase 2 is a well-scoped local persistence layer built on three stable primitives: pydantic v2 for typed serialisation, `os.replace` for atomic swaps, and the `filelock` library for cross-process ownership. Async ergonomics are the only place with a real choice — `aiofiles` does **not** expose `fsync`, so the atomic write helper must either use `asyncio.to_thread(...)` around a synchronous write function, or do async write + `await asyncio.to_thread(os.fsync, fd)` + async `os.replace`. Recommendation: keep the atomic write **synchronous internally** and wrap the whole helper in `await asyncio.to_thread(...)` — simpler, one thread hop, semantically identical.

Textual's `ModalScreen[T]` generic works with `push_screen(screen, callback)` and `dismiss(result)` for typed data passthrough. Do not `await` `dismiss()` from within the screen's own message handler.

Auto-title generation is fire-and-forget: `asyncio.create_task(self._generate_title(session))` after the first assistant turn completes; the task calls Ollama with a short prompt, then re-persists the session via the store (which handles filelock + atomic write). The task must be tracked on the `SessionMgr` so shutdown can cancel it cleanly (avoids Pitfall 11: dangling tasks on quit).

**Primary recommendation:** Build a `SessionStore` service that owns the filelock lifecycle and the atomic-write helper; keep the `Session` pydantic model dumb (no I/O). Build `ResumeScreen(ModalScreen[dict | None])` returning `{"action": "resume", "session_id": uuid}` or `None` for "start fresh". Track title-generation task on the store, cancel on shutdown.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Session data model | Core (`session/models.py`) | — | Pure pydantic — no I/O, no framework coupling |
| Atomic disk write | Core (`session/store.py`) | Filesystem | I/O boundary; wraps sync stdlib in `asyncio.to_thread` |
| Cross-process lock | Core (`session/store.py`) | OS (fcntl via filelock) | OS-level; auto-released on process death |
| Startup active-session scan | Core (`session/store.py`) | Filesystem | Reads `active/` dir, tries filelock on each `.json` |
| Resume UX | TUI (`tui/screens/resume.py`) | Core (via SessionStore) | Presentation only; queries store for scan result |
| Boot sequencing | TUI (`tui/app.py`) | Core | Runs scan → ResumeScreen? → MainScreen |
| Auto-title generation | Core (`session/titler.py` or SessionMgr) | Router (Phase 3 dep) | Fire-and-forget asyncio task; touches Ollama client |
| Archive move | Core (`session/store.py`) | Filesystem | `os.replace` (same filesystem) — atomic rename between `active/` and `archive/` |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | ^2.13 [ASSUMED — from STACK.md, not re-verified this session] | Session/Message/ModelCall models + JSON serialisation | Native UUID/datetime handling; `model_dump_json()`/`model_validate_json()` are the canonical serialisation paths; Rust core is fast on ARM64 |
| filelock | ^3.16 [ASSUMED] | Cross-process file lock (`<uuid>.lock`) | Documented in STACK.md; portable (Unix `fcntl`, Windows `msvcrt`); auto-releases on process death; `AsyncFileLock` exists for native async but sync `FileLock` in `asyncio.to_thread` is equally correct |
| aiofiles | ^25.1 [ASSUMED — from STACK.md] | Async file I/O for the JSON write | Wraps stdlib file ops in `asyncio.to_thread` internally; does NOT expose `fsync` [CITED: github.com/Tinche/aiofiles README] |
| Textual | ^8.2 | `ModalScreen[T]` for ResumeScreen | Phase 1 baseline; screen dismiss/callback API is the sanctioned data-return pattern [CITED: textual.textualize.io/api/screen] |
| stdlib `os` | 3.11 | `os.replace`, `os.fsync`, `os.open` | `os.replace` is atomic on POSIX when src+dst on same filesystem; must be same directory as final path for `.tmp` |
| stdlib `uuid` | 3.11 | UUID4 for session IDs | pydantic v2 serialises UUID → str natively |
| stdlib `datetime` | 3.11 | Timestamps (UTC) | Pair with `datetime.now(timezone.utc)`; pydantic v2 serialises to ISO-8601 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `pathlib` | 3.11 | Path composition | Everywhere — no `os.path.join` string manipulation |
| stdlib `asyncio` | 3.11 | Task management for auto-title | `create_task` for fire-and-forget; store the Task on SessionMgr for shutdown cancel |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `filelock.FileLock` in `to_thread` | `filelock.AsyncFileLock` | Native async avoids thread hop, but sync FileLock is battle-tested; either is correct. **Recommend sync FileLock** — matches how atomic write is already wrapped in `to_thread`. |
| Full-file JSON rewrite each turn | JSONL append-only journal | Journal avoids O(N) writes but the design (D-04) explicitly picks single file until ~1MB warning. Journal is deferred. |
| aiofiles for write | Sync `path.write_bytes` in `asyncio.to_thread` | aiofiles adds a dep for what to_thread already gives us. **Recommend sync + to_thread** for the atomic write helper — one thread hop, no partial-write ambiguity. |

**Installation:** No new packages beyond Phase 1 baseline.

**Version verification:** All packages are inherited from Phase 1. `pip`/`uv` are not installed in the research environment, so registry versions could not be re-verified — versions above are marked `[ASSUMED]` and inherited from `.planning/research/STACK.md`. Planner should re-verify with `uv pip index versions <pkg>` before generating install tasks.

## Package Legitimacy Audit

> No new packages are installed in this phase — everything is inherited from Phase 1 (pydantic, filelock, aiofiles, Textual). See `.planning/phases/01-foundation-scaffold/01-RESEARCH.md` Package Legitimacy Audit for baseline verification.

**slopcheck could not be run in this environment (pip unavailable). All Phase 1 packages should be verified in that phase's audit — this phase adds none.**

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────┐
                    │            App.on_mount()            │
                    │  boot sequence in tui/app.py         │
                    └────────────────┬─────────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     │  SessionStore.scan_active()   │
                     │  - list active/*.json         │
                     │  - try filelock nonblocking   │
                     │  - return list[LockedSession] │
                     └───────────────┬───────────────┘
                                     │
                    ┌────────────────┴─────────────────┐
                    │   found > 0 lockable sessions?   │
                    └───┬─────────────────────────┬────┘
                        │ yes                     │ no
                        ▼                         ▼
        ┌──────────────────────────┐    ┌────────────────────────┐
        │ push ResumeScreen        │    │ SessionStore.create()  │
        │ ModalScreen[dict|None]   │    │ - new UUID             │
        │ callback → dispatch      │    │ - filelock.acquire()   │
        └───┬──────────────────────┘    │ - persist active       │
            │                           └──────────┬─────────────┘
            │ dismiss(result)                      │
            ▼                                      ▼
   ┌─────────────────────┐              ┌──────────────────────┐
   │ result.action:      │              │      MainScreen      │
   │  - "resume" → load  │              │  (Phase 5 attaches)  │
   │  - "fresh"  → abandon│              └──────────────────────┘
   │    all + create new │
   └─────────────────────┘

   Turn lifecycle (per-turn):
   user submits text
        │
        ▼
   session.messages.append(Message(role="user", ...))
   await store.save(session)      ← atomic write, BEFORE model call
        │
        ▼
   router.stream(...)             ← Phase 3 dep
        │
        ▼ (stream ends)
   session.messages.append(Message(role="assistant", _model=...))
   session.model_log.append(ModelCall(...))
   await store.save(session)      ← atomic write, AFTER

   Auto-title (first assistant message only):
        │
        ▼
   asyncio.create_task(titler.generate(session))   ← fire-and-forget
   task tracked on SessionMgr for shutdown cancel
        │
        ▼ (Ollama returns 3-5 word title)
   session.title = title
   await store.save(session)      ← re-persist under filelock
```

### Recommended Project Structure

```
packages/client/src/cyberharness/session/
├── __init__.py           # public exports: Session, Message, ModelCall, SessionStore, SessionMgr
├── models.py             # pydantic v2 models (D-18)
├── store.py              # SessionStore: scan/create/load/save/complete/abandon/archive + atomic write + filelock
├── manager.py            # SessionMgr: turn API (add_user_turn, add_assistant_turn), auto-title task tracker
└── titler.py             # generate_title(session) - stub-friendly for Phase 2 (real Ollama call wired in Phase 3)

packages/client/src/cyberharness/tui/screens/
└── resume.py             # ResumeScreen(ModalScreen[ResumeResult])
```

### Pattern 1: Atomic Write Helper

**What:** Sync helper wrapped in `asyncio.to_thread` — atomic replace with fsync.
**When to use:** All session and (later) config persistence.

```python
# session/store.py
import os
import asyncio
from pathlib import Path
from pydantic import BaseModel

def _atomic_write_sync(path: Path, data: str) -> None:
    """Sync atomic write. MUST be called via asyncio.to_thread from async code."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    # write + fsync file contents
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)  # atomic on POSIX when tmp and path share the directory

async def atomic_write_json(path: Path, model: BaseModel) -> None:
    data = model.model_dump_json(indent=2)
    await asyncio.to_thread(_atomic_write_sync, path, data)
```

Why sync-inside-to_thread instead of aiofiles: aiofiles does not expose `fsync` [CITED: github.com/Tinche/aiofiles README lists `stat, statvfs, sendfile, rename, renames, replace, remove, unlink, mkdir, ...` — no `fsync`]. Mixing async writes with `await asyncio.to_thread(os.fsync, fd)` requires holding the fd across two await points, which is awkward. Single sync helper is simpler.

### Pattern 2: Filelock Nonblocking Acquire on Startup Scan

```python
# session/store.py
from filelock import FileLock, Timeout
from pathlib import Path

def _scan_active_sync(active_dir: Path) -> list[tuple[Path, FileLock]]:
    """Returns (session_path, held_lock) for every session we successfully claimed."""
    claimed = []
    for session_path in active_dir.glob("*.json"):
        if session_path.name.endswith(".tmp"):
            continue  # skip transient partial writes
        lock_path = session_path.with_suffix(".lock")
        lock = FileLock(str(lock_path))
        try:
            lock.acquire(timeout=0)  # nonblocking; raises Timeout if held
            claimed.append((session_path, lock))
        except Timeout:
            continue  # another live instance owns this session
    return claimed

async def scan_active(self) -> list[LoadedSession]:
    claimed = await asyncio.to_thread(_scan_active_sync, self.active_dir)
    sessions = []
    for path, lock in claimed:
        try:
            raw = await asyncio.to_thread(path.read_text)
            session = Session.model_validate_json(raw)
            sessions.append(LoadedSession(session=session, lock=lock, path=path))
        except (ValidationError, JSONDecodeError):
            # corrupt session — release lock, move to corrupt/, continue
            lock.release()
            # ... quarantine logic
    # sort most-recent-first by updated_at (D-15)
    sessions.sort(key=lambda s: s.session.updated_at, reverse=True)
    return sessions
```

**Stale lock behaviour:** `filelock.FileLock` uses `fcntl.flock` on Unix. When the holding process dies, the kernel releases the flock automatically — the lock file may still exist on disk, but the next `acquire(timeout=0)` succeeds because the kernel-level lock is gone. **No manual staleness check needed on Unix.** [CITED: py-filelock.readthedocs.io — `AsyncUnixFileLock` uses `fcntl.flock()`, kernel-managed.] The `SoftFileLock` variant has explicit stale-PID detection, but the default `FileLock` does not need it. [VERIFIED via docs]

### Pattern 3: ModalScreen Return Value

```python
# tui/screens/resume.py
from typing import TypedDict, Literal
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.widgets import Button, Label, ListView, ListItem

class ResumeResult(TypedDict):
    action: Literal["resume", "fresh"]
    session_id: str | None  # UUID str when action=="resume", None when "fresh"

class ResumeScreen(ModalScreen[ResumeResult]):
    def __init__(self, sessions: list[LoadedSession]) -> None:
        super().__init__()
        self._sessions = sessions

    def compose(self) -> ComposeResult:
        yield Label(f"Resume an interrupted session? ({len(self._sessions)} found)")
        yield ListView(*[
            ListItem(Label(f"[{i+1}] {s.session.title or 'Untitled session'} "
                           f"({len(s.session.messages)} turns, {humanize_ago(s.session.updated_at)})"),
                     id=f"session-{i}")
            for i, s in enumerate(self._sessions)
        ])
        yield Button("Start fresh", id="fresh")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-")[1])
        self.dismiss({"action": "resume", "session_id": str(self._sessions[idx].session.id)})

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fresh":
            self.dismiss({"action": "fresh", "session_id": None})
```

Caller side in `tui/app.py`:

```python
async def on_mount(self) -> None:
    sessions = await self.session_store.scan_active()
    if not sessions:
        # D-16: zero interrupted → skip modal
        await self._start_new_session()
        return
    # D-17: even one → still prompt
    self.push_screen(ResumeScreen(sessions), self._handle_resume_choice)

async def _handle_resume_choice(self, result: ResumeResult | None) -> None:
    # `None` should not occur since dismiss is always called; defensive fallback
    if result is None or result["action"] == "fresh":
        # D-15: "start fresh" abandons ALL listed sessions
        await self.session_store.abandon_all(self._pending_sessions)
        await self._start_new_session()
    else:
        await self.session_store.resume(result["session_id"])
```

**Critical:** never `await self.dismiss(...)` inside a message handler on the modal being dismissed — Textual raises `ScreenError`. Just call `self.dismiss(result)` as a plain method call. [CITED: textual.textualize.io/api/screen]

### Pattern 4: Fire-and-Forget Auto-Title

```python
# session/manager.py
class SessionMgr:
    def __init__(self, store: SessionStore, titler: Titler):
        self._store = store
        self._titler = titler
        self._bg_tasks: set[asyncio.Task] = set()

    async def add_assistant_turn(self, session: Session, content: str, model_id: str) -> None:
        session.messages.append(Message(role="assistant", content=content, _model=model_id, timestamp=utcnow()))
        session.model_log.append(ModelCall(model_id=model_id, ...))
        session.updated_at = utcnow()
        await self._store.save(session)

        # trigger auto-title only after FIRST assistant message
        if session.title is None and self._first_assistant_response(session):
            task = asyncio.create_task(self._title_and_persist(session.id))
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    async def _title_and_persist(self, session_id: UUID) -> None:
        try:
            title = await self._titler.generate(session_id)   # calls Ollama
            session = await self._store.load(session_id)
            session.title = title
            await self._store.save(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Auto-title generation failed; session remains untitled")

    async def shutdown(self) -> None:
        for task in list(self._bg_tasks):
            task.cancel()
        # await cancellation cleanly
        await asyncio.gather(*self._bg_tasks, return_exceptions=True)
```

### Anti-Patterns to Avoid

- **`asyncio.Lock` instead of filelock for session ownership** — In-process only; two TUI instances both "own" the file. Use `filelock` (see PITFALLS.md Pitfall 6, ARCHITECTURE.md Anti-Pattern 6).
- **`path.write_text(json.dumps(...))` for session persistence** — Not atomic. Truncate-then-write. Corrupts on power loss. Use the atomic helper (PITFALLS.md Pitfall 3).
- **Persisting the assistant turn before the model call completes** — Wrong order. User turn first (D-07), then model call, then assistant turn.
- **`await self.dismiss(result)` inside modal message handler** — Textual raises `ScreenError`. Call `self.dismiss(result)` without `await` [CITED: textual docs].
- **`asyncio.create_task(titler.generate(...))` without storing the task** — Task gets garbage-collected mid-run; `Task was destroyed but it is pending` warning. Always keep a reference (see PITFALLS.md Pitfall 11).
- **Scanning `archive/` on startup** — Only scan `active/`. Archive can grow unbounded without affecting boot time (D-05).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process file lock | pidfile + mtime staleness check | `filelock.FileLock` | fcntl semantics are already portable and kernel-managed; DIY misses death-of-holder cases |
| Atomic JSON persistence | write + rename by hand | `os.replace` (stdlib) via the helper pattern | POSIX guarantees atomic rename on same filesystem; the recipe is standard |
| UUID/datetime JSON encoding | custom `default=` in `json.dumps` | `Session.model_dump_json()` (pydantic v2) | Native UUID (→ str) and datetime (→ ISO-8601) handling |
| Model validation on load | `try: json.loads; if 'messages' in data: ...` | `Session.model_validate_json()` | Raises `ValidationError` fast; catch it and quarantine the corrupt file |
| Modal return values | callback via `self.app.foo = ...` | `ModalScreen[T]` + `push_screen(screen, callback)` + `dismiss(result)` | Sanctioned Textual pattern; typed via generic |

**Key insight:** Session persistence is a small surface with well-known failure modes (crash mid-write, cross-process races, corrupt files on load). Every failure has a canonical library-provided fix. Do not reinvent.

## Runtime State Inventory

**Not applicable** — Phase 2 is greenfield (creates new session/ package; no rename or migration). No existing runtime state to migrate.

## Common Pitfalls

### Pitfall 1: `.tmp` file collision across concurrent turns

**What goes wrong:** If (hypothetically) two saves overlap on the same session, both write to `<uuid>.json.tmp` and `os.replace` races.
**Why it happens:** Phase 2's design says one turn at a time per session, but a background auto-title task can race with a user turn.
**How to avoid:** Serialise all saves for a given session through the SessionStore. Simplest: `asyncio.Lock` on the in-memory `LoadedSession` object (per-session, in-process — this is the correct use for asyncio.Lock, not for cross-process). The filelock still guards cross-process.
**Warning signs:** `FileNotFoundError` in `os.replace`; occasional stale sessions where auto-title overwrote a user turn.

### Pitfall 2: fsync omitted, silent corruption on power loss

**What goes wrong:** Without `os.fsync(fd)` before `os.replace`, the filesystem may reorder — `.tmp` appears renamed but its contents were never flushed to disk. Post-power-loss reads see a zero-length file.
**Why it happens:** Devs know `os.replace` is atomic and skip the fsync, thinking atomicity of rename implies durability of contents.
**How to avoid:** Always `os.fsync(fd)` on the tmp file BEFORE `os.replace`. Optionally `os.fsync(dir_fd)` on the parent directory for full metadata durability — worthwhile on Jetson SD cards where sudden power-off is realistic.
**Warning signs:** Zero-byte session files after unclean shutdown; `JSONDecodeError` on resume that clean shutdowns never produce.

### Pitfall 3: `updated_at` not sortable

**What goes wrong:** ResumeScreen shows sessions out of order because `updated_at` was serialised as local time on one turn and UTC on another.
**Why it happens:** `datetime.now()` returns naive local time.
**How to avoid:** Always `datetime.now(timezone.utc)`. Pydantic v2 serialises tz-aware datetimes to ISO-8601 with offset — sortable as strings AND as datetimes.
**Warning signs:** Sessions listed in wrong order in ResumeScreen.

### Pitfall 4: "Start fresh" abandons only the visible session, not all interrupted

**What goes wrong:** D-15 says "Start fresh" abandons ALL listed sessions. Naive implementation only abandons the highlighted one.
**Why it happens:** UX ambiguity — "start fresh" could mean either.
**How to avoid:** `abandon_all(sessions)` iterates over the full list; each session gets state=abandoned + move to archive/ + lock release.
**Warning signs:** Zombie sessions in `active/` after user picks "Start fresh".

### Pitfall 5: Filelock released before archive move

**What goes wrong:** Move sequence goes `save state=complete → release lock → os.replace(active/uuid.json, archive/uuid.json)`. Between the release and the move, another instance could scan the active dir and claim the (nearly-archived) file.
**Why it happens:** Locks feel like they should release "at the end."
**How to avoid:** Order: save with state=complete → move to archive/ → release lock last. `os.replace` between directories on the same filesystem is atomic; the moved file is no longer at the active path when the lock releases.
**Warning signs:** Duplicate resume prompts on rapid start/stop cycles; occasional `FileNotFoundError` during archive.

### Pitfall 6: Auto-title task cancelled before persist

**What goes wrong:** User quits the app while auto-title is generating; task is cancelled; the generated title is lost.
**Why it happens:** `CancelledError` interrupts between the Ollama response and the `store.save()` call.
**How to avoid:** Auto-title is best-effort. Accept that a cancelled title just re-fires next time the session is resumed (check `session.title is None` on resume and re-schedule). Do NOT try to make it durable.
**Warning signs:** Sessions permanently stuck as "Untitled" even after long conversations.

### Pitfall 7: pydantic v2 `Literal` narrowing on load

**What goes wrong:** A session file with `state: "draining"` (leftover from a future/experimental version) fails validation because `Literal["active","complete","abandoned"]` rejects it.
**Why it happens:** D-11 restricts states to 3 values, but the design also mentions `draining`/`queued` as "stubs."
**How to avoid:** Keep the Literal strict (D-11 is explicit). If a corrupt/foreign state is encountered, quarantine the file to `sessions/corrupt/` rather than crashing startup.
**Warning signs:** `ValidationError: state Input should be...` in logs.

## Code Examples

### Session Models (D-18, D-19)

```python
# session/models.py
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, ConfigDict

class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime
    # harness-internal, MUST be stripped before any wire call (PITFALLS Pitfall 2)
    model_id: str | None = Field(default=None, alias="_model")

class ModelCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    timestamp: datetime

class Session(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    workspace_id: str = "default"
    title: str | None = None
    state: Literal["active", "complete", "abandoned"] = "active"
    messages: list[Message] = Field(default_factory=list)
    model_log: list[ModelCall] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
```

Note on `_model` field: pydantic v2 rejects field names starting with `_` (treated as private attributes). Use `alias="_model"` on a normally-named field (`model_id`) + `populate_by_name=True` — the JSON key is `_model`, the Python attribute is `model_id`. Confirm serialisation with `Message(...).model_dump_json(by_alias=True)` to keep the on-disk `_model` key. [ASSUMED — pydantic v2 alias behaviour; planner should include a unit test asserting round-trip preserves `_model` key.]

### model_validate_json + extra="forbid"

`extra="forbid"` on the top-level Session and on nested Message/ModelCall rejects unknown keys. This surfaces schema drift immediately instead of silently dropping fields. Confirmed behaviour: nested models each need their own `model_config = ConfigDict(extra="forbid")` — it does not propagate. [CITED: pydantic v2 docs on ConfigDict]

### Filelock lifecycle across process death

```python
from filelock import FileLock, Timeout

lock = FileLock("/path/to/session.lock")
lock.acquire(timeout=0)      # raises Timeout if held
# ... work ...
lock.release()               # explicit release
# on process death without release: kernel releases fcntl.flock automatically;
# the .lock file may remain on disk but is empty and does not block acquire.
```

### `_model` stripping before wire (belongs in Phase 3 but decision belongs here)

```python
def to_wire(messages: list[Message]) -> list[dict]:
    """Strip harness-only fields before any HTTP send."""
    return [
        {"role": m.role, "content": m.content}
        for m in messages
    ]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pydantic v1 `.json()` | pydantic v2 `.model_dump_json()` | pydantic 2.0 (2023) | Faster, stricter validation; already the project baseline |
| Textual v0.x `Screen` return via app-level attribute | Textual v0.30+ `ModalScreen[T]` + `dismiss(result)` + `push_screen(callback)` | Textual generics landed 2023 | Type-safe screen returns; project already on Textual 8.x |
| Raw `open() + fsync` in async | `asyncio.to_thread(sync_helper)` | asyncio 3.9+ | Cleaner than manual executor management |

**Deprecated/outdated:**
- pydantic v1 `Config` inner class → pydantic v2 `ConfigDict`
- pydantic v1 `parse_raw_as` → `model_validate_json`
- Textual `App.push_screen` with untyped callbacks → `ModalScreen[T]` for type safety

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `filelock` version ^3.16 is current | Standard Stack | Low — planner will re-verify via `uv pip index versions filelock`; API is stable across recent versions |
| A2 | `aiofiles` version ^25.1 is current | Standard Stack | Low — we're not using aiofiles for fsync anyway; deferred to Phase 1 baseline |
| A3 | pydantic v2 alias `_model` + `populate_by_name=True` round-trips correctly to `{"_model": "..."}` on `model_dump_json(by_alias=True)` | Code Examples | Medium — planner must include a unit test; if wrong, either name the JSON key differently (e.g. `model`) or use a plain `str | None` field named `model` (drop the underscore) — DISCUSSION-LOG or CONTEXT.md would need updating |
| A4 | `filelock.FileLock` on Linux uses `fcntl.flock` and releases on process death without stale-lock cleanup | Pattern 2 | Low — docs confirm; verified pattern is portable |
| A5 | `os.replace` between `active/<uuid>.json` and `archive/<uuid>.json` (same filesystem within `~/.cyberharness/`) is atomic | Pitfall 5 | Low — POSIX guarantee. Only fails cross-filesystem (would need `shutil.move`) |

## Open Questions

1. **`_model` field name at rest — literal `_model` or `model`?**
   - What we know: D-18 says "`_model` (str | None — harness metadata, stripped before any API call)"; ARCHITECTURE.md Anti-Pattern in Pitfall 2 also uses `_model`.
   - What's unclear: pydantic v2 forbids field names starting with underscore. `alias="_model"` works but requires `populate_by_name=True` and `by_alias=True` on dump. Alternative: rename to `model` at rest (no leading underscore) and rely on `to_wire()` stripping.
   - Recommendation: Keep the on-disk key as `_model` for continuity with docs; use `alias`. Add a round-trip unit test. If the alias approach proves fragile, escalate to discuss-phase.

2. **`workspace_id` from what source?**
   - What we know: D-08 says workspace_id="default" in Phase 2.
   - What's unclear: Where does the string come from? Config? Env var? Hardcoded literal?
   - Recommendation: Phase 2 hardcodes `"default"` in `SessionStore.__init__`. Config-driven workspace comes in a later phase; documenting this as a TODO in the store is fine.

3. **Title-generation prompt (D-02)**
   - What we know: 3–5 word title, async, non-blocking.
   - What's unclear: Exact prompt; which Ollama model; error handling.
   - Recommendation: Titler is a thin interface in Phase 2 (`async def generate(session_id: UUID) -> str`) with a **stub implementation** that returns e.g. first 40 chars of the first user message. Real Ollama call wires up when Phase 3 lands its OllamaClient. This keeps Phase 2 shippable without a Phase 3 dependency.

4. **Concurrent writes within one session (in-process)**
   - What we know: Filelock guards cross-process; asyncio.Lock guards in-process.
   - What's unclear: Should SessionMgr use one `asyncio.Lock` per session id, or serialise via a single-writer coroutine?
   - Recommendation: `asyncio.Lock` per LoadedSession in the store; taken automatically inside `save()`. Simpler than a writer coroutine and handles the auto-title vs user-turn race cleanly.

## Environment Availability

Phase 2 has no external service dependencies — it's a local persistence layer. All dependencies are Python packages inherited from Phase 1.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | asyncio.TaskGroup, tomllib | (Phase 1 baseline) | — | — |
| pydantic v2 | models.py serialisation | (Phase 1) | ^2.13 | — |
| filelock | store.py cross-process lock | (Phase 1) | ^3.16 | — |
| Textual v8 | ResumeScreen ModalScreen | (Phase 1) | ^8.2 | — |
| Ollama | Auto-title generation (D-02) | Phase 3 dep | — | Stub titler that uses first-user-message excerpt until Phase 3 wires the real call |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** Ollama (Phase 3 dependency) — Phase 2 ships with a stub titler.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (Phase 1 baseline) |
| Config file | `packages/client/pyproject.toml` under `[tool.pytest.ini_options]` (verify in Phase 1) |
| Quick run command | `uv run pytest packages/client/tests/session/ -x` |
| Full suite command | `uv run pytest packages/client/tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SESS-01 | Session accumulates messages across turns; `updated_at` advances | unit | `pytest tests/session/test_manager.py::test_multi_turn_accumulates -x` | ❌ Wave 0 |
| SESS-01 | Session round-trips through `model_dump_json`/`model_validate_json` losslessly (including `_model` key) | unit | `pytest tests/session/test_models.py::test_roundtrip_preserves_model_alias -x` | ❌ Wave 0 |
| SESS-02 | Atomic write: SIGKILL between `.tmp` write and `os.replace` leaves the previous JSON intact and parseable | integration | `pytest tests/session/test_store.py::test_crash_mid_write_preserves_prior -x` | ❌ Wave 0 |
| SESS-02 | User turn is persisted before model call — order of `store.save` invocations in SessionMgr | unit | `pytest tests/session/test_manager.py::test_user_turn_persisted_before_router -x` | ❌ Wave 0 |
| SESS-02 | `.tmp` files in active/ are excluded from scan | unit | `pytest tests/session/test_store.py::test_scan_ignores_tmp_files -x` | ❌ Wave 0 |
| SESS-02 | Corrupt JSON in active/ is quarantined, not crash on startup | unit | `pytest tests/session/test_store.py::test_corrupt_session_quarantined -x` | ❌ Wave 0 |
| SESS-03 | Zero interrupted sessions → ResumeScreen NOT shown | integration | `pytest tests/tui/test_boot.py::test_no_sessions_skips_resume -x` | ❌ Wave 0 |
| SESS-03 | One interrupted session → ResumeScreen IS shown | integration | `pytest tests/tui/test_boot.py::test_one_session_still_prompts -x` | ❌ Wave 0 |
| SESS-03 | Multiple sessions sorted most-recent-first | unit | `pytest tests/session/test_store.py::test_scan_orders_recent_first -x` | ❌ Wave 0 |
| SESS-03 | "Start fresh" abandons ALL listed sessions | integration | `pytest tests/tui/test_boot.py::test_fresh_abandons_all -x` | ❌ Wave 0 |
| SESS-03 (filelock) | Second-instance startup skips sessions locked by first instance | integration | `pytest tests/session/test_store.py::test_locked_session_skipped_on_scan -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest packages/client/tests/session/ -x` (unit tests only, <5s)
- **Per wave merge:** `uv run pytest packages/client/tests/ -x` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `packages/client/tests/session/__init__.py`
- [ ] `packages/client/tests/session/test_models.py` — pydantic round-trip, `_model` alias, `extra="forbid"` behaviour
- [ ] `packages/client/tests/session/test_store.py` — atomic write, filelock scan, quarantine, ordering
- [ ] `packages/client/tests/session/test_manager.py` — turn API ordering, auto-title task tracking
- [ ] `packages/client/tests/tui/test_boot.py` — ResumeScreen boot sequence (using Textual `App.run_test` pilot API)
- [ ] `packages/client/tests/conftest.py` — shared fixture: `tmp_sessions_dir` factory + `session_factory` helper

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in Phase 2 — single-user local tool |
| V3 Session Management | partial | "Session" here is the conversation session, not an authn session; still ensure filelock prevents cross-process corruption |
| V4 Access Control | yes | File permissions 0o700 on `~/.cyberharness/sessions/`, 0o600 on session JSON — sessions may contain sensitive prompts (PITFALLS.md security row) |
| V5 Input Validation | yes | pydantic `extra="forbid"` on load; `model_validate_json` rejects malformed input |
| V6 Cryptography | no | No crypto in Phase 2 — no at-rest encryption yet (deferred, PITFALLS.md security notes) |

### Known Threat Patterns for local session store

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Torn/corrupt JSON on crash | Denial-of-service (data loss) | Atomic write pattern (D-06); quarantine corrupt files instead of crashing |
| World-readable session files leak user prompts | Information Disclosure | `os.umask(0o077)` at process startup; explicit `0o600` on session files via `os.open(..., mode=0o600)` in atomic helper |
| Cross-process race corrupts session | Tampering | filelock cross-process lock (D-09) |
| Malformed JSON in active/ crashes startup | Denial-of-service | try/except ValidationError + JSONDecodeError → quarantine to `sessions/corrupt/` |
| API keys pasted into a session leak on backup sync | Information Disclosure | Documented user guidance; redaction is a v1.1 concern (PITFALLS.md) — out of scope for Phase 2 |

## Project Constraints (from CLAUDE.md)

No `./CLAUDE.md` at repo root as of research time — no explicit project directives to enforce beyond CONTEXT.md decisions.

## Sources

### Primary (HIGH confidence)
- textual.textualize.io/api/screen — ModalScreen[T], push_screen(callback), dismiss(result), ScreenError warning against awaiting dismiss
- py-filelock.readthedocs.io/en/latest/api.html — FileLock/AsyncFileLock, nonblocking `timeout=0` raising Timeout, fcntl.flock semantics on Unix, stale lock behaviour
- github.com/Tinche/aiofiles README — aiofiles.os function list; `fsync` is NOT exposed
- Python stdlib docs — `os.replace` atomic on same filesystem; `asyncio.to_thread` (3.9+)
- `.planning/research/STACK.md` — package versions inherited from Phase 1 baseline
- `.planning/research/ARCHITECTURE.md` — session state machine, ordering invariants, anti-patterns
- `.planning/research/PITFALLS.md` — Pitfall 3 (torn JSON), Pitfall 6 (asyncio.Lock misuse), Pitfall 8 (unbounded dir), Pitfall 11 (dangling tasks)

### Secondary (MEDIUM confidence)
- pydantic v2 ConfigDict behaviour with `extra="forbid"` and alias fields (docs consulted; project-specific behaviour not re-verified this session)

### Tertiary (LOW confidence)
- None — all findings verified against at least one authoritative doc or existing project research.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — inherited from Phase 1 research; versions marked ASSUMED pending planner re-verification
- Architecture: HIGH — patterns are stdlib primitives + one well-known lib
- Pitfalls: HIGH — cross-referenced with PITFALLS.md and ARCHITECTURE.md anti-patterns
- Textual ModalScreen API: HIGH — verified against official docs
- pydantic `_model` alias behaviour: MEDIUM — documented alias mechanism, flagged as A3 assumption for planner to unit-test

**Research date:** 2026-07-08
**Valid until:** 2026-08-07 (30 days — stack is stable)
