import json
import sys
from contextlib import contextmanager

from .change_facts import TERMINAL_FACTS_PER_FILE
from .collisions import is_binary_sensitive


MAX_FACT_TEXT = 100
MANUAL_REVIEW_TERMINAL_LIMIT = 20


class _EncodingFallbackStream:
    """Text wrapper that escapes characters the destination encoding cannot store."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        return self._stream.write(_text_for_stream(text, self._stream))

    def flush(self):
        flush = getattr(self._stream, "flush", None)
        if flush is not None:
            flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _text_for_stream(text, stream):
    """Keep Unicode when the stream can encode it; otherwise escape the rest."""
    if not text:
        return text
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return text
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return text.encode(encoding, errors="backslashreplace").decode(encoding)
    return text


@contextmanager
def _terminal_stdout():
    """Route report printing through the active stdout encoding boundary."""
    current = sys.stdout
    if isinstance(current, _EncodingFallbackStream):
        yield
        return
    sys.stdout = _EncodingFallbackStream(current)
    try:
        yield
    finally:
        sys.stdout = current


def terminal_safe(value):
    """Escape terminal control characters in untrusted repo/config text."""
    text = str(value)
    escaped = []
    for char in text:
        code = ord(char)
        if char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif char.isprintable() and char != "\x1b":
            escaped.append(char)
        elif code <= 0xFF:
            escaped.append(f"\\x{code:02x}")
        elif code <= 0xFFFF:
            escaped.append(f"\\u{code:04x}")
        else:
            escaped.append(f"\\U{code:08x}")
    return "".join(escaped)

def _display_text(value):
    text = str(value)
    if len(text) > MAX_FACT_TEXT:
        return text[: MAX_FACT_TEXT - 3] + "..."
    return text


def format_change_fact(fact):
    kind = fact["kind"]
    if kind == "value_changed":
        return (
            f"{terminal_safe(fact['key'])}: "
            f"{terminal_safe(_display_text(fact['before']))} -> "
            f"{terminal_safe(_display_text(fact['after']))}"
        )
    if kind == "line_added":
        return f"+ added: {terminal_safe(_display_text(fact['text']))}"
    if kind == "line_removed":
        return f"- removed: {terminal_safe(_display_text(fact['text']))}"
    return terminal_safe(kind)


def _yes_no(value):
    return "yes" if value else "no"


def _facts_by_path(report):
    mapping = {}
    for entry in (report.get("change_facts") or {}).get("files") or []:
        mapping[entry["path"]] = entry.get("facts") or []
    return mapping


def _is_binary_change(change):
    return is_binary_sensitive(change.get("file_type")) or is_binary_sensitive(
        change.get("old_file_type")
    )


def _print_revision_identity(label, requested, sha):
    requested_text = terminal_safe(requested)
    print(f"  {label}: {requested_text}")
    if requested != sha:
        print(f"        {terminal_safe(sha)}")


def _print_analyzed(report):
    print("Analyzed:")
    provenance = report.get("revision_provenance")
    topology = report.get("topology")
    if provenance:
        base = provenance["base"]
        head = provenance["head"]
        _print_revision_identity("Base", base["requested"], base["sha"])
        _print_revision_identity("Head", head["requested"], head["sha"])
        print(f"  Merge base: {terminal_safe(provenance['merge_base_sha'])}")
        print(f"  Comparison: {terminal_safe(provenance['comparison'])}")
        print(
            "  Head is current checkout: "
            f"{_yes_no(provenance['head_is_current_checkout'])}"
        )
    else:
        print(f"  Base: {terminal_safe(report['base'])}")
        print(f"  Head: {terminal_safe(report['head'])}")
        if topology is not None:
            print(f"  Merge base: {terminal_safe(topology['merge_base'])}")
            print(f"  Base SHA: {terminal_safe(topology['base_sha'])}")
            print(f"  Head SHA: {terminal_safe(topology['head_sha'])}")
    print(f"  Current branch: {terminal_safe(report['branch'])}")
    print(f"  Repository state: {terminal_safe(report['repository_state'])}")
    if report["repository_state"] == "DIRTY":
        print("  Warning: uncommitted changes are not included in the branch diff.")


def _print_file_group(title, changes, facts_by_path):
    if not changes:
        return
    print()
    print(f"  {title}")
    for change in changes:
        path = change["path"]
        print(f"    {terminal_safe(path)}")
        facts = facts_by_path.get(path) or []
        visible = facts[:TERMINAL_FACTS_PER_FILE]
        omitted = len(facts) - len(visible)
        for fact in visible:
            print(f"      {format_change_fact(fact)}")
        if omitted:
            print(f"      ... {omitted} more exact changes omitted")


def _print_what_changed(report):
    summary = report["summary"]
    print()
    print("What changed:")
    total = summary["total_changes"]
    noun = "file" if total == 1 else "files"
    print(f"  {total} {noun} changed")
    print(f"  Technical risk: {terminal_safe(report['technical_risk'])}")
    print(f"  High risk: {summary['high_count']}")
    print(f"  Medium risk: {summary['medium_count']}")
    print(f"  Low risk: {summary['low_count']}")
    if summary.get("status_counts"):
        mix = ", ".join(
            f"{terminal_safe(status)}={count}"
            for status, count in summary["status_counts"].items()
        )
        print(f"  Git status mix: {mix}")
    if summary.get("file_type_counts"):
        mix = ", ".join(
            f"{terminal_safe(file_type)}={count}"
            for file_type, count in summary["file_type_counts"].items()
        )
        print(f"  File types: {mix}")
    if summary.get("owner_counts"):
        mix = ", ".join(
            f"{terminal_safe(owner)}={count}"
            for owner, count in summary["owner_counts"].items()
        )
        print(f"  Owners: {mix}")

    facts_by_path = _facts_by_path(report)
    listed_paths = set()
    text_changes = []
    binary_changes = []
    for change in report["changes"]:
        listed_paths.add(change["path"])
        if _is_binary_change(change):
            binary_changes.append(change)
        else:
            text_changes.append(change)
    for path, facts in facts_by_path.items():
        if path in listed_paths or not facts:
            continue
        text_changes.append({"path": path})
    _print_file_group("Source/config:", text_changes, facts_by_path)
    _print_file_group("Binary:", binary_changes, {})


def _print_readiness(report):
    binary_readiness = report.get("binary_readiness")
    files = (binary_readiness or {}).get("files") or []
    if not files:
        return
    print()
    print("Repository readiness:")
    for item in files:
        print(f"  {terminal_safe(item['path'])}")
        managed = item.get("lfs_managed")
        if managed is True:
            managed_text = "yes"
        elif managed is False:
            managed_text = "no"
        else:
            managed_text = "unknown"
        print(f"    LFS-managed: {managed_text}")
        print(f"    State: {terminal_safe(item['lfs_state'])}")
        print(f"    Readiness: {terminal_safe(item['readiness'])}")
        if item.get("reason"):
            print(f"    Reason: {terminal_safe(item['reason'])}")


def _print_integration(report):
    topology = report.get("topology")
    collisions = report.get("collisions")
    if topology is None and collisions is None:
        return
    print()
    print("Integration:")
    if topology is not None:
        print(f"  Topology: {terminal_safe(topology['relationship'])}")
        print(f"  Fast-forward eligible: {_yes_no(topology['ff_eligible'])}")
        print(f"  Ahead: {terminal_safe(topology['ahead'])}")
        print(f"  Behind: {terminal_safe(topology['behind'])}")
    if collisions is not None:
        print(f"  Same-path collisions: {terminal_safe(collisions['count'])}")
        print(
            "  Binary-sensitive collisions: "
            f"{terminal_safe(collisions['binary_sensitive_count'])}"
        )
        for item in collisions.get("files") or []:
            path = terminal_safe(item["path"])
            file_type = terminal_safe(item["file_type"])
            if item.get("binary_sensitive"):
                print(f"    - {path} [{file_type}, BINARY-SENSITIVE]")
            else:
                print(f"    - {path} [{file_type}]")


def _print_governance(report):
    governance = report["governance"]
    policy_status = governance["ownership_policy_status"]

    print()
    print("Governance:")

    if governance["evaluation_status"] == "not_evaluated":
        print(
            "  Ownership policy: "
            f"{terminal_safe(policy_status.replace('_', ' '))}"
        )
        print("  Evaluation: not evaluated")
        return

    print(f"  {terminal_safe(report['governance_status'])}")

    for issue in governance["issues"]:
        print(
            f"  - [{terminal_safe(issue['code'])}] "
            f"{terminal_safe(issue['path'])}"
        )
        print(f"    {terminal_safe(issue['message'])}")


def _print_verification(report):
    summary = report["summary"]
    checks = summary.get("required_checks") or []
    review_files = summary.get("manual_review_files") or []
    if not checks and not review_files:
        return
    print()
    print("Required verification:")
    if checks:
        for check in checks:
            print(f"  - {terminal_safe(check)}")
    if review_files:
        count = len(review_files)
        noun = "file" if count == 1 else "files"
        print(f"  Manual review: {count} {noun}")
        shown = review_files[:MANUAL_REVIEW_TERMINAL_LIMIT]
        for path in shown:
            print(f"    - {terminal_safe(path)}")
        omitted = count - len(shown)
        if omitted:
            print(f"    ... {omitted} more paths omitted")


COMPACT_PATH_LIMIT = 3


def print_compact_report(report):
    """Bounded, advisory terminal summary. Never equate overlap with merge conflict.

    This is a presentation-only layer: the report and JSON contracts are unchanged.
    """
    with _terminal_stdout():
        summary = report["summary"]
        topology = report.get("topology") or {}
        collisions = report.get("collisions") or {}
        readiness = report.get("binary_readiness") or {}
        governance = report.get("governance") or {}
        base = terminal_safe(report.get("base", "?"))
        head = terminal_safe(report.get("head", "?"))

        print(f"BranchRift | {base} <- {head}")
        if topology:
            print(
                f"Topology: {terminal_safe(topology['relationship'])}"
                f" | ahead {topology['ahead']} / behind {topology['behind']}"
            )
        print(
            f"Changed: {summary['total_changes']} files"
            f" | manual review: {summary['manual_review_count']}"
        )
        if collisions:
            print(
                f"Same-path overlap: {collisions['count']}"
                f" | binary-sensitive: {collisions['binary_sensitive_count']}"
            )
        else:
            print("Same-path overlap: NOT CHECKED")
        simulation = report.get("merge_simulation")
        if simulation is None:
            print("Git merge conflict prediction: NOT CHECKED")
        else:
            status = terminal_safe(simulation["status"])
            count = simulation.get("conflicted_path_count", 0)
            verification = simulation.get("verification")
            if verification is None:
                check_note = "build/tests not run"
            else:
                check_note = "pytest " + terminal_safe(verification["status"]) + "; build not run"
            print(f"Git merge simulation: {status} "
                  f"({count} unmerged paths; {check_note})")
            if verification is not None and verification.get("reason"):
                print("Verification reason: " + terminal_safe(verification["reason"]))
            if simulation.get("reason"):
                print("Simulation reason: " + terminal_safe(simulation["reason"]))
        print(f"Change risk: {terminal_safe(report['technical_risk'])}")
        if report.get("repository_state") == "DIRTY":
            print("Worktree: DIRTY (uncommitted changes excluded)")

        reasons = []
        deletion_count = summary.get("status_counts", {}).get("D", 0)
        if deletion_count:
            reasons.append(f"{deletion_count} deleted paths")
        if collisions.get("binary_sensitive_count", 0):
            reasons.append(f"{collisions['binary_sensitive_count']} binary-sensitive overlaps")
        elif collisions.get("count", 0):
            reasons.append(f"{collisions['count']} same-path overlaps")
        if readiness.get("attention_count", 0):
            reasons.append(f"{readiness['attention_count']} LFS/readiness attention items")
        if governance.get("issues"):
            reasons.append(f"{len(governance['issues'])} governance issues")
        if not reasons and report["technical_risk"] != "LOW":
            types = summary.get("file_type_counts") or {}
            noteworthy = [
                f"{count} {terminal_safe(kind)} files"
                for kind, count in sorted(types.items())
                if count and kind in ("asset", "map", "build_config")
            ]
            reasons.extend(noteworthy[:2])
        if reasons:
            print("Attention: " + "; ".join(reasons[:3]))

        # These are recommendations from the analyzer, NOT executed checks.
        checks = summary.get("required_checks") or []
        if checks:
            selected = [terminal_safe(check) for check in checks[:3]]
            remainder = len(checks) - len(selected)
            suffix = f"; +{remainder} more" if remainder else ""
            print("Required checks (not run): " + "; ".join(selected) + suffix)

        # Actual merge conflicts first, then overlap and review candidates.
        ordered_paths = list((report.get("merge_simulation") or {}).get("conflicted_paths") or [])
        for item in collisions.get("files") or []:
            ordered_paths.append(item["path"])
        for item in governance.get("issues") or []:
            ordered_paths.append(item["path"])
        for item in readiness.get("files") or []:
            if item.get("readiness") == "attention":
                ordered_paths.append(item["path"])
        ordered_paths.extend(summary.get("manual_review_files") or [])
        shown = list(dict.fromkeys(ordered_paths))
        if shown:
            print("Review paths:")
            for path in shown[:COMPACT_PATH_LIMIT]:
                print(f"  - {terminal_safe(path)}")
            if len(shown) > COMPACT_PATH_LIMIT:
                print(f"  ... {len(shown) - COMPACT_PATH_LIMIT} more")
        print("Details: branchrift --verbose | Full data: branchrift --json")





def _print_merge_simulation(report):
    simulation = report.get("merge_simulation")
    if simulation is None:
        return
    print()
    print("Git merge simulation (opt-in):")
    print(f"  Git result: {terminal_safe(simulation['status'])}")
    verification = simulation.get("verification")
    if verification is None:
        print("  Integration build/tests: NOT RUN")
    else:
        print("  Integration build: NOT RUN")
        print("  Merged-tree pytest: " + terminal_safe(verification["status"]))
        print("  Test runner invoked: " + _yes_no(verification["test_runner_invoked"]))
        if verification.get("exit_code") is not None:
            print("  Test exit code: " + terminal_safe(verification["exit_code"]))
        if verification.get("duration_seconds") is not None:
            print("  Test duration (s): " + terminal_safe(verification["duration_seconds"]))
        if verification.get("reason"):
            print("  Verification reason: " + terminal_safe(verification["reason"]))
        for field in ("stdout_tail", "stderr_tail"):
            if verification.get(field) and verification["status"] != "PASS":
                print(f"  Pytest {field}: {terminal_safe(verification[field])}")
        print("  Security sandbox: NO (trusted repositories only)")
    print("  Conflict path scope: unmerged index entries (not exhaustive)")
    print(f"  Base SHA: {terminal_safe(simulation['base_sha'])}")
    print(f"  Head SHA: {terminal_safe(simulation['head_sha'])}")
    tree = simulation.get("result_tree_oid")
    if tree:
        print(f"  Temporary result tree: {terminal_safe(tree)} (not retained)")
    reason = simulation.get("reason")
    if reason:
        print(f"  Reason: {terminal_safe(reason)}")
    paths = simulation.get("conflicted_paths") or []
    if paths:
        print(f"  Unmerged paths: {len(paths)}")
        for path in paths[:MANUAL_REVIEW_TERMINAL_LIMIT]:
            print(f"    - {terminal_safe(path)}")
        if len(paths) > MANUAL_REVIEW_TERMINAL_LIMIT:
            print(f"    ... {len(paths) - MANUAL_REVIEW_TERMINAL_LIMIT} more paths omitted")

def print_report(report):
    with _terminal_stdout():
        print("=== BranchRift ===")
        _print_analyzed(report)
        _print_what_changed(report)
        _print_readiness(report)
        _print_integration(report)
        _print_merge_simulation(report)
        _print_governance(report)
        _print_verification(report)


def print_json_report(report):
    print(json.dumps(report, indent=2, sort_keys=True))
