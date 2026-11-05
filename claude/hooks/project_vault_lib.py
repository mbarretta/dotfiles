"""Shared resolver for the project-vault hook and the vault migration script.

One module owns the contracts both callers must agree on: where the vault is,
which git root a session belongs to, whether that root is wired to the vault,
the project slug, and the one-way additive mirror and scoped commit into
``<vault>/projects/<slug>/``. Python 3 standard library only.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

MIRROR_DIRS = ("plans", "mockups", "reviews")
PROJECT_SUBDIRS = ("plans", "research", "reviews", "mockups", "memory")
GIT_TIMEOUT = 10
# Variables that point git at a different repository, index, or object store than
# ``-C <cwd>`` names. A hook inherits Claude Code's environment, so any of these
# would silently redirect every read and commit.
GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)


class SlugCollision(Exception):
    """Both candidate slugs are already claimed by other repos in the vault."""


class UnsafePath(Exception):
    """A vault path the lib would write through is a symlink."""


def git_run(cwd: Path, *args: str) -> subprocess.CompletedProcess | None:
    """Run ``git -C <cwd> <args>``; return None when git is missing or times out.

    The ``GIT_LOCATION_VARS`` are dropped from the environment so ``cwd`` alone
    decides which repository git acts on.
    """
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def symlink_on_path(base: Path, path: Path) -> bool:
    """Whether ``path`` or any directory between ``base`` (exclusive) and it is a symlink.

    ``base`` itself may be a symlink: the user chooses where the vault lives.
    """
    base, path = Path(base), Path(path)
    try:
        rel = path.relative_to(base)
    except ValueError:
        return True
    current = base
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


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
    result = git_run(
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
    """Whether ``projects/<slug>`` belongs to a repo other than ``root``.

    Fails closed: a non-empty folder with no ``_project.md`` was made by hand or
    by something else, so it counts as claimed rather than adopted. A missing or
    empty folder is free.
    """
    folder = vault / "projects" / slug
    marker = folder / "_project.md"
    if not marker.is_file():
        if folder.is_symlink():
            return True
        if not folder.is_dir():
            # A file squatting on the slug claims it; a missing path is free.
            return folder.exists()
        try:
            return any(folder.iterdir())
        except OSError:
            return True
    repo = _frontmatter_value(marker, "repo")
    if not repo:
        return True
    return Path(repo).expanduser().resolve() != Path(root).resolve()


def slug_for(root: Path, vault: Path) -> str:
    """The vault project slug for ``root``.

    ``root.name``, unless another repo already owns that slug in
    ``vault/projects/<slug>/_project.md`` (or the folder exists, is non-empty, and
    has no ``_project.md``); then ``<parent name>-<name>``. Raises
    ``SlugCollision`` when that is taken as well.
    """
    root = Path(root)
    for slug in (root.name, f"{root.parent.name}-{root.name}"):
        if not _claimed_by_other(root, vault, slug):
            return slug
    raise SlugCollision(
        f"slugs {root.name!r} and {root.parent.name}-{root.name!r} are both "
        f"claimed by other repos in {vault / 'projects'}"
    )


def redact_url(url: str) -> str:
    """``url`` without any ``user:password@`` userinfo.

    Only URLs with a scheme carry credentials; scp-style ``git@host:path`` names a
    login, not a secret, and is returned unchanged.
    """
    if "://" not in url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if "@" not in parts.netloc:
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.rpartition("@")[2]))


def _yaml_str(value: str) -> str:
    """``value`` as a double-quoted YAML scalar, so no character can end the line or the block."""
    return json.dumps(value, ensure_ascii=False)


def ensure_project(root: Path, vault: Path, slug: str) -> Path:
    """Create ``vault/projects/<slug>/``, its subfolders, and a write-once ``_project.md``.

    The marker is written first, so an interrupted run leaves either an empty
    folder (still unclaimed) or a claimed one. An existing marker is never
    rewritten. The origin URL is recorded with credentials removed. Raises
    ``UnsafePath`` when ``projects`` or ``projects/<slug>`` is a symlink.
    Returns the project folder.
    """
    root, vault = Path(root), Path(vault)
    folder = vault / "projects" / slug
    if symlink_on_path(vault, folder):
        raise UnsafePath(f"{folder} or its parent is a symlink")
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / "_project.md"
    if not marker.exists():
        remote = git_run(root, "remote", "get-url", "origin")
        url = remote.stdout.strip() if remote is not None and remote.returncode == 0 else ""
        today = datetime.date.today().isoformat()
        text = (
            f"---\nslug: {_yaml_str(slug)}\nrepo: {_yaml_str(str(root))}\n"
            f"remote: {_yaml_str(redact_url(url))}\ncreated: {today}\n---\n\n"
            f"# {slug}\n\nArtifacts for `{root}`, kept by the project-vault hook.\n"
        )
        try:
            with open(marker, "x", encoding="utf-8") as fh:
                fh.write(text)
        except FileExistsError:
            pass
    for name in PROJECT_SUBDIRS:
        (folder / name).mkdir(exist_ok=True)
    return folder


def mirror_dirs(root: Path) -> list[str]:
    """The subset of ``MIRROR_DIRS`` that exist as real directories in ``root/.claude``."""
    base = Path(root) / ".claude"
    return [
        name
        for name in MIRROR_DIRS
        if (base / name).is_dir() and not (base / name).is_symlink()
    ]


def copy_newer(src: Path, dst: Path, base: Path) -> bool:
    """Copy ``src`` to ``dst`` when ``dst`` is missing, older, or a same-mtime different size.

    ``shutil.copy2`` carries the source mtime over to the nanosecond, so any later
    edit to ``src`` is strictly newer than its last copy; the size check catches a
    second edit inside one tick of a coarse-mtime filesystem. A vault-side edit
    (``dst`` newer) is never overwritten. The copy goes to a temp file renamed
    over ``dst``, so a symlink at ``dst`` is replaced, not followed, and nothing
    is written when any path component below ``base`` is a symlink. Creates
    parents, never deletes. Returns whether a copy happened; a source that
    vanished first is a skip.
    """
    src, dst = Path(src), Path(dst)
    if symlink_on_path(base, dst):
        return False
    try:
        src_stat = src.stat()
    except FileNotFoundError:
        return False
    try:
        dst_stat = dst.stat()
    except FileNotFoundError:
        dst_stat = None
    if dst_stat is not None:
        if src_stat.st_mtime_ns < dst_stat.st_mtime_ns:
            return False
        if src_stat.st_mtime_ns == dst_stat.st_mtime_ns and src_stat.st_size == dst_stat.st_size:
            return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if symlink_on_path(base, dst.parent):
        return False
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except FileNotFoundError:
        Path(tmp).unlink(missing_ok=True)
        if not src.exists():
            return False
        raise
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
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
                if copy_newer(src, dst_base / src.relative_to(src_base), vault):
                    copied += 1
    return copied


def merge_setting(path: Path, key: str, value: str) -> bool:
    """Set ``key`` to ``value`` in the JSON object at ``path``, keeping every other key.

    A missing or empty file counts as ``{}``; parents are created. Writes only when
    the key is absent or different, with 2-space indent and a trailing newline.
    Returns whether the file changed; on unparseable JSON (or a non-object), or
    when ``path`` or its directory is a symlink, it writes nothing and returns False.
    """
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        return False
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
        # :(literal) keeps a slug containing glob or magic characters from widening the scope.
        spec = f":(literal)projects/{slug}"
        status = git_run(vault, "status", "--porcelain", "--", spec)
        if status is None or status.returncode != 0 or not status.stdout.strip():
            return
        added = git_run(vault, "add", "--", spec)
        if added is None or added.returncode != 0:
            return
        git_run(vault, "commit", "-q", "-m", message, "--", spec)
    except Exception:
        return
