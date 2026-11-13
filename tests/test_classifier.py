import pytest
from preflight.classifier import classify_file
from preflight.config import DEFAULT_FILE_TYPES


def test_source_extension():
    assert classify_file("src/app.py", DEFAULT_FILE_TYPES) == "source"


def test_workflow_path_beats_extension_or_other():
    assert classify_file(".github/workflows/ci.yml", DEFAULT_FILE_TYPES) == "build_config"


def test_dockerfile_is_build_config():
    assert classify_file("Dockerfile", DEFAULT_FILE_TYPES) == "build_config"


def test_unknown_file_is_other():
    assert classify_file("notes/random.xyz", DEFAULT_FILE_TYPES) == "other"


def test_longest_path_prefix_wins():
    file_types = {
        "general": {"names": [], "path_prefixes": ["src/"], "extensions": []},
        "security": {"names": [], "path_prefixes": ["src/security/"], "extensions": []},
    }
    assert classify_file("src/security/auth.py", file_types) == "security"


def test_path_prefix_is_path_segment_aware():
    file_types = {
        "special": {"names": [], "path_prefixes": ["src"], "extensions": []},
    }

    assert classify_file("src/readme.xyz", file_types) == "special"
    assert classify_file("src2/readme.xyz", file_types) == "other"


def test_path_prefix_normalizes_windows_separators():
    file_types = {
        "special": {"names": [], "path_prefixes": ["src\\security"], "extensions": []},
    }

    assert classify_file("src/security/policy.xyz", file_types) == "special"


@pytest.mark.parametrize(
    "manifest",
    [
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "requirements.txt",
        "services/api/pyproject.toml",
        "web/package.json",
        "crates/lib/Cargo.toml",
        "python/requirements.txt",
    ],
)
def test_common_dependency_manifests_are_build_config(manifest):
    # Default classification must not down-rank dependency/build edits to LOW.
    from preflight.analyzer import calculate_required_checks, calculate_technical_risk

    assert classify_file(manifest, DEFAULT_FILE_TYPES) == "build_config"
    change = {"git_status": "M", "file_type": "build_config"}
    assert calculate_technical_risk(change) == "MEDIUM"
    assert "build/config verification" in calculate_required_checks(change)


def test_custom_file_types_still_replace_defaults_for_manifests():
    custom_types = {
        "my_source": {"names": [], "path_prefixes": [], "extensions": [".py"]},
    }
    assert classify_file("pyproject.toml", custom_types) == "other"
