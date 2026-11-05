"""Tests for claude/hooks/vault-migrate.py, against fixtures only.

Every test runs under a fake HOME whose path contains a dot (the real one does,
and the memory-dir encoding turns dots into hyphens), with a fake git vault and
fixture repos under ``<HOME>/workspace/github/<owner>/``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from conftest import HOOKS_DIR, git, init_repo

SCRIPT = HOOKS_DIR / "vault-migrate.py"
_spec = importlib.util.spec_from_file_location("vault_migrate", SCRIPT)
vm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = vm  # dataclasses look the module up while exec runs
_spec.loader.exec_module(vm)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A resolved fake HOME whose name contains a dot, with the vault env pointing into it."""
    home = tmp_path.resolve() / "first.last"
    (home / "workspace" / "github").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OBSIDIAN_CLAUDE_VAULT_PATH", str(home / "workspace" / "obsidian-claude-vault"))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.resolve()))
    return home


@pytest.fixture
def vault(home: Path) -> Path:
    return init_repo(home / "workspace" / "obsidian-claude-vault")


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def mem_dir(root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / vm.encode(root) / "memory"


@pytest.fixture
def alpha(home: Path) -> Path:
    """Repo with tracked .claude/plans, a tracked lessons.md, and a populated memory dir."""
    root = init_repo(home / "workspace" / "github" / "owner" / "alpha-repo")
    write(root / ".claude" / "plans" / "design.md", "# design\n")
    write(root / ".claude" / "plans" / "feat.json", json.dumps({"status": "complete"}))
    write(root / ".claude" / "reviews" / "r1.md", "review\n")
    write(root / ".claude" / "lessons.md", "- a lesson\n")
    git(root, "add", "--", ".claude")
    git(root, "commit", "-q", "-m", "add claude artifacts")
    mem = mem_dir(root)
    write(mem / "MEMORY.md", f"- [topic](topic_file.md) see {home}/notes\n")
    write(
        mem / "topic_file.md",
        "---\nname: topic-file\ndescription: a topic\nmetadata:\n  type: project\n---\n\n"
        f"Body with {home}/workspace/x and [[other-topic]].\n",
    )
    return root


@pytest.fixture
def beta(home: Path) -> Path:
    """Repo with an in_progress plan JSON (untracked) and an untracked lessons.md."""
    root = init_repo(home / "workspace" / "github" / "owner" / "beta")
    write(root / ".claude" / "plans" / "wip.json", json.dumps({"status": "in_progress"}, indent=2))
    write(root / ".claude" / "lessons.md", "- beta lesson\n")
    return root


def run(*args: str) -> int:
    return vm.main(list(args))


def rows(out: str) -> dict[str, dict[str, str]]:
    """Parse the repo table (first block of output) into {slug: {column: cell}}."""
    block = out.split("\n\n")[0].splitlines()
    header = block[0].split()
    starts = [block[0].index(h) for h in header]
    parsed = {}
    for line in block[1:]:
        cells = [
            line[s:(starts[i + 1] if i + 1 < len(starts) else None)].strip()
            for i, s in enumerate(starts)
        ]
        parsed[cells[0]] = dict(zip(header, cells))
    return parsed


def head(path: Path) -> str:
    return git(path, "rev-parse", "HEAD").strip()


# --- CLI shape --------------------------------------------------------------


def test_apply_without_only_exits_2(vault, alpha, capsys):
    assert run("--apply") == 2
    assert "--only" in capsys.readouterr().err
    assert not (vault / "projects").exists()


def test_no_apply_all_flag():
    for flag in ("--all", "--yes"):
        with pytest.raises(SystemExit):
            run("--apply", flag)


def test_script_runs_as_subprocess(home, vault, alpha):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0].split()[:8] == [
        "slug", "plans", "mockups", "reviews", "lessons", "tracked", "memory", "blockers",
    ]
    assert "alpha-repo" in result.stdout


def test_imports_project_vault_lib():
    assert vm.lib.__name__ == "project_vault_lib"


# --- dry run ----------------------------------------------------------------


def test_dry_run_columns(home, vault, alpha, beta, capsys):
    primary = init_repo(home / "workspace" / "obsidian-primary-vault")
    (home / "workspace" / "github" / "owner" / "not-a-repo").mkdir()
    before = head(vault)
    assert run() == 0
    out = capsys.readouterr().out
    table = rows(out)
    assert set(table) == {"alpha-repo", "beta", primary.name}
    a = table["alpha-repo"]
    assert (a["plans"], a["mockups"], a["reviews"]) == ("2", "0", "1")
    assert (a["lessons"], a["tracked"], a["memory"], a["blockers"]) == ("yes", "yes", "2", "-")
    b = table["beta"]
    assert (b["plans"], b["lessons"], b["tracked"], b["memory"]) == ("1", "yes", "no", "-")
    assert "in_progress: wip.json" in b["blockers"]
    # Dry run mutates nothing.
    assert head(vault) == before and not (vault / "projects").exists()
    assert (alpha / ".claude" / "lessons.md").exists()


