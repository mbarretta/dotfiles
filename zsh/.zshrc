setopt PROMPT_SUBST

_git_prompt() {
  local branch=$(git branch --show-current 2>/dev/null)
  [[ -z "$branch" ]] && return
  local status_str=""
  git diff --quiet 2>/dev/null && git diff --quiet --cached 2>/dev/null || status_str="%F{yellow}*%f"
  git status --porcelain 2>/dev/null | grep -q '^??' && status_str="${status_str}%F{magenta}?%f"
  if [[ -n "$status_str" ]]; then
    echo " %F{240}::%f %F{cyan}${branch}%f [${status_str}]"
  else
    echo " %F{240}::%f %F{cyan}${branch}%f"
  fi
}

export PROMPT='
%B%F{cyan}%n%b%F{240}@%B%F{cyan}%m%f%b %F{240}::%f %F{green}%/$(_git_prompt)
%F{240}::%f %f'
export PATH="$HOME/.local/bin:$PATH"

alias ll="ls -al"

test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh"

