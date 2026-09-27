import json

from .change_facts import TERMINAL_FACTS_PER_FILE
from .collisions import is_binary_sensitive


MAX_FACT_TEXT = 100


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


def collect_governance_issues(report):
    issues = []
    for change in report["changes"]:
        for issue in change["governance_issues"]:
            issues.append({"path": change["path"], **issue})
    return issues


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
    issues = collect_governance_issues(report)
    print()
    print("Governance:")
    print(f"  {terminal_safe(report['governance_status'])}")
    for issue in issues:
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
        print("  Manual review:")
        for path in review_files:
            print(f"    - {terminal_safe(path)}")


def print_report(report):
    print("=== Repository Preflight ===")
    _print_analyzed(report)
    _print_what_changed(report)
    _print_readiness(report)
    _print_integration(report)
    _print_governance(report)
    _print_verification(report)


def print_json_report(report):
    print(json.dumps(report, indent=2, sort_keys=True))
