"""Regression: terminal manual-review lists stay bounded while JSON stays complete."""

import json

import pytest

from preflight.config import DEFAULT_GOVERNANCE
from preflight.report import build_report
from preflight.reporter import MANUAL_REVIEW_TERMINAL_LIMIT, print_json_report, print_report


REVIEW_COUNTS = (20, 100, 1000)


def _review_path(index):
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    chars = []
    value = index
    for _ in range(4):
        chars.append(alphabet[value % 26])
        value //= 26
    return "manual/" + "".join(chars) + ".txt"


def _review_report(count):
    changes = []
    for index in range(count):
        changes.append(
            {
                "path": _review_path(index),
                "git_status": "M",
                "file_type": "other",
                "owner": "Review",
                "technical_risk": "LOW",
                "confidence": "MEDIUM",
                "required_checks": [],
                "governance_issues": [],
                "manual_review_required": True,
            }
        )
    return build_report(
        "feature/evidence",
        "main",
        changes,
        DEFAULT_GOVERNANCE,
        False,
    )


def _manual_review_section(output):
    marker = "  Manual review:"
    assert marker in output
    return output.split(marker, 1)[1]


def _printed_paths(section, paths):
    return [path for path in paths if f"    - {path}\n" in section or section.endswith(f"    - {path}")]


@pytest.mark.parametrize("count", REVIEW_COUNTS)
def test_json_manual_review_list_stays_complete(capsys, count):
    report = _review_report(count)
    expected = [_review_path(index) for index in range(count)]
    print_json_report(report)
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["manual_review_files"] == sorted(expected)
    assert payload["summary"]["manual_review_count"] == count
    assert len(payload["summary"]["manual_review_files"]) == count


def test_terminal_manual_review_is_bounded_for_large_lists(capsys):
    for count in REVIEW_COUNTS:
        report = _review_report(count)
        paths = report["summary"]["manual_review_files"]
        assert len(paths) == count
        print_report(report)
        output = capsys.readouterr().out
        section = _manual_review_section(output)
        printed = _printed_paths(section, paths)
        omitted = count - MANUAL_REVIEW_TERMINAL_LIMIT
        assert f"Manual review: {count} files" in output
        assert len(printed) == min(count, MANUAL_REVIEW_TERMINAL_LIMIT)
        assert printed == paths[:MANUAL_REVIEW_TERMINAL_LIMIT]
        if omitted > 0:
            assert f"... {omitted} more paths omitted" in section
        else:
            assert "omitted" not in section
