from preflight.report import build_report
from preflight.reporter import print_report


GOVERNANCE = {
    "critical_escalation": True,
    "critical_unknown_count": 5,
    "critical_unknown_ratio": 0.25,
}


def _summary(**overrides):
    data = {
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
    }
    data.update(overrides)
    return data


def _base_report(**overrides):
    report = {
        "branch": "feature/x",
        "base": "dev",
        "head": "HEAD",
        "repository_state": "CLEAN",
        "technical_risk": "LOW",
        "governance_status": "PASS",
        "summary": _summary(),
        "changes": [],
    }
    report.update(overrides)
    return report


def test_clean_source_only_change_is_concise(capsys):
    print_report(
        _base_report(
            technical_risk="MEDIUM",
            summary=_summary(
                total_changes=1,
                medium_count=1,
                manual_review_count=1,
                manual_review_files=["src/app.py"],
                required_checks=["build verification"],
                owner_counts={"Backend": 1},
                file_type_counts={"source": 1},
                status_counts={"M": 1},
            ),
            changes=[
                {
                    "path": "src/app.py",
                    "file_type": "source",
                    "git_status": "M",
                    "owner": "Backend",
                    "governance_issues": [],
                    "required_checks": ["build verification"],
                    "manual_review_required": True,
                    "technical_risk": "MEDIUM",
                }
            ],
            change_facts={"count": 0, "files": []},
            topology={
                "base_sha": "a" * 40,
                "head_sha": "b" * 40,
                "merge_base": "a" * 40,
                "behind": 0,
                "ahead": 1,
                "relationship": "LINEAR",
                "ff_eligible": True,
            },
            collisions={"count": 0, "binary_sensitive_count": 0, "files": []},
        )
    )
    output = capsys.readouterr().out
    assert "What changed:" in output
    assert "src/app.py" in output
    assert "Source/config:" in output
    assert "Binary:" not in output
    assert "Repository readiness:" not in output
    assert "Same-path collisions: 0" in output
    assert "Required verification:" in output
    assert "build verification" in output


def test_exact_scalar_change_appears_under_what_changed(capsys):
    print_report(
        _base_report(
            summary=_summary(total_changes=1, medium_count=1, file_type_counts={"source": 1}),
            changes=[{"path": "HPDPrototypeCharacter.cpp", "file_type": "source", "governance_issues": []}],
            change_facts={
                "count": 1,
                "files": [
                    {
                        "path": "HPDPrototypeCharacter.cpp",
                        "facts": [
                            {
                                "kind": "value_changed",
                                "key": "CatchRadius",
                                "before": "140.0f",
                                "after": "120.0f",
                            }
                        ],
                    }
                ],
            },
        )
    )
    output = capsys.readouterr().out
    assert "Source/config:" in output
    assert "CatchRadius: 140.0f -> 120.0f" in output
    assert "Exact changes:" not in output


def test_hydrated_lfs_map_lists_binary_and_readiness(capsys):
    print_report(
        _base_report(
            summary=_summary(total_changes=1, medium_count=1, file_type_counts={"map": 1}),
            changes=[{"path": "Content/Maps/LV_HPD_NetTest.umap", "file_type": "map", "governance_issues": []}],
            binary_readiness={
                "count": 1,
                "attention_count": 0,
                "files": [
                    {
                        "path": "Content/Maps/LV_HPD_NetTest.umap",
                        "lfs_managed": True,
                        "lfs_state": "hydrated",
                        "readiness": "ready",
                    }
                ],
            },
        )
    )
    output = capsys.readouterr().out
    assert "Binary:" in output
    assert "Content/Maps/LV_HPD_NetTest.umap" in output
    assert "Repository readiness:" in output
    assert "State: hydrated" in output
    assert output.count("Content/Maps/LV_HPD_NetTest.umap") >= 2


def test_lfs_pointer_attention_is_visible(capsys):
    print_report(
        _base_report(
            summary=_summary(total_changes=1, file_type_counts={"asset": 1}),
            changes=[{"path": "Content/Assets/Test.uasset", "file_type": "asset", "governance_issues": []}],
            binary_readiness={
                "count": 1,
                "attention_count": 1,
                "files": [
                    {
                        "path": "Content/Assets/Test.uasset",
                        "lfs_managed": True,
                        "lfs_state": "pointer",
                        "readiness": "attention",
                        "reason": "working tree contains an LFS pointer instead of hydrated binary content",
                    }
                ],
            },
        )
    )
    output = capsys.readouterr().out
    assert "Readiness: attention" in output
    assert "LFS pointer" in output


