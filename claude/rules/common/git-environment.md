# Git and shell gotchas that fail confusingly

**Commit signing is Sigstore keyless (`gitsign`).** `gpg.format = x509` with `commit.gpgsign = true`,
signing through `gitsign` rather than GPG. There is no `gitsign-credential-cache` daemon running, so:

- A commit can **block on an OIDC browser tab**. If `git commit` hangs with no output, that is why —
  hand the command to the user (prefix `!` so they can complete the flow) rather than waiting on it
  or retrying.
- Signing needs network access to `oauth2.sigstore.dev`. In a sandboxed or offline context the
  failure surfaces as a **TLS certificate error**, not as a signing error, which reads like a broken
  toolchain. Retry with network access rather than reaching for `--no-gpg-sign`, which silently
  changes commit hygiene.

**Never pipe a command whose exit status you depend on.** `git merge ... | tail` returns the exit
status of `tail`, so a failed merge looks like success and the rest of a compound chain proceeds on a
broken tree. This has caused a bad wave consolidation. Capture output to a variable or a file and
check the status separately:

```bash
if out=$(git merge --no-ff "$branch" -m "$msg" 2>&1); then ... else ... fi
```

The same applies to any `cmd | head`, `cmd | grep`, or `cmd | tee` inside an `&&` chain. And
`PIPESTATUS` is **not** the escape hatch — see below; it is empty here, so reaching for it turns a
violation of this rule into a silently unverified claim.

**The shell is zsh 5.9 — there is no bash** (`BASH_VERSION` is unset). Bashisms mostly fail
*silently*, returning a wrong answer with a zero exit status, which is what makes them worse than a
crash:

| Bashism | zsh reality |
| --- | --- |
| `${PIPESTATUS[0]}` | Empty. zsh spells it `$pipestatus` and **1-indexes** it: `${pipestatus[1]}`. |
| `${arr[0]}` | Empty. Arrays start at 1 — `${arr[1]}` is the first element. |
| `for w in $unquoted` | Does **not** word-split; the whole value arrives as one word. Force it with `${=v}`. |
| `mapfile`, `readarray`, `shopt` | Not builtins. |
| `${v,,}` / `${v^^}` | Hard `bad substitution` that aborts the rest of the command. Use `${(L)v}` / `${(U)v}`. |

Only the last one is loud. Prefer POSIX-portable constructs, and when a result feeds a claim you are
about to make, verify it a second way rather than trusting one expansion.
