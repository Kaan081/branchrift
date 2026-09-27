import json
import os
import subprocess
import sys
from pathlib import Path

from preflight.change_facts import build_change_facts_report, parse_assignment
from preflight.report import build_report
from preflight.reporter import format_change_fact, print_json_report, print_report


GOVERNANCE = {
    "critical_escalation": True,
    "critical_unknown_count": 5,
    "critical_unknown_ratio": 0.25,
}


def unified_diff(path, body, old_line=10, new_line=10):
    minus = sum(1 for line in body.splitlines() if line.startswith("-"))
    plus = sum(1 for line in body.splitlines() if line.startswith("+"))
    old_count = f",{minus}" if minus != 1 else ""
    new_count = f",{plus}" if plus != 1 else ""
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -{old_line}{old_count} +{new_line}{new_count} @@\n"
        f"{body}"
    )


def facts_for(path, body, file_types=None, **kwargs):
    report = build_change_facts_report(
        unified_diff(path, body, **kwargs),
        file_types or {path: "source"},
    )
    if not report["files"]:
        return []
    return report["files"][0]["facts"]


def test_numeric_assignment_change():
    facts = facts_for(
        "HPDPrototypeCharacter.cpp",
        "-    CatchRadius = 140.0f;\n+    CatchRadius = 120.0f;\n",
    )
    assert facts == [
        {
            "kind": "value_changed",
            "key": "CatchRadius",
            "before": "140.0f",
            "after": "120.0f",
            "old_line": 10,
            "new_line": 10,
        }
    ]


def test_string_value_change():
    facts = facts_for(
        "src/app.py",
        '- name = "before";\n+ name = "after";\n',
    )
    assert facts[0]["kind"] == "value_changed"
    assert facts[0]["key"] == "name"
    assert facts[0]["before"] == '"before"'
    assert facts[0]["after"] == '"after"'


def test_boolean_value_change():
    facts = facts_for(
        "src/app.cpp",
        "-    bEnableAssist = false;\n+    bEnableAssist = true;\n",
    )
    assert facts[0]["kind"] == "value_changed"
    assert facts[0]["key"] == "bEnableAssist"
    assert facts[0]["before"] == "false"
    assert facts[0]["after"] == "true"


def test_json_and_yaml_key_changes():
    json_facts = facts_for(
        "config.json",
        '-  "timeout": 10\n+  "timeout": 20\n',
        file_types={"config.json": "other"},
    )
    yaml_facts = facts_for(
        "config.yaml",
        "- timeout: 10\n+ timeout: 20\n",
        file_types={"config.yaml": "other"},
    )
    assert json_facts[0]["kind"] == "value_changed"
    assert json_facts[0]["key"] == "timeout"
    assert json_facts[0]["before"] == "10"
    assert json_facts[0]["after"] == "20"
    assert yaml_facts[0]["key"] == "timeout"
    assert yaml_facts[0]["before"] == "10"
    assert yaml_facts[0]["after"] == "20"


def test_same_key_required_for_value_changed():
    parsed = parse_assignment("    CatchRadius = 140.0f;")
    assert parsed == ("CatchRadius", "140.0f")
    facts = facts_for(
        "src/app.cpp",
        "-    CatchRadius = 140;\n+    CatchRadius = 120;\n",
    )
    assert len(facts) == 1
    assert facts[0]["kind"] == "value_changed"
    assert facts[0]["key"] == "CatchRadius"


def test_different_lhs_lines_are_not_paired():
    facts = facts_for(
        "src/app.cpp",
        "-    CatchRadius = 140;\n+    ThrowSpeed = 120;\n",
    )
    kinds = [fact["kind"] for fact in facts]
    assert "value_changed" not in kinds
    assert {"line_removed", "line_added"} <= set(kinds)
    removed = next(fact for fact in facts if fact["kind"] == "line_removed")
    added = next(fact for fact in facts if fact["kind"] == "line_added")
    assert "CatchRadius" in removed["text"]
    assert "ThrowSpeed" in added["text"]


def test_pure_added_line():
    facts = facts_for(
        "src/app.cpp",
        '+    UE_LOG(LogTemp, Warning, TEXT("Catch evaluated"));\n',
    )
    assert facts == [
        {
            "kind": "line_added",
            "text": 'UE_LOG(LogTemp, Warning, TEXT("Catch evaluated"));',
            "new_line": 10,
        }
    ]


def test_pure_removed_line():
    facts = facts_for(
        "src/app.cpp",
        "-    debug_draw();\n",
    )
    assert facts == [
        {
            "kind": "line_removed",
            "text": "debug_draw();",
            "old_line": 10,
        }
    ]