def test_memory_dirs_with_dot_home_and_hyphen_name_resolve(home, vault, alpha, capsys):
    assert "." in str(home) and "-" in alpha.name
    orphan = write(home / ".claude" / "projects" / "-tmp-gone-repo" / "memory" / "MEMORY.md", "x\n")
    write(home / ".claude" / "plans" / "_index.json", "{}")
    assert run() == 0
    out = capsys.readouterr().out
    extra = out.split("\n\n")[1]
    assert str(orphan.parent) in extra and "unresolved; review for archive" in extra
    assert str(mem_dir(alpha)) not in extra
    assert re.search(re.escape(str(home / ".claude" / "plans")) + r"\s+leave$", extra, re.M)
    assert out.count("unresolved") == 1


def test_encoding_matches_spec():
    assert vm.encode(Path("/Users/a.b/workspace/x-y")) == "-Users-a-b-workspace-x-y"


def test_ambiguous_memory_dir_listed_and_untouched(home, vault, capsys):
    dotted = init_repo(home / "workspace" / "github" / "owner" / "x.y")
    init_repo(home / "workspace" / "github" / "owner" / "x-y")
    mem = write(mem_dir(dotted) / "MEMORY.md", "shared\n")
    assert run() == 0
    out = capsys.readouterr().out
    assert rows(out)["x.y"]["memory"] == "ambiguous"
    assert "ambiguous:" in out.split("\n\n")[1]
    assert run("--apply", "--only", "x.y") == 0
    assert mem.read_text() == "shared\n" and not (mem.parent / "MOVED.md").exists()


def test_vault_is_never_a_candidate(home, monkeypatch, capsys):
    inside = init_repo(home / "workspace" / "github" / "owner" / "the-vault")
    monkeypatch.setenv("OBSIDIAN_CLAUDE_VAULT_PATH", str(inside))
    init_repo(home / "workspace" / "github" / "owner" / "other")
    assert run() == 0
    assert set(rows(capsys.readouterr().out)) == {"other"}


def test_clickhouse_clones_excluded(home, vault, alpha, capsys):
    team = init_repo(home / "workspace" / "github" / "clickhouse" / "team")
    write(team / ".claude" / "lessons.md", "team lesson\n")
    write(team / ".claude" / "plans" / "p.md", "plan\n")
    team_mem = write(mem_dir(team) / "MEMORY.md", "team memory\n")
    before_vault, before_team = head(vault), head(team)
    assert run() == 0
    out = capsys.readouterr().out
    assert "team" not in rows(out)
    assert str(team_mem.parent) not in out  # matched by forward encoding, so not unresolved
    assert run("--apply", "--only", "team") == 2
    assert head(vault) == before_vault and not (vault / "projects").exists()
    assert head(team) == before_team
    assert (team / ".claude" / "lessons.md").read_text() == "team lesson\n"
    assert sorted(p.name for p in team_mem.parent.iterdir()) == ["MEMORY.md"]
    assert not (team / ".claude" / "settings.local.json").exists()


# --- blockers ---------------------------------------------------------------


def test_in_progress_blocks_apply_unless_allowed(home, vault, beta, capsys):
    assert run("--apply", "--only", "beta") == 2
    assert "in_progress" in capsys.readouterr().err
    assert not (vault / "projects").exists()
    assert run("--apply", "--only", "beta", "--allow-in-progress") == 0
    assert (vault / "projects" / "beta" / "plans" / "wip.json").is_file()
    # Untracked lessons: moved and deleted without a repo commit.
    assert (vault / "projects" / "beta" / "lessons.md").read_text() == "- beta lesson\n"
    assert not (beta / ".claude" / "lessons.md").exists()
    assert git(beta, "rev-list", "--count", "HEAD").strip() == "1"


def test_slug_collision_blocks(home, vault, alpha, capsys):
    for slug in ("alpha-repo", "owner-alpha-repo"):
        write(vault / "projects" / slug / "_project.md", "---\nrepo: /elsewhere/x\n---\n")
    assert run() == 0
    assert "slug collision" in rows(capsys.readouterr().out)["alpha-repo"]["blockers"]
    assert run("--apply", "--only", "alpha-repo", "--allow-in-progress") == 2
    assert (alpha / ".claude" / "lessons.md").exists()


def test_uncommitted_tracked_claude_changes_block(home, vault, alpha, capsys):
    write(alpha / ".claude" / "plans" / "design.md", "# edited\n")
    write(alpha / ".claude" / "plans" / "untracked.md", "new\n")
    assert run() == 0
    assert rows(capsys.readouterr().out)["alpha-repo"]["blockers"] == "uncommitted .claude changes"
    assert run("--apply", "--only", "alpha-repo", "--allow-in-progress") == 2
    assert not (vault / "projects").exists()


