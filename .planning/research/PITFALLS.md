# Pitfalls Research

**Domain:** Connectivity-aware Python async TUI + local/cloud model routing on Jetson ARM64
**Researched:** 2026-07-07
**Confidence:** HIGH (Textual, asyncio, httpx streaming, Ollama, Jetson) / MEDIUM (Reticulum/rnsh integration specifics)

## Critical Pitfalls

### Pitfall 1: Blocking the Textual event loop with sync HTTP / file I/O

**What goes wrong:**
The TUI freezes — spinner stops, keys are ignored, screen doesn't repaint — whenever a model call, disk write, or subprocess runs. `requests`, `ollama-python`'s sync client, or `json.dump` on a large session file inside an event handler will stall the whole app.

**Why it happens:**
Textual runs on a single asyncio loop. Any blocking call in a handler or reactive watcher stalls compositor + input. Devs reach for the familiar `requests` / `openai` sync client, or write session state with plain `open().write()` inside an async handler assuming disk I/O is "fast enough."

**How to avoid:**
- Use `httpx.AsyncClient` (streaming) for both Ollama and Claude — never `requests`, never the sync `openai` client. If you want the `openai` SDK, use `AsyncOpenAI`.
- Wrap unavoidable blocking work with `asyncio.to_thread(...)` or `loop.run_in_executor`.
- Persist sessions via `await asyncio.to_thread(path.write_text, json.dumps(...))` or use `aiofiles`.
- Long-running tasks belong in `App.run_worker(..., thread=False)` (async worker) — Textual's Worker API is the sanctioned pattern.
- Never call `time.sleep` — use `await asyncio.sleep`.

**Warning signs:**
- Cursor freezes for >100ms while streaming a token.
- Ctrl+C doesn't respond during model calls.
- `textual console` shows long gaps between log messages.
- Async task warnings: `coroutine was never awaited` or `Task was destroyed but it is pending`.

**Phase to address:**
Phase 1 (TUI + probe scaffold) — establish async-only I/O convention before any model integration.

---

### Pitfall 2: Not stripping `_model` and other harness-internal fields before HTTP send

**What goes wrong:**
Ollama accepts unknown message keys silently; Claude / OpenAI-compatible endpoints reject with 400 `Unexpected keyword` or, worse, some proxies pass them through and they end up billed as tokens. Also breaks when re-serialising a session that has been round-tripped through the API.

**Why it happens:**
The session design explicitly stores `_model` on each assistant message (docs/session-design.md:38). Devs forget the sanitisation step because Ollama tolerates it during local dev, then it blows up the first time a cloud drain runs.

**How to avoid:**
- Single choke-point: `to_wire(messages)` function that returns a deep-copied list with only `{role, content, name?, tool_calls?}` keys. Every outbound HTTP call goes through it.
- Unit test that asserts no `_`-prefixed keys and no unknown keys survive `to_wire`.
- Consider a `Message` dataclass with an explicit `.to_wire()` method rather than raw dicts.

**Warning signs:**
- Claude API returns `invalid_request_error` on the first queue drain.
- Token counts higher than expected on cloud calls.

**Phase to address:**
Phase 2 (Router + Ollama client) — bake the sanitiser in from turn one.

---

### Pitfall 3: Torn/corrupt session JSON on crash mid-write

**What goes wrong:**
Power loss, SIGKILL, or a crash mid-`write()` leaves `~/.cyberharness/sessions/<id>.json` truncated or half-written. On next startup the resumption code hits `json.JSONDecodeError` and either crashes or (worse) silently drops the session.

**Why it happens:**
Session is persisted after every turn (docs/session-design.md:9). Devs use `path.write_text(json.dumps(...))` — which under the hood is truncate-then-write, not atomic. On Jetson especially, sudden power loss during battery swap / hard reset is a realistic failure mode.

**How to avoid:**
- Atomic write pattern: write to `<id>.json.tmp` in the same directory, `fsync`, then `os.replace(tmp, final)`. `os.replace` is atomic on POSIX.
- Optionally keep a `<id>.json.bak` rotated on each successful write; recovery falls back to it on parse failure.
- Consider append-only journal (JSON Lines) of turns as the source of truth, with the aggregated JSON as a derived snapshot. Rebuild snapshot from journal on corruption.
- Wrap load in `try/except JSONDecodeError` — never let a bad session brick startup. Move corrupt files to `sessions/corrupt/` and log.

