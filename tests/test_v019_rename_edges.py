"""v0.1.9 evidence: real Git rename and copy interpretation.

These tests follow the commands Repo Preflight already runs. They do not
force a copy status that those commands do not request.
"""

import json
import subprocess

from preflight.cli import run


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


def init_repo(tmp_path, ownership):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    git(repo, "config", "core.autocrlf", "false")
    config_path = tmp_path / "preflight.json"
    config_path.write_text(
        json.dumps({"ownership": ownership}),
        encoding="utf-8",
    )
    return repo, config_path


def commit_all(repo, message):
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def analyze(repo, base, config_path):
    return run(["--base", base, "--config", str(config_path)], cwd=repo)


def _rename_body(count):
    lines = [f"line{index} = {index}\n" for index in range(30)]
    lines.append(f"count = {count}\n")
    return "".join(lines)


def test_rename_within_same_owner_and_type(tmp_path):
    repo, config_path = init_repo(
        tmp_path,
        [{"match": "prefix", "path": "src/", "owner": "Backend"}],
    )
    source = repo / "src" / "a.py"
    source.parent.mkdir()
    source.write_text(_rename_body(1), encoding="utf-8")
    base = commit_all(repo, "base")
    git(repo, "mv", "src/a.py", "src/b.py")
    (repo / "src" / "b.py").write_text(_rename_body(2), encoding="utf-8")
    commit_all(repo, "rename")

    report = analyze(repo, base, config_path)
    assert len(report["changes"]) == 1
    change = report["changes"][0]
    assert change["git_status"] == "R"
    assert change["old_path"] == "src/a.py"
    assert change["path"] == "src/b.py"
    assert isinstance(change["similarity"], int)
    assert change["old_file_type"] == "source"
    assert change["file_type"] == "source"
    assert change["old_owner"] == "Backend"
    assert change["owner"] == "Backend"
    assert change["technical_risk"] == "MEDIUM"
    assert change["required_checks"] == ["build verification"]
    assert change["manual_review_required"] is True
    assert change["governance_issues"] == []
    facts = report["change_facts"]["files"]
    assert len(facts) == 1
    assert facts[0]["path"] == "src/b.py"
    assert facts[0]["facts"] == [
        {
            "kind": "value_changed",
            "key": "count",
            "before": "1",
            "after": "2",
            "old_line": 31,
            "new_line": 31,
        }
    ]


def test_tiny_file_rewrite_follows_git_delete_and_add(tmp_path):
    """Git's own rename detector misses a one-line file. Preflight must not invent R."""
    repo, config_path = init_repo(
        tmp_path,
        [
            {"match": "prefix", "path": "backend/", "owner": "Backend"},
            {"match": "prefix", "path": "frontend/", "owner": "Frontend"},
        ],
    )
    source = repo / "backend" / "a.py"
    source.parent.mkdir()
    source.write_text("count = 1\n", encoding="utf-8")
    base = commit_all(repo, "base")
    (repo / "frontend").mkdir()
    git(repo, "mv", "backend/a.py", "frontend/a.py")
    (repo / "frontend" / "a.py").write_text("count = 2\n", encoding="utf-8")
    commit_all(repo, "rewrite")

    name_status = git(
        repo,
        "diff",
        "--name-status",
        "--find-renames",
        f"{base}...HEAD",
    )
    report = analyze(repo, base, config_path)
    statuses = sorted(change["git_status"] for change in report["changes"])
    crossings = [
        issue["code"]
        for change in report["changes"]
        for issue in change["governance_issues"]
        if issue["code"] == "OWNERSHIP_BOUNDARY_CROSSING"
    ]
    assert name_status.splitlines() == ["D\tbackend/a.py", "A\tfrontend/a.py"]
    assert statuses == ["A", "D"]
    assert crossings == []
    deleted = next(change for change in report["changes"] if change["git_status"] == "D")
    assert deleted["technical_risk"] == "HIGH"
    assert deleted["path"] == "backend/a.py"


