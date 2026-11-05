#!/usr/bin/env python3
"""Claude Code hook that keeps a project's artifacts in the claude vault.

Subcommands, each reading the hook JSON from stdin:

  start   SessionStart: create ``<vault>/projects/<slug>/``, point
          autoMemoryDirectory at it, sweep and commit what earlier sessions left,
          and inject the folder rules, lessons, and global memory as context.
  mirror  PostToolUse (Write|Edit|MultiEdit): copy an edited file under
          ``<repo>/.claude/{plans,mockups,reviews}`` into the vault.
  end     SessionEnd: sweep the mirror dirs and commit the session's artifacts.

A broken hook must never break a session, so every path exits 0, and any failure
leaves stdout and stderr empty. Python 3 standard library only.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

LESSONS_CAP = 8000
MEMORY_CAP = 2000
CONTEXT_CAP = 9000
MIRROR_SEGMENTS = ("/.claude/plans/", "/.claude/mockups/", "/.claude/reviews/")


def _lib():
    """Import project_vault_lib from this script's own directory."""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import project_vault_lib

    return project_vault_lib


def _today() -> str:
    return datetime.date.today().isoformat()


def _resolve(lib, cwd) -> tuple[Path, Path, str] | None:
    """``(root, vault, slug)`` for a wired repo containing ``cwd``, else None.

    Raises ``lib.SlugCollision`` when both candidate slugs are taken.
    """
    root = lib.main_root(Path(cwd))
    if root is None or not lib.wireable(root):
        return None
    vault = lib.vault_path()
    if vault is None:
        return None
    return root, vault, lib.slug_for(root, vault)


def _cwd(payload: dict):
    return payload.get("cwd") or os.getcwd()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _capped(body: str, cap: int, path: Path) -> str:
    if len(body) <= cap:
        return body
    return f"{body[:cap].rstrip()}\n\n[Truncated at {cap} chars. Read {path} for the rest.]"


def _append_capped(parts: list[str], intro: str, body: str, cap: int, path: Path) -> None:
    """Append ``intro`` plus ``body`` capped at ``cap``, shrinking the cap to fit CONTEXT_CAP.

    The cap only shrinks below its nominal value when the paths in the header are
    unusually long; the section is dropped when not even its intro and marker fit.
    """
    marker = len(f"\n\n[Truncated at {cap} chars. Read {path} for the rest.]")
    room = CONTEXT_CAP - len("\n\n".join(parts)) - len("\n\n") - len(intro) - marker
    cap = min(cap, room)
    if cap > 0:
        parts.append(intro + _capped(body, cap, path))


def _context(folder: Path, root: Path, vault: Path, memory_changed: bool) -> str:
    parts = [
        f"Artifact folder for this project: {folder}/. Design docs and research go in its research/, "
        f"reviews in reviews/, mockups in mockups/; plan-mode files are written to .claude/plans as "
        f"usual and mirrored there automatically."
    ]
    if memory_changed:
        parts.append("autoMemoryDirectory was just set; it takes effect next session.")

    # The vault copy is named relative to the folder above, to leave the budget for the body.
    lessons = folder / "lessons.md"
    body, source = _read(lessons), "lessons.md in that folder"
    if not body:
        lessons = root / ".claude" / "lessons.md"
        body, source = _read(lessons), f"{lessons} (unmigrated; run vault-migrate)"
    if body:
        intro = (
            f"Lessons for this project, from {source}. These are corrections the user made in "
            f"earlier sessions: follow them and do not repeat the mistakes they describe, unless "
            f"the user says otherwise in this session.\n\n"
        )
        _append_capped(parts, intro, body, LESSONS_CAP, lessons)

    memory = vault / "projects" / "_global" / "memory" / "MEMORY.md"
    body = _read(memory)
    if body:
        _append_capped(parts, f"Cross-project memory, from {memory}:\n\n", body, MEMORY_CAP, memory)

    # _append_capped keeps every section inside the budget; this only bounds a header
    # whose paths alone run past it.
    return "\n\n".join(parts)[:CONTEXT_CAP]


