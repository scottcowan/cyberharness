# Pitfalls Research

**Project:** warren v1.0 — Python environment broker for AI agent workspaces
**Domain:** FastAPI container-lifecycle broker (Podman/Docker rootless), secret injection, git worktree management, NDJSON streaming, UDP peer discovery, SQLite+Fernet persistence
**Researched:** 2026-07-12
**Confidence:** HIGH (container lifecycle, git worktrees, Fernet, aiosqlite — well-documented failure modes); MEDIUM (Podman rootless quirks and UDP+Tailscale interaction — depend on host config)

## Critical Pitfalls

### Pitfall 1: Leaked containers on server restart / crash

**What goes wrong:**
FastAPI process dies (SIGKILL, OOM, host reboot, `uvicorn --reload` in dev) while workspace containers are running. Containers keep executing, holding CPU/RAM/disk, but the DB row that tracked them is stale or points at a dead server. On next boot warren has no idea which containers it owns; users see duplicates, or "orphan" workspaces they cannot stop via the API.

**Why it happens:**
- Container lifetime is decoupled from the broker process — Podman/Docker outlives it, and rootless Podman has no `docker.service` to reconcile against.
- Devs test with graceful shutdown only; they never `kill -9` the server and then start it again to see what happens.
- The DB is treated as the source of truth without a reconcile step against the runtime.

**How to avoid:**
- **Deterministic labelling.** Every container gets labels `warren.workspace_id=<uuid>`, `warren.server_instance=<install_id>`, `warren.created_at=<iso>`. On boot: `podman ps -a --filter label=warren.server_instance=<id>` and cross-check against DB. Adopt survivors, mark missing rows as `state=lost`, `podman rm -f` unlabelled zombies from previous crash-loops beyond an age threshold.
- **Startup reconciliation is a first-class subsystem**, not a nice-to-have.
- Register a FastAPI lifespan `shutdown` hook to snapshot state — but assume it will not run and rely on labels as source of truth.
- Set `--restart=no` on containers so a host reboot does not silently resurrect them.

**Warning signs:**
- `podman ps -a | wc -l` grows monotonically across dev sessions.
- Users report "I stopped that workspace an hour ago, why is the CPU still pegged?"
- DB has more `state=running` rows than `podman ps` returns.

**Phase to address:** Phase 1 (Runtime foundation) — labelling + reconcile loop before workspace #2.

---

### Pitfall 2: Orphaned child processes inside containers (PID 1 problem)

**What goes wrong:**
Sidecar spawns subprocesses (git, python, the agent itself). Sidecar dies. Children reparent to PID 1. If PID 1 is `bash` or your sidecar without proper signal handling, zombies pile up, `podman stop` hangs 10s then SIGKILLs, and file locks are not released cleanly.

**Why it happens:**
Container PID 1 has special semantics: default signal handlers are not installed, and PID 1 must reap children. Most Python scripts do neither. Podman/Docker's `--init` flag fixes this via `tini`, but it is easily forgotten.

**How to avoid:**
- Always run containers with `--init` — puts `tini` at PID 1.
- If `--init` is unavailable (e.g. under nsjail), the sidecar must install `signal.signal(SIGCHLD, reap)` and forward SIGTERM/SIGINT to children.
- Spawn subprocesses with `Popen(..., start_new_session=True)` and kill the whole process group on shutdown (`os.killpg`).

**Warning signs:**
- `podman stop <c>` consistently takes ~10 seconds.
- `ps -ef` inside container shows `<defunct>` entries.
- Agent commands return but their spawned processes keep running.

**Phase to address:** Phase 1 (Runtime foundation) — bake `--init` into the runtime wrapper.

---

### Pitfall 3: Secrets leaking via `podman inspect`, `/proc/*/environ`, and logs

**What goes wrong:**
Secret injection via `-e FOO=$SECRET` or `--env-file` writes plaintext into container metadata that `podman inspect <c>` returns verbatim. It also appears in `/proc/<pid>/environ` on the host (readable by the same UID). If warren logs the subprocess argv, or FastAPI middleware logs request bodies, the plaintext secret lands in `journalctl`/stdout. Any operator running `ps auxe` sees them.

**Why it happens:**
- Env vars are the path of least resistance — SDKs literally offer `environment={...}`.
- Debug `logger.info(f"launching {cmd}")` added in Phase 1 is often forgotten.
- FastAPI's access log default is safe, but Sentry, request-logging middlewares, and error handlers commonly capture bodies.