def test_governance_gap_is_visible(capsys):
    print_report(
        _base_report(
            governance_status="ATTENTION",
            summary=_summary(total_changes=1, governance_issue_count=1),
            changes=[
                {
                    "path": "scripts/orphan.py",
                    "file_type": "source",
                    "owner": "Unknown",
                    "governance_issues": [
                        {
                            "code": "OWNERSHIP_GAP",
                            "priority": "HIGH",
                            "message": "No ownership rule matches scripts/orphan.py",
                        }
                    ],
                }
            ],
        )
    )
    output = capsys.readouterr().out
    assert "Governance:" in output
    assert "ATTENTION" in output
    assert "OWNERSHIP_GAP" in output
    assert "scripts/orphan.py" in output


def test_collision_present_is_listed_under_integration(capsys):
    print_report(
        _base_report(
            topology={
                "base_sha": "a" * 40,
                "head_sha": "b" * 40,
                "merge_base": "c" * 40,
                "behind": 1,
                "ahead": 1,
                "relationship": "DIVERGED",
                "ff_eligible": False,
            },
            collisions={
                "count": 1,
                "binary_sensitive_count": 1,
                "files": [
                    {
                        "path": "Content/Maps/Test.umap",
                        "file_type": "map",
                        "binary_sensitive": True,
                    }
                ],
            },
        )
    )
    output = capsys.readouterr().out
    assert "Topology: DIVERGED" in output
    assert "Fast-forward eligible: no" in output
    assert "Same-path collisions: 1" in output
    assert "BINARY-SENSITIVE" in output


def test_empty_optional_sections_are_omitted(capsys):
    print_report(_base_report())
    output = capsys.readouterr().out
    assert "Repository readiness:" not in output
    assert "Required verification:" not in output
    assert "Source/config:" not in output
    assert "Binary:" not in output
    assert "Collisions:" not in output
    assert "Exact changes:" not in output
    assert "What changed:" in output
    assert "Governance:" in output


def test_provenance_section_uses_requested_and_resolved_revisions(capsys):
    print_report(
        _base_report(
            revision_provenance={
                "base": {"requested": "origin/dev", "sha": "a" * 40},
                "head": {"requested": "feature/b12", "sha": "b" * 40},
                "merge_base_sha": "c" * 40,
                "comparison": "merge-base...head",
                "head_is_current_checkout": False,
            }
        )
    )
    output = capsys.readouterr().out
    assert "Analyzed:" in output
    assert "Base: origin/dev" in output
    assert "Head: feature/b12" in output
    assert "a" * 40 in output
    assert "b" * 40 in output
    assert "Comparison: merge-base...head" in output
    assert "Head is current checkout: no" in output


def test_singular_file_changed_grammar(capsys):
    print_report(
        _base_report(
            summary=_summary(total_changes=1, medium_count=1, file_type_counts={"source": 1}),
            changes=[{"path": "src/app.py", "file_type": "source", "governance_issues": []}],
        )
    )
    output = capsys.readouterr().out
    assert "1 file changed" in output
    assert "1 files changed" not in output


def test_plural_files_changed_grammar(capsys):
    print_report(
        _base_report(
            summary=_summary(total_changes=2, medium_count=2),
            changes=[
                {"path": "a.py", "file_type": "source", "governance_issues": []},
                {"path": "b.py", "file_type": "source", "governance_issues": []},
            ],
        )
    )
    output = capsys.readouterr().out
    assert "2 files changed" in output


def test_requested_sha_is_not_printed_twice(capsys):
    sha = "a" * 40
    head_sha = "b" * 40
    print_report(
        _base_report(
            revision_provenance={
                "base": {"requested": sha, "sha": sha},
                "head": {"requested": "feature/b12", "sha": head_sha},
                "merge_base_sha": "c" * 40,
                "comparison": "merge-base...head",
                "head_is_current_checkout": False,
            }
        )
    )
    output = capsys.readouterr().out
    lines = output.splitlines()
    base_line = next(line for line in lines if line.startswith("  Base:"))
    base_index = lines.index(base_line)
    assert base_line == f"  Base: {sha}"
    assert lines[base_index + 1].strip() != sha
    assert "Head: feature/b12" in output
    assert head_sha in output
