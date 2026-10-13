import json
import os
import subprocess
import sys

from preflight.analyzer import analyze_change
from preflight.config import normalize_config
from preflight.git import get_diff_name_status, parse_git_diff
from preflight.pipeline import build_change_context
from preflight.report import build_report


def git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def create_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")

    src = repo / "src"
    src.mkdir()
    (src / "app.py").write_text('print("v1")\n', encoding="utf-8")

    config_data = {
        "ownership": [
            {"match": "prefix", "path": "src/", "owner": "Backend"},
            {"match": "path_exact", "path": "Dockerfile", "owner": "Platform"},
            {"match": "path_exact", "path": ".preflight.json", "owner": "Platform"},
        ]
    }
    config_path = repo / ".preflight.json"
    config_path.write_text(json.dumps(config_data), encoding="utf-8")

    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    base_branch = git(repo, "branch", "--show-current").stdout.strip()

    git(repo, "checkout", "-b", "feature/test")
    (src / "app.py").write_text('print("v2")\n', encoding="utf-8")
    (repo / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "feature changes")

    return repo, base_branch, config_path


def test_real_repository_pipeline(tmp_path):
    repo, base_branch, _ = create_repo(tmp_path)
    config = normalize_config(
        {
            "ownership": [
                {"match": "prefix", "path": "src/", "owner": "Backend"},
                {"match": "path_exact", "path": "Dockerfile", "owner": "Platform"},
            ]
        }
    )

    raw_changes = parse_git_diff(get_diff_name_status(base_branch, cwd=repo))
    analyzed = [
        analyze_change(build_change_context(raw_change, config))
        for raw_change in raw_changes
    ]
    report = build_report(
        "feature/test", base_branch, analyzed, config["governance"], False
    )

    assert report["summary"]["total_changes"] == 2
    assert report["technical_risk"] == "MEDIUM"
    assert report["governance_status"] == "PASS"
    assert report["summary"]["manual_review_count"] == 2
    assert set(report["summary"]["required_checks"]) == {
        "build verification",
        "build/config verification",
    }
    assert set(report["summary"]["owners"]) == {"Backend", "Platform"}


def test_cli_json_end_to_end(tmp_path):
    repo, base_branch, config_path = create_repo(tmp_path)

    env = os.environ.copy()
    src_path = str((__import__("pathlib").Path(__file__).parents[1] / "src").resolve())
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "preflight",
            "--base",
            base_branch,
            "--config",
            str(config_path),
            "--json",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["technical_risk"] == "MEDIUM"
    assert report["governance_status"] == "PASS"
    assert report["repository_state"] == "CLEAN"
    assert report["head"] == "HEAD"
    topology = report["topology"]
    assert topology["relationship"] == "LINEAR"
    assert topology["behind"] == 0
    assert topology["ahead"] > 0
    assert topology["ff_eligible"] is True
    assert topology["merge_base"] == topology["base_sha"]
    assert isinstance(topology["ff_eligible"], bool)


def test_cli_bad_config_returns_2(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    bad_config = repo / ".preflight.json"
    bad_config.write_text(
    '{"ownership": "Backend"}',
    encoding="utf-8",
)

    env = os.environ.copy()
    src_path = str((__import__("pathlib").Path(__file__).parents[1] / "src").resolve())
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "preflight", "--config", str(bad_config)],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 2
    assert "CONFIG ERROR:" in result.stderr


def test_cli_can_analyze_explicit_head_without_checkout(tmp_path):
    repo, base_branch, config_path = create_repo(tmp_path)
    feature_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", base_branch)

    env = os.environ.copy()
    src_path = str((__import__("pathlib").Path(__file__).parents[1] / "src").resolve())
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "preflight",
            "--base",
            base_branch,
            "--head",
            feature_commit,
            "--config",
            str(config_path),
            "--json",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["branch"] == base_branch
    assert report["head"] == feature_commit
    assert report["summary"]["total_changes"] == 2
    assert report["technical_risk"] == "MEDIUM"
    topology = report["topology"]
    assert topology["head_sha"] == feature_commit
    assert topology["relationship"] == "LINEAR"
    assert topology["ff_eligible"] is True
    assert git(repo, "branch", "--show-current").stdout.strip() == base_branch
