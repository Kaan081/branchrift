import json
import os
import subprocess
import sys
from pathlib import Path

from preflight.binary_readiness import (
    build_binary_readiness_report,
    classify_binary_readiness,
    is_lfs_pointer_text,
)
from preflight.git import get_lfs_ls_files_names
from preflight.report import build_report
from preflight.reporter import print_json_report, print_report


GOVERNANCE = {
    "critical_escalation": True,
    "critical_unknown_count": 5,
    "critical_unknown_ratio": 0.25,
}

POINTER_TEXT = (
    "version https://git-lfs.github.com/spec/v1\n"
    "oid sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
    "size 12345\n"
)


def _change(path, file_type, status="M"):
    return {
        "path": path,
        "file_type": file_type,
        "git_status": status,
        "owner": "Art",
        "technical_risk": "MEDIUM",
        "confidence": "LOW",
        "required_checks": ["asset verification"],
        "governance_issues": [],
        "manual_review_required": True,
    }


def _write(repo, relative, data):
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    return relative


def test_is_lfs_pointer_text_requires_version_oid_and_size():
    assert is_lfs_pointer_text(POINTER_TEXT) is True
    assert is_lfs_pointer_text("version https://git-lfs.github.com/spec/v1\n") is False
    assert is_lfs_pointer_text("small text file\n") is False


def test_non_lfs_binary_sensitive_file(tmp_path):
    path = "Content/Thing.uasset"
    _write(tmp_path, path, b"\x00binary-asset-bytes\x00")
    report = build_binary_readiness_report(
        [_change(path, "asset")],
        cwd=tmp_path,
        analyzed_head_sha="abc",
        current_head_sha="abc",
        attr_values={path: "unspecified"},
        lfs_names=None,
    )
    item = report["files"][0]
    assert item["lfs_managed"] is False
    assert item["lfs_state"] == "not_lfs"
    assert item["readiness"] == "ready"
    assert report["attention_count"] == 0


def test_lfs_managed_hydrated_file(tmp_path):
    path = "Content/Maps/LV_HPD_NetTest.umap"
    _write(tmp_path, path, b"\x00hydrated-umap-bytes\x00")
    report = build_binary_readiness_report(
        [_change(path, "map")],
        cwd=tmp_path,
        analyzed_head_sha="abc",
        current_head_sha="abc",
        attr_values={path: "lfs"},
        lfs_names={path},
    )
    item = report["files"][0]
    assert item["lfs_managed"] is True
    assert item["lfs_state"] == "hydrated"
    assert item["readiness"] == "ready"
    assert item["working_tree_state"] == "present"
    assert "reason" not in item


def test_lfs_pointer_present_in_working_tree(tmp_path):
    path = "Content/Maps/LV_HPD_NetTest.umap"
    _write(tmp_path, path, POINTER_TEXT)
    report = build_binary_readiness_report(
        [_change(path, "map")],
        cwd=tmp_path,
        analyzed_head_sha="abc",
        current_head_sha="abc",
        attr_values={path: "lfs"},
        lfs_names=None,
    )
    item = report["files"][0]
    assert item["lfs_managed"] is True
    assert item["lfs_state"] == "pointer"
    assert item["readiness"] == "attention"
    assert "LFS pointer" in item["reason"]


def test_git_lfs_unavailable_does_not_crash(tmp_path, monkeypatch):
    path = "Content/Thing.uasset"
    _write(tmp_path, path, b"\x00data\x00")
    report = build_binary_readiness_report(
        [_change(path, "asset")],
        cwd=tmp_path,
        analyzed_head_sha="abc",
        current_head_sha="abc",
        attr_values={path: "lfs"},
        lfs_names=None,
    )
    assert report["files"][0]["lfs_managed"] is True
    assert report["files"][0]["lfs_state"] == "hydrated"

    from preflight.errors import GitError
    from preflight import git as gitmod

    def boom(*_args, **_kwargs):
        raise GitError("git-lfs was not found")

    monkeypatch.setattr(gitmod, "run_git", boom)
    assert get_lfs_ls_files_names(cwd=tmp_path) is None


def test_intentionally_deleted_binary_file(tmp_path):
    path = "Content/Gone.uasset"
    report = build_binary_readiness_report(
        [_change(path, "asset", status="D")],
        cwd=tmp_path,
        analyzed_head_sha="abc",
        current_head_sha="abc",
        attr_values={path: "lfs"},
        lfs_names=None,
    )
    item = report["files"][0]
    assert item["readiness"] == "ready"
    assert item["working_tree_state"] == "deleted"
    assert "intentionally deleted" in item["reason"]


def test_unexpectedly_missing_relevant_file(tmp_path):
    path = "Content/Missing.umap"
    report = build_binary_readiness_report(
        [_change(path, "map")],
        cwd=tmp_path,
        analyzed_head_sha="abc",
        current_head_sha="abc",
        attr_values={path: "lfs"},
        lfs_names=None,
    )
    item = report["files"][0]
    assert item["working_tree_state"] == "missing"
    assert item["lfs_state"] == "missing"
    assert item["readiness"] == "attention"
    assert "missing from the working tree" in item["reason"]


