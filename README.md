# Repo Preflight

[![PyPI](https://img.shields.io/pypi/v/repo-preflight.svg)](https://pypi.org/project/repo-preflight/)
[![Python](https://img.shields.io/pypi/pyversions/repo-preflight.svg)](https://pypi.org/project/repo-preflight/)
[![Tests](https://github.com/Kaan081/repo-preflight/actions/workflows/tests.yml/badge.svg)](https://github.com/Kaan081/repo-preflight/actions/workflows/tests.yml)
[![License](https://img.shields.io/github/license/Kaan081/repo-preflight.svg)](LICENSE)

**See branch divergence, same-path collisions, ownership gaps, and Git LFS readiness before integration — without modifying your repository.**

Repo Preflight is a read-only Git CLI for developers and small teams that want a repeatable integration check before merging, promoting, or reviewing a branch.

It answers questions such as:

- Did the base and feature branch diverge?
- Can this branch still fast-forward?
- Did both sides modify the same repository path?
- Is that collision a binary-sensitive `.uasset` or `.umap`?
- Are Git LFS-managed files actually ready in the current checkout?
- Did a change cross an ownership boundary?
- Which changed files deserve manual review?
- Which verification steps should happen before integration?

Repo Preflight is intentionally advisory.

It does **not** merge, checkout, pull, commit, delete, modify, or automatically approve repository changes.

## Demo

> Illustrative scenario based on verified Repo Preflight v0.1.9 behavior and output format.

<img width="960" height="540" alt="repo_preflight_v019_demo_preview" src="https://github.com/user-attachments/assets/3aa4ed11-b34e-42cd-aeda-bb4573a0b164" />


The demo shows a reproducible integration scenario with branch divergence, a same-path binary-sensitive Unreal map collision, Git LFS readiness, and required verification — without modifying the repository.

---

## Why this exists

A normal Git diff tells you what changed.

Before integration, teams often need a different view:

> **What could make this branch expensive or risky to integrate?**

Repo Preflight combines several signals that are normally inspected separately:

- Git topology;
- same-path changes on both sides of a branch;
- binary-sensitive files;
- Git LFS readiness;
- repository ownership;
- governance gaps;
- technical-risk signals;
- required verification;
- focused manual-review paths.

For Unreal Engine teams using Git and Git LFS, one especially useful case is simple:

> **Two branches touched the same `.umap`. Know before you integrate.**

Repo Preflight does not replace Git, Git LFS, file locking, code review, CI, or your source-control workflow.

It adds a read-only pre-integration view on top of them.

---

## Quick start

Install with `pipx`:

```bash
pipx install repo-preflight
```

Or with `pip`:

```bash
pip install repo-preflight
```

Create `.preflight.json` in the repository root:

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

---

## Example: catch integration risk before merge

A report can surface a divergent branch, a same-path Unreal map collision, and LFS readiness in one run:

```text
=== Repository Preflight ===
Analyzed:
  Base: main
        0123456789abcdef0123456789abcdef01234567
  Head: HEAD
        fedcba9876543210fedcba9876543210fedcba98
  Merge base: abcdefabcdefabcdefabcdefabcdefabcdefabcd
  Comparison: abcdefabcdefabcdefabcdefabcdefabcdefabcd...fedcba9876543210fedcba9876543210fedcba98
  Head is current checkout: yes
  Current branch: feature/environment-pass
  Repository state: CLEAN

What changed:
  14 files changed
  Technical risk: MEDIUM
  High risk: 0
  Medium risk: 14
  Low risk: 0
  Git status mix: M=2, A=12
  File types: source=1, asset=12, map=1
  Owners: Code=1, Content=13

  Source/config:
    Source/Game/Inventory.cpp

  Binary:
    Content/Maps/L_Main.umap

Repository readiness:
  Content/Maps/L_Main.umap
    LFS-managed: yes
    State: pointer
    Readiness: attention

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
  - map integration verification
  - build verification
  Manual review: 2 files
    - Content/Maps/L_Main.umap
    - Source/Game/Inventory.cpp
```

A **collision** means the same repository path changed on both sides since the merge-base.

It does **not** mean Repo Preflight is claiming that Git will definitely produce a textual merge conflict.

For binary files such as `.uasset` and `.umap`, Repo Preflight marks the overlap as **BINARY-SENSITIVE** instead of pretending it can inspect their internal semantics.

---

## What Repo Preflight reports

Repo Preflight currently reports:

- requested base and head revisions;
- resolved commit SHAs;
- merge-base;
- ahead/behind counts;
- topology relationship;
- fast-forward eligibility;
- same-path branch collisions;
- binary-sensitive asset/map collisions;
- conservative exact text change facts;
- Git LFS state;
- working-tree readiness;
- configurable repository ownership;
- ownership gaps;
- ownership-boundary crossings;
- technical-risk signals;
- required verification checks;
- focused manual-review paths;
- dirty working-tree state;
- revision provenance;
- human-readable terminal output;
- deterministic JSON output.

---

## Design principles

Repo Preflight is deliberately:

- **read-only** — it never mutates the repository;
- **conservative** — it does not invent semantics it cannot prove;
- **explicit** — topology, provenance, readiness, and uncertainty are visible;
- **automation-friendly** — terminal and JSON output are both supported;
- **Git-native** — it works with an existing Git workflow instead of replacing source control;
- **focused** — it prioritizes integration signals instead of trying to become a universal repository analyzer.

---

## Requirements

- Python 3.10+
- Git available on `PATH`

Runtime dependencies:

- Python standard library only

Git LFS is optional.

When Git LFS is unavailable, source-only analysis can still complete, while LFS-specific information may become unknown.

---

## Installation

Recommended isolated CLI installation:

```bash
pipx install repo-preflight
```

Standard Python installation:

```bash
pip install repo-preflight
```

Verify:

```bash
preflight --help
```

---

## Install for development

Clone the repository:

```bash
git clone https://github.com/Kaan081/repo-preflight.git
cd repo-preflight
```

Install in editable mode:

```bash
python -m pip install -e .
```

Install test dependencies:

```bash
python -m pip install -e '.[dev]'
```

Run the suite:

```bash
python -m pytest -q
```

---

## Configuration

Repo Preflight reads repository policy from `.preflight.json` by default.

A minimal configuration requires ownership rules:

```json
{
  "ownership": [
    {
      "match": "prefix",
      "path": "src/",
      "owner": "Backend"
    },
    {
      "match": "path_exact",
      "path": "Dockerfile",
      "owner": "Platform"
    }
  ]
}
```

`ownership` is required.

Governance thresholds and default file-type rules are provided automatically unless overridden.

You can also use a config file elsewhere:

```bash
preflight --base main --config /path/to/preflight.json
```

---

## Ownership matching

A repository can contain many ownership rules.

Each changed path resolves to one effective owner.

### Prefix ownership

A `prefix` rule owns a repository subtree:

```json
{
  "match": "prefix",
  "path": "src/payment/",
  "owner": "Payments"
}
```

### Exact-path ownership

A `path_exact` rule owns one repository-relative path:

```json
{
  "match": "path_exact",
  "path": "Dockerfile",
  "owner": "Platform"
}
```

When multiple ownership rules match:

1. the most-specific path wins;
2. an exact-path rule wins over an equivalent prefix rule.

Prefix matching is path-segment aware.

For example:

```text
src
```

matches:

```text
src/app.py
```

but does not match:

```text
src2/app.py
```

Equivalent prefix spellings such as:

```text
src
src/
src\
```

are canonicalized consistently.

An unmatched path becomes `Unknown`.

Analysis continues, but the path is reported as an ownership governance gap.

> Repo Preflight currently resolves one effective owner per path. Multiple simultaneous co-owners are not modeled.

---

## Running Repo Preflight

Compare the current checked-out revision against `dev`:

```bash
preflight --base dev
```

Compare against `main`:

```bash
preflight --base main
```

Analyze another fetched branch without checking it out:

```bash
preflight --base main --head origin/feature/my-change
```

Use an explicit configuration file:

```bash
preflight --base main --config /path/to/preflight.json
```

Produce machine-readable JSON:

```bash
preflight --base main --json
```

---

## Revision topology

Repo Preflight resolves both revisions to commit SHAs and reports their relationship.

Possible topology relationships include:

- `SAME`
- `LINEAR`
- `HEAD_BEHIND`
- `DIVERGED`

The report also includes:

- ahead count;
- behind count;
- merge-base;
- fast-forward eligibility.

Example:

```text
Integration:
  Topology: DIVERGED
  Fast-forward eligible: no
  Ahead: 7
  Behind: 4
```

This is advisory information.

Repo Preflight does not automatically merge or block the branch.

---

## Same-path collisions

A collision means that the **same repository path** changed independently on both sides since the merge-base.

Conceptually:

```text
merge-base -> base side changed path X
merge-base -> head side changed path X
```

then:

```text
path X = collision
```

Example:

```text
Integration:
  Same-path collisions: 2
  Binary-sensitive collisions: 1
    - Content/Maps/L_Main.umap [map, BINARY-SENSITIVE]
    - src/app.py [source]
```

A collision is **not** a prediction that Git must produce a merge conflict.

It is an integration-review signal.

### Binary-sensitive collisions

Files classified as `asset` or `map` are treated as binary-sensitive.

For Unreal projects this includes:

- `.uasset`
- `.umap`

Repo Preflight does not claim to inspect semantic changes inside these files.

### Rename behavior

Collision detection is intentionally path-based and uses path-string overlap.

It does not currently model rename identity when calculating same-path collisions.

---

## Exact change facts

Repo Preflight can extract conservative facts from text diffs.

These facts are literal observations from the merge-base unified diff.

They are **not** semantic code analysis.

A `value_changed` fact is recorded only when one removed line and one added line assign the same key to different scalar values.

Other meaningful text changes can appear as:

- `line_added`
- `line_removed`

For example:

```text
max_players: 4 -> 8
```

Repo Preflight intentionally avoids pretending to understand what that change means to the application.

### Binary files

Binary diffs and files classified as `asset` or `map` do not produce internal change facts.

Repo Preflight does not claim to inspect internal Unreal asset/map contents.

### Git LFS pointer metadata

A valid Git LFS pointer contains transport metadata such as:

```text
version
oid
size
```

When the changed content is itself a valid LFS pointer, those transport lines are not reported as meaningful exact change facts.

Ordinary source text that happens to contain words such as `size` or `oid` is not suppressed.

---

## Binary and Git LFS readiness

Asset and map changes receive readiness information.

A changed path managed by Git LFS can also receive a readiness record even when its semantic file type remains `other`.

For example, `.wav` is not classified as an asset by default, but it can still receive LFS readiness information if Git attributes identify it as LFS-managed.

Example:

```text
Repository readiness:
  Content/Maps/L_Main.umap
    LFS-managed: yes
    State: hydrated
    Readiness: ready
```

Possible states can include:

- hydrated;
- pointer;
- missing;
- unknown;
- not LFS-managed.

### Current checkout

When the analyzed revision is the current checkout, Repo Preflight can use working-tree state and Git LFS information to determine readiness.

A hydrated LFS file can be reported as ready.

A pointer left in the working tree can require attention.

### Historical or non-current revisions

When `--head` is not the currently checked-out commit, Repo Preflight does not incorrectly apply current working-tree hydration state to that historical revision.

Instead, readiness can become:

```text
unknown
```

with the reason:

```text
analyzed_head_not_current_checkout
```

This is intentional.

The tool prefers explicit uncertainty over a misleading conclusion.

---

## Detached HEAD support

Repo Preflight supports SHA-based analysis from detached HEAD checkouts.

A detached checkout is reported as:

```text
DETACHED
```

Topology, collisions, change facts, provenance, and revision analysis remain commit/SHA based.

This is useful for environments where a branch name is not available, including some CI workflows.

---

## Revision provenance

Every report records which revisions were actually analyzed.

This includes:

- requested base;
- resolved base SHA;
- requested head;
- resolved head SHA;
- merge-base SHA;
- comparison range;
- whether the analyzed head is the current checkout.

Example:

```text
Analyzed:
  Base: main
        0123456789abcdef0123456789abcdef01234567
  Head: origin/feature/test
        fedcba9876543210fedcba9876543210fedcba98
  Merge base: abcdefabcdefabcdefabcdefabcdefabcdefabcd
  Comparison: abcdefabcdefabcdefabcdefabcdefabcdefabcd...fedcba9876543210fedcba9876543210fedcba98
  Head is current checkout: no
```

This makes the report auditable and avoids ambiguity about which repository state produced a result.

---

## Dirty working tree

Repo Preflight reports whether the current worktree is clean or dirty.

Example:

```text
Repository state: DIRTY
Warning: uncommitted changes are not included in the branch diff.
```

The branch analysis remains revision-based.

A dirty worktree is reported as context rather than silently mixed into the comparison.

---

## Redirecting JSON output

JSON output is available with:

```bash
preflight --base main --json
```

If shell redirection creates the output file **inside the repository**:

```bash
preflight --base main --json > report.json
```

the shell creates `report.json` before Repo Preflight begins.

The repository may therefore correctly appear as `DIRTY`.

Redirect outside the inspected repository if you need the worktree state to remain unchanged.

---

## Git command timeouts

Git operations have timeout budgets based on expected cost.

| Operation class | Budget | Examples |
| --- | ---: | --- |
| fast | 15s | revision lookup, current branch, merge-base |
| normal | 30s | name-status, worktree status, `check-attr` |
| expensive | 90s | unified diff, collision scan, `git lfs ls-files` |

A timeout becomes a `GitError`.

Repo Preflight does not silently return a partial report after a Git timeout.

---

## UTF-8 and terminal output

Git stdout and stderr are decoded as UTF-8 on Windows and Linux.

This avoids relying on the Windows ANSI code page for Git output.

Valid Unicode text such as:

```text
—
→
çağrı
İstanbul
```

is preserved internally.

If the active terminal encoding cannot represent a character, Repo Preflight escapes that character deterministically at the output boundary instead of crashing.

For example:

```text
→
```

can become:

```text
\u2192
```

on a limited terminal encoding.

JSON output keeps normal `json.dumps` escaping behavior.

---

## Bounded terminal output

Large repositories can produce long manual-review lists.

Terminal output therefore shows at most 20 manual-review paths.

For example:

```text
Manual review: 57 files
  - path/one
  - path/two
  ...
  ... 37 more paths omitted
```

The full list is still available in JSON output.

This keeps interactive output readable without discarding machine-readable information.

---

## File classification

Default semantic file types include:

- `source`
- `asset`
- `map`
- `build_config`
- fallback `other`

Default examples include:

### Source

Extensions such as:

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
4. `other`.

Custom `file_types` rules replace the defaults.

---

## Governance

Repo Preflight separates technical risk from governance state.

Default governance configuration:

```json
{
  "critical_escalation": true,
  "critical_unknown_count": 5,
  "critical_unknown_ratio": 0.25
}
```

Ownership gaps initially produce:

```text
ATTENTION
```

When configured count/ratio thresholds are crossed, governance can escalate.

A confirmed ownership-boundary crossing is treated as critical governance information.

Governance status does not automatically block the repository.

Repo Preflight remains advisory.

---

## Required verification

Changed file types can produce targeted verification requirements.

Examples include:

```text
build verification
asset verification
map integration verification
```

The goal is not to claim that a change is correct.

The goal is to make the required human or automated verification explicit.

---

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Analysis completed successfully |
| `2` | Configuration error |
| `3` | Git/repository/revision error |
| `4` | Known Repo Preflight domain error |

A completed analysis still returns `0` when it discovers:

- high technical risk;
- critical governance;
- collisions;
- a dirty worktree;
- required manual review.

Repo Preflight is advisory in the current release.

---

## Security model

Repo Preflight is intentionally read-only.

The CLI:

- never uses `shell=True`;
- passes Git arguments as an argument list;
- validates user-supplied Git revision arguments;
- checks Git return codes;
- handles Git stderr explicitly;
- applies Git command timeouts;
- disables external diff helpers during diff inspection;
- disables textconv helpers during diff inspection;
- disables fsmonitor hooks during worktree status inspection;
- escapes terminal control characters from repository/config-derived display text;
- does not execute commands from `.preflight.json`;
- does not require API keys;
- does not require credentials;
- does not require network access for normal analysis;
- never merges;
- never checks out a revision;
- never commits;
- never deletes repository data;
- never modifies analyzed repository files.

See [`SECURITY.md`](SECURITY.md) for vulnerability reporting guidance.

---

## JSON output

Use:

```bash
preflight --base main --json
```

JSON output contains the full structured report, including data that may be truncated in terminal presentation.

It is intended for:

- scripts;
- CI experimentation;
- reporting;
- downstream tooling;
- automated inspection.

Repo Preflight does not currently turn risk/governance findings into blocking exit codes.

---

## Validation

Repo Preflight v0.1.9 has been tested across:

- Python 3.10;
- Python 3.11;
- Python 3.12;
- Python 3.13;
- Ubuntu CI;
- Windows CI;
- clean built-wheel installation;
- CLI execution outside the source tree;
- detached HEAD scenarios;
- Git LFS scenarios;
- Unicode/Windows terminal cases;
- rename/copy edge cases;
- large change sets.

The v0.1.9 test suite contains **167 tests**.

The release was also exercised with:

- 10,000 changed files;
- up to 1,000 Git LFS attribute paths.

These checks are validation evidence, not a performance SLA.

---

## Current scope and limitations

Repo Preflight is intentionally narrow.

It currently does **not** provide:

- AST-level semantic analysis;
- language-server analysis;
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

Current release:

```text
0.1.9
```

Repo Preflight is an early-stage developer tool.

The current focus is:

- real-repository validation;
- false-positive reduction;
- false-negative discovery;
- integration-workflow feedback;
- Git/LFS edge cases;
- onboarding and packaging;
- small-team workflows.

Feedback backed by a real repository or workflow problem is especially useful.

---

## Feedback

If you test Repo Preflight on a real repository, useful feedback includes:

1. Were same-path collisions useful or noisy?
2. Were binary-sensitive warnings actionable?
3. Was ownership resolution correct?
4. Did LFS readiness reflect the real repository state?
5. Were required checks useful?
6. Did the manual-review shortlist save time?
7. Did the CLI fail on a valid Git workflow?
8. What would prevent you from running it again?

Please do not publish:

- secrets;
- credentials;
- private repository contents;
- sensitive company information.

Security-sensitive reports should follow [`SECURITY.md`](SECURITY.md).

General feedback can be opened through [GitHub Issues](https://github.com/Kaan081/repo-preflight/issues).

---

## Contributing

Issues, tests, documentation improvements, focused rule changes, and small pull requests are welcome.

Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting a larger change.

Ideas backed by a real repository or workflow problem are preferred over speculative feature expansion.

---

## License

Repo Preflight is released under the MIT License.

See [`LICENSE`](LICENSE).
