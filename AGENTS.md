# AGENTS & MODULE OWNERSHIP MAP

**Primary Source of Truth (SOT)** — See the SOT table in [GROK_COORDINATION.md](GROK_COORDINATION.md). All Grok-related changes must be coordinated across Primaries (no fragmented updates). See also [GROK_USAGE.md](GROK_USAGE.md) for the complete canonical map of all Grok integrations.

**Last Updated**: 2026-06-07 (structured Grok market analysis output per Review Agent 2026-06 Approved with Conditions (High risk): 6-section Markdown enrichment; analysis only, renamed watchpoints, all 12 conditions + new artifact; Primary SOTs read) (coordinated docs update for Grok SOT structure)

## Current Ownership

| Module / Area                    | Primary Owner     | Secondary     | Status      |
|----------------------------------|-------------------|---------------|-------------|
| Deployment & Railway             | Grok              | -             | ✅ Active   |
| Worker Loop & Background Jobs    | Grok              | -             | Partially Functional - Real new pair alerts + wallet monitoring active. Remaining: persistence, EOD PnL, better filtering. |
| Telegram Handlers & Commands     | Grok + ChatGPT    | -             | Stable      |
| PnL Calculation & Reports        | Grok              | Codex         | Refactoring |
| GitHub Actions & CI/CD           | Grok              | -             | ✅ Clean    |
| Documentation (all .md files)    | Grok              | -             | ✅ Updated  |
| Grok Integration (API calls)     | Grok              | -             | ✅ Stable (see Primary SOT GROK_USAGE.md for full map of runtime/CI/prompts/gates) |

## Current Focus

**Grok** is leading:
- Advance Worker Loop (Partially Functional - real new pair alerts + wallet monitoring active)
- Grok Code Review workflow (strict GROK CODE REVIEW CONTRACT + expanded triggers: branches [main] + paths filter per Review Agent 2026-06 Approved with Conditions (High Risk) for automatic relevant PR reviews; remains advisory)
- Health Check + Telegram automation (strict GROK HEALTH CHECK CONTRACT, improved Telegram value with safe Markdown, worker limitation noted per Review Agent 2026-06)
- Documentation cleanup
- Workflow stability
- Phase 1 Orchestrator + Shared Memory (agents/orchestrator.py + agents/memory/ per Review Agent 2026-06 Approved with Conditions, High Risk): assists Master (Grok retains authority), loads committed context/memory, uses core/grok_client.py, references existing spawn_subagent + Review Gate. Foundation/script only. Coordinated SOT updates (no new Primary SOT).
- Phase 2 first scoped increment (Gated Feedback Loop + Self-Improvement Readiness, 2026-06 per Review Agent "Approved with Conditions"): minimal Improvement Proposer via `orchestrator.py --propose-improvements` + focused prompt. Reads Meta Notes + outcomes from memory; generates proposals **only** for prompts (grok_orchestrator_plan.txt) + memory schema. Every proposal embeds explicit "requires Review Agent + Master todo_write + handoff before any edit" language. Proposals-only (no auto-apply). Master-driven. No production logic touched. Coordinated SOT updates + reviews/2026-06-XX-phase2-feedback-loop.md. See project-awareness.md 4.7.
- Richer-context increment (higher-quality proposals, 2026-06 per Review Agent Approved with Conditions): plan_outcomes gains tiny `meta_summary` (Meta Notes excerpt) on plan runs; proposer receives last ~8 outcomes + meta_summary and prompt requires pattern detection + citations of specific runs/timestamps + precise before/after suggestions. Still proposals-only, Review Gate enforced, high-risk memory minimal, core/grok_client only. See updated 4.7 + new reviews/2026-06-XX-improve-proposer-quality.md. # Review Agent 2026-06.
- Agent Drift Detection (first inc, 2026-06 per Review Agent "Approved with Conditions", High risk): --detect-drift in orchestrator.py + grok_drift_detector.txt. Detects drift in SOT sections / prompt contracts / memory schema / project_context vs implementation. Structured proposals with full Review Gate enforcement. Detection + proposals only. Tiny records in plan_outcomes (high-risk). Master-driven, core client only. Detector subject to future runs (condition 10). See project-awareness.md + reviews/2026-06-XX-agent-drift-detection.md + 10 conditions. # Review Agent 2026-06.
- Drift Detection v2 (2026-06 per Review Agent "Approved with Conditions", Medium-High risk): modest evolution (extend existing; 1-2 addl high-value areas e.g. arg parsing/modes + SOT cross-refs). Smarter bounded context (targeted + recent plan_outcomes/drift summaries for patterns). Evolved prompt for citations/precision (history quality-only per condition 12). Still proposals-only, full gate (refs v2 review), tiny memory (high-risk), core client only, detector auditable (condition 10). See project-awareness.md + reviews/2026-06-XX-drift-detection-v2.md + 12 conditions. # Review Agent 2026-06.
- SOT Coordinated PR Helper (first inc): Added SOT Coordinated PR Helper (--sot-pr-helper) to agents/orchestrator.py per Review Agent Approved with Conditions (High risk). Read-only advisory only. Analyzes change to one SOT and generates ready-to-paste text for the other 4 SOTs. Reuses dry-run logic. All 12 mandatory conditions followed exactly. Primary SOTs read before implementation and on every run. (see GROK_COORDINATION.md Sec 3 + reviews/2026-06-XX-sot-coordinated-pr-helper.md). # Review Agent 2026-06
- Runtime Grok market analysis second inc (EOD PnL market context, 2026-06 per Review Agent "Approved with Conditions", High risk): exactly one additional point (post-process scheduled EOD only, reuse exact same helper + prompt, no core/pnl_calculator or grok_daily_pnl.txt changes). All 12 conditions + coordinated SOTs + new reviews/ file. # Review Agent 2026-06.
- Structured output enrichment (2026-06 per Review Agent 2026-06 Approved with Conditions, High risk): 6-section Markdown (Summary, Key Metrics, Market Narrative, Risk Signals, Observed Patterns & Contextual Watchpoints [renamed], Confidence & Data Notes) via prompt update + thin helper docs; all prior safety + 12 conditions + new ones (analysis/insights only, safe MD, no execution). Coordinated 5-SOT + new reviews/2026-06-XX-grok-market-analysis-structured.md. # Review Agent 2026-06: Structured inc.

**Next Priority**: Complete remaining Worker Loop features (persistence, EOD PnL, better filtering) + PnL refactoring. See GROK_COORDINATION.md + GROK_USAGE.md for coordination.

All non-trivial implementation work (including the above) must follow the **Mandatory Review Gate** defined in `project-awareness.md` Section 4.3 and `agents/personas/review-agent.md`. The improved Grok Code Review (strict contract + expanded triggers), Health Check CI (strict contracts), and Phase 1 Orchestrator are advisory support for this gate. Master retains final authority.