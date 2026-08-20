---
paths:
  - ".github/workflows/**"
  - ".github/**/*.yml"
  - ".github/**/*.yaml"
---

# Diagnosing a log-less CI failure

**A GitHub Actions job that fails in ~3 seconds with no retrievable logs never started**, so no log
blob exists. `gh run view <id> --log-failed` returns `log not found` and the raw log API returns
`BlobNotFound`. That reads like a tooling glitch and sends you hunting through workflow YAML for a
config error that isn't there.

Confirm the signature first:

```bash
gh api repos/O/R/actions/runs/<id>/jobs \
  -q '.jobs[] | "\(.name)|\(.conclusion)|steps=\(.steps|length)"'
```

`steps=0` on every job means failure to start. The reason is only in the **check-run annotations**:

```bash
suite=$(gh api repos/O/R/actions/runs/<id> -q '.check_suite_url')
gh api "${suite}/check-runs" -q '.check_runs[].id' | while read -r id; do
  gh api "repos/O/R/check-runs/$id/annotations"
done
```

Common cause: a billing lapse. Private repos burn billed Actions minutes; public repos are free, so a
**some-repos-only** outage is explained by visibility (`gh api repos/O/R -q .private`).

## Billing forensics

- The `users/<u>/settings/billing/actions` endpoints now return **410 Gone**. The live one is
  `gh api users/<u>/settings/billing/usage`, returning per-month `usageItems` with
  `grossAmount` / `discountAmount` / `netAmount`. Filter to `netAmount > 0` for real charges.
- **Don't estimate minutes from job durations.** `runs/<id>/timing` reports `billable.total_ms: 0`
  even for runs that plainly did work, and summing `completed_at - started_at` undercounts badly
  because it misses the 10× macOS multiplier. The `usage` endpoint is authoritative.
- **Private forks bill the personal account.** A private fork with the upstream's scheduled workflows
  still active fires nightly against your own allowance, duplicating upstream runs. Check forks first
  when a personal allowance drains.

`gh workflow disable` may be refused by the permission classifier as a CI-bypass even after an
explicit grant. Hand the command to the user rather than reaching for the REST API or editing workflow
files — that circumvention is what the guardrail exists to stop.