**Warning signs:**
- Any user report of "lost my session after a reboot."
- `JSONDecodeError` in logs.
- Session files with size 0 or ending mid-token.

**Phase to address:**
Phase 3 (Session manager) — atomic writes are non-negotiable from v1.

---

### Pitfall 4: Connectivity flapping causes queue drain thrash

**What goes wrong:**
On marginal WiFi / mobile hotspot / LoRa, the probe rapidly toggles `connected`/`disconnected`. Every rising edge kicks off `queue.drain()`, which starts a Claude request, which fails mid-stream when connectivity drops, which increments `attempts`, which retries immediately on the next rising edge. Queue attempts explode; Claude bills for aborted streams; user sees "burst of half-answers."

**Why it happens:**
The probe is a boolean edge trigger (docs/architecture.md:27). Real-world connectivity is a distribution, not a boolean. Naive edge triggering is the classic mistake.

**How to avoid:**
- Debounce: require N consecutive successful probes before declaring `connected` (e.g., 2 out of 2, or an EWMA over 3 samples). Same for `disconnected`.
- Single-flight drain: an `asyncio.Lock` around `queue.drain()` so at most one drainer runs. New `connected` events while draining are ignored (or queued as a single re-check flag).
- Exponential backoff on the *envelope*, not just the connection. If envelope attempts >= 3, don't retry until probe has been stably connected for M minutes.
- Idempotency: the router must be able to detect "this envelope was partially processed" — persist request ID before sending, check server for completion on retry (Anthropic supports `Idempotency-Key`).
- Probe target should be robust: don't probe `1.1.1.1` only via ICMP (blocked on many networks) — do a TCP connect to `1.1.1.1:443` or an HTTPS HEAD to a small endpoint. Better still: probe the *actual* endpoint you'll call (`api.anthropic.com`) — you can be "online" and still have Anthropic unreachable.

**Warning signs:**
- `attempts` field in queue envelopes climbing rapidly.
- Duplicate assistant responses appearing in session history.
- Anthropic billing shows many short streams.

**Phase to address:**
Phase 4 (Queue + probe integration) — debounce + single-flight are day-one features, not polish.

---

### Pitfall 5: Streaming response parsing that assumes complete SSE frames

**What goes wrong:**
The router reads `async for chunk in response.aiter_bytes()` and tries to parse each chunk as a JSON delta. On real networks, a single SSE `data: {...}\n\n` frame arrives split across two chunks, or two frames arrive concatenated in one chunk. Parser raises `JSONDecodeError`, stream is aborted, user sees a truncated response, envelope retries.

**Why it happens:**
Both Ollama's `/api/chat` (NDJSON) and Anthropic's messages API (SSE `event:`/`data:` pairs) stream frame-by-frame, but TCP does not preserve frame boundaries. Devs test on localhost where a chunk == a frame and ship.

**How to avoid:**
- Use `response.aiter_lines()` for Ollama NDJSON — httpx handles the line buffering.
- For Anthropic SSE, use `httpx-sse` or the official `anthropic` Python SDK's `client.messages.stream()` which handles reassembly.
- If rolling your own SSE: buffer bytes, split on `\n\n`, keep the tail for the next iteration.
- Always handle `[DONE]` sentinel (OpenAI-compat) or `message_stop` event (Anthropic) explicitly — don't rely on stream close.
- Test with `httpx-mock` injecting fragmented chunks; test with `tc qdisc` adding latency/loss.

**Warning signs:**
- Truncated responses on cellular/LoRa but fine on WiFi.
- Intermittent `JSONDecodeError` in stream handler.
- Last few tokens missing from persisted messages.

**Phase to address:**
Phase 2 (Router / Ollama client) for local streaming; Phase 5 (Claude integration) for SSE.

---

### Pitfall 6: Handoff summarisation loses critical context silently

**What goes wrong:**
Local Llama 3.2 3B is asked to summarise a 30-turn discuss session into a context doc. It hallucinates decisions, drops constraints, or paraphrases user requirements into something subtly wrong. The plan phase runs on Claude using this doc, produces a great plan for the wrong problem, and the user only notices at execute or verify time.

