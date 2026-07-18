# Architecture

## The Zones of Thought Model

The cyberharness is built around a routing philosophy borrowed from Vernor Vinge's
*A Fire Upon the Deep* (1992). The galaxy is divided into zones where the laws of
physics — and therefore the limits of intelligence — differ:

| Zone | cyberharness equivalent |
|---|---|
| Slow Zone | Local Llama 3B — constrained, always present, sovereign |
| The Beyond | Cloud API (Claude/GPT) — more capable, requires connectivity |
| Cyberharness | The ship that navigates between zones |

**The Slow Zone is the primary operating mode, not the fallback.**
The Beyond is an on-demand resource — invoked when the query genuinely requires it,
when budget is healthy, and when connectivity is available. The local model handles
continuity, context, and everything it can handle reliably.

This framing matters for UX: when the local model operates, it is not apologising
for the absence of the cloud. It is operating as intended.

---

## Overview

```
┌─────────────────────────────────────────────────┐
│                  cyberharness                    │
│                                                  │
│  CLI                                             │
│   └── phase runner                               │
│        ├── session manager                       │
│        │    ├── messages[]  (full history)       │
│        │    └── context_doc (phase output)       │
│        ├── router  ← Zones of Thought model      │
│        │    ├── probe (connectivity)             │
│        │    ├── budget tracker (token spend)     │
│        │    ├── rate limit tracker               │
│        │    ├── → Slow Zone: Ollama (local 3B)   │
│        │    └── → Beyond: Claude/GPT API         │
│        └── queue manager                         │
│             └── ~/.cyberharness/queue/*.json     │
└─────────────────────────────────────────────────┘
```

---

## Components

### Probe

Runs on a configurable interval (default 30s). Checks connectivity and Beyond
availability. Emits zone-state events that the router subscribes to.

```
Zone states:
  SLOW_ZONE_ONLY    — offline, no connectivity
  BEYOND_AVAILABLE  — connected, budget healthy, not rate-limited
  BEYOND_THROTTLED  — connected but rate-limited or budget threshold hit
  BEYOND_DEGRADED   — connected but high latency / errors
```

### Router — Zones of Thought Decision Logic

Single function: `route(phase, messages, query)` → response stream.

```
route(phase, messages, query):

  # 1. Always route locally if the Slow Zone can handle it
  if zone_state == SLOW_ZONE_ONLY:
    → Slow Zone (Ollama)

  # 2. Proactive budget management — shift to Slow Zone before hard limits
  elif budget.remaining_tokens < BUDGET_THRESHOLD:
    → Slow Zone (preserve Beyond for must-have queries)
    log: "Shifting to Slow Zone — Beyond budget conserving"

  # 3. Rate limit recovery — local handles continuity during throttle
  elif zone_state == BEYOND_THROTTLED:
    if phase_can_run_locally(phase):
      → Slow Zone
    else:
      → enqueue(phase, messages)  # hold until Beyond recovers
      return: "Beyond is resting. Queued for when it returns."

  # 4. Phase-based routing — some phases always prefer one zone
  elif phase in LOCAL_PHASES:
    → Slow Zone

  elif phase in CLOUD_PHASES:
    → Beyond

  # 5. Default: Slow Zone first, escalate if needed
  else:
    → Slow Zone
    # (user can explicitly escalate with /cloud or --beyond flag)
```

**Zone routing is visible to the user.** The router emits a zone indicator on
each response — which model handled it, which zone it was in. No silent switching.

```
[Slow Zone] You asked: what's the best approach here?
[Beyond ↑]  Routing to Claude — this needs precise code generation
[Slow Zone ←] Beyond throttled, continuing locally
```

### Budget Tracker

Tracks token spend across the session and rolling window (configurable: hourly, daily).
Proactively shifts routing before hitting hard limits.

```
BudgetTracker
  session_tokens:   int   # tokens spent this session
  rolling_tokens:   int   # tokens in rolling window
  threshold_pct:    float # default 0.80 — shift at 80% of limit
  hard_limit:       int   # from config or API tier

  is_healthy() → bool
  remaining_tokens() → int
  record_usage(prompt_tokens, completion_tokens)
```

On threshold breach: router shifts new queries to Slow Zone. Already-running cloud
queries complete. Queue drains when budget resets (next hour/day window).

### Rate Limit Tracker

Tracks 429 / rate-limit responses from the cloud API. Exponential backoff with jitter.
During backoff: local model handles all queries that can run locally; cloud-required
queries enqueue.

```
RateLimitTracker
  backoff_until:    datetime | None
  consecutive_429s: int

  is_throttled() → bool
  record_429(retry_after_seconds)
  record_success()
```

### Session Manager

One session per phase. Owns the message history across model switches.

```
Session
  id:             uuid
  phase:          str
  started_at:     timestamp
  messages:       Message[]       # full back-and-forth, all models
  model_log:      ModelCall[]     # zone + model per turn
  context_doc:    str | null      # populated on phase completion
  state:          active | complete | queued
  zone_switches:  ZoneSwitch[]    # log of zone transitions this session
```

