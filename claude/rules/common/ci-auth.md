---
paths:
  - ".github/workflows/**"
  - "**/*.sts.yaml"
---

# CI authentication

**Never store long-lived credentials in CI.** Federate instead, so nothing at rest is worth stealing
and every token is short-lived and scope-bound. A stored long-lived token is an exfiltration
liability; reject one even when it is the quickest path.

- Prefer OIDC federation over a stored secret. The only value that belongs in a secret store is an
  identity *reference*, not a credential.
- For bot pushes and PRs, mint a GitHub App token per run — `octo-sts/action` with a trust policy
  under `.github/*/**.sts.yaml` — rather than holding a personal access token.
- Pin third-party actions by commit SHA, not by tag.
- **Dependabot-triggered runs read only the Dependabot secret store.** An identity present solely in
  Actions secrets fails there, silently and only on Dependabot PRs.
- **Trust-policy subjects must cover pull-request events, not just branch refs.** A subject pattern
  restricted to `ref:.*` rejects PR-triggered runs; allow both (`repo:OWNER/REPO:(ref:.*|pull_request)`).
- Auto-merge shape depends on the plan: with branch protection available, gate on protection plus a
  `pull_request`-subject policy; without it, trigger on `workflow_run` after CI success, and note the
  policy subject is then the default branch because that is where the workflow executes.