**Why it happens:**
A 3B quantised model summarising freeform discussion is genuinely unreliable at edge cases. Users assume "summarisation is easy" because it looks fluent. There's no diff/review step — the doc goes straight to the queue.

**How to avoid:**
- Structured summarisation prompt with strict schema (Phase Goal / Decisions / Open Questions / Constraints) — reject and retry if output doesn't parse.
- Include raw user turns *verbatim* in the "Requirements" section — don't paraphrase user statements, only the assistant's clarifications.
- **User confirms the context doc before enqueue.** Show the doc in the TUI with an [approve / edit / regenerate] prompt. This is the single most important safeguard.
- Log both raw messages and generated doc — recovery = re-summarise or hand-edit.
- Consider a larger local model for summarisation specifically (e.g., a 7-8B if the Jetson has headroom) even if 3B handles the chat.

**Warning signs:**
- Plan phase output references things user never said.
- User reports "that's not what we discussed."
- Context docs shorter than ~200 words on 20+ turn sessions.

**Phase to address:**
Phase 3 (Session manager summarisation) — confirmation UX must be in v1.

---

### Pitfall 7: Ollama model not loaded / cold start blocking first turn

**What goes wrong:**
User types first message → 15-45s of silence while Ollama loads `llama3.2:3b-instruct-q4_K_M` into VRAM. UI appears frozen (see also Pitfall 1). On Jetson Orin Nano with limited VRAM, model may be evicted between sessions and reload every time. Worse: if VRAM is exhausted, Ollama silently falls back to CPU and inference goes from 40 tok/s to 3 tok/s.

**Why it happens:**
Ollama unloads models after `keep_alive` (default 5min). Jetson memory pressure from other processes can force eviction sooner. Devs test in a hot loop where the model stays loaded, then real users hit cold starts.

**How to avoid:**
- Warm on startup: fire an empty completion or `POST /api/generate` with `keep_alive: -1` at harness launch (in background, non-blocking).
- Show explicit "loading model..." state in TUI with elapsed timer — silence is worse than a slow spinner.
- Set `OLLAMA_KEEP_ALIVE=24h` or `-1` in the systemd unit for the local phases model.
- Check `/api/ps` (Ollama endpoint listing loaded models) on startup, warn if using CPU instead of GPU.
- Pre-pull models in Phase 0 install script — never fetch multi-GB models on first run over cellular.
- Jetson-specific: pin Ollama to GPU (`CUDA_VISIBLE_DEVICES=0`), verify `nvidia-smi` shows the process.

**Warning signs:**
- First turn of a session much slower than subsequent turns.
- `ollama ps` shows model not resident.
- Inference speed < 10 tok/s on Jetson Orin.

**Phase to address:**
Phase 2 (Ollama integration) + Phase 0 (install script).

---

### Pitfall 8: Sessions directory grows unbounded

**What goes wrong:**
Every phase creates a session file that's never cleaned up. After 6 months of use `~/.cyberharness/sessions/` has 10k JSON files. Startup scan (docs/session-design.md:65) walks all of them looking for `state: active`, taking 30s and burning battery. On Jetson's SD card this also risks wear-out.

**Why it happens:**
"Resumable sessions" implies retention. No archive/rotation policy is specified in the design.

**How to avoid:**
- Explicit archive step on `complete()`: move to `sessions/archive/YYYY-MM/` — startup only scans the root dir.
- Or maintain `~/.cyberharness/sessions/index.json` with `{id, state, phase, mtime}` — scan the index, not the filesystem. Rebuild index on corruption.
- Retention policy: archived sessions gzip'd after 30 days, deleted after 180 (configurable).
- Track directory size in probe/health check; warn on TUI when > threshold.

**Warning signs:**
- Startup time creeping up over weeks.
- `ls ~/.cyberharness/sessions | wc -l` in the thousands.

**Phase to address:**
Phase 3 (Session manager) — index or archive from v1, or you'll eat this later.

---

### Pitfall 9: API keys leaked into session files / logs / queue envelopes

**What goes wrong:**
Full request payload including `Authorization: Bearer sk-ant-...` gets logged in debug mode, or the router serialises the whole `httpx.Request` object into the session's `model_log`. Session files are then synced to a repo, pasted into a bug report, or committed as a fixture.

