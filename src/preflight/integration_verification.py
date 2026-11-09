"""Opt-in verification of a merged Git tree with the current Python interpreter.

This runs repository test code. It is NOT a security sandbox. Use trusted
repositories only. No installation, shell, checkout into original repo, network
setup, or arbitrary command strings are performed by BranchRift.
"""

import hashlib
import importlib.metadata
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PYTEST_TIMEOUT_SECONDS = 300
OUTPUT_TAIL_LIMIT = 3000
OUTPUT_CAPTURE_BYTES = 16384  # bounded memory per stream
OUTPUT_DRAIN_GRACE_SECONDS = 3


def _installed_pytest_version():
    """Installed distribution version in the current interpreter; not a lockfile proof."""
    try:
        return importlib.metadata.version("pytest")
    except importlib.metadata.PackageNotFoundError:
        return None


def _evidence(status, *, reason=None, exit_code=None, elapsed=None, stdout=b"", stderr=b"", invoked=False,
              stdout_bytes=None, stderr_bytes=None, streams_complete=True, cleanup="not_needed",
              stdout_sha256=None, stderr_sha256=None,
              source_import_precedence="not_run"):
    result = {
        "status": status,
        "tool": "pytest",
        "command": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        "exit_code": exit_code,
        "duration_seconds": round(elapsed, 3) if elapsed is not None else None,
        "stdout_tail": stdout.decode("utf-8", errors="replace")[-OUTPUT_TAIL_LIMIT:],
        "stderr_tail": stderr.decode("utf-8", errors="replace")[-OUTPUT_TAIL_LIMIT:],
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "output_hash_scope": "observed_stream_bytes",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "pytest_version": _installed_pytest_version(),
        "os_name": platform.system(),
        "os_release": platform.release(),
        "platform_machine": platform.machine(),
        "dependency_lock_verified": False,
        "environment_reproducible": False,
        "stdout_bytes_seen": stdout_bytes,
        "stderr_bytes_seen": stderr_bytes,
        "stdout_truncated": stdout_bytes is not None and stdout_bytes > len(stdout),
        "stderr_truncated": stderr_bytes is not None and stderr_bytes > len(stderr),
        "output_streams_complete": streams_complete,
        "process_tree_cleanup": cleanup,
        "test_runner_invoked": invoked,
        "temporary_checkout_retained": False,
        "security_sandbox": False,
        "dependency_environment": "existing Python interpreter; no install",
        "source_import_precedence": source_import_precedence,
    }
    if reason:
        result["reason"] = reason
    return result


class _Tail:
    """Drain stdout/stderr continuously while retaining only bounded bytes."""

    def __init__(self):
        self.total = 0
        self.digest = hashlib.sha256()
        self.data = b""
        self.error = False

    def drain(self, stream):
        try:
            while True:
                part = stream.read(65536)
                if not part:
                    break
                self.total += len(part)
                self.digest.update(part)
                self.data = (self.data + part)[-OUTPUT_CAPTURE_BYTES:]
        except OSError:
            self.error = True
        finally:
            stream.close()


