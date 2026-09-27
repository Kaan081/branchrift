"""v0.1.9 evidence: change-set and check-attr scaling on v0.1.8.

These measurements are not a performance SLA. They record whether current
timeouts or subprocess fan-out are approached.
"""

import json
import math
import subprocess
import sys
import time
import tracemalloc
from io import StringIO

from preflight.binary_readiness import build_binary_readiness_report
from preflight.cli import run
from preflight.git import CHECK_ATTR_CHUNK_SIZE, get_check_attr, get_lfs_ls_files_names
from preflight.reporter import print_json_report, print_report


def git(repo, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=True,
    )
    return result.stdout


def _operation(cmd):
    if not isinstance(cmd, (list, tuple)) or not cmd or cmd[0] != "git":
        return None
    args = list(cmd[1:])
    if "check-attr" in args:
        return "check_attr"
    if "lfs" in args:
        return "lfs_ls_files"
    if "--name-status" in args:
        return "name_status"
    if "--unified=0" in args:
        return "unified_diff"
    if "--name-only" in args and "--no-renames" in args:
        return "collision_scan"
    return "other"


def _spy(monkeypatch):
    events = []
    real_run = subprocess.run

    def wrapped(cmd, **kwargs):
        started = time.perf_counter()
        try:
            result = real_run(cmd, **kwargs)
        except Exception:
            events.append(
                {
                    "operation": _operation(cmd),
                    "elapsed": time.perf_counter() - started,
                    "timeout": kwargs.get("timeout"),
                    "error": True,
                }
            )
            raise
        events.append(
            {
                "operation": _operation(cmd),
                "elapsed": time.perf_counter() - started,
                "timeout": kwargs.get("timeout"),
                "error": False,
            }
        )
        return result

    monkeypatch.setattr(subprocess, "run", wrapped)
    return events


def _write_files(repo, count, text):
    root = repo / "files"
    root.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8")
    for index in range(count):
        (root / f"{index:05d}.txt").write_bytes(payload)


def _changed_text_repo(tmp_path, count):
    repo = tmp_path / f"repo-{count}"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    git(repo, "config", "core.autocrlf", "false")
    _write_files(repo, count, "v=1\n")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD").strip()
    _write_files(repo, count, "v=2\n")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", "change")
    config_path = tmp_path / f"preflight-{count}.json"
    config_path.write_text(
        json.dumps(
            {"ownership": [{"match": "prefix", "path": "files/", "owner": "Backend"}]}
        ),
        encoding="utf-8",
    )
    return repo, base, config_path


def _summarize(events, operation):
    matched = [event for event in events if event["operation"] == operation]
    return {
        "calls": len(matched),
        "seconds": round(sum(event["elapsed"] for event in matched), 4),
        "max_seconds": round(max((event["elapsed"] for event in matched), default=0), 4),
        "max_timeout": max((event["timeout"] or 0 for event in matched), default=0),
    }


def _capture_report(render):
    stdout = StringIO()
    previous = sys.stdout
    sys.stdout = stdout
    started = time.perf_counter()
    try:
        render()
    finally:
        sys.stdout = previous
    return time.perf_counter() - started, stdout.getvalue()


def test_change_set_scaling(tmp_path, monkeypatch):
    events = _spy(monkeypatch)
    rows = []
    for count in (1000, 10000):
        repo, base, config_path = _changed_text_repo(tmp_path, count)
        before = len(events)
        tracemalloc.start()
        started = time.perf_counter()
        cli_stdout = StringIO()
        previous = sys.stdout
        sys.stdout = cli_stdout
        try:
            report = run(
                ["--base", base, "--config", str(config_path), "--json"],
                cwd=repo,
            )
            cli_json = cli_stdout.getvalue()
        finally:
            sys.stdout = previous
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        total = time.perf_counter() - started
        terminal_seconds, terminal_text = _capture_report(lambda: print_report(report))
        json_seconds, json_text = _capture_report(lambda: print_json_report(report))
        used = events[before:]
        rows.append(
            {
                "files": count,
                "changes": report["summary"]["total_changes"],
                "total_seconds_including_json_from_cli": round(total, 4),
                "terminal_seconds": round(terminal_seconds, 4),
                "terminal_chars": len(terminal_text),
                "json_seconds": round(json_seconds, 4),
                "json_bytes": len(json_text.encode("utf-8")),
                "cli_json_bytes": len(cli_json.encode("utf-8")),
                "tracemalloc_peak_bytes": peak,
                "git_calls": len(used),
                "name_status": _summarize(used, "name_status"),
                "unified_diff": _summarize(used, "unified_diff"),
                "collision_scan": _summarize(used, "collision_scan"),
                "other_git": _summarize(used, "other"),
                "slowest_git": round(max(event["elapsed"] for event in used), 4),
                "timeouts_hit": any(event["error"] for event in used),
            }
        )
        assert report["summary"]["total_changes"] == count
        assert rows[-1]["timeouts_hit"] is False
        assert rows[-1]["slowest_git"] < 90

    ratio = rows[1]["total_seconds_including_json_from_cli"] / rows[0][
        "total_seconds_including_json_from_cli"
    ]
    print(
        "SCALE "
        + json.dumps({"rows": rows, "time_ratio_10k_over_1k": round(ratio, 2)}),
        file=sys.stderr,
    )


