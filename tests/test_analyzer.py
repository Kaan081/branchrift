from preflight.analyzer import analyze_change
from preflight.ownership import OwnershipResult, OwnershipStatus


def known_owner(owner):
    return OwnershipResult(
        status=OwnershipStatus.KNOWN,
        owner=owner,
    )


def no_owner_match():
    return OwnershipResult(
        status=OwnershipStatus.NO_MATCH,
        owner=None,
    )


def test_source_change_requires_review():
    change = {
        "git_status": "M",
        "path": "src/app.py",
        "file_type": "source",
        "owner": "Backend",
        "ownership": known_owner("Backend"),
    }

    result = analyze_change(change)

    assert result["technical_risk"] == "MEDIUM"
    assert result["confidence"] == "HIGH"
    assert result["manual_review_required"] is True
    assert "build verification" in result["required_checks"]

    assert change == {
        "git_status": "M",
        "path": "src/app.py",
        "file_type": "source",
        "owner": "Backend",
        "ownership": known_owner("Backend"),
    }


def test_asset_change_has_low_confidence():
    result = analyze_change(
        {
            "git_status": "M",
            "path": "Content/Enemy.uasset",
            "file_type": "asset",
            "owner": "Art",
            "ownership": known_owner("Art"),
        }
    )

    assert result["technical_risk"] == "MEDIUM"
    assert result["confidence"] == "LOW"
    assert result["manual_review_required"] is True


def test_unknown_owner_creates_governance_gap():
    result = analyze_change(
        {
            "git_status": "M",
            "path": "scripts/test.py",
            "file_type": "source",
            "owner": "Unknown",
            "ownership": no_owner_match(),
        }
    )

    codes = [issue["code"] for issue in result["governance_issues"]]

    assert "OWNERSHIP_GAP" in codes


def test_owner_crossing_creates_issue():
    result = analyze_change(
        {
            "git_status": "R",
            "old_path": "src/auth.py",
            "path": "src/security/auth.py",
            "old_owner": "Backend",
            "owner": "Security",
            "old_ownership": known_owner("Backend"),
            "ownership": known_owner("Security"),
            "old_file_type": "source",
            "file_type": "source",
        }
    )

    codes = [issue["code"] for issue in result["governance_issues"]]

    assert "OWNERSHIP_BOUNDARY_CROSSING" in codes
    assert result["manual_review_required"] is True


def test_added_asset_uses_verification_without_forcing_manual_review():
    result = analyze_change(
        {
            "git_status": "A",
            "path": "Content/NewTexture.uasset",
            "file_type": "asset",
            "owner": "Art",
            "ownership": known_owner("Art"),
        }
    )

    assert result["confidence"] == "LOW"
    assert result["manual_review_required"] is False
    assert "asset verification" in result["required_checks"]


def test_modified_map_still_requires_manual_review():
    result = analyze_change(
        {
            "git_status": "M",
            "path": "Content/Maps/Test.umap",
            "file_type": "map",
            "owner": "Shared",
            "ownership": known_owner("Shared"),
        }
    )

    assert result["manual_review_required"] is True
    assert "map integration verification" in result["required_checks"]