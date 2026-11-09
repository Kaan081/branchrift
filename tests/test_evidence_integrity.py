"""v0.5.2: provenance and bounded, cryptographic stream evidence."""
import hashlib
import os
import platform
import subprocess
import sys

from preflight.integration_verification import _evidence, _run_bounded
from preflight.merge_simulation import simulate_merge


def prepare(tmp_path, initial, left, right):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        proc = subprocess.run(["git", *args], cwd=repo,
                              capture_output=True, check=True)
        return proc.stdout.decode("utf-8").strip()

    def write_all(files):
        for name, content in files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git("add", ".")

    git("init")
    git("config", "user.name", "Evidence Test")
    git("config", "user.email", "evidence@example.com")
    git("config", "core.autocrlf", "false")
    write_all(initial)
    git("commit", "-m", "initial")
    main_branch = git("branch", "--show-current")
    git("switch", "-c", "right")
    write_all(right)
    git("commit", "-m", "right")
    head = git("rev-parse", "HEAD")
    git("switch", main_branch)
    write_all(left)
    git("commit", "-m", "left")
    base = git("rev-parse", "HEAD")
    return repo, base, head


def test_stream_hashes_cover_every_byte_even_when_tails_truncated(tmp_path):
    result = _run_bounded(
        [sys.executable, "-c",
         "import os; os.write(1, b'A'*250000); os.write(2, b'B'*200000)"],
        cwd=tmp_path, env=os.environ.copy(), timeout=10,
    )
    assert result["returncode"] == 0
    assert result["streams_complete"] is True
    assert result["stdout_bytes"] == 250000
    assert result["stderr_bytes"] == 200000
    assert result["stdout_sha256"] == hashlib.sha256(b"A" * 250000).hexdigest()
    assert result["stderr_sha256"] == hashlib.sha256(b"B" * 200000).hexdigest()
    assert len(result["stdout"]) <= 16384
    assert len(result["stderr"]) <= 16384


def test_empty_streams_hash_to_sha256_of_empty_bytes(tmp_path):
    result = _run_bounded(
        [sys.executable, "-c", "pass"], cwd=tmp_path,
        env=os.environ.copy(), timeout=10,
    )
    expected = hashlib.sha256(b"").hexdigest()
    assert result["stdout_sha256"] == expected
    assert result["stderr_sha256"] == expected
    assert result["stdout_bytes"] == result["stderr_bytes"] == 0


def test_evidence_metadata_is_explicitly_not_reproducible():
    evidence = _evidence("NOT_RUN", reason="Skipped")
    assert evidence["python_version"] == platform.python_version()
    assert evidence["python_implementation"] == platform.python_implementation()
    assert evidence["os_name"] == platform.system()
    assert evidence["platform_machine"] == platform.machine()
    assert evidence["dependency_lock_verified"] is False
    assert evidence["environment_reproducible"] is False
    assert evidence["stdout_sha256"] is None
    assert evidence["stderr_sha256"] is None
    assert evidence["recorded_at_utc"].endswith("Z")
    assert evidence["pytest_version"] is None or isinstance(evidence["pytest_version"], str)


def test_uninvoked_evidence_does_not_invent_output_hashes():
    evidence = _evidence("ERROR", stdout=b"partial", stdout_bytes=100)
    assert evidence["stdout_sha256"] is None
    assert evidence["stdout_truncated"] is True
    assert evidence["output_hash_scope"] == "observed_stream_bytes"


def test_run_result_has_matching_source_provenance_and_hashes(tmp_path):
    repo, base, head = prepare(
        tmp_path,
        {"test_ok.py": "def test_ok(): assert True\n"},
        {"left.py": "x = 1\n"}, {"right.py": "y = 2\n"},
    )
    result = simulate_merge(base, head, cwd=repo, verify_pytest=True)
    evidence = result["verification"]
    assert result["status"] == "CLEAN"
    assert evidence["status"] == "PASS", evidence
    assert evidence["exit_code"] == 0
    assert evidence["provenance"] == {
        "base_sha": base,
        "head_sha": head,
        "merged_tree_oid": result["result_tree_oid"],
    }
    assert evidence["stdout_sha256"] is not None
    assert evidence["stderr_sha256"] is not None
    assert evidence["output_streams_complete"] is True
    assert evidence["dependency_lock_verified"] is False
    assert evidence["environment_reproducible"] is False


def test_failed_test_keeps_full_stream_fingerprint(tmp_path):
    repo, base, head = prepare(
        tmp_path,
        {"test_fail.py": "def test_failure(): assert False\n"},
        {"left.py": "x = 1\n"}, {"right.py": "y = 2\n"},
    )
    result = simulate_merge(base, head, cwd=repo, verify_pytest=True)
    evidence = result["verification"]
    assert result["status"] == "CLEAN"
    assert evidence["status"] == "FAIL"
    assert evidence["exit_code"] == 1
    assert evidence["stdout_bytes_seen"] > 0
    assert len(evidence["stdout_sha256"]) == 64
    assert evidence["provenance"]["merged_tree_oid"] == result["result_tree_oid"]


def test_conflict_is_not_claimed_as_verified_execution(tmp_path):
    repo, base, head = prepare(
        tmp_path, {"shared.py": "x = 0\n"},
        {"shared.py": "x = 1\n"}, {"shared.py": "x = 2\n"},
    )
    result = simulate_merge(base, head, cwd=repo, verify_pytest=True)
    evidence = result["verification"]
    assert result["status"] == "CONFLICTS"
    assert evidence["status"] == "NOT_RUN"
    assert evidence["test_runner_invoked"] is False
    assert evidence["stdout_sha256"] is None
    assert evidence["provenance"]["base_sha"] == base
    assert evidence["provenance"]["head_sha"] == head


def test_default_simulation_never_adds_verification_metadata(tmp_path):
    repo, base, head = prepare(
        tmp_path, {"file.txt": "initial\n"},
        {"left.py": "a = 1\n"}, {"right.py": "b = 2\n"},
    )
    result = simulate_merge(base, head, cwd=repo)
    assert result["status"] == "CLEAN"
    assert "verification" not in result