def test_rename_across_ownership_boundary_is_reported_once(tmp_path):
    repo, config_path = init_repo(
        tmp_path,
        [
            {"match": "prefix", "path": "backend/", "owner": "Backend"},
            {"match": "prefix", "path": "frontend/", "owner": "Frontend"},
        ],
    )
    source = repo / "backend" / "a.py"
    source.parent.mkdir()
    source.write_text("count = 1\n", encoding="utf-8")
    base = commit_all(repo, "base")
    (repo / "frontend").mkdir()
    git(repo, "mv", "backend/a.py", "frontend/a.py")
    commit_all(repo, "move")

    report = analyze(repo, base, config_path)
    assert len(report["changes"]) == 1
    change = report["changes"][0]
    assert change["git_status"] == "R"
    assert change["old_path"] == "backend/a.py"
    assert change["path"] == "frontend/a.py"
    assert change["old_owner"] == "Backend"
    assert change["owner"] == "Frontend"
    assert change["old_file_type"] == "source"
    assert change["file_type"] == "source"
    crossings = [
        issue
        for issue in change["governance_issues"]
        if issue["code"] == "OWNERSHIP_BOUNDARY_CROSSING"
    ]
    assert crossings == [
        {
            "code": "OWNERSHIP_BOUNDARY_CROSSING",
            "priority": "HIGH",
            "message": "Ownership changed from Backend to Frontend",
        }
    ]
    assert report["summary"]["governance_issue_count"] == 1
    assert change["manual_review_required"] is True


def test_rename_across_file_type_keeps_old_and_new_classification(tmp_path):
    repo, config_path = init_repo(
        tmp_path,
        [
            {"match": "prefix", "path": "src/", "owner": "Product"},
            {"match": "prefix", "path": "assets/", "owner": "Product"},
        ],
    )
    source = repo / "src" / "item.py"
    source.parent.mkdir()
    source.write_text("count = 1\n", encoding="utf-8")
    base = commit_all(repo, "base")
    (repo / "assets").mkdir()
    git(repo, "mv", "src/item.py", "assets/item.uasset")
    commit_all(repo, "retype")

    report = analyze(repo, base, config_path)
    assert len(report["changes"]) == 1
    change = report["changes"][0]
    assert change["git_status"] == "R"
    assert change["old_path"] == "src/item.py"
    assert change["path"] == "assets/item.uasset"
    assert change["old_file_type"] == "source"
    assert change["file_type"] == "asset"
    assert change["old_owner"] == "Product"
    assert change["owner"] == "Product"
    assert change["technical_risk"] == "MEDIUM"
    assert change["required_checks"] == ["build verification", "asset verification"]
    assert change["manual_review_required"] is True
    assert change["governance_issues"] == []
    assert report["change_facts"]["files"] == []
    assert report["binary_readiness"]["count"] == 1
    assert report["binary_readiness"]["files"][0]["path"] == "assets/item.uasset"
    assert report["binary_readiness"]["files"][0]["file_type"] == "asset"


def test_unchanged_copy_is_not_emitted_as_copy_status(tmp_path):
    repo, config_path = init_repo(
        tmp_path,
        [{"match": "prefix", "path": "src/", "owner": "Backend"}],
    )
    source = repo / "src" / "a.py"
    source.parent.mkdir()
    source.write_text("count = 1\n", encoding="utf-8")
    base = commit_all(repo, "base")
    (repo / "src" / "a_copy.py").write_text("count = 1\n", encoding="utf-8")
    commit_all(repo, "copy")

    preflight_status = git(
        repo,
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        "--no-ext-diff",
        "--no-textconv",
        f"{base}...HEAD",
    )
    copy_status = git(
        repo,
        "diff",
        "--name-status",
        "--find-copies",
        "--find-renames",
        f"{base}...HEAD",
    )
    harder_status = git(
        repo,
        "diff",
        "--name-status",
        "--find-copies-harder",
        "--find-renames",
        f"{base}...HEAD",
    )
    report = analyze(repo, base, config_path)
    change = report["changes"][0]

    assert change["git_status"] == "A"
    assert change["path"] == "src/a_copy.py"
    assert "old_path" not in change
    assert "C" not in preflight_status.split("\0")[0]
    assert report["summary"]["governance_issue_count"] == 0
    print(
        "COPY_EVIDENCE "
        + json.dumps(
            {
                "preflight_git_status": change["git_status"],
                "preflight_name_status": preflight_status.replace("\0", "|"),
                "find_copies": copy_status.strip(),
                "find_copies_harder": harder_status.strip(),
            }
        )
    )
