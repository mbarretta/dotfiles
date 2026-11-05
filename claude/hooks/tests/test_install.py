"""Tests for install.sh's claude-core hook links, against a copied checkout only.

Each test copies install.sh and the claude/ tree into a temporary checkout with
its own ``git init`` and runs that copy against the fake HOME, so neither the
source checkout's install.sh nor its .git/config is ever touched.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import git

SOURCE = Path(__file__).resolve().parents[3]
HOOKS = ("project-vault.py", "project_vault_lib.py")


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    dest = tmp_path / "checkout"
    dest.mkdir()
    shutil.copy2(SOURCE / "install.sh", dest / "install.sh")
    shutil.copytree(
        SOURCE / "claude",
        dest / "claude",
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    git(dest, "init", "-q")
    return dest.resolve()


def install(checkout: Path, home: Path, *extra: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["bash", str(checkout / "install.sh"), "--only", "claude-core", "--home", str(home), *extra],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def retired(checkout: Path) -> Path:
    return checkout / "claude" / "hooks" / "load-lessons.py"


def old_link(home: Path) -> Path:
    return home / ".claude" / "hooks" / "load-lessons.py"


def plant_link(home: Path, target: Path) -> Path:
    link = old_link(home)
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, link)
    return link


def test_retired_file_is_gone_from_source():
    assert not (SOURCE / "claude" / "hooks" / "load-lessons.py").exists()


def test_install_removes_dangling_retired_link_and_links_new_hooks(checkout, fake_home):
    link = plant_link(fake_home, retired(checkout))
    assert not link.exists() and link.is_symlink()  # dangling
    result = install(checkout, fake_home, "--on-collision", "overwrite")
    assert not os.path.lexists(link)
    assert f"removed retired link {link}" in result.stdout
    for name in HOOKS:
        dst = fake_home / ".claude" / "hooks" / name
        assert dst.is_symlink()
        assert os.readlink(dst) == str(checkout / "claude" / "hooks" / name)
        assert dst.resolve() == (checkout / "claude" / "hooks" / name).resolve()


def test_regular_file_is_left_alone(checkout, fake_home):
    path = old_link(fake_home)
    path.parent.mkdir(parents=True)
    path.write_text("mine\n", encoding="utf-8")
    install(checkout, fake_home, "--on-collision", "overwrite")
    assert not path.is_symlink()
    assert path.read_text(encoding="utf-8") == "mine\n"


def test_link_to_another_target_is_left_alone(checkout, fake_home, tmp_path):
    other = tmp_path / "other-checkout" / "claude" / "hooks" / "load-lessons.py"
    link = plant_link(fake_home, other)
    install(checkout, fake_home, "--on-collision", "overwrite")
    assert link.is_symlink()
    assert os.readlink(link) == str(other)


def test_dry_run_reports_without_removing(checkout, fake_home):
    link = plant_link(fake_home, retired(checkout))
    result = install(checkout, fake_home, "--dry-run")
    assert f"would remove retired link {link}" in result.stdout
    assert link.is_symlink()


def test_print_map_lists_new_hooks_and_removes_nothing(checkout, fake_home):
    link = plant_link(fake_home, retired(checkout))
    result = install(checkout, fake_home, "--print-map")
    rows = [line.split("\t") for line in result.stdout.splitlines()]
    assert all(len(row) == 2 for row in rows), result.stdout
    srcs = {Path(src).name for src, _dst in rows}
    for name in HOOKS:
        assert [str(checkout / "claude" / "hooks" / name), str(fake_home / ".claude" / "hooks" / name)] in rows
    assert "load-lessons.py" not in srcs
    assert "load-lessons.py" not in result.stdout
    assert link.is_symlink()
