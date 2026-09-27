import json

from preflight.reporter import print_json_report, print_report, terminal_safe


def test_terminal_safe_escapes_control_characters():
    value = "evil\x1b[31m\nfile\tname"
    result = terminal_safe(value)

    assert "\x1b" not in result
    assert "\n" not in result
    assert "\t" not in result
    assert result == r"evil\x1b[31m\nfile\tname"


def _report_with_topology(ff_eligible=True):
    return {
        "branch": "feature/x",
        "base": "main",
        "head": "HEAD",
        "repository_state": "CLEAN",
        "technical_risk": "LOW",
        "governance_status": "PASS",
        "summary": {
            "total_changes": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "manual_review_count": 0,
            "manual_review_files": [],
            "required_checks": [],
            "owners": [],
            "owner_counts": {},
            "status_counts": {},
            "file_type_counts": {},
            "governance_issue_count": 0,
        },
        "changes": [],
        "topology": {
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "merge_base": "a" * 40,
            "behind": 0 if ff_eligible else 2,
            "ahead": 3,
            "relationship": "LINEAR" if ff_eligible else "DIVERGED",
            "ff_eligible": ff_eligible,
        },
    }


def test_print_report_includes_topology_section(capsys):
    print_report(_report_with_topology())
    output = capsys.readouterr().out
    assert "Analyzed:" in output
    assert f"{'a' * 40}" in output
    assert f"{'b' * 40}" in output
    assert "Merge base:" in output
    assert "Integration:" in output
    assert "Topology: LINEAR" in output
    assert "Fast-forward eligible: yes" in output
    assert "Ahead: 3" in output
    assert "Behind: 0" in output


def test_print_json_report_uses_boolean_ff_eligible(capsys):
    print_json_report(_report_with_topology(ff_eligible=False))
    raw = capsys.readouterr().out
    payload = json.loads(raw)
    assert payload["topology"]["ff_eligible"] is False
    assert "YES" not in raw
    assert "NO" not in json.dumps(payload["topology"])


def _report_with_collisions(files):
    report = _report_with_topology()
    report["collisions"] = {
        "count": len(files),
        "binary_sensitive_count": sum(1 for item in files if item["binary_sensitive"]),
        "files": files,
    }
    return report


def test_print_report_zero_collisions(capsys):
    print_report(_report_with_collisions([]))
    output = capsys.readouterr().out
    assert "Integration:" in output
    assert "Same-path collisions: 0" in output
    assert "Binary-sensitive collisions: 0" in output
    assert "BINARY-SENSITIVE" not in output


def test_print_report_nonzero_collisions(capsys):
    print_report(
        _report_with_collisions(
            [
                {
                    "path": "Content/Maps/Test.umap",
                    "file_type": "map",
                    "binary_sensitive": True,
                },
                {
                    "path": "src/app.py",
                    "file_type": "source",
                    "binary_sensitive": False,
                },
            ]
        )
    )
    output = capsys.readouterr().out
    assert "Integration:" in output
    assert "Same-path collisions: 2" in output
    assert "Binary-sensitive collisions: 1" in output
    assert "Content/Maps/Test.umap [map, BINARY-SENSITIVE]" in output
    assert "src/app.py [source]" in output