def test_source_only_repo_produces_no_readiness_report():
    report = build_binary_readiness_report(
        [_change("src/app.py", "source")],
        cwd=None,
        analyzed_head_sha="abc",
        current_head_sha="abc",
        attr_values={},
        lfs_names=None,
    )
    assert report is None


def test_existing_change_facts_and_verdicts_remain_unchanged():
    facts = {"count": 1, "files": [{"path": "src/app.py", "facts": [{"kind": "line_added", "text": "x", "new_line": 1}]}]}
    readiness = {
        "count": 1,
        "attention_count": 1,
        "files": [
            {
                "path": "Content/Thing.uasset",
                "file_type": "asset",
                "git_status": "M",
                "lfs_managed": True,
                "working_tree_state": "present",
                "lfs_state": "pointer",
                "readiness": "attention",
                "reason": "working tree contains an LFS pointer instead of hydrated binary content",
            }
        ],
    }
    report = build_report(
        "feature/x",
        "main",
        [_change("src/app.py", "source")],
        GOVERNANCE,
        False,
        change_facts=facts,
        binary_readiness=readiness,
    )
    assert report["change_facts"] == facts
    assert report["technical_risk"] == "MEDIUM"
    assert report["governance_status"] == "PASS"
    assert report["binary_readiness"]["attention_count"] == 1


def test_text_and_json_readiness_output(capsys):
    hydrated = {
        "path": "Content/Maps/LV_HPD_NetTest.umap",
        "file_type": "map",
        "git_status": "M",
        "lfs_managed": True,
        "working_tree_state": "present",
        "lfs_state": "hydrated",
        "readiness": "ready",
    }
    pointer = {
        "path": "Content/Assets/Test.uasset",
        "file_type": "asset",
        "git_status": "M",
        "lfs_managed": True,
        "working_tree_state": "present",
        "lfs_state": "pointer",
        "readiness": "attention",
        "reason": "working tree contains an LFS pointer instead of hydrated binary content",
    }
    report = build_report(
        "feature/x",
        "main",
        [],
        GOVERNANCE,
        False,
        change_facts={"count": 0, "files": []},
        binary_readiness={"count": 2, "attention_count": 1, "files": [hydrated, pointer]},
    )
    print_report(report)
    output = capsys.readouterr().out
    assert "What changed:" in output
    assert "Repository readiness:" in output
    assert "Content/Maps/LV_HPD_NetTest.umap" in output
    assert "State: hydrated" in output
    assert "Readiness: ready" in output
    assert "Content/Assets/Test.uasset" in output
    assert "State: pointer" in output
    assert "Readiness: attention" in output
    assert "Technical risk: LOW" in output
    assert "Governance:" in output
    assert "PASS" in output

    print_json_report(report)
    payload = json.loads(capsys.readouterr().out)
    assert payload["binary_readiness"]["files"][1]["lfs_managed"] is True
    assert payload["binary_readiness"]["files"][1]["readiness"] == "attention"
    assert payload["change_facts"]["count"] == 0
    assert "YES" not in json.dumps(payload["binary_readiness"])


def test_source_only_report_omits_noisy_readiness_section(capsys):
    report = build_report(
        "feature/x",
        "main",
        [],
        GOVERNANCE,
        False,
        change_facts={"count": 0, "files": []},
    )
    print_report(report)
    output = capsys.readouterr().out
    assert "Repository readiness:" not in output
    assert "change_facts" in json.dumps(report) or "change_facts" in report
    assert "binary_readiness" not in report


def test_classify_pointer_without_attr_still_attention():
    result = classify_binary_readiness(
        git_status="M",
        lfs_managed=None,
        exists=True,
        is_pointer=True,
        worktree_matches_head=True,
    )
    assert result["lfs_state"] == "pointer"
    assert result["readiness"] == "attention"
    assert result["lfs_managed"] is True


def test_historical_head_does_not_inherit_current_checkout_hydration(tmp_path):
    path = "Content/Project2/VSlice/Gameplay/BP_VSliceThreat.uasset"
    _write(tmp_path, path, b"\x00hydrated-from-checkout-C\x00")
    report = build_binary_readiness_report(
        [_change(path, "asset")],
        cwd=tmp_path,
        analyzed_head_sha="b" * 40,
        current_head_sha="c" * 40,
        head_is_current_checkout=False,
        attr_values={path: "lfs"},
        lfs_names={path},
    )
    item = report["files"][0]
    assert item["lfs_managed"] is True
    assert item["lfs_state"] != "hydrated"
    assert item["readiness"] != "ready"
    assert item["lfs_state"] == "unknown"
    assert item["readiness"] == "unknown"
    assert item["working_tree_state"] == "unknown"
    assert item["reason"] == "analyzed_head_not_current_checkout"


