import json
import subprocess
from pathlib import Path

from preflight.cli import run


UNICODE_SAMPLE = "çğşİ—é"
UNICODE_PATH = "notes/çağrışım-İ-é.md"


def git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=True,
    )


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Preflight Test")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "core.quotepath", "true")
    return repo


def _commit_all(repo, message):
    git(repo, "add", "--", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_unicode_content_and_paths_survive_preflight(tmp_path):
    repo = _init_repo(tmp_path)
    source = repo / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("count = 1\n", encoding="utf-8")
    base = _commit_all(repo, "base")

    source.write_text(
        f"count = 2\nlabel = \"{UNICODE_SAMPLE}\"\n",
        encoding="utf-8",
    )
    note = repo / UNICODE_PATH
    note.parent.mkdir()
    note.write_text(f"heading {UNICODE_SAMPLE}\n", encoding="utf-8")
    _commit_all(repo, "unicode")

    config_path = tmp_path / "preflight.json"
    config_path.write_text(
        json.dumps(
            {
                "ownership": [
                    {"match": "prefix", "path": "src/", "owner": "Code"},
                    {"match": "prefix", "path": "notes/", "owner": "Docs"},
                ]
            }
        ),
        encoding="utf-8",
    )

    def analyze():
        return run(
            ["--base", base, "--config", str(config_path), "--json"],
            cwd=repo,
        )

    first = analyze()
    second = analyze()

    paths = [change["path"] for change in first["changes"]]
    assert UNICODE_PATH in paths
    assert "src/app.py" in paths

    serialized = json.dumps(first, sort_keys=True)
    assert json.loads(serialized)["change_facts"] == first["change_facts"]
    readable = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert first["change_facts"] == second["change_facts"]

    facts_by_path = {
        item["path"]: item["facts"] for item in first["change_facts"]["files"]
    }
    app_facts = facts_by_path["src/app.py"]
    value_changes = [fact for fact in app_facts if fact["kind"] == "value_changed"]
    assert value_changes == [
        {
            "kind": "value_changed",
            "key": "count",
            "before": "1",
            "after": "2",
            "old_line": 1,
            "new_line": 1,
        }
    ]
    added = [fact["text"] for fact in app_facts if fact["kind"] == "line_added"]
    assert f'label = "{UNICODE_SAMPLE}"' in added

    note_facts = facts_by_path[UNICODE_PATH]
    assert any(UNICODE_SAMPLE in fact.get("text", "") for fact in note_facts)
    for character in ("ç", "ğ", "ş", "İ", "—", "é"):
        assert character in readable
