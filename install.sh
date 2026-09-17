#!/bin/bash
# dotfiles install script — symlinks shared config into place and ensures each
# file's machine-local companion exists (never committed; see README)
#
# Components are opt-in per environment via profiles, so one repo can serve
# several differently-purposed machines (work, personal) without leaking
# job-specific config into the wrong one.
set -e

DOTFILES="$(cd "$(dirname "$0")" && pwd)"

COMPONENTS="zsh ghostty claude-core claude-rules claude-commands claude-skills claude-plugins"

TARGET_HOME="$HOME"
ON_COLLISION="backup"     # backup | skip | overwrite
DRY_RUN=0
PRINT_MAP=0
DO_PRUNE=0
FORCE=0
INTERACTIVE=1
ONLY=""
SKIP=""
EXCLUDE=""

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

  --all                    install everything, no prompts
  --only a,b               only these components (alias: "claude" = all claude-*)
  --skip a,b               everything except these
  --exclude name,name      skip individual rule/command/plugin items
  --home PATH              target home directory (default: $HOME)
  --on-collision POLICY    backup (default) | skip | overwrite
  --dry-run                print what would happen, change nothing
  --print-map              emit "src<TAB>dst" for every managed path
  --prune [--force]        report (then remove) orphaned symlinks
  -h, --help               this message

With no options, prompts for the target home then asks per component.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --all)           INTERACTIVE=0 ;;
    --only)          ONLY="$2"; INTERACTIVE=0; shift ;;
    --skip)          SKIP="$2"; INTERACTIVE=0; shift ;;
    --exclude)       EXCLUDE="$2"; shift ;;
    --home)          TARGET_HOME="$2"; shift ;;
    --on-collision)  ON_COLLISION="$2"; shift ;;
    --dry-run)       DRY_RUN=1; INTERACTIVE=0 ;;
    --print-map)     PRINT_MAP=1; INTERACTIVE=0 ;;
    --prune)         DO_PRUNE=1; INTERACTIVE=0 ;;
    --force)         FORCE=1 ;;
    -h|--help)       usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$ON_COLLISION" in
  backup|skip|overwrite) ;;
  *) echo "invalid --on-collision: $ON_COLLISION" >&2; exit 2 ;;
esac

TARGET_HOME="${TARGET_HOME%/}"
BACKUP_ROOT="$TARGET_HOME/.claude-migration-backups"
RUN_TS="$(date +%Y%m%dT%H%M%S)"

# --print-map must emit nothing but the map, so all chatter goes through say()
say() { [ "$PRINT_MAP" = 1 ] || echo "$1"; }
warn() { [ "$PRINT_MAP" = 1 ] || echo "  ! $1"; }

in_list() {  # in_list needle "a b c"
  local n="$1" hay="$2" i
  for i in $hay; do [ "$i" = "$n" ] && return 0; done
  return 1
}

is_excluded() {
  [ -n "$EXCLUDE" ] || return 1
  in_list "$1" "$(echo "$EXCLUDE" | tr ',' ' ')"
}

# "claude" expands to every claude-* component
expand() {
  local out="" i
  for i in $(echo "$1" | tr ',' ' '); do
    if [ "$i" = "claude" ]; then
      for c in $COMPONENTS; do case "$c" in claude-*) out="$out $c";; esac; done
    else
      out="$out $i"
    fi
  done
  echo "$out"
}

active_profiles() {
  local f="$TARGET_HOME/.claude/sync-profile.local" p=""
  [ -f "$f" ] && p="$(sed 's/#.*//' "$f" | tr '\n' ' ' | xargs)"
  echo "${p:-common}"
}

# Move an existing destination out of the way. Backups are timestamped and live
# OUTSIDE ~/.claude — a *.bak left in ~/.claude/skills becomes a shadow skill,
# and a single .bak slot is silently clobbered by a second run.
# Returns non-zero if the backup could not be made. Callers MUST NOT proceed to
# link in that case — replacing a file whose backup failed loses it outright.
stash() {
  local dst="$1" rel bak
  rel="${dst#"$TARGET_HOME"/}"
  bak="$BACKUP_ROOT/$RUN_TS/$rel"
  mkdir -p "$(dirname "$bak")" 2>/dev/null || return 1
  mv "$dst" "$bak" 2>/dev/null || return 1
  echo "  backed up $dst -> $bak"
}

