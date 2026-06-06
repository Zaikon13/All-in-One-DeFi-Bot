# AGENTS & MODULE OWNERSHIP MAP

**Primary Source of Truth (SOT)** — See the SOT table in [GROK_COORDINATION.md](GROK_COORDINATION.md). All Grok-related changes must be coordinated across Primaries (no fragmented updates). See also [GROK_USAGE.md](GROK_USAGE.md) for the complete canonical map of all Grok integrations.

**Last Updated**: 2026-06 (coordinated docs update for Grok SOT structure)

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

**Next Priority**: Complete remaining Worker Loop features (persistence, EOD PnL, better filtering) + PnL refactoring. See GROK_COORDINATION.md + GROK_USAGE.md for coordination.

All non-trivial implementation work (including the above) must follow the **Mandatory Review Gate** defined in `project-awareness.md` Section 4.3 and `agents/personas/review-agent.md`. The improved Grok Code Review (strict contract + expanded triggers), Health Check CI (strict contracts), and Phase 1 Orchestrator are advisory support for this gate. Master retains final authority.