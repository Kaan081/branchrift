from .config import OwnershipPolicyStatus
from .ownership import OwnershipStatus


SCHEMA_VERSION = "1.0"
COMPARISON_MERGE_BASE_HEAD = "merge-base...head"


def build_summary(changes):
    high_count = 0
    medium_count = 0
    low_count = 0
    manual_review_files = []
    required_checks = set()
    owners = set()
    owner_counts = {}
    ownership_status_counts = {}
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

        ownership = change["ownership"]
        ownership_status = ownership.status.value

        ownership_status_counts[ownership_status] = (
            ownership_status_counts.get(ownership_status, 0) + 1
        )

        if ownership.status is OwnershipStatus.KNOWN:
            owner = ownership.owner

            if owner is not None:
                owners.add(owner)
                owner_counts[owner] = owner_counts.get(owner, 0) + 1

        elif ownership.status is OwnershipStatus.NO_MATCH:
            # Preserve legacy configured-repository reporting.
            owners.add("Unknown")
            owner_counts["Unknown"] = owner_counts.get("Unknown", 0) + 1

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
        "ownership_status_counts": dict(
            sorted(ownership_status_counts.items())
        ),
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

    no_match_count = 0
    boundary_crossing_count = 0

    for change in changes:
        if change["ownership"].status is OwnershipStatus.NO_MATCH:
            no_match_count += 1

        for issue in change["governance_issues"]:
            if issue["code"] == "OWNERSHIP_BOUNDARY_CROSSING":
                boundary_crossing_count += 1

    if boundary_crossing_count > 0:
        return "CRITICAL"

    if no_match_count == 0:
        return "PASS"

    if not governance["critical_escalation"]:
        return "ATTENTION"

    no_match_ratio = no_match_count / len(changes)

    if (
        no_match_count >= governance["critical_unknown_count"]
        or no_match_ratio >= governance["critical_unknown_ratio"]
    ):
        return "CRITICAL"

    return "ATTENTION"


def build_governance_report(changes, ownership_policy_status):
    if ownership_policy_status in (
        OwnershipPolicyStatus.NOT_CONFIGURED,
        OwnershipPolicyStatus.CONFIGURED_EMPTY,
    ):
        return {
            "evaluation_status": "not_evaluated",
            "ownership_policy_status": ownership_policy_status.value,
            "issues": [],
        }

    issues = []

    for change in changes:
        for issue in change["governance_issues"]:
            issues.append(
                {
                    "path": change["path"],
                    **issue,
                }
            )

    return {
        "evaluation_status": "evaluated",
        "ownership_policy_status": ownership_policy_status.value,
        "issues": issues,
    }


def serialize_ownership(ownership):
    return {
        "status": ownership.status.value,
        "owner": ownership.owner,
    }


def serialize_change(change):
    serialized = dict(change)

    ownership = serialized.get("ownership")

    if ownership is not None:
        serialized["ownership"] = serialize_ownership(ownership)

    old_ownership = serialized.get("old_ownership")

    if old_ownership is not None:
        serialized["old_ownership"] = serialize_ownership(old_ownership)

    return serialized


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
    ownership_policy_status=OwnershipPolicyStatus.CONFIGURED,
):
    summary = build_summary(changes)
    public_changes = [serialize_change(change) for change in changes]

    report = {
        "schema_version": SCHEMA_VERSION,
        "branch": branch,
        "base": base_branch,
        "head": head_revision,
        "repository_state": "DIRTY" if worktree_dirty else "CLEAN",
        "technical_risk": calculate_overall_technical_risk(summary),
        "governance_status": calculate_governance_status(
            changes,
            governance_config,
        ),
        "governance": build_governance_report(
            changes,
            ownership_policy_status,
        ),
        "summary": summary,
        "changes": public_changes,
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