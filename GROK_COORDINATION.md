# GROK_COORDINATION.md

**Primary Source of Truth (SOT)** — This file defines the authoritative SOT table for the project. All Grok-related changes must be coordinated across the Primary SOTs listed below (no fragmented updates). See also [GROK_USAGE.md](GROK_USAGE.md) for the complete canonical map of Grok integrations.

**Project**: All-in-One-DeFi-Bot  
**Repository**: Zaikon13/All-in-One-DeFi-Bot  
**Primary Coordinator**: Grok (xAI Grok-4.3)  
**Created**: 2026-05 (post Full Repo Sync)  
**Last Updated**: 2026-06 (coordinated docs update for Grok SOT structure)

This is the **central coordination and Single Source of Truth** document for all Grok-led work on the repository. All agents, sub-agents, and manual sessions must reference and keep this file updated.

---

## 1. Project Architecture Summary

**High-Level**:
- Professional DeFi Telegram bot specialized for the **Cronos** ecosystem.
- Real-time wallet monitoring, transaction tracking, new pair alerts (Dexscreener), daily PnL reports, Grok-powered AI analysis.
- **Hybrid deployment** on Railway: Web (FastAPI + Telegram webhook) + Worker (background asyncio jobs).
- Strong GitHub Actions automation with Grok-4.3 deeply integrated for health monitoring, code reviews, and sync checks.
- Modular Python structure with clear separation between HTTP surface and background jobs.

**Key Components**:

| Layer              | Location                          | Responsibility |
|--------------------|-----------------------------------|----------------|
| **HTTP / Telegram** | `app/main.py`, `app/commands/`, `app/github_webhook.py`, `app/health.py` | FastAPI webhook handler, command routing (`/daily_pnl`, `/balances`, `/grok-analyze`), balances & PnL orchestration |
| **Core Logic**     | `core/` (grok_client.py, pnl_calculator.py, wallet.py, dexscreener.py) | Grok API wrapper, PnL computation (Cronos Explorer + advanced reports), wallet helpers, Dexscreener polling |
| **Background Worker** | `worker.py` (WorkerLoop class) | Full Worker Loop: real Dexscreener new pair alerts, wallet balance monitoring + change alerts, heartbeat. All loops active. |
| **Deployment**     | `railway.toml`, `Dockerfile`, `Procfile`, `DEPLOYMENT_SOP.md` | 3 Railway services |
| **CI/CD**          | `.github/` (workflows + dependabot.yml) | sync-check, health-check, grok-code-review, dependency-check, ci + **Dependabot** (pip + GitHub Actions + Docker) |
| **Docs & Coordination** | Root `.md` files + `docs/project-status.md` + `GROK_USAGE.md` + this file | See SOT section (Primary: GROK_COORDINATION.md, project-awareness.md, docs/project-status.md, GROK_USAGE.md, AGENTS.md) |

**Railway Services (Current)**:
- **bot** (web, primary): Handles live Telegram webhook `https://bot-production-3d9c.up.railway.app/telegram/webhook`. Healthy.
- **web-gpl6** (web, redundant): Duplicate code, no webhook registered. Can be disabled.
- **worker** (worker): Background jobs. Config/start command currently inconsistent across files.

**Grok Integration**:
- Model: `grok-4.3`
- **Runtime (Python)**: Centralized in `core/grok_client.py` (SOT for load_prompt, call_grok with timeout, is_valid_grok_response quality gate). Used in:
  - `app/main.py`: `/grok-analyze` (Telegram + HTTP) with live wallet balances + recent txs via core/wallet, using `prompts/grok_wallet_analysis.txt`.
  - `core/pnl_calculator.py`: `/daily_pnl` Grok insight enhancement using `prompts/grok_daily_pnl.txt` (with pre-computed summaries, 25s timeout, quality gate, safe fallbacks).
