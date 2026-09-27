import subprocess

from .errors import GitError, GitTimeoutError


TIMEOUT_FAST_SECONDS = 15
TIMEOUT_NORMAL_SECONDS = 30
TIMEOUT_EXPENSIVE_SECONDS = 90

TIMEOUT_SECONDS = {
    "fast": TIMEOUT_FAST_SECONDS,
    "normal": TIMEOUT_NORMAL_SECONDS,
    "expensive": TIMEOUT_EXPENSIVE_SECONDS,
}

OPERATION_TIMEOUT_CLASS = {
    "ensure_repository": "fast",
    "rev_parse": "fast",
    "current_branch": "fast",
    "merge_base": "fast",
    "rev_list": "normal",
    "name_status": "normal",
    "status": "normal",
    "check_attr": "normal",
    "collision_scan": "expensive",
    "unified_diff": "expensive",
    "lfs_ls_files": "expensive",
}


def timeout_for_operation(operation):
    kind = OPERATION_TIMEOUT_CLASS.get(operation, "normal")
    return TIMEOUT_SECONDS[kind]


def run_git(args, cwd=None, timeout=None, operation=None):
    operation_name = operation or "git"
    budget = timeout if timeout is not None else timeout_for_operation(operation)
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=budget,
        )
    except FileNotFoundError as error:
        raise GitError("Git executable was not found") from error
    except subprocess.TimeoutExpired as error:
        raise GitTimeoutError(
            "Git operation timed out\n"
            f"Operation: {operation_name}\n"
            f"Timeout: {budget}s"
        ) from error

    # A locale decoder can fail inside the reader thread and leave stdout as None.
    stdout = result.stdout if result.stdout is not None else ""
    stderr = result.stderr if result.stderr is not None else ""
    if result.stdout is None:
        raise GitError(
            "Git command produced undecodable output\n"
            f"Operation: {operation_name}"
        )

    if result.returncode != 0:
        message = stderr.strip() or stdout.strip() or "Git command failed"
        raise GitError(message)

    return stdout


def ensure_git_repository(cwd=None):
    value = run_git(
        ["rev-parse", "--is-inside-work-tree"],
        cwd=cwd,
        operation="ensure_repository",
    ).strip()
    if value != "true":
        raise GitError("Current directory is not a Git repository")


def get_current_branch(cwd=None):
    branch = run_git(
        ["branch", "--show-current"],
        cwd=cwd,
        operation="current_branch",
    ).strip()
    if not branch:
        raise GitError("Could not determine current branch (detached HEAD is not supported in v0.1)")
    return branch


def validate_revision_argument(revision):
    if not isinstance(revision, str) or not revision:
        raise GitError("Git revision must be a non-empty string")
    if revision.startswith("-") or "\0" in revision or "\n" in revision or "\r" in revision:
        raise GitError(f"Unsafe Git revision argument: {revision!r}")


def ensure_revision_exists(revision, cwd=None):
    validate_revision_argument(revision)
    try:
        run_git(
            ["rev-parse", "--verify", "--quiet", revision],
            cwd=cwd,
            operation="rev_parse",
        )
    except GitTimeoutError:
        raise
    except GitError as error:
        raise GitError(f"Git revision does not exist: {revision}") from error


def resolve_commit_sha(revision, cwd=None):
    validate_revision_argument(revision)
    try:
        sha = run_git(
            ["rev-parse", "--verify", f"{revision}^{{commit}}"],
            cwd=cwd,
            operation="rev_parse",
        ).strip()
    except GitTimeoutError:
        raise
    except GitError as error:
        raise GitError(f"Git revision does not exist: {revision}") from error
    if not sha:
        raise GitError(f"Git revision does not exist: {revision}")
    return sha


def classify_topology_relationship(behind, ahead):
    if behind == 0 and ahead == 0:
        return "SAME"
    if behind == 0 and ahead > 0:
        return "LINEAR"
    if behind > 0 and ahead == 0:
        return "HEAD_BEHIND"
    return "DIVERGED"


def get_git_topology(base_revision, head_revision, cwd=None):
    base_sha = resolve_commit_sha(base_revision, cwd=cwd)
    head_sha = resolve_commit_sha(head_revision, cwd=cwd)
    merge_base = run_git(
        ["merge-base", base_sha, head_sha],
        cwd=cwd,
        operation="merge_base",
    ).strip()
    count_output = run_git(
        ["rev-list", "--left-right", "--count", f"{base_sha}...{head_sha}"],
        cwd=cwd,
        operation="rev_list",
    ).strip()
    parts = count_output.split()
    if len(parts) != 2:
        raise GitError(f"Unexpected git rev-list count output: {count_output}")
    try:
        behind = int(parts[0])
        ahead = int(parts[1])
    except ValueError as error:
        raise GitError(f"Unexpected git rev-list count output: {count_output}") from error
    if behind < 0 or ahead < 0:
        raise GitError(f"Unexpected git rev-list count output: {count_output}")

    relationship = classify_topology_relationship(behind, ahead)
    return {
        "base_sha": base_sha,
        "head_sha": head_sha,
        "merge_base": merge_base,
        "behind": behind,
        "ahead": ahead,
        "relationship": relationship,
        "ff_eligible": behind == 0,
    }


