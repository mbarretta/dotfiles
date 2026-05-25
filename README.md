# dotfiles

Personal shell and tool configuration for [@mbarretta](https://github.com/mbarretta).

## Structure

```
dotfiles/
├── zsh/
│   └── .zshrc                       # Zsh config: custom prompt (git-aware), aliases, PATH
├── claude/
│   ├── statusline-command.sh        # Claude Code status bar: model, cost, context bar, rate limits
│   ├── settings.json                # Claude Code settings: plugins, theme, effort level
│   └── skills/
│       └── git-commit/SKILL.md      # Custom git-commit skill (conventional commits, no co-author)
└── install.sh                       # Symlinks everything into place
```

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
