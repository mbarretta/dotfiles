#!/bin/sh
input=$(cat)
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
model=$(echo "$input" | jq -r '.model.display_name // empty')
effort=$(echo "$input" | jq -r '.effort.level // empty')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')
rate5=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
rate7=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')

# Git branch + dirty indicator
git_branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
git_dirty=""
if [ -n "$git_branch" ]; then
  git -C "$cwd" diff --quiet --cached 2>/dev/null || git_dirty="*"
fi

printf '\033[1;36m%s\033[0m\033[0;34m@\033[0m\033[1;36m%s\033[0m :: \033[0;32m%s\033[0m' "$(whoami)" "$(hostname -s)" "$cwd"

[ -n "$git_branch" ] && printf ' \033[0;34m[\033[0m\033[0;33m%s%s\033[0m\033[0;34m]\033[0m' "$git_branch" "$git_dirty"

meta=""
[ -n "$model" ] && meta="$model"
[ -n "$effort" ] && meta="$meta  effort:$effort"
[ -n "$cost" ] && meta="$meta  \$$(printf '%.2f' "$cost")"

[ -n "$meta" ] && printf ' \033[0;34m::\033[0m \033[0;36m%s\033[0m' "$meta"

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
    bar_color='\033[0;34m'
  fi
  printf "  \033[0;34mctx:\033[0m${bar_color}%s\033[0m" "$bar"
fi

if [ -n "$rate5" ] || [ -n "$rate7" ]; then
  printf ' \033[0;34m:: rate limits —\033[0m \033[0;35m5hr:%.0f%%  7d:%.0f%%\033[0m' "$rate5" "$rate7"
fi
