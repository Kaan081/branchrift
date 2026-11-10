# BranchRift

> See integration risk before branches come back together.

**BranchRift** is an open-source Git CLI for pre-integration checks: branch divergence, same-path overlaps, Git LFS and Unreal asset readiness, optional merge simulation, and a focused manual-review list. For **trusted Python repositories**, it can optionally run pytest on a temporary merged source snapshot.

**Try a real branch (Python 3.10+; Git 2.38+ for merge simulation):**

```bash
pipx install branchrift
branchrift --base main --head feature/my-change --simulate-merge --json
```

The simulation reports **CLEAN**, **CONFLICTS**, **UNKNOWN**, or **ERROR**, separately from same-path overlaps. For a **trusted** Python repository with installed pytest/dependencies, you can explicitly run:

```bash
branchrift --base main --head feature/my-change --verify-pytest --json
```

This adds a separate pytest result (such as **PASS** or **FAIL**) for the temporary merged tree, so **CLEAN + FAIL** can be reported. It does **not** imply every test will run or reproduce a CI environment.

**Safety:** default analysis is advisory and read-only. Merge simulation does not change your original worktree, but custom Git merge drivers may execute programs. `--verify-pytest` **runs repository code with your permissions** and is **not a sandbox**. Never opt into untrusted code. No automatic merge approval or CI gate is provided.

