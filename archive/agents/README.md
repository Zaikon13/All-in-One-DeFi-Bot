# Agents Directory - Grok Native Sub-Agents System

**Master Agent (Grok)** is the central coordinator and retains **final decision authority**. You must use the Sub-Agent system and Mandatory Review Gate for all non-trivial work (see project-awareness.md Section 4 and GROK_COORDINATION.md).

The **Orchestrator** (`orchestrator.py`) is a **tool that assists the Master**, not a replacement:

- Loads shared `memory/project_context.md` (human-readable summary of current SOTs, rules, priorities) and `memory/agent_memory.json` (machine state between runs).
- Uses Grok **exclusively via `core/grok_client.py`** (SOT) to help plan which Sub-Agents (Review, Code, etc.) to invoke for a task.
- Prepares context and suggests the next steps using the **existing handoff protocol**: Master opens `todo_write`, prepends full persona from `agents/personas/`, includes Primary SOT references + current todo context, then calls `spawn_subagent`.
- After runs, updates memory (Master reviews changes).

## Phase 1 Scope (Foundation Only)
- Script-based (run manually or via scheduled skills / Execute Agent). **No long-running autonomous daemon.**
- No feedback loops, self-improvement, or deep autonomy.
- Sub-Agent wrappers in `sub_agents/` are convenience only; **always use the official `spawn_subagent` mechanism** with full personas.
- **High-risk work** (architecture, SOTs, core/, worker.py, new integrations, etc.) **must still go through the Review Agent** (either by spawning the persona or Master explicitly running the gate).

## Memory
- `project_context.md`: Committed, treated as SOT-like. **Meaningful updates are high-risk** and require Review Gate + coordinated Primary SOT updates.
- `agent_memory.json`: Committed simple state (last runs, pending, versions). Ephemeral risks on Railway (like `data/known_pairs.json`).
- Both files are part of the repo for auditability.

## Folder Structure (Phase 1)
- `personas/` - Official Sub-Agent definitions (do not modify here in Phase 1; prepend full text when spawning).
- `orchestrator.py` - The assistant script.
- `memory/` - Shared context and state.
- `sub_agents/` - Optional thin wrappers (use existing spawn protocol).
- `README.md` - This file.

## Usage Example (Master-driven)
```bash
python agents/orchestrator.py --task "Review and implement the new feature X"
# Orchestrator loads memory, calls Grok via core client for plan suggestion.
# Master reviews the plan, opens todo_write, spawns Review Agent (full persona + SOTs), then Code if approved.
```

See Primary SOTs for full protocol:
- GROK_COORDINATION.md (Section 3)
- project-awareness.md (Section 4, including 4.7 for Phase 2)
- AGENTS.md
- GROK_USAGE.md
- docs/project-status.md

**Phase 2 first scoped increment note** (2026-06, Review Agent "Approved with Conditions"): `orchestrator.py --propose-improvements` + `prompts/grok_improvement_proposer.txt` adds a minimal Master-driven Improvement Proposer. Generates gated proposals (prompts + memory schema only). Every proposal text requires Review Agent + Master todo_write + handoff before any edit. Proposals-only (no auto-apply). See project-awareness.md 4.7 and reviews/2026-06-XX-phase2-feedback-loop.md.

# Review Agent 2026-06: Phase 1 Orchestrator + memory per "Approved with Conditions (High Risk)". Phase 2 first inc (Improvement Proposer) added per same Review decision: proposals only, Review Gate language non-bypassable in output, core/grok_client only, Master authority explicit, coordinated SOTs. All new code has traceability. Memory files committed (plan_outcomes addition high-risk documented).