def test_binary_sensitive_file_is_not_content_inspected():
    diff = unified_diff(
        "Content/Thing.uasset",
        "-foo = 1\n+foo = 2\n",
    )
    report = build_change_facts_report(diff, {"Content/Thing.uasset": "asset"})
    assert report["count"] == 0
    assert report["files"] == []

    map_diff = unified_diff(
        "Content/Maps/Test.umap",
        "-foo = 1\n+foo = 2\n",
    )
    report = build_change_facts_report(map_diff, {"Content/Maps/Test.umap": "map"})
    assert report["count"] == 0

    binary_marker = (
        "diff --git a/Content/Thing.uasset b/Content/Thing.uasset\n"
        "Binary files a/Content/Thing.uasset and b/Content/Thing.uasset differ\n"
    )
    report = build_change_facts_report(binary_marker, {"Content/Thing.uasset": "other"})
    assert report["count"] == 0


def test_multiple_changes_in_one_hunk():
    facts = facts_for(
        "HPDPrototypeCharacter.cpp",
        (
            "-    CatchRadius = 140.0f;\n"
            "-    bEnableAssist = false;\n"
            "+    CatchRadius = 120.0f;\n"
            "+    bEnableAssist = true;\n"
            '+    UE_LOG(LogTemp, Warning, TEXT("Catch evaluated"));\n'
        ),
    )
    assert [fact["kind"] for fact in facts] == [
        "value_changed",
        "value_changed",
        "line_added",
    ]
    assert facts[0]["key"] == "CatchRadius"
    assert facts[0]["before"] == "140.0f"
    assert facts[0]["after"] == "120.0f"
    assert facts[1]["key"] == "bEnableAssist"
    assert facts[2]["kind"] == "line_added"


def test_whitespace_only_lines_are_ignored():
    facts = facts_for(
        "src/app.cpp",
        "-    \n+    CatchRadius = 1;\n",
    )
    assert facts[0]["kind"] == "line_added"
    assert all(fact["kind"] != "line_removed" for fact in facts)


def test_build_report_keeps_change_facts_optional():
    report = build_report("feature/x", "main", [], GOVERNANCE, False)
    assert "change_facts" not in report
    facts = {"count": 0, "files": []}
    report = build_report(
        "feature/x",
        "main",
        [],
        GOVERNANCE,
        False,
        change_facts=facts,
    )
    assert report["change_facts"] == facts
    assert report["technical_risk"] == "LOW"
    assert report["governance_status"] == "PASS"


def test_terminal_and_json_exact_changes(capsys):
    facts = {
        "count": 3,
        "files": [
            {
                "path": "HPDPrototypeCharacter.cpp",
                "facts": [
                    {
                        "kind": "value_changed",
                        "key": "CatchRadius",
                        "before": "140.0f",
                        "after": "120.0f",
                        "old_line": 10,
                        "new_line": 10,
                    },
                    {
                        "kind": "line_added",
                        "text": "UE_LOG(LogTemp, Warning, TEXT(\"Catch evaluated\"));",
                        "new_line": 12,
                    },
                    {
                        "kind": "line_removed",
                        "text": "debug_draw();",
                        "old_line": 13,
                    },
                ],
            }
        ],
    }
    report = build_report(
        "feature/x",
        "main",
        [],
        GOVERNANCE,
        False,
        change_facts=facts,
    )
    print_report(report)
    output = capsys.readouterr().out
    assert "What changed:" in output
    assert "HPDPrototypeCharacter.cpp" in output
    assert "CatchRadius: 140.0f -> 120.0f" in output
    assert "+ added:" in output
    assert "- removed:" in output
    assert "Technical risk: LOW" in output
    assert "Governance:" in output
    assert "PASS" in output

    print_json_report(report)
    payload = json.loads(capsys.readouterr().out)
    assert payload["change_facts"]["count"] == 3
    assert payload["change_facts"]["files"][0]["facts"][0]["kind"] == "value_changed"
    assert payload["change_facts"]["files"][0]["facts"][1]["new_line"] == 12
    assert isinstance(payload["change_facts"]["count"], int)


def test_format_change_fact_value_changed():
    assert (
        format_change_fact(
            {
                "kind": "value_changed",
                "key": "retry_count",
                "before": "3",
                "after": "5",
            }
        )
        == "retry_count: 3 -> 5"
    )


def git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def test_cli_json_includes_change_facts_without_breaking_existing_schema(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    src = repo / "src"
    src.mkdir()
    (src / "app.cpp").write_text("CatchRadius = 140.0f;\n", encoding="utf-8")
    config_path = repo / ".preflight.json"
    config_path.write_text(
        json.dumps({"ownership": [{"match": "prefix", "path": "src/", "owner": "Backend"}]}),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    (src / "app.cpp").write_text(
        "CatchRadius = 120.0f;\nbEnableAssist = true;\n",
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "head")

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
    assert report["technical_risk"] == "MEDIUM"
    assert report["governance_status"] == "PASS"
    assert "changes" in report
    assert "summary" in report
    facts = report["change_facts"]
    assert facts["count"] >= 1
    kinds = [fact["kind"] for file_entry in facts["files"] for fact in file_entry["facts"]]
    assert "value_changed" in kinds
    catch = next(
        fact
        for file_entry in facts["files"]
        for fact in file_entry["facts"]
        if fact.get("key") == "CatchRadius"
    )
    assert catch["before"] == "140.0f"
    assert catch["after"] == "120.0f"
