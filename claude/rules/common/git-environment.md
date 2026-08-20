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

The same applies to any `cmd | head`, `cmd | grep`, or `cmd | tee` inside an `&&` chain.
