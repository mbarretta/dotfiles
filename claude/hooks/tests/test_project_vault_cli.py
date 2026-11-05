"""Tests for claude/hooks/project-vault.py, driven through subprocess.

Every run inherits the autouse fake HOME, fake vault path, and fake git config
from conftest, so the hook only ever sees fixtures under ``tmp_path``.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import git, init_repo

SCRIPT = Path(__file__).resolve().parent.parent / "project-vault.py"
TRUNCATION = "[Truncated at 8000 chars. Read {path} for the rest.]"
TODAY = datetime.date.today().isoformat()


def run_hook(command: str, payload=None, *, raw: str | None = None, env: dict | None = None,
             argv: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run the hook the way Claude Code does: JSON on stdin, one subcommand."""
    stdin = raw if raw is not None else json.dumps(payload if payload is not None else {})
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    args = argv if argv is not None else [command]
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
        check=False,
    )


def context_of(result: subprocess.CompletedProcess) -> str:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    out = json.loads(result.stdout)
    assert list(out) == ["hookSpecificOutput"]
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart"
    return hso["additionalContext"]


def commit_subjects(vault: Path) -> list[str]:
    return git(vault, "log", "--format=%s").splitlines()


def project(vault: Path, slug: str = "name") -> Path:
    return vault / "projects" / slug


# --- ac1: shape and failure handling ---------------------------------------


def test_script_is_executable_with_env_python_shebang():
    assert os.access(SCRIPT, os.X_OK)
    first = SCRIPT.read_text(encoding="utf-8").splitlines()[0]
    assert first == "#!/usr/bin/env python3"


def test_runs_through_its_shebang(repo, vault):
    result = subprocess.run(
        [str(SCRIPT), "start"],
        input=json.dumps({"cwd": str(repo)}),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert str(project(vault)) in context_of(result)


def test_imports_only_standard_library_and_the_lib():
    import ast

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert "project_vault_lib" in imported
    assert imported - sys.stdlib_module_names - {"__future__", "project_vault_lib"} == set()


def test_imports_the_lib_from_its_own_directory(tmp_path, repo, vault):
    # A copy of the script next to a stub lib must load the stub, not any other copy.
    alt = tmp_path / "alt"
    alt.mkdir()
    (alt / "project-vault.py").write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    (alt / "project_vault_lib.py").write_text(
        "import sys\n"
        "def main_root(cwd):\n"
        "    sys.stdout.write('STUB-LIB-LOADED')\n"
        "    return None\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(alt / "project-vault.py"), "start"],
        input=json.dumps({"cwd": str(repo)}),
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=60,
        check=False,
    )
    assert result.returncode == 0
    assert "STUB-LIB-LOADED" in result.stdout


@pytest.mark.parametrize("command", ["start", "mirror", "end"])
@pytest.mark.parametrize("raw", ["", "   \n", "{not json", "[1, 2]", "null", '"text"'])
def test_bad_stdin_is_silent(command, raw, repo, vault):
    result = run_hook(command, raw=raw)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (vault / "projects").exists()


@pytest.mark.parametrize(
    "command,payload",
    [
        ("start", {"cwd": 123}),
        ("end", {"cwd": ["not", "a", "path"]}),
        ("mirror", {"tool_input": {"file_path": 5}, "cwd": 7}),
        ("mirror", {"tool_input": "not-a-dict"}),
    ],
)
def test_exceptions_are_swallowed(command, payload, vault):
    result = run_hook(command, payload)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize("argv", [[], ["bogus"], ["start", "extra"], ["START"]])
def test_only_the_three_subcommands_are_accepted(argv, repo, vault):
    result = run_hook("", {"cwd": str(repo)}, argv=argv)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (vault / "projects").exists()


def test_exception_inside_start_after_resolution_is_silent(repo, vault):
    # projects/ as a regular file makes the folder creation raise mid-run.
    (vault / "projects").write_text("blocker\n", encoding="utf-8")
    result = run_hook("start", {"cwd": str(repo)})
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


# --- ac2: start creates the layout, wires settings, commits ----------------


def test_start_creates_layout_and_project_note(repo, vault):
    git(repo, "remote", "add", "origin", "https://example.invalid/owner/name")
    ctx = context_of(run_hook("start", {"cwd": str(repo)}))
    base = project(vault)
    for sub in ("plans", "research", "reviews", "mockups", "memory"):
        assert (base / sub).is_dir(), sub
    assert (vault / "projects" / "_global" / "memory").is_dir()
    note = (base / "_project.md").read_text(encoding="utf-8")
    assert note.startswith("---\n")
    front = note.split("---\n")[1]
    assert f"slug: name\n" in front
    assert f"repo: {repo}\n" in front
    assert "remote: https://example.invalid/owner/name\n" in front
    assert f"created: {TODAY}\n" in front
    assert str(base) in ctx


def test_project_note_is_written_once(repo, vault):
    run_hook("start", {"cwd": str(repo)})
    note = project(vault) / "_project.md"
    note.write_text("---\nslug: name\nrepo: " + str(repo) + "\n---\nhand edited\n", encoding="utf-8")
    before = note.stat().st_mtime_ns
    run_hook("start", {"cwd": str(repo)})
    assert note.read_text(encoding="utf-8").endswith("hand edited\n")
    assert note.stat().st_mtime_ns == before


def test_project_note_without_remote_has_empty_remote(repo, vault):
    run_hook("start", {"cwd": str(repo)})
    front = (project(vault) / "_project.md").read_text(encoding="utf-8").split("---\n")[1]
    assert "remote: \n" in front


def test_start_merges_auto_memory_directory(repo, vault):
    settings = repo / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"env": {"X": "1"}}), encoding="utf-8")
    run_hook("start", {"cwd": str(repo)})
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data == {"env": {"X": "1"}, "autoMemoryDirectory": f"{vault}/projects/name/memory"}


