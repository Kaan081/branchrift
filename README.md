# Repo Preflight

**See branch divergence, same-path collisions, ownership gaps, and Git LFS readiness before integration — without modifying your repository.**

Repo Preflight is a read-only Git CLI for developers and small teams that want a fast integration check before merging or promoting a branch.

It answers questions such as:

- Did the base and feature branch diverge?
- Did both sides modify the same repository path?
- Is that collision a binary-sensitive `.uasset` or `.umap`?
- Are Git LFS-managed files hydrated and ready?
- Did a change cross an ownership boundary?
- Which changed files actually deserve manual review?

Repo Preflight is intentionally advisory. It does **not** merge, checkout, pull, commit, delete, modify, or automatically approve repository changes.

## Why this exists

A normal Git diff tells you what changed.

Before integration, teams often need a different view:

> **What could make this branch expensive or risky to integrate?**

Repo Preflight combines Git topology, same-path branch collisions, ownership rules, binary/LFS readiness, technical-risk signals, and focused verification checks into one report.

For Unreal Engine teams using Git/LFS, one especially useful case is simple:

> **Two branches touched the same `.umap`. Know before you integrate.**

## Quick start

Install from PyPI:

```bash
pipx install repo-preflight
```

Create a minimal `.preflight.json`:

```json
{
  "ownership": [
    {
      "match": "prefix",
      "path": "Source/",
      "owner": "Code"
    },
    {
      "match": "prefix",
      "path": "Content/",
      "owner": "Content"
    }
  ]
}
```

Then run:

```bash
preflight --base main
```

Or inspect another fetched branch without checking it out:

```bash
preflight --base main --head origin/feature/environment-pass
```

## Example: catch integration risk before merge

```text
=== Repository Preflight ===
Current branch: feature/environment-pass
Base: main
Head: HEAD
Repository state: CLEAN

Topology:
Behind: 4
Ahead: 7
Relationship: DIVERGED
FF eligible: NO

Collisions:
Count: 2
Binary-sensitive: 1

- Content/Maps/L_Main.umap [map, BINARY-SENSITIVE]
- Source/Game/Inventory.cpp [source]

Binary / LFS readiness:
- Content/Maps/L_Main.umap
  LFS managed: YES
  LFS state: pointer
  Readiness: ATTENTION

Technical risk: MEDIUM
Governance: PASS

Required checks:
- map integration verification
- build verification

Manual review:
- Content/Maps/L_Main.umap
- Source/Game/Inventory.cpp
```

A **collision** means the same repository path changed on both sides since the merge-base. It does **not** mean Repo Preflight is claiming that Git will definitely produce a textual merge conflict.

For binary Unreal files such as `.uasset` and `.umap`, collisions are marked **BINARY-SENSITIVE** instead of pretending the tool can inspect their internal semantics.

## What it reports

Repo Preflight currently reports:

- base/head commit SHAs and merge-base;
- ahead/behind counts and topology relationship;
- fast-forward eligibility;
- same-path branch collisions;
- binary-sensitive asset/map collisions;
- exact conservative text change facts;
- Git LFS and working-tree readiness;
- configurable repository ownership;
- ownership gaps and boundary crossings;
- technical-risk signals;
- required verification checks;
- focused manual-review paths;
- dirty working-tree state;
- revision provenance;
- deterministic JSON output.

## Design principles

Repo Preflight is deliberately:

- **read-only** — it never mutates the repository;
- **conservative** — it does not invent semantics it cannot prove;
- **explicit** — topology, provenance, readiness, and uncertainty are reported directly;
- **automation-friendly** — human-readable terminal output and deterministic JSON are both supported;
- **Git-native** — it works with existing Git workflows instead of replacing source control.
