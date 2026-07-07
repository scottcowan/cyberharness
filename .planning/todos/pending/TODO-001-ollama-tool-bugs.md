---
created: 2026-07-08
title: Guard against Ollama tool use parser bugs
area: router/tools
resolves_phase: 3
files:
  - src/cyberharness/router/ollama.py
  - src/cyberharness/tools/registry.py
---

## Problem

Ollama has several active tool use parser bugs (as of 0.30.12) that will silently corrupt or drop tool calls if not guarded against. These are model-specific but affect multiple families we intend to bench.

## Known bugs to defend against

1. **Mistral-family**: Parameter named `name` silently drops the entire tool call (issue #16932). Workaround: never use `name` as a parameter key — use `value`, `query`, `text`, etc. Enforce in tool registry schema.

2. **Thinking models (Qwen etc.)**: Tool calls placed inside the reasoning block and stripped before parsing. Workaround: explicitly set `think: false` in every tool-use request — don't rely on Ollama's default.

3. **JSON brace detection**: Pre-0.30.12, `{}` inside a JSON string triggers false end-of-call. Workaround: require Ollama ≥ 0.30.12. Check version at startup.

4. **Qwen 3.5**: XML malformation (`<function>` closed by wrong tag) — tool calling completely broken. No fix yet (PR #16841 pending). Recommendation: exclude from tool-capable tier in bench results.

5. **Parallel/nested tool calls**: Unreliable on several models (ornith:35b, possibly others). For v1.0's minimal tool surface this is low risk, but validate single-call round-trips in the bench suite.

## Solution

- Tool registry: disallow parameter named `name` (validation at definition time, clear error message)
- OllamaClient: always inject `"think": false` when tools are present in the request
- Startup check: verify Ollama version ≥ 0.30.12; warn and offer to continue if below
- Bench suite: include a tool call round-trip test for each model (single-call, simple schema); flag models that fail as "tool-use: unreliable"
- Tool response validation: always parse and validate the tool call fields before executing — don't assume a 200 means the call parsed correctly

## References

- Ollama issues: #16932, #16810, #16758, #16693, #16992
- Fixed in 0.30.12: brace detection inside JSON strings
- Pending PRs: #16758 (thinking default), #16934 (mistral3 parser), #16841 (Qwen XML)
