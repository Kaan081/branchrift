# Security Policy

## Supported versions

Only the latest published BranchRift version receives security fixes. Earlier releases are not actively maintained.

## Execution and trust boundaries

BranchRift's default analysis is advisory and does not intentionally modify the analyzed repository's project files. It does not run project tests, install dependencies, merge branches, or approve integrations by default. However, default analysis runs Git commands including `git status`, which can invoke executable clean filters already configured in local or global Git settings for matching paths. Such filters may have side effects, including writes outside the repository. A tracked `.gitattributes` file alone does not define an executable filter, but it can select one that is already configured. Thus, "read-only" does **not** promise that Git or configured subprocesses execute no commands or have no side effects. Inspect only trusted repositories and Git configurations; a temporary directory is not a sandbox.

Two opt-in features have different security implications:

- `--simulate-merge` uses Git's `merge-tree` with a temporary object store and index. It does not change the original index, worktree, or branch, but Git configuration can invoke custom/external merge drivers.
- `--verify-pytest` implies merge simulation and, on a clean merge, exports the merged tree and **executes repository-supplied Python tests with the current user's permissions**. The temporary checkout is **not a security sandbox**. Tests, Git checkout filters, and custom merge drivers can execute commands, read secrets, access the network, or change files outside that checkout. Only use these options on repositories and configurations you trust. Use a separately isolated CI runner for untrusted code.

Test-process timeout and descendant cleanup are best-effort, not process containment. BranchRift does not install or lock test dependencies, guarantee a reproducible environment, prove test coverage, or verify an Unreal build. A `PASS` means only that the tests that ran passed in the observed environment. See the README for the exact result and provenance semantics.

## Sensitive data and reports

Report fields and captured test stdout/stderr tails can include repository paths, configuration values, secrets, or other sensitive data written by tests. Review JSON and terminal reports before sharing them publicly. SHA-256 output digests provide a comparison fingerprint, not a signature or a confidentiality guarantee.

Security-sensitive implementation areas include:

- Git subprocess arguments, revision resolution, timeouts, custom merge drivers, and checkout filters
- temporary object stores, indexes, source export, and process cleanup
- path validation, symlinks/submodules, and configuration parsing
- terminal rendering, JSON integrity, and potentially sensitive test output
- GitHub Actions release permissions and PyPI Trusted Publishing

## Reporting a vulnerability

Do not disclose exploitable details in a public GitHub issue.

Use GitHub's **Private Vulnerability Reporting** for this repository if enabled. Otherwise, contact the maintainer privately through a channel already listed on the maintainer's public GitHub profile. Include the affected version, reproduction steps, expected and actual behavior, and security impact. Do not attach credentials or real customer data.

This document describes intended boundaries and responsible reporting; it is not a claim that the project has undergone an independent security audit.
