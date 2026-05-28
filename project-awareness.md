# project-awareness.md

**Project**: All-in-One-DeFi-Bot  
**Repository**: Zaikon13/All-in-One-DeFi-Bot  
**Last Updated**: 2026-05-28 (by Grok AI Agent System)  
**Purpose**: Single Source of Truth for the Grok AI Agent System operating on this project.

---

## 1. Project Overview

All-in-One-DeFi-Bot is a professional DeFi Telegram bot focused on the **Cronos** ecosystem.

**Core Capabilities**:
- Real-time wallet monitoring & transaction tracking
- Dexscreener new pair discovery with Telegram alerts
- Daily PnL reports
- Grok-powered AI analysis (`/grok-analyze`)
- Background worker for automation

**Deployment**:
- Railway (3 services: `bot`, `web-gpl6` (redundant), `worker`)
- Primary webhook on `bot-production-3d9c`

---

## 2. Current Architecture

| Layer              | Key Files                          | Status                  | Notes |
|--------------------|------------------------------------|-------------------------|-------|
| Web / Telegram     | `app/main.py`, `app/commands/`     | Stable                  | Handles webhook + commands |
| Core Logic         | `core/` (grok_client, wallet, dexscreener, pnl_calculator) | Partially Mature | Needs unification |
| Worker             | `worker.py`                        | Partially Functional    | Real alerts active, missing persistence & EOD PnL |
| Deployment         | `railway.toml`, `Dockerfile`, `DEPLOYMENT_SOP.md` | Needs Cleanup     | Some drift remains |
| CI/CD + Automation | `.github/` + Dependabot            | Strong                  | Good coverage |
| Documentation      | Root `.md` files + `docs/`         | Good but Inconsistent   | Major updates done in May 2026 |

---

## 3. Current Status (as of 2026-05-28)

### What is Working Well
- Worker Loop: Real new pair alerts + basic JSON persistence for known pairs + basic wallet monitoring + heartbeat
- GitHub Actions: Multiple clean workflows (sync-check, health-check, grok-code-review, dependency-check)
- Dependabot: Active for pip, GitHub Actions, and Docker
- Stale PR cleanup: 8 old PRs closed via pr-babysit skill
- Documentation: Significantly improved (GROK_COORDINATION.md as central hub)

### Known Issues / Gaps
- **Worker Loop**:
  - Basic persistence for `known_pairs` via JSON file (added 2026-05-28)
    - Survives in-process and local restarts.
    - Does **not** survive Railway redeploys without a Volume (documented limitation + TODO).
  - No EOD PnL scheduling
  - `monitor_wallet()` is still basic
  - Start command references are inconsistent in some docs

- **Config Drift**:
  - Some docs still reference old `RAILWAY_CONFIG.md`
  - Worker start command drift mentioned in coordination docs

- **Legacy Content**:
  - Old ChatGPT/Codex references in secondary files
  - Some outdated documentation (README_SYNC.md, MANIFEST.md, SUMMARY.md)

- **Grok AI Integration**:
  - Sub-agent usage is improving but not yet standardized
  - No formal "Grok Native Sub-Agents" framework defined yet
  - Limited scheduled automations

---

## 4. Grok AI Agent System Setup (Native Sub-Agents Architecture)

**Master Agent**: Grok (you) — The central coordinator and decision maker.

**Permanent Knowledge Base** (must be read at the start of every complex task or new session):
- `GROK_COORDINATION.md`
- `AGENTS.md`
- `project-awareness.md` (this file)

### Sub-Agent Roles & Personas

The following specialized Sub-Agents are defined in `agents/personas/`:

| Sub-Agent       | Primary Responsibility                          | Key Constraints                          | When Master Delegates |
|-----------------|------------------------------------------------|------------------------------------------|-----------------------|
| **Review Agent**    | Mandatory code/design review before implementation or merge | Never implements changes itself; focuses on risks, correctness, and project rules | Before any search_replace/write on code |
| **Code Agent**      | Implements features and fixes following instructions | Smallest correct change; follows existing patterns; reuses core/ when possible | After Review Agent approval |
| **Execute Agent**   | Runs commands, tests, git operations, and deployment steps | Never performs destructive actions without explicit Master confirmation | For testing, builds, git ops, local execution |
| **Analysis Agent**  | Deep analysis of code, logs, behavior, or data | Evidence-based; distinguishes facts from hypotheses | When debugging, understanding gaps, or evaluating options |
| **Research Agent**  | Investigates external libraries, APIs, patterns, or best practices | Focuses on practical, production-relevant information aligned with current stack | When evaluating new tools, APIs, or architectural options |

