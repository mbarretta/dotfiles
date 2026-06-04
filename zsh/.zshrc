setopt PROMPT_SUBST

_git_prompt() {
  local branch=$(git branch --show-current 2>/dev/null)
  [[ -z "$branch" ]] && return
  local status_chars=""
  git diff --quiet 2>/dev/null && git diff --quiet --cached 2>/dev/null || status_chars="${status_chars}*"
  git status --porcelain 2>/dev/null | grep -q '^??' && status_chars="${status_chars}?"
  [[ -n "$status_chars" ]] && branch="${branch} [${status_chars}]"
  echo " %F{blue}::%f %F{yellow}${branch}%f"
}

export PROMPT='
%B%F{cyan}%n%b%F{blue}@%B%F{cyan}%m%f%b :: %F{green}%/$(_git_prompt)
:: %f'
export PATH="$HOME/.local/bin:$PATH"

alias ll="ls -al"

test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh"

