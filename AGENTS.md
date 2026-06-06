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
- Grok Code Review workflow (now with strict GROK CODE REVIEW CONTRACT enforcing Review Gate, SOTs, core/ reuse, Railway/legacy/UTC rules per Review Agent 2026-06)
- Health Check + Telegram automation (strict GROK HEALTH CHECK CONTRACT, improved Telegram value with safe Markdown, worker limitation noted per Review Agent 2026-06)
- Documentation cleanup
- Workflow stability

**Next Priority**: Complete remaining Worker Loop features (persistence, EOD PnL, better filtering) + PnL refactoring. See GROK_COORDINATION.md + GROK_USAGE.md for coordination.

All non-trivial implementation work (including the above) must follow the **Mandatory Review Gate** defined in `project-awareness.md` Section 4.3 and `agents/personas/review-agent.md`. The improved Grok Code Review and Health Check CI (strict contracts) are advisory support for this gate.