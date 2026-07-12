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

## Workspace Config Schema (YAML, server-side only)

```yaml
name: myproject
image: cyberharness-workspace:latest

# Bare clone — no default working tree
repos:
  - url: git@github.com:scottcowan/cyberharness.git
    bare_path: /workspace/.git-store
    worktrees:
      - branch: main
        path: /workspace/main
      - branch: feature/probe-debounce
        path: /workspace/feature-probe

# Permission level: readonly | write | admin
permission: write
scope:
  paths:
    - /workspace/cyberharness/src/
  git:
    push_pattern: "hotfix/*"   # only branches matching this can be pushed

# Secret refs — values pulled from secret store at provision time
# Tagged by permission level — readonly workspaces only get readonly secrets
secrets:
  - name: ANTHROPIC_API_KEY
    permission: readonly
  - name: GITHUB_TOKEN
    permission: write
  - name: AWS_ACCESS_KEY_ID
    permission: write

ssh_keys:
  - path: ~/.ssh/id_ed25519
    mount: readonly   # bind-mounted read-only into container

mcp:
  - name: filesystem
    config: /workspace/.mcp/filesystem.json

# CLAUDE.md composition — multiple files concatenated in order
# Later entries override earlier ones on conflicts
claude_md:
  - /workspace/cyberharness/CLAUDE.md        # repo conventions (from the repo itself)
  - /workspace/.workspace/HOTFIX.md          # workspace-specific runbooks and scope constraints
knowledge:
  wiki_root: /workspace/knowledge/wiki
  refs_root: /workspace/knowledge/refs
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
