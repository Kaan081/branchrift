# Changelog

## 0.4.0

### Added

- Explicit, opt-in Git merge simulation (`--simulate-merge`) using an ephemeral object store; reports `CLEAN`, `CONFLICTS`, `UNKNOWN` or `ERROR` separately from advisory same-path overlaps. Git >=2.38 required.
- Experimental, opt-in merged-tree pytest verification (`--verify-pytest`) for **trusted** Python repositories. Reports test outcome separately from Git merge outcome and binds evidence to commit and merged-tree IDs.
- Bounded test stdout/stderr capture, metadata, output digests and source-import precedence for normal `src/`-layout projects; source paths are prioritized without claiming hermetic package provenance.

### Changed

- Clearer README first-run instructions and a separate explanation of the merge/test safety boundary.
- Package distribution version and import-time `preflight.__version__` now both report `0.4.0`.

### Validation / limitations

- 241 local regression tests passed following the source-import fix; PR #14 passed 14/14 pre-merge checks, and `main` passed 7/7 post-merge checks.
- On a controlled Reprovant integration test, independently green branches produced a Git CLEAN merge with failing combined pytest; the independent Git tree OID and test result agreed with BranchRift. This was a **controlled injection**, not an organically discovered production bug.
- For an external public pytest-impacted PR #109, same-path overlaps were identified and BranchRift's Git CLEAN merged-tree OID matched an independent Git merge. **Pytest was not run** on this untrusted external code; no regression claim follows.
- No independent user adoption, paid demand, or human-time savings has yet been established.
- The CLI remains advisory and does not provide a security sandbox, automatic CI gate, environment/dependency reproducibility, Unreal build validation, or general language test execution. Git merge drivers and opted-in tests may execute code with local permissions.

## 0.3.0

### Changed

- **Behavior change:** without `--base`, infer the comparison base from the locally recorded `origin/HEAD` (or the sole configured remote's HEAD) instead of assuming `dev`. If that reference is unavailable or ambiguous, stop with an actionable error. Explicit `--base` retains its previous behavior.
- Resolve repository-relative Git paths from the repository root, including analyses launched from nested directories.
- Limit binary worktree inspection to the bytes needed for LFS pointer detection instead of reading whole assets into memory.
- Parse Git attribute and porcelain status records in NUL-delimited form, including Unicode paths and renames.
- Treat unreadable worktree binary files conservatively rather than claiming they are hydrated and ready.
- Reject non-string ownership match types as configuration errors.

### Compatibility

- Users relying on the former implicit `dev` base must now pass `--base dev` explicitly.
- No intentional public JSON schema version change; historical revision provenance and read-only analysis remain supported.
- Both the `branchrift` and legacy `preflight` CLI commands remain available.

### Verification

- 195 local tests passed on Windows after the default-base changes.
- PR #6 and PR #7 each passed 14/14 CI checks (Linux, Windows, and wheel smoke).
- Four distinct public Git repositories passed read-only CLI acceptance checks, including a Git/LFS Unreal project.
- A separate disposable Unreal-repository divergence test matched Git's independent same-path collision result (one binary-sensitive `.umap`; no false collision for a base-only `.uasset`).
- These checks do not establish Unreal asset loadability, full Git LFS hydration, third-party adoption, or willingness to pay.

## 0.2.1

### Added

- Zero-config analysis when `.preflight.json` is absent.
- Repository-root discovery for the default `.preflight.json`, including runs started from nested directories.
- Structured ownership policy states: `not_configured`, `configured_empty`, and `configured`.
- Structured per-path ownership results: `known`, `not_configured`, and `no_match`.
- Structured governance output with explicit evaluation status and ownership policy status.
- Public report `schema_version` set to `1.0`.
- Ownership status counts in report summaries.

### Changed

- Ownership configuration is now optional.
- Missing ownership configuration no longer creates false `OWNERSHIP_GAP` findings, false governance escalation, or manual-review noise.
- Governance decisions now use structured ownership state instead of the legacy `"Unknown"` owner sentinel.
- Report serialization now converts internal ownership models at the public JSON boundary.
- Terminal output explicitly reports when ownership governance was not evaluated.
- Explicit `--config` paths remain strict: missing or invalid explicitly requested configuration still fails with a configuration error.

### Compatibility

- The legacy `owner` field and `governance_status` remain available for compatibility.
- The legacy `preflight` command remains available in v0.2.1.

## 0.2.0

- Renamed the public product from Repo Preflight to BranchRift.
- Distribution package is now `branchrift`.
- Added `branchrift` as the primary CLI command.
- Retained `preflight` as a compatibility CLI alias. This release does not print a runtime deprecation warning.
- Internal Python package remains `preflight` (`import preflight`). The config filename remains `.preflight.json`.
- No intentional analysis, risk, governance, collision, or Git LFS semantic changes in this release.

## 0.1.9

- Canonicalize file-type path prefixes so equivalent spellings such as `src`, `src/`, and `src\` cannot change classification or specificity; reject prefixes that canonicalize to an empty path.
- Support detached HEAD checkouts while keeping revision analysis SHA-based and reporting the current branch as `DETACHED`.
- Extend LFS readiness to LFS-managed paths outside the built-in asset/map types without changing their semantic file type or technical-risk classification.
- Suppress valid Git LFS pointer transport metadata (`version`, `oid`, `size`) from exact change facts.
- Bound terminal manual-review output to 20 paths while preserving the complete machine-readable list in JSON.
- Prevent terminal reports from crashing on limited Windows code pages by safely escaping characters the active stdout encoding cannot represent.

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
