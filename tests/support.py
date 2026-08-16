from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


def run_git(
    repo: Path,
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    effective = os.environ.copy()
    effective.update(
        {
            "GIT_AUTHOR_NAME": "Coordinator Test",
            "GIT_AUTHOR_EMAIL": "coordinator@example.invalid",
            "GIT_COMMITTER_NAME": "Coordinator Test",
            "GIT_COMMITTER_EMAIL": "coordinator@example.invalid",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if env:
        effective.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env=effective,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def initialize_git(repo: Path, *, commit: bool) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, "init", "--quiet", "--initial-branch=main")
    run_git(repo, "config", "user.name", "Coordinator Test")
    run_git(repo, "config", "user.email", "coordinator@example.invalid")
    if commit:
        (repo / "README.md").write_text("fixture\n", encoding="utf-8")
        run_git(repo, "add", "README.md")
        run_git(repo, "commit", "--quiet", "-m", "fixture")


def tree_hash(root: Path, *, excluded_names: Iterable[str] = ()) -> str:
    excluded = set(excluded_names)
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if any(part in excluded for part in path.relative_to(root).parts):
            continue
        digest.update(relative.encode("utf-8"))
        if path.is_symlink():
            digest.update(b"L")
            digest.update(os.readlink(path).encode("utf-8"))
        elif path.is_file():
            digest.update(b"F")
            digest.update(path.read_bytes())
        elif path.is_dir():
            digest.update(b"D")
    return digest.hexdigest()
