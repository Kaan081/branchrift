import re

from .collisions import is_binary_sensitive


TERMINAL_FACTS_PER_FILE = 20

HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)
EQUALS_ASSIGNMENT = re.compile(
    r"^\s*([A-Za-z_][\w.]*)\s*=(?!=)\s*(.+?)\s*$"
)
COLON_ASSIGNMENT = re.compile(
    r"^\s*([A-Za-z_][\w.]*)\s*:\s+(.+?)\s*$"
)
JSON_ASSIGNMENT = re.compile(
    r'^\s*"([^"\\]+)"\s*:\s*(.+?)\s*$'
)
SCALAR_VALUE = re.compile(
    r"""
    ^
    (?:
        true|false|null|none|nullptr|NULL|nil|True|False|None|TRUE|FALSE
        |
        -?(?:0[xX][0-9A-Fa-f]+|\d+)
        |
        -?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?[fFlL]?
        |
        "(?:\\.|[^"\\])*"
        |
        '(?:\\.|[^'\\])*'
    )
    $
    """,
    re.VERBOSE,
)


def _strip_a_or_b_prefix(path):
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _unquote_git_path(text):
    """Decode one Git C-quoted path, including its surrounding quotes."""
    if len(text) < 2 or not text.startswith('"'):
        return text

    body = []
    index = 1
    while index < len(text):
        char = text[index]
        if char == '"':
            break
        if char != "\\":
            body.append(char)
            index += 1
            continue
        if index + 1 >= len(text):
            body.append("\\")
            break
        nxt = text[index + 1]
        octal = text[index + 1 : index + 4]
        if len(octal) == 3 and all(digit in "01234567" for digit in octal):
            body.append(chr(int(octal, 8)))
            index += 4
            continue
        simple = {
            "\\": "\\",
            '"': '"',
            "n": "\n",
            "t": "\t",
            "a": "\a",
            "b": "\b",
            "f": "\f",
            "r": "\r",
            "v": "\v",
        }
        body.append(simple.get(nxt, nxt))
        index += 2

    # Octal escapes are raw bytes. UTF-8 paths decode; other bytes are replaced.
    return "".join(body).encode("latin-1", errors="replace").decode("utf-8", errors="replace")


def _parse_diff_path(raw):
    text = raw.strip()
    if text.startswith('"'):
        text = _unquote_git_path(text)
    elif "\t" in text:
        text = text.split("\t", 1)[0]
    if text == "/dev/null":
        return None
    return _strip_a_or_b_prefix(text)


def _is_meaningful_line(text):
    stripped = text.strip()
    if not stripped:
        return False
    return any(character.isalnum() for character in stripped)


def _normalize_scalar(raw):
    text = raw.strip()
    if text.endswith(",") or text.endswith(";"):
        text = text[:-1].strip()
    quoted = len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]
    if not quoted:
        if "//" in text:
            text = text.split("//", 1)[0].strip()
        if "#" in text:
            text = text.split("#", 1)[0].strip()
        if text.endswith(",") or text.endswith(";"):
            text = text[:-1].strip()
    if SCALAR_VALUE.match(text):
        return text
    return None


def parse_assignment(line):
    """Return (key, scalar_value) when the line is a conservative assignment."""
    for pattern in (EQUALS_ASSIGNMENT, JSON_ASSIGNMENT, COLON_ASSIGNMENT):
        match = pattern.match(line)
        if match is None:
            continue
        value = _normalize_scalar(match.group(2))
        if value is None:
            return None
        return match.group(1), value
    return None