link() {
  local src="$1" dst="$2"

  if [ "$PRINT_MAP" = 1 ]; then printf '%s\t%s\n' "$src" "$dst"; return 0; fi

  # already pointing where we want: nothing to do, and re-runs stay quiet
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    echo "  ok $dst"
    return 0
  fi

  if [ "$DRY_RUN" = 1 ]; then
    if [ -e "$dst" ] || [ -L "$dst" ]; then
      echo "  would $ON_COLLISION + link $dst"
    else
      echo "  would link $dst"
    fi
    return 0
  fi

  mkdir -p "$(dirname "$dst")"

  if [ -e "$dst" ] || [ -L "$dst" ]; then
    case "$ON_COLLISION" in
      skip)
        echo "  skip (exists) $dst"; return 0 ;;
      overwrite)
        rm -rf -- "$dst" 2>/dev/null || {
          warn "cannot remove $dst — not linking"; return 0; } ;;
      backup)
        stash "$dst" || {
          warn "cannot back up $dst — leaving it in place, not linking"; return 0; } ;;
    esac
  fi

  # -n is load-bearing: without it, `ln -sf` onto an existing symlink-to-directory
  # follows the link and creates the new one INSIDE the target, i.e. inside this repo.
  ln -sfn "$src" "$dst"
  echo "  linked $dst"
}

# A companion that can't be written must not abort the run under `set -e` —
# otherwise one permission error silently skips every remaining component.
companion() {
  local dst="$1" seed="${2:-}"
  [ "$PRINT_MAP" = 1 ] && return 0
  [ -f "$dst" ] && return 0
  if [ "$DRY_RUN" = 1 ]; then echo "  would create $dst (machine-local)"; return 0; fi
  if ! mkdir -p "$(dirname "$dst")" 2>/dev/null \
     || ! printf '%s' "$seed" > "$dst" 2>/dev/null; then
    warn "could not create $dst — create it by hand"
    return 0
  fi
  echo "  created $dst (machine-local, never committed)"
}

need_bin() {
  command -v "$1" >/dev/null 2>&1 || warn "missing '$1' — $2"
}

# ---------------------------------------------------------------- components

do_zsh() {
  say "==> zsh"
  link "$DOTFILES/zsh/.zshrc" "$TARGET_HOME/.zshrc"
  companion "$TARGET_HOME/.zshrc.local"
}

do_ghostty() {
  say "==> ghostty"
  # XDG path works on macOS and Linux (ghostty loads it on both)
  link "$DOTFILES/ghostty/config.ghostty" "$TARGET_HOME/.config/ghostty/config.ghostty"
  companion "$TARGET_HOME/.config/ghostty/config.local.ghostty"
}

# Because ~/.claude/settings.json is a symlink into this repo, Claude Code's own
# writes land in the working tree. It re-adds `enabledPlugins` on every plugin
# enable/disable, and `model`/`effortLevel` on /model and /config changes —
# machine-local state that must not be committed, or a fresh clone inherits
# this machine's plugin/model/effort choices. `autoMode` (the classifier
# customization block) is also machine/project-specific by nature and gets
# the same treatment, even though nothing writes it automatically — it's
# edited by hand per-project the same way. .gitattributes marks the file; the
# clean filter itself lives in .git/config, which git deliberately never takes
# from a clone, so every machine has to set it here.
install_settings_filter() {
  [ "$DRY_RUN" = 0 ] && [ "$PRINT_MAP" = 0 ] || return 0
  [ -d "$DOTFILES/.git" ] || return 0
  if ! command -v jq >/dev/null 2>&1; then
    warn "jq missing — settings.json clean filter inactive; machine-local keys will leak into commits"
    return 0
  fi
  local want="jq -S 'del(.enabledPlugins, .model, .effortLevel, .autoMode)'"
  if [ "$(git -C "$DOTFILES" config --get filter.claude-settings.clean 2>/dev/null)" = "$want" ]; then
    say "  ok settings.json clean filter"
  elif git -C "$DOTFILES" config filter.claude-settings.clean "$want" 2>/dev/null; then
    say "  set settings.json clean filter"
  else
    warn "could not set the settings.json clean filter; machine-local keys will leak into commits"
  fi
  return 0
}

