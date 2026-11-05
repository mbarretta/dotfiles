#!/bin/sh
input=$(cat)
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
model=$(echo "$input" | jq -r '.model.display_name // empty')
effort=$(echo "$input" | jq -r '.effort.level // empty')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
total_tokens=$(echo "$input" | jq -r '.context_window.total_input_tokens // empty')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')
rate5=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
rate7=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
cache_ttl=$(echo "$input" | jq -r '.prompt_cache.ttl // empty')
cache_expires=$(echo "$input" | jq -r '.prompt_cache.expires_at // empty')

# Total line width; override per machine with CLAUDE_STATUSLINE_WIDTH
line_width=${CLAUDE_STATUSLINE_WIDTH:-172}

# Git branch + status
git_branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
git_dirty=""
git_untracked=""
if [ -n "$git_branch" ]; then
  git -C "$cwd" diff --quiet 2>/dev/null && git -C "$cwd" diff --quiet --cached 2>/dev/null || git_dirty="*"
  git -C "$cwd" status --porcelain 2>/dev/null | grep -q '^??' && git_untracked="?"
fi

# Visible width of a rendered string: strip ANSI colors, then count UTF-8 characters
# (bytes minus continuation bytes) so the result doesn't depend on the locale
esc=$(printf '\033')
vis_width() {
  printf '%s' "$1" | sed "s/${esc}\[[0-9;]*m//g" | LC_ALL=C tr -d '\200-\277' | wc -c | tr -d ' '
}

# Everything right of the cwd column, rendered first so the cwd can take the remaining width
right_segments() {
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

  # :: model · effort ::
  if [ -n "$model" ]; then
    printf ' \033[38;5;240m::\033[0m \033[0;36m%s\033[0m' "$model"
    [ -n "$effort" ] && printf ' \033[38;5;240m·\033[0m \033[0;37m%s\033[0m' "$effort"
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
    printf " \033[0;37mctx:\033[0m${bar_color}%s\033[0m" "$bar"
    if [ -n "$total_tokens" ]; then
      tokens_k=$(printf '%.0f' "$(echo "$total_tokens / 1000" | bc -l)")
      printf ' \033[0;37m%sk\033[0m' "$tokens_k"
    fi
  fi

  # :: cache: time left on the prompt cache TTL (yellow in its last 20%, red once cold)
  if [ -n "$cache_ttl" ]; then
    cache_left=$(( ${cache_expires:-0} - $(date +%s) ))
    if [ -z "$cache_expires" ] || [ "$cache_left" -le 0 ]; then
      printf ' \033[38;5;240m::\033[0m \033[0;37mcache:\033[0m \033[0;31mcold\033[0m'
    else
      [ "$cache_ttl" = "1h" ] && cache_span=3600 || cache_span=300
      if [ "$cache_left" -le $((cache_span / 5)) ]; then cache_color='\033[0;33m'; else cache_color='\033[0;32m'; fi
      printf " \033[38;5;240m::\033[0m \033[0;37mcache:\033[0m ${cache_color}%d:%02d\033[0m" $((cache_left / 60)) $((cache_left % 60))
    fi
  fi

  # :: rate limits (only claude.ai Pro/Max sessions receive these)
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
      printf ' \033[38;5;240m·\033[0m '
    fi
    if [ -n "$rate7" ]; then
      printf '%s7d:%.0f%%\033[0m' "$(rate_color "$rate7")" "$rate7"
    fi
  fi

  # :: $cost
  [ -n "$cost" ] && printf ' \033[38;5;240m::\033[0m \033[0;35m$%s\033[0m' "$(printf '%.2f' "$cost")"
}
right=$(right_segments)

# cwd column gets whatever width remains: $HOME becomes ~, drop whole leading dirs behind
# "…/" if still too wide, pad short paths
user=$(whoami)
host=$(hostname -s)
cwd_width=$((line_width - ${#user} - 1 - ${#host} - 4 - $(vis_width "$right")))
[ "$cwd_width" -lt 12 ] && cwd_width=12
case $cwd in
  "$HOME") cwd_disp="~" ;;
  "$HOME"/*) cwd_disp="~/${cwd#"$HOME"/}" ;;
  *) cwd_disp=$cwd ;;
esac
cwd_vis=${#cwd_disp}
if [ "$cwd_vis" -gt "$cwd_width" ]; then
  rest=${cwd_disp#/}
  rest=${rest#\~/}
  while [ $((${#rest} + 2)) -gt "$cwd_width" ] && [ "${rest#*/}" != "$rest" ]; do rest=${rest#*/}; done
  # A single component wider than the column keeps its last characters
  [ $((${#rest} + 2)) -gt "$cwd_width" ] && rest=$(printf '%s' "$rest" | cut -c $((${#rest} - cwd_width + 3))-)
  cwd_disp="…/$rest"
  cwd_vis=$((${#rest} + 2))
fi

# user@host :: /path<pad><right segments>
printf '\033[1;36m%s\033[0m\033[38;5;240m@\033[0m\033[1;36m%s\033[0m \033[38;5;240m::\033[0m \033[0;32m%s\033[0m' "$user" "$host" "$cwd_disp"
printf "%$((cwd_width - cwd_vis))s" ''
printf '%s' "$right"
