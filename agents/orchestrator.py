#!/usr/bin/env python3
"""
agents/orchestrator.py - Phase 1 Orchestrator (assists Master Agent)

Core Mission: Help the Master (Grok) load shared context/memory and use Grok (via SOT) to suggest Sub-Agent plans for tasks.
This is a **tool that assists the Master**, not a replacement. Grok (Master) retains final decision authority.

**Phase 1 Scope (Foundation Only - per Review Agent 2026-06 Approved with Conditions, High Risk)**:
- Script-based: invoke manually (python agents/orchestrator.py --task "...") or via scheduled skills/Execute Agent.
- No long-running autonomous daemon, no feedback loops, no self-improvement, no deep autonomy.
- Loads committed memory/ files.
- Uses **core/grok_client.py exclusively** for any Grok planning calls (SOT: load_prompt + call_grok + is_valid_grok_response).
- References the **existing handoff protocol** (project-awareness.md 4.2): Master opens todo_write, prepends full persona from agents/personas/, includes Primary SOT refs + current todo context, then calls spawn_subagent.
- For high-risk work: explicitly recommends/requires spawning Review Agent persona first or Master running the gate.
- Does **not** invent new spawning; uses existing spawn_subagent mechanism.
- Updates simple memory state after run (Master reviews/approves changes).

**Usage**:
  python agents/orchestrator.py --task "Describe the high-level task, e.g. 'Add EOD PnL to worker and update docs'"

Master then uses the plan to drive todo_write + spawn_subagent (with full persona prepended).

# Review Agent 2026-06: Phase 1 foundation implementation per "Approved with Conditions (High Risk)". Orchestrator assists Master (does not replace authority or bypass Review Gate). Uses existing spawn_subagent protocol and core/grok_client.py only. Memory files committed; project_context.md updates are high-risk SOT-like. Start simple/script. No new SOT file. Focused on foundation. All new code has traceability. See agents/README.md, Primary SOTs (especially project-awareness.md Section 4 and GROK_COORDINATION.md Section 3), and reviews/2026-06-XX-orchestrator-phase1.md.

See:
- agents/README.md (Master-Orchestrator relationship)
- project-awareness.md (full Sub-Agent + Review Gate protocol)
- GROK_COORDINATION.md (agent section)
- AGENTS.md
"""

import argparse
import asyncio
import json
from pathlib import Path
import sys

# Ensure core/ is importable (SOT for Grok)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.grok_client import load_prompt, call_grok, is_valid_grok_response  # noqa: E402

MEMORY_DIR = Path(__file__).parent / "memory"
PROJECT_CONTEXT_PATH = MEMORY_DIR / "project_context.md"
AGENT_MEMORY_PATH = MEMORY_DIR / "agent_memory.json"

def load_shared_memory() -> tuple[str, dict]:
    """Load committed project context (SOT-like) and agent memory. Master must review context changes."""
    with open(PROJECT_CONTEXT_PATH, "r", encoding="utf-8") as f:
        context = f.read()
    with open(AGENT_MEMORY_PATH, "r", encoding="utf-8") as f:
        memory = json.load(f)
    return context, memory

def save_agent_memory(memory: dict) -> None:
    """Persist simple state. Changes to project_context.md (not this) are high-risk SOT-like."""
    with open(AGENT_MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)

async def get_grok_plan(task_description: str, context: str, memory: dict) -> str:
    """
    Use Grok (via core/grok_client.py SOT only) to suggest a Sub-Agent plan.
    Plan must respect: Review Gate first for high-risk, existing spawn_subagent + full personas, todo_write, Master authority.
    """
    # Review Agent 2026-06: Switched to dedicated prompts/grok_orchestrator_plan.txt (per Approved with Conditions).
    # Minimal change only: use load_prompt with the new contract-style prompt. No logic changes.
    # Planning prompt now enforces Phase 1 rules and includes Meta Notes for future self-improvement readiness (without consuming them here).
    planning_prompt = load_prompt(
        "grok_orchestrator_plan.txt",
        task=task_description,
        context=context[:2000],
        memory=json.dumps(memory, indent=2)[:800]
    )

    result = await call_grok(planning_prompt, timeout=45.0)
    if is_valid_grok_response(result):
        return result.strip()
    return f"[Grok planning unavailable or low quality per is_valid_grok_response. Raw: {result[:200]}]"

def update_memory_after_run(memory: dict, task: str) -> None:
    """Minimal state update. Master reviews before committing memory changes."""
    from datetime import datetime, timezone
    memory["last_orchestrator_run"] = datetime.now(timezone.utc).isoformat()
    memory["last_task"] = task
    if "agent_state" not in memory:
        memory["agent_state"] = {}
    # Simple tracking (expand later if needed)
    memory.setdefault("run_history", []).append({"task": task, "time": memory["last_orchestrator_run"]})
    if len(memory["run_history"]) > 20:
        memory["run_history"] = memory["run_history"][-20:]

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1 Orchestrator - assists Master Agent with context loading and Grok-assisted Sub-Agent planning. "
                    "Master retains authority and must enforce Review Gate. Uses existing spawn_subagent protocol."
    )
    parser.add_argument("--task", required=True, help="High-level description of the task to plan Sub-Agents for.")
    args = parser.parse_args()

    print("=== Orchestrator (Phase 1) - Assisting Master Agent ===")
    print("Loading committed shared memory (project_context.md is SOT-like; updates require Review Gate)...")
    context, memory = load_shared_memory()
    print(f"  Context length: {len(context)} chars")
    print(f"  Memory version: {memory.get('version')}, last run: {memory.get('last_orchestrator_run')}")

    print("\nUsing Grok (exclusively via core/grok_client.py SOT) to generate plan...")
    plan = await get_grok_plan(args.task, context, memory)

    print("\n=== Grok-Assisted Plan (Master decides and acts) ===")
    print(plan)

    print("\n=== Master Next Steps (per protocol) ===")
    print("1. Review the plan above.")
    print("2. If high-risk: Open todo_write (merge:false) including 'Spawn Review' step, prepare full Review persona prompt (prepend agents/personas/review-agent.md + SOTs + todo), call spawn_subagent.")
    print("3. After Review output, address points, then (if approved) spawn Code/others using full personas + SOT refs.")
    print("4. Use Execute Agent for any commands. Capture full output.")
    print("5. Update memory only after your review (this script did a minimal update).")
    print("6. Commit with reference to this run and Review Agent 2026-06.")

    update_memory_after_run(memory, args.task)
    save_agent_memory(memory)
    print("\nMemory state lightly updated (review before commit). Run complete.")

if __name__ == "__main__":
    asyncio.run(main())

# Review Agent 2026-06: Phase 1 orchestrator.py per Approved with Conditions (High Risk).
# - Assists Master (does not replace authority or bypass Review Gate).
# - Uses core/grok_client.py exclusively for Grok calls.
# - References (does not replace) existing spawn_subagent + full personas + todo_write + SOT handoff protocol.
# - Memory loaded from committed files; project_context.md updates documented as high-risk SOT-like.
# - Script only (manual/scheduled); foundation scope, no autonomy.
# - All new code has traceability. See agents/README.md and Primary SOTs for full requirements.
# - Master must still open todos, spawn Review for high-risk, read/address outputs.
