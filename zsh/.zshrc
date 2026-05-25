setopt PROMPT_SUBST

_git_prompt() {
  local branch=$(git branch --show-current 2>/dev/null)
  [[ -z "$branch" ]] && return
  git diff --quiet 2>/dev/null && git diff --quiet --cached 2>/dev/null || branch="${branch}*"
  git status --porcelain 2>/dev/null | grep -q '^??' && branch="${branch}?"
  echo " %F{blue}::%f %F{yellow}${branch}%f"
}

export PROMPT='
%B%F{cyan}%n%b%F{blue}@%B%F{cyan}%m%f%b :: %F{green}%/$(_git_prompt)
:: %f'
export PATH="$HOME/.local/bin:$PATH"

alias ll="ls -al"

test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh"

