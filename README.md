# dotfiles

Personal shell and tool configuration for [@mbarretta](https://github.com/mbarretta).

## Structure

```
dotfiles/
├── zsh/
│   └── .zshrc                       # Zsh config: custom prompt (git-aware), aliases, PATH
├── claude/
│   ├── CLAUDE.md                    # Global Claude Code instructions (workflow, git prefs)
│   ├── statusline-command.sh        # Claude Code status bar: model, cost, context bar, rate limits
│   ├── settings.json                # Claude Code settings: model, theme, effort, marketplaces
│   ├── rules/                       # ~/.claude/rules/ — instruction rules, per profile
│   │   ├── common/                  #   every environment
│   │   └── personal/                #   personal environment only
│   ├── commands/                    # Custom slash commands
│   └── plugins-common.txt           # Plugins installed everywhere (add plugins-<profile>.txt to scope one)
├── ghostty/
│   └── config.ghostty               # Ghostty terminal config
└── install.sh                       # Symlinks everything into place, creates local companions
```

Skills are **not** vendored here. They arrive as plugins from a marketplace, or from their own
upstream installers (`npx skills add vercel-labs/agent-skills -g`). Vendored
copies drift silently, which is the problem this repo exists to avoid.

Auto memory is **not** synced. It is machine-local by design, keyed to a repository path, and holds
the content least suitable for a git remote. Portable working knowledge belongs in `claude/rules/`
or in a skill instead.

## Shared vs. local

The repo holds only the **shared baseline** — the parts worth having on any machine. Machine-specific content (secrets, absolute paths, locally-installed tool inits, work-only plugins) lives in a **local companion** file that is never committed. `install.sh` creates empty companions when missing.

| Managed file (repo) | Local companion | Include mechanism |
|---|---|---|
| `zsh/.zshrc` | `~/.zshrc.local` | sourced at the *top* of `.zshrc` — local sets up the machine first, shared prompt/aliases win |
| `claude/CLAUDE.md` | `~/.claude/CLAUDE.local.md` | `@~/.claude/CLAUDE.local.md` import at the end |
| `claude/settings.json` | `~/.claude/settings.local.json` | built into Claude Code (local merges over shared) |
| `ghostty/config.ghostty` | `~/.config/ghostty/config.local.ghostty` | `config-file = ?config.local.ghostty` — resolves next to the live symlink, loads after the shared file so local wins; `?` makes it optional |

Rule of thumb: if it wouldn't be true or useful on a fresh machine — a credential, a `/Users/...` path, pyenv/cargo init, a work plugin — it goes in the companion. The `/sync-dotfiles` skill routes drift accordingly. If a future dotfile's format has no include mechanism, fall back to generating the live file from shared + local at install time (nothing needs this today).

One key needs more than a companion. Because `~/.claude/settings.json` is a **symlink into this
repo**, Claude Code's own writes land in the working tree — and it re-adds `enabledPlugins` on every
plugin enable/disable. A fresh clone must not inherit this machine's plugin set, so `.gitattributes`
puts that file behind a `clean` filter (`jq -S 'del(.enabledPlugins)'`) which strips the key at stage
time. The key keeps working locally and never reaches a commit; `jq -S` also absorbs Claude Code's
key reordering. Git never takes filter definitions from a clone, so `install.sh` sets it on each
machine — and warns if `jq` is missing, because the filter then silently degrades.

## Profiles

One repo serves several differently-purposed machines. Components are **opt-in**, not opt-out, so
job-specific config cannot leak into the personal environment by forgetting an exclusion.

`~/.claude/sync-profile.local` — machine-local, never committed, created empty-with-`common` by
`install.sh` — names the profiles this machine takes:

```
common personal
```

Rules land in per-profile subdirectories (`~/.claude/rules/common/`, `~/.claude/rules/personal/`).
Claude Code discovers `rules/` recursively, so this namespaces them and avoids cross-profile
filename collisions. Plugin lists follow the same pattern: `plugins-<profile>.txt`.

Today only `common` carries content: everything portable turned out to be genuinely universal,
including Obsidian (personal notes, but used on every machine). The split exists for the *next*
employer's config, which should never reach the personal machine by default.

## Install

```bash
git clone https://github.com/mbarretta/dotfiles ~/workspace/github/mbarretta/dotfiles
cd ~/workspace/github/mbarretta/dotfiles
chmod +x install.sh
./install.sh                      # interactive: asks for target home, then per component
```

Non-interactive and inspection modes:

```bash
./install.sh --all                # everything, no prompts
./install.sh --only claude        # just the claude-* components
./install.sh --skip zsh,ghostty   # everything else
./install.sh --exclude foo.md     # skip an individual rule/command/plugin
./install.sh --home /Users/other  # target a different home directory
./install.sh --dry-run            # print actions, change nothing
./install.sh --print-map          # "src<TAB>dst" for every managed path
./install.sh --prune              # report orphaned symlinks (add --force to remove)
```

`--print-map` is the interface `/sync-dotfiles` uses to build its file map. It replaces grepping
`^link ` out of this script, which misses anything called from a loop or a component function.

Re-running is safe: a destination already pointing at the repo reports `ok` and is left alone.
Anything real that has to be moved aside goes to a timestamped directory under
`~/.claude-migration-backups/`, never to an in-place `.bak` — a single `.bak` slot gets clobbered by
the second run, and a `.bak` left inside `~/.claude/skills/` is discovered as a duplicate skill.

Prerequisites: `git`, `rsync`, `jq`, `claude` on `PATH`, and `npx`. Plugin installs need git auth for
any private marketplace.

## Claude Code status line

The `claude/statusline-command.sh` renders a custom status bar with:
- **user@host :: cwd** with current git branch + dirty flag
- **model** and **effort level**
- **session cost** (running total)
- **ctx bar** — 10-block visual bar color-coded by usage (blue→yellow→red)
- **rate limits** — 5-hour and 7-day usage percentages

To activate, add to `~/.claude/settings.json`:
```json
{
  "statusLine": {
    "type": "command",
    "command": "sh ~/.claude/statusline-command.sh"
  }
}
```
