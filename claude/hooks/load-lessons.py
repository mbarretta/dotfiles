#!/usr/bin/env python3
"""SessionStart hook: inject the project's .claude/lessons.md into context.

Silent no-op when the file is absent or empty, so it is safe in every project.
Caps the injected size so an unbounded lessons file cannot quietly eat context.
"""
import json
import os
import sys

CAP = 8000


def main() -> int:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    path = os.path.join(root, ".claude", "lessons.md")
    try:
        with open(path, encoding="utf-8") as fh:
            body = fh.read().strip()
    except (OSError, UnicodeDecodeError):
        return 0
    if not body:
        return 0

    note = ""
    if len(body) > CAP:
        body = body[:CAP].rstrip()
        note = f"\n\n[Truncated at {CAP} chars. Read {path} for the rest.]"

    context = (
        f"Lessons recorded for this project, from {path}. These are corrections the user has "
        f"already made — treat them as binding for this session and do not repeat the mistakes "
        f"they describe.\n\n{body}{note}"
    )
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
