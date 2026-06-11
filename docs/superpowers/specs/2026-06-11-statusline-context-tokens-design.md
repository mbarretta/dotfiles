# Statusline: show token count in context bar

## Goal

Surface the actual number of tokens currently in context, alongside the
existing percentage-based context bar in the Claude Code statusline.

## Data source

The statusline receives `context_window.total_input_tokens` (current input
tokens, including cache reads/writes) via stdin JSON, in addition to the
already-used `context_window.used_percentage`.

## Change

In `claude/statusline-command.sh` (and the synced copy at
`~/.claude/statusline-command.sh`):

- Read `total_input_tokens` from the input JSON.
- After the existing 10-character block bar, append the token count rounded
  to the nearest thousand with a `k` suffix (e.g. `42k`, `116k`).
- Render this in grey (`\033[38;5;240m`), matching the `ctx:` label.
- Result: `ctx:[██████░░░░] 116k`
- Gate this independently on `total_input_tokens` being present, so it
  degrades gracefully like the rest of the bar.

## Out of scope

- Showing the total context window size (e.g. `116k/200k`) — rejected in
  favor of the more compact "used only" display.
- Color-coding the token count by severity — kept neutral grey.
