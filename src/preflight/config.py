import json
from copy import deepcopy
from pathlib import Path

from .errors import ConfigError
from .pathmatch import canonical_prefix


DEFAULT_GOVERNANCE = {
    "critical_escalation": True,
    "critical_unknown_count": 5,
    "critical_unknown_ratio": 0.25,
}

DEFAULT_FILE_TYPES = {
    "source": {
        "names": [],
        "path_prefixes": [],
        "extensions": [
            ".py", ".c", ".cpp", ".h", ".hpp", ".cc", ".cxx",
            ".cs", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
        ],
    },
    "asset": {
        "names": [],
        "path_prefixes": [],
        "extensions": [".uasset", ".fbx", ".blend"],
    },
    "map": {
        "names": [],
        "path_prefixes": [],
        "extensions": [".umap"],
    },
    "build_config": {
        "names": ["Dockerfile", "Makefile", "CMakeLists.txt", "Jenkinsfile", "Procfile"],
        "path_prefixes": [".github/workflows/"],
        "extensions": [".gradle"],
    },
}

ALLOWED_MATCH_TYPES = {"prefix", "path_exact"}


def load_config(path):
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except FileNotFoundError as error:
        raise ConfigError(f"Config file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"Invalid JSON config: {error}") from error

    validate_config(config)
    return normalize_config(config)


def validate_config(config):
    if not isinstance(config, dict):
        raise ConfigError("Config root must be an object")

    if "ownership" not in config:
        raise ConfigError("Config is missing required field: ownership")

    rules = config["ownership"]
    if not isinstance(rules, list):
        raise ConfigError("ownership must be a list")
    if not rules:
        raise ConfigError("ownership cannot be empty")

    validate_ownership_rules(rules)

    if "default_owner" in config:
        default_owner = config["default_owner"]
        if default_owner is not None and (
            not isinstance(default_owner, str) or not default_owner.strip()
        ):
            raise ConfigError("default_owner must be null or a non-empty string")

    if "governance" in config and not isinstance(config["governance"], dict):
        raise ConfigError("governance must be an object")

    if "file_types" in config:
        validate_file_types(config["file_types"])


def validate_ownership_rules(rules):
    seen_rules = set()

    for rule in rules:
        if not isinstance(rule, dict):
            raise ConfigError("Each ownership rule must be an object")

        match_type = rule.get("match", "prefix")
        if match_type not in ALLOWED_MATCH_TYPES:
            raise ConfigError(f"Unsupported ownership match type: {match_type}")

        if "path" not in rule:
            raise ConfigError("Ownership rule is missing path")
        if "owner" not in rule:
            raise ConfigError("Ownership rule is missing owner")

        path = rule["path"]
        owner = rule["owner"]

        if not isinstance(path, str) or not path:
            raise ConfigError("Ownership path must be a non-empty string")
        if not isinstance(owner, str) or not owner.strip():
            raise ConfigError("Ownership owner must be a non-empty string")

        if match_type == "prefix":
            rule_path = canonical_prefix(path)
            if not rule_path:
                raise ConfigError(
                    f"Ownership prefix cannot canonicalize to an empty path: {path}"
                )
        else:
            rule_path = path
        rule_key = (match_type, rule_path)
        if rule_key in seen_rules:
            raise ConfigError(f"Duplicate ownership rule: {match_type}:{path}")
        seen_rules.add(rule_key)


def validate_file_types(file_types):
    if not isinstance(file_types, dict) or not file_types:
        raise ConfigError("file_types must be a non-empty object")

    seen = {"names": {}, "path_prefixes": {}, "extensions": {}}

    for file_type, rules in file_types.items():
        if not isinstance(file_type, str) or not file_type.strip():
            raise ConfigError("file type names must be non-empty strings")
        if not isinstance(rules, dict):
            raise ConfigError(f"file type '{file_type}' must be an object")

        for key in ("names", "path_prefixes", "extensions"):
            values = rules.get(key, [])
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                raise ConfigError(f"file_types.{file_type}.{key} must be a list of non-empty strings")

            for value in values:
                if key == "path_prefixes":
                    normalized_value = canonical_prefix(value).lower()
                    if not normalized_value:
                        raise ConfigError(
                            "File type prefix cannot canonicalize to an empty path: "
                            f"{value}"
                        )
                elif key != "names":
                    normalized_value = value.lower()
                else:
                    normalized_value = value
                previous_type = seen[key].get(normalized_value)
                if previous_type is not None and previous_type != file_type:
                    raise ConfigError(
                        f"Conflicting file type rule '{value}' in {previous_type} and {file_type}"
                    )
                seen[key][normalized_value] = file_type


def normalize_governance_config(config):
    governance = config.get("governance", {})
    normalized = {
        "critical_escalation": governance.get(
            "critical_escalation", DEFAULT_GOVERNANCE["critical_escalation"]
        ),
        "critical_unknown_count": governance.get(
            "critical_unknown_count", DEFAULT_GOVERNANCE["critical_unknown_count"]
        ),
        "critical_unknown_ratio": governance.get(
            "critical_unknown_ratio", DEFAULT_GOVERNANCE["critical_unknown_ratio"]
        ),
    }
    validate_governance_config(normalized)
    return normalized


def validate_governance_config(governance):
    escalation = governance["critical_escalation"]
    count = governance["critical_unknown_count"]
    ratio = governance["critical_unknown_ratio"]

    if not isinstance(escalation, bool):
        raise ConfigError("critical_escalation must be boolean")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ConfigError("critical_unknown_count must be an integer >= 1")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
        raise ConfigError("critical_unknown_ratio must be numeric")
    if not 0 <= ratio <= 1:
        raise ConfigError("critical_unknown_ratio must be between 0 and 1")


def normalize_file_types(config):
    user_file_types = config.get("file_types")
    if user_file_types is None:
        return deepcopy(DEFAULT_FILE_TYPES)

    validate_file_types(user_file_types)
    return deepcopy(user_file_types)


def normalize_config(config):
    normalized = {
        **deepcopy(config),
        "ownership": deepcopy(config["ownership"]),
        "governance": normalize_governance_config(config),
        "file_types": normalize_file_types(config),
    }
    return normalized
