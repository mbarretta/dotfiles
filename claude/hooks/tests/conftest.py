"""Fixtures for the claude/hooks tests.

Every test runs against a fake HOME and a fake vault under ``tmp_path``; the
autouse ``isolated_env`` fixture repoints HOME, the vault path, and git's global
config before any test body runs, so nothing reads or writes the real HOME or
the real vault.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

# Git variables that would redirect a git call away from the fixture repos.
_GIT_REDIRECTS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_NAMESPACE",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
)


def git(cwd: Path, *args: str) -> str:
    """Run git in ``cwd``, fail the test on error, return stdout."""
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def init_repo(path: Path) -> Path:
    """``git init`` ``path`` with one commit on ``main``."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    git(path, "add", "--", "README.md")
    git(path, "commit", "-q", "-m", "init")
    return path


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME, the vault, and git config at ``tmp_path``; return the fake HOME."""
    home = tmp_path / "home"
    (home / "workspace").mkdir(parents=True)
    gitconfig = home / ".gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Fixture\n\temail = fixture@example.invalid\n"
        "[commit]\n\tgpgsign = false\n"
        "[init]\n\tdefaultBranch = main\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OBSIDIAN_CLAUDE_VAULT_PATH", str(home / "workspace" / "obsidian-claude-vault"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # Repo discovery never climbs out of the test's own tmp dir.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    for name in (*_GIT_REDIRECTS, "CLAUDE_VAULT_WIRE", "CLAUDE_PROJECT_DIR"):
        monkeypatch.delenv(name, raising=False)
    return home


@pytest.fixture
def fake_home(isolated_env: Path) -> Path:
    """The fake HOME, with an empty ``workspace/`` inside it."""
    return isolated_env


@pytest.fixture
def vault(fake_home: Path) -> Path:
    """A git-initialised vault with one commit, at the OBSIDIAN_CLAUDE_VAULT_PATH location."""
    return init_repo(fake_home / "workspace" / "obsidian-claude-vault")


@pytest.fixture
def repo(fake_home: Path) -> Path:
    """A git repo with one commit at ``<HOME>/workspace/github/owner/name``."""
    return init_repo(fake_home / "workspace" / "github" / "owner" / "name")
