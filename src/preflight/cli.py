import argparse
import sys
from pathlib import Path

from .analyzer import analyze_change
from .binary_readiness import build_binary_readiness_report
from .change_facts import build_change_facts_report, file_types_for_change_facts
from .collisions import build_collision_report
from .config import load_config, normalize_config
from .errors import ConfigError, GitError, PreflightError
from .git import (
    ensure_git_repository,
    ensure_revision_exists,
    get_collision_paths,
    get_current_branch,
    get_diff_name_status,
    get_git_topology,
    get_repository_root,
    get_unified_diff,
    get_worktree_status,
    parse_git_diff,
    resolve_commit_sha,
    run_git,
)
from .pipeline import build_change_context
from .report import build_report, build_revision_provenance
from .reporter import print_compact_report, print_json_report, print_report


DEFAULT_CONFIG_NAME = ".preflight.json"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze Git changes before integration"
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Base branch/revision (default: local remote HEAD; use --base if unavailable)",
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="Head branch/revision to analyze without checking it out",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to preflight config",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    output.add_argument(
        "--verbose",
        action="store_true",
        help="Print full human-readable report (previous default)",
    )
    return parser.parse_args(argv)


def resolve_config(config_arg, cwd=None):
    analysis_root = Path(cwd) if cwd is not None else Path.cwd()

    if config_arg is not None:
        config_path = Path(config_arg)

        if not config_path.is_absolute():
            config_path = analysis_root / config_path

        return load_config(config_path)

    repository_root = Path(get_repository_root(cwd=cwd))
    default_config_path = repository_root / DEFAULT_CONFIG_NAME

    if default_config_path.exists():
        return load_config(default_config_path)

    return normalize_config({})


def resolve_default_base(cwd=None):
    """Return a locally recorded remote default, without network access.

    origin wins when present; a sole non-origin remote is also supported.
    A branch name without a remote HEAD is ambiguous, so we fail rather than guess.
    """
    remotes = run_git(["remote"], cwd=cwd, operation="rev_parse").splitlines()
    if "origin" in remotes:
        remote = "origin"
    elif len(remotes) == 1:
        remote = remotes[0]
    else:
        remote = None

    if remote is not None:
        try:
            base = run_git(
                ["symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD"],
                cwd=cwd,
                operation="rev_parse",
            ).strip()
        except GitError:
            base = ""
        if base.startswith(f"{remote}/"):
            try:
                ensure_revision_exists(base, cwd=cwd)
            except GitError:
                pass
            else:
                return base

    raise GitError(
        "Could not determine a default base from the locally recorded remote HEAD. "
        "Pass --base explicitly (for example: --base main)."
    )


def run(argv=None, cwd=None):
    args = parse_args(argv)
    config = resolve_config(args.config, cwd=cwd)

    ensure_git_repository(cwd=cwd)
    # Git diff/status paths are repository-relative, even from nested directories.
    # Keep explicit --config resolution caller-relative (handled above), then root all analysis.
    cwd = get_repository_root(cwd=cwd)
    base = args.base if args.base is not None else resolve_default_base(cwd=cwd)
    ensure_revision_exists(base, cwd=cwd)
    ensure_revision_exists(args.head, cwd=cwd)

    branch = get_current_branch(cwd=cwd)
    worktree_status = get_worktree_status(cwd=cwd)
    dirty = bool(worktree_status.strip())

    topology = get_git_topology(
        base,
        args.head,
        cwd=cwd,
    )

    collisions = build_collision_report(
        get_collision_paths(topology, cwd=cwd),
        config["file_types"],
    )

    raw_changes = parse_git_diff(
        get_diff_name_status(
            topology["base_sha"],
            topology["head_sha"],
            cwd=cwd,
        )
    )

    analyzed_changes = []

    for raw_change in raw_changes:
        context = build_change_context(raw_change, config)
        analyzed_changes.append(analyze_change(context))

    change_facts = build_change_facts_report(
        get_unified_diff(
            topology["base_sha"],
            topology["head_sha"],
            cwd=cwd,
        ),
        file_types_for_change_facts(analyzed_changes),
    )

    current_head_sha = topology["head_sha"]

    if args.head != "HEAD":
        current_head_sha = resolve_commit_sha("HEAD", cwd=cwd)

    revision_provenance = build_revision_provenance(
        base,
        args.head,
        topology,
        current_head_sha=current_head_sha,
    )

    binary_readiness = build_binary_readiness_report(
        analyzed_changes,
        cwd=cwd,
        worktree_status=worktree_status,
        analyzed_head_sha=topology["head_sha"],
        current_head_sha=current_head_sha,
        head_is_current_checkout=revision_provenance[
            "head_is_current_checkout"
        ],
    )

    report = build_report(
    branch,
    base,
    analyzed_changes,
    config["governance"],
    worktree_dirty=dirty,
    head_revision=args.head,
    topology=topology,
    collisions=collisions,
    change_facts=change_facts,
    binary_readiness=binary_readiness,
    revision_provenance=revision_provenance,
    ownership_policy_status=config["ownership_policy_status"],
)

    if args.json:
        print_json_report(report)
    elif args.verbose:
        print_report(report)
    else:
        print_compact_report(report)

    return report


def main():
    try:
        run()
    except ConfigError as error:
        print(f"CONFIG ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
    except GitError as error:
        print(f"GIT ERROR: {error}", file=sys.stderr)
        raise SystemExit(3)
    except PreflightError as error:
        print(f"PREFLIGHT ERROR: {error}", file=sys.stderr)
        raise SystemExit(4)