def start(payload: dict) -> str:
    lib = _lib()
    try:
        resolved = _resolve(lib, _cwd(payload))
    except lib.SlugCollision as exc:
        context = f"project-vault: vault wiring skipped, slug collision: {exc}".replace("\n", " ")
        return _session_start_output(context)
    if resolved is None:
        return ""
    root, vault, slug = resolved

    try:
        folder = lib.ensure_project(root, vault, slug)
    except lib.UnsafePath as exc:
        return _session_start_output(f"project-vault: vault wiring skipped, {exc}".replace("\n", " "))
    (vault / "projects" / "_global" / "memory").mkdir(parents=True, exist_ok=True)

    memory_dir = f"{vault}/projects/{slug}/memory"
    changed = lib.merge_setting(root / ".claude" / "settings.local.json", "autoMemoryDirectory", memory_dir)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir and Path(project_dir).is_dir() and Path(project_dir).resolve() != root.resolve():
        target = Path(project_dir) / ".claude" / "settings.local.json"
        changed = lib.merge_setting(target, "autoMemoryDirectory", memory_dir) or changed

    lib.sweep(root, vault, slug)
    lib.vault_commit(vault, slug, f"{slug} catch-up artifacts {_today()}")
    return _session_start_output(_context(folder, root, vault, changed))


def _session_start_output(context: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}})


def mirror(payload: dict) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    raw = tool_input.get("file_path")
    if not raw:
        return ""
    # Cheap string filter before any import or git call: this runs on every edit.
    if not any(seg[1:] in raw for seg in MIRROR_SEGMENTS):
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = Path(_cwd(payload)) / path
    # A symlinked file is skipped, as sweep skips it; resolving first would hide it.
    if path.is_symlink():
        return ""
    path = path.resolve()
    text = path.as_posix()
    # The last match wins, so a worktree path (<repo>/.claude/worktrees/x/.claude/plans/...)
    # maps to the worktree's own mirror dir.
    index, segment = max((text.rfind(seg), seg) for seg in MIRROR_SEGMENTS)
    if index < 0 or not path.is_file():
        return ""
    checkout = Path(text[:index])
    # Only a .claude dir at a checkout root counts, not one nested in a subdirectory.
    if not (checkout / ".git").exists():
        return ""

    lib = _lib()
    try:
        resolved = _resolve(lib, checkout)
    except lib.SlugCollision:
        return ""
    if resolved is None:
        return ""
    root, vault, slug = resolved
    # Claim the folder before writing into it, so a later start never finds it unmarked.
    try:
        lib.ensure_project(root, vault, slug)
    except lib.UnsafePath:
        return ""
    name = segment.split("/")[2]
    remainder = text[index + len(segment):]
    lib.copy_newer(path, vault / "projects" / slug / name / remainder, vault)
    return ""


def end(payload: dict) -> str:
    lib = _lib()
    try:
        resolved = _resolve(lib, _cwd(payload))
    except lib.SlugCollision:
        return ""
    if resolved is None:
        return ""
    root, vault, slug = resolved
    try:
        lib.ensure_project(root, vault, slug)
    except lib.UnsafePath:
        return ""
    lib.sweep(root, vault, slug)
    lib.vault_commit(vault, slug, f"{slug} session artifacts {_today()}")
    return ""


COMMANDS = {"start": start, "mirror": mirror, "end": end}


def main(argv: list[str]) -> int:
    try:
        # Nothing may reach stderr, including warnings from deep inside a call.
        sys.stderr = open(os.devnull, "w")
        if len(argv) != 2 or argv[1] not in COMMANDS:
            return 0
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        # Output is built in full before anything is written, so a failure
        # part-way leaves stdout empty.
        out = COMMANDS[argv[1]](payload)
        if out:
            sys.stdout.write(out)
            sys.stdout.flush()
    except BaseException:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
