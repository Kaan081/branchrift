from pathlib import Path

from .collisions import is_binary_sensitive
from .git import get_check_attr, get_lfs_ls_files_names


_UNSET = object()
LFS_POINTER_MAX_BYTES = 1024
LFS_POINTER_VERSION = "version https://git-lfs.github.com/spec/v1"


def is_lfs_pointer_text(text):
    if not text:
        return False
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    if not lines or lines[0] != LFS_POINTER_VERSION:
        return False
    has_oid = any(line.startswith("oid sha256:") and len(line) > len("oid sha256:") for line in lines)
    has_size = False
    for line in lines:
        if not line.startswith("size "):
            continue
        size_text = line[len("size ") :].strip()
        if size_text.isdigit():
            has_size = True
            break
    return has_oid and has_size


def inspect_worktree_file(cwd, path):
    root = Path(cwd) if cwd is not None else Path.cwd()
    root = root.resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return {"exists": False, "pointer": False, "readable": False}

    if not target.is_file():
        return {"exists": False, "pointer": False, "readable": True}

    try:
        size = target.stat().st_size
        prefix = target.read_bytes()[: LFS_POINTER_MAX_BYTES + 1]
    except OSError:
        return {"exists": True, "pointer": False, "readable": False}

    pointer = False
    if size <= LFS_POINTER_MAX_BYTES:
        try:
            text = prefix.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        pointer = is_lfs_pointer_text(text)
    return {"exists": True, "pointer": pointer, "readable": True}


def parse_porcelain_paths(raw):
    states = {}
    for line in raw.splitlines():
        if not line:
            continue
        if line.startswith("?? "):
            states[line[3:].replace("\\", "/")] = "??"
            continue
        if len(line) < 4:
            continue
        xy = line[:2]
        rest = line[3:]
        if rest.startswith('"') and rest.endswith('"'):
            rest = rest[1:-1]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        states[rest.replace("\\", "/")] = xy
    return states


def binary_sensitive_changes(changes):
    selected = []
    for change in changes:
        if is_binary_sensitive(change.get("file_type")) or is_binary_sensitive(
            change.get("old_file_type")
        ):
            selected.append(change)
    return selected


def _lfs_managed(attr_value, lfs_names, path):
    if attr_value == "lfs":
        return True
    if lfs_names is not None and path in lfs_names:
        return True
    if attr_value in ("unspecified", "unset"):
        return False
    if lfs_names is not None:
        return False
    if attr_value is None:
        return None
    return False


def classify_binary_readiness(
    *,
    git_status,
    lfs_managed,
    exists,
    is_pointer,
    worktree_matches_head,
    porcelain_xy=None,
    head_is_current_checkout=True,
):
    if not head_is_current_checkout:
        return {
            "lfs_managed": lfs_managed,
            "working_tree_state": "unknown",
            "lfs_state": "unknown",
            "readiness": "unknown",
            "reason": "analyzed_head_not_current_checkout",
        }

    if git_status == "D":
        working_tree_state = "deleted" if not exists else "present"
        lfs_state = "not_lfs" if lfs_managed is False else "unknown"
        return {
            "lfs_managed": lfs_managed,
            "working_tree_state": working_tree_state,
            "lfs_state": lfs_state,
            "readiness": "ready",
            "reason": "intentionally deleted in the analyzed diff",
        }

    if exists and is_pointer:
        return {
            "lfs_managed": True if lfs_managed is None else lfs_managed,
            "working_tree_state": "present",
            "lfs_state": "pointer",
            "readiness": "attention",
            "reason": "working tree contains an LFS pointer instead of hydrated binary content",
        }

    if not exists:
        if not worktree_matches_head:
            return {
                "lfs_managed": lfs_managed,
                "working_tree_state": "missing",
                "lfs_state": "unknown",
                "readiness": "unknown",
                "reason": "working tree is not the analyzed head; hydration cannot be confirmed",
            }
        return {
            "lfs_managed": lfs_managed,
            "working_tree_state": "missing",
            "lfs_state": "missing" if lfs_managed else "unknown",
            "readiness": "attention",
            "reason": "expected path is missing from the working tree",
        }

    working_tree_state = "present"
    if porcelain_xy and "M" in porcelain_xy:
        working_tree_state = "modified"

    if lfs_managed is True:
        return {
            "lfs_managed": True,
            "working_tree_state": working_tree_state,
            "lfs_state": "hydrated",
            "readiness": "ready",
        }
    if lfs_managed is False:
        return {
            "lfs_managed": False,
            "working_tree_state": working_tree_state,
            "lfs_state": "not_lfs",
            "readiness": "ready",
        }
    return {
        "lfs_managed": None,
        "working_tree_state": working_tree_state,
        "lfs_state": "unknown",
        "readiness": "unknown",
        "reason": "Git LFS state could not be determined",
    }


def build_binary_readiness_report(
    changes,
    *,
    cwd=None,
    worktree_status="",
    analyzed_head_sha=None,
    current_head_sha=None,
    head_is_current_checkout=None,
    attr_values=_UNSET,
    lfs_names=_UNSET,
):
    selected = binary_sensitive_changes(changes)
    if not selected:
        return None

    paths = []
    seen = set()
    for change in selected:
        path = change["path"]
        if path not in seen:
            seen.add(path)
            paths.append(path)

    if head_is_current_checkout is None:
        head_is_current_checkout = bool(
            analyzed_head_sha and current_head_sha and analyzed_head_sha == current_head_sha
        )

    if attr_values is _UNSET:
        if analyzed_head_sha:
            attr_values = get_check_attr(
                "filter",
                paths,
                cwd=cwd,
                source=analyzed_head_sha,
            )
        else:
            attr_values = {path: None for path in paths}
    if lfs_names is _UNSET:
        if head_is_current_checkout:
            lfs_names = get_lfs_ls_files_names(cwd=cwd)
        else:
            lfs_names = None

    porcelain = parse_porcelain_paths(worktree_status)
    worktree_matches_head = bool(head_is_current_checkout)

    files = []
    for change in selected:
        path = change["path"]
        if head_is_current_checkout:
            inspection = inspect_worktree_file(cwd, path)
            porcelain_xy = porcelain.get(path)
            names_for_path = lfs_names
        else:
            inspection = {"exists": False, "pointer": False, "readable": False}
            porcelain_xy = None
            names_for_path = None
        classified = classify_binary_readiness(
            git_status=change.get("git_status"),
            lfs_managed=_lfs_managed(attr_values.get(path), names_for_path, path),
            exists=inspection["exists"],
            is_pointer=inspection["pointer"],
            worktree_matches_head=worktree_matches_head,
            porcelain_xy=porcelain_xy,
            head_is_current_checkout=head_is_current_checkout,
        )
        entry = {
            "path": path,
            "file_type": change.get("file_type"),
            "git_status": change.get("git_status"),
            "lfs_managed": classified["lfs_managed"],
            "working_tree_state": classified["working_tree_state"],
            "lfs_state": classified["lfs_state"],
            "readiness": classified["readiness"],
        }
        if classified.get("reason"):
            entry["reason"] = classified["reason"]
        files.append(entry)

    files.sort(key=lambda item: item["path"])
    return {
        "count": len(files),
        "attention_count": sum(1 for item in files if item["readiness"] == "attention"),
        "files": files,
    }
