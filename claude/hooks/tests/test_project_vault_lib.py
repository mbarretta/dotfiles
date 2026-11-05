"""Tests for claude/hooks/project_vault_lib.py, against fixtures only."""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import pytest

import project_vault_lib as lib
from conftest import claim, git, init_repo


# --- module shape -----------------------------------------------------------


def test_imports_only_standard_library():
    tree = ast.parse(Path(lib.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert imported - sys.stdlib_module_names - {"__future__"} == set()


def test_public_functions_exist():
    for name in (
        "vault_path",
        "main_root",
        "wireable",
        "slug_for",
        "mirror_dirs",
        "copy_newer",
        "sweep",
        "ensure_project",
        "redact_url",
        "git_run",
        "symlink_on_path",
        "merge_setting",
        "vault_commit",
    ):
        assert callable(getattr(lib, name)), name


# --- vault_path -------------------------------------------------------------


def test_vault_path_returns_git_vault(vault):
    assert lib.vault_path() == vault


def test_vault_path_none_without_git(fake_home):
    (fake_home / "workspace" / "obsidian-claude-vault").mkdir()
    assert lib.vault_path() is None


def test_vault_path_none_when_missing(fake_home):
    assert lib.vault_path() is None


def test_vault_path_defaults_under_home(fake_home, monkeypatch):
    monkeypatch.delenv("OBSIDIAN_CLAUDE_VAULT_PATH")
    default = init_repo(fake_home / "workspace" / "obsidian-claude-vault")
    assert lib.vault_path() == default


# --- main_root --------------------------------------------------------------


def test_main_root_from_root(repo):
    assert lib.main_root(repo) == repo.resolve()


def test_main_root_from_nested_subdirectory(repo):
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    assert lib.main_root(nested) == repo.resolve()


def test_main_root_from_linked_worktree(repo):
    worktree = repo / ".claude" / "worktrees" / "x"
    git(repo, "worktree", "add", "-q", str(worktree))
    assert lib.main_root(worktree) == repo.resolve()
    sub = worktree / "deep"
    sub.mkdir()
    assert lib.main_root(sub) == repo.resolve()


def test_main_root_none_outside_git(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert lib.main_root(plain) is None


def test_main_root_none_for_bare_repo(tmp_path):
    bare = tmp_path / "bare.git"
    bare.mkdir()
    git(bare, "init", "-q", "--bare")
    assert lib.main_root(bare) is None


# --- wireable ---------------------------------------------------------------


def test_wireable_true_for_root_under_workspace(repo):
    assert lib.wireable(repo) is True


def test_wireable_false_outside_workspace(fake_home, tmp_path):
    assert lib.wireable(init_repo(fake_home / "elsewhere" / "r")) is False
    assert lib.wireable(init_repo(tmp_path / "outside")) is False


def test_wireable_false_for_workspace_itself(fake_home):
    assert lib.wireable(fake_home / "workspace") is False


def test_wireable_false_for_vault(vault):
    assert lib.wireable(vault) is False


def test_wireable_false_when_disabled(repo, monkeypatch):
    monkeypatch.setenv("CLAUDE_VAULT_WIRE", "0")
    assert lib.wireable(repo) is False


def test_wireable_other_wire_values_do_not_disable(repo, monkeypatch):
    monkeypatch.setenv("CLAUDE_VAULT_WIRE", "1")
    assert lib.wireable(repo) is True


# --- slug_for ---------------------------------------------------------------


def _claim(vault: Path, slug: str, repo_path: str) -> None:
    marker = vault / "projects" / slug / "_project.md"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"---\nslug: {slug}\nrepo: {repo_path}\ncreated: 2026-11-05\n---\n", encoding="utf-8")


def test_slug_for_plain(repo, vault):
    assert lib.slug_for(repo, vault) == "name"


def test_slug_for_own_marker_keeps_basename(repo, vault):
    _claim(vault, "name", str(repo))
    assert lib.slug_for(repo, vault) == "name"


def test_slug_for_collision_uses_parent(repo, vault):
    _claim(vault, "name", "/somewhere/else/name")
    assert lib.slug_for(repo, vault) == "owner-name"


def test_slug_for_fallback_owned_by_self(repo, vault):
    _claim(vault, "name", "/somewhere/else/name")
    _claim(vault, "owner-name", str(repo))
    assert lib.slug_for(repo, vault) == "owner-name"


def test_slug_for_double_collision_raises(repo, vault):
    _claim(vault, "name", "/somewhere/else/name")
    _claim(vault, "owner-name", "/another/owner/name")
    with pytest.raises(lib.SlugCollision):
        lib.slug_for(repo, vault)


# --- mirror_dirs ------------------------------------------------------------


def test_mirror_dirs_only_existing_real_dirs(repo, tmp_path):
    claude = repo / ".claude"
    (claude / "plans").mkdir(parents=True)
    (claude / "reviews").write_text("not a dir", encoding="utf-8")
    target = tmp_path / "linked"
    target.mkdir()
    (claude / "mockups").symlink_to(target)
    assert lib.mirror_dirs(repo) == ["plans"]


def test_mirror_dirs_none(repo):
    assert lib.mirror_dirs(repo) == []


# --- copy_newer -------------------------------------------------------------


def _write(path: Path, text: str, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_copy_newer_copies_when_missing_and_preserves_mtime(tmp_path):
    src = _write(tmp_path / "src.md", "a", mtime=1_700_000_000)
    dst = tmp_path / "out" / "deep" / "dst.md"
    assert lib.copy_newer(src, dst, tmp_path) is True
    assert dst.read_text(encoding="utf-8") == "a"
    assert dst.stat().st_mtime == src.stat().st_mtime


def test_copy_newer_copies_when_source_more_than_one_second_newer(tmp_path):
    dst = _write(tmp_path / "dst.md", "old", mtime=1_700_000_000)
    src = _write(tmp_path / "src.md", "new", mtime=1_700_000_002)
    assert lib.copy_newer(src, dst, tmp_path) is True
    assert dst.read_text(encoding="utf-8") == "new"


def test_copy_newer_copies_an_edit_within_one_second(tmp_path):
    dst = _write(tmp_path / "dst.md", "old", mtime=1_700_000_000)
    src = _write(tmp_path / "src.md", "new", mtime=1_700_000_000.5)
    assert lib.copy_newer(src, dst, tmp_path) is True
    assert dst.read_text(encoding="utf-8") == "new"


def test_copy_newer_same_mtime_copies_only_when_size_differs(tmp_path):
    dst = _write(tmp_path / "dst.md", "old", mtime=1_700_000_000)
    same = _write(tmp_path / "same.md", "xyz", mtime=1_700_000_000)
    assert lib.copy_newer(same, dst, tmp_path) is False
    longer = _write(tmp_path / "longer.md", "longer", mtime=1_700_000_000)
    assert lib.copy_newer(longer, dst, tmp_path) is True
    assert dst.read_text(encoding="utf-8") == "longer"


def test_copy_newer_second_call_after_copy_is_a_skip(tmp_path):
    src = _write(tmp_path / "src.md", "a", mtime=1_700_000_000.123456)
    dst = tmp_path / "out" / "dst.md"
    assert lib.copy_newer(src, dst, tmp_path) is True
    assert lib.copy_newer(src, dst, tmp_path) is False


def test_copy_newer_replaces_a_symlinked_dst_without_following_it(tmp_path):
    outside = _write(tmp_path / "outside.md", "outside", mtime=1_600_000_000)
    base = tmp_path / "vault"
    dst = base / "projects" / "s" / "plans" / "a.md"
    dst.parent.mkdir(parents=True)
    dst.symlink_to(outside)
    src = _write(tmp_path / "src.md", "new", mtime=1_700_000_000)
    assert lib.copy_newer(src, dst, base) is False
    assert outside.read_text(encoding="utf-8") == "outside"


def test_copy_newer_refuses_a_symlinked_ancestor_below_base(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    base = tmp_path / "vault"
    (base / "projects").mkdir(parents=True)
    (base / "projects" / "s").symlink_to(elsewhere)
    src = _write(tmp_path / "src.md", "new", mtime=1_700_000_000)
    assert lib.copy_newer(src, base / "projects" / "s" / "plans" / "a.md", base) is False
    assert list(elsewhere.iterdir()) == []


def test_copy_newer_leaves_no_temp_files(tmp_path):
    src = _write(tmp_path / "src.md", "a", mtime=1_700_000_000)
    dst = tmp_path / "out" / "dst.md"
    assert lib.copy_newer(src, dst, tmp_path) is True
    assert [p.name for p in dst.parent.iterdir()] == ["dst.md"]


def test_copy_newer_skips_older_source(tmp_path):
    dst = _write(tmp_path / "dst.md", "newer", mtime=1_700_000_100)
    src = _write(tmp_path / "src.md", "older", mtime=1_700_000_000)
    assert lib.copy_newer(src, dst, tmp_path) is False
    assert dst.read_text(encoding="utf-8") == "newer"


def test_copy_newer_skips_vanished_source(tmp_path):
    dst = tmp_path / "out" / "dst.md"
    assert lib.copy_newer(tmp_path / "gone.md", dst, tmp_path) is False
    assert not dst.exists()


def test_copy_newer_never_deletes(tmp_path):
    src = _write(tmp_path / "src" / "a.md", "a", mtime=1_700_000_100)
    sibling = _write(tmp_path / "dst" / "keep.md", "keep")
    assert lib.copy_newer(src, tmp_path / "dst" / "a.md", tmp_path) is True
    assert src.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"


# --- sweep ------------------------------------------------------------------


def test_sweep_walks_only_existing_mirror_dirs(repo, vault):
    claude = repo / ".claude"
    _write(claude / "plans" / "a.md", "plan")
    _write(claude / "plans" / "sub" / "b.json", "{}")
    _write(claude / "mockups" / "m.html", "<p>")
    _write(claude / "other" / "x.md", "not mirrored")
    _write(claude / "lessons.md", "not mirrored")

    assert lib.sweep(repo, vault, "name") == 3
    project = vault / "projects" / "name"
    assert (project / "plans" / "a.md").read_text(encoding="utf-8") == "plan"
    assert (project / "plans" / "sub" / "b.json").exists()
    assert (project / "mockups" / "m.html").exists()
    assert not (project / "reviews").exists()
    assert not (project / "other").exists()
    assert not (project / "lessons.md").exists()

    assert lib.sweep(repo, vault, "name") == 0


def test_sweep_never_deletes_destination_files(repo, vault):
    _write(repo / ".claude" / "plans" / "a.md", "plan")
    extra = _write(vault / "projects" / "name" / "plans" / "vault-only.md", "keep")
    assert lib.sweep(repo, vault, "name") == 1
    assert extra.read_text(encoding="utf-8") == "keep"
    assert (repo / ".claude" / "plans" / "a.md").exists()


def test_sweep_no_mirror_dirs(repo, vault):
    assert lib.sweep(repo, vault, "name") == 0
    assert not (vault / "projects").exists()


# --- merge_setting ----------------------------------------------------------


def test_merge_setting_creates_missing_file_and_parents(tmp_path):
    path = tmp_path / "repo" / ".claude" / "settings.local.json"
    assert lib.merge_setting(path, "autoMemoryDirectory", "/v/m") is True
    assert path.read_text(encoding="utf-8") == '{\n  "autoMemoryDirectory": "/v/m"\n}\n'


def test_merge_setting_treats_empty_file_as_object(tmp_path):
    path = _write(tmp_path / "s.json", "  \n")
    assert lib.merge_setting(path, "k", "v") is True
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": "v"}


def test_merge_setting_preserves_other_keys(tmp_path):
    original = {
        "permissions": {"allow": ["Bash(ls:*)"], "deny": []},
        "env": {"A": "1"},
        "model": "opus",
        "autoMemoryDirectory": "/old",
    }
    path = _write(tmp_path / "s.json", json.dumps(original, indent=2) + "\n")
    assert lib.merge_setting(path, "autoMemoryDirectory", "/new") is True
    assert json.loads(path.read_text(encoding="utf-8")) == {**original, "autoMemoryDirectory": "/new"}


def test_merge_setting_adds_key_byte_for_byte_otherwise(tmp_path):
    original = {"permissions": {"allow": ["x"]}, "model": "opus"}
    path = _write(tmp_path / "s.json", json.dumps(original, indent=2) + "\n")
    assert lib.merge_setting(path, "k", "v") is True
    assert path.read_text(encoding="utf-8") == json.dumps({**original, "k": "v"}, indent=2) + "\n"


def test_merge_setting_identical_value_does_not_write(tmp_path):
    path = _write(tmp_path / "s.json", '{"k": "v", "other": 1}', mtime=1_700_000_000)
    before = path.stat().st_mtime_ns
    assert lib.merge_setting(path, "k", "v") is False
    assert path.stat().st_mtime_ns == before
    assert path.read_text(encoding="utf-8") == '{"k": "v", "other": 1}'


def test_merge_setting_invalid_json_does_not_write(tmp_path):
    path = _write(tmp_path / "s.json", '{"k": ', mtime=1_700_000_000)
    before = path.stat().st_mtime_ns
    assert lib.merge_setting(path, "k", "v") is False
    assert path.stat().st_mtime_ns == before
    assert path.read_text(encoding="utf-8") == '{"k": '


def test_merge_setting_non_object_json_does_not_write(tmp_path):
    path = _write(tmp_path / "s.json", "[1, 2]")
    assert lib.merge_setting(path, "k", "v") is False
    assert path.read_text(encoding="utf-8") == "[1, 2]"


def test_merge_setting_leaves_no_temp_files(tmp_path):
    path = tmp_path / "cfg" / "s.json"
    lib.merge_setting(path, "k", "v")
    assert [p.name for p in path.parent.iterdir()] == ["s.json"]


# --- vault_commit -----------------------------------------------------------


def _commit_count(vault: Path) -> int:
    return int(git(vault, "rev-list", "--count", "HEAD").strip())


def _head_files(vault: Path) -> list[str]:
    return git(vault, "show", "--name-only", "--format=", "HEAD").split()


def _staged(vault: Path) -> list[str]:
    return git(vault, "diff", "--cached", "--name-only").split()


def test_vault_commit_commits_untracked_project_files(vault):
    _write(vault / "projects" / "s" / "plans" / "a.md", "plan")
    _write(vault / "projects" / "s" / "_project.md", "---\nslug: s\n---\n")
    _write(vault / "projects" / "other" / "x.md", "not mine")
    lib.vault_commit(vault, "s", "s session artifacts")
    assert _commit_count(vault) == 2
    assert sorted(_head_files(vault)) == ["projects/s/_project.md", "projects/s/plans/a.md"]
    assert git(vault, "log", "-1", "--format=%s").strip() == "s session artifacts"
    assert git(vault, "status", "--porcelain", "--", "projects/s") == ""
    assert "projects/other/" in git(vault, "status", "--porcelain")


def test_vault_commit_includes_tracked_modifications(vault):
    plan = _write(vault / "projects" / "s" / "plans" / "a.md", "v1")
    lib.vault_commit(vault, "s", "first")
    plan.write_text("v2", encoding="utf-8")
    lib.vault_commit(vault, "s", "second")
    assert _commit_count(vault) == 3
    assert _head_files(vault) == ["projects/s/plans/a.md"]


def test_vault_commit_keeps_unrelated_staged_changes_out(vault):
    _write(vault / "notes.md", "staged elsewhere")
    git(vault, "add", "--", "notes.md")
    _write(vault / "projects" / "s" / "plans" / "a.md", "plan")
    lib.vault_commit(vault, "s", "msg")
    assert _commit_count(vault) == 2
    assert _head_files(vault) == ["projects/s/plans/a.md"]
    assert _staged(vault) == ["notes.md"]


def test_vault_commit_no_project_changes_with_unrelated_staged(vault):
    _write(vault / "notes.md", "staged elsewhere")
    git(vault, "add", "--", "notes.md")
    lib.vault_commit(vault, "s", "msg")
    assert _commit_count(vault) == 1
    assert _staged(vault) == ["notes.md"]


def test_vault_commit_no_changes_no_commit(vault):
    lib.vault_commit(vault, "s", "msg")
    assert _commit_count(vault) == 1


def test_vault_commit_skips_when_index_locked(vault):
    _write(vault / "projects" / "s" / "a.md", "plan")
    lock = vault / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")
    try:
        lib.vault_commit(vault, "s", "msg")
    finally:
        lock.unlink()
    assert _commit_count(vault) == 1
    assert "?? projects/" in git(vault, "status", "--porcelain")


def test_vault_commit_never_pushes(vault, tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "-q", "--bare")
    git(vault, "remote", "add", "origin", str(remote))
    _write(vault / "projects" / "s" / "a.md", "plan")
    lib.vault_commit(vault, "s", "msg")
    assert _commit_count(vault) == 2
    assert git(remote, "for-each-ref") == ""


def test_vault_commit_never_raises(tmp_path, monkeypatch):
    assert lib.vault_commit(tmp_path / "missing", "s", "msg") is None
    assert lib.vault_commit(init_repo(tmp_path / "v"), "s", "msg") is None
    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))
    _write(tmp_path / "v" / "projects" / "s" / "a.md", "x")
    assert lib.vault_commit(tmp_path / "v", "s", "msg") is None


def test_vault_commit_uses_git_timeout(vault, monkeypatch):
    calls = []
    real_run = lib.subprocess.run

    def spy(*args, **kwargs):
        calls.append(kwargs.get("timeout"))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(lib.subprocess, "run", spy)
    _write(vault / "projects" / "s" / "a.md", "x")
    lib.vault_commit(vault, "s", "msg")
    assert calls and all(t == 10 for t in calls)


# --- review fixes: slug fail-closed ----------------------------------------


def test_slug_for_non_empty_unmarked_folder_is_claimed(repo, vault):
    (vault / "projects" / "name" / "plans").mkdir(parents=True)
    assert lib.slug_for(repo, vault) == "owner-name"


def test_slug_for_empty_folder_is_free(repo, vault):
    (vault / "projects" / "name").mkdir(parents=True)
    assert lib.slug_for(repo, vault) == "name"


def test_slug_for_file_at_slug_path_is_claimed(repo, vault):
    (vault / "projects").mkdir()
    (vault / "projects" / "name").write_text("squat\n", encoding="utf-8")
    assert lib.slug_for(repo, vault) == "owner-name"


def test_slug_for_symlinked_folder_is_claimed(repo, vault, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (vault / "projects").mkdir()
    (vault / "projects" / "name").symlink_to(target)
    assert lib.slug_for(repo, vault) == "owner-name"


# --- review fixes: ensure_project and redaction ----------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://user:tok3n@github.com/o/r.git", "https://github.com/o/r.git"),
        ("https://ghp_abc@github.com/o/r", "https://github.com/o/r"),
        ("ssh://git@host:22/o/r", "ssh://host:22/o/r"),
        ("https://github.com/o/r", "https://github.com/o/r"),
        ("git@github.com:o/r.git", "git@github.com:o/r.git"),
        ("", ""),
    ],
)
def test_redact_url(url, expected):
    assert lib.redact_url(url) == expected


def _front(marker: Path) -> str:
    return marker.read_text(encoding="utf-8").split("---\n")[1]


def test_ensure_project_creates_layout_and_redacted_quoted_marker(repo, vault):
    git(repo, "remote", "add", "origin", "https://me:s3cret@example.invalid/owner/name")
    folder = lib.ensure_project(repo, vault, "name")
    assert folder == vault / "projects" / "name"
    for sub in lib.PROJECT_SUBDIRS:
        assert (folder / sub).is_dir(), sub
    front = _front(folder / "_project.md")
    assert 'slug: "name"\n' in front
    assert f'repo: "{repo}"\n' in front
    assert 'remote: "https://example.invalid/owner/name"\n' in front
    assert "s3cret" not in (folder / "_project.md").read_text(encoding="utf-8")
    # The marker the lib writes is the one slug_for reads back as this repo's claim.
    assert lib.slug_for(repo, vault) == "name"


def test_ensure_project_quoting_keeps_a_hostile_value_on_one_line(repo, vault):
    git(repo, "remote", "add", "origin", "https://example.invalid/x\"\nrepo: /evil")
    marker = lib.ensure_project(repo, vault, "name") / "_project.md"
    lines = _front(marker).splitlines()
    assert [line.split(":", 1)[0] for line in lines] == ["slug", "repo", "remote", "created"]
    assert lib.slug_for(repo, vault) == "name"


def test_ensure_project_never_rewrites_marker(repo, vault):
    folder = claim(vault, "name", repo)
    before = (folder / "_project.md").read_bytes()
    lib.ensure_project(repo, vault, "name")
    assert (folder / "_project.md").read_bytes() == before


def test_ensure_project_refuses_symlinked_folder(repo, vault, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (vault / "projects").mkdir()
    (vault / "projects" / "name").symlink_to(target)
    with pytest.raises(lib.UnsafePath):
        lib.ensure_project(repo, vault, "name")
    assert list(target.iterdir()) == []


# --- review fixes: git environment, pathspec, symlinked settings -----------


def test_git_run_ignores_inherited_git_dir(repo, vault, monkeypatch):
    monkeypatch.setenv("GIT_DIR", str(vault / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(vault))
    result = lib.git_run(repo, "rev-parse", "--show-toplevel")
    assert result is not None and result.stdout.strip() == str(repo)


def test_vault_commit_treats_slug_as_a_literal_path(vault):
    (vault / "projects" / "a" / "plans").mkdir(parents=True)
    (vault / "projects" / "a" / "plans" / "x.md").write_text("x\n", encoding="utf-8")
    (vault / "projects" / "*").mkdir()
    (vault / "projects" / "*" / "y.md").write_text("y\n", encoding="utf-8")
    lib.vault_commit(vault, "*", "star only")
    changed = git(vault, "show", "--name-only", "--format=", "HEAD").split()
    assert changed == ["projects/*/y.md"]
    assert "projects/a/" in git(vault, "status", "--porcelain", "--untracked-files=all")


def test_merge_setting_refuses_symlinked_file(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}\n", encoding="utf-8")
    link = tmp_path / ".claude" / "settings.local.json"
    link.parent.mkdir()
    link.symlink_to(real)
    assert lib.merge_setting(link, "k", "v") is False
    assert real.read_text(encoding="utf-8") == "{}\n" and link.is_symlink()


def test_merge_setting_refuses_symlinked_directory(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / ".claude").symlink_to(real)
    assert lib.merge_setting(tmp_path / ".claude" / "settings.local.json", "k", "v") is False
    assert list(real.iterdir()) == []
