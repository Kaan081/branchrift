"""Regression tests for BranchRift v0.2.1 Git path and binary-readiness hardening."""

import subprocess
from pathlib import Path

import pytest

from preflight.binary_readiness import (
    build_binary_readiness_report,
    inspect_worktree_file,
    parse_porcelain_paths,
)
from preflight.cli import run
from preflight.config import validate_config
from preflight.errors import ConfigError
from preflight.git import get_check_attr, get_worktree_status


def git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()


def init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "branchrift-test@example.com")
    git(repo, "config", "user.name", "BranchRift Test")
    git(repo, "config", "core.quotepath", "true")
    return repo


def test_nested_cli_uses_repo_root_for_binary_readiness(tmp_path):
    repo = init_repo(tmp_path)
    (repo / "Source").mkdir()
    asset = repo / "Content" / "Maps" / "Level.umap"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"first-version\x00")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    asset.write_bytes(b"second-version\x00")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "change binary")

    report = run(["--base", base, "--json"], cwd=repo / "Source")
    readiness = report["binary_readiness"]["files"]
    item = next(entry for entry in readiness if entry["path"] == "Content/Maps/Level.umap")
    assert item["working_tree_state"] == "present"
    assert item["readiness"] == "ready"


def test_binary_prefix_read_is_bounded(tmp_path, monkeypatch):
    asset = tmp_path / "large.uasset"
    asset.write_bytes(b"X" * (2 * 1024 * 1024))
    original_open = Path.open
    sizes = []

    class BoundedReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def read(self, size=-1):
            sizes.append(size)
            assert 0 <= size <= 1025
            return self.handle.read(size)

    def guarded_open(self, *args, **kwargs):
        handle = original_open(self, *args, **kwargs)
        if self == asset:
            return BoundedReader(handle)
        return handle

    monkeypatch.setattr(Path, "open", guarded_open)
    inspection = inspect_worktree_file(tmp_path, "large.uasset")
    assert inspection == {"exists": True, "pointer": False, "readable": True}
    assert sizes == [1025]


def test_read_failure_cannot_be_reported_as_hydrated(tmp_path, monkeypatch):
    relative = "Content/Locked.umap"
    asset = tmp_path / relative
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"hydrated\x00")
    original_open = Path.open

    def unreadable_asset(self, *args, **kwargs):
        if self == asset:
            raise PermissionError("simulated read denial")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable_asset)
    report = build_binary_readiness_report(
        [{"path": relative, "file_type": "map", "git_status": "M"}],
        cwd=tmp_path,
        analyzed_head_sha="a" * 40,
        current_head_sha="a" * 40,
        attr_values={relative: "lfs"},
        lfs_names={relative},
    )
    item = report["files"][0]
    assert item["working_tree_state"] == "present"
    assert item["lfs_state"] == "unknown"
    assert item["readiness"] == "attention"
    assert "read" in item["reason"]


def test_check_attr_unicode_git_path(tmp_path):
    repo = init_repo(tmp_path)
    (repo / ".gitattributes").write_text("*.uasset filter=lfs\n", encoding="utf-8")
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-m", "attributes")
    sha = git(repo, "rev-parse", "HEAD")
    path = "Content/çalışma.uasset"
    attrs = get_check_attr("filter", [path], cwd=repo, source=sha)
    assert attrs[path] == "lfs"


def test_status_unicode_and_rename_are_nul_safe(tmp_path):
    repo = init_repo(tmp_path)
    original = repo / "çalışma.txt"
    original.write_text("original\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")

    original.write_text("updated\n", encoding="utf-8")
    states = parse_porcelain_paths(get_worktree_status(cwd=repo))
    assert states["çalışma.txt"] == " M"

    git(repo, "add", "çalışma.txt")
    git(repo, "commit", "-m", "update")
    git(repo, "mv", "çalışma.txt", "new - filename.txt")
    states = parse_porcelain_paths(get_worktree_status(cwd=repo))
    assert states["new - filename.txt"] == "R "
    assert "çalışma.txt" not in states

    # Verify literal arrows separately; ">" is invalid in Windows filenames.
    synthetic = parse_porcelain_paths("R  new -> filename.txt\0çalışma.txt\0")
    assert synthetic["new -> filename.txt"] == "R "


def test_non_string_ownership_match_returns_config_error():
    with pytest.raises(ConfigError, match="Unsupported ownership match type"):
        validate_config(
            {"ownership": [{"match": ["prefix"], "path": "Source/", "owner": "Code"}]}
        )
