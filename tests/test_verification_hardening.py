"""v0.5.1: bounded evidence, subprocess timeouts, and conservative reporting."""

import os
import subprocess
import sys
import time

from preflight.integration_verification import _evidence, _run_bounded, _terminate_group


def _execute(tmp_path, script, timeout=5):
    return _run_bounded(
        [sys.executable, "-c", script], cwd=tmp_path,
        env=os.environ.copy(), timeout=timeout,
    )


def test_large_stdout_and_stderr_are_drained_without_unbounded_capture(tmp_path):
    script = (
        "import os\n"
        "os.write(1, b'A' * 2000000)\n"
        "os.write(2, b'B' * 2000000)\n"
    )
    result = _execute(tmp_path, script)
    assert result["returncode"] == 0
    assert result["streams_complete"] is True
    assert result["stdout_bytes"] == 2000000
    assert result["stderr_bytes"] == 2000000
    assert len(result["stdout"]) <= 16384
    assert len(result["stderr"]) <= 16384
    assert result["stdout"].endswith(b"A" * 50)
    assert result["stderr"].endswith(b"B" * 50)


def test_timeout_never_reports_success(tmp_path):
    result = _execute(tmp_path, "import time;time.sleep(30)", timeout=.2)
    assert result["timed_out"] is True
    assert result["cleanup"] == "attempted_not_guaranteed"
    assert result["streams_complete"] is True
    assert result["returncode"] != 0


def test_process_tree_cleanup_attempt_targets_spawned_descendants(tmp_path):
    marker = tmp_path / "descendant-did-work"
    script = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', "
        + repr(f"import time, pathlib; time.sleep(1.5); pathlib.Path({str(marker)!r}).write_text('alive')")
        + "])\n"
        "print('spawned', flush=True)\n"
        "time.sleep(30)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script], cwd=tmp_path, env=os.environ.copy(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=(os.name != "nt"),
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )
    try:
        assert proc.stdout.readline().strip() == b"spawned"
        _terminate_group(proc)
        assert proc.poll() is not None
        time.sleep(1.6)
        assert not marker.exists(), "Descendant survived cleanup and wrote a marker"
    finally:
        if proc.poll() is None:
            _terminate_group(proc)
        proc.stdout.close()
        proc.stderr.close()


def test_evidence_marks_truncation_and_cleanup_as_non_guaranteed():
    evidence = _evidence(
        "TIMEOUT", stdout=b"x" * 32, stderr=b"y" * 12,
        stdout_bytes=1000000, stderr_bytes=12,
        cleanup="attempted_not_guaranteed", invoked=True,
    )
    assert evidence["stdout_truncated"] is True
    assert evidence["stderr_truncated"] is False
    assert evidence["process_tree_cleanup"] == "attempted_not_guaranteed"
    assert evidence["test_runner_invoked"] is True
    assert evidence["security_sandbox"] is False


def test_no_timestamps_in_bounded_output_and_no_shell(tmp_path):
    result = _execute(tmp_path, "print('safe')")
    assert result["returncode"] == 0
    assert result["stdout"].strip() == b"safe"
    assert result["cleanup"] == "not_needed"