[Short demonstration](https://github.com/user-attachments/assets/2c032aa3-86f6-44b4-a3fc-86d83c5ecdc7) · [Detailed setup](#quick-start) · [Evidence/limits](#experimental-merged-tree-pytest-verification-v040) · [Feedback](#feedback)

[![PyPI](https://img.shields.io/pypi/v/branchrift.svg)](https://pypi.org/project/branchrift/)
[![Python](https://img.shields.io/pypi/pyversions/branchrift.svg)](https://pypi.org/project/branchrift/)
[![Tests](https://github.com/kaanbartubozkurt/branchrift/actions/workflows/tests.yml/badge.svg)](https://github.com/kaanbartubozkurt/branchrift/actions/workflows/tests.yml)
[![License](https://img.shields.io/github/license/kaanbartubozkurt/branchrift.svg)](LICENSE)

Formerly Repo Preflight; the `preflight` CLI alias remains available.

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

Then run inside a Git repository with a locally recorded default remote HEAD:

```bash
branchrift
```

With no `--base` argument, BranchRift selects the remote-tracking branch recorded
by `origin/HEAD` (or by the only configured remote's HEAD). It does not contact
GitHub or guess a branch name. If Git has no unambiguous local default, it
reports an error instead of silently comparing against the wrong branch.

Use `--base main`, `--base dev`, or another explicit revision to override this.
This changes the previous no-argument default (`dev`); explicit usage is unchanged.

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

By default, the terminal output is a compact summary. For the original
detailed report, use:

```bash
branchrift --base main --verbose
```

For complete machine-readable output (unchanged schema), use:

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

By default, BranchRift prints a bounded, advisory summary:

```text
BranchRift | main <- HEAD
Topology: DIVERGED | ahead 7 / behind 4
Changed: 14 files | manual review: 2
Same-path overlap: 2 | binary-sensitive: 1
Git merge conflict prediction: NOT CHECKED
Change risk: MEDIUM
Attention: 1 binary-sensitive overlaps
Required checks (not run): build verification; map integration verification
Review paths:
  - Content/Maps/L_Main.umap
  - Source/Game/Inventory.cpp
Details: branchrift --verbose | Full data: branchrift --json
```

**Important:** Same-path overlap is not a confirmed Git merge conflict. The listed
verification checks are recommendations; BranchRift has **not** run them.
`--verbose` restores the full sectioned human-readable report.

With `--verbose`, missing ownership configuration is shown explicitly:

```text
Governance:
  Ownership policy: not configured
  Evaluation: not evaluated
```

---

## Experimental Git merge simulation (source-only, opt-in)

Git 2.38 or newer is required for this optional mode:

```bash
branchrift --base main --head feature/x --simulate-merge
branchrift --base main --head feature/x --simulate-merge --verbose
branchrift --base main --head feature/x --simulate-merge --json
```

Without `--simulate-merge`, BranchRift behaves as before and does **not** perform
Git merge simulation. With the option, it uses the resolved base/head commit SHAs
and `git merge-tree --write-tree --name-only -z --no-messages` to return a
`merge_simulation` object in JSON. It does **not** create a merge commit or change
branches, the index, or the working tree. Because `--write-tree` normally creates
Git objects, BranchRift redirects object writes to a temporary object directory
and deletes it after reporting. `result_tree_oid` is therefore an **ephemeral
identifier** and is not guaranteed to be available later in the original repository.

Possible results:

- `CLEAN`: Git could merge the committed changes; **no build or tests were run**.
- `CONFLICTS`: Git reported a real merge conflict (not merely same-path overlap).
- `UNKNOWN`: the Git version or capability could not be confirmed.
- `ERROR`: the simulation failed; no clean/conflict conclusion may be inferred.

`conflicted_paths` lists Git's *unmerged-index* paths. Some conflict kinds are
represented in Git's informational messages instead and may not have a path in
this list; use `status`, not the list length, to decide whether Git found conflicts.
This mode remains **advisory**, and the CLI exit code remains 0 on a completed
analysis even if `merge_simulation.status` is `CONFLICTS`, `UNKNOWN`, or `ERROR`.
CI users must inspect the structured status explicitly; no merge gate is provided.

**Security boundary:** Git may honor configured external/custom merge drivers.
Only opt in for repositories you trust. The feature does not run build tools or
arbitrary commands from BranchRift config, but Git's own merge configuration
may still execute external programs. Worktree/index isolation does not imply a
sandbox for malicious merge drivers.

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

The legacy `owner` field and `governance_status` remain available for compatibility.

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

## Experimental merged-tree pytest verification (v0.4.0)

For **trusted repositories only**, explicitly request a merged-tree pytest run:

```bash
branchrift --base main --head feature/my-change --verify-pytest
branchrift --base main --head feature/my-change --verify-pytest --json
```

`--verify-pytest` implies `--simulate-merge` and does **not** run by default.
If Git reports `CLEAN`, BranchRift reconstructs the merged Git tree in a temporary
folder using a temporary index and object store, runs the active Python
interpreter's `python -m pytest -q -p no:cacheprovider` there, and removes the
folder when finished. No `git checkout`, `git merge`, package installation,
or commit is applied to the original working tree. Git LFS automatic smudge is
skipped during export; existing Python dependencies are assumed installed.

The JSON `merge_simulation.status` continues to mean **Git merge status**, not
test status. With `--verify-pytest`, `merge_simulation.verification.status` adds:

- `PASS`: pytest exited 0 on the merged snapshot; this only proves the tests that ran passed.
- `FAIL`: pytest returned its normal test-failure exit code 1.
- `NOT_RUN`: merge conflicts, no tests collected, unsupported tree entries
  (symlinks/submodules), or tests skipped for another reason.
- `ERROR`: checkout or pytest infrastructure/configuration failed.
- `TIMEOUT`: test run exceeded the bounded time budget (currently 300 seconds).

The report includes the base/head SHAs, temporary merge tree OID, test command,
exit code, duration and bounded stdout/stderr tails. This release adds recorded UTC
time, interpreter version/implementation, installed pytest distribution version,
OS details, and SHA-256 fingerprints of **all output bytes observed** by the
capture threads (not merely the retained tails). Full stream lengths, truncation
flags and completeness status remain explicit. For `--verify-pytest`, the nested
`verification.provenance` binds the base/head SHAs and temporary merged tree OID;
`NOT_RUN` evidence is never evidence of an executed test. The result tree itself is
not retained. `CLEAN + FAIL` is possible and is **not** a Git conflict. The CLI
remains advisory and does not fail CI automatically when tests fail; inspect
`merge_simulation.verification.status` in JSON for gating.

**Security:** running pytest executes repository-supplied Python code with your
user's normal permissions. This is **not a sandbox**, even though files are
materialized into a temporary directory. Git checkout filters and custom merge
drivers may also execute external programs. Do not use this option on untrusted
repositories; use an externally isolated runner/CI for untrusted code.

This first implementation is Python/pytest-only. It does not install dependencies,
validate other build systems, prove test coverage, run an Unreal build, or verify
runtime behavior outside the executed tests.

---

## Verification hardening (experimental)

The opt-in pytest runner now drains output while retaining bounded stdout/stderr
**tails in memory**, with `stdout_bytes_seen`, `stderr_bytes_seen` and explicit
`stdout_truncated` / `stderr_truncated` evidence. This limits BranchRift's
output capture, **not** the amount of output the test code could produce
elsewhere.

Pytest runs in a separate process group on POSIX. When its deadline is hit,
BranchRift attempts to terminate that group. On Windows it attempts
`taskkill /PID ... /T /F` and falls back to killing the immediate process.
This is **best effort only**: a detached descendant may survive and have side
effects. JSON records `process_tree_cleanup: attempted_not_guaranteed` on a
timeout. A pytest process that exits but leaves output streams open yields
`ERROR`, never `PASS`. The temporary merged checkout is **not a security sandbox**.

The test command is unchanged (`python -m pytest -q -p no:cacheprovider`) and
its normal timeout remains 300 seconds. Pytest still uses the active Python
environment, disables autoloaded third-party plugins, and verifies only tests
that actually execute. Build verification and arbitrary external commands are
not part of this feature. No new dependencies are installed.

## Evidence integrity (v0.4.0)

Pytest stdout/stderr SHA-256 digests are computed incrementally over the bytes
actually read from each stream. A digest plus observed byte count can help detect
changed or incomplete output when comparing saved reports, but **is not a digital
signature** and does not prove that tests were correct or code was safe. If output
streams are incomplete, pytest verification is `ERROR`, not `PASS`, and the
hash describes only observed bytes. `stdout_tail`/`stderr_tail` may contain
repository-supplied sensitive values: review before sharing reports publicly.

Platform and pytest package metadata describe the local interpreter at execution
time, not a hermetic environment. The report explicitly states
`dependency_lock_verified: false` and `environment_reproducible: false`. No
reproduction guarantee, package dependency hashing, or build verification exists.
This is still trusted-repository-only execution, **not** a sandbox.

---

## Merged-source import precedence (v0.4.0)

For opt-in merged-tree pytest runs, BranchRift puts the **temporary merged
checkout's** `src/` directory (when present) ahead of its repository root on
the child Python process's `PYTHONPATH`. For flat-layout projects, only the
merged checkout root is used. The caller's `PYTHONPATH` stays excluded.
This prevents common `src/` packages from accidentally resolving to another
editable/site-installed checkout merely because the temporary checkout wasn't
on Python's import path. No package installation or dependency resolution occurs.

JSON records `verification.source_import_precedence` as `merged_src_then_root`,
`merged_root`, or `not_run`. This is a **path precedence declaration**, not proof
that every imported dependency/module came from the intended snapshot: custom
import hooks, unusual layouts and test code may override normal import behavior.
Only tests actually exercised are covered. For trustworthy project acceptance,
check test collection, skip reasons, and the applicable dependency environment.
Earlier development-build `PASS` reports for `src/` layout projects need revalidation.

---

## Terminal output

The default CLI output is a short advisory summary with at most three review paths
and up to three recommended checks. It never claims to have executed those checks.
Use `--verbose` for the previous detailed report or `--json` for complete structured
data (including full review lists).

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

BranchRift remains advisory; reporting high risk does not change the exit status.

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
git clone https://github.com/kaanbartubozkurt/branchrift.git
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

Published versions: [PyPI](https://pypi.org/project/branchrift/) and
[GitHub Releases](https://github.com/kaanbartubozkurt/branchrift/releases).
The source tree may contain changes not yet published.

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

https://github.com/kaanbartubozkurt/branchrift/issues

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