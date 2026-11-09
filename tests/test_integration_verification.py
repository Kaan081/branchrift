"""v0.5: merged-tree proof is distinct from a successful Git merge."""

import subprocess

from preflight.merge_simulation import simulate_merge


def git(repo, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, check=True,
    )
    return result.stdout.decode("utf-8", errors="replace").strip()


def write(repo, name, content):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def prepare(tmp_path, initial, left, right):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Integration Test")
    git(repo, "config", "user.email", "integration@example.com")
    git(repo, "config", "core.autocrlf", "false")
    for name, content in initial.items():
        write(repo, name, content)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    base_branch = git(repo, "branch", "--show-current")
    git(repo, "switch", "-c", "branch-right")
    for name, content in right.items():
        write(repo, name, content)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "right")
    right_sha = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", base_branch)
    for name, content in left.items():
        write(repo, name, content)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "left")
    left_sha = git(repo, "rev-parse", "HEAD")
    return repo, left_sha, right_sha


def snapshot(repo):
    return (git(repo, "rev-parse", "HEAD"), git(repo, "status", "--porcelain"), git(repo, "ls-files", "--stage"))


def test_merge_clean_but_combination_fails_tests(tmp_path):
    baseline = {
        "one.py": "def enabled():\n    return False\n",
        "two.py": "def enabled():\n    return False\n",
        "test_pair.py": (
            "from one import enabled as a\n"
            "from two import enabled as b\n"
            "def test_integration_contract():\n    assert not (a() and b())\n"
        ),
    }
    repo, left, right = prepare(
        tmp_path, baseline,
        {"one.py": "def enabled():\n    return True\n"},
        {"two.py": "def enabled():\n    return True\n"},
    )
    before = snapshot(repo)
    legacy = simulate_merge(left, right, cwd=repo)
    assert legacy["status"] == "CLEAN"
    assert "verification" not in legacy
    result = simulate_merge(left, right, cwd=repo, verify_pytest=True)
    assert result["status"] == "CLEAN"
    assert result["verification"]["status"] == "FAIL", result
    assert result["verification"]["exit_code"] == 1
    assert result["integration_tests_executed"] is True
    assert "test_integration_contract" in result["verification"]["stdout_tail"]
    assert result["result_tree_retained"] is False
    assert snapshot(repo) == before
    assert subprocess.run(["git", "cat-file", "-e", result["result_tree_oid"]], cwd=repo, capture_output=True).returncode != 0


def test_merge_clean_and_tests_pass(tmp_path):
    base = {
        "one.py": "def count():\n    return 1\n",
        "two.py": "def count():\n    return 1\n",
        "test_pair.py": (
            "from one import count as a\n"
            "from two import count as b\n"
            "def test_integrated():\n    assert a() + b() >= 2\n"
        ),
    }
    repo, left, right = prepare(
        tmp_path, base,
        {"one.py": "def count():\n    return 2\n"},
        {"two.py": "def count():\n    return 2\n"},
    )
    result = simulate_merge(left, right, cwd=repo, verify_pytest=True)
    assert result["status"] == "CLEAN"
    assert result["verification"]["status"] == "PASS", result
    assert result["verification"]["exit_code"] == 0
    assert result["integration_tests_executed"] is True
    assert "1 passed" in result["verification"]["stdout_tail"]


def test_conflict_skips_tests_and_reports_not_run(tmp_path):
    repo, left, right = prepare(
        tmp_path,
        {"a.py": "value = 1\n", "test_a.py": "def test_ok(): assert True\n"},
        {"a.py": "value = 2\n"},
        {"a.py": "value = 3\n"},
    )
    result = simulate_merge(left, right, cwd=repo, verify_pytest=True)
    assert result["status"] == "CONFLICTS"
    assert result["verification"]["status"] == "NOT_RUN"
    assert result["verification"]["test_runner_invoked"] is False
    assert result["integration_tests_executed"] is False


def test_no_tests_is_not_a_pass(tmp_path):
    repo, left, right = prepare(tmp_path, {"README.md": "readme\n"}, {"a.py": "a=1\n"}, {"b.py": "b=1\n"})
    result = simulate_merge(left, right, cwd=repo, verify_pytest=True)
    assert result["status"] == "CLEAN"
    assert result["verification"]["status"] == "NOT_RUN", result
    assert result["verification"]["exit_code"] == 5
    assert result["integration_tests_executed"] is False


