# Session Design

## Principles

1. **The harness owns the session, not the model.** Context survives model switches, reboots, and connectivity changes.
2. **One session per phase.** Clean boundary, predictable token cost, maps to GSD's phase structure.
3. **Summarise before handoff.** Raw discuss turns are not sent to the cloud model. The session is summarised into a structured context doc first.
4. **Sessions are durable.** Written to disk after every turn. Resumable.

## Session Lifecycle

```
create(phase)
  │
  ├── [turns: local Ollama]
  │    add_turn(user) → route() → add_turn(assistant, model=ollama)
  │
  ├── [optional reconnect — model switches at next phase boundary]
  │
  ├── complete()
  │    └── summarise messages → context_doc
  │    └── write context_doc to .planning/<phase>/context.md
  │    └── if next phase is cloud: enqueue(context_doc)
  │
  └── [cloud phase session — new session, starts from context_doc]
       add_turn(system, content=context_doc)
       route() → Claude API
```

## Message Format

Standard OpenAI messages array. Both Ollama and Claude API accept this natively.

```json
[
  {"role": "system",    "content": "You are helping with a GSD discuss phase..."},
  {"role": "user",      "content": "I want to add auth to the API"},
  {"role": "assistant", "content": "...", "_model": "ollama/llama3.2:3b"},
  {"role": "user",      "content": "JWT or session tokens?"},
  {"role": "assistant", "content": "...", "_model": "ollama/llama3.2:3b"}
]
```

`_model` is a harness-only metadata field, stripped before sending to any API.

## Summarisation

Before a discuss session is handed to a cloud phase, the harness runs a summarisation pass:

```
summarise(session.messages) → context_doc

context_doc structure:
  ## Phase Goal
  ## Key Decisions
  ## Open Questions
  ## Constraints
  ## Relevant Context
```

This is itself a local Ollama call — cheap, no connectivity required, runs at phase completion. The context doc is what travels to the cloud, not the raw message history.

## Resumption

On startup, harness scans `~/.cyberharness/sessions/` for sessions in state `active`. If found:

- Presents to user: "Resume session <phase> started <time>? [y/n]"
- On yes: loads messages, continues from last turn
- On no: marks session `abandoned`, starts fresh

Queue items from prior sessions are drained automatically on reconnect without user prompt.
