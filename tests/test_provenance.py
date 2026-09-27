import json
import os
import subprocess
import sys
from pathlib import Path

from preflight.git import get_git_topology
from preflight.report import COMPARISON_MERGE_BASE_HEAD, build_revision_provenance
from preflight.reporter import print_json_report


def git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    return repo


def write_config(repo):
    config_path = repo / ".preflight.json"
    config_path.write_text(
        json.dumps({"ownership": [{"match": "prefix", "path": "src/", "owner": "Backend"}]}),
        encoding="utf-8",
    )
    return config_path


def run_preflight_json(repo, config_path, *extra_args):
    env = os.environ.copy()
    src_path = str((Path(__file__).parents[1] / "src").resolve())
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "preflight",
            "--config",
            str(config_path),
            "--json",
            *extra_args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def test_symbolic_base_head_resolve_to_shas(tmp_path):
    repo = init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    write_config(repo)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base_branch = git(repo, "branch", "--show-current").stdout.strip()
    git(repo, "checkout", "-b", "feature/prov")
    (repo / "src" / "app.py").write_text("v2\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "head")

    topology = get_git_topology(base_branch, "feature/prov", cwd=repo)
    provenance = build_revision_provenance(
        base_branch,
        "feature/prov",
        topology,
        current_head_sha=topology["head_sha"],
    )
    assert provenance["base"]["requested"] == base_branch
    assert provenance["head"]["requested"] == "feature/prov"
    assert provenance["base"]["sha"] == topology["base_sha"]
    assert provenance["head"]["sha"] == topology["head_sha"]
    assert len(provenance["base"]["sha"]) >= 40
    assert provenance["merge_base_sha"] == topology["merge_base"]
    assert provenance["comparison"] == COMPARISON_MERGE_BASE_HEAD
    assert provenance["head_is_current_checkout"] is True


def test_explicit_commit_shas_and_merge_base(tmp_path):
    repo = init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "src" / "app.py").write_text("v2\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "head")
    head_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    topology = get_git_topology(base_sha, head_sha, cwd=repo)
    provenance = build_revision_provenance(base_sha, head_sha, topology, head_sha)
    assert provenance["base"]["requested"] == base_sha
    assert provenance["head"]["requested"] == head_sha
    assert provenance["base"]["sha"] == base_sha
    assert provenance["head"]["sha"] == head_sha
    assert provenance["merge_base_sha"] == base_sha


def test_provenance_survives_json_and_keeps_existing_keys(capsys):
    topology = {
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "merge_base": "a" * 40,
        "behind": 0,
        "ahead": 1,
        "relationship": "LINEAR",
        "ff_eligible": True,
    }
    provenance = build_revision_provenance("dev", "HEAD", topology, "b" * 40)
    report = {
        "branch": "feature/x",
        "base": "dev",
        "head": "HEAD",
        "repository_state": "CLEAN",
        "technical_risk": "LOW",
        "governance_status": "PASS",
        "summary": {},
        "changes": [],
        "topology": topology,
        "revision_provenance": provenance,
        "change_facts": {"count": 0, "comparison": "merge-base...head", "files": []},
    }
    print_json_report(report)
    payload = json.loads(capsys.readouterr().out)
    assert payload["base"] == "dev"
    assert payload["head"] == "HEAD"
    assert payload["topology"]["base_sha"] == "a" * 40
    assert payload["revision_provenance"]["comparison"] == "merge-base...head"
    assert payload["revision_provenance"]["head_is_current_checkout"] is True
    assert payload["change_facts"]["comparison"] == "merge-base...head"
    assert isinstance(payload["revision_provenance"]["head_is_current_checkout"], bool)


def test_non_current_head_is_not_current_checkout(tmp_path):
    repo = init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    config_path = write_config(repo)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base_branch = git(repo, "branch", "--show-current").stdout.strip()
    git(repo, "checkout", "-b", "feature/prov")
    (repo / "src" / "app.py").write_text("CatchRadius = 120.0f;\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "head")
    feature_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", base_branch)
    checkout_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    result = run_preflight_json(
        repo,
        config_path,
        "--base",
        base_branch,
        "--head",
        feature_sha,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    provenance = report["revision_provenance"]
    assert provenance["head"]["requested"] == feature_sha
    assert provenance["head"]["sha"] == feature_sha
    assert provenance["head_is_current_checkout"] is False
    assert provenance["merge_base_sha"] == report["topology"]["merge_base"]
    assert provenance["comparison"] == "merge-base...head"
    assert report["change_facts"]["comparison"] == "merge-base...head"
    assert report["topology"]["head_sha"] == feature_sha
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == checkout_sha
    assert report["technical_risk"] in {"LOW", "MEDIUM", "HIGH"}
    assert report["governance_status"] in {"PASS", "ATTENTION", "CRITICAL"}
    assert report["base"] == base_branch
    assert report["head"] == feature_sha


def test_cli_current_checkout_provenance(tmp_path):
    repo = init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    config_path = write_config(repo)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "src" / "app.py").write_text("v2\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "head")

    result = run_preflight_json(repo, config_path, "--base", base_sha)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    provenance = report["revision_provenance"]
    assert provenance["base"]["requested"] == base_sha
    assert provenance["head"]["requested"] == "HEAD"
    assert provenance["head"]["sha"] == report["topology"]["head_sha"]
    assert provenance["head_is_current_checkout"] is True
    assert provenance["comparison"] == report["change_facts"]["comparison"]
    assert "changes" in report
    assert "summary" in report
    assert "topology" in report