do_claude_core() {
  say "==> claude core"
  if [ "$DRY_RUN" = 0 ] && [ "$PRINT_MAP" = 0 ] && pgrep -qf 'claude' 2>/dev/null; then
    warn "a claude process is running; it may rewrite settings.json through the symlink"
    warn "and undo what this run installs. Close it, or re-check settings.json afterward."
  fi
  install_settings_filter
  link "$DOTFILES/claude/CLAUDE.md"            "$TARGET_HOME/.claude/CLAUDE.md"
  link "$DOTFILES/claude/statusline-command.sh" "$TARGET_HOME/.claude/statusline-command.sh"
  link "$DOTFILES/claude/settings.json"        "$TARGET_HOME/.claude/settings.json"
  companion "$TARGET_HOME/.claude/CLAUDE.local.md"
  companion "$TARGET_HOME/.claude/settings.local.json" '{}
'
  companion "$TARGET_HOME/.claude/sync-profile.local" 'common
'
}

# Rules land in per-profile subdirectories: Claude Code discovers .claude/rules/
# recursively, so this namespaces them and avoids cross-profile name collisions.
do_claude_rules() {
  say "==> claude rules [profiles: $(active_profiles)]"
  local p f n any=0
  for p in $(active_profiles); do
    [ -d "$DOTFILES/claude/rules/$p" ] || continue
    for f in "$DOTFILES/claude/rules/$p"/*.md; do
      [ -e "$f" ] || continue
      any=1
      n="$(basename "$f")"
      if is_excluded "$n"; then say "  excluded $n"; continue; fi
      link "$f" "$TARGET_HOME/.claude/rules/$p/$n"
    done
  done
  [ "$any" = 0 ] && say "  (no rules yet)"
  return 0
}

do_claude_commands() {
  say "==> claude commands"
  local f n any=0
  for f in "$DOTFILES/claude/commands"/*.md; do
    [ -e "$f" ] || continue
    any=1
    n="$(basename "$f")"
    if is_excluded "$n"; then say "  excluded $n"; continue; fi
    link "$f" "$TARGET_HOME/.claude/commands/$n"
  done
  [ "$any" = 0 ] && say "  (no commands)"
  return 0
}

# Skills are distributed as plugins (see claude-plugins) or come from upstream
# installers. Nothing is vendored here, so this is mostly a prerequisite check.
do_claude_skills() {
  [ "$PRINT_MAP" = 1 ] && return 0
  say "==> claude skills"
  need_bin gws "brew install gws — provides the 25 gws-*/recipe-* skills"
  [ -d "$TARGET_HOME/.agents/skills/web-design-guidelines" ] || \
    warn "vercel-labs skills absent — npx skills add vercel-labs/agent-skills -g"
  return 0
}

# `claude plugin install` resolves a plugin name against the marketplace clone
# under ~/.claude/plugins/marketplaces/<name>/, and nothing has cloned those on a
# fresh machine: the clones are fetched lazily by an interactive session reading
# extraKnownMarketplaces, and the non-interactive `plugin` subcommands don't
# register settings-declared marketplaces at all. So every install fails with
# "not found in marketplace" — the CLI's suggested `marketplace update` fails too
# ("Marketplace not found"), because there is nothing registered yet to update.
#
# `marketplace add` is the only bootstrap primitive. It needs a real source (a
# bare marketplace name is rejected), so the sources come from settings.json —
# the same declaration Claude Code itself reads, rather than a second copy that
# could drift. It is idempotent once the clone exists.
bootstrap_marketplaces() {
  local name src mp="$TARGET_HOME/.claude/plugins/marketplaces"
  if ! command -v jq >/dev/null 2>&1; then
    warn "jq missing — cannot read marketplace sources from settings.json; plugin installs will fail"
    return 0
  fi
  # claude-plugins-official is a CLI default rather than a settings entry, but it
  # still has to be cloned explicitly; the rest are read from settings.json.
  while IFS="$(printf '\t')" read -r name src; do
    [ -n "$name" ] && [ -n "$src" ] || continue
    if [ -d "$mp/$name" ]; then say "  ok marketplace $name"; continue; fi
    if [ "$DRY_RUN" = 1 ]; then echo "  would add marketplace $name ($src)"; continue; fi
    if claude plugin marketplace add "$src" </dev/null >/dev/null 2>&1; then
      say "  added marketplace $name"
    else
      warn "could not add marketplace $name ($src)"
    fi
  done <<EOF
claude-plugins-official	anthropics/claude-plugins-official
$(jq -r '.extraKnownMarketplaces // {} | to_entries[]
         | "\(.key)\t\(.value.source.repo // .value.source.url // .value.source.path // "")"' \
       "$DOTFILES/claude/settings.json")
EOF
  return 0
}

do_claude_plugins() {
  [ "$PRINT_MAP" = 1 ] && return 0
  say "==> claude plugins [profiles: $(active_profiles)]"
  command -v claude >/dev/null 2>&1 || { warn "claude not on PATH; skipping plugins"; return 0; }
  bootstrap_marketplaces
  local p prof f err
  for prof in $(active_profiles); do
    f="$DOTFILES/claude/plugins-$prof.txt"
    [ -f "$f" ] || continue
    # read on fd 3: a bare `done < "$f"` hands the loop body this file as stdin,
    # and the first `claude` call consumes the rest of it (1 install, exit 0).
    while IFS= read -r p <&3 || [ -n "$p" ]; do
      case "$p" in ''|\#*) continue ;; esac
      if is_excluded "$p"; then say "  excluded $p"; continue; fi
      if [ "$DRY_RUN" = 1 ]; then echo "  would install $p"; continue; fi
      if err="$(claude plugin install "$p" -s user -y </dev/null 2>&1)"; then
        echo "  installed $p"
      else
        # keep the HEAD of the message: `tail -c` lopped off the front, so the
        # plugin name and the actual error were the parts that got eaten
        # ("claude-api" surfacing as "de-api") while the generic advice survived.
        echo "  FAILED $p — $(printf '%s' "$err" | tr '\n' ' ' | cut -c1-200)"
      fi
    done 3< "$f"
  done
  return 0
}

run_component() {
  case "$1" in
    zsh)             do_zsh ;;
    ghostty)         do_ghostty ;;
    claude-core)     do_claude_core ;;
    claude-rules)    do_claude_rules ;;
    claude-commands) do_claude_commands ;;
    claude-skills)   do_claude_skills ;;
    claude-plugins)  do_claude_plugins ;;
    *) echo "unknown component: $1" >&2; return 1 ;;
  esac
}

