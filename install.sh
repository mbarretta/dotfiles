#!/bin/bash
# dotfiles install script — symlinks config files into place
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

echo "==> zsh"
link "$DOTFILES/zsh/.zshrc" "$HOME/.zshrc"

echo "==> claude"
link "$DOTFILES/claude/statusline-command.sh" "$HOME/.claude/statusline-command.sh"
link "$DOTFILES/claude/settings.json" "$HOME/.claude/settings.json"
link "$DOTFILES/claude/skills/git-commit/SKILL.md" "$HOME/.claude/skills/git-commit/SKILL.md"

echo "Done."
