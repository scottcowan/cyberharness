---
created: 2026-07-12
title: Define workspace config schema and secret store design
area: server/workspace
resolves_phase: 8
files:
  - packages/server/src/cyberharness_server/workspace/config.py
  - packages/server/src/cyberharness_server/secrets/store.py
  - docs/workspace-config.md
---

## Project/Intent Object Model

Projects are first-class objects. Each project contains named intents — each intent represents what you want to do with that project (observe, develop, hotfix, review). The TUI workspace picker is two-level: project → intent.

- **Project** carries: repo (bare clone), knowledge base, base CLAUDE.md, base image, default secrets
- **Intent** carries: permission level, path scope, git push patterns, model class pairing, additional CLAUDE.md layers (runbooks/criteria), additional secrets
- Intent name is human-readable ("hotfix", "review") — not a container ID
- Cross-workspace workflow addressing: `workspace: cyberharness/hotfix` (project/intent)
- Intent files (`.intents/hotfix.md`, `.intents/review.md`) live in the repo alongside the code — versioned and improvable

## Project Config Schema (YAML, server-side only)

```yaml
# ~/.cyberharness/projects/cyberharness.yaml
name: cyberharness
description: Connectivity-aware AI harness for the Jetson Cyberdeck
repo: git@github.com:scottcowan/cyberharness.git
bare_path: /workspaces/cyberharness/.git-store
base_image: cyberharness-workspace:latest
claude_md: /workspaces/cyberharness/CLAUDE.md    # base — all intents inherit this
knowledge:
  wiki: /workspaces/cyberharness/knowledge/wiki
  refs: /workspaces/cyberharness/knowledge/refs
ssh_keys:
  - path: ~/.ssh/id_ed25519
    mount: readonly
mcp:
  - name: filesystem
    config: /workspaces/cyberharness/.mcp/filesystem.json
default_secrets:
  - name: GITHUB_TOKEN
    permission: readonly

intents:
  observe:
    description: Browse code, ask questions, view logs
    permission: readonly
    model_class: remote-sonnet

  develop:
    description: Normal development work
    permission: write
    scope:
      paths: [/workspace/]
      git: { push_pattern: "feature/*, fix/*" }
    model_class: remote-sonnet
    additional_secrets:
      - name: ANTHROPIC_API_KEY
        permission: write

  hotfix:
    description: Targeted fix with runbooks — scoped to router/ and probe/
    permission: write
    scope:
      paths:
        - /workspace/src/cyberharness/router/
        - /workspace/src/cyberharness/probe/
      git: { push_pattern: "hotfix/*" }
    model_class: remote-sonnet
    claude_md:                                   # appended after base claude_md
      - /workspaces/cyberharness/.intents/hotfix.md
    worktrees:
      - branch: main
        path: /workspace/main

  review:
    description: Verify a change or PR — read-only, high reasoning
    permission: readonly
    model_class: remote-opus
    claude_md:
      - /workspaces/cyberharness/.intents/review.md
```

## Secret Store Design

- SQLite database at `/var/cyberharness/secrets.db` on node2
- Fernet encryption (Python `cryptography` library); master key in node2 env var `CYBERHARNESS_SECRET_KEY`
- Schema: `secrets(name TEXT PRIMARY KEY, ciphertext BLOB, permission_level TEXT, created_at, rotated_at)`
- `cyberharness-secrets` CLI: `add <name> <permission>`, `rotate <name>`, `list`, `delete <name>`
- Server reads secrets at provision time; injects as env vars into workspace container; never writes to container filesystem
- Audit log: every secret access logged with timestamp, workspace_id, secret name (not value)

## Escalation Token Design

- Readonly workspace requests a write action → server issues a scoped escalation token
- Token: `{workspace_id, allowed_paths: [...], allowed_git_patterns: [...], expires_at: now+15min}`
- Stored in memory only (not persisted); surfaced to user in TUI for approval before issuance
- Audit log entry on issue and expiry

## CLAUDE.md Composition

Workspace CLAUDE.md is a list of files concatenated in order before injecting as system context. Later files override earlier ones on conflict. This allows:
- Repo CLAUDE.md: code conventions, architecture decisions, project context
- Workspace CLAUDE.md: operational scope constraints, runbooks for specific tasks, risk profile

Example hotfix workspace CLAUDE.md content:
- Scope declaration ("this workspace has write access to X only")
- Runbooks for common operations (fix dropped connection bug, roll back bad router change)
- Explicit constraints ("push only to hotfix/* branches")
- The model reads this before acting — no need to infer safe procedures from the codebase

## Questions to resolve during Phase 8 planning

1. Where does the master Fernet key live in production? Node2 env var is fine for home server; what about if the server moves to a cloud VM?
2. Should worktrees be provisioned eagerly (all listed branches cloned at workspace create) or lazily (branch cloned when first accessed)?
3. SSH key handling: bind-mount read-only (simplest) vs ssh-agent forwarding into container (cleaner, no key file in container namespace)?
