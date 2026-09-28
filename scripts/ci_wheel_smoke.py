"""Smoke-test an already installed BranchRift wheel.

The caller must put the clean environment's executables on PATH and must not
set PYTHONPATH to the repository source tree.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def git(repo, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=True,
    )
    return result.stdout


def main():
    import preflight

    package_file = Path(preflight.__file__).resolve()
    repo_src = Path(__file__).resolve().parents[1] / "src"
    if repo_src in package_file.parents:
        raise SystemExit(f"preflight imported from the source tree: {package_file}")

    executable = shutil.which("branchrift")
    legacy = shutil.which("preflight")
    if not executable:
        raise SystemExit("branchrift executable was not found on PATH")
    if not legacy:
        raise SystemExit("preflight executable was not found on PATH")

    print(f"version={preflight.__version__}")
    print(f"package={package_file}")
    print(f"executable={executable}")
    print(f"legacy={legacy}")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init")
        git(repo, "config", "user.email", "smoke@example.com")
        git(repo, "config", "user.name", "Preflight Smoke")
        git(repo, "config", "core.autocrlf", "false")
        source = repo / "src" / "app.py"
        source.parent.mkdir()
        source.write_text("count = 1\n", encoding="utf-8")
        git(repo, "add", "--", ".")
        git(repo, "commit", "-m", "base")
        base = git(repo, "rev-parse", "HEAD").strip()
        source.write_text("count = 2\n", encoding="utf-8")
        git(repo, "add", "--", ".")
        git(repo, "commit", "-m", "change")

        config_path = root / "preflight.json"
        config_path.write_text(
            json.dumps(
                {
                    "ownership": [
                        {"match": "prefix", "path": "src/", "owner": "Code"}
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                executable,
                "--base",
                base,
                "--config",
                str(config_path),
                "--json",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            sys.stderr.write(result.stdout)
            raise SystemExit(result.returncode or 1)

        report = json.loads(result.stdout)
        paths = [change["path"] for change in report["changes"]]
        if paths != ["src/app.py"]:
            raise SystemExit(f"unexpected changed paths: {paths}")
        if report["summary"]["total_changes"] != 1:
            raise SystemExit("expected one changed file")
        print("smoke=ok")
        print(result.stdout)


if __name__ == "__main__":
    main()
