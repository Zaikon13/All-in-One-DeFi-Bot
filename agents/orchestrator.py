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

**Agent Drift Detection (first increment, per Review Agent 2026-06 "Approved with Conditions", High risk)**:
- Master-driven only via new `--detect-drift` flag (condition 5: extend existing orchestrator.py, no new module).
- Uses Grok **exclusively via core/grok_client.py** to analyze drift between documented agent artifacts (SOT sections, prompt contracts, memory schema, project_context) and current implementation.
- Generates structured proposals **only** for the four high-value areas. Every proposal contains the full non-bypassable Review Gate enforcement language (condition 2).
- Strictly detection + proposals only. No application logic, no production impact (conditions 1,7).
- Minimal memory append (tiny record in plan_outcomes, high-risk documented per condition 6).
- Master authority explicit. The detector/prompt are themselves subject to future Improvement Proposer / drift runs (condition 10).
- All new code carries # Review Agent 2026-06 comments. See reviews/2026-06-XX-agent-drift-detection.md and coordinated SOT updates.

**Drift Detection v2 (per Review Agent 2026-06 "Approved with Conditions", Medium-High risk)**: Modest evolution of the above. Smarter bounded drift_context (targeted extraction + recent plan_outcomes/drift history last 5-8 with summaries for pattern awareness). 1-2 additional high-value areas (orchestrator arg parsing/mode logic vs docs; SOT cross-refs vs actual reviews/ files). Stronger prompt requirements for citations of prior runs + precise fixes. Still proposals-only, full gate, extend-existing, tiny memory (any summary high-risk per condition 6), core client only. Detector (incl. context builder) remains auditable by future runs (condition 10). See new reviews/2026-06-XX-drift-detection-v2.md and updated SOTs + the 12 conditions.

**Usage (Phase 1)**:
  python agents/orchestrator.py --task "Describe the high-level task, e.g. 'Add EOD PnL to worker and update docs'"

**Usage (Phase 2 - Master-driven only)**:
  python agents/orchestrator.py --propose-improvements

**Usage (Drift Detection - Master-driven only)**:
  python agents/orchestrator.py --detect-drift

Master then uses any plan or proposals to drive todo_write + spawn_subagent (with full persona prepended). For proposals: Review Gate is mandatory before any follow-on edit.

# Review Agent 2026-06: Phase 1 foundation + Phase 2 first scoped "Improvement Proposer" increment per "Approved with Conditions". Orchestrator assists Master (does not replace authority or bypass Review Gate). Uses existing spawn_subagent protocol and core/grok_client.py only. Memory files committed; project_context.md updates high-risk SOT-like. Proposals strictly limited to prompts + memory schema; every proposal text requires Review Agent before implementation. No autonomous action. Agent Drift Detection first inc added per Approved with Conditions (High risk): --detect-drift mode + grok_drift_detector.txt, proposals-only with full gate enforcement, minimal plan_outcomes record, coordinated SOTs. v2 modest evolution (richer bounded history, 1-2 areas, stronger citations/precision per 12 conditions). See Primary SOTs (project-awareness.md 4.6/4.7/4.8, GROK_COORDINATION.md Section 3), agents/README.md, reviews/2026-06-XX-agent-drift-detection.md, reviews/2026-06-XX-drift-detection-v2.md, and the 12 mandatory conditions.

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