**Why it happens:**
Devs log request objects for debugging. Session `model_log` is under-specified in the design (docs/architecture.md:53). Anthropic keys are long-lived and high-privilege.

**How to avoid:**
- Never log request headers. `httpx` event hooks: strip `Authorization` before logging.
- Config file `~/.cyberharness/config.toml` should never contain the key — read from env var (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) or system keyring (`python-keyring`).
- `model_log` schema is explicit: `{model, tokens_in, tokens_out, latency_ms, timestamp}` — no raw request/response objects.
- Add a pre-commit hook and CI check scanning `~/.cyberharness/**/*.json` (in fixtures / test data) for `sk-` prefixes.
- Rotate keys on any suspicion.

**Warning signs:**
- Any `sk-` string appearing in `grep -r ~/.cyberharness`.
- Debug logs containing headers.

**Phase to address:**
Phase 5 (Claude integration) — but the pattern (keyring + env) should be set in Phase 0.

---

### Pitfall 10: ARM64 wheel gaps break `pip install` on Jetson

**What goes wrong:**
`pip install cyberharness` on Jetson (aarch64) tries to install a dependency (common offenders: `pydantic-core`, `tiktoken`, `orjson`, `cryptography`, `numpy`, older `httptools`) that has no aarch64 wheel on PyPI. Pip falls back to source build, which needs Rust / C compilers, may take 20+ minutes, and often fails on Jetson's default JetPack Python.

**Why it happens:**
Jetson runs Ubuntu-on-aarch64 with a system Python that's usually behind PyPI's supported versions. Some maintainers ship x86_64 + arm64 macOS wheels but skip Linux/aarch64.

**How to avoid:**
- Pin to Python versions with best aarch64 wheel coverage — currently 3.11 or 3.12 (3.13 aarch64 wheel coverage is still catching up as of mid-2026; verify per-dep). Use `pyenv` or `uv` rather than JetPack's system Python.
- Prefer `uv` for install — faster resolution + clearer errors on missing wheels.
- Test dependency install on a Jetson (or `docker run --platform linux/arm64`) in CI before every release.
- Vendor a `requirements-jetson.txt` with known-good pinned versions.
- Avoid heavy deps entirely where possible: `httpx` over `aiohttp` (both fine on aarch64 but httpx has fewer C deps); `msgspec` or stdlib `json` over `orjson` if orjson wheel is missing for your Python version.
- NVIDIA's own `jetson-containers` project publishes prebuilt images with common ML deps — piggyback.

**Warning signs:**
- `pip install` output shows `Building wheel for X (pyproject.toml)` for anything non-trivial.
- Install takes > 2 minutes.
- CI passes on Linux x86_64 but user reports failure on hardware.

**Phase to address:**
Phase 0 (project scaffolding) — dependency choices are hard to reverse.

---

### Pitfall 11: Textual `App.exit()` leaving background workers running

**What goes wrong:**
User hits `q` to quit. The TUI closes but the queue drain worker is mid-stream to Claude. The Python process hangs (asyncio tasks pending), or worse, Ctrl+C corrupts the session mid-write (see Pitfall 3). On next launch the "active" session is stale.

**Why it happens:**
Textual's `App.exit()` cancels the app but doesn't automatically await background tasks the app has spawned outside its Worker API. Devs spawn `asyncio.create_task()` directly and forget the cancellation path.

**How to avoid:**
- All background work via `App.run_worker()` — Textual will cancel workers on exit.
- Register an `on_unmount` / shutdown hook that: sets a shutdown event, awaits in-flight streams to reach a safe cancel point, flushes session snapshot, then exits.
- In-flight streams should periodically check `asyncio.current_task().cancelled()` and persist a partial-response marker so replay knows to re-request.
- Handle SIGTERM (systemd stop) the same as `q` — don't rely on Textual's key binding alone.

**Warning signs:**
- `q` doesn't return to shell for several seconds.
- Sessions occasionally stuck in `state: active` with no matching process.
- Pending task warnings on shutdown.

**Phase to address:**
Phase 1 (TUI scaffold) — set the pattern before workers proliferate.

---

