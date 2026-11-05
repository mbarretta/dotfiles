"""Shared resolver for the project-vault hook and the vault migration script.

One module owns the contracts both callers must agree on: where the vault is,
which git root a session belongs to, whether that root is wired to the vault,
the project slug, and the one-way additive mirror and scoped commit into
``<vault>/projects/<slug>/``. Python 3 standard library only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

MIRROR_DIRS = ("plans", "mockups", "reviews")
GIT_TIMEOUT = 10


class SlugCollision(Exception):
    """Both candidate slugs are already claimed by other repos in the vault."""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess | None:
    """Run ``git -C <cwd> <args>``; return None when git is missing or times out."""
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _configured_vault() -> Path:
    env = os.environ.get("OBSIDIAN_CLAUDE_VAULT_PATH")
    if env:
        return Path(env).expanduser()
    return Path.home() / "workspace" / "obsidian-claude-vault"


def vault_path() -> Path | None:
    """The claude vault, or None unless it is a directory containing ``.git``."""
    path = _configured_vault()
    if path.is_dir() and (path / ".git").exists():
        return path
    return None


def main_root(cwd: Path) -> Path | None:
    """The main worktree root of the repo containing ``cwd``, or None.

    A linked worktree (``<repo>/.claude/worktrees/x``) maps to ``<repo>``, because
    the root is taken as the parent of the shared ``--git-common-dir``. Returns
    None when ``cwd`` is not inside a git repository or the repository is bare.
    """
    result = _git(
        Path(cwd),
        "rev-parse",
        "--path-format=absolute",
        "--git-common-dir",
        "--is-bare-repository",
    )
    if result is None or result.returncode != 0:
        return None
    lines = result.stdout.splitlines()
    if len(lines) != 2 or lines[1].strip() != "false":
        return None
    common = Path(lines[0].strip())
    # A common dir not named .git belongs to a bare repo (or a separate git dir),
    # whose parent is not a worktree root.
    if common.name != ".git":
        return None
    return common.parent


def wireable(root: Path) -> bool:
    """Whether ``root`` may be wired to the vault.

    True only when ``root`` resolves under ``~/workspace/``, is not the vault
    itself, and ``CLAUDE_VAULT_WIRE`` is not ``"0"``.
    """
    if os.environ.get("CLAUDE_VAULT_WIRE") == "0":
        return False
    resolved = Path(root).resolve()
    workspace = (Path.home() / "workspace").resolve()
    if resolved == workspace or not resolved.is_relative_to(workspace):
        return False
    vault = _configured_vault().resolve()
    if resolved == vault or resolved.is_relative_to(vault):
        return False
    return True


def _frontmatter_value(path: Path, key: str) -> str | None:
    """The value of ``key:`` in the YAML frontmatter of ``path``, or None."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        name, sep, value = line.partition(":")
        if sep and name.strip() == key:
            return value.strip().strip("'\"")
    return None


def _claimed_by_other(root: Path, vault: Path, slug: str) -> bool:
    marker = vault / "projects" / slug / "_project.md"
    if not marker.is_file():
        return False
    repo = _frontmatter_value(marker, "repo")
    if not repo:
        return True
    return Path(repo).expanduser().resolve() != Path(root).resolve()


def slug_for(root: Path, vault: Path) -> str:
    """The vault project slug for ``root``.

    ``root.name``, unless another repo already owns that slug in
    ``vault/projects/<slug>/_project.md``; then ``<parent name>-<name>``. Raises
    ``SlugCollision`` when that is taken by another repo as well.
    """
    root = Path(root)
    for slug in (root.name, f"{root.parent.name}-{root.name}"):
        if not _claimed_by_other(root, vault, slug):
            return slug
    raise SlugCollision(
        f"slugs {root.name!r} and {root.parent.name}-{root.name!r} are both "
        f"claimed by other repos in {vault / 'projects'}"
    )


def mirror_dirs(root: Path) -> list[str]:
    """The subset of ``MIRROR_DIRS`` that exist as real directories in ``root/.claude``."""
    base = Path(root) / ".claude"
    return [
        name
        for name in MIRROR_DIRS
        if (base / name).is_dir() and not (base / name).is_symlink()
    ]


def copy_newer(src: Path, dst: Path) -> bool:
    """Copy ``src`` to ``dst`` when ``dst`` is missing or more than 1 s older.

    Preserves mtime via ``shutil.copy2`` and creates parents. Never deletes.
    Returns whether a copy happened; a source that vanished first is a skip.
    """
    src, dst = Path(src), Path(dst)
    try:
        dst_mtime = dst.stat().st_mtime
    except FileNotFoundError:
        dst_mtime = None
    try:
        if dst_mtime is not None and src.stat().st_mtime <= dst_mtime + 1:
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except FileNotFoundError:
        if not src.exists():
            return False
        raise
    return True


def sweep(root: Path, vault: Path, slug: str) -> int:
    """Mirror every file in the existing mirror dirs into ``vault/projects/<slug>/``.

    Symlinked files and directories are skipped. Returns the number of files copied.
    """
    root, vault = Path(root), Path(vault)
    copied = 0
    for name in mirror_dirs(root):
        src_base = root / ".claude" / name
        dst_base = vault / "projects" / slug / name
        for dirpath, _dirnames, filenames in os.walk(src_base):
            for filename in filenames:
                src = Path(dirpath) / filename
                if src.is_symlink() or not src.is_file():
                    continue
                if copy_newer(src, dst_base / src.relative_to(src_base)):
                    copied += 1
    return copied


def merge_setting(path: Path, key: str, value: str) -> bool:
    """Set ``key`` to ``value`` in the JSON object at ``path``, keeping every other key.

    A missing or empty file counts as ``{}``; parents are created. Writes only when
    the key is absent or different, with 2-space indent and a trailing newline.
    Returns whether the file changed; on unparseable JSON (or a non-object), it
    writes nothing and returns False.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    except (OSError, UnicodeDecodeError):
        return False
    if text.strip():
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return False
        if not isinstance(data, dict):
            return False
    else:
        data = {}
    if key in data and data[key] == value:
        return False
    data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True


def vault_commit(vault: Path, slug: str, message: str) -> None:
    """Commit pending changes under ``projects/<slug>`` in the vault, and nothing else.

    Skips while ``<vault>/.git/index.lock`` exists or when that path has no tracked
    or untracked changes. The pathspec on both ``add`` and ``commit`` keeps changes
    staged elsewhere out of the commit and leaves them staged. Never pushes and
    never raises: every git call has a timeout and failures are swallowed.
    """
    try:
        vault = Path(vault)
        if (vault / ".git" / "index.lock").exists():
            return
        spec = f"projects/{slug}"
        status = _git(vault, "status", "--porcelain", "--", spec)
        if status is None or status.returncode != 0 or not status.stdout.strip():
            return
        added = _git(vault, "add", "--", spec)
        if added is None or added.returncode != 0:
            return
        _git(vault, "commit", "-q", "-m", message, "--", spec)
    except Exception:
        return
