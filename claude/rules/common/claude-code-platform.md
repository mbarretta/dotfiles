# Claude Code platform behavior

**The installed plugin is a managed cache, not your working tree.** Committing and pushing a change
to a plugin repo does **not** make it live. Claude Code loads plugins from the marketplace clone under
`~/.claude/plugins/marketplaces/<name>/` and runs versioned copies from `~/.claude/plugins/cache/`.
That clone lags `origin/main` until a `/plugin` update re-fetches and re-caches it.

- Verify what is actually loaded by grepping the marketplace clone, not the repo.
- After editing a plugin skill, say explicitly that it needs a `/plugin` update to take effect.
- Local edits to files *inside* the marketplace clone are overwritten by the next update. Treat that
  directory as disposable.

Code that runs from a workspace checkout directly — scripts invoked by path, CLIs on `$PATH` — has no
such lag and is live as soon as it is saved. Don't assume one propagation model for both.