### Pitfall 12: Retry storm on 429 / 529 from Anthropic

**What goes wrong:**
Anthropic returns 429 (rate limit) or 529 (overloaded). Naive retry-immediately or fixed-backoff hammers the API, gets the account rate-limited harder, and cascades: every queue envelope now blocked, user's session drain stalls entirely.

**Why it happens:**
Exponential backoff sounds simple until it isn't. Devs implement `sleep(2**attempt)` but skip jitter, skip Retry-After header, and share no state across envelopes.

**How to avoid:**
- Respect `retry-after` header verbatim (both `429` and `529` may include it).
- Exponential backoff **with full jitter**: `sleep(random.uniform(0, min(cap, base * 2**attempt)))`.
- Circuit breaker at the router level: after N consecutive 429/529s, freeze all cloud calls for a cooldown window (e.g., 5 min) and surface the state to the TUI.
- Distinguish retryable (429, 5xx, network) from non-retryable (400, 401, 403). Non-retryable → dead-letter, not retry loop.
- Use the official `anthropic` SDK if possible — it has correct retry semantics baked in. If rolling your own, mirror its behaviour.

**Warning signs:**
- Multiple envelopes in `attempts >= 5` state.
- Anthropic dashboard shows spikes of failed requests.
- TUI shows "queued" for extended periods with no progress.

