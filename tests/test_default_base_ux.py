"""Default base must be grounded in Git metadata, never guessed."""
import subprocess

import pytest

from preflight.cli import parse_args, resolve_default_base, run
from preflight.errors import GitError


def git(repo, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=True,
    )
    return result.stdout.strip()


def make_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "BranchRift Test")
    (source / "src").mkdir()
    (source / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    git(source, "add", ".")
    git(source, "commit", "-m", "base")
    return source


def make_clone(tmp_path):
    source = make_source(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "--bare", str(source), str(bare))
    clone = tmp_path / "clone"
    git(tmp_path, "clone", str(bare), str(clone))
    git(clone, "config", "user.email", "test@example.com")
    git(clone, "config", "user.name", "BranchRift Test")
    return clone, bare


def test_no_arg_parser_does_not_presume_dev():
    assert parse_args([]).base is None
    assert parse_args(["--base", "dev"]).base == "dev"


def test_default_base_uses_origin_head_and_cli_report(tmp_path, capsys):
    clone, _ = make_clone(tmp_path)
    assert git(clone, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") == "origin/main"
    git(clone, "switch", "-c", "feature/test")
    (clone / "src" / "app.py").write_text("value = 2\n", encoding="utf-8")
    git(clone, "add", ".")
    git(clone, "commit", "-m", "feature")
    assert resolve_default_base(cwd=clone) == "origin/main"
    report = run(["--json"], cwd=clone)
    capsys.readouterr()
    assert report["base"] == "origin/main"
    assert report["summary"]["total_changes"] == 1
    assert report["topology"]["relationship"] == "LINEAR"


def test_explicit_base_wins_even_when_remote_head_exists(tmp_path, capsys):
    clone, _ = make_clone(tmp_path)
    git(clone, "branch", "dev")
    git(clone, "switch", "-c", "feature/test")
    (clone / "src" / "app.py").write_text("value = 3\n", encoding="utf-8")
    git(clone, "add", ".")
    git(clone, "commit", "-m", "feature")
    report = run(["--json", "--base", "dev"], cwd=clone)
    capsys.readouterr()
    assert report["base"] == "dev"
    assert report["revision_provenance"]["base"]["requested"] == "dev"


def test_fresh_local_repo_requires_explicit_base(tmp_path, capsys):
    source = make_source(tmp_path)
    with pytest.raises(GitError, match="Pass --base explicitly"):
        resolve_default_base(cwd=source)
    report = run(["--base", "main", "--json"], cwd=source)
    capsys.readouterr()
    assert report["base"] == "main"


def test_single_non_origin_remote_head_is_supported(tmp_path):
    clone, _ = make_clone(tmp_path)
    git(clone, "remote", "rename", "origin", "upstream")
    assert resolve_default_base(cwd=clone) == "upstream/main"


def test_ambiguous_remotes_require_base(tmp_path):
    clone, bare = make_clone(tmp_path)
    git(clone, "remote", "rename", "origin", "upstream")
    git(clone, "remote", "add", "backup", str(bare))
    with pytest.raises(GitError, match="Pass --base explicitly"):
        resolve_default_base(cwd=clone)


def test_missing_remote_head_does_not_fallback_to_guess(tmp_path):
    clone, _ = make_clone(tmp_path)
    git(clone, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
    with pytest.raises(GitError, match="Pass --base explicitly"):
        resolve_default_base(cwd=clone)
