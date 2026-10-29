# Working habits

- **Confirm the target before investigating.** When a report names a symptom but no project — "the
  CI failure", "the test that broke", "the deploy" — ask which one, or sweep for the symptom first.
  The working directory is where the session happened to start, not a statement of what the user is
  working on. Signals that the cwd is not the target: a sibling project with uncommitted changes or
  a recently touched plan, or the cwd project having no failures at all.

- **Re-read before editing anything the user may have touched.** Deliverable docs, plans, and prose
  are often hand-edited between turns, and their version is canonical. Anchor edits on the live text
  and make surgical changes — never rewrite a file wholesale, never "clean up" or restore your own
  earlier phrasing over theirs. If one of their edits creates a factual problem, flag it rather than
  silently reverting it.

- **Encode rules where they will actually load.** A correction saved only to memory is absent from
  headless and scheduled runs, where only skill and reference files are in context. If a rule
  governs a skill's behavior, put it in that skill's files and leave memory as a pointer at most.

- **Changes go in the real code, not one-off scripts.** Use throwaway scripts for diagnosis and
  verification only. When asked to change behavior, change the thing that ships.

- **Working artifacts go in a dedicated directory.** Screenshots, mockups, exploratory HTML, palette
  previews, and scratch output belong in a purpose-named directory, never loose at the repo root
  where they clutter `git status` and pollute the project listing. If a tool defaults to the root,
  override the output path explicitly.

- **Show the diff itself when asking for approval.** Tool output is not reliably visible to the
  user, so a diff printed by a Bash call has not been shown. Paste the raw unified diff into the
  reply in a ```diff fence before the approval question. A prose summary of the changes is a
  companion to the diff, never a substitute for it.

- **Slack text the user will paste uses `[text](url)` links.** Slack's composer takes standard
  Markdown links; `<url|text>` is the API's mrkdwn format, so don't use it. Put the text in a code
  block so the raw link syntax survives the terminal's Markdown rendering when copied.

- **Size each subagent's model to its task.** Before spawning, pick the lightest model that can do
  the job without a noticeable drop in quality, and set it with the Agent tool's `model` parameter:
  `haiku` for short mechanical work whose output is verified afterwards (moving files, simple
  lookups, copying a few short values), never for transcribing long or many values into a tool call:
  on 40-60-row Sheet ranges it dropped rows and shifted cells (2026-10-27), so use `sonnet` there, in ranges of at most 10 rows, because Sonnet too miscounted a 31-row range of repeated text and reported it correct, and verify every writer's output with a read-back; `sonnet` for bounded research and checks against a
  written brief (citation checks, per-item evidence research, sweeps), and the session's own model
  only for open-ended judgment, legal or contractual wording, or evidence that conflicts. The goal
  is lower cost and faster turnaround at the same quality (user, 2026-10-27). A fork always
  inherits the parent model.
