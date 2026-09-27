# Repo Preflight

Repo Preflight is a read-only Git CLI that turns a branch diff into an integration-focused report: **ownership, technical risk, governance gaps, required checks, and a focused manual-review list**.

It is designed for small teams and solo developers who want a repeatable pre-merge or pre-integration check without giving the tool permission to modify the repository.

## What it does

Repo Preflight can:

- compare a base revision against `HEAD` or another fetched revision;
- classify changed files using exact names, path prefixes, and extensions;
- resolve repository ownership with `prefix` and `path_exact` rules;
- flag ownership gaps and ownership-boundary crossings;
- separate technical risk from governance status;
- emit required verification checks;
- produce a focused manual-review list instead of treating every changed file equally;
- warn when the working tree is dirty;
- report how the analyzed head relates to the base revision (ahead/behind, merge-base, relationship, and fast-forward eligibility);
- report same-path collisions since the merge-base as a separate advisory signal;
- output human-readable text or deterministic JSON.

It **does not** merge, checkout, commit, delete, modify, or automatically approve repository changes.

## Example

```text
=== Repository Preflight ===
Current branch: dev
Base: dev
Head: origin/feature/environment-pass
Repository state: CLEAN

Topology:
Base SHA: 0123456789abcdef0123456789abcdef01234567
Head SHA: fedcba9876543210fedcba9876543210fedcba98
Merge base: 0123456789abcdef0123456789abcdef01234567
Behind: 0
Ahead: 3
Relationship: LINEAR
FF eligible: YES

Collisions:
Count: 0
Binary-sensitive: 0
- None

Technical risk: MEDIUM
Governance: PASS

Changed files: 14
High risk: 0
Medium risk: 14
Low risk: 0
Manual reviews: 1
Git status mix: A=13, M=1
File types: asset=13, map=1
Owners: Art=13, Shared=1

Required checks:
- asset verification
- map integration verification

Manual review:
- Content/Maps/Level_Art.umap

Governance issues:
- None
```

## Requirements

- Python 3.10+
- Git available on `PATH`

Runtime dependencies: none outside the Python standard library.

## Install

Install from PyPI:

```bash
pip install repo-preflight
```

For isolated CLI installation with pipx:

```bash
pipx install repo-preflight
```


## Install for development

Clone the repository and run:

```bash
python -m pip install -e .
```

Verify the CLI:

```bash
preflight --help
```

Install test dependencies and run the suite:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

## Minimal configuration

Create `.preflight.json` in your repository root:

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

`ownership` is required. Governance thresholds and file-type rules have defaults.

## Ownership matching

A repository can contain **many ownership rules**. Each changed path resolves to one effective owner.

A `prefix` rule owns a path subtree:

```json
{"match": "prefix", "path": "src/payment/", "owner": "Payments"}
```

A `path_exact` rule owns one exact repository-relative path:

```json
{"match": "path_exact", "path": "Dockerfile", "owner": "Platform"}
```

When several rules match, the most specific rule wins. An exact-path rule wins over an equivalent prefix rule.

Prefix matching is path-segment aware. For example, a rule for `src` matches `src/app.py` but not `src2/app.py`. Equivalent prefix spellings such as `src`, `src/`, and `src\\` are the same ownership rule.

An unmatched path becomes `Unknown`. Analysis continues and the path is reported as an ownership governance gap.

> Current ownership resolution returns one effective owner per path. Multiple co-owners for the same path are not modeled.

## Run

Compare the current checked-out revision against `dev`:

```bash
preflight --base dev
```

Analyze a fetched branch without checking it out:

```bash
preflight --base dev --head origin/feature/my-change
```

Use a config outside the repository:

```bash
preflight --base main --config /path/to/preflight.json
```

Machine-readable output:

```bash
preflight --base main --json
```

If JSON is redirected into a file inside the inspected repository, the shell creates that file before Repo Preflight starts, so the working tree can correctly appear as `DIRTY`. Redirect outside the repository if you want an unchanged worktree state.

## Exact change facts

Change facts are taken from the merge-base unified diff. They are literal diff observations, not an interpretation of what the change means.

- A `value_changed` fact is recorded only when one removed line and one added line assign the same key to different scalar values.
- Other meaningful lines are `line_added` or `line_removed`.
- Binary diffs, and files classified as `asset` or `map`, do not produce change facts. Repo Preflight does not claim internal changes inside `.uasset` or `.umap` files.

