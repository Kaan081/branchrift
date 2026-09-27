def build_summary(changes):
    high_count = 0
    medium_count = 0
    low_count = 0
    manual_review_files = []
    required_checks = set()
    owners = set()
    owner_counts = {}
    status_counts = {}
    file_type_counts = {}
    governance_issue_count = 0

    for change in changes:
        risk = change["technical_risk"]
        if risk == "HIGH":
            high_count += 1
        elif risk == "MEDIUM":
            medium_count += 1
        else:
            low_count += 1

        if change["manual_review_required"]:
            manual_review_files.append(change["path"])

        required_checks.update(change["required_checks"])
        governance_issue_count += len(change["governance_issues"])

        owner = change["owner"]
        owners.add(owner)
        owner_counts[owner] = owner_counts.get(owner, 0) + 1

        status = change.get("git_status", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        file_type = change.get("file_type", "other")
        file_type_counts[file_type] = file_type_counts.get(file_type, 0) + 1

    return {
        "total_changes": len(changes),
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "manual_review_count": len(manual_review_files),
        "manual_review_files": sorted(manual_review_files),
        "required_checks": sorted(required_checks),
        "owners": sorted(owners),
        "owner_counts": dict(sorted(owner_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "file_type_counts": dict(sorted(file_type_counts.items())),
        "governance_issue_count": governance_issue_count,
    }


def calculate_overall_technical_risk(summary):
    if summary["high_count"] > 0:
        return "HIGH"
    if summary["medium_count"] > 0:
        return "MEDIUM"
    return "LOW"


def calculate_governance_status(changes, governance):
    if not changes:
        return "PASS"

    unknown_count = 0
    boundary_crossing_count = 0

    for change in changes:
        if change["owner"] == "Unknown":
            unknown_count += 1
        for issue in change["governance_issues"]:
            if issue["code"] == "OWNERSHIP_BOUNDARY_CROSSING":
                boundary_crossing_count += 1

    if boundary_crossing_count > 0:
        return "CRITICAL"
    if unknown_count == 0:
        return "PASS"
    if not governance["critical_escalation"]:
        return "ATTENTION"

    unknown_ratio = unknown_count / len(changes)
    if (
        unknown_count >= governance["critical_unknown_count"]
        or unknown_ratio >= governance["critical_unknown_ratio"]
    ):
        return "CRITICAL"

    return "ATTENTION"


COMPARISON_MERGE_BASE_HEAD = "merge-base...head"


def build_revision_provenance(
    requested_base,
    requested_head,
    topology,
    current_head_sha=None,
):
    head_sha = topology["head_sha"]
    return {
        "base": {
            "requested": requested_base,
            "sha": topology["base_sha"],
        },
        "head": {
            "requested": requested_head,
            "sha": head_sha,
        },
        "merge_base_sha": topology["merge_base"],
        "comparison": COMPARISON_MERGE_BASE_HEAD,
        "head_is_current_checkout": bool(
            current_head_sha and current_head_sha == head_sha
        ),
    }


def build_report(
    branch,
    base_branch,
    changes,
    governance_config,
    worktree_dirty,
    head_revision="HEAD",
    topology=None,
    collisions=None,
    change_facts=None,
    binary_readiness=None,
    revision_provenance=None,
):
    summary = build_summary(changes)
    report = {
        "branch": branch,
        "base": base_branch,
        "head": head_revision,
        "repository_state": "DIRTY" if worktree_dirty else "CLEAN",
        "technical_risk": calculate_overall_technical_risk(summary),
        "governance_status": calculate_governance_status(changes, governance_config),
        "summary": summary,
        "changes": changes,
    }
    if topology is not None:
        report["topology"] = topology
    if collisions is not None:
        report["collisions"] = collisions
    if change_facts is not None:
        report["change_facts"] = change_facts
    if binary_readiness is not None:
        report["binary_readiness"] = binary_readiness
    if revision_provenance is not None:
        report["revision_provenance"] = revision_provenance
    return report
