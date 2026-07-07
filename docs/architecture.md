# Architecture

## Overview

```
┌─────────────────────────────────────────────┐
│                cyberharness                  │
│                                              │
│  CLI                                         │
│   └── phase runner                           │
│        ├── session manager                   │
│        │    ├── messages[]  (full history)   │
│        │    └── context_doc (phase output)   │
│        ├── router                            │
│        │    ├── probe (connectivity)         │
│        │    ├── → Ollama  (offline/discuss)  │
│        │    └── → Claude API (online/cloud)  │
│        └── queue manager                     │
│             └── ~/.cyberharness/queue/*.json │
└─────────────────────────────────────────────┘
```

## Components

### Probe

Runs on a configurable interval (default 30s). Checks connectivity by attempting a DNS resolution or lightweight HTTP probe against a known endpoint. Emits `connected` / `disconnected` events that the router and queue manager subscribe to.

### Router

Single function: given a `(phase, message_history)` → returns a response stream.

```
route(phase, messages)
  if phase in LOCAL_PHASES or not connected:
    call Ollama API (base_url=localhost:11434, model=llama3.2:3b-instruct-q4_K_M)
  else if connected:
    call Claude API (base_url=api.anthropic.com, model=claude-sonnet-5)
  else:
    enqueue(phase, messages) → return queued acknowledgement
```

Both Ollama and Claude API are OpenAI messages-format compatible. The router swaps endpoint and model name; the messages array is unchanged.

### Session Manager

One session per phase. Owns the message history.

```
Session
  id:           uuid
  phase:        str
  started_at:   timestamp
  messages:     Message[]      # full back-and-forth, all models
  model_log:    ModelCall[]    # which model handled which turn
  context_doc:  str | null     # populated on phase completion
  state:        active | complete | queued
```

Persisted to `~/.cyberharness/sessions/<id>.json` after every turn. On reconnect or reboot, active sessions are resumable.

**Handoff summarisation:** before routing a completed discuss session to the cloud plan phase, the harness summarises the raw message history into a structured context doc. This avoids sending verbose back-and-forth to the cloud model and keeps token cost predictable.

### Queue Manager

Watches `~/.cyberharness/queue/`. Each envelope is a JSON file:

```json
{
  "id": "uuid",
  "phase": "plan",
  "session_id": "uuid",
  "context_doc": "...",
  "enqueued_at": "2026-07-07T16:00:00Z",
  "attempts": 0
}
```

On `connected` event: drains queue in FIFO order, retries failed envelopes with exponential backoff, removes on success.

### GSD Phase Hooks

Thin wrappers that translate GSD phase invocations into harness `route()` calls. The goal is minimal coupling — GSD doesn't need to know about the harness internals, just that model calls go through this layer.

## Data Flow

### Offline (discuss phase)

```
user input
  → session.add_turn(user)
  → router.route(phase=discuss, messages=session.messages)
    → Ollama API (local)
  → session.add_turn(assistant, model=ollama/llama3.2)
  → stream to terminal
```

### Reconnect → cloud phase

```
probe: connected event
  → queue.drain()
    → for each envelope:
        router.route(phase=plan, messages=context_doc)
          → Claude API
        → stream results to terminal
        → session.complete()
        → write to .planning/
```

### Mid-phase model switch (offline → online during discuss)

```
turn N:   offline → Ollama
turn N+1: reconnect event fires
turn N+2: still discuss → Ollama (no switch yet, phase not complete)
phase completes → summarise → enqueue for plan → Claude API
```

The switch only happens at phase boundaries, not mid-phase. This keeps the session coherent.

## Configuration

`~/.cyberharness/config.toml`

```toml
[models]
local = "llama3.2:3b-instruct-q4_K_M"
cloud = "claude-sonnet-5"
ollama_base_url = "http://localhost:11434"

[routing]
local_phases = ["discuss", "spec", "explore"]
cloud_phases = ["plan", "execute", "verify"]

[probe]
interval_seconds = 30
probe_host = "1.1.1.1"

[paths]
sessions = "~/.cyberharness/sessions"
queue = "~/.cyberharness/queue"
```
