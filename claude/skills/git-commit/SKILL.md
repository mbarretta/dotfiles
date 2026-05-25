---
name: git-commit
description: Use this skill whenever committing code to git — whether completing a task, making a checkpoint commit, or finishing a full workflow. Handles staging, writing the commit message (conventional commits, single line, no co-author info), and pushing only when a task is fully complete. Use this any time you're about to run git add, git commit, or git push, or when a task has been implemented and is ready to be committed.
---

# Git Commit Workflow

## Staging

Stage all files that were changed as part of the current task.

**If there are other modified or untracked files that are NOT part of the task**, stop and ask the user what to do with them before proceeding. Options to offer:
- Stage them too (include in this commit)
- Leave them unstaged (ignore for now)
- Stash them

Never silently include unrelated files.

## Writing the Commit Message

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short description
```

Rules:
- **Single line only** — never multi-line, never a body, never a footer
- **No co-author information** — ever
- Types: `feat`, `fix`, `refactor`, `style`, `docs`, `test`, `chore`, `build`, `ci`
- Scope is optional but helpful (e.g., `feat(auth):`, `fix(api):`)
- Description: present tense, lowercase, no period at end
- Total length: under 72 characters

**Examples:**
```
feat(search): add keyboard shortcut to open search overlay
fix(rss): guard against missing site config
refactor: replace max-width containers with css grid layout
chore: update dependencies
```

**Never write:**
```
# Wrong: multi-line
feat(search): add search overlay

This adds a search overlay triggered by ⌘K.

Co-authored-by: Claude <noreply@anthropic.com>  ← NEVER

# Wrong: too long / imperative
Added the new search overlay feature with keyboard shortcut support and blur backdrop
```

## Pushing

- **Checkpoint commits** (mid-task, WIP): commit only, do not push
- **Task completion** (feature done, bug fixed, task complete): commit and push

If it's unclear whether this is a checkpoint or completion, ask before pushing.

## The Workflow

1. Run `git status` to see all changed files
2. Identify which files belong to the current task
3. If unrelated files are present → **ask the user** before proceeding
4. Stage task files: `git add <specific files>`
5. Write commit message following Conventional Commits (single line, no co-author)
6. Commit: `git commit -m "type(scope): description"`
7. If task is complete → `git push`; if checkpoint → stop here