def git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def test_cli_historical_head_does_not_report_checkout_hydration(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    path = "Content/Project2/VSlice/Gameplay/BP_VSliceThreat.uasset"
    asset = repo / path
    asset.parent.mkdir(parents=True)
    (repo / ".gitattributes").write_text("*.uasset filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
    config_path = repo / ".preflight.json"
    config_path.write_text(
        json.dumps({"ownership": [{"match": "prefix", "path": "Content/", "owner": "Art"}]}),
        encoding="utf-8",
    )
    asset.write_bytes(b"base-bytes")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "checkout", "-b", "feature/b")
    asset.write_bytes(b"head-B-bytes")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "head-B")
    head_b = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "checkout", "-b", "verify/c")
    asset.write_bytes(b"\x00hydrated-checkout-C-bytes\x00")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "checkout-C")
    checkout_c = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert checkout_c != head_b

    env = os.environ.copy()
    src_path = str((Path(__file__).parents[1] / "src").resolve())
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "preflight",
            "--base",
            base_sha,
            "--head",
            head_b,
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
    assert report["revision_provenance"]["head_is_current_checkout"] is False
    assert report["revision_provenance"]["head"]["sha"] == head_b
    item = next(
        entry
        for entry in report["binary_readiness"]["files"]
        if entry["path"] == path
    )
    assert item["lfs_state"] != "hydrated"
    assert item["readiness"] != "ready"
    assert item["reason"] == "analyzed_head_not_current_checkout"
    assert report["technical_risk"] in {"LOW", "MEDIUM", "HIGH"}
    assert report["governance_status"] in {"PASS", "ATTENTION", "CRITICAL"}


def test_historical_head_ignores_current_checkout_lfs_names(tmp_path):
    path = "Content/Thing.uasset"
    _write(tmp_path, path, b"\x00hydrated-from-C\x00")
    report = build_binary_readiness_report(
        [_change(path, "asset")],
        cwd=tmp_path,
        analyzed_head_sha="b" * 40,
        current_head_sha="c" * 40,
        head_is_current_checkout=False,
        attr_values={path: "unspecified"},
        lfs_names={path},
    )
    item = report["files"][0]
    assert item["lfs_managed"] is False
    assert item["lfs_state"] == "unknown"
    assert item["readiness"] == "unknown"
    assert item["reason"] == "analyzed_head_not_current_checkout"


def _run_preflight_json(repo, config_path, *extra_args):
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


def _init_content_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    path = "Content/Project2/VSlice/Gameplay/BP_VSliceThreat.uasset"
    asset = repo / path
    asset.parent.mkdir(parents=True)
    config_path = repo / ".preflight.json"
    config_path.write_text(
        json.dumps({"ownership": [{"match": "prefix", "path": "Content/", "owner": "Art"}]}),
        encoding="utf-8",
    )
    return repo, path, asset, config_path


def test_cli_attribute_drift_keeps_historical_lfs_managed(tmp_path):
    repo, path, asset, config_path = _init_content_repo(tmp_path)
    (repo / ".gitattributes").write_text(
        "*.uasset filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    asset.write_bytes(b"base-bytes")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    asset.write_bytes(b"head-B-bytes")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "head-B")
    head_b = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "checkout", "-b", "verify/c")
    (repo / ".gitattributes").write_text("# LFS rule removed at checkout C\n", encoding="utf-8")
    asset.write_bytes(b"\x00hydrated-checkout-C\x00")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "checkout-C")

    result = _run_preflight_json(repo, config_path, "--base", base_sha, "--head", head_b)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["revision_provenance"]["head_is_current_checkout"] is False
    item = next(entry for entry in report["binary_readiness"]["files"] if entry["path"] == path)
    assert item["lfs_managed"] is True
    assert item["lfs_state"] == "unknown"
    assert item["readiness"] == "unknown"
    assert item["reason"] == "analyzed_head_not_current_checkout"
    assert report["technical_risk"] in {"LOW", "MEDIUM", "HIGH"}
    assert report["governance_status"] in {"PASS", "ATTENTION", "CRITICAL"}


def test_cli_attribute_drift_does_not_inherit_later_lfs_rule(tmp_path):
    repo, path, asset, config_path = _init_content_repo(tmp_path)
    asset.write_bytes(b"base-bytes")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    asset.write_bytes(b"head-B-bytes")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "head-B")
    head_b = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "checkout", "-b", "verify/c")
    (repo / ".gitattributes").write_text(
        "*.uasset filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    asset.write_bytes(b"\x00hydrated-and-lfs-at-C\x00")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "checkout-C")

    result = _run_preflight_json(repo, config_path, "--base", base_sha, "--head", head_b)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["revision_provenance"]["head_is_current_checkout"] is False
    item = next(entry for entry in report["binary_readiness"]["files"] if entry["path"] == path)
    assert item["lfs_managed"] is not True
    assert item["lfs_managed"] is False
    assert item["lfs_state"] == "unknown"
    assert item["readiness"] == "unknown"
    assert item["reason"] == "analyzed_head_not_current_checkout"