def parse_unified_diff(raw):
    files = []
    current = None
    hunk = None
    old_line = 0
    new_line = 0

    def finish_hunk():
        nonlocal hunk
        if current is not None and hunk is not None:
            current["hunks"].append(hunk)
        hunk = None

    def finish_file():
        nonlocal current
        finish_hunk()
        if current is not None:
            files.append(current)
        current = None

    for raw_line in raw.splitlines():
        line = raw_line.rstrip("\r")
        if line.startswith("diff --git "):
            finish_file()
            current = {"path": None, "binary": False, "hunks": []}
            continue
        if line.startswith("Binary files ") and line.endswith(" differ"):
            if current is None:
                current = {"path": None, "binary": True, "hunks": []}
            current["binary"] = True
            rest = line[len("Binary files ") : -len(" differ")]
            if " and " in rest:
                current["path"] = _parse_diff_path(rest.split(" and ", 1)[1])
            continue
        if line.startswith("--- "):
            if current is None:
                current = {"path": None, "binary": False, "hunks": []}
            parsed = _parse_diff_path(line[4:])
            if parsed is not None:
                current["path"] = parsed
            continue
        if line.startswith("+++ "):
            if current is None:
                current = {"path": None, "binary": False, "hunks": []}
            parsed = _parse_diff_path(line[4:])
            if parsed is not None:
                current["path"] = parsed
            continue
        header = HUNK_HEADER.match(line)
        if header:
            finish_hunk()
            old_line = int(header.group(1))
            new_line = int(header.group(3))
            hunk = {"removed": [], "added": []}
            continue
        if hunk is None or current is None or current["binary"]:
            continue
        if line.startswith("\\"):
            continue
        if line.startswith("-"):
            text = line[1:]
            if _is_meaningful_line(text):
                hunk["removed"].append({"line": old_line, "text": text})
            old_line += 1
            continue
        if line.startswith("+"):
            text = line[1:]
            if _is_meaningful_line(text):
                hunk["added"].append({"line": new_line, "text": text})
            new_line += 1
            continue
        if line.startswith(" "):
            old_line += 1
            new_line += 1

    finish_file()
    return files


def _extract_hunk_facts(hunk):
    facts = []
    used_removed = set()
    used_added = set()
    removed_by_key = {}
    added_by_key = {}

    for index, entry in enumerate(hunk["removed"]):
        parsed = parse_assignment(entry["text"])
        if parsed is None:
            continue
        key, value = parsed
        removed_by_key.setdefault(key, []).append((index, value, entry))

    for index, entry in enumerate(hunk["added"]):
        parsed = parse_assignment(entry["text"])
        if parsed is None:
            continue
        key, value = parsed
        added_by_key.setdefault(key, []).append((index, value, entry))

    for key, removed_entries in removed_by_key.items():
        added_entries = added_by_key.get(key, [])
        if len(removed_entries) != 1 or len(added_entries) != 1:
            continue
        removed_index, before_value, before = removed_entries[0]
        added_index, after_value, after = added_entries[0]
        used_removed.add(removed_index)
        used_added.add(added_index)
        if before_value == after_value:
            continue
        facts.append(
            {
                "kind": "value_changed",
                "key": key,
                "before": before_value,
                "after": after_value,
                "old_line": before["line"],
                "new_line": after["line"],
            }
        )

    for index, entry in enumerate(hunk["removed"]):
        if index in used_removed:
            continue
        facts.append(
            {
                "kind": "line_removed",
                "text": entry["text"].strip(),
                "old_line": entry["line"],
            }
        )

    for index, entry in enumerate(hunk["added"]):
        if index in used_added:
            continue
        facts.append(
            {
                "kind": "line_added",
                "text": entry["text"].strip(),
                "new_line": entry["line"],
            }
        )
    return facts


def extract_change_facts(raw_diff, path_file_types=None):
    path_file_types = path_file_types or {}
    files = []
    for parsed in parse_unified_diff(raw_diff):
        path = parsed.get("path")
        if not path:
            continue
        file_type = path_file_types.get(path)
        if parsed["binary"] or is_binary_sensitive(file_type):
            continue
        facts = []
        for hunk in parsed["hunks"]:
            facts.extend(_extract_hunk_facts(hunk))
        if facts:
            files.append({"path": path, "facts": facts})
    files.sort(key=lambda item: item["path"])
    return files


def build_change_facts_report(raw_diff, path_file_types=None):
    files = extract_change_facts(raw_diff, path_file_types)
    return {
        "count": sum(len(item["facts"]) for item in files),
        "comparison": "merge-base...head",
        "files": files,
    }


def file_types_for_change_facts(changes):
    path_file_types = {}
    for change in changes:
        path_file_types[change["path"]] = change["file_type"]
        old_path = change.get("old_path")
        old_file_type = change.get("old_file_type")
        if old_path and old_file_type:
            path_file_types[old_path] = old_file_type
    return path_file_types
