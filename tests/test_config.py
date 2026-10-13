import pytest

from preflight.config import (
    DEFAULT_FILE_TYPES,
    OwnershipPolicyStatus,
    normalize_config,
    validate_config,
    validate_ownership_rules,
)
from preflight.errors import ConfigError


def test_missing_ownership_is_not_configured():
    validate_config({})

    result = normalize_config({})

    assert result["ownership"] == []
    assert (
        result["ownership_policy_status"]
        is OwnershipPolicyStatus.NOT_CONFIGURED
    )


def test_empty_ownership_is_configured_empty():
    config = {"ownership": []}

    validate_config(config)
    result = normalize_config(config)

    assert result["ownership"] == []
    assert (
        result["ownership_policy_status"]
        is OwnershipPolicyStatus.CONFIGURED_EMPTY
    )
def test_default_owner_counts_as_configured_ownership():
    config = {"default_owner": "Core"}

    validate_config(config)
    result = normalize_config(config)

    assert (
        result["ownership_policy_status"]
        is OwnershipPolicyStatus.CONFIGURED
    )

def test_duplicate_rule_fails():
    rules = [
        {"match": "prefix", "path": "src/", "owner": "A"},
        {"match": "prefix", "path": "src/", "owner": "B"},
    ]
    with pytest.raises(ConfigError, match="Duplicate ownership rule"):
        validate_ownership_rules(rules)


def test_canonical_prefix_slash_and_backslash_are_duplicates():
    rules = [
        {"match": "prefix", "path": "src/", "owner": "A"},
        {"match": "prefix", "path": "src\\", "owner": "B"},
    ]
    with pytest.raises(ConfigError, match="Duplicate ownership rule"):
        validate_ownership_rules(rules)


def test_canonical_prefix_with_and_without_trailing_slash_are_duplicates():
    rules = [
        {"match": "prefix", "path": "src", "owner": "A"},
        {"match": "prefix", "path": "src/", "owner": "B"},
    ]
    with pytest.raises(ConfigError, match="Duplicate ownership rule"):
        validate_ownership_rules(rules)


@pytest.mark.parametrize("path", ["/", "\\", "///", "\\\\"])
def test_empty_canonical_prefix_is_rejected(path):
    rules = [{"match": "prefix", "path": path, "owner": "A"}]
    with pytest.raises(ConfigError, match="empty path"):
        validate_ownership_rules(rules)


def test_path_exact_slash_is_still_allowed():
    validate_ownership_rules(
        [{"match": "path_exact", "path": "/", "owner": "Root"}]
    )


def test_normalize_config_adds_defaults_without_mutating_input():
    config = {"ownership": [{"path": "src/", "owner": "Backend"}]}
    result = normalize_config(config)

    assert "governance" not in config
    assert "file_types" not in config
    assert result["governance"]["critical_escalation"] is True
    assert result["governance"]["critical_unknown_count"] == 5
    assert result["governance"]["critical_unknown_ratio"] == 0.25
    assert result["file_types"] == DEFAULT_FILE_TYPES


def test_zero_unknown_ratio_threshold_is_allowed():
    result = normalize_config(
        {
            "ownership": [{"path": "src/", "owner": "Backend"}],
            "governance": {"critical_unknown_ratio": 0},
        }
    )
    assert result["governance"]["critical_unknown_ratio"] == 0


def test_negative_unknown_ratio_fails():
    with pytest.raises(ConfigError, match="between 0 and 1"):
        normalize_config(
            {
                "ownership": [{"path": "src/", "owner": "Backend"}],
                "governance": {"critical_unknown_ratio": -0.1},
            }
        )


def test_conflicting_file_type_rule_fails():
    with pytest.raises(ConfigError, match="Conflicting file type rule"):
        validate_config(
            {
                "ownership": [{"path": "src/", "owner": "Backend"}],
                "file_types": {
                    "one": {"extensions": [".py"]},
                    "two": {"extensions": [".py"]},
                },
            }
        )
