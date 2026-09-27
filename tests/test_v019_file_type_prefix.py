"""Regression: file-type prefixes use ownership's canonical prefix rules."""

import pytest

from preflight.classifier import classify_file
from preflight.config import validate_file_types
from preflight.errors import ConfigError
from preflight.pathmatch import canonical_prefix


def _types(source_prefix, asset_prefix):
    return {
        "source": {"path_prefixes": [source_prefix]},
        "asset": {"path_prefixes": [asset_prefix]},
    }


def test_equivalent_file_type_prefixes_are_rejected():
    pairs = [("src", "src/"), ("src", "src\\"), ("src/", "src\\")]
    accepted = []
    for source_prefix, asset_prefix in pairs:
        file_types = _types(source_prefix, asset_prefix)
        chosen = classify_file("src/app.py", file_types)
        try:
            validate_file_types(file_types)
        except ConfigError:
            continue
        accepted.append(
            f"source={source_prefix!r} asset={asset_prefix!r} "
            f"canonical=({canonical_prefix(source_prefix)!r}, {canonical_prefix(asset_prefix)!r}) "
            f"classify('src/app.py')={chosen!r}"
        )

    if accepted:
        pytest.fail(
            "v0.1.8 accepted equivalent file-type prefixes:\n" + "\n".join(accepted)
        )


def test_equivalent_prefix_spellings_do_not_change_specificity():
    spellings = ["src", "src/", "src\\"]
    choices = {}
    for source_prefix in spellings:
        for asset_prefix in spellings:
            if canonical_prefix(source_prefix) != canonical_prefix(asset_prefix):
                continue
            chosen = classify_file("src/app.py", _types(source_prefix, asset_prefix))
            choices[(source_prefix, asset_prefix)] = chosen

    distinct = sorted(set(choices.values()))
    if len(distinct) != 1:
        rendered = "\n".join(
            f"source={source!r} asset={asset!r} -> {chosen}"
            for (source, asset), chosen in choices.items()
        )
        pytest.fail(
            "v0.1.8 specificity follows raw prefix spelling, not the canonical prefix.\n"
            f"distinct choices: {distinct}\n{rendered}"
        )


def test_trailing_separators_do_not_outrank_a_longer_canonical_prefix():
    file_types = {
        "source": {"path_prefixes": ["src///"]},
        "asset": {"path_prefixes": ["src/a"]},
    }
    chosen = classify_file("src/a/main.py", file_types)
    assert chosen == "asset", (
        "v0.1.8 let trailing separators outrank a longer canonical prefix: "
        f"source='src///' raw_len={len('src///')} canonical={canonical_prefix('src///')!r}; "
        f"asset='src/a' raw_len={len('src/a')} canonical={canonical_prefix('src/a')!r}; "
        f"classify('src/a/main.py')={chosen!r}"
    )


@pytest.mark.parametrize("prefix", ["/", "\\"])
def test_empty_canonical_file_type_prefix_is_rejected(prefix):
    file_types = {"source": {"path_prefixes": [prefix]}}
    samples = ["src/app.py", "README", "Audio/hit.wav"]
    observed = {path: classify_file(path, file_types) for path in samples}
    try:
        validate_file_types(file_types)
    except ConfigError:
        return

    pytest.fail(
        "v0.1.8 accepted a file-type prefix that canonicalizes to empty: "
        f"prefix={prefix!r} canonical={canonical_prefix(prefix)!r} classify={observed}"
    )