# ---------------------------------------------------------------------- prune

# Only ever removes a symlink that points into this repo and whose target is gone.
# Never -r, never a trailing slash: `rm -rf <symlink>/` follows into the repo and
# deletes the real content.
do_prune() {
  say "==> prune [orphaned symlinks into $DOTFILES]"
  local d l t found=0
  for d in "$TARGET_HOME/.claude/rules" "$TARGET_HOME/.claude/commands" \
           "$TARGET_HOME/.claude/skills" "$TARGET_HOME/.config/ghostty"; do
    [ -d "$d" ] || continue
    while IFS= read -r l; do
      [ -n "$l" ] || continue
      t="$(readlink "$l")"
      case "$t" in "$DOTFILES"*) ;; *) continue ;; esac
      [ -e "$t" ] && continue
      found=1
      if [ "$FORCE" = 1 ]; then
        rm -f -- "$l"; echo "  removed $l"
      else
        echo "  orphan $l -> $t"
      fi
    done <<EOF
$(find "$d" -type l 2>/dev/null)
EOF
  done
  if [ "$found" = 0 ]; then
    say "  no orphans"
  elif [ "$FORCE" = 0 ]; then
    say "  (re-run with --prune --force to remove)"
  fi
  return 0
}

# ----------------------------------------------------------------------- main

if [ "$DO_PRUNE" = 1 ]; then
  do_prune
  exit 0
fi

if [ "$INTERACTIVE" = 1 ]; then
  printf 'Target home directory [%s]: ' "$TARGET_HOME"
  read -r reply
  [ -n "$reply" ] && TARGET_HOME="${reply%/}"
  BACKUP_ROOT="$TARGET_HOME/.claude-migration-backups"
  SELECTED=""
  for c in $COMPONENTS; do
    printf '  install %-16s [Y/n]: ' "$c"
    read -r reply
    case "$reply" in [Nn]*) ;; *) SELECTED="$SELECTED $c" ;; esac
  done
else
  if [ -n "$ONLY" ]; then
    SELECTED="$(expand "$ONLY")"
  else
    SELECTED=""
    SKIPX="$(expand "$SKIP")"
    for c in $COMPONENTS; do
      in_list "$c" "$SKIPX" || SELECTED="$SELECTED $c"
    done
  fi
fi

for c in $SELECTED; do
  in_list "$c" "$COMPONENTS" || { echo "unknown component: $c" >&2; exit 2; }
done

for c in $SELECTED; do
  run_component "$c"
done

say "Done."