def test_start_in_worktree_wires_both_settings_files(repo, vault):
    wt = repo / ".claude" / "worktrees" / "x"
    git(repo, "worktree", "add", "-q", "-b", "wt", str(wt))
    ctx = context_of(run_hook("start", {"cwd": str(wt)}, env={"CLAUDE_PROJECT_DIR": str(wt)}))
    want = f"{vault}/projects/name/memory"
    for root in (repo, wt):
        data = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
        assert data["autoMemoryDirectory"] == want, root
    # The slug comes from the main root, not the worktree's directory name.
    assert project(vault).is_dir()
    assert not (vault / "projects" / "x").exists()
    assert str(project(vault)) in ctx


def test_start_runs_sweep_and_catch_up_commit(repo, vault):
    plans = repo / ".claude" / "plans"
    plans.mkdir(parents=True)
    (plans / "feat.json").write_text('{"status": "pending"}\n', encoding="utf-8")
    (repo / ".claude" / "reviews").mkdir()
    (repo / ".claude" / "reviews" / "r1.md").write_text("review\n", encoding="utf-8")
    run_hook("start", {"cwd": str(repo)})
    assert (project(vault) / "plans" / "feat.json").read_text(encoding="utf-8") == '{"status": "pending"}\n'
    assert (project(vault) / "reviews" / "r1.md").is_file()
    assert commit_subjects(vault)[0] == f"name catch-up artifacts {TODAY}"
    changed = git(vault, "show", "--name-only", "--format=", "HEAD").split()
    assert "projects/name/plans/feat.json" in changed
    assert "projects/name/_project.md" in changed
    assert all(p.startswith("projects/name/") for p in changed)


def test_start_twice_makes_no_second_commit(repo, vault):
    run_hook("start", {"cwd": str(repo)})
    count = len(commit_subjects(vault))
    run_hook("start", {"cwd": str(repo)})
    assert len(commit_subjects(vault)) == count


def test_start_slug_collision_warns_and_does_nothing_else(repo, vault):
    for slug in ("name", "owner-name"):
        (vault / "projects" / slug).mkdir(parents=True)
        (vault / "projects" / slug / "_project.md").write_text(
            f"---\nslug: {slug}\nrepo: /elsewhere/{slug}\n---\n", encoding="utf-8"
        )
    ctx = context_of(run_hook("start", {"cwd": str(repo)}))
    assert len(ctx.splitlines()) == 1
    assert "collision" in ctx
    assert not (repo / ".claude" / "settings.local.json").exists()
    assert not (vault / "projects" / "_global").exists()


# --- ac3: the injected context ---------------------------------------------