# Review Agent 2026-06: New async detect_drift (Agent Drift Detection first inc).
# - Master-driven only (--detect-drift flag).
# - Builds drift_context by reading key documented artifacts (SOT agent sections, prompt contracts, memory handling, project_context) vs current code.
# - Calls Grok **exclusively** via core/grok_client.py (load_prompt + call_grok + is_valid).
# - Generates structured proposals for the four high-value areas ONLY.
# - Every proposal contains the full "REQUIRES REVIEW AGENT STEP" enforcement (condition 2).
# - NO apply logic, NO production paths, NO autonomy (conditions 1,7).
# - Minimal append to plan_outcomes (tiny record only; high-risk per condition 6; full details in printed output + reviews/).
# - Aligns with existing handoff: any real synchronization requires Master todo_write + spawn_subagent (full persona + SOTs).
# - The new prompt and this logic are subject to future Improvement Proposer / drift runs (condition 10).
async def detect_drift(context: str, memory: dict) -> str:
    """Generate gated drift detection proposals using Grok via SOT only. Master reviews output."""
    from pathlib import Path as _Path  # local alias to avoid shadowing

    # Build smarter bounded drift_context (v2: targeted extraction + recent plan_outcomes/drift history for patterns, summaries only).
    # # Review Agent 2026-06 (v2): Improved relevance filtering and history (last 5-8 relevant entries, truncated summaries; full details in printed output + reviews/).
    # History used for quality/patterns only (condition 12). No auto-apply.
    pa_path = _Path("project-awareness.md")
    pa_text = pa_path.read_text(encoding="utf-8") if pa_path.exists() else ""
    pa_excerpt = ""
    if "4.6 Phase 1" in pa_text or "4.7 Phase 2" in pa_text or "Agent Drift Detection" in pa_text:
        start = pa_text.find("### 4.6 Phase 1")
        if start == -1: start = pa_text.find("### 4.7 Phase 2")
        if start == -1: start = pa_text.find("**Agent Drift Detection")
        if start != -1:
            pa_excerpt = pa_text[start:start+2400]  # slightly more for v2 4.8 ref

    coord_path = _Path("GROK_COORDINATION.md")
    coord_text = coord_path.read_text(encoding="utf-8") if coord_path.exists() else ""
    coord_excerpt = ""
    if "Phase 2 first scoped" in coord_text or "Agent Drift Detection" in coord_text:
        idx = coord_text.find("**Phase 2 first scoped increment")
        if idx == -1: idx = coord_text.find("**Agent Drift Detection")
        if idx != -1:
            coord_excerpt = coord_text[idx:idx+1100]

    agents_path = _Path("AGENTS.md")
    agents_text = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    agents_excerpt = ""
    if "Phase 2 first scoped" in agents_text or "Agent Drift Detection" in agents_text:
        idx = agents_text.find("Phase 2 first scoped increment")
        if idx == -1: idx = agents_text.find("Agent Drift Detection")
        if idx != -1:
            agents_excerpt = agents_text[idx:idx+800]

    # Prompt contracts
    plan_prompt = _Path("prompts/grok_orchestrator_plan.txt").read_text(encoding="utf-8")[:1200] if _Path("prompts/grok_orchestrator_plan.txt").exists() else ""
    impr_prompt = _Path("prompts/grok_improvement_proposer.txt").read_text(encoding="utf-8")[:1200] if _Path("prompts/grok_improvement_proposer.txt").exists() else ""
    drift_prompt_text = _Path("prompts/grok_drift_detector.txt").read_text(encoding="utf-8")[:1200] if _Path("prompts/grok_drift_detector.txt").exists() else ""

    # Current implementation (targeted for v1 + v2 areas: memory/propose + arg parsing/modes)
    orch_text = _Path("agents/orchestrator.py").read_text(encoding="utf-8") if _Path("agents/orchestrator.py").exists() else ""
    orch_excerpt = ""
    if "plan_outcomes" in orch_text or "detect-drift" in orch_text or "argparse" in orch_text:
        idx = orch_text.find("plan_outcomes")
        if idx == -1: idx = orch_text.find("--detect-drift")
        if idx == -1: idx = orch_text.find("parser.add_argument")
        if idx != -1:
            orch_excerpt = orch_text[max(0, idx-400):idx+2200]

    proj_ctx = _Path("agents/memory/project_context.md").read_text(encoding="utf-8")[:900] if _Path("agents/memory/project_context.md").exists() else ""

    # Bounded recent history for patterns (v2; filter relevant types, small summaries only)
    recent = [r for r in memory.get("plan_outcomes", []) if r.get("type") in ("plan", "drift_detection", "improvement_proposal")][-8:]
    history_section = "=== RECENT HISTORY (plan_outcomes / prior drift for pattern detection - summaries/truncated only; full in printed + reviews/) ===\n" + json.dumps(recent, indent=2)[:900] + "\n"

    # SOT cross-ref examples + reviews/ note (v2 modest area)
    cross_ref_note = "=== SOT CROSS-REFS vs ACTUAL (v2 area; examples from SOTs like 'see reviews/2026-06-XX-...' or 'see project-awareness 4.7' vs files in reviews/ and consistency) ===\n" + " (Check for dangling refs in the DOCUMENTED excerpts above vs actual reviews/ dir contents.)\n"

    drift_ctx = (
        "=== DOCUMENTED (SOTs / prompts / project_context expectations) ===\n"
        f"project-awareness 4.6/4.7/4.8 (agent system + Phase 2 + Drift v1/v2):\n{pa_excerpt}\n\n"
        f"GROK_COORDINATION Sec 3 (Phase 2 + Drift):\n{coord_excerpt}\n\n"
        f"AGENTS.md Current Focus (Phase 2 + Drift):\n{agents_excerpt}\n\n"
        f"grok_orchestrator_plan.txt contract (excerpt):\n{plan_prompt}\n\n"
        f"grok_improvement_proposer.txt contract (excerpt):\n{impr_prompt}\n\n"
        f"grok_drift_detector.txt contract (excerpt):\n{drift_prompt_text}\n\n"
        f"project_context.md (priorities):\n{proj_ctx}\n\n"
        "=== CURRENT IMPLEMENTATION (orchestrator.py memory/propose/arg parsing + modes for v1/v2) ===\n"
        f"{orch_excerpt}\n\n"
        f"{history_section}\n"
        f"{cross_ref_note}\n"
        "=== MEMORY SCHEMA (from agent_memory.json notes) ===\n"
        f"{memory.get('notes','')[:700]}\n"
    )

    # Dedicated drift detector prompt (evolved for v2). load_prompt via core/grok_client SOT.
    # # Review Agent 2026-06 (v2): Contract updated for history/patterns (quality only), stronger citations/precision, modest areas. Full gate preserved. Detector subject to system (condition 10).
    drift_prompt = load_prompt(
        "grok_drift_detector.txt",
        context=context[:1200],
        current_memory=json.dumps(memory, indent=2)[:700],
        drift_context=drift_ctx
    )

    result = await call_grok(drift_prompt, timeout=45.0)
    if is_valid_grok_response(result):
        return result.strip()
    return f"[Grok drift detection unavailable or low quality per is_valid_grok_response. Raw: {result[:200]}]"


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
    # Drift Detection flag (first inc per Review 2026-06 Approved with Conditions, High risk; condition 5: extend existing)
    parser.add_argument("--detect-drift", action="store_true",
                        help="Agent Drift Detection (first inc): detect drift between SOT agent sections / prompt contracts / memory schema / project_context vs current orchestrator + prompts + memory code. Generates gated proposals only (full Review Gate enforcement in output). Master-driven only. No auto-apply.")
    args = parser.parse_args()

    active_modes = sum([bool(args.propose_improvements), bool(args.detect_drift), bool(args.task)])
    if active_modes > 1:
        print("Error: Use only one of --task, --propose-improvements, or --detect-drift (mutually exclusive).")
        sys.exit(2)
    if active_modes == 0:
        print("Error: Provide --task (Phase 1), --propose-improvements (Phase 2), or --detect-drift (see --help).")
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

    if args.detect_drift:
        # Review Agent 2026-06: Drift Detection first inc path (High risk). Strictly detection + proposals.
        # Builds context from actual files vs documented. Output contains full Review Gate (condition 2).
        # Master must still open todo_write and follow handoff for any actual edits (condition 2).
        # No production logic touched. Memory append is tiny record only (condition 6).
        print("\n=== Agent Drift Detection (first inc, Gated, Master-driven only) ===")
        print("Building drift_context from SOTs/prompts/memory docs vs current implementation; using Grok via core/grok_client.py SOT...")
        proposals = await detect_drift(context, memory)

        print("\n=== Generated Drift Proposals (Master reviews; NO auto-apply) ===")
        print(proposals)

        print("\n=== Master Next Steps (MANDATORY - conditions 2,4,8) ===")
        print("1. Proposals above are for your review ONLY. Every proposal text requires Review Agent before implementation.")
        print("2. To pursue: Open todo_write (merge:false) with review-gate item, spawn Review Agent (full persona + Primary SOTs + proposal text + this run + reviews/2026-06-XX-agent-drift-detection.md), address output.")
        print("3. Only after Review + Master address: use Code Agent for coordinated SOT updates (condition 9).")
        print("4. Never apply proposals directly. This mode stores only a minimal run record in plan_outcomes (full text in printed output + reviews/).")
        print("5. Commit referencing Review Agent 2026-06 decision. The detector itself is subject to the system (condition 10).")

        # Minimal memory append (condition 6: tiny record only; prefer printed output + reviews/ for full details)
        # # Review Agent 2026-06 (v2): drift run record + tiny bounded summary (high-risk). Full proposals in printed + reviews/.
        from datetime import datetime, timezone
        drift_record = {
            "type": "drift_detection",
            "time": datetime.now(timezone.utc).isoformat(),
            "focus": "SOT agent sections / prompt contracts / memory schema / project_context + v2 modest areas (arg parsing, SOT cross-refs) vs impl",
            "note": "See printed proposals above. Requires Review Agent + Master todo_write + handoff before any edit. # Review Agent 2026-06"
        }
        # tiny summary (v2, bounded)
        drift_record["summary"] = "v2 drift proposals generated (see full printed output + reviews/2026-06-XX-drift-detection-v2.md for details)."
        memory.setdefault("plan_outcomes", []).append(drift_record)
        if len(memory["plan_outcomes"]) > 12:
            memory["plan_outcomes"] = memory["plan_outcomes"][-12:]
        save_agent_memory(memory)
        print("\nMinimal drift run record (with tiny summary) appended to plan_outcomes (review before commit). Run complete.")
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
# Agent Drift Detection first inc (High risk): added --detect-drift + grok_drift_detector.txt per Approved with Conditions. Proposals-only with full gate enforcement in output, minimal plan_outcomes record, extend-existing (no new module), core client only. Detector subject to system (condition 10). Coordinated SOTs + new reviews/ file.
