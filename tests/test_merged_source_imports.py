"""Regression tests: merged src-layout code must win over installed packages."""
import os
import subprocess

from preflight.merge_simulation import simulate_merge


def repo_pair(tmp_path, initial, left, right):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        proc = subprocess.run(["git", *args], cwd=repo,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True)
        return proc.stdout.decode("utf-8").strip()

    def write(files):
        for name, body in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        git("add", ".")

    git("init")
    git("config", "user.name", "Source Import Acceptance")
    git("config", "user.email", "source-import@example.invalid")
    git("config", "core.autocrlf", "false")
    write(initial)
    git("commit", "-m", "initial")
    branch = git("branch", "--show-current")
    git("switch", "-c", "right")
    write(right)
    git("commit", "-m", "right")
    head = git("rev-parse", "HEAD")
    git("switch", branch)
    write(left)
    git("commit", "-m", "left")
    base = git("rev-parse", "HEAD")
    return repo, base, head


def test_src_layout_imports_exact_merged_checkout(tmp_path, monkeypatch):
    test = (
        "from pathlib import Path\n"
        "import branchrift_fixture_src_proof as pkg\n"
        "def test_uses_merged_source():\n"
        "    assert pkg.value() == 42\n"
        "    root = Path(__file__).resolve().parents[1]\n"
        "    assert Path(pkg.__file__).resolve().is_relative_to((root / 'src').resolve())\n"
    )
    repo, base, head = repo_pair(
        tmp_path,
        {"src/branchrift_fixture_src_proof/__init__.py": "def value(): return 42\n",
         "tests/test_source_proof.py": test},
        {"left.txt": "left\n"}, {"right.txt": "right\n"},
    )
    # A parent PYTHONPATH cannot redirect merged imports to an arbitrary checkout.
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "wrong-import-root"))
    result = simulate_merge(base, head, cwd=repo, verify_pytest=True)
    v = result["verification"]
    assert result["status"] == "CLEAN"
    assert v["status"] == "PASS", v
    assert v["source_import_precedence"] == "merged_src_then_root"
    assert "1 passed" in v["stdout_tail"]


def test_two_individually_safe_src_changes_fail_only_when_merged(tmp_path):
    initial = {
        "src/branchrift_fixture_pair/__init__.py": "",
        "src/branchrift_fixture_pair/one.py": "def enabled(): return False\n",
        "src/branchrift_fixture_pair/two.py": "def enabled(): return False\n",
        "tests/test_pair.py": (
            "from branchrift_fixture_pair.one import enabled as a\n"
            "from branchrift_fixture_pair.two import enabled as b\n"
            "def test_combined_contract(): assert not (a() and b())\n"
        ),
    }
    repo, base, head = repo_pair(
        tmp_path, initial,
        {"src/branchrift_fixture_pair/one.py": "def enabled(): return True\n"},
        {"src/branchrift_fixture_pair/two.py": "def enabled(): return True\n"},
    )
    result = simulate_merge(base, head, cwd=repo, verify_pytest=True)
    v = result["verification"]
    assert result["status"] == "CLEAN"
    assert v["status"] == "FAIL", v
    assert v["exit_code"] == 1
    assert "test_combined_contract" in v["stdout_tail"]
    assert v["source_import_precedence"] == "merged_src_then_root"


def test_root_layout_still_supported(tmp_path):
    repo, base, head = repo_pair(
        tmp_path,
        {"single_module.py": "def count(): return 7\n",
         "test_root.py": "from single_module import count\ndef test_root(): assert count()==7\n"},
        {"left.txt": "left\n"}, {"right.txt": "right\n"},
    )
    result = simulate_merge(base, head, cwd=repo, verify_pytest=True)
    assert result["verification"]["status"] == "PASS", result
    assert result["verification"]["source_import_precedence"] == "merged_root"


def test_skipped_test_never_claims_local_import_precedence(tmp_path):
    repo, base, head = repo_pair(
        tmp_path,
        {"README.md": "no tests\n"},
        {"left.txt": "left\n"}, {"right.txt": "right\n"},
    )
    result = simulate_merge(base, head, cwd=repo, verify_pytest=True)
    assert result["verification"]["status"] == "NOT_RUN"
    assert result["verification"]["source_import_precedence"] == "merged_root"