**Phase to address:**
Phase 4 (Queue + retry policy) — do this before Phase 5 goes to real API.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Sync `requests` for the probe "because it's just a health check" | 3 lines of code | Freezes TUI when probe target is slow; async pattern gets muddled | Never — use `httpx.AsyncClient` from day one |
| Non-atomic `write_text` for session persistence | Simpler write path | Data loss on any unclean shutdown (frequent on battery-powered Jetson) | Never in production; ok in throwaway prototypes |
| Store API key in `config.toml` | One less env var to set | Key leaks via git commit, screen share, bug report | Only in local-dev with a scoped/limited key |
| Skip the human-confirms-context-doc step | Faster phase transitions | Silent summarisation drift; wrong plans; hard to detect | For non-plan cloud phases (execute/verify) with warning banner; never for plan |
| No debounce on connectivity probe | Fewer moving parts | Queue thrash on marginal networks (very common on LoRa/hotspot) | Never — even a 2-sample debounce is cheap |
| Log full `httpx.Request` for debugging | Fast diagnosis | Key leakage | Only behind an off-by-default `--debug-unsafe` flag |
| Use JetPack's system Python | No extra install step | ARM64 wheel gaps, no upgrade path | Never — always pyenv/uv |
| Global `ollama-python` sync client | Familiar API | Blocks event loop | Never in the TUI process |
| No index/archive on sessions dir | No cleanup code | Startup slows to seconds over months | For prototypes with <100 sessions expected |
| One giant `App` class in Textual | Faster start | Untestable; state bleeds across screens | Weekend spike only |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| **Ollama** | Assuming `/v1/chat/completions` OpenAI-compat endpoint is identical | It's close but not 100% — `logprobs`, some `response_format` variants, and function-calling semantics differ. Test the specific fields you use against Ollama, not against OpenAI docs. |
| **Ollama** | Not setting `keep_alive` per-request | Ollama unloads models after ~5min idle. Pass `"keep_alive": "24h"` (or `-1`) in local phases to keep VRAM warm. |
| **Ollama** | Not handling `model not found` on first run | Detect 404 with "model not found" message → prompt user or auto-`ollama pull`; don't crash. |
| **Anthropic** | Using `max_tokens` too low and truncating mid-stream | Anthropic requires `max_tokens`; setting it low silently truncates. Use `stop_reason` to detect and continue. |
| **Anthropic** | Ignoring the `input_tokens` cache-control fields | Structured system prompts benefit hugely from prompt caching — set `cache_control` on the context doc block. |
| **Anthropic SSE** | Treating each SSE `event` as a full message | Anthropic sends `content_block_start`/`_delta`/`_stop`/`message_stop` — you must reassemble deltas. |
| **httpx** | Creating a new `AsyncClient` per request | Blows connection pooling; TLS handshake per call. Keep a module-level or app-scoped client, close in `on_unmount`. |
| **Reticulum / rnsh** | Assuming it behaves like TCP | LoRa is high-latency (seconds), low-bandwidth (kbps), lossy. Streaming responses over LoRa is often impractical — prefer non-streaming, small-payload paths, and accept queued (not real-time) delivery. |
| **Reticulum** | Not budgeting for airtime / duty cycle regulations | Depending on region (EU 868MHz has 1% duty cycle limits) you cannot send large payloads continuously. Design around bounded message size. |
| **Systemd on Jetson** | Running the harness as root | Sessions end up in `/root/.cyberharness/`, users can't inspect. Run as normal user with a `User=` in the unit. |
| **YAML workflow queue** | Using `yaml.load()` (unsafe) | Use `yaml.safe_load` — YAML files may be user-editable and arbitrary tag execution is a footgun. |
| **YAML** | Assuming stable ordering | Dumping to YAML then reading back can reorder keys. If ordering matters (e.g., queue FIFO), use JSON or an explicit `sequence` field. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Redrawing entire Textual RichLog on every token | UI stutters mid-stream, CPU spikes | Append via `RichLog.write(...)` (incremental) rather than reconstructing the widget's content | Immediately on Jetson (weaker CPU) for streams > 5 tok/s |
| Re-serialising full session on every turn | Disk writes grow linearly with session length; sudden pause at end of long chats | Append-only journal (JSONL) or write only the delta; snapshot every N turns | Sessions > ~50 turns on SD card |
| Polling probe with tight interval | Battery drain, radio wake-ups | 30s+ default (as designed), backoff further on stable-connected | Battery mode / mobile |
| Loading all session files on startup to find active ones | Slow launch after weeks of use | Maintain sessions index, or use dedicated `active/` subdir | ~1000 sessions |
| Sync `json.dumps` on 10k-message history | UI freeze at end of long chat | `asyncio.to_thread(json.dumps, ...)`; consider msgspec | Discuss sessions > ~1000 turns (rare but possible for long research sessions) |
| Ollama running on CPU when GPU available | Inference at 2-3 tok/s | Verify `nvidia-smi` shows ollama; set `CUDA_VISIBLE_DEVICES` | Immediately — 10x slowdown |
| Queue drained sequentially with no parallelism cap | First envelope takes 60s, blocks 20 more | Concurrent drain with semaphore (e.g., 2-3 in flight) | Queue depth > ~5 |
| Not compressing archived sessions | Disk fills over months | gzip on archive move | Months of use on 32GB SD card |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| API keys in config file / env in dotfiles committed to git | Key exfiltration | Use OS keyring (`python-keyring`) or env-only; add `.env` and `~/.cyberharness/config.toml` to shipped `.gitignore` guidance |
| World-readable session files (contain user prompts, possibly secrets pasted in) | Local privilege escalation reads sensitive prompts | `chmod 0700` on `~/.cyberharness/`, `0600` on files; enforce in code with `os.umask(0o077)` at startup |
| Session/context docs synced to cloud backup unencrypted | Leaks proprietary work | Document this behaviour clearly; recommend excluding `~/.cyberharness/` from iCloud/Dropbox/etc; optional at-rest encryption via age/fernet |
| Trusting response content into eval / shell / file paths | RCE if a model is prompt-injected | Never `eval` model output; sanitise paths; if executing suggested commands (GSD execute phase), require explicit user confirm per command |
| YAML workflow files with `!!python/object` tags | Arbitrary code execution | `yaml.safe_load` only, never `yaml.load` |
| Following redirects on the connectivity probe | Probe endpoint captured → leak of "I'm online" fingerprint or SSRF-adjacent behaviour | `follow_redirects=False`, probe a known IP, not a hostname owned by a third party |
| Prompt injection via included files / context doc | Model exfiltrates data or ignores instructions | Treat all non-user content as untrusted; use Anthropic's system prompt for hard instructions; consider a "guard" prompt structure |
| Cloud model sees the raw discuss history including keys pasted in | Key exposure | Summarisation step should redact patterns matching common key formats (`sk-`, `ghp_`, `AKIA`, JWTs) before doc is enqueued |
| Log files including full messages world-readable in `/tmp` | Sensitive prompts leaked | Log to `~/.cyberharness/logs/` with 0600; rotate |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No indication whether current response is from Ollama or Claude | User can't judge quality/latency | Persistent status bar showing `phase / model / connectivity`; per-message model tag inline |
| "Queued" state with no progress indicator | User doesn't know if the task will ever run | Show queue depth, position, last-attempt time, next-retry ETA |
| Silent connectivity switch mid-phase | User confusion about "why did this suddenly get slow/fast" | Explicit non-modal toast: "Reconnected — next phase will use Claude" |
| Streaming with no cancel key | User is stuck waiting for a bad response | Bind Esc / Ctrl-C to cancel current stream, mark turn `cancelled` in session |
| Resumption prompt with no preview | User can't remember which session was which | Show phase, started_at, first user message (truncated), turn count |
| Auto-summarisation with no visibility | User trusts a possibly-wrong doc | Confirmation UX (see Pitfall 6) |
| Errors surfaced as raw stack traces | User can't act | Human-readable error panel with next-step suggestion ("Ollama not running — start with `sudo systemctl start ollama`") |
| No copy path for context doc | User can't hand it to another tool | Bind key to copy context doc to clipboard / write to `-` stdout |
| First-run without visible model download progress | User thinks harness is broken | Explicit setup screen showing `ollama pull` progress |
| No offline indicator | User tries a cloud phase, waits, sees a queue message minutes later | Header shows connectivity state at all times; block cloud phase attempts with clear "queued for reconnect" confirm |

