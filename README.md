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
│   ├── settings.json                # Claude Code settings: model, theme, effort level
│   └── skills/
│       └── git-commit/SKILL.md      # Custom git-commit skill (conventional commits, no co-author)
├── ghostty/
│   └── config.ghostty               # Ghostty terminal config
└── install.sh                       # Symlinks everything into place, creates local companions
```

## Shared vs. local

The repo holds only the **shared baseline** — the parts worth having on any machine. Machine-specific content (secrets, absolute paths, locally-installed tool inits, work-only plugins) lives in a **local companion** file that is never committed. `install.sh` creates empty companions when missing.

| Managed file (repo) | Local companion | Include mechanism |
|---|---|---|
| `zsh/.zshrc` | `~/.zshrc.local` | sourced at the *top* of `.zshrc` — local sets up the machine first, shared prompt/aliases win |
| `claude/CLAUDE.md` | `~/.claude/CLAUDE.local.md` | `@~/.claude/CLAUDE.local.md` import at the end |
| `claude/settings.json` | `~/.claude/settings.local.json` | built into Claude Code (local merges over shared) |
| `ghostty/config.ghostty` | `~/.config/ghostty/config.local.ghostty` | `config-file = ?config.local.ghostty` — resolves next to the live symlink, loads after the shared file so local wins; `?` makes it optional |

Rule of thumb: if it wouldn't be true or useful on a fresh machine — a credential, a `/Users/...` path, pyenv/cargo init, a work plugin — it goes in the companion. The `/sync-dotfiles` skill routes drift accordingly. If a future dotfile's format has no include mechanism, fall back to generating the live file from shared + local at install time (nothing needs this today).

## Install

```bash
git clone https://github.com/mbarretta/dotfiles ~/workspace/github/mbarretta/dotfiles
cd ~/workspace/github/mbarretta/dotfiles
chmod +x install.sh
./install.sh
```

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
