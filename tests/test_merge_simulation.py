"""v0.4: real Git merge simulation, independent of path overlap reporting."""

import json
import subprocess
from pathlib import Path

import pytest

from preflight.merge_simulation import _parse_merge_output, simulate_merge


def _git(repo, *args, check=True):
    return subprocess.run(
        ["git", *args], cwd=repo, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=check,
    )


def _write(repo, rel, content):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _commit(repo, message):
    _git(repo, "add", "--", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip()


def _repo(tmp_path, main_change, feature_change, initial=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "BranchRift Test")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "core.autocrlf", "false")
    initial = initial or {"README.md": "base\n"}
    for path, content in initial.items():
        _write(repo, path, content)
    _commit(repo, "initial")
    default_branch = _git(repo, "branch", "--show-current").stdout.decode("utf-8").strip()
    _git(repo, "switch", "-c", "feature")
    for path, content in feature_change.items():
        _write(repo, path, content)
    feature_sha = _commit(repo, "feature")
    _git(repo, "switch", default_branch)
    for path, content in main_change.items():
        _write(repo, path, content)
    main_sha = _commit(repo, "main")
    return repo, main_sha, feature_sha


def _snapshot(repo):
    return (
        _git(repo, "rev-parse", "HEAD").stdout,
        _git(repo, "status", "--porcelain", "-z").stdout,
        _git(repo, "ls-files", "--stage", "-z").stdout,
    )


def test_clean_merge_is_not_a_build_or_test_claim(tmp_path):
    repo, base, head = _repo(
        tmp_path,
        main_change={"src/base.py": "main = True\n"},
        feature_change={"src/feature.py": "feature = True\n"},
    )
    before = _snapshot(repo)
    result = simulate_merge(base, head, cwd=repo)
    assert result["status"] == "CLEAN", result
    assert result["conflicted_paths"] == []
    assert result["integration_tests_executed"] is False
    assert result["result_tree_retained"] is False
    assert len(result["result_tree_oid"]) in (40, 64)
    assert _snapshot(repo) == before
    # The result tree was made in a disposable object directory, not repo/.git/objects.
    missing = _git(repo, "cat-file", "-e", result["result_tree_oid"], check=False)
    assert missing.returncode != 0


def test_actual_content_conflict_reports_path_and_preserves_checkout(tmp_path):
    repo, base, head = _repo(
        tmp_path,
        main_change={"shared.py": "value = 'main'\n"},
        feature_change={"shared.py": "value = 'feature'\n"},
        initial={"shared.py": "value = 'original'\n"},
    )
    before = _snapshot(repo)
    result = simulate_merge(base, head, cwd=repo)
    assert result["status"] == "CONFLICTS", result
    assert result["conflicted_paths"] == ["shared.py"]
    assert result["conflicted_path_count"] == 1
    assert _snapshot(repo) == before


def test_same_path_but_nonoverlapping_hunks_merge_cleanly(tmp_path):
    repo, base, head = _repo(
        tmp_path,
        main_change={"shared.py": "first\nsecond\nthird\nfourth changed\n"},
        feature_change={"shared.py": "first changed\nsecond\nthird\nfourth\n"},
        initial={"shared.py": "first\nsecond\nthird\nfourth\n"},
    )
    result = simulate_merge(base, head, cwd=repo)
    assert result["status"] == "CLEAN", result


def test_binary_sensitive_conflict_is_a_real_git_conflict(tmp_path):
    repo, base, head = _repo(
        tmp_path,
        main_change={"Content/Map.umap": b"\x00binary-main\n"},
        feature_change={"Content/Map.umap": b"\x00binary-feature\n"},
        initial={"Content/Map.umap": b"\x00binary-original\n"},
    )
    result = simulate_merge(base, head, cwd=repo)
    assert result["status"] == "CONFLICTS", result
    assert result["conflicted_paths"] == ["Content/Map.umap"]


