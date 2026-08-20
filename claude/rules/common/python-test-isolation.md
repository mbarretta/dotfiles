---
paths:
  - "**/*.py"
---

# When a Python test isn't testing what you think

Two mechanisms produce test results that contradict the source in front of you. Suspect both before
suspecting the code.

## Stale bytecode on same-size edits

CPython invalidates `.pyc` files on source **mtime at whole-second resolution, plus size**. An edit
that does not change the file's size — flipping a one-character constant, `= 3` to `= 6` — combined
with a fast mutate → test → restore cycle can write the file twice inside one clock second. The
restored source then validates a `.pyc` compiled from the *mutated* version, and the suite reports a
failure the source does not contain.

`python -B` does not help: it suppresses *writing* bytecode, not reading a stale one. Block-sized
edits escape this only by luck, which is why it bites on constants specifically.

```bash
find . -name '__pycache__' -type d -not -path './.venv/*' -exec rm -rf {} +
```

Or run the probe against a `/tmp` copy with `PYTHONDONTWRITEBYTECODE=1`.

## Editable installs resolve to the main checkout, not your worktree

A package pip-installed **editable** points at one checkout. Running tests inside a *git worktree* of
that repo resolves imports from the editable install — the **main** checkout's code — while
file-path-based fixtures read the worktree's files. The mixed old-code / new-assets state produces
bizarre phantom failures that exist in neither tree.

```bash
PYTHONPATH=<worktree>/src python -m pytest
```

Confirm what actually loaded, in either case:

```bash
python -c "import core.models as m; print(m.__file__)"
```

Also watch for tiers that skip silently — tests gated on an optional binary (`node`, a browser) report
as skipped, not failed, so "~49 skipped" can mean an entire parity tier never ran.