def test_untracked_claude_files_do_not_block(home, vault, alpha, capsys):
    write(alpha / ".claude" / "plans" / "untracked.md", "new\n")
    assert run() == 0
    assert rows(capsys.readouterr().out)["alpha-repo"]["blockers"] == "-"


def _session(home: Path, name: str, payload) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    write(home / ".claude" / "sessions" / name, text)


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


@pytest.mark.parametrize("where", ["root", "subdir", "worktree"])
def test_live_session_blocks_and_is_not_bypassed(home, vault, alpha, capsys, where):
    if where == "worktree":
        cwd = alpha / ".claude" / "worktrees" / "wt"
        git(alpha, "worktree", "add", "-q", str(cwd))
        cwd = cwd / "sub"
    else:
        cwd = alpha if where == "root" else alpha / "src"
    _session(home, f"{os.getpid()}.json", {"pid": os.getpid(), "cwd": str(cwd), "status": "busy"})
    assert run() == 0
    row = rows(capsys.readouterr().out)["alpha-repo"]
    assert f"live session pid {os.getpid()}" in row["blockers"]
    assert vm.SESSIONS_UNKNOWN not in row["notes"]
    assert run("--apply", "--only", "alpha-repo", "--allow-in-progress") == 2
    assert not (vault / "projects").exists()
    assert (alpha / ".claude" / "lessons.md").exists()


def test_live_session_elsewhere_and_stale_session_ignored(home, vault, alpha, capsys):
    _session(home, "1.json", {"pid": os.getpid(), "cwd": str(home), "status": "idle"})
    dead = _dead_pid()
    _session(home, f"{dead}.json", {"pid": dead, "cwd": str(alpha), "status": "busy"})
    assert run() == 0
    row = rows(capsys.readouterr().out)["alpha-repo"]
    assert row["blockers"] == "-" and row["notes"] == "-"


def test_sessions_absent_is_unknown_not_blocker(home, vault, alpha, capsys):
    assert run() == 0
    row = rows(capsys.readouterr().out)["alpha-repo"]
    assert row["notes"] == vm.SESSIONS_UNKNOWN and row["blockers"] == "-"


def test_sessions_unparseable_is_unknown_not_blocker(home, vault, alpha, capsys):
    _session(home, "1.json", "{not json")
    _session(home, "2.json", json.dumps(["a list"]))
    write(home / ".claude" / "sessions" / "3.abc.key", "{}")
    assert run() == 0
    row = rows(capsys.readouterr().out)["alpha-repo"]
    assert row["notes"] == vm.SESSIONS_UNKNOWN and row["blockers"] == "-"


# --- apply ------------------------------------------------------------------


