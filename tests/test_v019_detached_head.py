"""Regression: detached HEAD still analyzes explicit revisions."""

import json
import subprocess

from preflight.change_facts import build_change_facts_report, file_types_for_change_facts
from preflight.cli import run
from preflight.config import normalize_config
from preflight.git import (
    ensure_revision_exists,
    get_collision_paths,
    get_diff_name_status,
    get_git_topology,
    get_unified_diff,
    parse_git_diff,
)
from preflight.pipeline import build_change_context
from preflight.report import build_revision_provenance


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


def detached_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    git(repo, "config", "core.autocrlf", "false")
    source = repo / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("count = 1\n", encoding="utf-8")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", "base")
    older = git(repo, "rev-parse", "HEAD").strip()
    source.write_text("count = 2\n", encoding="utf-8")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", "change")
    detached = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "checkout", "--detach", detached)
    assert git(repo, "branch", "--show-current").strip() == ""
    config_path = tmp_path / "preflight.json"
    config_path.write_text(
        json.dumps(
            {"ownership": [{"match": "prefix", "path": "src/", "owner": "Backend"}]}
        ),
        encoding="utf-8",
    )
    return repo, older, detached, config_path


def test_detached_sha_analysis_is_available_without_a_branch_name(tmp_path):
    repo, older, detached, _config_path = detached_repo(tmp_path)
    ensure_revision_exists(older, cwd=repo)
    ensure_revision_exists("HEAD", cwd=repo)
    ensure_revision_exists(detached, cwd=repo)

    topology = get_git_topology(older, detached, cwd=repo)
    assert topology["base_sha"] == older
    assert topology["head_sha"] == detached
    assert topology["merge_base"] == older
    assert topology["relationship"] == "LINEAR"

    raw_changes = parse_git_diff(get_diff_name_status(older, detached, cwd=repo))
    assert [(change["git_status"], change["path"]) for change in raw_changes] == [
        ("M", "src/app.py")
    ]
    config = normalize_config(
        {"ownership": [{"match": "prefix", "path": "src/", "owner": "Backend"}]}
    )
    analyzed = [build_change_context(change, config) for change in raw_changes]
    facts = build_change_facts_report(
        get_unified_diff(older, detached, cwd=repo),
        file_types_for_change_facts(analyzed),
    )
    assert facts["count"] == 1
    assert facts["files"][0]["facts"][0]["kind"] == "value_changed"
    assert get_collision_paths(topology, cwd=repo) == set()

    provenance = build_revision_provenance(
        older,
        detached,
        topology,
        current_head_sha=detached,
    )
    assert provenance["head"]["sha"] == detached
    assert provenance["head_is_current_checkout"] is True
    assert provenance["comparison"] == "merge-base...head"


def test_detached_checkout_keeps_sha_provenance(tmp_path):
    repo, older, detached, config_path = detached_repo(tmp_path)
    report = run(
        ["--base", older, "--head", detached, "--config", str(config_path)],
        cwd=repo,
    )
    assert report["branch"] == "DETACHED"
    provenance = report["revision_provenance"]
    assert provenance["head"]["sha"] == detached
    assert provenance["head_is_current_checkout"] is True
    assert provenance["comparison"] == "merge-base...head"
    assert report["changes"][0]["path"] == "src/app.py"
    assert report["change_facts"]["count"] == 1
    assert report["collisions"]["count"] == 0


def test_explicit_revisions_continue_when_head_is_detached(tmp_path):
    repo, older, detached, config_path = detached_repo(tmp_path)
    cases = [
        ["--base", older, "--config", str(config_path)],
        ["--base", older, "--head", "HEAD", "--config", str(config_path)],
        ["--base", older, "--head", detached, "--config", str(config_path)],
    ]
    for argv in cases:
        report = run(argv, cwd=repo)
        assert report["branch"] == "DETACHED"
        assert report["revision_provenance"]["head"]["sha"] == detached
        assert report["revision_provenance"]["head_is_current_checkout"] is True
        assert report["summary"]["total_changes"] == 1


def test_named_branch_label_is_unchanged(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    git(repo, "config", "core.autocrlf", "false")
    source = repo / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("count = 1\n", encoding="utf-8")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", "base")
    older = git(repo, "rev-parse", "HEAD").strip()
    source.write_text("count = 2\n", encoding="utf-8")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", "change")
    branch = git(repo, "branch", "--show-current").strip()
    config_path = tmp_path / "preflight.json"
    config_path.write_text(
        json.dumps(
            {"ownership": [{"match": "prefix", "path": "src/", "owner": "Backend"}]}
        ),
        encoding="utf-8",
    )
    report = run(["--base", older, "--config", str(config_path)], cwd=repo)
    assert branch
    assert branch != "DETACHED"
    assert report["branch"] == branch
    assert report["revision_provenance"]["head_is_current_checkout"] is True
