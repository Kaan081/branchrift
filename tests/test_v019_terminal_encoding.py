"""Regression: terminal rendering survives a limited stdout encoding."""

import io
import json
import sys

from preflight.reporter import print_json_report, print_report


ARROW = "\u2192"
UNSUPPORTED = "\u0100"
TURKISH = "çağrı İstanbul"
ASCII_FACT = "count = 2"


def _summary(**overrides):
    data = {
        "total_changes": 1,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 1,
        "manual_review_count": 1,
        "manual_review_files": ["src/app.py"],
        "required_checks": ["build verification"],
        "owners": ["Backend"],
        "owner_counts": {"Backend": 1},
        "status_counts": {"M": 1},
        "file_type_counts": {"source": 1},
        "governance_issue_count": 0,
    }
    data.update(overrides)
    return data


def _report(*, path="src/app.py", fact_text=ASCII_FACT, message="owner missing", reason="ready"):
    return {
        "branch": "feature/x",
        "base": "dev",
        "head": "HEAD",
        "repository_state": "CLEAN",
        "technical_risk": "LOW",
        "governance_status": "ATTENTION",
        "summary": _summary(manual_review_files=[path]),
        "changes": [
            {
                "path": path,
                "file_type": "source",
                "git_status": "M",
                "owner": "Backend",
                "governance_issues": [
                    {"code": "OWNERSHIP_GAP", "message": message},
                ],
                "manual_review_required": True,
                "technical_risk": "LOW",
            }
        ],
        "change_facts": {
            "count": 1,
            "files": [
                {
                    "path": path,
                    "facts": [{"kind": "line_added", "text": fact_text, "new_line": 1}],
                }
            ],
        },
        "binary_readiness": {
            "count": 1,
            "attention_count": 0,
            "files": [
                {
                    "path": path,
                    "file_type": "other",
                    "git_status": "M",
                    "lfs_managed": True,
                    "working_tree_state": "present",
                    "lfs_state": "unknown",
                    "readiness": "unknown",
                    "reason": reason,
                }
            ],
        },
    }


def _render(render, encoding):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(
        buffer,
        encoding=encoding,
        errors="strict",
        newline="\n",
    )
    previous = sys.stdout
    sys.stdout = stream
    try:
        render()
        stream.flush()
        payload = buffer.getvalue()
    finally:
        sys.stdout = previous
    return payload.decode(encoding)


def test_cp1254_terminal_escapes_unsupported_characters_and_keeps_turkish():
    path = f"notlar/{TURKISH}/{ARROW}.md"
    fact = f"count {ARROW} value {UNSUPPORTED} {TURKISH}"
    message = f"sorumlu {TURKISH} {ARROW} eksik"
    reason = f"durum {TURKISH} {ARROW}"
    report = _report(path=path, fact_text=fact, message=message, reason=reason)

    output = _render(lambda: print_report(report), "cp1254")

    assert "Manual review:" in output
    assert TURKISH in output
    assert ARROW not in output
    assert UNSUPPORTED not in output
    assert r"\u2192" in output
    assert r"\u0100" in output
    assert "count \\u2192 value \\u0100 " + TURKISH in output
    assert "notlar/" + TURKISH + r"/\u2192.md" in output
    assert message.replace(ARROW, r"\u2192") in output
    assert reason.replace(ARROW, r"\u2192") in output
    assert _render(lambda: print_report(report), "cp1254") == output


def test_utf8_terminal_preserves_unicode():
    fact = f"count {ARROW} value {UNSUPPORTED} {TURKISH}"
    report = _report(path=f"notlar/{TURKISH}.md", fact_text=fact, message=TURKISH, reason=TURKISH)
    output = _render(lambda: print_report(report), "utf-8")
    assert fact in output
    assert TURKISH in output
    assert ARROW in output
    assert UNSUPPORTED in output
    assert r"\u2192" not in output


def test_ascii_terminal_is_unchanged_across_encodings():
    report = _report()
    cp1254 = _render(lambda: print_report(report), "cp1254")
    utf8 = _render(lambda: print_report(report), "utf-8")
    assert cp1254 == utf8
    assert "src/app.py" in cp1254
    assert ASCII_FACT in cp1254
    assert "Manual review:" in cp1254
    assert r"\u" not in cp1254


def test_json_serializes_on_cp1254_without_changing_unicode_values():
    report = _report(
        path=f"notlar/{TURKISH}/{ARROW}.md",
        fact_text=f"count {ARROW} value",
        message=TURKISH,
        reason=f"durum {ARROW}",
    )
    rendered = _render(lambda: print_json_report(report), "cp1254")
    payload = json.loads(rendered)
    assert ARROW not in rendered
    assert "\\u2192" in rendered
    assert payload["changes"][0]["path"] == report["changes"][0]["path"]
    assert payload["change_facts"]["files"][0]["facts"][0]["text"] == "count \u2192 value"