def _lfs_repo(tmp_path, count, name=None):
    repo = tmp_path / (name or f"lfs-{count}")
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    git(repo, "config", "core.autocrlf", "false")
    (repo / ".gitattributes").write_text(
        "*.wav filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    audio = repo / "Audio"
    audio.mkdir()
    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "size 128\n"
    )
    for index in range(count):
        (audio / f"{index:04d}.wav").write_text(pointer, encoding="utf-8")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", "lfs pointers")
    sha = git(repo, "rev-parse", "HEAD").strip()
    paths = [f"Audio/{index:04d}.wav" for index in range(count)]
    return repo, sha, paths


def test_check_attr_chunk_scaling(tmp_path, monkeypatch):
    events = _spy(monkeypatch)
    rows = []
    for count in (10, 100, 1000):
        repo, sha, paths = _lfs_repo(tmp_path, count)
        changes = [
            {"path": path, "file_type": "asset", "git_status": "A"} for path in paths
        ]
        before = len(events)
        started = time.perf_counter()
        report = build_binary_readiness_report(
            changes,
            cwd=repo,
            worktree_status="",
            analyzed_head_sha=sha,
            current_head_sha=sha,
            head_is_current_checkout=True,
        )
        elapsed = time.perf_counter() - started
        used = events[before:]
        check_attr = _summarize(used, "check_attr")
        lfs = _summarize(used, "lfs_ls_files")
        rows.append(
            {
                "paths": count,
                "seconds": round(elapsed, 4),
                "readiness_count": report["count"],
                "check_attr": check_attr,
                "lfs_ls_files": lfs,
            }
        )
        assert report["count"] == count
        assert check_attr["calls"] == math.ceil(count / CHECK_ATTR_CHUNK_SIZE)
        assert check_attr["max_seconds"] < 30
        assert lfs["calls"] == 1

    repo, sha, paths = _lfs_repo(tmp_path, 1000, name="lfs-direct-1000")
    before = len(events)
    direct_started = time.perf_counter()
    values = get_check_attr("filter", paths, cwd=repo, source=sha)
    direct_elapsed = time.perf_counter() - direct_started
    direct_calls = _summarize(events[before:], "check_attr")
    assert len(values) == 1000
    assert direct_calls["calls"] == 20
    assert direct_calls["max_seconds"] < 30

    real_run = subprocess.run

    def missing_lfs(cmd, **kwargs):
        if isinstance(cmd, (list, tuple)) and "lfs" in cmd:
            return subprocess.CompletedProcess(
                cmd, 1, stdout="", stderr="git: 'lfs' is not a git command"
            )
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", missing_lfs)
    missing_started = time.perf_counter()
    missing = get_lfs_ls_files_names(cwd=repo)
    missing_elapsed = time.perf_counter() - missing_started
    assert missing is None

    print(
        "LFS_SCALE "
        + json.dumps(
            {
                "chunk_size": CHECK_ATTR_CHUNK_SIZE,
                "rows": rows,
                "direct_check_attr_1000_seconds": round(direct_elapsed, 4),
                "direct_check_attr_calls": direct_calls,
                "missing_lfs_seconds": round(missing_elapsed, 4),
                "missing_lfs_result": missing,
            }
        ),
        file=sys.stderr,
    )