## "Looks Done But Isn't" Checklist

- [ ] **Session persistence:** Session survives `kill -9` mid-turn — verify by killing during a stream, restarting, checking `state: active` file is valid JSON and resumable.
- [ ] **Connectivity probe:** Handles captive portal WiFi (probe returns 200 from portal, not from real target) — verify by testing against a captive network or `probe_host` mismatch.
- [ ] **Queue drain:** Handles envelope for a session whose local file has been deleted — verify graceful skip + dead-letter.
- [ ] **Model router:** Handles Ollama returning 503 (loading) — verify retry-with-backoff, not crash.
- [ ] **Streaming:** Handles server closing connection mid-stream — verify last partial token is persisted and turn marked incomplete.
- [ ] **Summarisation:** Handles a discuss session with <2 turns — verify no crash, sensible short doc or skip.
- [ ] **TUI:** Handles terminal resize during streaming — Textual usually handles this, but custom widgets can misbehave.
- [ ] **TUI:** Handles very long single messages (multi-screen) — verify scrolling works, doesn't lock rendering.
- [ ] **Config:** Missing config file / missing keys → sensible defaults + clear error, not stack trace.
- [ ] **Config:** Config file present but Ollama host unreachable → probe reports it correctly, user gets actionable message.
- [ ] **Retry:** Envelope in `attempts=5` state still visible to user with option to give up / edit / retry manually.
- [ ] **Auth:** Missing `ANTHROPIC_API_KEY` → refuses cloud phase with clear message, doesn't leak "None" into headers.
- [ ] **Time:** All timestamps UTC ISO-8601 with `Z`, not local time (Jetson clocks drift when offline — pair with NTP-on-reconnect).
- [ ] **Concurrency:** Two harness processes started accidentally → detects via lockfile / socket, second refuses to start.
- [ ] **Uninstall:** Clear path to remove `~/.cyberharness/` — documented, and no orphan systemd services.
- [ ] **Jetson thermal:** Under sustained load, does the CLI degrade gracefully as Jetson throttles? — bench at `nvpmodel` low-power mode.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Corrupt session JSON | LOW | Restore from `.bak`, or rebuild from journal, or move to `corrupt/` and start fresh with a warning |
| Runaway queue retries | LOW | Stop harness, `jq` to bump `attempts` beyond cap or delete stuck envelopes, restart |
| API key leaked in a committed session | MEDIUM | Rotate key immediately in Anthropic console; git-filter-repo or BFG to purge; audit usage logs |
| Bad summary produced wrong plan | LOW–MEDIUM | Re-open discuss session, edit context doc manually, re-enqueue plan |
| Session dir grew huge and startup is slow | LOW | Archive script: move everything >30 days to `archive/`, rebuild index |
| Model eviction causing 30s stalls | LOW | Set `keep_alive=-1`, enable model preload on startup |
| Ollama on CPU not GPU | LOW | Restart Ollama with correct `CUDA_VISIBLE_DEVICES`; verify with `ollama ps` |
| ARM64 install failure at user site | MEDIUM | Pin to known-good `requirements-jetson.txt`; ship a `uv`-based install script; offer container fallback |
| Textual TUI hangs on quit | LOW | SIGKILL, add shutdown hook fix, ship patch — no persistent damage if atomic writes are in place |
| Retry storm hit Anthropic rate limit | MEDIUM | Circuit breaker kicks in; pause queue for cooldown window; user can manually retry after |
| Prompt injection in a discuss session | MEDIUM–HIGH | Isolate session, audit any tool/exec calls that ran, rotate any secrets that were in scope |
| SD card wear-out / corruption | HIGH | Sessions on SD is fine if archived/rotated; recommend external SSD for `~/.cyberharness/` on heavy users |

