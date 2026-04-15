# Copilot Instructions for Futoshiki A\* Project

## Project context

- Language: Python >= 3.7
- Goal: solve Futoshiki puzzles with A\* search and heuristics.
- Main source of truth: src/
- Documents: docs/ (PDF assignment/reference files)

## Brain orchestration (must follow every session)

- This file is the project brain and has highest priority.
- On every new session, read these files in order:
  1.  .github/copilot-instructions.md
  2.  .copilot/rules/hard-rules.md
  3.  .copilot/rules/README.md
  4.  .copilot/agents/README.md
  5.  .copilot/rules/architecture.md
  6.  .copilot/rules/data-contracts.md
  7.  .copilot/rules/solver-guidance.md
  8.  .copilot/rules/fetching-dependencies.md
  9.  .copilot/rules/validation-checklist.md
  10. .copilot/copilot-memory.md
  11. .copilot/progress-tracker.md
- If any detail conflicts with this file, this file wins.

## Rule ownership

- Detailed implementation rules are maintained only in .copilot/rules/\*.md.
- This brain file should not duplicate detailed content from rules files.
- Progress details are maintained only in .copilot/progress-tracker.md.

## Hard mandatory rules (must obey)

- Hard rules are defined only in .copilot/rules/hard-rules.md.
- Do not duplicate hard-rule text in other files; always enforce that file.

## Working rules for the agent

- Prefer edits in src/ unless explicitly asked otherwise.
- Keep Python 3.7+ compatibility.
- Preserve current module names and project structure.
- Keep changes incremental and testable; avoid monolithic rewrites.
- Use concise comments only where logic is non-obvious.
- Before coding, load memory and progress notes from .copilot/copilot-memory.md and .copilot/progress-tracker.md.
- After coding, update .copilot/copilot-memory.md and .copilot/progress-tracker.md with meaningful changes.

## Session maintenance

- Keep .copilot/rules/\*.md as the only place for detailed rules.
- Keep .copilot/progress-tracker.md as the only place for Done/In Progress/Next.
- Keep .copilot/copilot-memory.md concise and decision-focused.