def test_utf8_path_preserved_from_nul_records(tmp_path):
    path = "src/çağrı_İ.py"
    repo, base, head = _repo(
        tmp_path,
        main_change={path: "winner = 'main'\n"},
        feature_change={path: "winner = 'feature'\n"},
        initial={path: "winner = 'original'\n"},
    )
    result = simulate_merge(base, head, cwd=repo)
    assert result["status"] == "CONFLICTS", result
    assert result["conflicted_paths"] == [path]


def test_wrong_sha_returns_error_without_executing_merge(tmp_path):
    result = simulate_merge("main; rm -rf .", "a" * 40, cwd=tmp_path)
    assert result["status"] == "ERROR"
    assert result["result_tree_oid"] is None


def test_old_git_reports_unknown(monkeypatch, tmp_path):
    from preflight import merge_simulation as sim

    def fake_git(args, cwd, **kwargs):
        assert args == ["--version"]
        return subprocess.CompletedProcess(args, 0, b"git version 2.37.6\n", b"")

    monkeypatch.setattr(sim, "_git_call", fake_git)
    result = sim.simulate_merge("a" * 40, "b" * 40, cwd=tmp_path)
    assert result["status"] == "UNKNOWN"
    assert result["conflicted_paths"] == []


def test_malformed_git_output_cannot_be_clean():
    with pytest.raises(ValueError):
        _parse_merge_output(b"hello\0")
    with pytest.raises(ValueError):
        _parse_merge_output(b"a" * 40 + b"\n")


def test_cli_option_is_opt_in_and_json_is_additive(tmp_path, capsys):
    from preflight.cli import parse_args, run

    assert parse_args(["--base", "main"]).simulate_merge is False
    assert parse_args(["--base", "main", "--simulate-merge", "--json"]).simulate_merge is True

    repo, base, head = _repo(
        tmp_path,
        main_change={"src/first.py": "main = True\n"},
        feature_change={"src/second.py": "feature = True\n"},
    )
    old_report = run(["--base", base, "--head", head, "--json"], cwd=repo)
    old_payload = json.loads(capsys.readouterr().out)
    assert "merge_simulation" not in old_report
    assert "merge_simulation" not in old_payload

    new_report = run(["--base", base, "--head", head, "--json", "--simulate-merge"], cwd=repo)
    new_payload = json.loads(capsys.readouterr().out)
    assert new_report["merge_simulation"]["status"] == "CLEAN"
    assert new_payload["merge_simulation"] == new_report["merge_simulation"]
    assert new_payload["schema_version"] == old_payload["schema_version"]
    assert _git(repo, "status", "--porcelain").stdout == b""


def test_cli_distinguishes_same_path_overlap_from_actual_git_conflict(tmp_path, capsys):
    from preflight.cli import run

    repo, base, head = _repo(
        tmp_path,
        main_change={"shared.py": "first\nsecond\nthird\nfourth changed\n"},
        feature_change={"shared.py": "first changed\nsecond\nthird\nfourth\n"},
        initial={"shared.py": "first\nsecond\nthird\nfourth\n"},
    )
    report = run(["--base", base, "--head", head, "--json", "--simulate-merge"], cwd=repo)
    capsys.readouterr()
    assert report["collisions"]["count"] == 1
    assert report["merge_simulation"]["status"] == "CLEAN"


def test_cli_reports_true_conflict_in_human_modes(tmp_path, capsys):
    from preflight.cli import run

    repo, base, head = _repo(
        tmp_path,
        main_change={"shared.py": "value = 'main'\n"},
        feature_change={"shared.py": "value = 'feature'\n"},
        initial={"shared.py": "value = 'original'\n"},
    )
    report = run(["--base", base, "--head", head, "--simulate-merge"], cwd=repo)
    compact = capsys.readouterr().out
    assert report["merge_simulation"]["status"] == "CONFLICTS"
    assert "Git merge simulation: CONFLICTS" in compact
    assert "build/tests not run" in compact
    run(["--base", base, "--head", head, "--simulate-merge", "--verbose"], cwd=repo)
    verbose = capsys.readouterr().out
    assert "Git merge simulation (opt-in):" in verbose
    assert "shared.py" in verbose
    assert "NOT RUN" in verbose
