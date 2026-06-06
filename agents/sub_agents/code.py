"""
agents/sub_agents/code.py - Thin wrapper / convenience for Phase 1.

Purpose: Provides a simple interface for the Orchestrator (or Master) to prepare Code Agent context.
This does **not** replace the official spawn_subagent mechanism or personas.

Usage (Master-driven, only after Review approval):
- Load full persona: open("agents/personas/code-agent.md").read()
- Prepend to prompt along with Primary SOT refs + current todo_write context + explicit "Review Agent [date] output received. Recommendation: Approve... Key points addressed: ..."
- Call spawn_subagent.
- Master must have read the Review output in full.

See project-awareness.md Section 4.2 and code-agent.md (strict preconditions for Review Gate).

# Review Agent 2026-06: Phase 1 wrapper per Approved with Conditions. Code Agent only after explicit Review approval. Use existing spawn_subagent + full persona. No new spawning layer. Master retains authority.
"""

from pathlib import Path

PERSONA_PATH = Path(__file__).parent.parent / "personas" / "code-agent.md"

def get_persona_text() -> str:
    with open(PERSONA_PATH, "r", encoding="utf-8") as f:
        return f.read()

def prepare_code_prompt(task_description: str, current_todo: str, sot_refs: str, review_summary: str) -> str:
    """Helper to build prompt for Code Agent (only after Review)."""
    persona = get_persona_text()
    return f"{persona}\n\nTask: {task_description}\n\nCurrent todo context:\n{current_todo}\n\nPrimary SOTs referenced:\n{sot_refs}\n\nReview Gate status: {review_summary}\n\nExact scope: Implement the smallest correct change after Review."

# Master usage example (after Review):
# prompt = prepare_code_prompt(...)
# spawn_subagent(..., prompt=prompt)
