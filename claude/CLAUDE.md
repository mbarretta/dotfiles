# Workflow

## 1. Plan Mode Default
- Plan when the solution's shape is open: architecture, multi-module changes, an ask with more than one reading. Step count isn't the test.
- Plan the verification too: decide up front what evidence proves it works.
- If a task goes sideways, stop and re-plan.

## 2. Subagent Strategy
- Delegate read-heavy work where you need only the conclusion: pattern sweeps, unfamiliar-code surveys, independent investigations. Launch independent agents in one message so they run in parallel.
- Don't delegate what one grep or a known-file read answers.
- One concern per agent; ask for findings with `file:line`, not transcripts.
- Never delegate a search and also run it yourself.

## 3. Self-Improvement Loop
- After ANY correction: append the preventing rule to the project's `lessons.md` — the rule, not the story. It lives in the project's vault artifact folder, the one the `SessionStart` hook names in its injected context.
- The `SessionStart` hook injects that file automatically, headless runs included.
- Environment-wide lessons go in `~/.claude/rules/` instead — see `working-habits`.

## 4. Verification Before Done
- Diff behavior against `main` when a change is behavioral. Standard of evidence: `verification-and-claims`.

## 5. Demand Elegance
- If a fix feels hacky, re-prompt yourself: "knowing everything I know now, implement the elegant solution." Skip for simple, obvious fixes.

## 6. Autonomous Bug Fixing
- A bug report, failing test, or red CI is an unambiguous goal with an unknown cause: diagnose and fix it — no plan mode, no hand-holding. Confirm the mechanism before editing (`verification-and-claims`).
- Report what you found and changed; don't ask which obvious path to take.
- Explicit exception to §1.

# User Preferences

## Communication Style
- Use a balanced communication style: be concise, but provide key explanations when relevant

## Git Workflow
- **IMPORTANT**: Commit messages MUST be one sentence only - no multi-line descriptions or bullet points in the message body
- Follow conventional commit format when appropriate (feat:, fix:, refactor:, etc.)
- PR bodies follow the same rules: 2-4 sentences covering what changed, why, and the verification gate — no attribution footer, no section headers unless genuinely needed

## Planning Documents
- Plan-mode files are written to the project's `.claude/plans/`, as Claude Code requires, and are mirrored to the project's vault artifact folder automatically. Don't copy them by hand.
- **IMPORTANT**: Hand-authored specs, architecture notes, design docs, and research go straight into the `research/` subfolder of the project's vault artifact folder (the one the `SessionStart` hook names), not into `.claude/plans/`.
- Whether a project tracks `.claude/plans/` in git is still a per-project decision. Don't assume either way — follow what the project already does, and ask if it's a new directory.

## Markdown Files
- Write every paragraph, list item, and blockquote as one continuous line. Never insert a line break in the middle of a paragraph unless it meets the following conditions:
    - You're purposely creating an ASCII graphic or markdown table that needs to render with exact character counts. 
    - When linebreaks give semantic meaning: between block elements (headings, list items, table rows), inside code block/fences, and a deliberate blank line to separate paragraphs
- These preferences do not apply to inline text output in the chat

# Machine-Local Additions

@~/.claude/CLAUDE.local.md
