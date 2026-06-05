# reviews/ — Review Agent Output Archive

This directory stores full outputs from the **Mandatory Review Agent** for non-trivial changes.

## Convention
- Filename pattern: `YYYY-MM-DD-short-task-description.md`
  - Example: `2026-06-05-pnl-unification-review.md`
  - Example: `2026-06-04-grok-ci-unify-review.md`

## What to Save
- Any Review whose output is longer than a few paragraphs or contains multiple issues/guardrails.
- Master is responsible for saving the Review Agent's complete structured output here.

## How Reviews Are Used
1. Master spawns Review Agent (full persona + context + proposed change prepended).
2. Review produces the exact structured format defined in `agents/personas/review-agent.md`.
3. Master saves the output here (for long reviews).
4. Master references the review in the active `todo_write` list and in any subsequent Code Agent prompt.
5. Code changes include attribution comments: `# Review Agent 2026-06-XX: [specific guardrail]`.
6. For PRs/commits, reference the review file or date.

## Enforcement
This is part of the **Mandatory Review Gate Protocol** (see `project-awareness.md` Section 4.3).

Skipping Review is only allowed for trivial non-SOT documentation typos, and must be explicitly noted in the todo and commit message.

The Review Agent's job is to protect SOT alignment, legacy paths, safety, and project rules (small PRs, coordinated updates, green CI, UTC discipline, Telegram Markdown safety, core/ reuse, etc.).

**Master (Grok) is responsible for following this protocol in every session.** Sub-Agents (including Review) are tools; the Master orchestrates and takes final responsibility.

See:
- `project-awareness.md` (full protocol + table)
- `agents/personas/review-agent.md` (detailed checklist and required output format)
- `GROK_COORDINATION.md` (high-level Sub-Agent section)