def test_symlink_or_gitlink_in_tree_blocks_verification(tmp_path):
    # Cross-platform: construct Git symlink entry directly, no Windows symlink privilege needed.
    repo, left, right = prepare(
        tmp_path,
        {"README.md": "hello\n", "test_one.py": "def test_ok(): assert True\n"},
        {"left.py": "a=1\n"}, {"right.py": "b=1\n"},
    )
    # Use a separate initial repo path on POSIX; Windows cannot create symlinks
    # easily, so this test uses index-info to attach a Git tree entry.
    payload = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=repo,
                             input=b"outside", capture_output=True, check=True).stdout.decode().strip()
    subprocess.run(["git", "update-index", "--add", "--cacheinfo", "120000," + payload + ",outside"], cwd=repo, check=True)
    git(repo, "commit", "-m", "add symlink index entry")
    linked = git(repo, "rev-parse", "HEAD")
    result = simulate_merge(linked, right, cwd=repo, verify_pytest=True)
    assert result["status"] == "CLEAN", result
    assert result["verification"]["status"] == "NOT_RUN", result
    assert "symlinks/submodules" in result["verification"]["reason"]
    assert result["integration_tests_executed"] is False


def test_uncommitted_edits_do_not_contaminate_merged_tests(tmp_path):
    repo, left, right = prepare(
        tmp_path,
        {"test_basic.py": "def test_basic(): assert True\n"},
        {"left.py": "value = 1\n"},
        {"right.py": "value = 2\n"},
    )
    write(repo, "test_basic.py", "def test_basic(): assert False\n")
    before = snapshot(repo)
    result = simulate_merge(left, right, cwd=repo, verify_pytest=True)
    assert result["status"] == "CLEAN"
    assert result["verification"]["status"] == "PASS", result
    assert snapshot(repo) == before


def test_bad_sha_does_not_run_tests(tmp_path):
    result = simulate_merge("bad ref", "a" * 40, cwd=tmp_path, verify_pytest=True)
    assert result["status"] == "ERROR"
    assert result["verification"]["status"] == "NOT_RUN"
    assert result["integration_tests_executed"] is False


def test_pytest_failure_is_not_a_merge_conflict(tmp_path):
    repo, left, right = prepare(
        tmp_path, {"test_fail.py": "def test_always_fails(): assert False\n"},
        {"left.py": "a = 1\n"}, {"right.py": "b = 1\n"},
    )
    result = simulate_merge(left, right, cwd=repo, verify_pytest=True)
    assert result["status"] == "CLEAN"
    assert result["conflicted_path_count"] == 0
    assert result["verification"]["status"] == "FAIL"


def test_output_is_bounded_even_if_tests_are_noisy(tmp_path):
    repo, left, right = prepare(
        tmp_path,
        {"test_noise.py": "def test_noise():\n    assert False, 'x' * 10000\n"},
        {"a.py": "a = 1\n"}, {"b.py": "b = 1\n"},
    )
    result = simulate_merge(left, right, cwd=repo, verify_pytest=True)
    assert result["verification"]["status"] == "FAIL"
    assert len(result["verification"]["stdout_tail"]) <= 3000
    assert len(result["verification"]["stderr_tail"]) <= 3000


def test_preflight_cli_flag_defaults_off():
    # The fixture repo in this local development bundle does not include all
    # production CLI modules; this test is still exercised in the full user repo.
    from preflight.cli import parse_args
    assert parse_args([]).verify_pytest is False
    assert parse_args(["--verify-pytest"]).verify_pytest is True


def test_cli_verify_returns_distinct_merge_and_test_results(tmp_path, capsys):
    import json
    from preflight.cli import run
    base = {
        "one.py": "def active(): return False\n",
        "two.py": "def active(): return False\n",
        "test_contract.py": (
            "from one import active as a\n"
            "from two import active as b\n"
            "def test_contract(): assert not (a() and b())\n"
        ),
    }
    repo, left, right = prepare(
        tmp_path, base,
        {"one.py": "def active(): return True\n"},
        {"two.py": "def active(): return True\n"},
    )
    old = run(["--base", left, "--head", right, "--json"], cwd=repo)
    capsys.readouterr()
    assert "merge_simulation" not in old
    new = run(["--base", left, "--head", right, "--verify-pytest", "--json"], cwd=repo)
    decoded = json.loads(capsys.readouterr().out)
    assert decoded["schema_version"] == old["schema_version"]
    assert decoded["merge_simulation"]["status"] == "CLEAN"
    assert decoded["merge_simulation"]["verification"]["status"] == "FAIL"
    assert decoded["merge_simulation"]["integration_tests_executed"] is True
    run(["--base", left, "--head", right, "--verify-pytest"], cwd=repo)
    compact = capsys.readouterr().out
    assert "pytest FAIL" in compact
    run(["--base", left, "--head", right, "--verify-pytest", "--verbose"], cwd=repo)
    verbose = capsys.readouterr().out
    assert "Merged-tree pytest: FAIL" in verbose
    assert "test_contract" in verbose
    assert snapshot(repo)[1] == ""
