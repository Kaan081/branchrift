from preflight.report import build_report, calculate_governance_status


GOVERNANCE = {
    "critical_escalation": True,
    "critical_unknown_count": 5,
    "critical_unknown_ratio": 0.25,
}


def _change(path, risk="LOW", owner="Docs", issues=None, review=False, checks=None):
    return {
        "path": path,
        "technical_risk": risk,
        "owner": owner,
        "governance_issues": issues or [],
        "manual_review_required": review,
        "required_checks": checks or [],
    }


def test_unknown_ratio_can_be_critical():
    changes = [
        _change("a", owner="Unknown"),
        _change("b", owner="Unknown"),
        _change("c"),
        _change("d"),
    ]
    assert calculate_governance_status(changes, GOVERNANCE) == "CRITICAL"


def test_boundary_crossing_is_critical():
    changes = [
        _change(
            "src/security/auth.py",
            owner="Security",
            issues=[
                {
                    "code": "OWNERSHIP_BOUNDARY_CROSSING",
                    "priority": "HIGH",
                    "message": "Backend -> Security",
                }
            ],
        )
    ]
    assert calculate_governance_status(changes, GOVERNANCE) == "CRITICAL"


def test_build_report_aggregates_counts():
    changes = [
        _change("a", risk="HIGH", review=True, checks=["build verification"]),
        _change("b", risk="MEDIUM", review=True, checks=["build verification"]),
        _change("c", risk="MEDIUM", review=True, checks=["asset verification"]),
        _change("d", risk="LOW"),
    ]
    report = build_report("feature/x", "main", changes, GOVERNANCE, False)
    summary = report["summary"]
    assert summary["total_changes"] == 4
    assert summary["high_count"] == 1
    assert summary["medium_count"] == 2
    assert summary["low_count"] == 1
    assert summary["manual_review_count"] == 3
    assert set(summary["required_checks"]) == {"build verification", "asset verification"}


def test_summary_includes_status_type_and_owner_counts():
    changes = [
        {**_change("a.uasset", risk="MEDIUM", owner="Art"), "git_status": "A", "file_type": "asset"},
        {**_change("b.uasset", risk="MEDIUM", owner="Art"), "git_status": "A", "file_type": "asset"},
        {**_change("map.umap", risk="MEDIUM", owner="Shared", review=True), "git_status": "M", "file_type": "map"},
    ]
    report = build_report("feature/x", "main", changes, GOVERNANCE, False)
    summary = report["summary"]
    assert summary["status_counts"] == {"A": 2, "M": 1}
    assert summary["file_type_counts"] == {"asset": 2, "map": 1}
    assert summary["owner_counts"] == {"Art": 2, "Shared": 1}


def test_build_report_includes_optional_topology():
    topology = {
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "merge_base": "a" * 40,
        "behind": 0,
        "ahead": 1,
        "relationship": "LINEAR",
        "ff_eligible": True,
    }
    report = build_report(
        "feature/x",
        "main",
        [],
        GOVERNANCE,
        False,
        topology=topology,
    )
    assert report["topology"] == topology


def test_build_report_omits_topology_when_not_provided():
    report = build_report("feature/x", "main", [], GOVERNANCE, False)
    assert "topology" not in report


def test_build_report_includes_optional_collisions():
    collisions = {
        "count": 1,
        "binary_sensitive_count": 0,
        "files": [
            {"path": "src/app.py", "file_type": "source", "binary_sensitive": False}
        ],
    }
    report = build_report(
        "feature/x",
        "main",
        [],
        GOVERNANCE,
        False,
        collisions=collisions,
    )
    assert report["collisions"] == collisions
    assert report["technical_risk"] == "LOW"
    assert report["governance_status"] == "PASS"


def test_build_report_omits_collisions_when_not_provided():
    report = build_report("feature/x", "main", [], GOVERNANCE, False)
    assert "collisions" not in report


def test_build_report_includes_optional_provenance():
    provenance = {
        "base": {"requested": "dev", "sha": "a" * 40},
        "head": {"requested": "HEAD", "sha": "b" * 40},
        "merge_base_sha": "a" * 40,
        "comparison": "merge-base...head",
        "head_is_current_checkout": True,
    }
    report = build_report(
        "feature/x",
        "dev",
        [],
        GOVERNANCE,
        False,
        revision_provenance=provenance,
    )
    assert report["revision_provenance"] == provenance
    assert report["base"] == "dev"
    assert report["head"] == "HEAD"
    assert report["technical_risk"] == "LOW"