- **CI / GitHub Actions** (now unified to reuse `core/grok_client.py`):
  - `.github/scripts/call_grok.py`: Reusable CLI (setup-python + pip -r + PYTHONPATH) that loads from `prompts/` and calls via the SOT client.
  - `.github/workflows/grok-code-review.yml`: PR diff reviews (via `prompts/grok_code_review.txt` + {diff} var). Uses strict GROK CODE REVIEW CONTRACT (2026-06, Review Agent Approved with Conditions). Triggers updated 2026-06 per Review Agent Approved with Conditions (High Risk): pull_request to branches: [main] + paths filter (**.py, .github/workflows/**, prompts/**, core/**, docs/** etc.) for automatic reviews on relevant changes to main. Remains advisory (`continue-on-error: true`). # Review Agent 2026-06: Expanded per decision to improve automatic useful reviews while controlling noise.
  - `.github/workflows/health-check.yml`: Railway failure analysis + Issue + enriched Telegram (via strict GROK HEALTH CHECK CONTRACT in `prompts/grok_health_check.txt`, redesigned 2026-06 per Review Agent "Approved with Conditions"). Non-blocking. Bot liveness only (worker visibility gap explicitly noted). Minimal workflow_call support.
  - Both keep `continue-on-error: true` and github-script posting.
- **Prompts** (in `prompts/` , now shared by runtime + CI, loaded exclusively via client):
  - `grok_daily_pnl.txt`, `grok_wallet_analysis.txt`
  - `grok_code_review.txt`, `grok_health_check.txt`
- **Dependencies**: `GROK_API_KEY` (env / GitHub secret), referenced in coordination docs, agent personas, .env.example, DEPLOYMENT_SOP.md.
- Safe patterns: `continue-on-error`, fallbacks, centralized quality gates + error prefixes in client.
- See **Primary SOT `GROK_USAGE.md`** for the full living map of call sites, quality gates, and pending items.

**Current State Notes**:
- Git: Fully synced with `origin/main` (post-rebase).
- Worker Loop & PnL: Marked "In Progress" (AGENTS.md). Basic scaffolding exists; full features pending.
- All public health endpoints responsive.

---

## 2. Single Source of Truth (SOT / SPOT) Files

From `SYNC.md` (core rule): **SPOT υπερισχύει** — these files define truth. All other docs are derived or supplementary.

**Primary (Authoritative)**:
- `GROK_COORDINATION.md` (this file) — **Central coordination hub** for agents, skills, protocol, priorities, Grok integration rules.
- `project-awareness.md` — Grok AI Agent System definition, handoff protocols, review gate, priorities, architecture awareness.
- `docs/project-status.md` — Overall project health, workflows status, next steps.
- `GROK_USAGE.md` — **Complete canonical map of all Grok integrations** (runtime call sites, CI workflows, prompts, quality gates, dependencies, pending items).
- `AGENTS.md` — Module ownership map, current focus, responsibilities.

**Strong Supporting SOT**:
- `DEPLOYMENT_SOP.md` — Railway architecture, services, env vars, redeploy process.
- `CHECKS.md` — System health checklist.
- `GROK_HEALTH.md` — Grok integration status and best practices.
- `WORKER.md` — Worker purpose and start command (note: conflicts with railway.toml).
- `README.md` — Public-facing overview.

**Legacy / To Be Updated or Deprecated**:
- `README_SYNC.md` — Outdated ChatGPT/Codex era instructions (references non-existent `sync.yml`, OPENAI keys).
- `MANIFEST.md` — Stale auto-generated manifest (wrong modules, old sync references).
- `RAILWAY.md` — References missing `RAILWAY_CONFIG.md` (from unmerged Railway bot PRs).
- `SUMMARY.md` — High-level overview (keep but make it point to project-status.md).

**Rule Going Forward**:
- Before editing any doc, update the relevant SOT first (especially the Primary list below and cross-references).
- **GROK_USAGE.md** is now a required Primary SOT for any Grok-related work (runtime, CI, prompts, gates).
- All Primary SOTs must be updated in a **coordinated single PR** for any Grok touch or docs change (see task history for "coordinated documentation update plan").
- Small PRs only. Green CI required.
- After any sync or major change, run full audit against this section.
- All Primary SOTs carry this header (or equivalent): "See GROK_COORDINATION.md SOT table and GROK_USAGE.md for Grok integrations." (This file is the source of the table.)

---

## 3. Agents, Sub-Agents & Skills

**Ownership (from AGENTS.md)**:
- Grok is primary for: Deployment & Railway, Worker Loop & Background Jobs, Telegram Handlers (shared), PnL Calculation, GitHub Actions & CI/CD, Documentation, Grok Integration.
- Focus: Complete Worker Loop + PnL refactoring.

**Skills We Will Use (Bundled + User)**:

| Skill              | Path (relative)                  | Primary Use Case for This Project | When to Invoke |
|--------------------|----------------------------------|-----------------------------------|----------------|
| **review**        | bundled/skills/review           | Code reviews of changes/PRs (posts PENDING reviews on GitHub) | `/review`, before PRs, on `grok-code-review` validation |
| **pr-babysit**    | bundled/skills/pr-babysit       | Monitor stale PRs (#13, old Railway bot PRs #7-9), fix CI, address comments, restack | `/pr-babysit add 13`, scheduled `/loop` |
| **implement**     | bundled/skills/implement        | Full feature implementation (Worker Loop, PnL refactor) with multi-reviewer loop | Major work: "implement full worker loop" |
| **design** + **execute-plan** | bundled/skills/design + execute-plan | Architecture for large refactors (Railway cleanup, new features) | Before big changes |
| **check**         | .grok/skills/check              | Self-verification of diffs/builds/tests after changes | Post-implement, before claiming done |
| **best-of-n**     | .grok/skills/best-of-n          | Evaluate multiple approaches in parallel (e.g. PnL strategies) | When multiple reasonable implementations exist |
| **help**          | .grok/skills/help               | Grok TUI / CLI / MCP / skills documentation | When user asks about features or setup |

**Sub-Agent & Parallel Execution**:
- The project now operates under the formal **Grok Native Sub-Agents Architecture with Mandatory Review Gate** (see `project-awareness.md` Section 4 for the complete protocol).
- Master Agent (Grok) coordinates specialized Sub-Agents: Review (mandatory gate before any code/SOT edit), Code/Implementer, Execute, Analysis, and Research.
- **Always** prepend the full persona text from `agents/personas/<name>-agent.md` + references to Primary SOTs when calling `spawn_subagent`.
- Plan Mode + `todo_write` (merge:false) is the default for non-trivial work. Include explicit "Spawn Review" and "Address Review feedback" steps in todos.
- `background: true` + `get_command_or_subagent_output` for long-running tasks.
- Personas live in `agents/personas/` (in addition to bundled skills personas). The bundled `review` skill is for GitHub PR reviews only; the internal Review Agent is the pre-edit gate.
- MCP Server: `grok_com_github` — all GitHub operations. Use `search_tool` first for schema.

**Phase 1 Orchestrator (agents/orchestrator.py + agents/memory/)** (added 2026-06 per Review Agent "Approved with Conditions", High Risk):
- Tool that **assists the Master Agent** (Grok retains final authority; does not replace Master or bypass Review Gate).
- Loads committed shared `memory/project_context.md` (SOT-like human summary; meaningful updates are high-risk SOT changes requiring Review + coordinated Primary SOT update) and `agent_memory.json` (simple state, committed for auditability, subject to Railway ephemeral FS limitations).
- Uses **core/grok_client.py exclusively** for any Grok planning calls.
- Suggests plans that reference the existing handoff protocol (todo_write, full personas prepended, SOT refs, spawn_subagent).
- For high-risk work: explicitly recommends spawning Review Agent first.
- Start simple: script (manual or scheduled via existing skills); foundation only (no autonomy, loops, or self-improvement in Phase 1).
- Sub-agents/ are thin wrappers only; spawning uses the official mechanism.
- Traceability: # Review Agent 2026-06 comments in new code. reviews/ for outputs.
- See agents/README.md for Master-Orchestrator relationship and full conditions.

**Protocol for Using Them**:
- Always open complex tasks (3+ steps or any edit/SOT impact) with `todo_write` (merge:false for new lists).
- One `in_progress` item at a time.
- For any code change, architecture decision, or Primary SOT update: the Review Agent gate is **mandatory** (detailed checklist, output format, and recording rules are in `project-awareness.md` Section 4.3 and `agents/personas/review-agent.md`).
- For PR babysitting or long monitoring: use scheduler + state files in `~/.grok/plugin-data/`.
- Reseed todos after context compaction. Reference the latest review logs when resuming.

---

## 4. Chat Synchronization Protocol

This project uses multiple Grok sessions / chats (TUI, different terminals, scheduled loops). Protocol ensures consistency:

1. **Repo-First + SOT**:
   - All permanent decisions live in this repo (especially this file + AGENTS.md + project-status.md).
   - Never rely on chat history alone.

2. **Todo Discipline** (enforced by harness):
   - Every 3+ action task **must** start with `todo_write` (full list, merge:false).
   - Exactly one item `in_progress`.
   - Mark `completed` immediately on finish (no batching).
   - Never end turn with unbacked pending/in_progress items.

3. **Background & Scheduling**:
   - Long-running monitors (pr-babysit, health polling): `spawn_subagent` (background) or `scheduler_create`.
   - State persisted in `~/.grok/plugin-data/pr-babysit/` (and similar for other skills).
   - Use `resume_from` for subagent continuity across turns/compactions.

4. **Full Repo Sync Protocol** (as executed in this session):
   - `git fetch origin`
   - `git rebase origin/main` (or `--rebase` pull when clean tree)
   - Verify: `rev-list --count HEAD..origin/main == 0` + `git status --porcelain == 0`
   - Run equivalent of `.github/workflows/sync-check.yml` locally.
   - Audit docs against SOT section.
   - Update this coordination file if drift found.

5. **Multi-Chat / Multi-Agent Handoff**:
   - Reference this `GROK_COORDINATION.md` + current todo list at start of new session.
   - For parallel work: spawn isolated sub-agents (worktree) and collect via `get_command_or_subagent_output`.
   - After compaction: reseed todos from state files + this doc.
   - Use MCP GitHub tools for shared truth (issues/comments as coordination bus).

6. **Safety**:
   - Worktree isolation for any git-mutating subagent work.
   - No direct edits to main workspace from babysit/implement loops.
   - Cap fix attempts per cycle (see pr-babysit skill).

---

## 5. Current Problems & Priorities

**Identified Problems (Post Full Sync Audit)**:
- **Stale PR Cleanup**: Successfully closed 8 stale PRs (#1, #2, #3, #5, #6, #7, #8, #9) using pr-babysit skill. All PRs were clearly superseded by current railway.toml, DEPLOYMENT_SOP.md, and GROK_COORDINATION.md. PR #13 remains intentionally open (small valid test for grok-code-review). Remaining potentially stale items: #12 and #15 (left open for now as they appear more recent/relevant).
- **Config Drift** (high priority):
  - Worker start command: `railway.toml` + `DEPLOYMENT_SOP.md` say `python -u main.py`; `WORKER.md` says `python -u worker.py`.
  - Multiple references to missing `RAILWAY_CONFIG.md`.
- **Documentation Inconsistency**:
  - Conflicting SOT claims (`docs/project-status.md` vs `SYNC.md` SPOT list).
  - Legacy files (README_SYNC.md, MANIFEST.md) reference dead ChatGPT/Codex/OPENAI setup.
- **Worker Loop**: Partially Functional - Real alerts active (new pair detection + wallet monitoring + heartbeat), improvements ongoing. Missing: persistence for known_pairs, full change detection, EOD PnL reports.
- **Minor Technical**:
  - `grok-code-review.yml` has stray leading `##last ` line.
  - Local workspace was 15 commits behind (now resolved).
- **Dependency Management**: Now handled proactively by **Dependabot** (weekly updates for pip, GitHub Actions, and Docker with PR limits). The existing `dependency-check.yml` workflow remains as a secondary security/outdated audit that creates issues. The previous open issue (#14) is superseded by Dependabot automation.
- **Redundant Service**: web-gpl6 still active and healthy but unnecessary.

**Priorities (Ranked)**:
1. **Advance Worker Loop** (Partially Functional) - Add persistence, better filtering, EOD PnL reports.
2. **PnL module refactoring** (accurate reports, Covalent vs Explorer consistency).
3. **Documentation hygiene**: Consolidate SOT claims, update or archive legacy files, make this GROK_COORDINATION.md the hub.
4. **Railway alignment**: Disable web-gpl6 if confirmed unused; ensure `railway.toml` + SOP + actual UI match.
5. **Ongoing**: Use `pr-babysit` on remaining open PRs (#12, #15); enforce small-PR + green-CI + doc-update rule.

**Completed**:
- Stale PR cleanup (8 PRs closed via pr-babysit skill).

**Success Metric**: Zero behind on main, all docs point to this file + project-status.md, Worker Loop feature-complete, 0 stale high-impact PRs.

---

**Next Action After This Document**: Activate Plan Mode + spawn parallel sub-agents for prioritized work (Worker Loop design + stale PR analysis).

**Maintained by**: Grok AI Coordinator (update via PR after any significant session).

---

*End of GROK_COORDINATION.md*