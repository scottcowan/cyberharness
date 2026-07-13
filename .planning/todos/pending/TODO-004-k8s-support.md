---
created: 2026-07-13
title: k8s support
area: server/workspace
files: []
---

## Problem

Placeholder: capture the idea of adding Kubernetes as a deployment/orchestration target for cyberharness. Scope unclear — could mean any of:

- Kubernetes as a hosting target for the cyberharness server (Helm chart / manifests).
- Kubernetes as the *workspace runtime* (per-workspace Pod instead of a per-workspace container via sysbox/Podman — see TODO-002).
- Both.

Needs a scoping pass before it becomes a plan.

## Solution

TBD. Open questions to resolve first:

- Which cluster shape is the target — single-node k3s on a home server, or multi-node managed (EKS/GKE)?
- Does workspace isolation via a Pod (with `securityContext` + gVisor/Kata runtime class) replace the sysbox path in TODO-002, or coexist with it?
- Networking model for MCP tool egress from workspace Pods.
- Storage: PVCs for persistent workspace state vs. ephemeral emptyDir.
- Relationship to warren's runtime abstraction — is a `KubernetesRuntime` implementation of `ContainerRuntime` the right shape, or is k8s a wholly different deployment mode?

Related: TODO-002 (workspace container runtime research).