def test_context_names_folder_and_subfolder_rules(repo, vault):
    ctx = context_of(run_hook("start", {"cwd": str(repo)}))
    assert str(project(vault)) in ctx
    for sub in ("research/", "reviews/", "mockups/", ".claude/plans"):
        assert sub in ctx


def test_context_notes_auto_memory_change_only_when_written(repo, vault):
    first = context_of(run_hook("start", {"cwd": str(repo)}))
    assert "takes effect next session" in first
    second = context_of(run_hook("start", {"cwd": str(repo)}))
    assert "takes effect next session" not in second


def test_context_uses_vault_lessons_first(repo, vault):
    project(vault).mkdir(parents=True)
    (project(vault) / "lessons.md").write_text("- vault lesson\n", encoding="utf-8")
    (repo / ".claude").mkdir()
    (repo / ".claude" / "lessons.md").write_text("- repo lesson\n", encoding="utf-8")
    ctx = context_of(run_hook("start", {"cwd": str(repo)}))
    assert "- vault lesson" in ctx
    assert "- repo lesson" not in ctx
    assert "unmigrated" not in ctx


def test_context_falls_back_to_repo_lessons_with_note(repo, vault):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "lessons.md").write_text("- repo lesson\n", encoding="utf-8")
    ctx = context_of(run_hook("start", {"cwd": str(repo)}))
    assert "- repo lesson" in ctx
    assert "unmigrated; run vault-migrate" in ctx


def test_context_includes_global_memory_capped(repo, vault):
    mem = vault / "projects" / "_global" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("G" * 3000, encoding="utf-8")
    ctx = context_of(run_hook("start", {"cwd": str(repo)}))
    assert "G" * 2000 in ctx
    assert "G" * 2001 not in ctx


def test_context_caps_lessons_and_total(repo, vault):
    project(vault).mkdir(parents=True)
    lessons = project(vault) / "lessons.md"
    lessons.write_text("L" * 20000, encoding="utf-8")
    mem = vault / "projects" / "_global" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("G" * 5000, encoding="utf-8")
    ctx = context_of(run_hook("start", {"cwd": str(repo)}))
    assert len(ctx) <= 9000
    assert "L" * 8000 in ctx
    assert "L" * 8001 not in ctx
    assert TRUNCATION.format(path=lessons) in ctx
    # Order: header, then lessons, then memory.
    assert ctx.index(str(project(vault))) < ctx.index("L" * 100)


# --- ac4: non-wireable cwd -------------------------------------------------


def _assert_untouched(result, vault: Path, *settings_roots: Path):
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (vault / "projects").exists()
    for root in settings_roots:
        assert not (root / ".claude" / "settings.local.json").exists(), root


def test_start_outside_workspace_is_silent(tmp_path, vault):
    outside = init_repo(tmp_path / "outside" / "repo")
    _assert_untouched(run_hook("start", {"cwd": str(outside)}), vault, outside)


def test_start_in_vault_is_silent(vault):
    _assert_untouched(run_hook("start", {"cwd": str(vault)}), vault, vault)


def test_start_in_non_git_dir_is_silent(fake_home, vault):
    plain = fake_home / "workspace" / "plain"
    plain.mkdir()
    _assert_untouched(run_hook("start", {"cwd": str(plain)}), vault, plain)


def test_start_with_wire_disabled_is_silent(repo, vault):
    result = run_hook("start", {"cwd": str(repo)}, env={"CLAUDE_VAULT_WIRE": "0"})
    _assert_untouched(result, vault, repo)


def test_start_without_vault_is_silent(repo, fake_home):
    result = run_hook("start", {"cwd": str(repo)})
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (repo / ".claude" / "settings.local.json").exists()


# --- ac5: mirror -----------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("sub", ["plans", "mockups", "reviews"])
def test_mirror_copies_matching_path(sub, repo, vault):
    src = _write(repo / ".claude" / sub / "deep" / "doc.md", f"{sub} body\n")
    result = run_hook("mirror", {"tool_name": "Write", "tool_input": {"file_path": str(src)}, "cwd": str(repo)})
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert (project(vault) / sub / "deep" / "doc.md").read_text(encoding="utf-8") == f"{sub} body\n"