def test_full_apply_then_idempotent(home, vault, alpha, capsys):
    # Pre-existing vault-only file must survive; an unrelated staged change must stay staged.
    write(vault / "projects" / "alpha-repo" / "plans" / "archived.md", "old plan\n")
    write(alpha / "unrelated.txt", "staged\n")
    git(alpha, "add", "--", "unrelated.txt")
    repo_head, vault_head = head(alpha), head(vault)

    assert run("--apply", "--only", "alpha-repo") == 0
    project = vault / "projects" / "alpha-repo"

    # projects/<slug> and _project.md
    for sub in vm.PROJECT_SUBDIRS:
        assert (project / sub).is_dir()
    marker = (project / "_project.md").read_text()
    assert "slug: alpha-repo\n" in marker and f"repo: {alpha}\n" in marker and "created: " in marker

    # mirror
    assert (project / "plans" / "design.md").read_text() == "# design\n"
    assert (project / "plans" / "feat.json").is_file()
    assert (project / "reviews" / "r1.md").read_text() == "review\n"
    assert (project / "plans" / "archived.md").read_text() == "old plan\n"
    assert (alpha / ".claude" / "plans" / "design.md").exists()

    # lessons: moved, repo commit holds only its deletion, unrelated file still staged
    assert (project / "lessons.md").read_text() == "- a lesson\n"
    assert not (alpha / ".claude" / "lessons.md").exists()
    assert git(alpha, "rev-parse", "HEAD~1").strip() == repo_head
    assert git(alpha, "log", "-1", "--format=%s").strip() == vm.LESSONS_COMMIT_MSG
    assert git(alpha, "show", "--name-only", "--format=", "HEAD").split() == [".claude/lessons.md"]
    stat = git(alpha, "show", "--stat", "--format=", "HEAD")
    assert ".claude/lessons.md" in stat and "unrelated.txt" not in stat
    assert git(alpha, "diff", "--cached", "--name-only").split() == ["unrelated.txt"]

    # memory: copied with aliases and ~/ rewrite, backed up, emptied, MOVED.md
    topic = (project / "memory" / "topic_file.md").read_text()
    assert topic.startswith("---\nname: topic-file\naliases: [topic-file]\ndescription:")
    assert "Body with ~/workspace/x" in topic and str(home) not in topic
    assert (project / "memory" / "MEMORY.md").read_text() == "- [topic](topic_file.md) see ~/notes\n"
    src = mem_dir(alpha)
    assert src.is_dir() and [p.name for p in src.iterdir()] == ["MOVED.md"]
    assert (src / "MOVED.md").read_text().strip() == str(project / "memory")
    backups = list((home / ".claude" / "backups").glob("memory-alpha-repo-*.tar.gz"))
    assert [b.name for b in backups] == [f"memory-alpha-repo-{vm._today()}.tar.gz"]
    with tarfile.open(backups[0]) as tar:
        names = sorted(m.name for m in tar.getmembers() if m.isfile())
    assert names == ["memory/MEMORY.md", "memory/topic_file.md"]

    # settings.local.json
    settings = json.loads((alpha / ".claude" / "settings.local.json").read_text())
    assert settings["autoMemoryDirectory"] == str(project / "memory")

    # one vault commit, scoped to projects/<slug>
    assert git(vault, "rev-parse", "HEAD~1").strip() == vault_head
    assert git(vault, "log", "-1", "--format=%s").strip() == "alpha-repo artifacts migrated"
    changed = git(vault, "show", "--name-only", "--format=", "HEAD").split()
    assert changed and all(p.startswith("projects/alpha-repo/") for p in changed)
    assert git(vault, "status", "--porcelain").strip() == ""

    # second apply is a no-op
    capsys.readouterr()
    repo_head2, vault_head2 = head(alpha), head(vault)
    assert run("--apply", "--only", "alpha-repo") == 0
    assert head(alpha) == repo_head2 and head(vault) == vault_head2
    assert len(list((home / ".claude" / "backups").iterdir())) == 1
    assert [p.name for p in src.iterdir()] == ["MOVED.md"]
    capsys.readouterr()
    assert run() == 0
    assert rows(capsys.readouterr().out)["alpha-repo"]["memory"] == "moved"


def test_mirror_verify_failure_exits_1(home, vault, alpha, capsys):
    dst = write(vault / "projects" / "alpha-repo" / "plans" / "design.md", "# vault edit\n")
    future = dst.stat().st_mtime + 100
    os.utime(dst, (future, future))
    vault_only = write(vault / "projects" / "alpha-repo" / "plans" / "keep.md", "keep\n")
    assert run("--apply", "--only", "alpha-repo") == 1
    assert "design.md" in capsys.readouterr().err
    assert dst.read_text() == "# vault edit\n" and vault_only.read_text() == "keep\n"
    # Stopped before lessons and memory were touched.
    assert (alpha / ".claude" / "lessons.md").exists()
    assert not (mem_dir(alpha) / "MOVED.md").exists()


def test_memory_conflict_in_vault_exits_1_before_emptying_source(home, vault, alpha):
    write(vault / "projects" / "alpha-repo" / "memory" / "MEMORY.md", "written by a live session\n")
    assert run("--apply", "--only", "alpha-repo") == 1
    assert sorted(p.name for p in mem_dir(alpha).iterdir()) == ["MEMORY.md", "topic_file.md"]
    assert not (home / ".claude" / "backups").exists()


def test_apply_unwireable_root_exits_2(home, vault, alpha, monkeypatch):
    monkeypatch.setenv("CLAUDE_VAULT_WIRE", "0")
    assert run("--apply", "--only", "alpha-repo") == 2
    assert not (vault / "projects").exists()
    assert (alpha / ".claude" / "lessons.md").exists()


def test_unparseable_settings_warns(home, vault, alpha, capsys):
    write(alpha / ".claude" / "settings.local.json", "{broken")
    assert run("--apply", "--only", "alpha-repo") == 0
    assert "could not set autoMemoryDirectory" in capsys.readouterr().err
    assert (alpha / ".claude" / "settings.local.json").read_text() == "{broken"


def test_apply_unknown_slug_exits_2(home, vault, alpha):
    assert run("--apply", "--only", "nope") == 2


def test_add_alias_leaves_existing_aliases_and_nested_name():
    assert vm.add_alias("---\nname: a\naliases: [b]\n---\n") == "---\nname: a\naliases: [b]\n---\n"
    nested = "---\nmetadata:\n  name: x\n---\n"
    assert vm.add_alias(nested) == nested
    assert vm.add_alias("no frontmatter\nname: x\n") == "no frontmatter\nname: x\n"
    assert vm.add_alias('---\nname: "a b"\n---\n') == '---\nname: "a b"\naliases: ["a b"]\n---\n'
