# Changelog

## 0.1.8

- Report exact change facts from the merge-base diff: conservative scalar `value_changed` pairs, otherwise added or removed lines. Asset, map, and binary diffs are not given internal semantic claims.
- Report binary/LFS readiness for asset and map changes. Attributes come from the analyzed head. A historical head does not inherit the current checkout's hydration; readiness stays `unknown` with reason `analyzed_head_not_current_checkout`.
- Report revision provenance: requested refs, resolved SHAs, comparison mode, and whether the analyzed head is the current checkout.
- Use operation-aware Git timeouts: 15s fast, 30s normal, and 90s for unified diff, collision scan, and `git lfs ls-files`. A missing Git LFS command degrades to unknown LFS names and does not fail source-only analysis.
- Decode Git command output as UTF-8 on every platform, including Windows, so valid UTF-8 such as U+2014 is not decoded through the ANSI code page. Missing stdout becomes a `GitError`. Invalid bytes are replaced instead of crashing. Git-quoted Unicode paths in unified diffs are decoded back to the repository path.
- Add Windows CI for Python 3.10 and 3.13, and a wheel-install smoke job that does not use an editable install.

## 0.1.7

- Detect same-path branch collisions: repository paths changed on both `--base` and `--head` since their merge-base.
- Report collisions as a separate advisory signal. A collision is not a claim of a Git textual merge conflict.
- Mark `asset` and `map` collisions as binary-sensitive without inspecting file contents.
- Include deterministic collision data in JSON and a dedicated terminal section.
- Collision detection honors explicit `--head` without checking that revision out.
- Rename handling is path-level and conservative (`--no-renames`): overlap is the same path string, not rename identity.
- Technical-risk and governance verdicts are unchanged.
- Validate the release with a 75-test suite.

## 0.1.6

- Report Git topology for `--base` and `--head`: resolved SHAs, merge-base, ahead/behind counts, relationship, and fast-forward eligibility.
- Treat equivalent ownership prefix spellings (`src`, `src/`, `src\\`) as the same rule during config validation.
- Reject ownership prefix rules that canonicalize to an empty path.
- Use canonical prefix length for ownership specificity so trailing slashes cannot make a prefix artificially more specific.
- Add focused topology and prefix-canonicalization tests.

## 0.1.5

- Add PyPI package metadata and project links.
- Add GitHub Actions Trusted Publishing workflow for PyPI.
- Add direct `pip` and `pipx` installation documentation.
- Prepare Repo Preflight for public package distribution.


## 0.1.4

- Make ownership prefix matching path-segment aware, so a rule such as `src` no longer matches `src2/...`.
- Apply the same path-segment boundary behavior to custom file-classification prefixes.
- Normalize Windows-style separators for prefix matching.
- Add regression tests for prefix-boundary behavior.
- Improve README Markdown structure and quick-start documentation.
- Publish package metadata as version 0.1.4.

## 0.1.3

- Add terminal output sanitization for control characters in repository/config-derived text.
- Disable external diff and textconv helpers during Git diff inspection.
- Disable fsmonitor hooks during worktree status inspection.
- Add `CONTRIBUTING.md` and expanded security/public-release documentation.
- Publish package metadata as version 0.1.3.

## 0.1.2

- Reduce manual-review noise: newly added binary assets remain covered by asset verification without forcing individual manual review.
- Keep modified/deleted/renamed assets, maps, source, build config, high-risk changes, and governance issues reviewable.
- Add Git-status, file-type, and owner-count summaries to terminal and JSON reports.

## 0.1.1

- Add `--head` to analyze any fetched branch/revision without checking it out.
- Include analyzed head revision in terminal and JSON reports.
- Add end-to-end coverage for explicit-head analysis.

## 0.1.0

- Initial development release.
- Read-only Git branch preflight analysis.
- Ownership rules with `prefix` and `path_exact` matching.
- Config validation and defaults.
- File classification with semantic precedence.
- Technical risk and confidence signals.
- Required checks and manual-review shortlist.
- Ownership-gap and ownership-boundary-crossing governance signals.
- Dirty worktree warning.
- Human-readable and JSON output.
- Unit, integration, and CLI tests.
