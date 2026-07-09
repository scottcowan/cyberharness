---
created: 2026-07-09
title: Research workspace container runtime for v1.1 server
area: server/workspace
resolves_phase: 7
files:
  - packages/server/src/cyberharness_server/workspace/runtime.py
---

## Problem

The cyberharness server runs fully containerised. Each workspace needs its own isolated container (git, auth, SSH keys, env, MCP tools). Running containers-inside-a-container requires a container runtime that doesn't need `--privileged` — otherwise we negate the security model.

## Options to research

1. **sysbox-runc** (https://github.com/nestybox/sysbox) — Designed specifically for "system containers" running Docker/containers inside containers without `--privileged`. Uses user namespaces. May be the right fit. Check:
   - Can sysbox run inside a cloud-hosted container (ECS, Fly, Render, etc.)?
   - Does it require host kernel modules? If so, what's the hosting requirement?
   - Licensing: Apache 2.0 for sysbox-runc, commercial for some Nestybox features.

2. **Rootless Docker / Podman** — Docker or Podman in rootless mode inside the server container. No host socket needed. Check:
   - Does rootless-in-rootless work cleanly?
   - Performance overhead vs sysbox?

3. **Docker socket passthrough** — Mount `/var/run/docker.sock` into the server container. Simple but the workspace containers become siblings (not children) of the server container, and leaking the Docker socket gives workspace containers potential host access.

4. **Kata Containers** — VM-based, strong isolation, but heavyweight for per-workspace use.

## Key finding: sysbox coexists with Docker

sysbox-runc runs alongside Docker's default runc — it does NOT replace it. Register it in `/etc/docker/daemon.json`, then use `docker run --runtime=sysbox-runc` for workspace containers. The server container itself keeps using standard runc.

**Blocker:** sysbox requires host-level install. It cannot be bundled in a container image and does NOT work on managed cloud platforms (Fly.io, ECS, Render).

**v1.1 is a home server** — user controls the host, so sysbox is viable. Cloud hosting is a later concern.

## Decision criteria

- No `--privileged` required on the server container
- Per-workspace container can exec arbitrary shell (extended tool tier in v1.2)
- Reasonable startup latency (< 5s to provision a workspace container)
- Path to cloud hosting if needed in future

## Recommendation

**v1.1 home server:** sysbox-runc alongside Docker. Install sysbox on the home Linux host; server container uses Docker socket (or host Docker CLI); workspace containers launched with `--runtime=sysbox-runc`. Clean, no `--privileged`, proper nested container support.

**If cloud hosting ever needed:** Switch to Docker socket passthrough (workspace containers as siblings) or rootless Podman inside the server container. Document the trade-off at that point.

## References

- https://github.com/nestybox/sysbox
- Nestybox blog: "Running Docker inside Docker without privileged"
- Fly.io / Render container runtime docs — do they support sysbox or nested containers?
