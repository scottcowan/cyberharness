---
gsd_roadmap_version: 1.0
milestone: v1.1
milestone_name: Same-Network Server
granularity: standard
total_phases: 6
phase_range: 7–12
last_updated: 2026-07-08
---

# Roadmap: cyberharness v1.1 — Same-Network Server

**Goal:** A Python FastAPI server running on the home network that the Cyberdeck client discovers via mDNS, provisions workspaces on, and connects to for cloud-model access, file browsing, and codebase knowledge graphs.

**Continues from:** v1.0 Phase 6 (queue stub active; relay client stub wired in)

---

## Phases

- [ ] **Phase 7: Server Foundation** — Installable FastAPI server with mDNS, HTTPS, and shared-secret auth
- [ ] **Phase 8: Workspace Provisioning** — Server-side workspace lifecycle: create, configure, list, delete
- [ ] **Phase 9: OpenAI-Compatible Relay** — Server proxies cloud providers; client queue drains through it
- [ ] **Phase 10: File & Diff Surface** — Directory tree, file read, git diff endpoints + TUI rendering
- [ ] **Phase 11: Knowledge Graph** — graphify runs over workspace codebases; graph served to TUI
- [ ] **Phase 12: Client Integration & E2E** — Client auto-discovers server, connects, full offline→online→drain loop verified

---

## Phase Details

### Phase 7: Server Foundation
**Goal:** A user on a home Linux machine installs `cyberharness-server` via uv, starts it, and it is discoverable on the LAN from the Cyberdeck client.
**Depends on:** v1.0 complete
**Requirements:** SERVER-01, SERVER-02, SERVER-03, SERVER-04
**Success Criteria:**
  1. `uv tool install cyberharness-server` on aarch64 or x86_64 Linux produces a working `cyberharness-server` entry point
  2. On startup, server advertises itself via mDNS (`_cyberharness._tcp.local`) and the Cyberdeck client discovers it without manual IP config
  3. All endpoints require a shared-secret bearer token; unauthenticated requests return 401
  4. Server serves HTTPS with an auto-generated self-signed cert; client trusts on first connect (TOFU) and pins the cert fingerprint

### Phase 8: Workspace Provisioning
**Goal:** A user can create and configure a named workspace on the server from the Cyberdeck TUI, and the workspace persists git repos, auth keys, SSH keys, CLAUDE.md, and MCP config server-side.
**Depends on:** Phase 7
**Requirements:** WORK-01, WORK-02, WORK-04
**Success Criteria:**
  1. `POST /workspaces` creates a named workspace directory; `GET /workspaces` lists all with status
  2. TUI workspace provisioning flow (GSD-style) guides the user through repo clone, .env setup, SSH key, CLAUDE.md, and MCP config — all stored on the server, never on the Cyberdeck
  3. Workspace survives a server restart: all config, credentials, and git state intact
  4. `DELETE /workspaces/{id}` removes the workspace and its credentials; deletion is confirmed before executing
  5. Local workspace structure (`~/.cyberharness/workspace/`) mirrors the server directory layout — ready for sync in a later milestone

### Phase 9: OpenAI-Compatible Relay
**Goal:** The server proxies requests to OpenAI and Anthropic cloud APIs; the client queue drains through the server rather than calling cloud APIs directly.
**Depends on:** Phase 8
**Requirements:** RELC-01, RELC-02, SERVER-05
**Success Criteria:**
  1. `POST /v1/chat/completions` on the server proxies to the configured cloud provider and streams tokens back to the client via SSE — client code is unchanged
  2. Cloud API keys are stored on the server only; client config has no cloud API keys
  3. Client's QueueManager drains envelopes to the server relay endpoint; server executes against the cloud model; SSE stream returned to client
  4. A queue item enqueued while offline drains correctly on reconnect — full round-trip verified
  5. Failed cloud calls (5xx, timeout) are retried on the server with exponential backoff; 4xx (auth failure, bad request) surface to the client immediately

### Phase 10: File & Diff Surface
**Goal:** A user on the Cyberdeck can browse workspace files and view git diffs in the TUI artifact surface.
**Depends on:** Phase 8
**Requirements:** WORK-03, FILE-01, FILE-02, FILE-03
**Success Criteria:**
  1. `GET /workspaces/{id}/files` returns the directory tree excluding .env and credential files
  2. `GET /workspaces/{id}/files/{path}` returns file contents; binary files return a "binary file" indicator
  3. `GET /workspaces/{id}/diff` returns the current git diff formatted for diff-so-fancy rendering
  4. TUI artifact surface renders the file tree and diffs — user can navigate the tree and open files into the artifact pane
  5. Secrets never appear in file tree responses (`.env`, `*.key`, `*.pem`, credentials directories are excluded at the server)

### Phase 11: Knowledge Graph
**Goal:** The server runs graphify over a workspace's codebases on demand, and the Cyberdeck TUI can view the resulting graph in the artifact surface.
**Depends on:** Phase 8
**Requirements:** WORK-05, GRAPH-01, GRAPH-02
**Success Criteria:**
  1. `POST /workspaces/{id}/graph/build` triggers graphify over the workspace's git repos; completes asynchronously; progress streamed via SSE
  2. `GET /workspaces/{id}/graph` returns the graph data (nodes, edges, metadata)
  3. Graph is rebuilt automatically when a workspace repo receives new commits
  4. TUI artifact surface renders the graph — user can navigate nodes (files, functions, modules) and see edges

### Phase 12: Client Integration & E2E
**Goal:** The assembled v1.1 system works end-to-end: client discovers server, connects, provisions a workspace, runs a conversation that queues while offline, drains through the relay, and the user can browse files and graph.
**Depends on:** Phases 7–11
**Requirements:** INTG-01, INTG-02
**Success Criteria:**
  1. Full flow works: client auto-discovers server → user selects workspace → sends a cloud-phase message → goes offline → message queues → reconnects → drains through server relay → response streams back
  2. Server connection status visible in client status bar at all times; disconnect/reconnect handled gracefully without losing in-flight local turns
  3. Workspace file tree and diff view accessible from client TUI without any additional config after initial workspace setup
  4. All v1.0 local-only behavior is unaffected when server is not present on the network

---

## Ordering Rationale

- Phase 7 (server foundation) is prerequisite — everything else runs on top of it
- Phase 8 (workspaces) before Phase 9 (relay) — relay needs a workspace context to execute within
- Phase 10 (files) and Phase 11 (graph) are independent of each other after Phase 8 — can run in parallel
- Phase 12 (integration) comes last — verifies the assembled system including queue drain

---

*Roadmap created: 2026-07-08*
