"""v0.2.0 public identity: BranchRift distribution, CLI aliases, report heading."""

import importlib
from pathlib import Path

from preflight import __version__
from preflight.cli import main
from preflight.reporter import print_report


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _script_target(name):
    in_scripts = False
    for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_scripts = stripped == "[project.scripts]"
            continue
        if not in_scripts or "=" not in stripped or stripped.startswith("#"):
            continue
        key, value = (part.strip() for part in stripped.split("=", 1))
        if key == name:
            return value.strip().strip('"').strip("'")
    raise AssertionError(f"{name} script entry was not found")


def _load_entrypoint(spec):
    module_name, attribute = spec.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


def _minimal_report():
    return {
        "branch": "feature/x",
        "base": "main",
        "head": "HEAD",
        "repository_state": "CLEAN",
        "technical_risk": "LOW",
        "governance_status": "PASS",
        "summary": {
            "total_changes": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "manual_review_count": 0,
            "manual_review_files": [],
            "required_checks": [],
            "owners": [],
            "owner_counts": {},
            "status_counts": {},
            "file_type_counts": {},
            "governance_issue_count": 0,
        },
        "changes": [],
    }


def test_public_version_is_0_2_0():
    assert __version__ == "0.2.0"
    text = PYPROJECT.read_text(encoding="utf-8")
    assert 'name = "branchrift"' in text
    assert 'version = "0.2.0"' in text
    assert "BranchRift" in text


def test_cli_entry_points_resolve_to_the_same_main():
    primary = _script_target("branchrift")
    legacy = _script_target("preflight")
    assert primary == "preflight.cli:main"
    assert legacy == "preflight.cli:main"
    assert _load_entrypoint(primary) is main
    assert _load_entrypoint(legacy) is main


def test_report_heading_is_branchrift(capsys):
    print_report(_minimal_report())
    output = capsys.readouterr().out
    assert output.startswith("=== BranchRift ===\n")
    assert "Repository Preflight" not in output
    assert "Analyzed:" in output
    assert "What changed:" in output
    assert "Governance:" in output
