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
2. If the changes are trivial or clearly one-sided, summarize them in one line each and ask the user per-file: **adopt live version**, **keep repo version**, or **merge selectively** (walk hunks only when they ask).
3. Apply the chosen result to the repo copy (`src`).
4. Re-link: `ln -sf src dst` so future edits flow through the symlink again. For anything under `~/.claude/`, warn the user that a running Claude Code session may rewrite `settings.json` and detach it again.

Never overwrite the live file with the repo copy without showing the diff and getting confirmation — the live version usually has the newer intent.

## 4. Commit

After merging, if `git status` shows changes, offer to commit using the git-commit skill (one-sentence conventional commit, no attribution).

## Notes

- New candidates: if the user mentions a config that isn't in `install.sh` yet, offer to add it (copy the live file into the repo, add a `link` line, run install).
- JSON files (`settings.json`): after any merge, validate with `jq . file >/dev/null` before committing.
