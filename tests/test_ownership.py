from preflight.config import OwnershipPolicyStatus
from preflight.ownership import (
    OwnershipStatus,
    get_owner,
    resolve_ownership,
    rule_matches,
)

def test_specific_prefix_wins():
    rules = [
        {"path": "src/", "owner": "Backend"},
        {"path": "src/payment/", "owner": "Payments"},
    ]
    assert get_owner("src/payment/checkout.py", rules) == "Payments"


def test_unmatched_path_is_unknown():
    rules = [{"path": "src/", "owner": "Backend"}]
    assert get_owner("scripts/deploy.py", rules) == "Unknown"


def test_default_owner_is_used():
    rules = [{"path": "src/", "owner": "Backend"}]
    assert get_owner("scripts/deploy.py", rules, "Core") == "Core"


def test_path_exact_does_not_match_similar_name():
    rule = {"match": "path_exact", "path": "Dockerfile", "owner": "Platform"}
    assert rule_matches("Dockerfile", rule) is True
    assert rule_matches("Dockerfile.backup", rule) is False
    assert rule_matches("infra/Dockerfile", rule) is False


def test_path_exact_beats_equal_length_prefix():
    rules = [
        {"match": "prefix", "path": "src/", "owner": "General"},
        {"match": "path_exact", "path": "src/", "owner": "Exact"},
    ]
    assert get_owner("src/", rules) == "Exact"


def test_prefix_is_path_segment_aware():
    rule = {"match": "prefix", "path": "src", "owner": "Backend"}

    assert rule_matches("src", rule) is True
    assert rule_matches("src/app.py", rule) is True
    assert rule_matches("src2/app.py", rule) is False


def test_prefix_normalizes_windows_separators():
    rule = {"match": "prefix", "path": "src\\payment", "owner": "Payments"}

    assert rule_matches("src/payment/checkout.py", rule) is True


def test_canonical_prefix_spelling_does_not_change_specificity():
    padded_short_prefix = [
        {"match": "prefix", "path": "src////////", "owner": "Shallow"},
        {"match": "prefix", "path": "src/app", "owner": "Deep"},
    ]
    canonical_short_prefix = [
        {"match": "prefix", "path": "src", "owner": "Shallow"},
        {"match": "prefix", "path": "src/app", "owner": "Deep"},
    ]
    path = "src/app/checkout.py"
    assert get_owner(path, padded_short_prefix) == "Deep"
    assert get_owner(path, canonical_short_prefix) == "Deep"
    assert get_owner(path, padded_short_prefix) == get_owner(path, canonical_short_prefix)

def test_resolve_known_owner():
    rules = [{"path": "src/", "owner": "Backend"}]

    result = resolve_ownership(
        "src/app.py",
        rules,
        policy_status=OwnershipPolicyStatus.CONFIGURED,
    )

    assert result.status is OwnershipStatus.KNOWN
    assert result.owner == "Backend"


def test_resolve_configured_policy_without_match():
    rules = [{"path": "src/", "owner": "Backend"}]

    result = resolve_ownership(
        "scripts/deploy.py",
        rules,
        policy_status=OwnershipPolicyStatus.CONFIGURED,
    )

    assert result.status is OwnershipStatus.NO_MATCH
    assert result.owner is None


def test_resolve_missing_policy():
    result = resolve_ownership(
        "scripts/deploy.py",
        [],
        policy_status=OwnershipPolicyStatus.NOT_CONFIGURED,
    )

    assert result.status is OwnershipStatus.NOT_CONFIGURED
    assert result.owner is None


def test_resolve_empty_policy():
    result = resolve_ownership(
        "scripts/deploy.py",
        [],
        policy_status=OwnershipPolicyStatus.CONFIGURED_EMPTY,
    )

    assert result.status is OwnershipStatus.NOT_CONFIGURED
    assert result.owner is None


def test_resolve_default_owner():
    rules = [{"path": "src/", "owner": "Backend"}]

    result = resolve_ownership(
        "scripts/deploy.py",
        rules,
        policy_status=OwnershipPolicyStatus.CONFIGURED,
        default_owner="Core",
    )

    assert result.status is OwnershipStatus.KNOWN
    assert result.owner == "Core"