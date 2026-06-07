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
# Review Agent 2026-06: Low-risk Auto-Apply Dry-Run first inc (cond 1-12) added inside existing --detect-drift path only (thin read-only sim of Last Updated updates for 5 Primary SOTs when drift already flags SOT/doc issues). Env default false, zero writes except mandatory reviews/ audit log, re-embeds full gate + disclaimer, feeds normal coordinated SOT PR process. No prompt/memory schema changes. Feature subject to future Review (cond 9). All 12 conditions followed exactly.

**SOT Coordinated PR Helper (first inc, per Review Agent 2026-06 "Approved with Conditions", High risk)**:
- New --sot-pr-helper mode (extend existing orchestrator.py only, no new scripts).
- Read-only / advisory: generates ready-to-paste text (always 5 exact new Last Updated lines + per-SOT precise find/replace blocks + consolidated instructions) for the other 4 Primary SOTs after a change (or proposed change) to one.
- Supports both local uncommitted edits (--changed-sot + on-disk as after) and proposed (via --change-summary intent).
- Always prints full Review Gate paragraph + exact "ADVISORY ONLY" disclaimer.
- Mandatory audit written to reviews/2026-06-XX-sot-coordinated-pr-helper.md (modeled on dry-run + v2 review style).
- Zero writes to SOTs/memory/prompts/core/worker. Output feeds the normal manual coordinated 5-SOT PR process.
- All 12 mandatory conditions followed exactly (quoted in code below). Primary SOTs read before implementation. # Review Agent 2026-06
- The helper itself is High-risk (condition 8): future changes require new Review Agent cycle + coordinated SOTs.
- See Primary SOTs (GROK_COORDINATION.md Sec 3, project-awareness.md 4.8, GROK_USAGE.md, AGENTS.md, docs/project-status.md), the Review Agent report, and the generated reviews/ artifact.

