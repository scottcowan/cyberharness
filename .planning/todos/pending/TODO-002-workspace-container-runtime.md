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

## Decision criteria

- No `--privileged` required on the server container
- Works on a standard cloud hosting provider (Fly, Render, AWS ECS, etc.)
- Per-workspace container can exec arbitrary shell (extended tool tier in v1.2)
- Reasonable startup latency (< 5s to provision a workspace container)

## Recommendation hypothesis

sysbox-runc is the strongest fit if it works on the target cloud host. Docker socket passthrough is the fallback — simpler but the security trade-off needs documenting.

## References

- https://github.com/nestybox/sysbox
- Nestybox blog: "Running Docker inside Docker without privileged"
- Fly.io / Render container runtime docs — do they support sysbox or nested containers?
