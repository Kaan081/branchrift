"""Compact CLI keeps risks clear and JSON/verbose available."""

import json

import pytest

from preflight.cli import parse_args
from preflight.reporter import print_compact_report, print_json_report


def _report():
    return {
        "base": "main",
        "head": "feature/x",
        "repository_state": "DIRTY",
        "technical_risk": "HIGH",
        "summary": {
            "total_changes": 231,
            "manual_review_count": 113,
            "manual_review_files": [f"Content/{n:03d}.uasset" for n in range(113)],
            "status_counts": {"D": 52, "M": 179},
            "file_type_counts": {"asset": 229, "map": 1, "build_config": 1},
        },
        "topology": {"relationship": "DIVERGED", "ahead": 3, "behind": 2},
        "collisions": {"count": 0, "binary_sensitive_count": 0, "files": []},
        "binary_readiness": {"attention_count": 0, "files": []},
        "governance": {"issues": [], "evaluation_status": "not_evaluated"},
    }


def test_default_parser_and_mutual_exclusion():
    args = parse_args([])
    assert not args.json and not args.verbose
    assert parse_args(["--verbose"]).verbose
    assert parse_args(["--json"]).json
    with pytest.raises(SystemExit):
        parse_args(["--json", "--verbose"])


def test_compact_large_repo_is_bounded_and_honest(capsys):
    print_compact_report(_report())
    output = capsys.readouterr().out
    assert "Changed: 231 files | manual review: 113" in output
    assert "52 deleted paths" in output
    assert "Same-path overlap: 0 | binary-sensitive: 0" in output
    assert "Git merge conflict prediction: NOT CHECKED" in output
    assert "Worktree: DIRTY (uncommitted changes excluded)" in output
    assert output.count("  - Content/") == 3
    assert "... 110 more" in output
    assert len(output.splitlines()) <= 15


def test_compact_prioritizes_collisions_and_sanitizes_paths(capsys):
    report = _report()
    report["collisions"] = {
        "count": 1,
        "binary_sensitive_count": 1,
        "files": [{"path": "Content/Maps/unsafe\x1b[31m.umap", "binary_sensitive": True}],
    }
    print_compact_report(report)
    output = capsys.readouterr().out
    assert "binary-sensitive overlaps" in output
    assert "unsafe\\x1b[31m.umap" in output
    assert "unsafe\x1b[31m.umap" not in output
    assert "Git merge conflict prediction: NOT CHECKED" in output


def test_compact_does_not_mutate_json_report(capsys):
    report = _report()
    expected = json.dumps(report, sort_keys=True)
    print_compact_report(report)
    capsys.readouterr()
    assert json.dumps(report, sort_keys=True) == expected
    print_json_report(report)
    assert json.loads(capsys.readouterr().out) == report


def test_compact_without_optional_sections(capsys):
    report = _report()
    report.pop("collisions")
    report.pop("topology")
    report.pop("binary_readiness")
    report.pop("governance")
    print_compact_report(report)
    output = capsys.readouterr().out
    assert "Same-path overlap: NOT CHECKED" in output
    assert "Git merge conflict prediction: NOT CHECKED" in output
