---
paths:
  - "**/*.py"
---

# Stale bytecode on same-size edits

CPython invalidates `.pyc` files on source **mtime at whole-second resolution, plus size**. So an
edit that does not change the file's size — flipping a one-character constant, `= 3` to `= 6` —
combined with a fast mutate → test → restore cycle can write the file twice inside one clock second.
The restored source then validates a `.pyc` compiled from the *mutated* version, and the test suite
reports a failure the source does not contain.

`python -B` does not help: it suppresses *writing* bytecode, not reading a stale one. Block-sized
edits escape this only by luck, which is why it bites on constants specifically.

**When a probe result contradicts the source, suspect this before suspecting the code.** Clear caches
between probes:

```bash
find . -name '__pycache__' -type d -not -path './.venv/*' -exec rm -rf {} +
```

Or run the probe against a `/tmp` copy with `PYTHONDONTWRITEBYTECODE=1`. Confirm what is actually
loaded with `python -c "import mod; print(mod.CONST)"` and compare it to the file's text.
