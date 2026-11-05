#!/usr/bin/env python3
"""Migrate per-repo Claude artifacts into the claude vault, one repo at a time.

A dry run by default: prints one row per candidate repo (the git roots matching
``~/workspace/github/*/*`` plus ``~/workspace/obsidian-primary-vault``) with its
mirror-dir file counts, lessons and memory state, and blockers, then lists the
memory dirs that match no repo or more than one. ``--apply --only <slug>``
migrates exactly one repo; there is deliberately no way to apply to all of them.

Exit codes: 0 success, 1 a copy failed verification, 2 usage error or refusal
(blocker, excluded or unwireable root, unknown slug). Python 3 stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import filecmp
import json
import os
import re
import shutil
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_vault_lib as lib  # noqa: E402

PROJECT_SUBDIRS = ("plans", "research", "reviews", "mockups", "memory")
MOVED_NAME = "MOVED.md"
SESSIONS_UNKNOWN = "sessions: unknown, confirm no Claude session is open"
LESSONS_COMMIT_MSG = "chore: move lessons.md to the claude vault"
IN_PROGRESS_RE = re.compile(r'"status"\s*:\s*"in_progress"')
EXCLUDED_OWNER = "clickhouse"


class Refusal(Exception):
    """A condition that stops ``--apply`` with exit 2."""


class VerifyError(Exception):
    """A copy that failed verification; stops ``--apply`` with exit 1."""


# --- discovery --------------------------------------------------------------


def encode(root: Path) -> str:
    """Claude Code's project-dir name for ``root``; not reversible, never decode it."""
    return "-" + str(root).lstrip("/").replace("/", "-").replace(".", "-")


