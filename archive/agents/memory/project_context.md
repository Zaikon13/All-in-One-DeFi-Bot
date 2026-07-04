# Project Context for Agent System (Phase 1)

**This file is committed and treated as SOT-like. Meaningful updates are high-risk changes requiring the Mandatory Review Gate + coordinated updates to Primary SOTs (GROK_COORDINATION.md, project-awareness.md, AGENTS.md, GROK_USAGE.md, docs/project-status.md).**

## Master Agent + Sub-Agents Overview
- **Master Agent (Grok)**: Central coordinator with final authority. Must use Sub-Agent system and Review Gate for non-trivial work. Always reads Primary SOTs in session, opens `todo_write` (merge:false) for 3+ action tasks, prepends full personas, calls `spawn_subagent`, reads and addresses outputs.
- Sub-Agents (in `agents/personas/`): Review (mandatory gate), Code (implement after Review), Execute (safe commands), Analysis (investigation), Research (external translated to stack).
- **Handoff Protocol** (always): Full persona text prepended + Primary SOT references + current todo context. Use `spawn_subagent` (background for long-running). Master addresses output.
- **Review Gate** (project-awareness.md 4.3): Mandatory for high-risk (core/, worker.py, app/main.py, SOTs, agents/personas/, .github/workflows/, architecture, new agent integrations, etc.). High-risk changes must include `# Review Agent 2026-06-XX` comments. Save reviews to `reviews/`.
- Grok Usage: Exclusively via `core/grok_client.py` (load_prompt, call_grok, is_valid_grok_response). Advisory in CI (continue-on-error). Strict contracts in prompts/.

## Current Priorities (from AGENTS.md and project-awareness.md)
- Complete Worker Loop (persistence for known_pairs, EOD PnL, better filtering/monitoring).
- PnL refactoring.
- Adopt full Sub-Agent + Review Gate for all non-trivial work.
- Small PRs → Green CI → Update docs (coordinated across Primaries).

## Key Rules & Guardrails
- Smallest correct change, reuse core/, defensive code, UTC discipline, Railway ephemeral FS awareness (no reliance on local state across deploys without Volume), Telegram Markdown v1 safety ( **bold** + simple -/• bullets only for user-visible).
- Legacy protection: Covalent only in telegram/handlers.py (legacy); production async Etherscan in core/.
- All permanent decisions in repo (Primary SOTs). Use reviews/ for long Review outputs.
- Orchestrator (this Phase 1) assists with context loading and Grok-assisted planning but **does not replace Master authority or bypass Review Gate**.

## Recent Agent Improvements (2026-06)
- Strict GROK CODE REVIEW CONTRACT and GROK HEALTH CHECK CONTRACT.
- Expanded grok-code-review triggers (branches [main] + paths).
- Health Check + Telegram enriched with safe Markdown.

**Last Synced**: 2026-06 (see GROK_COORDINATION.md for full sync protocol).

# Review Agent 2026-06: Initial project_context.md for Phase 1 per Approved with Conditions. This is SOT-like; future updates require Review Gate + coordinated Primary SOT changes. Orchestrator assists Master.