**How to avoid:**
- **Prefer tmpfs-mounted secret files** where the workload can read a path: `--mount type=tmpfs,dst=/run/secrets` + write files with `0400` perms via a small init step. Mirrors Docker/Podman secret semantics.
- If env vars are unavoidable, use `--env-file <path>` on a tmpfs and delete the file immediately after start. (Note: still visible in `inspect`; container's copy remains.)
- **Redacting log formatter**: hash any value whose key matches `(secret|token|key|password|api)` before emit.
- Never log full subprocess argv — log `argv[0]` and a redacted arg count.
- Disable body-capturing middleware on endpoints accepting secrets.
- Document: `podman inspect` output is a secret-bearing artefact — do not paste in bug reports.

**Warning signs:**
- `grep -r "AKIA\|sk-\|ghp_" /var/log` returns hits.
- `podman inspect <c> | jq .Config.Env` shows anything sensitive in plaintext.
- Any secret ever appears in Sentry, a crash report, or a screenshot.

**Phase to address:** Phase 2 (Secret management) — before any real credential is injected. Add a test asserting a known-secret token never appears in captured logs.

---

### Pitfall 4: Podman rootless — user namespace exhaustion (subuid/subgid limits)

**What goes wrong:**
Rootless Podman uses `/etc/subuid` and `/etc/subgid` to map container UIDs. Default allocation is 65536 IDs per user. Container images requesting high in-container UIDs, or `--userns=keep-id` combined with high UIDs, fail at container-create with `newuidmap: write to uid_map failed: Invalid argument` or `numerical result out of range`.

**Why it happens:**
- Default 65536 is often enough for one image but not many.
- Some cloud-init'd VMs do not populate `/etc/subuid` for non-login users at all → rootless Podman refuses to start.

**How to avoid:**
- Preflight on server boot: `podman info --format '{{.Host.IDMappings}}'`, verify ≥ 65536, refuse to start with a clear error otherwise.
- Document `usermod --add-subuids 100000-165535 --add-subgids 100000-165535 <user>` in setup script.
- Prefer container images that stay in low UID space (< 65536). Log a WARN if `--userns=keep-id` is used.
- Set `storage.conf`'s `runroot`/`graphroot` to a path with plenty of inodes — not `/tmp`.

**Warning signs:**
- Errors mentioning `newuidmap`, `slirp4netns`, or `cannot set up userns`.
- Works for user A, fails for user B on the same host.

**Phase to address:** Phase 1 (Runtime foundation).

---

### Pitfall 5: Podman rootless — overlay storage silently falling back to `vfs`

**What goes wrong:**
Rootless Podman defaults to overlay storage in `~/.local/share/containers/storage`. If `$HOME` is on NFS/ecryptfs/ZFS-without-config, or `fuse-overlayfs` is missing, Podman silently falls back to `vfs`, which copies the entire image on every layer — 10-100× slower and eats disk. Or it fails to start.

**Why it happens:**
- `fuse-overlayfs` is not installed on minimal distros.
- Kernel < 5.11 without `fuse-overlayfs` cannot do rootless overlay natively.

**How to avoid:**
- Preflight: check `podman info --format '{{.Store.GraphDriverName}}'` — refuse to start on `vfs` unless explicitly opted in.
- Install `fuse-overlayfs` as a hard setup dep.
- Allow `WARREN_STORAGE_ROOT` to point graph store at a known-good path (e.g. `/var/lib/warren-storage`).

**Warning signs:**
- Container start times measured in minutes.
- Disk usage of `~/.local/share/containers` balloons past image_sum × N.
- `podman info` reports `graphDriverName: vfs`.

**Phase to address:** Phase 1 (Runtime foundation).

---

### Pitfall 6: Rootless port-binding failures and slirp4netns performance cliff

**What goes wrong:**
Rootless containers cannot bind ports < 1024 without host-level tweaks. `-p 80:8080` silently fails. Rootless default networking is slirp4netns, which adds ~2× latency and ~10× throughput hit vs. host networking — often unnoticed until file transfers or large streams get sluggish.

**Why it happens:**
`net.ipv4.ip_unprivileged_port_start=1024` on most distros. slirp4netns is user-mode TCP/IP.

**How to avoid:**
- Publish only on high ports (≥ 10000). Warren's proxy handles any low-port façade.
- Document `sysctl net.ipv4.ip_unprivileged_port_start=443` if truly needed.
- For sidecar streams, prefer Unix domain sockets on a shared volume over TCP where possible.
- Consider `--network=pasta` (Podman 4.4+) for better rootless throughput than slirp4netns.

**Warning signs:**
- `Error: rootlessport cannot expose privileged port 80`.
- Intra-host bandwidth < 100 Mbps.

**Phase to address:** Phase 3 (Networking/proxy).

---

### Pitfall 7: Bare git clone corruption via concurrent worktree operations

**What goes wrong:**
Two worktrees created from the same bare clone run `git fetch` simultaneously, or one runs `git gc` while another is mid-checkout. Result: half-written `.pack` files, corrupted `packed-refs`, stale `index.lock` after a crash, worktree metadata pointing at deleted branches. Recovery ranges from `git worktree prune` + `git worktree repair` to a full reclone.

**Why it happens:**
- Git assumes a single writer per repo. `git worktree` shares the object DB across workers but does not add locking beyond `index.lock`.
- `git gc --auto` fires opportunistically and can conflict with concurrent fetches.
- SIGKILL during `git fetch`/`git checkout` leaves stale `.lock` files that clear only manually.

**How to avoid:**
- **Serialise writes to the bare repo** via an asyncio Lock keyed by repo path. Reads/checkouts inside a worktree are safe concurrently — only fetch/gc/prune need the global lock.
- Disable auto-gc on bare repos: `git config gc.auto 0`, run `git gc` on a scheduled job under the lock.
- Never `rm -rf` a worktree directory — always `git worktree remove <name>` (removes metadata too). If the directory is already gone, `git worktree prune`.
- On workspace destroy: `git worktree remove --force <path>` first, then `rm -rf` any residue.
- Store bare repos on a local filesystem — never NFS/SMB (fcntl locks unreliable).

**Warning signs:**
- `error: unable to read <sha>` or `bad object` on fetch.
- `fatal: '<path>' is already checked out at '<other>'` — stale worktree metadata.
- `.lock` files older than a few seconds in `.git/`.

**Phase to address:** Phase 4 (Git/workspace management).

---

### Pitfall 8: NDJSON stream buffering — the "live output arrives in bursts" problem

**What goes wrong:**
Sidecar writes NDJSON events with `print(json.dumps(evt))`. Python buffers stdout in 4-8 KB blocks when not attached to a TTY. Client sees nothing for 30 seconds, then a burst. Add a reverse proxy (nginx/Traefik) and it re-buffers. Add gzip and it gets worse.

**Why it happens:**
- Python `sys.stdout` is line-buffered on TTY, block-buffered on pipes.
- FastAPI/Starlette's `StreamingResponse` flushes per yield, but middlewares like `GZipMiddleware` buffer the entire response.
- Nginx/Traefik default to proxy buffering.

**How to avoid:**
- Sidecar: `python -u` or `PYTHONUNBUFFERED=1`; explicit `sys.stdout.flush()` after every event. Better: write bytes directly (`os.write(1, line)`).
- Server: `StreamingResponse(content_type="application/x-ndjson")`; exclude stream routes from GZipMiddleware.
- Set headers: `X-Accel-Buffering: no` (nginx), `Cache-Control: no-cache`.
- Use HTTP/1.1 chunked transfer; verify HTTP/2 frame flushing end-to-end before adopting.
- Emit heartbeat events every ~15s so idle connections survive middlebox timeouts (typically 30-60s).

**Warning signs:**
- Events arrive in bursts, not smoothly.
- Time-to-first-byte > 1s.
- Long-running commands appear to hang, then dump everything at once.

**Phase to address:** Phase 3 (Streaming/proxy).

---

### Pitfall 9: NDJSON reconnection loses events (no resume semantics)

**What goes wrong:**
Client's HTTP connection drops mid-stream (WiFi flap, proxy idle timeout, laptop lid close). Sidecar keeps emitting; when the client reconnects, everything between disconnect and reconnect is gone. Or worse: reconnect spawns a second consumer on the same sidecar stream, interleaving events.

**Why it happens:**
NDJSON has no built-in resume (unlike SSE's `Last-Event-ID`). HTTP request/response is not a session.

**How to avoid:**
- Assign each event a monotonic `seq` per workspace; buffer the last N (e.g. 1000) in warren-server memory or an aiosqlite events table.
- Reconnect endpoint accepts `?since=<seq>` and replays.
- Enforce single-consumer per sidecar stream — warren-server multiplexes; sidecar always talks to warren.
- Consider SSE (`text/event-stream`) if the client is a browser — `EventSource` reconnect is free.
- Client-side ack ("processed up to seq N") allows warren to drop older buffered events.

**Warning signs:**
- After a brief network blip, users see truncated command output.
- Events observed twice or interleaved.

**Phase to address:** Phase 3 (Streaming/proxy) — retrofit is painful.

---

### Pitfall 10: UDP peer discovery — Docker/Podman bridges "steal" broadcasts

**What goes wrong:**
Warren advertises `255.255.255.255:<port>` for LAN peer discovery. On a host with Docker/Podman up, default bridges (`docker0`, `cni-podman0`) sit on `172.x/16`. The broadcast goes out the wrong interface, or the listener bound to `0.0.0.0` picks up its own broadcast from every bridge — duplicate "peer" records and loops.

**Why it happens:**
- Linux routes `255.255.255.255` by kernel routing-table order — not necessarily the user's LAN.
- A `0.0.0.0`-bound listener receives every interface's broadcast, including bridge subnet broadcasts (`172.17.255.255`).

**How to avoid:**
- Enumerate interfaces via `psutil.net_if_addrs()` or `netifaces`; filter out `docker*`, `cni-*`, `podman*`, `br-*`, `veth*`, `lo`.
- Send subnet-directed broadcasts (e.g. `192.168.1.255`) instead of `255.255.255.255` — routes cleanly out one interface.
- Bind the listener to a specific interface IP, not `0.0.0.0`, or filter incoming packets by source subnet.
- De-dupe peers by an install UUID in the advertisement payload — not by `(ip, port)`, since one host may appear via multiple interfaces.

**Warning signs:**
- Warren "discovers itself" as a peer.
- Peers on the same LAN cannot see each other; peers on different LANs appear via VPN.
- Discovery works with Docker stopped, breaks when Docker starts.

**Phase to address:** Phase 6 (Peer discovery) — interface selection as a config surface from day 1.

---

### Pitfall 11: UDP discovery advertising Tailscale/VPN addresses

**What goes wrong:**
Tailscale creates `tailscale0` on `100.64.0.0/10`. Warren advertises "connect me at <first non-loopback IPv4>" and picks the tailnet address. LAN peers try to route to `100.64.x.x` and fail unless they are also on the tailnet.

**Why it happens:**
- Interface order is non-deterministic on Linux.
- `socket.gethostbyname(socket.gethostname())` is notoriously unreliable — often returns `127.0.1.1` or the tailnet address.

**How to avoid:**
- Explicit config: `WARREN_ADVERTISE_IFACE=eth0` or `WARREN_ADVERTISE_IP=192.168.1.42`.
- Auto-detect: respond on the interface the incoming discovery message arrived on (packet source-based).
- Exclude interface prefixes: `tailscale*`, `wg*`, `zt*`, `tun*`, `tap*` from LAN broadcast scope; treat them as separate discovery scopes.
- On the tailnet, use MagicDNS + `tailscale status --json` for service discovery — UDP broadcasts do not cross the tailnet anyway.

**Warning signs:**
- Peers announce a `100.64.x.x` IP to LAN peers.
- Warren works over Tailscale or LAN but not both simultaneously.

**Phase to address:** Phase 6 (Peer discovery).

---

### Pitfall 12: aiosqlite connection-per-request thrash and writer contention

**What goes wrong:**
Devs write `async with aiosqlite.connect(db_path) as db: ...` inside every request handler. SQLite has a single writer — under load, `sqlite3.OperationalError: database is locked` fires unpredictably. Even without contention, `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout` must be set per connection and are lost on close.

**Why it happens:**
aiosqlite is a thin async wrapper — no built-in pool. FastAPI tutorials copy-paste Postgres patterns that assume server-side concurrency.

**How to avoid:**
- **One long-lived writer connection** owned by a background task + an asyncio.Queue for write ops. All writes serialised through it.
- **A small pool of read connections** (2-4) reused across requests.
- Set PRAGMAs once at connection open: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `foreign_keys=ON`.
- Alternatively use SQLAlchemy 2.x async (`create_async_engine("sqlite+aiosqlite:///...", pool_size=5, max_overflow=0)`).
- Never call sync `sqlite3` from an async handler — blocks the event loop.

**Warning signs:**
- Intermittent `database is locked`.
- Latency spikes proportional to concurrent write load.
- `PRAGMA journal_mode` returns `delete` — WAL was never enabled.

**Phase to address:** Phase 1 (Persistence layer).

---

### Pitfall 13: aiosqlite + FastAPI test isolation (in-memory DB per event loop)

**What goes wrong:**
Tests use `:memory:` SQLite. First test passes; second test sees prior data or gets `no such table` because a new event loop got a fresh in-memory DB.

**Why it happens:**
`:memory:` databases are per-connection. Different connections (or the same connection across different event loops) see different DBs. pytest-asyncio's default `loop_scope="function"` closes loops per test.

**How to avoid:**
- Use `file::memory:?cache=shared` URI with `uri=True`, or a tempfile DB per test session.
- Set pytest-asyncio `loop_scope="session"` and truncate tables between tests.
- Never share aiosqlite connections across event loops.

**Warning signs:**
- Tests pass individually, fail when run together.
- `no such table` errors only in CI.

**Phase to address:** Phase 1 (Persistence layer) — nail testing pattern before schema grows.

---

### Pitfall 14: Fernet key stored as a config value

**What goes wrong:**
The Fernet key ends up in `.env.example`, or logged during startup, or included in a support bundle. Anyone with read access to config now has read access to every stored secret.

**Why it happens:**
- Fernet keys look like innocuous base64 strings; the API accepts them as `str`.
- `python-dotenv` loads them alongside non-secret config.
- Startup logs often dump all config for debugging.

**How to avoid:**
- Load the key from a **path** (`WARREN_FERNET_KEY_FILE=/etc/warren/keys/current`), not an env var. File mode `0400`, owned by warren user.
- Redacting formatter for any config value whose name contains `KEY|SECRET|TOKEN`.
- Leave `.env.example` empty for that field; error clearly if unset.
- Generate the key at install time via `Fernet.generate_key()` and write to the file — never let the user paste one.

**Warning signs:**
- Fernet key appears in `git log -p`, `podman inspect`, `ps auxe`, or any log file.
- Key file is world-readable.

**Phase to address:** Phase 2 (Secret management).

---

### Pitfall 15: No Fernet key rotation path baked in

**What goes wrong:**
Six months in, the key needs rotation (staff departure, leak, compliance). Every stored ciphertext was encrypted with a single key with no version tag — rotation requires downtime + full re-encrypt migration. Destroy the old key too early and ciphertexts become unrecoverable.

**Why it happens:**
Fernet has `MultiFernet` for exactly this, but tutorials use plain `Fernet`. Rotation is "future work" that never happens.

**How to avoid:**
- Use `MultiFernet([current, previous])` from day 1. Decryption tries keys in order; encryption always uses the first.
- Prefix ciphertexts with a key-id (Fernet's token includes a timestamp but not a key-id — wrap it: `f"v1:{fernet.encrypt(x)}"`).
- Store key metadata (created_at, retired_at) in DB or a keys directory.
- CLI subcommand `warren rotate-key`: (1) generate new key, (2) new = current + old = previous, (3) walk DB re-encrypting rows, (4) drop old key.
- Never delete an old key until re-encryption is verified complete.

**Warning signs:**
- Only one key file has ever existed.
- No test covers "decrypt data encrypted with a previous key."

**Phase to address:** Phase 2 (Secret management).

---

### Pitfall 16: Fernet — encrypting the wrong things

**What goes wrong:**
Two symmetric failures:
1. **Over-encrypting**: workspace names, timestamps, git URLs are Fernet-encrypted. Cannot query "list workspaces where git_url = X" without decrypting every row. Unindexable data store.
2. **Under-encrypting**: encrypted secret payload is stored, but metadata (`secret_name=OPENAI_API_KEY`, `provider=openai`, `last_used_at`) reveals what the user has connected to. Workspace env templates list every secret name in plaintext.

Also: Fernet is authenticated (HMAC-SHA256) and uses a random IV per encrypt — encrypting the same plaintext twice yields different ciphertexts. Devs try to use it for equality checks/dedup and get burned. IV reuse is not a risk here, but re-encrypting-then-comparing is broken.

**Why it happens:**
"Encrypt everything sensitive" without a threat model. Fields needed for querying get encrypted anyway.

**How to avoid:**
- Explicit list of encrypted fields: **secret values only.** Names, provider hints, workspace metadata stay plaintext.
- Never index or WHERE-clause on a ciphertext column.
- For "does this secret already exist?" checks, use an HMAC (with a separate key) stored alongside the ciphertext — not the ciphertext itself.
- Log a WARN if any code path decrypts more than N rows in a single request (bulk decrypt = design smell).

**Warning signs:**
- Queries that decrypt every row.
- Migration adds an "index on encrypted_col" — reject.
- Bug reports about "search doesn't find my workspace by name".

**Phase to address:** Phase 2 (Secret management) — schema design.

---

### Pitfall 17: FastAPI async endpoint calls blocking subprocess

**What goes wrong:**
Handler does `subprocess.run(["podman", "create", ...], capture_output=True)`. Blocks the event loop for 200ms-2s per call. Under any concurrency, throughput collapses and unrelated requests time out.

**Why it happens:**
`subprocess` is sync. `async def` does not make it async. Devs assume `async def` runs everything off-thread.

**How to avoid:**
- Use `asyncio.create_subprocess_exec(...)` throughout. `await proc.communicate()`.
- For unavoidable sync code, wrap in `await asyncio.to_thread(func)` (Python 3.9+).
- No first-class async Podman SDK exists — `podman-py` is sync; wrap in `to_thread` or shell out with `create_subprocess_exec`.
- Lint rule: no bare `subprocess.` inside `async def`.

**Warning signs:**
- p99 latency correlates with concurrent request count.
- Health check endpoint times out when a workspace is starting.

**Phase to address:** Phase 1 (Runtime foundation).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip startup reconciliation | Ship faster | Every crash orphans a container; user distrust | Never — first-week feature |
| Env-var-only secret injection (no tmpfs option) | Simple, one code path | `podman inspect` leaks; retrofit breaks clients | v0 dev prototype only |
| Single Fernet key, no MultiFernet | 5 lines less code | Rotation needs downtime + full re-encrypt migration | Never — MultiFernet same complexity |
| One aiosqlite connection per request | Familiar Django/Flask pattern | `database is locked` under any real load; WAL not set | Never — pool from day 1 |
| `subprocess.run` for container ops | "Async is complicated" | Event loop stalls; latency scales with concurrency | Prototype/CLI-only paths |
| No event `seq` on NDJSON stream | Simpler payload | No reconnect resume; users lose output on WiFi blip | Single-process demo only |
| `255.255.255.255` broadcast without interface filter | 3 lines of code | Broken on any host with Docker/Tailscale/VPN | Never on real hardware |
| No `--init` on containers | One less flag | Zombies; `stop` hangs; file locks leak | Never (zero cost) |
| Plain `git worktree add` without a lock | Simpler code | Corruption under concurrent fetch; recovery painful | Only if strictly single-workspace |
| Log `subprocess` argv for debugging | Easy debug | Secret leak whenever args contain secrets | Redacted argv only |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Podman rootless | Assume same behaviour as root Podman | Preflight subuid/subgid, storage driver, port range |
| Podman vs Docker | Hard-code `docker` CLI | Abstract runtime; detect `podman`/`docker`; different flag semantics (e.g. `--userns`) |
| nsjail | Treat as drop-in for container | No image layer; runs a binary in a namespace — bring your own rootfs |
| Tailscale | Advertise `tailscale0` IP as "your address" | Explicit interface config; MagicDNS on tailnet |
| Docker bridge | Assume `172.17.0.0/16` is always reachable | Never rely on bridge subnet for peer connectivity |
| SQLite WAL | Enable WAL, forget `synchronous=NORMAL` and `busy_timeout` | Set all three together at connection open |
| Fernet | Store key in env var, log config at startup | Key file `0400`; startup log redaction |
| FastAPI streaming | Wrap `StreamingResponse` in GZipMiddleware | Exclude stream routes from gzip; `X-Accel-Buffering: no` |
| Git worktree | `rm -rf` a worktree directory | `git worktree remove` first, then prune |
| `subprocess` in async | `subprocess.run()` in `async def` | `asyncio.create_subprocess_exec` |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Podman `vfs` storage instead of overlay | Container starts take minutes; disk explodes | Preflight; require `fuse-overlayfs` | Immediately, on first container |
| Sync `subprocess.run` in async handler | Latency spikes with concurrency | `asyncio.create_subprocess_exec` | >2 concurrent workspace ops |
| SQLite writer contention | `database is locked` | Single writer + queue; WAL mode | ~5-10 concurrent writes/sec |
| NDJSON buffered by proxy/gzip | Streams arrive in bursts | Disable gzip on streams; `X-Accel-Buffering: no` | Any reverse proxy in path |
| Discovery broadcast loops (no dedupe) | CPU pegged from packet flood | Install UUID dedupe + interface filter | 3+ peers on same subnet |
| Fernet bulk-decrypt on list endpoints | List latency scales with row count | Encrypt only secret values, not metadata | ~100+ workspaces |
| No connection pool for aiosqlite readers | Cold connections re-set PRAGMAs | Small persistent read pool | Any real traffic |
| Fetch inside global worktree lock | All git ops serialised globally | Lock scope = bare repo only; reads unlocked | Multi-workspace pull-heavy loads |
| slirp4netns network mode | Poor throughput/latency | `--network=pasta` (Podman 4.4+); UDS for internal streams | Bulk file ops or high-bandwidth streams |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Env-var secrets visible in `podman inspect` | Any local admin/support tool reads secrets | Tmpfs-mounted secret files |
| Secrets in FastAPI access logs / Sentry | Secret sprawl into log aggregators | Redacting formatter + body stripping on secret routes |
| Fernet key in env var + config log | Master-key theft = all secrets compromised | Key file `0400`; explicit log redaction |
| Container running as UID 0 (rootless-mapped) | Escape to user's UID on host if kernel bug | Non-root user in image; `--user` flag |
| No cap-drop on container | CAP_NET_RAW, CAP_SYS_PTRACE enable attacks | `--cap-drop=ALL --cap-add=<minimal>` |
| Sidecar has host network access | Container can hit warren's admin API | `--network=<workspace-net>`; deny host loopback |
| Git repo mounted with credential helpers active | Container reads `~/.git-credentials` | Mount `.git` config subset only; no HOME leak |
| UDP discovery replies to any source | Trivial spoofing → fake peers | Signed advertisements (HMAC) or explicit peer trust list |
| SQLite DB file world-readable | Encrypted-secrets DB stolen; offline attacks possible | DB file `0600`, owned by warren user |
| Fernet key derived from a passphrase | Offline brute force | Only accept `Fernet.generate_key()` output (32 bytes random) |
| Reusing container across users (no destroy) | Prior user's tmpfs/env leaks | Destroy container on session end; no reuse across identities |
| Logging `podman inspect` output in support bundles | Support archives contain plaintext secrets | Redact `Config.Env` before emitting bundles |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent container startup failures | "Why isn't my workspace up?" — no feedback | Stream provision events over NDJSON from `POST /workspaces` |
| No workspace status endpoint | Client polls, gets stale data | `GET /workspaces/<id>` with live state + last event seq |
| Destroy returns 200 immediately, container still tearing down | User creates new one, hits port conflict | Wait for actual removal, or 202 + status URL |
| Peer discovery lists "self" | Confusing UI showing localhost as peer | Filter own install UUID |
| Secret rotation without ack from workspaces | Old secret still in running containers | Emit event to sidecar; require ack or restart |
| Log output truncated mid-line on reconnect | JSON parse errors client-side | Server buffers by complete NDJSON lines only |
| Long-running fetch blocks entire git subsystem | User creates workspace, waits for unrelated fetch | Per-repo lock, not global |

## "Looks Done But Isn't" Checklist

- [ ] **Container lifecycle:** verify orphan cleanup on `kill -9 <server>; restart` — not just graceful shutdown.
- [ ] **Secret injection:** grep `podman inspect` output for the raw secret; check `/proc/<pid>/environ`; check journalctl.
- [ ] **Fernet:** verify `MultiFernet` path with a synthetic "old key" — decrypt succeeds, encrypt uses new key.
- [ ] **Fernet key file perms:** confirm `0400`, owned by warren user, not world-readable.
- [ ] **NDJSON streaming:** run through nginx/Traefik with default config; confirm events arrive within 100ms of emission.
- [ ] **NDJSON reconnect:** kill client mid-stream, reconnect with `?since=`, verify no gaps and no duplicates.
- [ ] **UDP discovery:** run on host with Docker AND Tailscale up; verify advertised IP is LAN, not tailnet or bridge.
- [ ] **aiosqlite:** run 50 concurrent write requests; verify no `database is locked` and latency stays flat.
- [ ] **Git worktrees:** run parallel fetch + checkout on 3 worktrees of same bare; verify no corruption via `git fsck`.
- [ ] **Podman preflight:** boot on fresh VM without subuid entries — warren must error clearly, not silently `vfs`-fallback.
- [ ] **`--init` flag:** kill a long-running child inside sidecar; verify `podman stop` returns in < 2s.
- [ ] **Log redaction:** insert a known fake secret into a request; grep every log destination — must not appear.
- [ ] **Sidecar signal handling:** SIGTERM the sidecar; verify child procs terminated (no zombies).
- [ ] **Async subprocess:** grep codebase for `subprocess.run\|subprocess.check_` inside `async def` — must be zero.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Orphaned containers after crash | LOW | `podman ps -a --filter label=warren.server_instance=<id>`, adopt or `podman rm -f` |
| Corrupted bare repo | MEDIUM | Reclone from origin into new bare; `git worktree repair` on each worktree; verify `git fsck` |
| Fernet key lost | HIGH | Encrypted rows unrecoverable; require re-entry of every secret; user-visible outage |
| `database is locked` cascade | LOW | Restart server; ensure WAL + `busy_timeout`; move to writer-queue |
| Duplicate peer entries from UDP loops | LOW | Restart discovery with interface allowlist; purge peers table |
| Leaked secret in logs | HIGH | Rotate every leaked credential upstream; purge log aggregator; audit access |
| Wrong graph driver (`vfs`) | MEDIUM | Stop server; move `~/.local/share/containers` aside; install `fuse-overlayfs`; re-pull images |
| Sidecar PID 1 zombies | LOW | Restart container with `--init`; no data loss |
| Encrypted-field-as-index performance rot | MEDIUM | Add plaintext hash column; backfill; drop encrypted-field query paths |
| Stale `git worktree` metadata | LOW | `git worktree prune`; if directories missing, `git worktree repair` |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Leaked containers on restart (#1) | Phase 1 — Runtime foundation | `kill -9` server, restart, assert container count and DB state consistent |
| PID 1 / zombie procs (#2) | Phase 1 — Runtime foundation | Grep for `--init` in runtime wrapper; `stop` latency test |
| Secrets in inspect/logs (#3) | Phase 2 — Secret management | Test injects known token, greps all log sinks post-run |
| Rootless subuid limits (#4) | Phase 1 — Runtime foundation | Preflight test on VM without subuid entries |
| Overlay storage fallback (#5) | Phase 1 — Runtime foundation | Assert `podman info` graphDriver ≠ vfs at boot |
| Rootless low-port binding (#6) | Phase 3 — Networking/proxy | Integration test uses high ports only |
| Bare repo corruption (#7) | Phase 4 — Git/workspace | Concurrent-fetch chaos test; `git fsck` clean |
| NDJSON buffering (#8) | Phase 3 — Streaming/proxy | End-to-end latency test through a reverse proxy |
| NDJSON reconnect gaps (#9) | Phase 3 — Streaming/proxy | Drop-and-resume test with `?since=` |
| UDP discovery interface confusion (#10) | Phase 6 — Peer discovery | Test on host with Docker bridge up |
| Tailscale interface confusion (#11) | Phase 6 — Peer discovery | Test on host with `tailscale0` present |
| aiosqlite connection thrash (#12) | Phase 1 — Persistence | Concurrent-write load test; assert no `database is locked` |
| Test DB isolation (#13) | Phase 1 — Persistence | Full suite passes in shuffled order |
| Fernet key exposure (#14) | Phase 2 — Secret management | Startup log inspection; file-perms assertion |
| No key rotation (#15) | Phase 2 — Secret management | `rotate-key` command exists; MultiFernet decrypts old ciphertext |
| Wrong things encrypted (#16) | Phase 2 — Secret management | Schema review: encrypted columns are secret values only |
| Blocking subprocess in async (#17) | Phase 1 — Runtime foundation | Lint rule; latency-under-load test |

## Sources

- Podman rootless documentation: https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md — HIGH
- `tini` / container PID 1 problem: https://github.com/krallin/tini — HIGH
- Docker `--init` docs: https://docs.docker.com/reference/cli/docker/container/run/#init — HIGH
- Git worktree concurrency: `git-worktree(1)` man page; Git mailing list discussions on `gc.auto` — HIGH
- SQLite WAL + `busy_timeout`: https://www.sqlite.org/wal.html, https://www.sqlite.org/pragma.html — HIGH
- aiosqlite (no built-in pool; per-connection PRAGMAs): https://github.com/omnilib/aiosqlite — HIGH
- cryptography Fernet + MultiFernet: https://cryptography.io/en/latest/fernet/ — HIGH
- FastAPI streaming + buffering: Starlette `StreamingResponse`; nginx `X-Accel-Buffering` — HIGH
- Tailscale `100.64.0.0/10` CGNAT range: https://tailscale.com/kb/1015/100.x-addresses — HIGH
- UDP broadcast interface selection: Linux routing behaviour for `255.255.255.255` — HIGH
- Podman networking (`pasta` vs `slirp4netns`): https://docs.podman.io/en/latest/markdown/podman-run.1.html#network — MEDIUM
- Personal/operational experience: rootless Podman on ARM64, orphan containers under `uvicorn --reload`, SQLite WAL under FastAPI — MEDIUM

---
*Pitfalls research for: warren v1.0 — Python environment broker for AI agent workspaces*
*Researched: 2026-07-12*