## Binary and LFS readiness

Asset and map changes get a readiness record:

- `lfs_managed` comes from `git check-attr` on the analyzed head. When that head is the current checkout, `git lfs ls-files` can confirm it.
- A hydrated LFS file at the current checkout is `ready`. An LFS pointer left in the worktree needs attention.
- When `--head` is not the current checkout, working-tree hydration is not consulted. Readiness is `unknown`, LFS state is `unknown`, and the reason is `analyzed_head_not_current_checkout`.
- If `git lfs` is not installed, LFS name lookup becomes unknown. Source-only analysis still completes.

## Revision provenance

Each report records the requested base and head, their resolved SHAs, the merge-base, the comparison `merge-base...head`, and whether the analyzed head is the commit currently checked out.

## Git command timeouts

Git commands use a budget by operation class:

| Class | Budget | Examples |
| --- | ---: | --- |
| fast | 15s | revision lookup, current branch, merge-base |
| normal | 30s | name-status, worktree status, check-attr |
| expensive | 90s | unified diff, collision scan, `git lfs ls-files` |

A timeout is a `GitError` that names the operation and the budget. It does not return a partial report.

## UTF-8 Git output

Git stdout and stderr are decoded as UTF-8 on Windows and Linux. Decoding does not follow the Windows ANSI code page, so valid UTF-8 text such as `—` (U+2014) survives. If Git returns no stdout, Repo Preflight raises `GitError` instead of failing later with `AttributeError`. Bytes that are not valid UTF-8 are replaced; that keeps the process alive. Lossless recovery of non-UTF-8 byte filenames is not attempted.

## Collisions

A **collision** means the same repository path changed on both sides since the merge-base of `--base` and `--head`. It does **not** guarantee a textual Git merge conflict.

`asset` and `map` collisions are marked `BINARY-SENSITIVE`. Rename handling in v0.1.7 is path-string overlap only (`--no-renames`); it is not rename-identity aware.

Collisions are a separate advisory signal. They do not change technical-risk or governance verdicts. Repo Preflight remains read-only and advisory.

```text
Collisions:
Count: 2
Binary-sensitive: 1
- Content/Maps/Test.umap [map, BINARY-SENSITIVE]
- src/app.py [source]
```

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Analysis completed successfully, even if risk/governance warnings were found |
| `2` | Configuration error |
| `3` | Git/repository/revision error |
| `4` | Known Repo Preflight domain error |

`HIGH` technical risk, `CRITICAL` governance, or a dirty worktree do not block by default. Repo Preflight is advisory in the current release.

## Security model

Repo Preflight is intentionally read-only.

The CLI:

- never uses `shell=True`;
- passes Git arguments as an argument list;
- validates user-supplied Git revisions before invoking Git;
- uses a Git command timeout;
- checks Git return codes and stderr;
- disables external diff and textconv helpers for diff inspection;
- disables fsmonitor hooks for worktree status inspection;
- escapes terminal control characters from repository/config-derived display text;
- does not execute commands from `.preflight.json`;
- does not require API keys, credentials, or network access.

See `SECURITY.md` for vulnerability reporting guidance.

## File classification

Default semantic types include:

- `source`
- `asset`
- `map`
- `build_config`
- fallback `other`

Classification precedence:

1. exact filename;
2. most-specific path prefix;
3. extension;
4. `other`.

Custom `file_types` replace the default classification rules.

## Governance defaults

If omitted, governance uses:

```json
{
  "critical_escalation": true,
  "critical_unknown_count": 5,
  "critical_unknown_ratio": 0.25
}
```

Ownership gaps produce `ATTENTION` until the configured count/ratio threshold is crossed. A confirmed ownership-boundary crossing is `CRITICAL`.

## Project status

Current release: **0.1.8**

The project is intentionally conservative: it reports and prioritizes integration signals instead of automatically merging or blocking changes.

Known scope limits include detached-HEAD handling, one effective owner per path, and richer language/framework-specific semantic analysis.

## Contributing

Issues, tests, rule improvements, documentation changes, and focused pull requests are welcome. See `CONTRIBUTING.md`.

## License

MIT License. See `LICENSE`.
