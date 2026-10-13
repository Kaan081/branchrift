# BranchRift

https://github.com/user-attachments/assets/2c032aa3-86f6-44b4-a3fc-86d83c5ecdc7

> See integration risk before branches come back together.
> See integration risk before branches come back together.

**BranchRift is a read-only Git CLI that surfaces branch divergence, same-path collisions, binary-sensitive changes, Git LFS readiness, ownership gaps, and review requirements before integration.**

Two branches touched the same `.umap`? Know before you integrate.

[![PyPI](https://img.shields.io/pypi/v/branchrift.svg)](https://pypi.org/project/branchrift/)
[![Python](https://img.shields.io/pypi/pyversions/branchrift.svg)](https://pypi.org/project/branchrift/)
[![Tests](https://github.com/Kaan081/branchrift/actions/workflows/tests.yml/badge.svg)](https://github.com/Kaan081/branchrift/actions/workflows/tests.yml)
[![License](https://img.shields.io/github/license/Kaan081/branchrift.svg)](LICENSE)

BranchRift is advisory and read-only.

It does **not** merge, checkout, pull, commit, delete, modify, or automatically approve repository changes.

BranchRift was formerly released as Repo Preflight. The legacy `preflight` command remains available in v0.2.1 for compatibility.

---

## Why BranchRift?

A normal Git diff answers:

> What changed?

Before integration, teams often need a different question:

> What could make this branch expensive or risky to integrate?

BranchRift combines signals that are normally inspected separately:

- branch topology and divergence;
- ahead / behind counts;
- fast-forward eligibility;
- same-path changes on both sides;
- binary-sensitive collisions;
- Git LFS readiness;
- exact conservative text-change facts;
- repository ownership;
- ownership gaps and boundary crossings;
- technical-risk signals;
- required verification;
- focused manual-review paths.

For Unreal Engine teams using Git and Git LFS, one common example is:

> Two branches modified the same `.umap`.

BranchRift surfaces that overlap before integration without pretending it can semantically inspect Unreal binary assets.

---

## Quick start

Install with `pipx`:

```bash
pipx install branchrift
```

Or:

```bash
pip install branchrift
```

Then run inside a Git repository:

```bash
branchrift --base main
```

No configuration file is required.

BranchRift can run in **zero-config mode** and still analyze:

- topology;
- divergence;
- collisions;
- file classification;
- technical risk;
- exact change facts;
- Git LFS readiness;
- required verification;
- manual-review candidates.

Analyze another fetched revision without checking it out:

```bash
branchrift --base main --head origin/feature/environment-pass
```

Produce JSON:

```bash
branchrift --base main --json
```

---

## Optional ownership policy

Ownership configuration is optional.

If you want ownership and governance analysis, create `.preflight.json` in the repository root:

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

Then run normally:

```bash
branchrift --base main
```

BranchRift discovers the default `.preflight.json` from the **Git repository root**, even when launched from a nested directory.

For example:

```text
repo/
├── .preflight.json
└── Source/
    └── Game/
```

Running BranchRift from `Source/Game/` still discovers:

```text
repo/.preflight.json
```

You can also request a specific configuration explicitly:

```bash
branchrift --base main --config /path/to/preflight.json
```

Explicit config paths are strict.

If an explicitly requested config file is missing or invalid, BranchRift exits with a configuration error.

---

## Zero-config ownership semantics

BranchRift distinguishes between:

```text
ownership policy not configured
```

and:

```text
ownership policy configured, but no rule matched this path
```

These are not the same condition.

When ownership is not configured:

- analysis still runs;
- no synthetic `OWNERSHIP_GAP` is created;
- governance is not falsely escalated;
- missing configuration does not force manual review;
- reports explicitly say ownership governance was not evaluated.

When ownership is configured and a changed path matches no rule:

```text
NO_MATCH
```

is a real ownership gap.

This distinction is represented explicitly in structured output.

---

## Ownership matching

BranchRift currently resolves one effective owner per path.

### Prefix rule

```json
{
  "match": "prefix",
  "path": "src/payment/",
  "owner": "Payments"
}
```

A prefix owns a repository subtree.

Prefix matching is path-segment aware.

For example:

```text
src
```

matches:

```text
src/app.py
```

but not:

```text
src2/app.py
```

### Exact-path rule

```json
{
  "match": "path_exact",
  "path": "Dockerfile",
  "owner": "Platform"
}
```

When multiple rules match:

1. the most-specific path wins;
2. an exact-path rule wins over an equivalent prefix rule.

A `default_owner` may also be configured.

---

## What BranchRift reports

### Revision topology

BranchRift resolves the requested revisions and reports:

- requested base;
- requested head;
- resolved SHAs;
- merge-base;
- ahead count;
- behind count;
- topology relationship;
- fast-forward eligibility.

Possible relationships include:

```text
SAME
LINEAR
HEAD_BEHIND
DIVERGED
```

---

### Same-path collisions

A collision means the same repository path changed independently on both sides since the merge-base.

Conceptually:

```text
merge-base → base changed path X
merge-base → head changed path X
```

Therefore:

```text
path X = same-path collision
```

This does **not** mean BranchRift claims Git will definitely produce a textual merge conflict.

It is an integration-review signal.

---

### Binary-sensitive files

Files classified as `asset` or `map` are treated as binary-sensitive.

For Unreal projects this includes:

```text
.uasset
.umap
```

A same-path collision involving one of these files is highlighted as binary-sensitive.

BranchRift does not inspect the internal semantics of `.uasset` or `.umap` files.

---

### Git LFS readiness

BranchRift can inspect Git LFS state for relevant changed files.

Possible states include:

```text
hydrated
pointer
missing
unknown
not LFS-managed
```

When the analyzed revision is the current checkout, BranchRift can use working-tree state to determine readiness.

When analyzing another revision through `--head`, BranchRift does not incorrectly reuse current-checkout hydration state.

If readiness cannot be established safely, it reports uncertainty instead.

Git LFS itself is optional.

---

### Exact change facts

For text diffs, BranchRift can extract conservative facts such as:

```text
line_added
line_removed
value_changed
```

These are literal observations from the Git diff.

They are not AST analysis and do not claim application-level meaning.

Binary assets and maps do not produce fake internal change facts.

---

### Technical risk

BranchRift separates technical risk from governance.

Examples of signals include:

- source changes;
- build/config changes;
- maps;
- assets;
- deletions;
- renames;
- copies.

Technical risk is reported independently from repository ownership policy.

---

### Required verification

Changed file types can produce targeted verification requirements such as:

```text
build verification
asset verification
map integration verification
build/config verification
reference verification
```

BranchRift does not claim the change is correct.

It makes the required verification explicit.

---

## Governance

Ownership governance is evaluated only when ownership policy is configured.

Internally, policy state is explicit:

```text
not_configured
configured_empty
configured
```

Per-path ownership state is also explicit:

```text
known
not_configured
no_match
```

A configured ownership policy with an unmatched changed path can produce:

```text
OWNERSHIP_GAP
```

A confirmed rename across two known owners can produce:

```text
OWNERSHIP_BOUNDARY_CROSSING
```

Ownership boundary crossings are treated as critical governance information.

Governance remains advisory and does not automatically block the repository.

---

## Example terminal output

```text
=== BranchRift ===

Analyzed:
  Base: main
  Head: HEAD
  Current branch: feature/environment-pass
  Repository state: CLEAN

What changed:
  14 files changed
  Technical risk: MEDIUM
  High risk: 0
  Medium risk: 14
  Low risk: 0

Integration:
  Topology: DIVERGED
  Fast-forward eligible: no
  Ahead: 7
  Behind: 4
  Same-path collisions: 2
  Binary-sensitive collisions: 1
    - Content/Maps/L_Main.umap [map, BINARY-SENSITIVE]
    - Source/Game/Inventory.cpp [source]

Governance:
  PASS

Required verification:
  - build verification
  - map integration verification

  Manual review: 2 files
    - Content/Maps/L_Main.umap
    - Source/Game/Inventory.cpp
```

Without ownership configuration, governance output is explicit:

```text
Governance:
  Ownership policy: not configured
  Evaluation: not evaluated
```

---

## JSON output

Use:

```bash
branchrift --base main --json
```

Public reports include:

```json
{
  "schema_version": "1.0"
}
```

Ownership results are structured:

```json
{
  "ownership": {
    "status": "known",
    "owner": "Backend"
  }
}
```

Zero-config ownership is represented as:

```json
{
  "ownership": {
    "status": "not_configured",
    "owner": null
  }
}
```

Structured governance makes evaluation state explicit:

```json
{
  "governance": {
    "evaluation_status": "not_evaluated",
    "ownership_policy_status": "not_configured",
    "issues": []
  }
}
```

The legacy `owner` field and `governance_status` remain available in v0.2.1 for compatibility.

JSON output contains the complete report even when interactive terminal sections are intentionally bounded.

---

## File classification

Default semantic file types include:

```text
source
asset
map
build_config
other
```

Examples:

### Source

```text
.py
.c
.cpp
.h
.hpp
.cs
.js
.ts
.java
.go
.rs
```

### Assets

```text
.uasset
.fbx
.blend
```

### Maps

```text
.umap
```

### Build/config

Examples include:

```text
Dockerfile
Makefile
CMakeLists.txt
Jenkinsfile
Procfile
.github/workflows/
.gradle
```

Classification precedence is:

1. exact filename;
2. most-specific path prefix;
3. extension;
4. fallback `other`.

Custom `file_types` rules replace the defaults.

---

## Dirty worktree

BranchRift reports whether the current worktree is clean or dirty.

```text
Repository state: DIRTY
```

Branch analysis remains revision-based.

Uncommitted changes are not silently mixed into the branch comparison.

---

## Detached HEAD

BranchRift supports SHA-based analysis from detached HEAD checkouts.

A detached checkout is reported as:

```text
DETACHED
```

Topology and comparison logic remain commit-based.

---

## Terminal output

Large manual-review lists are bounded in interactive output.

The full list remains available in JSON.

Repository and configuration-derived terminal text is escaped to avoid control-character injection.

Unicode Git output is decoded as UTF-8.

If the active terminal cannot represent a character, BranchRift escapes it deterministically instead of crashing.

---

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Analysis completed successfully |
| `2` | Configuration error |
| `3` | Git / repository / revision error |
| `4` | Known BranchRift domain error |

A completed analysis still returns `0` when it discovers:

- high technical risk;
- critical governance;
- collisions;
- a dirty worktree;
- manual-review requirements.

BranchRift is advisory in v0.2.1.

---

## Safety model

BranchRift is intentionally read-only.

It:

- never uses `shell=True`;
- passes Git arguments as argument lists;
- validates Git revision arguments;
- checks Git return codes;
- applies Git operation timeouts;
- disables external diff helpers where appropriate;
- disables textconv during diff inspection;
- disables fsmonitor hooks during worktree inspection;
- escapes terminal control characters;
- does not execute commands from `.preflight.json`;
- does not require API keys;
- does not require credentials;
- does not require network access for normal analysis;
- never merges;
- never checks out a revision;
- never commits;
- never deletes repository data;
- never modifies analyzed repository files.

See [`SECURITY.md`](SECURITY.md) for security reporting.

---

## Requirements

- Python 3.10+
- Git available on `PATH`

Runtime dependencies:

- Python standard library only

Git LFS is optional.

---

## Development

Clone:

```bash
git clone https://github.com/Kaan081/branchrift.git
cd branchrift
```

Install editable:

```bash
python -m pip install -e .
```

Install development dependencies:

```bash
python -m pip install -e '.[dev]'
```

Run tests:

```bash
python -m pytest -q
```

---

## Current scope

BranchRift intentionally does **not** provide:

- AST-level semantic analysis;
- dependency-graph reasoning;
- automatic merge-conflict resolution;
- guaranteed Git conflict prediction;
- semantic inspection inside `.uasset` or `.umap`;
- rename-aware collision identity;
- multiple simultaneous co-owners for one path;
- automatic repository modification;
- automatic merge approval.

The project prefers conservative facts over unsupported conclusions.

---

## Project status

Current release: **0.2.1**

BranchRift is an early-stage developer tool focused on real-repository validation.

Current priorities include:

- false-positive reduction;
- false-negative discovery;
- Git/LFS edge cases;
- integration-workflow feedback;
- Unreal/Git team validation;
- onboarding and packaging.

Feedback backed by a real repository or workflow problem is especially useful.

---

## Feedback

Useful questions when testing BranchRift:

1. Were same-path collisions useful or noisy?
2. Were binary-sensitive warnings actionable?
3. Did ownership resolution match the real repository?
4. Did Git LFS readiness reflect the actual checkout?
5. Were required checks useful?
6. Did the manual-review shortlist save time?
7. Did BranchRift fail on a valid Git workflow?
8. What would stop you from running it again?

Please do not publish secrets, credentials, private repository contents, or sensitive company information.

General feedback:

https://github.com/Kaan081/branchrift/issues

Security-sensitive reports should follow [`SECURITY.md`](SECURITY.md).

---

## Contributing

Issues, tests, documentation improvements, focused rule changes, and small pull requests are welcome.

Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before larger changes.

Ideas backed by real repository or workflow problems are preferred over speculative feature expansion.

---

## License

BranchRift is released under the MIT License.

See [`LICENSE`](LICENSE).