from pathlib import PurePosixPath

from .pathmatch import canonical_prefix, path_prefix_matches


def classify_file(path, file_types):
    normalized_path = path.replace("\\", "/")
    file_name = PurePosixPath(normalized_path).name
    lower_path = normalized_path.lower()

    # 1) Exact filename. Config validation prevents ambiguous duplicates.
    for file_type, rules in file_types.items():
        if file_name in rules.get("names", []):
            return file_type

    # 2) Path prefix. Longest matching prefix wins.
    prefix_matches = []
    for file_type, rules in file_types.items():
        for prefix in rules.get("path_prefixes", []):
            normalized_prefix = canonical_prefix(prefix).lower()
            if not normalized_prefix:
                continue
            if path_prefix_matches(lower_path, normalized_prefix):
                prefix_matches.append((len(normalized_prefix), file_type))

    if prefix_matches:
        return max(prefix_matches, key=lambda item: item[0])[1]

    # 3) Extension. Longest matching extension wins.
    extension_matches = []
    for file_type, rules in file_types.items():
        for extension in rules.get("extensions", []):
            normalized_extension = extension.lower()
            if lower_path.endswith(normalized_extension):
                extension_matches.append((len(normalized_extension), file_type))

    if extension_matches:
        return max(extension_matches, key=lambda item: item[0])[1]

    return "other"
