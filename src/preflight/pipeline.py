from .classifier import classify_file
from .ownership import resolve_ownership


def build_change_context(raw_change, config):
    path = raw_change["path"]
    default_owner = config.get("default_owner")

    ownership = resolve_ownership(
        path,
        config["ownership"],
        policy_status=config["ownership_policy_status"],
        default_owner=default_owner,
    )

    context = {
        **raw_change,
        "file_type": classify_file(path, config["file_types"]),
        "ownership": ownership,
        "owner": ownership.owner or "Unknown",
    }

    if raw_change["git_status"] in ("R", "C"):
        old_path = raw_change["old_path"]
        old_ownership = resolve_ownership(
            old_path,
            config["ownership"],
            policy_status=config["ownership_policy_status"],
            default_owner=default_owner,
        )

        context["old_ownership"] = old_ownership
        context["old_owner"] = old_ownership.owner or "Unknown"
        context["old_file_type"] = classify_file(
            old_path,
            config["file_types"]
        )

    return context