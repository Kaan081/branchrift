"""Regression: LFS transport stays separate from semantic file type."""

import json
import subprocess

from preflight.change_facts import extract_change_facts
from preflight.cli import run


POINTER_TEXT = (
    "version https://git-lfs.github.com/spec/v1\n"
    "oid sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
    "size 128\n"
)
WAV_PATH = "Audio/hit.wav"
ATTRIBUTES = "*.wav filter=lfs diff=lfs merge=lfs -text\n"


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


def wav_report(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    git(repo, "config", "core.autocrlf", "false")
    (repo / ".gitattributes").write_text(ATTRIBUTES, encoding="utf-8")
    git(repo, "add", "--", ".gitattributes")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD").strip()

    audio = repo / "Audio"
    audio.mkdir()
    (audio / "hit.wav").write_text(POINTER_TEXT, encoding="utf-8")
    git(repo, "add", "--", WAV_PATH)
    git(repo, "commit", "-m", "add wav pointer")

    config_path = tmp_path / "preflight.json"
    config_path.write_text(
        json.dumps(
            {"ownership": [{"match": "prefix", "path": "Audio/", "owner": "Audio"}]}
        ),
        encoding="utf-8",
    )
    return run(["--base", base, "--config", str(config_path)], cwd=repo)


def _wav_change(report):
    matches = [change for change in report["changes"] if change["path"] == WAV_PATH]
    assert len(matches) == 1
    return matches[0]


def _pointer_facts(report):
    facts = []
    for entry in report["change_facts"]["files"]:
        if entry["path"] != WAV_PATH:
            continue
        for fact in entry["facts"]:
            text = " ".join(
                str(fact.get(key, "")) for key in ("text", "key", "before", "after")
            )
            if (
                "git-lfs.github.com/spec/v1" in text
                or "oid sha256:" in text
                or text.strip().startswith("size ")
            ):
                facts.append(fact)
    return facts


def test_default_classification_keeps_wav_as_other_with_low_risk(tmp_path):
    report = wav_report(tmp_path)
    change = _wav_change(report)
    assert change["file_type"] == "other"
    assert change["technical_risk"] == "LOW"
    assert report["technical_risk"] == "LOW"


def test_lfs_managed_other_file_has_readiness_entry(tmp_path):
    report = wav_report(tmp_path)
    change = _wav_change(report)
    readiness_report = report.get("binary_readiness")
    files = [] if not readiness_report else readiness_report.get("files") or []
    readiness = [item for item in files if item["path"] == WAV_PATH]
    observed = {
        "file_type": change["file_type"],
        "technical_risk": change["technical_risk"],
        "report_technical_risk": report["technical_risk"],
        "binary_readiness_present": readiness_report is not None,
        "binary_readiness": readiness_report,
    }
    assert readiness, (
        "v0.1.8 produced no LFS readiness entry for a filter=lfs .wav path "
        "while leaving it outside asset/map classification:\n"
        + json.dumps(observed, indent=2, sort_keys=True)
    )
    assert readiness[0]["file_type"] == "other"
    assert readiness[0]["lfs_managed"] is True
    assert readiness[0]["lfs_state"]


def test_ordinary_size_text_is_not_treated_as_pointer_metadata():
    diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-size = 1
+size = 2
@@ -3 +3 @@
-size 128
+size 256
"""
    files = extract_change_facts(diff, {"src/app.py": "source"})
    assert len(files) == 1
    kinds = [fact["kind"] for fact in files[0]["facts"]]
    assert "value_changed" in kinds
    assert any(fact.get("text") == "size 128" for fact in files[0]["facts"])
    assert any(fact.get("text") == "size 256" for fact in files[0]["facts"])


def test_lfs_pointer_metadata_is_not_an_exact_change_fact(tmp_path):
    report = wav_report(tmp_path)
    facts = _pointer_facts(report)
    assert facts == []
    assert _wav_change(report)["file_type"] == "other"