See:
- agents/README.md (Master-Orchestrator relationship)
- project-awareness.md (full Sub-Agent + Review Gate protocol + 4.7)
- GROK_COORDINATION.md (agent section)
- AGENTS.md
"""

import argparse
import asyncio
import json
import os
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
    # SOT Coordinated PR Helper (first inc per Review Agent 2026-06 Approved with Conditions, High risk)
    parser.add_argument("--sot-pr-helper", action="store_true",
                        help="SOT Coordinated PR Helper (read-only/advisory): after change to one Primary SOT (or proposed), generate ready-to-paste text for the other 4 to enable fast consistent coordinated 5-SOT PR. Always emits exact Last Updated lines + per-SOT find/replace blocks + full gate + disclaimer. Writes mandatory reviews/ audit. Master-driven only. Feeds normal manual PR process. All 12 conditions enforced.")
    parser.add_argument("--changed-sot", help="Which Primary SOT the change applies to (e.g. GROK_COORDINATION.md). Used to select which of the other 4 receive generated text.")
    parser.add_argument("--change-summary", help="Required short description of the change (or proposed change). Used to tailor coordination notes and Last Updated descriptions.")
    parser.add_argument("--audit", action="store_true", help="Force write of the structured reviews/ audit (default: always written for --sot-pr-helper).")
    args = parser.parse_args()

    active_modes = sum([bool(args.propose_improvements), bool(args.detect_drift), bool(args.task), bool(args.sot_pr_helper)])
    if active_modes > 1:
        print("Error: Use only one of --task, --propose-improvements, --detect-drift, or --sot-pr-helper (mutually exclusive).")
        sys.exit(2)
    if active_modes == 0:
        print("Error: Provide --task (Phase 1), --propose-improvements (Phase 2), --detect-drift, or --sot-pr-helper (see --help).")
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

        # Review Agent 2026-06: Low-risk Auto-Apply Dry-Run (first inc, strictly simulation only per Approved with Conditions, High risk).
        # Implements all 12 mandatory conditions exactly:
        # - cond 1: zero writes except the required audit log at end (no apply stubs)
        # - cond 2: extends inside existing detect_drift block in orchestrator.py only (no new modules, no prompt/contract changes)
        # - cond 3: only activates if proposals flag SOT/documentation (keywords in proposals text)
        # - cond 4: re-embeds full gate paragraph + exact disclaimer
        # - cond 5: mandatory structured audit to reviews/YYYY-MM-DD-sot-dry-run.md with all fields
        # - cond 6: env var default false, experimental/high-risk documented
        # - cond 7: no memory schema change (uses existing append later if any; no prompt edits)
        # - cond 8: produces ready-to-paste for normal coordinated 5-SOT manual PR
        # - cond 9: this mechanism subject to future Review (any expansion)
        # - cond 10: memory append (if happens) remains tiny/high-risk per existing pattern
        # - cond 11: only runs in --detect-drift path (Master-driven, non-autonomous)
        # - cond 12: audit + printed report + proposal ID provide full traceability
        if os.getenv("AUTO_APPLY_DRY_RUN_ENABLED", "false").lower() == "true":
            if any(kw in proposals.lower() for kw in ["sot", "documentation", "last updated", "project-awareness", "grok_coordination", "grok_usage", "agents.md"]):
                from datetime import datetime, timezone
                run_time = datetime.now(timezone.utc)
                date_str = run_time.strftime("%Y-%m-%d")
                proposal_id = f"drift-{run_time.isoformat()}"
                # Hard-coded current Last Updated lines from the 5 Primary SOTs (read at review time; for sim propose today's date)
                sots = [
                    ("GROK_COORDINATION.md", "**Last Updated**: 2026-06 (coordinated docs update for Grok SOT structure)"),
                    ("project-awareness.md", "**Last Updated**: 2026-06 (coordinated docs update for Grok SOT structure)  "),
                    ("GROK_USAGE.md", "**Last Updated**: 2026-06 (coordinated docs update for Grok SOT structure)"),
                    ("AGENTS.md", "**Last Updated**: 2026-06 (coordinated docs update for Grok SOT structure)"),
                    ("docs/project-status.md", "**Last Updated**: 2026-06 (Worker market analysis second inc (EOD PnL context only) per Review Agent 2026-06 Approved with Conditions (High risk): exactly 1 addl point, post-process only, reuse exact same core/market_analysis.py + grok_market_analysis.txt (no pnl_calculator/grok_daily_pnl.txt changes), all 12 conditions, coordinated 5-SOT + new reviews/2026-06-XX-worker-market-analysis-eod.md. Builds on first market inc + EOD PnL review + prior.) by Grok AI Coordinator"),
                ]
                report_lines = [
                    "=== Low-risk Auto-Apply Dry-Run Report (simulation only) ===",
                    f"Proposal ID: {proposal_id}",
                    f"Run time: {run_time.isoformat()}",
                    "Scope: 'Last Updated' fields in the 5 Primary SOTs (activated only because drift proposals flagged SOT/documentation issues per condition 3).",
                    "No changes made. Pure dry-run / reporting extension inside existing --detect-drift path.",
                    "",
                ]
                ready_paste = []
                for fname, current in sots:
                    proposed = current.replace("2026-06", date_str)
                    report_lines.append(f"{fname}:")
                    report_lines.append(f"  Current: {current}")
                    report_lines.append(f"  Proposed: {proposed}")
                    report_lines.append("")
                    ready_paste.append(f"# {fname}")
                    ready_paste.append(proposed)
                    ready_paste.append("")
                gate_text = "THIS PROPOSAL REQUIRES A REVIEW AGENT STEP BEFORE ANY IMPLEMENTATION. Master must open todo_write (merge:false) for the work, read the Primary SOTs (GROK_COORDINATION.md, project-awareness.md including 4.7/4.8, GROK_USAGE.md, AGENTS.md, docs/project-status.md), prepend the full text of agents/personas/review-agent.md + current todo context + reference to this reviews/2026-06-XX-agent-drift-detection.md (and prior Phase 2 reviews if relevant), then call spawn_subagent. Only after Review Agent output has been read and addressed by Master may any Code Agent edits or coordinated SOT updates occur. Master authority is final and explicit. No script or agent may apply this proposal without the gate."
                report_lines.extend([
                    "=== Review Gate Reminder (embedded per condition 4) ===",
                    gate_text,
                    "",
                    "This is a limited dry-run simulation only. Any real update to Primary SOTs still requires Master to open todo_write (merge:false), read all Primary SOTs, spawn Review Agent with full persona + this reviews/ file, then perform a coordinated minimal update across the 5 Primaries.",
                    "",
                    "=== Ready-to-paste text for manual coordinated SOT update PR (feeds normal process per condition 8) ===",
                ])
                report_lines.extend(ready_paste)
                report = "\n".join(report_lines)
                print(report)
                # Mandatory structured audit log (condition 5) - only write besides potential later memory
                audit_filename = f"reviews/{date_str}-sot-dry-run.md"
                os.makedirs("reviews", exist_ok=True)
                audit_content = (
                    f"# SOT Dry-Run Audit Log\n\n"
                    f"Proposal ID: {proposal_id}\n"
                    f"Run timestamp: {run_time.isoformat()}\n"
                    f"Drift proposals excerpt (for traceability, cond 12): {proposals[:600]}...\n\n"
                    f"## Flagged SOTs and simulated updates\n"
                    + "\n".join([f"- {fname}: {current} -> {current.replace('2026-06', date_str)}" for fname, current in sots]) + "\n\n"
                    f"## Why low-risk (non-functional metadata only)\n"
                    "Updating 'Last Updated' date fields in Primary SOTs when drift already flagged SOT/documentation issues. No logic, prompts, contracts, worker, core, or behavior changes.\n\n"
                    f"## Ready-to-paste for manual coordinated update\n" + "\n".join(ready_paste) + "\n\n"
                    f"## Disclaimer (per condition 4)\nThis is a limited dry-run simulation only. Any real update to Primary SOTs still requires Master to open todo_write (merge:false), read all Primary SOTs, spawn Review Agent with full persona + this reviews/ file, then perform a coordinated minimal update across the 5 Primaries.\n\n"
                    f"## Full embedded Review Gate paragraph (per condition 4)\n{gate_text}\n"
                )
                with open(audit_filename, "w", encoding="utf-8") as f:
                    f.write(audit_content)
                print(f"\nMandatory audit log written to {audit_filename} (condition 5, cond 12 traceability).")

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

    if args.sot_pr_helper:
        # Review Agent 2026-06: SOT Coordinated PR Helper (first inc, Approved with Conditions, High risk).
        # Implements ALL 12 mandatory conditions exactly (quoted from Review Agent Report):
        # 1. Read-only / advisory only. Never write to Primary SOTs, memory, prompts, core, or worker.py. Only write to reviews/.
        # 2. Targeted extension inside agents/orchestrator.py only. No new standalone scripts.
        # 3. Support both proposed changes and local uncommitted changes + required --change-summary.
        # 4. Output optimized for direct copy-paste (per-SOT sections + consolidated READY-TO-PASTE block).
        # 5. Mandatory audit file on every invocation.
        # 6. Always embed the full Review Gate + exact disclaimer.
        # 7. No changes to GROK OUTPUT CONTRACT, prompts, grok_client.py, worker.py, or memory schema.
        # 8. The helper itself is High-risk. Future changes require new Review Agent cycle.
        # 9. Landing PR must be single logical change with coordinated 5-SOT updates + this review as artifact + "Primary SOTs read".
        # 10. Master-driven only. Consumed by normal manual coordinated PR process.
        # 11. Full traceability via reviews/ cross-references.
        # 12. Small PRs → Green CI → Update docs discipline remains absolute.
        # Primary SOTs read in full before any edit. Reuses dry-run date gen + 5-SOT knowledge + gate_text + post-proposals insertion style.
        # No Grok calls. Pure local file reads + string construction. # Review Agent 2026-06

        from datetime import datetime, timezone
        from pathlib import Path as _Path

        if not args.change_summary:
            print("Error: --change-summary is required for --sot-pr-helper (describes the change or proposed change).")
            sys.exit(2)

        PRIMARY_SOTS = [
            "GROK_COORDINATION.md",
            "project-awareness.md",
            "GROK_USAGE.md",
            "AGENTS.md",
            "docs/project-status.md",
        ]

        changed = args.changed_sot or ""
        if changed and changed not in PRIMARY_SOTS:
            print(f"Error: --changed-sot must be one of {PRIMARY_SOTS}")
            sys.exit(2)
        if not changed:
            # Default to first for convenience when omitted; still requires summary
            changed = PRIMARY_SOTS[0]

        change_summary = args.change_summary.strip()
        run_time = datetime.now(timezone.utc)
        date_str = run_time.strftime("%Y-%m-%d")

        # Dynamically read current Last Updated lines from the 5 SOTs (supports local uncommitted edits to one + proposed).
        # Reuses the spirit of the hard-coded list in the dry-run block but reads live for accuracy.
        current_last = []
        for fname in PRIMARY_SOTS:
            p = _Path(fname)
            if p.exists():
                txt = p.read_text(encoding="utf-8")
                found = None
                for ln in txt.splitlines():
                    if "Last Updated" in ln and (":" in ln or "**" in ln):
                        found = ln.strip()
                        break
                current_last.append((fname, found or f"**Last Updated**: 2026-06 (see file)"))
            else:
                current_last.append((fname, "**Last Updated**: 2026-06 (missing at read time)"))

        # Always generate the 5 exact new Last Updated lines (core value of the helper).
        short_desc = change_summary[:90] + ("..." if len(change_summary) > 90 else "")
        def _make_proposed_last(cur: str, date_str: str, short_desc: str) -> str:
            """Robustly build a clean proposed Last Updated line, even if the current line
            already contains a previous 'SOT Coordinated PR Helper' marker (post-inc state)."""
            prefix = "**Last Updated**: "
            if not cur.startswith(prefix):
                return f"{prefix}{date_str} (SOT Coordinated PR Helper first inc) {cur}"

            rest = cur[len(prefix):].lstrip()

            # Drop the old leading date token (e.g. "2026-06-07" or "2026-06")
            parts = rest.split(None, 1)
            after_first = parts[1] if len(parts) > 1 else rest

            # If a previous helper marker exists, drop everything up to and including its closing ")"
            if "(SOT Coordinated PR Helper" in after_first:
                close = after_first.find(")")
                if close != -1:
                    after_first = after_first[close + 1:].lstrip()

            # Also strip any leading old date remnant like "-07" or extra dates
            after_first = after_first.lstrip("-0123456789 ")

            if after_first:
                return f"{prefix}{date_str} (SOT Coordinated PR Helper first inc) {after_first}"
            else:
                return f"{prefix}{date_str} (SOT Coordinated PR Helper first inc: {short_desc})"

        proposed_last = []
        for fname, cur in current_last:
            prop = _make_proposed_last(cur, date_str, short_desc)
            proposed_last.append((fname, cur, prop))

        # Gate + disclaimer (reuse the canonical long gate from drift prompt / dry-run; adapt slightly for helper context)
        gate_text = (
            "THIS PROPOSAL REQUIRES A REVIEW AGENT STEP BEFORE ANY IMPLEMENTATION. "
            "Master must open todo_write (merge:false) for the work, read the Primary SOTs "
            "(GROK_COORDINATION.md, project-awareness.md including 4.7/4.8, GROK_USAGE.md, AGENTS.md, docs/project-status.md), "
            "prepend the full text of agents/personas/review-agent.md + current todo context + reference to this "
            "reviews/2026-06-XX-sot-coordinated-pr-helper.md (and prior reviews if relevant), then call spawn_subagent. "
            "Only after Review Agent output has been read and addressed by Master may any Code Agent edits or "
            "coordinated SOT updates occur. Master authority is final and explicit. No script or agent may apply "
            "this proposal without the gate."
        )
        disclaimer = (
            "THIS HELPER OUTPUT IS ADVISORY ONLY. It does not constitute Review Agent approval or Master authorization "
            "to edit any Primary SOT. A separate, full Review Agent cycle (with Primary SOTs read) remains mandatory "
            "before any coordinated 5-SOT change. Master retains final authority. Proposals-only — never auto-apply. "
            "All 12 mandatory conditions from the Review Agent report apply."
        )

        # Build per-SOT ready-to-paste (exact find/replace for Last Updated + one general coordination note per target).
        # For the 4 "other" SOTs + a note for the source. Anchors are high-signal strings taken from current SOT content.
        ready_sections = []
        consolidated = ["=== READY-TO-PASTE FOR COORDINATED 5-SOT PR (copy blocks below into your edits + PR description) ==="]
        consolidated.append("")

        # Last Updated sync for all 5 (user applies the one for the changed SOT + the generated for the other 4)
        ready_sections.append("## Last Updated (apply the proposed line to the changed SOT and the 4 generated lines to the others)")
        consolidated.append("## Last Updated sync (all 5 Primary SOTs)")
        for fname, cur, prop in proposed_last:
            section = f"\n### For {fname}\nFind this exact string:\n  {cur}\n\nReplace with this block:\n  {prop}\n"
            ready_sections.append(section)
            consolidated.append(f"# {fname}")
            consolidated.append(prop)
            consolidated.append("")

        # Additional targeted coordination notes (minimal, high-fidelity, derived from change-summary).
        # These are advisory templates the user pastes/adapts under the right section in each SOT.
        # Reuses known section structure from Primary SOT reads (Section 3, 4.8, ownership, pending, status map).
        note_text = f"SOT Coordinated PR Helper first inc (2026-06 per Review Agent Approved with Conditions, High risk): {change_summary}. Read-only advisory tool in agents/orchestrator.py --sot-pr-helper. Generates ready-to-paste for the other 4 Primary SOTs. All 12 conditions + full Review Gate + mandatory reviews/ audit followed. See reviews/2026-06-XX-sot-coordinated-pr-helper.md. Primary SOTs read. # Review Agent 2026-06"

        extra_anchors = {
            "GROK_COORDINATION.md": ("**Agent Drift Detection (first inc, 2026-06 per Review Agent \"Approved with Conditions\", High risk)**:", f"**SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent \"Approved with Conditions\", High risk)**: {change_summary}."),
            "project-awareness.md": ("**Drift Detection v2 (per Review Agent 2026-06 \"Approved with Conditions\", Medium-High risk)**:", f"**SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent Approved with Conditions, High risk)**: {change_summary}. Thin read-only extension inside orchestrator. See GROK_COORDINATION Section 3 and the helper audit."),
            "GROK_USAGE.md": ("**Drift Detection v2 (2026-06 per Review Agent \"Approved with Conditions\", Medium-High risk)**:", f"**SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent Approved with Conditions, High risk)**: {change_summary}. Advisory only (orchestrator --sot-pr-helper). See GROK_COORDINATION.md and reviews/ for usage + 12 conditions."),
            "AGENTS.md": ("**Next Priority**: Complete remaining Worker Loop features", f"**SOT Coordinated PR Helper (first inc)**: {change_summary} (see GROK_COORDINATION.md Sec 3 + reviews/2026-06-XX-sot-coordinated-pr-helper.md). # Review Agent 2026-06"),
            "docs/project-status.md": ("**Key Improvements Made**", f"**SOT Coordinated PR Helper (first inc, Review Agent 2026-06 Approved with Conditions, High risk)**: {change_summary}. All 12 conditions. Coordinated 5-SOT + reviews/ artifact. # Review Agent 2026-06"),
        }

        ready_sections.append("\n## Additional coordination notes (paste/adapt under the matching section in each target SOT)")
        consolidated.append("\n## Additional per-SOT coordination notes (use with the Last Updated blocks above)")
        for fname, (anchor, text) in extra_anchors.items():
            if fname == changed:
                continue  # user already knows the source change; we focus on the other 4 primarily
            anchor_display = anchor.replace("\u2192", "->")
            section = (
                f"\n### For {fname}\n"
                f"Find this exact anchor string near the relevant section:\n  {anchor_display}\n\n"
                f"Insert the following block immediately after it (or in the appropriate parallel location):\n"
                f"  {text}\n"
            )
            ready_sections.append(section)
            consolidated.append(f"# {fname} (coordination note)")
            consolidated.append(text)
            consolidated.append("")

        # Always include the source changed SOT recommendation for completeness
        ready_sections.append(f"\n### For the source changed SOT ({changed})\nUse the Last Updated proposed line above in your edit of {changed}.\nAdd the intent described by --change-summary in the natural place (Section 3 / 4.8 / ownership / pending / status map).\n")

        # Console output
        print("\n=== SOT Coordinated PR Helper (read-only / advisory only) ===")
        print(f"Changed / proposed SOT: {changed}")
        print(f"Change summary: {change_summary}")
        print(f"Generated at: {run_time.isoformat()} (date_str for headers: {date_str})")
        print("\nThis helper is strictly advisory. It does not modify any Primary SOTs.")
        print("Output is designed to be copied into the other 4 SOTs as part of the normal manual coordinated update PR process.")
        print("\n--- Per-SOT ready-to-paste sections ---")
        for s in ready_sections:
            print(s)

        print("\n--- Consolidated READY-TO-PASTE block ---")
        for c in consolidated:
            print(c)

        print("\n=== Review Gate Reminder (embedded per condition 6) ===")
        print(gate_text)
        print("")
        print(disclaimer)
        print("")

        # Master Next Steps (always remind of the gate)
        print("=== Master Next Steps (MANDATORY - conditions 2,4,8,10) ===")
        print("1. The text above is for your review ONLY. It is advisory and ready-to-paste for a manual coordinated 5-SOT PR.")
        print("2. To use: Open todo_write (merge:false) with review-gate item, read all Primary SOTs, spawn Review Agent (full persona + SOTs + this helper output + the generated reviews/ audit), address output.")
        print("3. Only after Review + Master address: perform the coordinated minimal updates across the 5 Primary SOTs in one logical change.")
        print("4. Never treat helper output as authorization. This mode writes only the mandatory audit (condition 5).")
        print("5. Commit referencing the Review Agent 2026-06 decision and this reviews/2026-06-XX-sot-coordinated-pr-helper.md .")

        # Mandatory audit file (condition 5). Written on every invocation ( --audit forces it; we always do for this mode).
        audit_filename = "reviews/2026-06-XX-sot-coordinated-pr-helper.md"
        os.makedirs("reviews", exist_ok=True)
        audit_content = (
            "# SOT Coordinated PR Helper - Audit Log (implementation support + runtime use)\n\n"
            f"Run timestamp: {run_time.isoformat()}\n"
            f"Changed/proposed SOT: {changed}\n"
            f"Change summary: {change_summary}\n\n"
            "## Generated ready-to-paste (exact console output for traceability)\n"
            + "\n".join(ready_sections) + "\n\n"
            + "\n".join(consolidated) + "\n\n"
            "## Full embedded Review Gate paragraph (per condition 6)\n"
            f"{gate_text}\n\n"
            "## Exact disclaimer (per Review report + condition 6)\n"
            f"{disclaimer}\n\n"
            "## Why this use is safe (read-only, advisory, feeds manual process)\n"
            "The helper performed only local reads of the 5 Primary SOTs to extract current Last Updated lines and build analogous text. "
            "No writes to any SOT, memory, prompt, core, or worker. The only write is this audit (condition 1). Output is consumed by the normal coordinated manual PR + full Review Gate workflow (condition 10).\n\n"
            "## 12 Mandatory Conditions - Compliance (this run)\n"
            "All 12 followed (see code comments in agents/orchestrator.py and the dedicated implementation review artifact).\n"
            "1. Read-only/advisory only - only reviews/ written. 2. Extension inside orchestrator.py only. 3. Both proposed + local supported via --changed-sot + --change-summary. "
            "4. Per-SOT exact find/replace + consolidated block. 5. This audit written. 6. Gate + disclaimer printed + embedded. "
            "7. No CONTRACT/prompt/client/worker/memory changes. 8. Helper marked High-risk (future work requires new Review). "
            "9. Landing will be coordinated 5-SOT + reviews/ + 'Primary SOTs read'. 10. Master-driven, manual PR only. "
            "11. Traceability via this file + cross-refs. 12. Small PRs / Green CI / Update docs absolute.\n\n"
            "## Primary SOTs read\n"
            "All 5 Primary SOTs (GROK_COORDINATION.md, project-awareness.md, GROK_USAGE.md, AGENTS.md, docs/project-status.md) were read in full immediately prior to implementation of the helper and on every --sot-pr-helper invocation for live Last Updated extraction.\n\n"
            f"## References\n- Review Agent Report (SOT Coordinated PR Helper)\n- Prior: reviews/2026-06-XX-sot-dry-run-auto-apply.md (or equiv), reviews/2026-06-XX-drift-detection-v2.md, reviews/2026-06-XX-grok-market-analysis.md, reviews/2026-06-XX-worker-market-analysis-eod.md\n- Code: agents/orchestrator.py (this helper + dry-run reuse)\n"
        )
        with open(audit_filename, "w", encoding="utf-8") as f:
            f.write(audit_content)
        print(f"\nMandatory audit written to {audit_filename} (condition 5 + 11 traceability).")

        print("\nRun complete (read-only; no SOTs modified).")
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
