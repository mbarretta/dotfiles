---
name: sync-dotfiles
description: Detect drift between the live (installed) versions of each dotfile and the versions committed in this repo, then interactively merge local changes back. Use when the user asks to sync dotfiles, check for local changes, pull in drift, or asks "did anything change locally?"
---

# Sync Dotfiles

Compare the live copy of every managed file against this repo and merge local changes back in, without going file-by-file manually.

## 1. Build the file map

`install.sh` is the single source of truth. Extract every `link "src" "dst"` pair from it — do NOT hardcode the list here, it will go stale:

```bash
grep -E '^link ' install.sh
```

Expand `$DOTFILES` to this repo's root and `$HOME` to the user's home when resolving paths.

## 2. Classify each destination

For each `src -> dst` pair, determine its state:

- **LINKED**: `dst` is a symlink resolving to `src` (compare with `readlink` against the repo's real path). Live edits flow straight into the repo, so any drift shows up as an unstaged change in `git status` — nothing to merge, skip to step 4.
- **STALE LINK**: `dst` is a symlink but points somewhere else (e.g. another clone of this repo). Diff its target against `src`; treat differences like DETACHED below, and offer to re-point the link here.
- **DETACHED**: `dst` exists but is a regular file (a tool rewrote it in place, breaking the link). This is the main drift case.
- **MISSING**: `dst` doesn't exist. Offer to run `./install.sh` (or just the one `ln -sf`).

## 3. Merge drift for DETACHED / STALE files

For each drifted file:

1. Show `diff -u src dst` (repo vs live).
2. Classify each difference as **shareable** (useful on any machine: aliases, prompt tweaks, general settings) or **machine-specific** (absolute paths under `$HOME`, hostnames, credentials, tool inits for locally-installed tools like pyenv/cargo, work-vs-personal config). When unsure, ask.
3. Shareable changes: ask the user per-file — **adopt live version**, **keep repo version**, or **merge selectively** (walk hunks only when they ask) — and apply the result to the repo copy (`src`).
4. Machine-specific changes: never merge them into the repo. Route them to the file's local companion (see below), creating it if needed.
5. Re-link: `ln -sf src dst` so future edits flow through the symlink again. For anything under `~/.claude/`, warn the user that a running Claude Code session may rewrite `settings.json` and detach it again.

Never overwrite the live file with the repo copy without showing the diff and getting confirmation — the live version usually has the newer intent.

### Grafted files

A DETACHED file may be a **graft**: a pre-existing personal config with a block of repo content pasted in (look for marker comments like "from dotfiles repo", or a contiguous region that matches the repo copy). Don't hunk-merge these. Instead: the matching block is already in the repo (diff it for stragglers), everything else is machine-specific and moves to the local companion, then install the symlink. The grafted file itself should end up deleted (backed up first).

### Local companions (machine-specific overrides)

Machine-specific content lives in an unmanaged, never-committed companion file that the repo copy includes:

| Managed file | Companion | Include mechanism |
|---|---|---|
| `zsh/.zshrc` | `~/.zshrc.local` | `[ -f ~/.zshrc.local ] && source ~/.zshrc.local` (last line of repo `.zshrc`) |
| `ghostty/config.ghostty` | `config.local.ghostty` alongside the live config | `config-file = ?config.local.ghostty` (`?` = optional) |
| `claude/settings.json` | `~/.claude/settings.local.json` | Built into Claude Code — no include line needed |

If a repo file is missing its include line when you need to route content there, add it (and commit that with the sync).

## 4. Commit

After merging, if `git status` shows changes, offer to commit using the git-commit skill (one-sentence conventional commit, no attribution).

## Notes

- New candidates: if the user mentions a config that isn't in `install.sh` yet, offer to add it (copy the live file into the repo, add a `link` line, run install).
- JSON files (`settings.json`): after any merge, validate with `jq . file >/dev/null` before committing.
