#!/usr/bin/env python3
"""
agents/orchestrator.py - Phase 1 Orchestrator (assists Master Agent) + Phase 2 first scoped increment (Improvement Proposer)

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

**Phase 2 First Scoped Increment (Gated Feedback Loop + Self-Improvement Readiness - per Review Agent 2026-06 "Approved with Conditions")**:
- Master-driven only via new `--propose-improvements` mode (condition 10: extend existing orchestrator.py rather than new component).
- Reads past Meta Notes + simple outcome data from memory (run_history, notes, last_task, plan_outcomes).
- Uses Grok **exclusively via core/grok_client.py** to generate structured proposals **only** for prompts (starting with grok_orchestrator_plan.txt) and memory schema.
- **Every generated proposal contains explicit Review Gate enforcement language** (impossible to act on without Review Agent + Master todo_write + full handoff).
- Proposals only. No execution, no auto-apply, no changes to worker.py/core/app/workflows/production logic (conditions 1,8).
- Minimal memory schema evolution allowed (plan_outcomes array) — documented as high-risk (condition 7); full proposals live in printed output + reviews/ file.
- Master authority explicit in comments, prompt contract, and SOT updates.
- All new code carries # Review Agent 2026-06 comments. See reviews/2026-06-XX-phase2-feedback-loop.md.

**Phase 2 richer-context increment (higher-quality proposals)**: 
- plan_outcomes now carries tiny `meta_summary` (bounded excerpt of '## Meta Notes for Future Improvement') for "plan" entries.
- propose_improvements passes last ~8 outcomes + meta_summary so Grok can detect patterns and produce specific, citable, actionable proposals.
- Still proposals-only, Review Gate enforcement identical, memory changes minimal/high-risk documented. See new review file and updated 4.7.

**Usage (Phase 1)**:
  python agents/orchestrator.py --task "Describe the high-level task, e.g. 'Add EOD PnL to worker and update docs'"

**Usage (Phase 2 - Master-driven only)**:
  python agents/orchestrator.py --propose-improvements

Master then uses any plan or proposals to drive todo_write + spawn_subagent (with full persona prepended). For proposals: Review Gate is mandatory before any follow-on edit.

# Review Agent 2026-06: Phase 1 foundation + Phase 2 first scoped "Improvement Proposer" increment per "Approved with Conditions". Orchestrator assists Master (does not replace authority or bypass Review Gate). Uses existing spawn_subagent protocol and core/grok_client.py only. Memory files committed; project_context.md updates high-risk SOT-like. Proposals strictly limited to prompts + memory schema; every proposal text requires Review Agent before implementation. No autonomous action. See Primary SOTs (project-awareness.md 4.6/4.7, GROK_COORDINATION.md Section 3), agents/README.md, and reviews/2026-06-XX-phase2-feedback-loop.md.

See:
- agents/README.md (Master-Orchestrator relationship)
- project-awareness.md (full Sub-Agent + Review Gate protocol + 4.7)
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


# Review Agent 2026-06: New async propose_improvements (Phase 2 first scoped inc - "Improvement Proposer").
# - Master-driven only (--propose-improvements flag).
# - Reads Meta Notes + simple outcomes from memory (run_history, notes, last_task, plan_outcomes).
# - Calls Grok **exclusively** via core/grok_client.py (load_prompt + call_grok + is_valid).
# - Generates structured proposals for prompts (grok_orchestrator_plan.txt first) + minimal memory schema ONLY.
# - The prompt contract forces explicit "REQUIRES REVIEW AGENT STEP" language into every proposal (condition 2).
# - NO apply logic, NO changes to production paths (worker/core/app), NO autonomy (conditions 1,8).
# - Minimal append to plan_outcomes in memory (full proposal text lives in printed output + reviews/ file).
# - Aligns with existing handoff: any real follow-on work requires Master todo_write + spawn_subagent (full persona + SOTs).

# Review Agent 2026-06 (next inc): Helper for bounded meta notes excerpt (high-risk memory evolution per condition 6).
# Only tiny excerpts (~450 chars) of the "## Meta Notes for Future Improvement" section are stored in plan_outcomes.
# Full content remains in printed output + reviews/. Never used for auto-apply.
def _extract_meta_notes_excerpt(plan_text: str, max_chars: int = 450) -> str:
    if not plan_text or not isinstance(plan_text, str):
        return ""
    marker = "## Meta Notes for Future Improvement"
    idx = plan_text.find(marker)
    if idx == -1:
        return ""
    excerpt = plan_text[idx:idx + max_chars].strip()
    # Keep clean: cut at last complete line if possible
    last_nl = excerpt.rfind("\n")
    if last_nl > 100:
        excerpt = excerpt[:last_nl].strip()
    return excerpt or ""


async def propose_improvements(context: str, memory: dict) -> str:
    """Generate gated improvement proposals (prompts + memory schema) using Grok via SOT only. Master reviews output."""
    from datetime import datetime, timezone
    # Build richer "past Meta Notes + outcome data" context (this inc: last 5-8 plan_outcomes + any meta_summary).
    # # Review Agent 2026-06: Richer but still bounded history for higher-quality, specific, pattern-aware proposals.
    # Full prior Meta Notes live in stdout/reviews/; we only pass tiny excerpts via meta_summary in plan_outcomes.
    recent_history = memory.get("run_history", [])[-5:]
    plan_outcomes = memory.get("plan_outcomes", [])[-8:]  # modestly richer per scoped MVP
    meta_context = (
        f"Last orchestrator task: {memory.get('last_task', 'N/A')}\n"
        f"Recent run history (task + time): {json.dumps(recent_history, indent=2)}\n"
        f"Recent plan_outcomes (with meta_summary when present for prior plans): {json.dumps(plan_outcomes, indent=2)}\n"
        f"Memory notes: {memory.get('notes', '')[:500]}\n"
        "Note: meta_summary (if present) contains a short bounded excerpt of the '## Meta Notes for Future Improvement' section from that run's plan output. "
        "Use it + run timestamps to detect patterns (e.g. repeated weak Meta Notes quality, missing context). "
        "Master may still supply additional full excerpts when invoking. This increment improves specificity while remaining proposals-only."
    )

    # Use dedicated focused prompt (new for Phase 2 inc). load_prompt via core/grok_client SOT.
    # # Review Agent 2026-06: The prompt (grok_improvement_proposer.txt) is contract-enforced to embed Review Gate language in proposals and limit scope ruthlessly.
    improvement_prompt = load_prompt(
        "grok_improvement_proposer.txt",
        context=context[:1800],
        current_memory=json.dumps(memory, indent=2)[:900],
        meta_notes_context=meta_context
    )

    result = await call_grok(improvement_prompt, timeout=45.0)
    if is_valid_grok_response(result):
        return result.strip()
    return f"[Grok improvement proposal generation unavailable or low quality per is_valid_grok_response. Raw: {result[:200]}]"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1 Orchestrator (+ Phase 2 gated Improvement Proposer) - assists Master Agent. "
                    "Master retains authority and must enforce Review Gate. Uses existing spawn_subagent protocol + core/grok_client.py only."
    )
    # Phase 1 flag (existing)
    parser.add_argument("--task", help="High-level description of the task to plan Sub-Agents for (Phase 1).")
    # Phase 2 flag (condition 10 + richer context inc: extend existing orchestrator; Master-driven only)
    parser.add_argument("--propose-improvements", action="store_true",
                        help="Phase 2: read past Meta Notes + outcomes (incl. tiny meta_summary excerpts) from memory and generate gated proposals for prompts (grok_orchestrator_plan.txt) and memory schema only. Richer history for more specific/actionable proposals. Proposals-only (no apply). Review Gate language embedded. Master-driven only.")
    args = parser.parse_args()

    if args.propose_improvements and args.task:
        print("Error: Use either --task (Phase 1 planning) or --propose-improvements (Phase 2 proposals), not both.")
        sys.exit(2)
    if not args.propose_improvements and not args.task:
        print("Error: Provide --task for Phase 1 or --propose-improvements for Phase 2 first inc (see --help).")
        sys.exit(2)

    print("=== Orchestrator - Assisting Master Agent ===")
    print("Loading committed shared memory (project_context.md is SOT-like; updates require Review Gate)...")
    context, memory = load_shared_memory()
    print(f"  Context length: {len(context)} chars")
    print(f"  Memory version: {memory.get('version')}, last run: {memory.get('last_orchestrator_run')}")

    if args.propose_improvements:
        # Review Agent 2026-06: Phase 2 first inc path. Strictly proposals for prompts + memory schema.
        # No production logic touched. Output will contain explicit Review Gate enforcement (per prompt contract).
        # Master must still open todo_write and follow handoff for any actual edits (condition 2).
        print("\n=== Phase 2 First Increment: Improvement Proposer (Gated, Master-driven only) ===")
        print("Reading past Meta Notes + simple outcome data from memory; using Grok via core/grok_client.py SOT...")
        proposals = await propose_improvements(context, memory)

        print("\n=== Generated Improvement Proposals (Master reviews; NO auto-apply) ===")
        print(proposals)

        print("\n=== Master Next Steps (MANDATORY - conditions 2,4,8) ===")
        print("1. Proposals above are for your review ONLY. Every proposal text requires Review Agent before implementation.")
        print("2. To pursue: Open todo_write (merge:false) with review-gate item, spawn Review Agent (full persona + Primary SOTs + proposal text + this run), address output.")
        print("3. Only after Review + Master address: use Code Agent for coordinated SOT updates. Reference reviews/2026-06-XX-phase2-feedback-loop.md.")
        print("4. Never apply proposals directly. This mode stores only a minimal run record in plan_outcomes (full text in printed output + reviews/).")
        print("5. Commit referencing Review Agent 2026-06 decision.")

        # Minimal memory append (condition 7: prefer plan output + simple appends; do not store full proposals here)
        # Review Agent 2026-06: proposal run record only (no meta content needed beyond the printed proposals).
        from datetime import datetime, timezone
        memory.setdefault("plan_outcomes", []).append({
            "type": "improvement_proposal",
            "time": datetime.now(timezone.utc).isoformat(),
            "focus": "prompts (grok_orchestrator_plan.txt) + memory_schema",
            "note": "See printed proposals above. Requires Review Agent + Master todo_write + handoff before any edit. # Review Agent 2026-06"
        })
        if len(memory["plan_outcomes"]) > 10:
            memory["plan_outcomes"] = memory["plan_outcomes"][-10:]
        save_agent_memory(memory)
        print("\nMinimal proposal run record appended to plan_outcomes (review before commit). Run complete.")
        return

    # Existing Phase 1 path (unchanged behavior except updated prints + memory append for outcomes)
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
    # Review Agent 2026-06 (richer context inc): append plan outcome + tiny meta_summary excerpt (high-risk per condition 6).
    # Only the bounded excerpt of '## Meta Notes for Future Improvement' is captured here so future --propose-improvements
    # runs can detect patterns. Full Meta Notes text lives in the printed plan + reviews/ files. No auto-apply.
    from datetime import datetime, timezone
    meta_excerpt = _extract_meta_notes_excerpt(plan)
    plan_outcome = {
        "type": "plan",
        "time": datetime.now(timezone.utc).isoformat(),
        "task": args.task,
        "note": "Phase 1 plan run. See meta_summary for bounded excerpt of '## Meta Notes for Future Improvement'. Full text in printed output + reviews/.",
    }
    if meta_excerpt:
        plan_outcome["meta_summary"] = meta_excerpt
    memory.setdefault("plan_outcomes", []).append(plan_outcome)
    if len(memory["plan_outcomes"]) > 10:
        memory["plan_outcomes"] = memory["plan_outcomes"][-10:]
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