Persisted to `~/.cyberharness/sessions/<id>.json` after every turn.
Zone switches are logged so you can review which model handled which turns.

**Handoff summarisation:** Before routing a discuss session to the cloud plan phase,
the harness summarises raw message history into a structured context doc. This:
- Reduces token cost on the Beyond (send summary, not raw chat)
- Makes the handoff explicit — you can review the context doc before it goes cloud

### Queue Manager

Holds cloud-required queries during Slow Zone periods. Drains automatically when
Beyond becomes available again and budget is healthy.

```json
{
  "id": "uuid",
  "phase": "plan",
  "session_id": "uuid",
  "context_doc": "...",
  "enqueued_at": "2026-07-19T14:32:00Z",
  "reason": "rate_limited",   // or "offline" | "budget_threshold" | "user_deferred"
  "attempts": 0
}
```

Drain triggers: `connected` event, `rate_limit_cleared` event, `budget_reset` event.
Drain order: FIFO within priority (cloud-required before cloud-preferred).

---

## Local Model System Prompt — Slow Zone Behaviour

The local Llama 3B receives a system prompt that reflects its Zones role:

```
You are the cyberdeck's local intelligence — the Slow Zone mind.

You are fast, private, always present, and operate without network dependency.
You are not omniscient. Your value is sovereignty and continuity, not raw power.

Operating principles:
- Express calibrated uncertainty. "I think, but I'm not sure" is correct behaviour,
  not failure. A confident wrong answer is worse than an honest uncertain one.
- When a query exceeds your reliable knowledge or requires precise tool use,
  say so and offer to route to the Beyond: "This would benefit from a more capable
  system — want me to queue it for when the Beyond is available?"
- You know the current machine state (injected below). Use it.
- Maintain session continuity when the Beyond is unavailable. Keep the work moving.
- Never pretend to be the Beyond. You are the Slow Zone — that is your design,
  not your limitation.

{machine_context}
```

The machine context block is injected by `voice-query`'s context step:
time, power mode, system draw, Reticulum mesh status, loaded models, tmux sessions,
and current zone state.

---

## Data Flow

### Normal operation — Slow Zone primary

```
user input
  → session.add_turn(user)
  → router: phase=discuss, budget=healthy, zone=BEYOND_AVAILABLE
    → LOCAL_PHASES → Slow Zone (Ollama)
  → session.add_turn(assistant, model=ollama/llama3.2, zone=SLOW)
  → stream to terminal with [Slow Zone] indicator
```

### Beyond needed — plan phase, budget healthy

```
user triggers plan phase
  → router: phase=plan, budget=healthy, zone=BEYOND_AVAILABLE
    → CLOUD_PHASES → Beyond (Claude)
  → stream to terminal with [Beyond ↑] indicator
  → budget_tracker.record_usage(...)
```

### Beyond throttled — rate limit hit

```
429 received from Claude API
  → rate_limit_tracker.record_429(retry_after=60)
  → router: zone shifts to BEYOND_THROTTLED
  → current session: Slow Zone handles remaining discuss turns
  → cloud-required phases: enqueue with reason="rate_limited"
  → terminal: "[Slow Zone ←] Beyond throttled — continuing locally, cloud work queued"

60s later:
  → rate_limit_tracker.is_throttled() → False
  → queue.drain() → cloud phases resume
```

### Budget threshold reached

```
budget_tracker: session_tokens approaching threshold
  → router: shift new queries to Slow Zone
  → terminal: "[Slow Zone] Beyond budget conserving — local handling until reset"
  → cloud-required phases: enqueue with reason="budget_threshold"
  → at budget reset window: queue.drain()
```

### Offline — Slow Zone only

```
probe: SLOW_ZONE_ONLY
  → all queries → Slow Zone
  → cloud-required phases → enqueue with reason="offline"
  → terminal: "[Slow Zone] Operating offline — Beyond unavailable"
  → on reconnect: queue.drain() if budget healthy
```

---

## Configuration

`~/.cyberharness/config.toml`

```toml
[zones]
# Zones of Thought routing model
local_model = "llama3.2:3b-instruct-q4_K_M"
cloud_model = "claude-sonnet-5"
ollama_base_url = "http://localhost:11434"

# Phase routing defaults
local_phases = ["discuss", "spec", "explore", "ideate"]
cloud_phases = ["plan", "execute", "verify", "review"]

[beyond]
# Budget management — shift to Slow Zone at threshold to avoid hard limits
budget_threshold_pct = 0.80     # shift at 80% of token limit
daily_token_limit = 100000      # 0 = no limit
hourly_token_limit = 0          # 0 = no limit

# Rate limit recovery
min_backoff_seconds = 10
max_backoff_seconds = 300

[probe]
interval_seconds = 30
probe_host = "1.1.1.1"

[paths]
sessions = "~/.cyberharness/sessions"
queue = "~/.cyberharness/queue"
```