def memory_dir(root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / encode(root) / "memory"


def _is_git_root(path: Path) -> bool:
    if not path.is_dir() or path.is_symlink():
        return False
    root = lib.main_root(path)
    return root is not None and root.resolve() == path.resolve()


def discover() -> tuple[list[Path], list[Path]]:
    """``(candidates, excluded)``: the migratable roots and the clickhouse team clones."""
    workspace = Path.home() / "workspace"
    vault = lib.vault_path()
    vault_resolved = vault.resolve() if vault else None
    candidates: list[Path] = []
    excluded: list[Path] = []
    github = workspace / "github"
    paths = sorted(github.glob("*/*")) if github.is_dir() else []
    paths.append(workspace / "obsidian-primary-vault")
    for path in paths:
        if not _is_git_root(path):
            continue
        if vault_resolved is not None and path.resolve() == vault_resolved:
            continue
        if path.parent.name == EXCLUDED_OWNER:
            excluded.append(path)
        else:
            candidates.append(path)
    return candidates, excluded


def _files_under(base: Path) -> list[Path]:
    """Regular non-symlink files under ``base``, recursively, in a stable order."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_file() and not path.is_symlink():
                found.append(path)
    return sorted(found)


def _populated_memory_dirs() -> list[Path]:
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return []
    return sorted(
        mem
        for mem in (p / "memory" for p in projects.iterdir())
        if mem.is_dir() and _files_under(mem)
    )


def _memory_moved(mem: Path) -> bool:
    files = _files_under(mem)
    return len(files) == 1 and files[0] == mem / MOVED_NAME


# --- sessions ---------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except (OSError, OverflowError, ValueError):
        return False
    return True


def live_sessions() -> list[dict] | None:
    """Live entries in ``~/.claude/sessions/*.json``, or None when that state is unknown.

    Unknown means the directory is absent or no file in it parses as a session
    entry (a JSON object with an integer ``pid`` and a string ``cwd``).
    """
    sessions = Path.home() / ".claude" / "sessions"
    if not sessions.is_dir():
        return None
    parsed = 0
    live = []
    for path in sorted(sessions.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        pid, cwd = data.get("pid"), data.get("cwd")
        if not isinstance(pid, int) or isinstance(pid, bool) or not isinstance(cwd, str):
            continue
        parsed += 1
        if _pid_alive(pid):
            live.append(data)
    return live if parsed else None


def _worktree_paths(root: Path) -> list[Path]:
    paths = [root.resolve()]
    result = lib._git(root, "worktree", "list", "--porcelain")
    if result is not None and result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                paths.append(Path(line[len("worktree "):]).resolve())
    return paths


def _session_in(root: Path, live: list[dict]) -> list[int]:
    trees = _worktree_paths(root)
    pids = []
    for entry in live:
        cwd = Path(entry["cwd"]).expanduser().resolve()
        if any(cwd == tree or cwd.is_relative_to(tree) for tree in trees):
            pids.append(entry["pid"])
    return pids


# --- rows -------------------------------------------------------------------


@dataclass
class Row:
    root: Path
    slug: str
    counts: dict[str, int]
    lessons: bool
    tracked: bool
    memory: str
    in_progress: list[str] = field(default_factory=list)
    hard_blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def blockers(self, allow_in_progress: bool = False) -> list[str]:
        soft = [] if allow_in_progress else [f"in_progress: {p}" for p in self.in_progress]
        return soft + self.hard_blockers


def _slug(root: Path, vault: Path) -> tuple[str, str | None]:
    try:
        return lib.slug_for(root, vault), None
    except lib.SlugCollision as exc:
        return root.name, f"slug collision: {exc}"


def build_row(
    root: Path,
    vault: Path,
    memory_owners: dict[str, list[Path]],
    live: list[dict] | None,
) -> Row:
    slug, collision = _slug(root, vault)
    claude = root / ".claude"
    present = set(lib.mirror_dirs(root))
    counts = {
        name: len(_files_under(claude / name)) if name in present else 0
        for name in lib.MIRROR_DIRS
    }
    listed = lib._git(root, "ls-files", "--", ".claude/plans")
    tracked = bool(listed and listed.returncode == 0 and listed.stdout.strip())

    mem = memory_dir(root)
    if len(memory_owners.get(encode(root), [])) > 1:
        memory = "ambiguous"
    elif not mem.is_dir():
        memory = "-"
    elif _memory_moved(mem):
        memory = "moved"
    else:
        memory = str(len(_files_under(mem)))

    row = Row(root, slug, counts, (claude / "lessons.md").is_file(), tracked, memory)
    plans = claude / "plans"
    if "plans" in present:
        for plan in sorted(plans.glob("*.json")):
            try:
                text = plan.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if IN_PROGRESS_RE.search(text):
                row.in_progress.append(plan.name)
    if collision:
        row.hard_blockers.append(collision)
    status = lib._git(root, "status", "--porcelain", "--untracked-files=no", "--", ".claude")
    if status is None or status.returncode != 0:
        row.hard_blockers.append("git status failed")
    elif status.stdout.strip():
        row.hard_blockers.append("uncommitted .claude changes")
    if live is None:
        row.notes.append(SESSIONS_UNKNOWN)
    else:
        for pid in _session_in(root, live):
            row.hard_blockers.append(f"live session pid {pid}")
    return row


def memory_owners(roots: list[Path]) -> dict[str, list[Path]]:
    """Forward-encode every root; map each encoded name to the roots that produce it."""
    owners: dict[str, list[Path]] = {}
    for root in roots:
        owners.setdefault(encode(root), []).append(root)
    return owners


def _all_roots(candidates: list[Path], excluded: list[Path]) -> list[Path]:
    roots = [*candidates, *excluded]
    vault = lib.vault_path()
    if vault is not None:
        roots.append(vault)
    return roots


def _table(rows: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip() for r in rows
    )


def _yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


def dry_run(vault: Path, only: str | None, allow_in_progress: bool) -> int:
    candidates, excluded = discover()
    owners = memory_owners(_all_roots(candidates, excluded))
    live = live_sessions()
    header = ["slug", "plans", "mockups", "reviews", "lessons", "tracked", "memory", "blockers", "notes"]
    lines = [header]
    for root in candidates:
        row = build_row(root, vault, owners, live)
        if only is not None and row.slug != only:
            continue
        lines.append([
            row.slug,
            str(row.counts["plans"]),
            str(row.counts["mockups"]),
            str(row.counts["reviews"]),
            _yes_no(row.lessons),
            _yes_no(row.tracked),
            row.memory,
            "; ".join(row.blockers(allow_in_progress)) or "-",
            "; ".join(row.notes) or "-",
        ])
    print(_table(lines))

    extra = []
    for mem in _populated_memory_dirs():
        matched = owners.get(mem.parent.name, [])
        if not matched:
            extra.append([str(mem), "unresolved; review for archive"])
        elif len(matched) > 1:
            extra.append([str(mem), "ambiguous: " + ", ".join(str(r) for r in matched)])
    global_plans = Path.home() / ".claude" / "plans"
    if global_plans.is_dir():
        extra.append([str(global_plans), "leave"])
    if extra:
        print()
        print(_table([["path", "action"], *extra]))
    return 0


# --- apply ------------------------------------------------------------------


def _today() -> str:
    return datetime.date.today().isoformat()


def ensure_project(root: Path, vault: Path, slug: str) -> None:
    """Create ``projects/<slug>/`` with its subfolders and a write-once ``_project.md``."""
    project = vault / "projects" / slug
    for name in PROJECT_SUBDIRS:
        (project / name).mkdir(parents=True, exist_ok=True)
    marker = project / "_project.md"
    if marker.exists():
        return
    remote = lib._git(root, "remote", "get-url", "origin")
    url = remote.stdout.strip() if remote is not None and remote.returncode == 0 else ""
    marker.write_text(
        f"---\nslug: {slug}\nrepo: {root}\nremote: {url}\ncreated: {_today()}\n---\n",
        encoding="utf-8",
    )


def mirror_and_verify(root: Path, vault: Path, slug: str) -> int:
    """Sweep the mirror dirs, then require every source file to match its copy byte for byte."""
    copied = lib.sweep(root, vault, slug)
    bad = []
    for name in lib.mirror_dirs(root):
        src_base = root / ".claude" / name
        dst_base = vault / "projects" / slug / name
        for src in _files_under(src_base):
            dst = dst_base / src.relative_to(src_base)
            if not dst.is_file() or not filecmp.cmp(src, dst, shallow=False):
                bad.append(str(dst))
    if bad:
        raise VerifyError("mirror copy missing or different: " + ", ".join(bad))
    return copied


def move_lessons(root: Path, vault: Path, slug: str) -> str | None:
    src = root / ".claude" / "lessons.md"
    if not src.is_file():
        return None
    dst = vault / "projects" / slug / "lessons.md"
    if dst.exists() and not filecmp.cmp(src, dst, shallow=False):
        raise VerifyError(f"{dst} already exists with different content; reconcile it by hand")
    if not dst.exists():
        shutil.copy2(src, dst)
    if not filecmp.cmp(src, dst, shallow=False):
        raise VerifyError(f"lessons copy {dst} differs from {src}")
    rel = ".claude/lessons.md"
    tracked = lib._git(root, "ls-files", "--error-unmatch", "--", rel)
    if tracked is not None and tracked.returncode == 0:
        for args in (("rm", "-q", "--", rel), ("commit", "-q", "-m", LESSONS_COMMIT_MSG, "--", rel)):
            result = lib._git(root, *args)
            if result is None or result.returncode != 0:
                err = result.stderr.strip() if result is not None else "git unavailable"
                raise VerifyError(f"git {args[0]} of {rel} failed: {err}")
        return "lessons moved; repo commit created"
    src.unlink()
    return "lessons moved"


def _frontmatter_bounds(lines: list[str]) -> int | None:
    """Index of the closing ``---`` of a leading frontmatter block, or None."""
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return i
    return None


def add_alias(text: str) -> str:
    """Add top-level ``aliases: [<name>]`` after a top-level ``name:`` frontmatter key."""
    lines = text.splitlines(keepends=True)
    end = _frontmatter_bounds(lines)
    if end is None:
        return text
    keys = {line.split(":", 1)[0] for line in lines[1:end] if line[:1] not in (" ", "\t", "#")}
    if "aliases" in keys:
        return text
    for i in range(1, end):
        key, sep, value = lines[i].partition(":")
        if sep and key == "name":
            name = value.strip().strip("'\"")
            if not name:
                return text
            item = name if re.fullmatch(r"[\w.-]+", name) else json.dumps(name)
            newline = "\r\n" if lines[i].endswith("\r\n") else "\n"
            lines.insert(i + 1, f"aliases: [{item}]{newline}")
            return "".join(lines)
    return text


def _transform(src: Path) -> bytes:
    data = src.read_bytes()
    if src.suffix != ".md":
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    text = add_alias(text).replace(os.path.expanduser("~") + "/", "~/")
    return text.encode("utf-8")


def _backup_path(slug: str) -> Path:
    backups = Path.home() / ".claude" / "backups"
    path = backups / f"memory-{slug}-{_today()}.tar.gz"
    n = 1
    while path.exists():
        path = backups / f"memory-{slug}-{_today()}-{n}.tar.gz"
        n += 1
    return path


def move_memory(root: Path, vault: Path, slug: str, owners: dict[str, list[Path]]) -> str | None:
    """Copy the encoded memory dir into the vault, back it up, empty it, and leave MOVED.md."""
    src = memory_dir(root)
    if len(owners.get(encode(root), [])) > 1:
        return f"memory dir {src} is ambiguous; left untouched"
    if not src.is_dir() or _memory_moved(src) or not _files_under(src):
        return None
    dst_base = vault / "projects" / slug / "memory"
    files = _files_under(src)
    planned = []
    for path in files:
        dst = dst_base / path.relative_to(src)
        content = _transform(path)
        if dst.exists() and dst.read_bytes() != content:
            raise VerifyError(f"{dst} already exists with different content; reconcile it by hand")
        planned.append((dst, content))
    for dst, content in planned:
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(content)
    copied = [dst for dst, content in planned if dst.is_file() and dst.read_bytes() == content]
    if len(copied) != len(files):
        raise VerifyError(f"memory copy has {len(copied)} of {len(files)} files")

    backup = _backup_path(slug)
    backup.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(backup, "w:gz") as tar:
        tar.add(src, arcname="memory")
    with tarfile.open(backup, "r:gz") as tar:
        archived = [m for m in tar.getmembers() if m.isfile()]
    if len(archived) != len(files):
        raise VerifyError(f"backup {backup} has {len(archived)} of {len(files)} files")

    for child in src.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    (src / MOVED_NAME).write_text(f"{dst_base}\n", encoding="utf-8")
    return f"memory moved ({len(files)} files); backup {backup}"


def _resolve_target(slug: str, vault: Path) -> tuple[Path, list[Path], list[Path]]:
    candidates, excluded = discover()
    for root in excluded:
        if _slug(root, vault)[0] == slug:
            raise Refusal(f"{root} is a clickhouse team clone; the migration excludes it")
    matches = [root for root in candidates if _slug(root, vault)[0] == slug]
    if not matches:
        raise Refusal(f"no candidate repo has slug {slug!r}; run without --apply to list them")
    if len(matches) > 1:
        raise Refusal(f"slug {slug!r} matches several repos: " + ", ".join(map(str, matches)))
    return matches[0], candidates, excluded


def _setting(path: Path, key: str):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data.get(key) if isinstance(data, dict) else None


def apply(vault: Path, slug: str, allow_in_progress: bool) -> int:
    root, candidates, excluded = _resolve_target(slug, vault)
    if not lib.wireable(root):
        raise Refusal(f"{root} is not wireable to the vault")
    owners = memory_owners(_all_roots(candidates, excluded))
    row = build_row(root, vault, owners, live_sessions())
    blockers = row.blockers(allow_in_progress)
    if blockers:
        raise Refusal(f"{slug} is blocked: " + "; ".join(blockers))
    for note in row.notes:
        print(f"note: {note}", file=sys.stderr)

    ensure_project(root, vault, slug)
    copied = mirror_and_verify(root, vault, slug)
    print(f"{slug}: mirrored {copied} new or changed files")
    for step in (move_lessons(root, vault, slug), move_memory(root, vault, slug, owners)):
        if step:
            print(f"{slug}: {step}")
    settings = root / ".claude" / "settings.local.json"
    target = str(vault / "projects" / slug / "memory")
    if lib.merge_setting(settings, "autoMemoryDirectory", target):
        print(f"{slug}: set autoMemoryDirectory in {settings}")
    elif _setting(settings, "autoMemoryDirectory") != target:
        print(f"warning: could not set autoMemoryDirectory in {settings} (not a JSON object)", file=sys.stderr)
    lib.vault_commit(vault, slug, f"{slug} artifacts migrated")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vault-migrate.py",
        allow_abbrev=False,  # "--all" must not silently mean --allow-in-progress
        description="Dry-run table of repo artifacts to migrate into the claude vault; "
        "--apply --only <slug> migrates one repo.",
    )
    parser.add_argument("--apply", action="store_true", help="migrate (requires --only)")
    parser.add_argument("--only", metavar="SLUG", help="limit to the repo with this slug")
    parser.add_argument(
        "--allow-in-progress",
        action="store_true",
        help="do not block on an in_progress plan JSON",
    )
    args = parser.parse_args(argv)
    if args.apply and not args.only:
        parser.print_usage(sys.stderr)
        print("vault-migrate.py: error: --apply requires --only <slug>", file=sys.stderr)
        return 2
    vault = lib.vault_path()
    if vault is None:
        print("vault-migrate.py: error: claude vault not found (need a git dir)", file=sys.stderr)
        return 2
    try:
        if args.apply:
            return apply(vault, args.only, args.allow_in_progress)
        return dry_run(vault, args.only, args.allow_in_progress)
    except Refusal as exc:
        print(f"vault-migrate.py: refused: {exc}", file=sys.stderr)
        return 2
    except VerifyError as exc:
        print(f"vault-migrate.py: verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
