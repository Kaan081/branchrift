"""Opt-in Git merge simulation and explicit merged-tree verification.

Git's merge-tree does not change index/worktree, but --write-tree writes objects.
We divert its object writes to a temporary store with the repository objects as
read-only alternates; the temporary objects are discarded after reporting.

Simulation alone does NOT test the resulting program. Verification runs
repository test code without a security sandbox: only use trusted repositories.
Custom Git merge drivers and checkout filters may also execute commands.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from .integration_verification import _evidence, verify_merged_tree

MERGE_TIMEOUT_SECONDS = 90
MIN_GIT_VERSION = (2, 38)
_SHA_PATTERN = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")
_TREE_PATTERN = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_METHOD = "git merge-tree --write-tree --name-only -z --no-messages"


def _outcome(status, base_sha, head_sha, *, reason=None, tree_oid=None, paths=None, verification=None):
    data = {
        "status": status,
        "method": _METHOD,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "conflicted_paths": paths or [],
        "conflicted_path_count": len(paths or []),
        "conflicted_paths_scope": "unmerged-index-paths",
        "result_tree_oid": tree_oid,
        "result_tree_retained": False,
        "integration_tests_executed": False,
    }
    if reason is not None:
        data["reason"] = reason
    if verification is not None:
        data["verification"] = verification
        data["integration_tests_executed"] = verification["status"] in ("PASS", "FAIL")
    return data


def _git_call(args, cwd, *, env=None, timeout=15):
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout, check=False,
    )


def _parse_merge_output(raw):
    """Parse NUL-delimited tree OID and unmerged-path list, never message text."""
    if not raw.endswith(b"\0"):
        raise ValueError("Git returned an unterminated merge result")
    pieces = raw.split(b"\0")
    if len(pieces) < 2 or not _TREE_PATTERN.fullmatch(pieces[0]):
        raise ValueError("Git returned an invalid result tree ID")
    if pieces[-1] != b"":
        raise ValueError("Malformed NUL-delimited merge result")
    try:
        paths = [path.decode("utf-8", errors="strict") for path in pieces[1:-1]]
    except UnicodeDecodeError as exc:
        raise ValueError("Git merge path is not valid UTF-8") from exc
    if any(not path for path in paths):
        raise ValueError("Git returned an empty conflicted path")
    return pieces[0].decode("ascii"), sorted(set(paths))


def simulate_merge(
    base_sha, head_sha, *, cwd, timeout=MERGE_TIMEOUT_SECONDS, verify_pytest=False,
):
    """Evaluate two resolved commit SHAs. Return status, not an applied merge.

    Statuses: CLEAN, CONFLICTS, UNKNOWN (unsupported capability), ERROR.
    A conflict's reported paths are unmerged-index paths; they may not include
    every file mentioned in Git's informational conflict messages.
    verify_pytest explicitly executes Python test code on CLEAN merged output.
    It is not a security sandbox and does not verify a build.
    """
    def finish(*args, **kwargs):
        if verify_pytest and kwargs.get("verification") is None:
            kwargs["verification"] = _evidence(
                "NOT_RUN", reason="Merge did not produce a verified clean tree"
            )
        outcome = _outcome(*args, **kwargs)
        if verify_pytest:
            # Bind test evidence to the *requested* commits and ephemeral merge tree.
            # A NOT_RUN record is provenance, not proof that code was executed.
            outcome["verification"]["provenance"] = {
                "base_sha": base_sha,
                "head_sha": head_sha,
                "merged_tree_oid": outcome["result_tree_oid"],
            }
        return outcome

    if not isinstance(base_sha, str) or not _SHA_PATTERN.fullmatch(base_sha):
        return finish("ERROR", base_sha, head_sha, reason="Invalid base commit SHA")
    if not isinstance(head_sha, str) or not _SHA_PATTERN.fullmatch(head_sha):
        return finish("ERROR", base_sha, head_sha, reason="Invalid head commit SHA")

    try:
        version = _git_call(["--version"], cwd)
        if version.returncode != 0:
            return finish("ERROR", base_sha, head_sha, reason="Cannot determine Git version")
        match = re.search(rb"git version (\d+)\.(\d+)", version.stdout)
        if not match:
            return finish("UNKNOWN", base_sha, head_sha, reason="Git version cannot be determined")
        version_tuple = (int(match.group(1)), int(match.group(2)))
        if version_tuple < MIN_GIT_VERSION:
            return finish("UNKNOWN", base_sha, head_sha, reason="Git 2.38 or newer is required for merge-tree simulation")

        # --git-path accounts for separate worktrees and GIT_COMMON_DIR.
        object_lookup = _git_call(
            ["rev-parse", "--path-format=absolute", "--git-path", "objects"], cwd,
        )
        if object_lookup.returncode != 0:
            return finish("ERROR", base_sha, head_sha, reason="Cannot locate Git object directory")
        try:
            repo_objects = Path(object_lookup.stdout.decode("utf-8").strip())
        except UnicodeDecodeError:
            return finish("ERROR", base_sha, head_sha, reason="Git object path could not be decoded")
        if not repo_objects.is_absolute() or not repo_objects.is_dir():
            return finish("ERROR", base_sha, head_sha, reason="Git object directory is not accessible")

        with tempfile.TemporaryDirectory(prefix="branchrift-merge-") as temp:
            scratch = Path(temp) / "objects"
            scratch.mkdir()
            env = os.environ.copy()
            old_alternates = env.get("GIT_ALTERNATE_OBJECT_DIRECTORIES")
            env["GIT_OBJECT_DIRECTORY"] = str(scratch)
            env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(repo_objects) + (
                os.pathsep + old_alternates if old_alternates else ""
            )
            env["GIT_OPTIONAL_LOCKS"] = "0"
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["GIT_INDEX_FILE"] = str(Path(temp) / "index")
            result = _git_call(
                ["merge-tree", "--write-tree", "--name-only", "-z", "--no-messages",
                 base_sha, head_sha], cwd,
                env=env, timeout=timeout,
            )
            # Parse *before* removing temporary object store; never claim its
            # resulting tree ID can be read from the original repository.
            if result.returncode not in (0, 1):
                return finish(
                    "ERROR", base_sha, head_sha,
                    reason="Git merge-tree failed (exit code {})".format(result.returncode),
                )
            try:
                tree_oid, paths = _parse_merge_output(result.stdout)
            except ValueError as exc:
                return finish("ERROR", base_sha, head_sha, reason=str(exc))
            if result.returncode == 0 and paths:
                return finish("ERROR", base_sha, head_sha, reason="Git reported clean merge with unmerged paths")
            verification = None
            if verify_pytest:
                if result.returncode == 0:
                    verification = verify_merged_tree(
                        tree_oid, cwd=cwd, git_env=env, temp_root=temp,
                        git_call=_git_call,
                    )
                else:
                    verification = _evidence("NOT_RUN", reason="Git merge has conflicts; tests were skipped")
            return finish(
                "CLEAN" if result.returncode == 0 else "CONFLICTS",
                base_sha, head_sha,
                tree_oid=tree_oid, paths=paths, verification=verification,
            )
    except subprocess.TimeoutExpired:
        return finish("ERROR", base_sha, head_sha, reason="Git merge simulation timed out")
    except (OSError, ValueError) as exc:
        return finish("ERROR", base_sha, head_sha, reason=f"Git merge simulation unavailable: {type(exc).__name__}")
