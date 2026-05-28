# GROK_COORDINATION.md

**Project**: All-in-One-DeFi-Bot  
**Repository**: Zaikon13/All-in-One-DeFi-Bot  
**Primary Coordinator**: Grok (xAI Grok-4.3)  
**Created**: 2026-05 (post Full Repo Sync)  
**Last Updated**: By Grok Coordinator (this file)

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
| **Docs & Coordination** | Root `.md` files + `docs/project-status.md` + this file | See SOT section |

**Railway Services (Current)**:
- **bot** (web, primary): Handles live Telegram webhook `https://bot-production-3d9c.up.railway.app/telegram/webhook`. Healthy.
- **web-gpl6** (web, redundant): Duplicate code, no webhook registered. Can be disabled.
- **worker** (worker): Background jobs. Config/start command currently inconsistent across files.

**Grok Integration**:
- Model: `grok-4.3`
- Used in: Health Check (root cause + auto GitHub Issue), Grok Code Review (PR diffs), future bot commands (`/grok-analyze`).
- Safe patterns: `continue-on-error`, fallbacks, jq parsing.

**Current State Notes**:
- Git: Fully synced with `origin/main` (post-rebase).
- Worker Loop & PnL: Marked "In Progress" (AGENTS.md). Basic scaffolding exists; full features pending.
- All public health endpoints responsive.

---

## 2. Single Source of Truth (SOT / SPOT) Files

From `SYNC.md` (core rule): **SPOT υπερισχύει** — these files define truth. All other docs are derived or supplementary.

**Primary (Authoritative)**:
- `docs/project-status.md` — Overall project health, workflows status, next steps (explicitly claimed as SOT in multiple places).
- `AGENTS.md` — Module ownership map, current focus, responsibilities.
- `SYNC.md` — Sync rules, checks, repo-first discipline.
- `GROK_COORDINATION.md` (this file) — **New central coordination hub** for agents, skills, protocol, priorities.

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
- Before editing any doc, update the relevant SOT first.
- Small PRs only. Green CI required.
- After any sync or major change, run full audit against this section.

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
- Use `spawn_subagent` (with `isolation: "worktree"` for safety on git-impacting work).
- `background: true` + `get_command_or_subagent_output` for long-running (e.g. pr-babysit groups, parallel reviews).
- Personas (shared/personas/): reviewer.md, implementer.md, design-doc-writer.md, etc. Always inject via prompt prefix for review/implement.
- MCP Server: `grok_com_github` — all GitHub operations (issues, PRs, reviews, commits). Use `search_tool` first for schema.

**Protocol for Using Them**:
- Always open complex tasks (3+ steps) with `todo_write` (merge:false for new lists).
- One `in_progress` item at a time.
- For PR babysitting or long monitoring: use scheduler + state files in `~/.grok/plugin-data/`.
- Reseed todos after context compaction.

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
- **Stale PRs**: 10+ open PRs, many from May 2026 or earlier (Railway bot PRs #7-9 created `RAILWAY_CONFIG.md` which no longer exists; old ChatGPT sync PRs from 2025). PR #13 is a small recent test for grok-code-review.
- **Config Drift** (high priority):
  - Worker start command: `railway.toml` + `DEPLOYMENT_SOP.md` say `python -u main.py`; `WORKER.md` says `python -u worker.py`.
  - Multiple references to missing `RAILWAY_CONFIG.md`.
- **Documentation Inconsistency**:
  - Conflicting SOT claims (`docs/project-status.md` vs `SYNC.md` SPOT list).
  - Legacy files (README_SYNC.md, MANIFEST.md) reference dead ChatGPT/Codex/OPENAI setup.
- **Worker Loop**: Major improvements delivered (real new pair alerts + wallet monitoring now active). Remaining: persistence for known pairs, EOD PnL reports, better error handling.
- **Minor Technical**:
  - `grok-code-review.yml` has stray leading `##last ` line.
  - Local workspace was 15 commits behind (now resolved).
- **Dependency Management**: Now handled proactively by **Dependabot** (weekly updates for pip, GitHub Actions, and Docker with PR limits). The existing `dependency-check.yml` workflow remains as a secondary security/outdated audit that creates issues. The previous open issue (#14) is superseded by Dependabot automation.
- **Redundant Service**: web-gpl6 still active and healthy but unnecessary.

**Priorities (Ranked)**:
1. **Complete Worker Loop** (AGENTS.md #1) + fix start command drift.
2. **PnL module refactoring** (accurate reports, Covalent vs Explorer consistency).
3. **Stale PR cleanup**: Close or merge Railway bot docs PRs; validate grok-code-review on #13 using the review skill.
4. **Documentation hygiene**: Consolidate SOT claims, update or archive legacy files, make this GROK_COORDINATION.md the hub.
5. **Railway alignment**: Disable web-gpl6 if confirmed unused; ensure `railway.toml` + SOP + actual UI match.
6. **Ongoing**: Use `pr-babysit` on open PRs; enforce small-PR + green-CI + doc-update rule.

**Success Metric**: Zero behind on main, all docs point to this file + project-status.md, Worker Loop feature-complete, 0 stale high-impact PRs.

---

**Next Action After This Document**: Activate Plan Mode + spawn parallel sub-agents for prioritized work (Worker Loop design + stale PR analysis).

**Maintained by**: Grok AI Coordinator (update via PR after any significant session).

---

*End of GROK_COORDINATION.md*