def test_mirror_resolves_worktree_to_main_root(repo, vault):
    wt = repo / ".claude" / "worktrees" / "x"
    git(repo, "worktree", "add", "-q", "-b", "wt", str(wt))
    src = _write(wt / ".claude" / "plans" / "wt-plan.json", "{}\n")
    result = run_hook("mirror", {"tool_name": "Edit", "tool_input": {"file_path": str(src)}, "cwd": str(wt)})
    assert (result.returncode, result.stdout) == (0, "")
    assert (project(vault) / "plans" / "wt-plan.json").read_text(encoding="utf-8") == "{}\n"
    assert not (vault / "projects" / "x").exists()


def test_mirror_skips_symlinked_file(repo, vault):
    target = _write(repo / ".claude" / "plans" / "real.md", "real\n")
    link = repo / ".claude" / "plans" / "alias.md"
    link.symlink_to(target)
    run_hook("mirror", {"tool_input": {"file_path": str(link)}, "cwd": str(repo)})
    assert not (vault / "projects").exists()


def test_mirror_relative_path_resolves_against_cwd(repo, vault):
    _write(repo / ".claude" / "plans" / "rel.md", "rel\n")
    run_hook("mirror", {"tool_input": {"file_path": ".claude/plans/rel.md"}, "cwd": str(repo)})
    assert (project(vault) / "plans" / "rel.md").is_file()


@pytest.mark.parametrize(
    "relpath",
    ["src/app.py", ".claude/settings.json", ".claude/worktrees/x/README.md", "docs/plans/x.md", ".claude/plansx/a.md"],
)
def test_mirror_ignores_other_paths(relpath, repo, vault):
    src = _write(repo / relpath, "x\n")
    result = run_hook("mirror", {"tool_input": {"file_path": str(src)}, "cwd": str(repo)})
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (vault / "projects").exists()


def test_mirror_ignores_unwired_repo(tmp_path, vault):
    outside = init_repo(tmp_path / "outside" / "repo")
    src = _write(outside / ".claude" / "plans" / "p.md", "p\n")
    result = run_hook("mirror", {"tool_input": {"file_path": str(src)}, "cwd": str(outside)})
    assert (result.returncode, result.stdout) == (0, "")
    assert not (vault / "projects").exists()


@pytest.mark.parametrize("payload", [{}, {"tool_name": "Write"}, {"tool_input": {}}, {"tool_input": {"file_path": ""}}])
def test_mirror_without_file_path_is_silent(payload, vault):
    result = run_hook("mirror", payload)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_mirror_miss_path_is_fast(repo, vault):
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(repo / "src" / "app.py")}, "cwd": str(repo)}
    # Best of three, so one scheduler hiccup on a loaded machine is not a failure;
    # every run is still the full interpreter start plus the miss path.
    timings = []
    for _ in range(3):
        start = time.perf_counter()
        result = run_hook("mirror", payload)
        timings.append(time.perf_counter() - start)
        assert (result.returncode, result.stdout) == (0, "")
    assert min(timings) < 0.1, timings


# --- ac6: end --------------------------------------------------------------


def test_end_sweeps_and_commits_once(repo, vault):
    _write(repo / ".claude" / "plans" / "p.json", "{}\n")
    first = run_hook("end", {"cwd": str(repo), "session_id": "s1"})
    assert (first.returncode, first.stdout, first.stderr) == (0, "", "")
    assert (project(vault) / "plans" / "p.json").is_file()
    subjects = commit_subjects(vault)
    assert subjects[0] == f"name session artifacts {TODAY}"
    changed = git(vault, "show", "--name-only", "--format=", "HEAD").split()
    assert changed == ["projects/name/plans/p.json"]
    second = run_hook("end", {"cwd": str(repo), "session_id": "s1"})
    assert (second.returncode, second.stdout) == (0, "")
    assert commit_subjects(vault) == subjects


def test_end_in_unwired_cwd_does_nothing(tmp_path, vault):
    outside = init_repo(tmp_path / "outside" / "repo")
    _write(outside / ".claude" / "plans" / "p.json", "{}\n")
    before = commit_subjects(vault)
    result = run_hook("end", {"cwd": str(outside)})
    assert (result.returncode, result.stdout) == (0, "")
    assert commit_subjects(vault) == before
    assert not (vault / "projects").exists()
