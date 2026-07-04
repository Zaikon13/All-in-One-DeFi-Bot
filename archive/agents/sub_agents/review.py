"""
agents/sub_agents/review.py - Thin wrapper / convenience for Phase 1.

Purpose: Provides a simple interface for the Orchestrator (or Master) to prepare Review Agent context.
This does **not** replace the official spawn_subagent mechanism or personas.

Usage (Master-driven):
- Load full persona: open("agents/personas/review-agent.md").read()
- Prepend to prompt along with Primary SOT refs (GROK_COORDINATION.md etc.) + current todo_write context.
- Call spawn_subagent(subagent_type="general-purpose" or appropriate, prompt=full_prompt)
- Master must read and address output before any high-risk action.

See project-awareness.md Section 4.2 (Handoff Protocol) and 4.3 (Review Gate).
Orchestrator assists with planning but Master executes the spawn and enforces the gate.

# Review Agent 2026-06: Phase 1 wrapper per Approved with Conditions. Does not bypass Review Gate or Master authority. Use existing spawn_subagent + full persona. No new spawning layer invented.
"""

from pathlib import Path

PERSONA_PATH = Path(__file__).parent.parent / "personas" / "review-agent.md"

def get_persona_text() -> str:
    """Return the full Review Agent persona text for prepending to spawn_subagent prompts."""
    with open(PERSONA_PATH, "r", encoding="utf-8") as f:
        return f.read()

def prepare_review_prompt(task_description: str, current_todo: str, sot_refs: str) -> str:
    """Helper to build a prompt for spawning Review (Master still calls spawn_subagent)."""
    persona = get_persona_text()
    return f"{persona}\n\nTask: {task_description}\n\nCurrent todo context:\n{current_todo}\n\nPrimary SOTs referenced in this session:\n{sot_refs}\n\nExact scope: Review the proposed change before any implementation."

# Example (Master would use this output with spawn_subagent):
# prompt = prepare_review_prompt(...)
# Then: spawn_subagent(..., prompt=prompt)  # Master calls the tool
