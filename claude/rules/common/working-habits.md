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
