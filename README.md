# cyberharness

Connectivity-aware AI harness designed for the [Jetson Cyberdeck](https://github.com/scottcowan/jetson-cyberdeck).

Routes GSD workflow phases to local inference (Ollama) when offline, queues cloud-required phases, and drains to Claude API on reconnect. Session state lives in the harness — not the model — so context survives model switches and reboots.

---

## Architecture

```
cyberharness
├── router/         # Model router — picks Ollama vs Claude API by phase + connectivity
├── session/        # Phase session manager — owns message history, serialises to disk
├── queue/          # Offline queue — JSON envelopes, drains on reconnect
├── probe/          # Connectivity probe — WiFi/network check on interval
├── phases/         # GSD phase hooks — discuss, spec, plan, execute, verify
└── cli/            # Terminal interface
```

## Phase Routing

| Phase | Model | Connectivity required |
|---|---|---|
| discuss | Local Ollama (Llama 3.2 3B) | No |
| spec | Local Ollama | No |
| explore / ideation | Local Ollama | No |
| plan | Claude API | Yes — queues if offline |
| execute | Claude API | Yes — queues if offline |
| verify | Claude API | Yes — queues if offline |

## Session Design

Sessions are owned by the harness, not the model. One session per phase.

- Message history accumulated locally across all turns
- Model switches mid-phase carry full history to the new endpoint
- On phase completion: history summarised into a context doc, written to `.planning/`
- Discuss turns summarised before cloud handoff to minimise token cost
- Sessions serialised to `~/.cyberharness/sessions/` — survive reboots

## Connectivity

- Primary: WiFi / Ethernet
- Secondary: Reticulum mesh (LoRa via RNode) — `rnsh` to home server
- Probe runs on interval, triggers queue drain on reconnect

---

## Status

- [ ] Connectivity probe
- [ ] Model router
- [ ] Session manager
- [ ] Offline queue
- [ ] GSD phase hooks (discuss, spec)
- [ ] GSD phase hooks (plan, execute, verify)
- [ ] CLI

---

## Related

- [jetson-cyberdeck](https://github.com/scottcowan/jetson-cyberdeck) — hardware repo
- [GSD](https://github.com/scottcowan/gsd) — workflow system this integrates with
