#!/bin/bash
# dotfiles install script — symlinks shared config into place and ensures each
# file's machine-local companion exists (never committed; see README)
set -e

DOTFILES="$(cd "$(dirname "$0")" && pwd)"

link() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    echo "  backing up existing $dst -> $dst.bak"
    mv "$dst" "$dst.bak"
  fi
  ln -sf "$src" "$dst"
  echo "  linked $dst"
}

companion() {
  local dst="$1" seed="${2:-}"
  [ -f "$dst" ] && return
  mkdir -p "$(dirname "$dst")"
  printf '%s' "$seed" > "$dst"
  echo "  created $dst (machine-local, never committed)"
}

echo "==> zsh"
link "$DOTFILES/zsh/.zshrc" "$HOME/.zshrc"
companion "$HOME/.zshrc.local"

echo "==> claude"
link "$DOTFILES/claude/CLAUDE.md" "$HOME/.claude/CLAUDE.md"
link "$DOTFILES/claude/statusline-command.sh" "$HOME/.claude/statusline-command.sh"
link "$DOTFILES/claude/settings.json" "$HOME/.claude/settings.json"
link "$DOTFILES/claude/skills/git-commit/SKILL.md" "$HOME/.claude/skills/git-commit/SKILL.md"
companion "$HOME/.claude/CLAUDE.local.md"
companion "$HOME/.claude/settings.local.json" '{}
'

echo "==> ghostty"
# XDG path works on macOS and Linux (ghostty loads it on both)
link "$DOTFILES/ghostty/config.ghostty" "$HOME/.config/ghostty/config.ghostty"
companion "$HOME/.config/ghostty/config.local.ghostty"

echo "Done."