## Pitfall-to-Phase Mapping

Suggested phase structure (informs roadmap ordering):

- **Phase 0:** Project scaffolding — deps, install, keyring, permissions
- **Phase 1:** Textual TUI shell + async foundations + probe
- **Phase 2:** Router + Ollama integration
- **Phase 3:** Session manager (persistence + summarisation)
- **Phase 4:** Offline queue + retry policy + drain
- **Phase 5:** Claude API integration + streaming
- **Phase 6:** GSD phase hooks + polish

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Blocking event loop | Phase 1 | Textual `--dev` shows no blocked-loop warnings; latency test during streaming |
| 2. `_model` leaking to wire | Phase 2 | Unit test `to_wire()` strips all `_`-prefix keys; integration test against Anthropic 400s |
| 3. Torn session JSON | Phase 3 | Chaos test: `SIGKILL` mid-write in a loop, verify all files parse |
| 4. Connectivity flapping | Phase 4 | Simulated flapping test (probe stub toggling), assert single-flight drain |
| 5. Streaming frame parsing | Phase 2 (Ollama) & Phase 5 (Anthropic) | Fragmented-chunk mock test; last-token integrity assertion |
| 6. Summarisation drift | Phase 3 | Confirmation UX is present; test with known-bad summariser producing empty sections |
| 7. Ollama cold start / CPU fallback | Phase 2 + Phase 0 | Startup shows model warm; `ollama ps` check; benchmark ≥ 20 tok/s on Jetson Orin |
| 8. Unbounded sessions dir | Phase 3 | Index file exists; startup time benchmark with 1000 seeded sessions |
| 9. API key leakage | Phase 0 & Phase 5 | grep-scan CI on session/log fixtures; keyring integration test |
| 10. ARM64 wheel gaps | Phase 0 | CI runs `pip install` under `--platform linux/arm64` |
| 11. Shutdown leaves workers | Phase 1 | Test: `q` from any state returns to shell within 2s; no pending-task warnings |
| 12. Retry storm on 429/529 | Phase 4 | Fault-injection test with 429 responses; assert backoff obeys retry-after + jitter |

## Sources

- Textual documentation — Workers, async patterns, `run_worker` API (textualize.io/docs). HIGH confidence — official.
- httpx documentation — `AsyncClient`, streaming with `aiter_lines`/`aiter_bytes`. HIGH confidence — official.
- Anthropic API docs — streaming events, retry semantics, prompt caching, idempotency. HIGH confidence — official.
- Ollama API reference — `/api/chat`, `/api/ps`, `keep_alive` semantics. HIGH confidence — official.
- NVIDIA Jetson developer forums — recurring reports of ARM64 wheel gaps, `nvpmodel` throttling, VRAM eviction under Ollama. MEDIUM confidence — community.
- Reticulum Network Stack documentation — bandwidth/latency characteristics; `rnsh` usage. MEDIUM confidence — official but small ecosystem.
- General distributed-systems folklore — exponential backoff with jitter (AWS Architecture Blog "Exponential Backoff and Jitter"), circuit breaker (Nygard, *Release It!*). HIGH confidence.
- Personal experience with async TUI apps, SSE parsing, and atomic file writes on POSIX.

---
*Pitfalls research for: connectivity-aware Python AI harness (cyberharness v1.0)*
*Researched: 2026-07-07*
