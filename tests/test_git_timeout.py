import json
import subprocess

import pytest

from preflight.binary_readiness import build_binary_readiness_report
from preflight.errors import GitError, GitTimeoutError
from preflight.git import (
    TIMEOUT_EXPENSIVE_SECONDS,
    TIMEOUT_FAST_SECONDS,
    TIMEOUT_NORMAL_SECONDS,
    get_check_attr,
    get_changed_paths,
    get_current_branch,
    get_lfs_ls_files_names,
    get_unified_diff,
    resolve_commit_sha,
    run_git,
    timeout_for_operation,
)


def _complete(cmd, stdout="ok\n", returncode=0, stderr=""):
    return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)


def test_timeout_policy_assigns_larger_budget_to_expensive_operations():
    assert timeout_for_operation("rev_parse") == TIMEOUT_FAST_SECONDS
    assert timeout_for_operation("merge_base") == TIMEOUT_FAST_SECONDS
    assert timeout_for_operation("name_status") == TIMEOUT_NORMAL_SECONDS
    assert timeout_for_operation("unified_diff") == TIMEOUT_EXPENSIVE_SECONDS
    assert timeout_for_operation("collision_scan") == TIMEOUT_EXPENSIVE_SECONDS
    assert timeout_for_operation("lfs_ls_files") == TIMEOUT_EXPENSIVE_SECONDS
    assert timeout_for_operation("unified_diff") > timeout_for_operation("rev_parse")
    assert timeout_for_operation("collision_scan") > timeout_for_operation("status")


def test_subprocess_receives_operation_timeout_budget(monkeypatch):
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(kwargs.get("timeout"))
        return _complete(cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    resolve_commit_sha("HEAD")
    get_unified_diff("base", "HEAD")
    get_changed_paths("abc", "def")
    get_current_branch()

    assert captured[0] == TIMEOUT_FAST_SECONDS
    assert captured[1] == TIMEOUT_EXPENSIVE_SECONDS
    assert captured[2] == TIMEOUT_EXPENSIVE_SECONDS
    assert captured[3] == TIMEOUT_FAST_SECONDS


def test_fast_required_timeout_is_fatal(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitTimeoutError, match="Operation: rev_parse") as exc:
        resolve_commit_sha("HEAD")
    text = str(exc.value)
    assert "Git operation timed out" in text
    assert f"Timeout: {TIMEOUT_FAST_SECONDS}s" in text


def test_expensive_required_timeout_is_fatal(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitTimeoutError) as exc:
        get_unified_diff("base", "HEAD")
    text = str(exc.value)
    assert "Git operation timed out" in text
    assert "Operation: unified_diff" in text
    assert f"Timeout: {TIMEOUT_EXPENSIVE_SECONDS}s" in text
    assert "--unified" not in text


def test_optional_lfs_timeout_degrades_to_unknown(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        if len(cmd) > 1 and cmd[1] == "lfs":
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
        if "check-attr" in cmd:
            return _complete(cmd, stdout="Content/Thing.uasset: filter: lfs\n")
        return _complete(cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert get_lfs_ls_files_names(cwd=tmp_path) is None

    path = "Content/Thing.uasset"
    (tmp_path / "Content").mkdir()
    (tmp_path / path).write_bytes(b"\x00data\x00")
    report = build_binary_readiness_report(
        [
            {
                "path": path,
                "file_type": "asset",
                "git_status": "M",
            }
        ],
        cwd=tmp_path,
        analyzed_head_sha="abc",
        current_head_sha="abc",
        head_is_current_checkout=True,
    )
    item = report["files"][0]
    assert item["lfs_managed"] is True
    assert item["readiness"] == "ready"
    assert item["lfs_state"] == "hydrated"


def test_optional_check_attr_timeout_degrades(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    values = get_check_attr("filter", ["Content/Thing.uasset"])
    assert values["Content/Thing.uasset"] is None
    values = get_check_attr(
        "filter",
        ["Content/Thing.uasset"],
        source="b" * 40,
    )
    assert values["Content/Thing.uasset"] is None


def test_check_attr_uses_revision_source(monkeypatch):
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return _complete(cmd, stdout="Content/Thing.uasset: filter: lfs\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    source = "b" * 40
    values = get_check_attr("filter", ["Content/Thing.uasset"], source=source)
    assert values["Content/Thing.uasset"] == "lfs"
    assert f"--source={source}" in captured[0]
    assert captured[0][1] == "check-attr"


def test_revision_scoped_attr_timeout_does_not_fail_readiness(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    path = "Content/Thing.uasset"
    report = build_binary_readiness_report(
        [{"path": path, "file_type": "asset", "git_status": "M"}],
        cwd=tmp_path,
        analyzed_head_sha="b" * 40,
        current_head_sha="c" * 40,
        head_is_current_checkout=False,
        lfs_names=None,
    )
    item = report["files"][0]
    assert item["lfs_managed"] is None
    assert item["lfs_state"] == "unknown"
    assert item["readiness"] == "unknown"
    assert item["reason"] == "analyzed_head_not_current_checkout"


def test_existing_nonzero_git_error_is_unchanged(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _complete(cmd, stdout="", returncode=1, stderr="fatal: bad object")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitError, match="fatal: bad object"):
        run_git(["rev-parse", "nope"], operation="rev_parse")


def test_unified_diff_preserves_utf8_outside_ansi_code_page(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Preflight Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    note = repo / "Docs" / "note.md"
    note.parent.mkdir()
    note.write_text("plain\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    note.write_text("Breaking Line \u2014 Pass A \u201dquote\u201d\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "note"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    diff = get_unified_diff(base, "HEAD", cwd=repo)
    assert "\u2014" in diff
    assert "\u201d" in diff


def test_undecodable_git_output_is_a_git_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=None, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitError, match="undecodable output"):
        run_git(["diff"], operation="unified_diff")


def test_git_output_uses_utf8_and_replaces_malformed_bytes(monkeypatch):
    def fake_run(cmd, **kwargs):
        decoded = b"caf\xe9 \xff\n".decode(kwargs["encoding"], kwargs["errors"])
        return _complete(cmd, stdout=decoded)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = run_git(["diff"], operation="unified_diff")
    assert output == "caf\ufffd \ufffd\n"


def test_source_only_preflight_survives_missing_lfs(tmp_path, monkeypatch):
    real_run = subprocess.run

    def wrapped(cmd, **kwargs):
        if isinstance(cmd, (list, tuple)) and "lfs" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout="",
                stderr="git: 'lfs' is not a git command",
            )
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", wrapped)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Preflight Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    source = repo / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("count = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    source.write_text("count = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "change"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    config_path = tmp_path / "preflight.json"
    config_path.write_text(
        json.dumps(
            {"ownership": [{"match": "prefix", "path": "src/", "owner": "Code"}]}
        ),
        encoding="utf-8",
    )

    from preflight.cli import run

    report = run(["--base", base, "--config", str(config_path)], cwd=repo)
    assert report["summary"]["total_changes"] == 1
    assert report["changes"][0]["path"] == "src/app.py"


def test_missing_git_executable_message_is_unchanged(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitError, match="Git executable was not found"):
        run_git(["status"], operation="status")