def get_changed_paths(from_revision, to_revision, cwd=None):
    validate_revision_argument(from_revision)
    validate_revision_argument(to_revision)
    raw = run_git(
        [
            "diff",
            "--name-only",
            "-z",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            from_revision,
            to_revision,
        ],
        cwd=cwd,
        operation="collision_scan",
    )
    return {path for path in raw.split("\0") if path}


def get_collision_paths(topology, cwd=None):
    merge_base = topology["merge_base"]
    base_paths = get_changed_paths(merge_base, topology["base_sha"], cwd=cwd)
    head_paths = get_changed_paths(merge_base, topology["head_sha"], cwd=cwd)
    return base_paths & head_paths


def get_diff_name_status(base_branch, head_revision="HEAD", cwd=None):
    validate_revision_argument(base_branch)
    validate_revision_argument(head_revision)
    return run_git(
        [
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            "--no-ext-diff",
            "--no-textconv",
            f"{base_branch}...{head_revision}",
        ],
        cwd=cwd,
        operation="name_status",
    )


def get_unified_diff(base_branch, head_revision="HEAD", cwd=None):
    validate_revision_argument(base_branch)
    validate_revision_argument(head_revision)
    return run_git(
        [
            "diff",
            "--unified=0",
            "--find-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            f"{base_branch}...{head_revision}",
        ],
        cwd=cwd,
        operation="unified_diff",
    )


def get_worktree_status(cwd=None):
    # Disable repo/user-configured fsmonitor hooks for read-only inspection.
    return run_git(
        ["-c", "core.fsmonitor=false", "status", "--porcelain"],
        cwd=cwd,
        operation="status",
    )


def is_worktree_dirty(cwd=None):
    return bool(get_worktree_status(cwd=cwd).strip())


CHECK_ATTR_CHUNK_SIZE = 50


def _safe_git_path(path):
    if not isinstance(path, str) or not path:
        return False
    if path.startswith("-") or "\0" in path or "\n" in path or "\r" in path:
        return False
    parts = path.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        return False
    return True


def get_check_attr(attribute, paths, cwd=None, source=None):
    values = {}
    safe_paths = []
    for path in paths:
        if _safe_git_path(path):
            safe_paths.append(path)
        else:
            values[path] = None

    if source is not None:
        validate_revision_argument(source)

    for start in range(0, len(safe_paths), CHECK_ATTR_CHUNK_SIZE):
        chunk = safe_paths[start : start + CHECK_ATTR_CHUNK_SIZE]
        try:
            args = ["check-attr"]
            if source is not None:
                args.append(f"--source={source}")
            args.extend([attribute, "--", *chunk])
            raw = run_git(args, cwd=cwd, operation="check_attr")
        except GitError:
            for path in chunk:
                values[path] = None
            continue
        marker = f": {attribute}: "
        for line in raw.splitlines():
            if marker not in line:
                continue
            path, value = line.rsplit(marker, 1)
            values[path.replace("\\", "/")] = value.strip()
    return values


def get_lfs_ls_files_names(cwd=None):
    try:
        raw = run_git(
            ["lfs", "ls-files", "--name-only"],
            cwd=cwd,
            operation="lfs_ls_files",
        )
    except GitError:
        return None
    return {line.strip().replace("\\", "/") for line in raw.splitlines() if line.strip()}


def parse_git_diff(raw):
    tokens = raw.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()

    changes = []
    index = 0

    while index < len(tokens):
        status_token = tokens[index]
        index += 1

        if not status_token:
            raise GitError("Malformed Git diff record: empty status")

        git_status = status_token[0]

        if git_status in ("R", "C"):
            if index + 1 >= len(tokens):
                raise GitError("Malformed Git rename/copy record")

            old_path = tokens[index]
            new_path = tokens[index + 1]
            index += 2

            score_text = status_token[1:]
            similarity = int(score_text) if score_text.isdigit() else None

            changes.append(
                {
                    "git_status": git_status,
                    "similarity": similarity,
                    "old_path": old_path,
                    "path": new_path,
                }
            )
            continue

        if index >= len(tokens):
            raise GitError("Malformed Git diff record")

        path = tokens[index]
        index += 1
        changes.append({"git_status": git_status, "path": path})

    return changes