def _terminate_group(proc):
    """Best-effort tree termination; NOT a sandbox or guaranteed cleanup."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _run_bounded(args, *, cwd, env, timeout):
    """No unbounded PIPE capture; timeout targets the process group/tree."""
    proc = subprocess.Popen(
        args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=(os.name != "nt"),
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )
    stdout = _Tail()
    stderr = _Tail()
    readers = [
        threading.Thread(target=stdout.drain, args=(proc.stdout,), daemon=True),
        threading.Thread(target=stderr.drain, args=(proc.stderr,), daemon=True),
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    cleanup = "not_needed"
    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        cleanup = "attempted_not_guaranteed"
        _terminate_group(proc)
        returncode = proc.poll()
    for reader in readers:
        reader.join(timeout=OUTPUT_DRAIN_GRACE_SECONDS)
    streams_complete = not any(reader.is_alive() for reader in readers) and not stdout.error and not stderr.error
    return {
        "returncode": returncode, "timed_out": timed_out,
        "stdout": stdout.data, "stderr": stderr.data,
        "stdout_bytes": stdout.total, "stderr_bytes": stderr.total,
        "stdout_sha256": stdout.digest.hexdigest(),
        "stderr_sha256": stderr.digest.hexdigest(),
        "streams_complete": streams_complete, "cleanup": cleanup,
    }


def verify_merged_tree(tree_oid, *, cwd, git_env, temp_root, git_call, timeout=PYTEST_TIMEOUT_SECONDS):
    """Check out a Git merge result into a disposable directory; run pytest there.

    Git merge-tree has already returned CLEAN, so its tree object still exists in
    the caller's disposable GIT_OBJECT_DIRECTORY. GIT_INDEX_FILE also points to
    a temporary index. Test processes do not inherit these Git overrides.
    """
    root = Path(temp_root)
    destination = root / "merged"
    destination.mkdir()
    git_timeout = 30

    # Symlinks and submodules would escape simple checkout assumptions or need
    # separate materialization. Fail closed rather than silently testing a partial tree.
    listing = git_call(["ls-tree", "-rz", tree_oid], cwd, env=git_env, timeout=git_timeout)
    if listing.returncode != 0:
        return _evidence("ERROR", reason="Could not enumerate merged Git tree")
    for record in listing.stdout.split(b"\0"):
        if not record:
            continue
        metadata, separator, _name = record.partition(b"\t")
        mode = metadata.split(b" ", 1)[0]
        if not separator or mode not in (b"100644", b"100755", b"120000", b"160000"):
            return _evidence("NOT_RUN", reason="Unsupported tree entry type; test checkout skipped")
        if mode in (b"120000", b"160000"):
            return _evidence("NOT_RUN", reason="Merged tree has symlinks/submodules; test checkout skipped")

    read_tree = git_call(["read-tree", tree_oid], cwd, env=git_env, timeout=git_timeout)
    if read_tree.returncode != 0:
        return _evidence("ERROR", reason="Could not load merged tree into temporary index")

    # Prefix includes the trailing separator required by git checkout-index.
    # Git attributes may use external filters; only run this on trusted repos.
    prefix = destination.resolve().as_posix() + "/"
    checkout_env = git_env.copy()
    checkout_env["GIT_LFS_SKIP_SMUDGE"] = "1"
    checkout = git_call(["checkout-index", "--all", "--prefix=" + prefix], cwd,
                        env=checkout_env, timeout=timeout)
    if checkout.returncode != 0:
        return _evidence("ERROR", reason="Temporary merged checkout failed; tests not run")

    test_env = os.environ.copy()
    for key in list(test_env):
        if key.startswith("GIT_") or key in ("PYTHONPATH", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
            test_env.pop(key, None)
    test_env["PYTHONDONTWRITEBYTECODE"] = "1"
    test_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    # The pytest process must import this *merged* project, not an unrelated
    # editable installation in the active interpreter. Restrict inherited paths,
    # then give the merged checkout precedence for common Python layouts.
    merged_src = destination / "src"
    if merged_src.is_dir():
        test_env["PYTHONPATH"] = os.pathsep.join((str(merged_src.resolve()), str(destination.resolve())))
        source_import_precedence = "merged_src_then_root"
    else:
        test_env["PYTHONPATH"] = str(destination.resolve())
        source_import_precedence = "merged_root"
    args = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    started = time.perf_counter()
    try:
        result = _run_bounded(args, cwd=destination, env=test_env, timeout=timeout)
    except OSError as exc:
        return _evidence("ERROR", reason="Test runner failed to start: " + type(exc).__name__)

    elapsed = time.perf_counter() - started
    details = {
        "exit_code": result["returncode"], "elapsed": elapsed,
        "stdout": result["stdout"], "stderr": result["stderr"],
        "stdout_bytes": result["stdout_bytes"],
        "stderr_bytes": result["stderr_bytes"],
        "stdout_sha256": result["stdout_sha256"],
        "stderr_sha256": result["stderr_sha256"],
        "streams_complete": result["streams_complete"],
        "cleanup": result["cleanup"], "invoked": True,
        "source_import_precedence": source_import_precedence,
    }
    if result["timed_out"]:
        return _evidence("TIMEOUT",
                         reason="Pytest exceeded time budget; descendant cleanup attempted, not guaranteed",
                         **details)
    if not result["streams_complete"]:
        return _evidence("ERROR",
                         reason="Test output streams did not close; possibly surviving child processes",
                         **details)
    err_text = result["stderr"].decode("utf-8", errors="replace")
    if "No module named pytest" in err_text:
        return _evidence("NOT_RUN", reason="pytest is not installed in the active Python interpreter",
                         **details)
    if result["returncode"] == 0:
        status = "PASS"
    elif result["returncode"] == 1:
        status = "FAIL"
    elif result["returncode"] == 5:
        status = "NOT_RUN"
    else:
        status = "ERROR"
    reason = "No tests collected" if result["returncode"] == 5 else None
    if status == "ERROR":
        reason = "Pytest infrastructure or configuration error"
    return _evidence(status, reason=reason, **details)
