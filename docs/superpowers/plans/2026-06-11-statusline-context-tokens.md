# Statusline Context Token Count Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the number of tokens currently in context (e.g. `116k`) appended to the existing context-usage bar in the Claude Code statusline.

**Architecture:** Single shell script (`claude/statusline-command.sh`) already reads `context_window.used_percentage` from stdin JSON to render a 10-character block bar. Add a read of `context_window.total_input_tokens` and append it, rounded to the nearest thousand with a `k` suffix, in grey, right after the bar. Then sync the change to the live copy at `~/.claude/statusline-command.sh`.

**Tech Stack:** POSIX `sh`, `jq`, `bc`, ANSI escape codes.

---

### Task 1: Add token count to the context bar

**Files:**
- Modify: `/Users/barretta/workspace/github/mbarretta/dotfiles/claude/statusline-command.sh`

- [ ] **Step 1: Capture current ("before") output for a sample input**

Create a sample input fixture and confirm today's output does NOT contain a token count.

Run:
```bash
cat > /tmp/statusline-sample.json <<'EOF'
{
  "workspace": {"current_dir": "/tmp"},
  "model": {"display_name": "sonnet-4.6"},
  "effort": {"level": "high"},
  "context_window": {"used_percentage": 58, "total_input_tokens": 116432},
  "cost": {"total_cost_usd": 0.42},
  "rate_limits": {"five_hour": {"used_percentage": 12}, "seven_day": {"used_percentage": 8}}
}
EOF
sh /Users/barretta/workspace/github/mbarretta/dotfiles/claude/statusline-command.sh < /tmp/statusline-sample.json | sed 's/\x1b\[[0-9;]*m//g'
```

Expected: a line ending in `... :: ctx:██████░░░░ :: 5hr:12% · 7d:8%` — note there is **no** `116k` anywhere in the output yet.

- [ ] **Step 2: Read `total_input_tokens` from the input**

In `claude/statusline-command.sh`, find this block near the top (lines 2-9):

```sh
input=$(cat)
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
model=$(echo "$input" | jq -r '.model.display_name // empty')
effort=$(echo "$input" | jq -r '.effort.level // empty')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')
rate5=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
rate7=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
```

Add a new line after the `used=` line:

```sh
input=$(cat)
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
model=$(echo "$input" | jq -r '.model.display_name // empty')
effort=$(echo "$input" | jq -r '.effort.level // empty')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
total_tokens=$(echo "$input" | jq -r '.context_window.total_input_tokens // empty')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')
rate5=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
rate7=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
```

- [ ] **Step 3: Append the token count after the context bar**

Find the end of the "ctx bar" block (currently ends with the line that prints the bar):

```sh
  printf " \033[38;5;240mctx:\033[0m${bar_color}%s\033[0m" "$bar"
fi
```

Change it to append the token count, rounded to the nearest thousand, in grey:

```sh
  printf " \033[38;5;240mctx:\033[0m${bar_color}%s\033[0m" "$bar"
  if [ -n "$total_tokens" ]; then
    tokens_k=$(printf '%.0f' "$(echo "$total_tokens / 1000" | bc -l)")
    printf ' \033[38;5;240m%sk\033[0m' "$tokens_k"
  fi
fi
```

- [ ] **Step 4: Verify the new output**

Run:
```bash
sh /Users/barretta/workspace/github/mbarretta/dotfiles/claude/statusline-command.sh < /tmp/statusline-sample.json | sed 's/\x1b\[[0-9;]*m//g'
```

Expected: the `ctx:` segment now reads `ctx:██████░░░░ 116k` (116432 / 1000 rounds to 116).

- [ ] **Step 5: Verify graceful fallback when `total_input_tokens` is absent**

Run:
```bash
cat > /tmp/statusline-sample-notokens.json <<'EOF'
{
  "workspace": {"current_dir": "/tmp"},
  "model": {"display_name": "sonnet-4.6"},
  "effort": {"level": "high"},
  "context_window": {"used_percentage": 58},
  "cost": {"total_cost_usd": 0.42}
}
EOF
sh /Users/barretta/workspace/github/mbarretta/dotfiles/claude/statusline-command.sh < /tmp/statusline-sample-notokens.json | sed 's/\x1b\[[0-9;]*m//g'
```

Expected: `ctx:██████░░░░` with no trailing token count and no errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/barretta/workspace/github/mbarretta/dotfiles
git add claude/statusline-command.sh
git commit -m "feat(claude): show token count in statusline context bar"
```

---

### Task 2: Sync the change to the live statusline script

**Files:**
- Modify: `/Users/barretta/.claude/statusline-command.sh`

- [ ] **Step 1: Copy the updated script to the live location**

```bash
cp /Users/barretta/workspace/github/mbarretta/dotfiles/claude/statusline-command.sh /Users/barretta/.claude/statusline-command.sh
```

- [ ] **Step 2: Confirm the two files are identical**

```bash
diff /Users/barretta/workspace/github/mbarretta/dotfiles/claude/statusline-command.sh /Users/barretta/.claude/statusline-command.sh
```

Expected: no output (files identical).

- [ ] **Step 3: Run the live script against the sample fixture**

```bash
sh /Users/barretta/.claude/statusline-command.sh < /tmp/statusline-sample.json | sed 's/\x1b\[[0-9;]*m//g'
```

Expected: same output as Task 1 Step 4, including ` 116k`.

- [ ] **Step 4: Clean up sample fixtures**

```bash
rm -f /tmp/statusline-sample.json /tmp/statusline-sample-notokens.json
```

No commit needed for this task — `~/.claude/statusline-command.sh` is outside the dotfiles git repo.
