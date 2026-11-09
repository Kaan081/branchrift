"""Opt-in verification of a merged Git tree with the current Python interpreter.

This runs repository test code. It is NOT a security sandbox. Use trusted
repositories only. No installation, shell, checkout into original repo, network
setup, or arbitrary command strings are performed by BranchRift.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

PYTEST_TIMEOUT_SECONDS = 300
OUTPUT_TAIL_LIMIT = 3000


def _evidence(status, *, reason=None, exit_code=None, elapsed=None, stdout=b"", stderr=b"", invoked=False):
    result = {
        "status": status,
        "tool": "pytest",
        "command": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        "exit_code": exit_code,
        "duration_seconds": round(elapsed, 3) if elapsed is not None else None,
        "stdout_tail": stdout.decode("utf-8", errors="replace")[-OUTPUT_TAIL_LIMIT:],
        "stderr_tail": stderr.decode("utf-8", errors="replace")[-OUTPUT_TAIL_LIMIT:],
        "test_runner_invoked": invoked,
        "temporary_checkout_retained": False,
        "security_sandbox": False,
        "dependency_environment": "existing Python interpreter; no install",
    }
    if reason:
        result["reason"] = reason
    return result


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
    args = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    started = time.perf_counter()
    try:
        result = subprocess.run(
            args, cwd=destination, env=test_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _evidence("TIMEOUT", reason="Pytest exceeded time budget; results are incomplete",
                         elapsed=time.perf_counter()-started,
                         stdout=exc.stdout or b"", stderr=exc.stderr or b"", invoked=True)
    except OSError as exc:
        return _evidence("ERROR", reason="Test runner failed to start: " + type(exc).__name__)

    elapsed = time.perf_counter() - started
    err_text = result.stderr.decode("utf-8", errors="replace")
    if "No module named pytest" in err_text:
        return _evidence("NOT_RUN", reason="pytest is not installed in the active Python interpreter",
                         exit_code=result.returncode, elapsed=elapsed,
                         stdout=result.stdout, stderr=result.stderr, invoked=True)
    if result.returncode == 0:
        status = "PASS"
    elif result.returncode == 1:
        status = "FAIL"
    elif result.returncode == 5:
        status = "NOT_RUN"
    else:
        status = "ERROR"
    reason = "No tests collected" if result.returncode == 5 else None
    if status == "ERROR":
        reason = "Pytest infrastructure or configuration error"
    return _evidence(status, reason=reason, exit_code=result.returncode,
                     elapsed=elapsed, stdout=result.stdout, stderr=result.stderr,
                     invoked=True)
