---
paths:
  - "**/*.plist"
  - "**/crontab"
  - "**/Library/LaunchAgents/**"
---

# Scheduling headless Claude runs

**Headless plugin commands only resolve from `$HOME`.** `claude -p '/plugin-command'` resolves plugin
slash commands only when the working directory is the home directory; from a repo checkout it fails
with `Unknown command`. Set `WorkingDirectory` to the home directory for any launchd or cron job that
invokes one.

**Exit status is not a success signal.** The `Unknown command` failure **exits 0**, so launchd reports
success while the job produced nothing. Verify the artifact the job was supposed to write, or grep its
log for `Unknown command`. Cheap resolution probe from the job's own cwd:

```bash
claude -p '/the-command' --max-turns 1 --allowedTools '' --model haiku
```

**Project memory is not loaded in headless runs.** Only skill and reference files are in context, so a
rule that governs a scheduled job's behavior must live in the skill's files — a correction saved to
memory silently fails to reach the scheduled path.

**Cron has no ssh-agent.** A scheduled job that pushes needs a passphraseless deploy key, or the push
fails silently.
