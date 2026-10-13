from dataclasses import dataclass
from enum import Enum

from .config import OwnershipPolicyStatus
from .errors import ConfigError
from .pathmatch import canonical_prefix, path_prefix_matches


class OwnershipStatus(str, Enum):
    KNOWN = "known"
    NOT_CONFIGURED = "not_configured"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class OwnershipResult:
    status: OwnershipStatus
    owner: str | None


def rule_matches(path, rule):
    match_type = rule.get("match", "prefix")
    rule_path = rule["path"]

    if match_type == "path_exact":
        return path == rule_path
    if match_type == "prefix":
        return path_prefix_matches(path, rule_path)

    raise ConfigError(f"Unsupported ownership match type: {match_type}")


def get_owner(path, rules, default_owner=None):
    matches = [rule for rule in rules if rule_matches(path, rule)]

    if not matches:
        return default_owner if default_owner is not None else "Unknown"

    def specificity(rule):
        match_type = rule.get("match", "prefix")
        match_rank = 1 if match_type == "path_exact" else 0
        path = rule["path"]
        if match_type == "prefix":
            path_length = len(canonical_prefix(path))
        else:
            path_length = len(path)
        return (path_length, match_rank)

    most_specific = max(matches, key=specificity)
    return most_specific["owner"]


def resolve_ownership(
    path,
    rules,
    *,
    policy_status,
    default_owner=None,
):
    if policy_status in (
        OwnershipPolicyStatus.NOT_CONFIGURED,
        OwnershipPolicyStatus.CONFIGURED_EMPTY,
    ):
        return OwnershipResult(
            status=OwnershipStatus.NOT_CONFIGURED,
            owner=None,
        )

    matches = [rule for rule in rules if rule_matches(path, rule)]

    if not matches:
        if default_owner is not None:
            return OwnershipResult(
                status=OwnershipStatus.KNOWN,
                owner=default_owner,
            )

        return OwnershipResult(
            status=OwnershipStatus.NO_MATCH,
            owner=None,
        )

    def specificity(rule):
        match_type = rule.get("match", "prefix")
        match_rank = 1 if match_type == "path_exact" else 0
        rule_path = rule["path"]

        if match_type == "prefix":
            path_length = len(canonical_prefix(rule_path))
        else:
            path_length = len(rule_path)

        return (path_length, match_rank)

    most_specific = max(matches, key=specificity)

    return OwnershipResult(
        status=OwnershipStatus.KNOWN,
        owner=most_specific["owner"],
    )