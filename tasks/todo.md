# Shared/local split across all dotfiles

Plan: ~/.claude/plans/buzzing-splashing-shannon.md

## Repo (pattern infrastructure)
- [x] zsh/.zshrc: move ~/.zshrc.local source line to top
- [x] claude/CLAUDE.md: portable workspace path + @~/.claude/CLAUDE.local.md import
- [x] claude/settings.json: slim to shared prefs, updated to live values, ~ statusline path
- [x] ghostty/config.ghostty: add config-file = ?config.local.ghostty
- [x] install.sh: ghostty → XDG path, create companions, restore exec bit
- [x] .gitignore: ignore local companion patterns

## This machine (migration)
- [x] ~/.zshrc.local: machine-specific half of live .zshrc (incl. API key — stays out of repo)
- [x] ~/.claude/settings.local.json: merge in permissions/plugins/marketplaces (via jq from live files)
- [x] ~/.claude/CLAUDE.local.md: scaffold
- [x] run install.sh; remove redundant AppSupport ghostty symlink

## Docs
- [x] README: Shared vs. local section + updated structure tree
- [x] sync-dotfiles SKILL.md: add CLAUDE.md companion row, fix companion paths/ordering

## Verify & ship
- [x] zsh smoke test: JAVA_HOME loads, `ll` alias present, cgr-token defined, custom prompt wins over omz
- [x] jq: both settings files valid; no secrets in repo (grep sk-ant/API_KEY clean)
- [x] readlink: all four managed files symlink into repo; install.sh idempotent (0 backups on re-run)
- [x] ghostty +show-config: config loads from XDG path; include expands to ~/.config/ghostty/config.local.ghostty
- [ ] commit + push

## Review

Every managed file now holds only the shared baseline; machine-specific content lives in
never-committed companions (~/.zshrc.local, ~/.claude/CLAUDE.local.md, ~/.claude/settings.local.json,
~/.config/ghostty/config.local.ghostty) that install.sh creates when missing. Ghostty consolidated to
the XDG path (works on macOS + Linux). Evidence for ghostty include semantics came from Config.zig
source: relative config-file paths expand against the file path *as opened* (the symlink dir), and
included files load last so local wins — confirmed live via +show-config. Merge-based generation was
considered and rejected (makes sync-back a permanent per-edit problem; documented as fallback in README).

Caveat: a running Claude Code session writes plugin/permission changes through the settings.json
symlink into the repo copy — that drift shows in `git status` and gets routed by /sync-dotfiles.
