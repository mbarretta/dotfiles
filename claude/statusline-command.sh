#!/bin/sh
input=$(cat)
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
model=$(echo "$input" | jq -r '.model.display_name // empty')
effort=$(echo "$input" | jq -r '.effort.level // empty')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')
rate5=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
rate7=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')

# Git branch + status
git_branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
git_dirty=""
git_untracked=""
if [ -n "$git_branch" ]; then
  git -C "$cwd" diff --quiet 2>/dev/null && git -C "$cwd" diff --quiet --cached 2>/dev/null || git_dirty="*"
  git -C "$cwd" status --porcelain 2>/dev/null | grep -q '^??' && git_untracked="?"
fi

# user@host :: /path
printf '\033[1;36m%s\033[0m\033[38;5;240m@\033[0m\033[1;36m%s\033[0m \033[38;5;240m::\033[0m \033[0;32m%s\033[0m' "$(whoami)" "$(hostname -s)" "$cwd"

# :: branch [*?]
if [ -n "$git_branch" ]; then
  printf ' \033[38;5;240m::\033[0m \033[0;36m%s\033[0m' "$git_branch"
  if [ -n "$git_dirty" ] || [ -n "$git_untracked" ]; then
    printf ' ['
    [ -n "$git_dirty" ] && printf '\033[0;33m*\033[0m'
    [ -n "$git_untracked" ] && printf '\033[0;35m?\033[0m'
    printf ']'
  fi
fi

# :: model · effort · $cost ::
if [ -n "$model" ]; then
  printf ' \033[38;5;240m::\033[0m \033[0;36m%s\033[0m' "$model"
  [ -n "$effort" ] && printf ' · \033[0;37m%s\033[0m' "$effort"
  [ -n "$cost" ] && printf ' · \033[0;35m$%s\033[0m' "$(printf '%.2f' "$cost")"
  printf ' \033[38;5;240m::\033[0m'
fi

# ctx bar
if [ -n "$used" ]; then
  filled=$(printf '%.0f' "$(echo "$used * 10 / 100" | bc -l)")
  [ "$filled" -gt 10 ] && filled=10
  empty=$((10 - filled))
  bar=""
  i=0
  while [ $i -lt $filled ]; do bar="${bar}█"; i=$((i+1)); done
  i=0
  while [ $i -lt $empty ]; do bar="${bar}░"; i=$((i+1)); done
  int_used=$(printf '%.0f' "$used")
  if [ "$int_used" -ge 80 ]; then
    bar_color='\033[0;31m'
  elif [ "$int_used" -ge 50 ]; then
    bar_color='\033[0;33m'
  else
    bar_color='\033[0;32m'
  fi
  printf " \033[38;5;240mctx:\033[0m${bar_color}%s\033[0m" "$bar"
fi

# rate limits
if [ -n "$rate5" ] || [ -n "$rate7" ]; then
  rate_color() {
    pct=$(printf '%.0f' "$1")
    if [ "$pct" -ge 80 ]; then printf '\033[0;31m'
    elif [ "$pct" -ge 50 ]; then printf '\033[0;33m'
    else printf '\033[0;32m'
    fi
  }
  printf ' \033[38;5;240m::\033[0m '
  if [ -n "$rate5" ]; then
    printf '%s5hr:%.0f%%\033[0m' "$(rate_color "$rate5")" "$rate5"
  fi
  if [ -n "$rate5" ] && [ -n "$rate7" ]; then
    printf ' · '
  fi
  if [ -n "$rate7" ]; then
    printf '%s7d:%.0f%%\033[0m' "$(rate_color "$rate7")" "$rate7"
  fi
fi