Detailed personas are stored in:
- `agents/personas/review-agent.md`
- `agents/personas/code-agent.md`
- `agents/personas/execute-agent.md`
- `agents/personas/analysis-agent.md`
- `agents/personas/research-agent.md`

### Handoff Protocol (Master → Sub-Agent)

1. Master creates a clear, self-contained task prompt.
2. Master includes references to `project-awareness.md`, `GROK_COORDINATION.md`, and specific file paths.
3. Master prepends the relevant persona to the prompt.
4. Master calls `spawn_subagent` (with appropriate `subagent_type` and `background` when needed).
5. Sub-Agent produces structured output (often to a file or clear sections).
6. Master reviews the output (especially mandatory for Review Agent).

### Plan Mode Discipline

- **Default for any non-trivial task** (anything with >3 steps, ambiguity, or architectural impact).
- Master must open with `todo_write` (merge:false) and explicit planning before delegating or making changes.
- Complex work should usually go through a planning cycle before execution.

### Mandatory Auto Code Review Gate

- **No code changes** (via `search_replace`, `write`, or direct edits) are allowed without first spawning the Review Agent on the proposed change.
- The Review Agent's output must be read and addressed before proceeding.

### Master Agent Coordination Principles

- The Master Agent retains final decision authority.
- Delegation happens via clear, written prompts + todos rather than vague instructions.
- The Master Agent maintains the global view using `project-awareness.md` and `GROK_COORDINATION.md`.
- Sub-Agents are tools — the Master Agent is responsible for orchestration, synthesis, and quality.

---

## 5. Key Priorities (Current)

1. Complete Worker Loop (persistence, EOD PnL, robustness)
2. Full Grok AI Agent System activation (Master + Sub-Agents + Automations)
3. Final documentation & config consistency cleanup
4. Railway service alignment (web-gpl6 deprecation)
5. Smart bot commands + scheduled automations

---

## 6. Action Plan — Path to Production Ready + Full Grok AI Integration

### All Necessary Actions (Comprehensive List)

**A. Worker Loop Completion**
- Add persistence for `known_pairs` (JSON file or database)
- Implement proper EOD PnL scheduling
- Improve `monitor_wallet()` with better change detection
- Add configurable thresholds and better error handling
- Full integration with core modules

**B. Grok AI Agent System Activation**
- Formalize Master Agent + Sub-Agent roles (Code, Review, Execute, Analysis, Research)
- Implement Auto Code Review before any code changes (using Review Agent)
- Develop Smart Commands: `/grok-analyze`, `/smart-report`, `/daily-insight`
- Set up Scheduled Automations (EOD PnL, Daily Summary, Risk Alerts)
- Create standard context headers and quick-sync prompts

**C. Documentation & Architecture Consistency**
- Resolve all remaining Config Drift (especially worker start command)
- Clean up or deprecate legacy files (README_SYNC.md, MANIFEST.md, etc.)
- Fully align all docs with GROK_COORDINATION.md and project-awareness.md
- Remove references to non-existent `RAILWAY_CONFIG.md`

**D. Railway & Deployment Hygiene**
- Decide on and execute `web-gpl6` deprecation
- Ensure 100% consistency between `railway.toml`, Dockerfile, Procfile, and docs

**E. Automation & Tooling**
- Activate pr-babysit as a scheduled/background process for remaining PRs
- Improve Grok Code Review workflow integration
- Set up better monitoring and alerting for the worker

**F. Testing & Reliability**
- Add basic tests for critical worker paths
- Improve error handling and retry logic across the board

---

## 7. Top 5 Priorities (Ranked)

1. **Formalize and Activate Grok Native Sub-Agents System**  
   (Master Agent + Code/Review/Execute/Analysis/Research agents, with Plan Mode by default and Auto Code Review)

2. **Complete Worker Loop Core Features**  
   (Persistence for known pairs + EOD PnL scheduling)

3. **Resolve Final Config Drift & Documentation Inconsistency**  
   (Make worker start command and service roles 100% consistent everywhere)

4. **Clean Up Remaining Stale / Low-Value PRs**  
   (#12 and any others that no longer add value)

5. **Develop Initial Smart Commands**  
   (`/grok-analyze`, `/smart-report`, `/daily-insight`) as the first user-facing Grok features

---

## 8. Immediate Next Step

**We will now enter Plan Mode** for Priority #1 (Formalizing the Grok Native Sub-Agents System), as this is the foundational piece for everything else.

---

**This document is the living awareness source for the Grok AI Agent System.** All agents and sessions must read it at the start of work.