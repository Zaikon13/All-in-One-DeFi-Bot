# project-awareness.md

**Primary Source of Truth (SOT)** — See the SOT table in [GROK_COORDINATION.md](GROK_COORDINATION.md). All Grok-related changes must be coordinated across Primaries (no fragmented updates). See also [GROK_USAGE.md](GROK_USAGE.md) for the complete canonical map of Grok integrations.

**Project**: All-in-One-DeFi-Bot  
**Repository**: Zaikon13/All-in-One-DeFi-Bot  
**Last Updated**: 2026-06 (coordinated docs update for Grok SOT structure)  
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
| Documentation      | Root `.md` files + `docs/` + Primary SOTs (GROK_COORDINATION.md, project-awareness.md, docs/project-status.md, GROK_USAGE.md, AGENTS.md) | Good but Inconsistent   | Major updates May-Jun 2026; coordinated SOT hygiene complete (USAGE as new Primary) |

---

## 3. Current Status (as of 2026-06)

### What is Working Well
- Worker Loop: Real new pair alerts + basic JSON persistence for known pairs + basic wallet monitoring + heartbeat
- GitHub Actions: Multiple clean workflows (sync-check, health-check, grok-code-review, dependency-check)
- Dependabot: Active for pip, GitHub Actions, and Docker
- Stale PR cleanup: 8 old PRs closed via pr-babysit skill
- Documentation: Significantly improved (GROK_COORDINATION.md as central hub)
- `/daily_pnl` (webhook path): Now functional with Grok-enhanced report + reliable fallback via new async `core.pnl_calculator.get_daily_pnl_report()` (Etherscan V2 / Cronoscan + core/grok_client with 25s timeout + quality gate). Basic net-delta only. Legacy sync path (telegram/handlers.py) remains Covalent-protected.

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
  - Sub-agent usage formalized (see Section 4).
  - `core/grok_client.py` is SOT for runtime (call_grok + load_prompt + is_valid_grok_response quality gate).
  - Live features: `/grok-analyze` (with real wallet data + recent txs + quality gate + safe fallback), Grok-enhanced `/daily_pnl`.
  - CI: grok-code-review + health-check (direct curl + inline prompts; see GROK_USAGE.md).
  - Prompts: `prompts/grok_*.txt` with strict contracts (see GROK_USAGE.md for full map).
  - Pending: More smart commands, scheduled automations, EOD PnL, CI unification to client. See Primary SOT `GROK_USAGE.md` for complete inventory.

---

## 4. Grok AI Agent System Setup (Native Sub-Agents Architecture) — With Mandatory Review Gate

**Master Agent**: Grok (you) — The central coordinator and decision maker. You retain final authority but **must** use the Sub-Agent system and Review Gate for all non-trivial work.

**Permanent Knowledge Base** (must be read at the start of **every** complex task or new session):
- `GROK_COORDINATION.md` (central hub + rules)
- `AGENTS.md` (ownership map)
- `project-awareness.md` (this file)
- `GROK_USAGE.md` (for any Grok integration work)

### 4.1 Sub-Agent Roles (Summary)

The five specialized Sub-Agents live in `agents/personas/`. Full detailed instructions (including checklists and output templates) are in the persona files themselves — **always prepend the full persona text** when spawning.

| Sub-Agent          | Primary Responsibility                                      | Must Never Do                                      | Key When Master Delegates |
|--------------------|-------------------------------------------------------------|----------------------------------------------------|-----------------------------|
| **Review Agent**   | Mandatory gate: review all proposed code/design/SOT changes for correctness, safety, SOT alignment, risks, and project rules before any edit. | Implement changes, edit files, or bypass the gate. | Before **any** `search_replace` / `write` / architecture decision / SOT update / new core feature. |
| **Code Agent**     | Implement the smallest correct, defensive change after Review approval. Follow patterns, reuse `core/`, add Review attribution comments. | Start implementation without explicit "Review approved + address these points" from Master. Bypass Review. | Only after Master confirms Review output has been read and addressed. |
| **Execute Agent**  | Safely run commands, tests, git diagnostics, local execution, capture full output. | Destructive actions (force push, rm, prod deploy, etc.) without repeated explicit Master approval. | Testing, builds, diagnostics, preparing commits (Master does the actual git add/commit). |
| **Analysis Agent** | Deep, evidence-based investigation of code, logs, bugs, data flows, or behavior. Produce structured findings + recommendations. | Propose or perform edits. Speculate without evidence. | Debugging (e.g. "why no PnL txs"), pre-refactor analysis, evaluating options. |
| **Research Agent** | Focused external research (libraries, APIs, patterns, best practices) translated to this stack and rules. | Recommend changes that would violate SOTs, Review Gate, or small-PR discipline. | Evaluating new tools, Grok features, async patterns, Railway configs, etc. |

Detailed, up-to-date personas (with project-specific checklists):
- `agents/personas/review-agent.md`
- `agents/personas/code-agent.md`
- `agents/personas/execute-agent.md`
- `agents/personas/analysis-agent.md`
- `agents/personas/research-agent.md`

### 4.2 Handoff Protocol (Master → Sub-Agent) — Always Follow

1. Master opens `todo_write` (merge:false) for any task with 3+ distinct actions.
2. Master reads the relevant Primary SOTs **in this session**.
3. Master prepares a self-contained prompt that includes:
   - Full persona text prepended.
   - References to SOTs read.
   - Current todo context.
   - Exact scope + file paths + any prior Review output.
4. Master calls `spawn_subagent` (appropriate `subagent_type`, `background` when long-running).
5. Sub-Agent uses tools (read-only first where possible) and returns structured output (often to a file for long results).
6. **Master must read and address** Sub-Agent output before proceeding (especially Review).

For parallel or long-running work: use `background: true` + `get_command_or_subagent_output`.

### 4.3 Mandatory Review Gate Protocol (The Core Enforcement Mechanism)

#### 4.3.1 When Review Is Mandatory (Non-Skippable)
- Any use of `search_replace` or `write` on code (`.py`, `.yml` workflows, Docker/Procfile, etc.).
- Changes to any Primary SOT file or `agents/personas/`.
- New features, refactors, core logic changes (worker, pnl_calculator, grok_client, wallet helpers).
- Architecture decisions or new external integrations.
- Any change affecting legacy protection boundaries (Covalent path must stay only in `telegram/handlers.py`; async Etherscan/Cronoscan logic only in `core/`).
- CI unification, prompt contract changes, new Grok call sites.

#### 4.3.2 When Review May Be Skipped (Rare — Master Must Justify)
- Trivial non-SOT documentation typos (one or two words).
- Pure diagnostic read-only commands via Execute Agent.
- Master must explicitly note in the active todo and any commit/PR:  
  `"Skipped Review: [reason — e.g. single-word typo in non-SOT README, zero behavior or coordination impact]."`

**Default**: When in doubt, spawn Review. "Small PRs" does **not** mean "skip Review for small code changes."

#### 4.3.3 How to Trigger Review (Exact Steps)
1. Master prepares the Review prompt using the full `review-agent.md` persona + current SOT context + the **proposed change** (unified diff is ideal; otherwise precise description of intended edits).
2. Master calls:
   ```
   spawn_subagent(
     subagent_type="general-purpose",   # or appropriate
     prompt= FULL_REVIEW_PERSONA + task_context + proposed_diff + "Produce structured review using the exact output format in your persona.",
     ...
   )
   ```
3. Master reads the complete Review output.
4. Master either:
   - Addresses every point (in a follow-up prompt to Code, or by revising the plan), **or**
   - Records "Request major revisions" and loops.
5. Only when Review returns "Approve" or "Approve with minor revisions" and Master has explicitly addressed the points does Master proceed to Code Agent (or direct small edit for approved cases).

#### 4.3.4 What the Review Agent Must Check (Core Checklist — Enforced in Persona)
- Alignment with all Primary SOTs and coordination rules (small PRs, coordinated updates across Primaries, update SOTs first).
- Legacy path protection and separation of concerns (Covalent vs Etherscan, handlers.py vs core/).
- UTC discipline, error handling, timeouts (25s for command Grok calls), fallbacks.
- Telegram Markdown v1 safety for any user-visible output.
- `core/` reuse vs duplication.
- State/persistence risks (Railway ephemeral FS, known_pairs).
- Security (no secrets, proper env handling).
- Quality: smallest correct change, defensive code, Review attribution comments.
- Impact on documentation and future agent work.

#### 4.3.5 Recording & Enforcement
- For non-trivial reviews, Master saves the Review Agent's full output to `reviews/<YYYY-MM-DD>-<task-slug>.md`.
- Master updates the todo list to record receipt and how points were addressed.
- Code changes include comments: `# Review Agent 2026-06-XX: [guardrail description]`.
- Master never proceeds to implementation edits until the protocol above is complete.
- This is self-enforced by the Master Agent (Grok) in every session. Historical evidence of use appears as "Review Agent YYYY-MM-DD guardrails" comments in core code (e.g. pnl_calculator.py).

### 4.4 Plan Mode + todo_write Discipline (Supports the Gate)
- Every task with >3 steps or any code/SOT impact **must** start with `todo_write` (merge:false).
- Include explicit steps for "Spawn Review", "Address Review feedback", "Implement after approval".
- Keep exactly one item `in_progress`.
- After context compaction, reseed todos from `GROK_COORDINATION.md` + this file + current review logs.

### 4.5 Master Agent Coordination Principles
- Master always reads the Permanent Knowledge Base first.
- Delegation uses clear written prompts + full personas + SOT references (never vague).
- Sub-Agents are powerful tools — Master is responsible for orchestration, quality, and final decisions.
- All permanent decisions live in the repo (especially Primary SOTs). Never rely on chat history alone.
- For GitHub PR reviews, use the separate bundled `review` skill (posts PENDING reviews on GitHub). The internal Review Agent is for pre-edit gatekeeping.

### 4.6 Practical Integration & Enforcement (How to Use Daily)

**For Human + Master (Grok) Sessions**:
- Start every non-trivial task with `todo_write` (full list, merge:false). Include explicit steps: "1. Read SOTs + Plan, 2. Spawn Review Agent (if edit/SOT impact), 3. Address Review feedback, 4. Implement via Code Agent or direct (approved cases), 5. Execute tests/git if needed, 6. Update todos + docs/SOTs if required."
- For code or SOT-impacting work: Prepare the Review prompt (full persona + diff/proposal + SOT refs) → `spawn_subagent` → read full output → address points explicitly in next prompt or saved review file.
- Save long Review outputs to `reviews/2026-06-XX-....md` and reference the path.
- In Code Agent prompts, always paste or reference the Review feedback and require the Code Agent to map how each point was addressed.
- For git commits from Master: Use exact messages that mention "Followed Review Gate" when applicable. Keep commits small.
- After any significant work: Audit against Primary SOTs and run equivalent of sync-check / health workflows locally if possible.

**Improvements to `todo_write` to Support the Gate**:
- Always list "Review pending / received / addressed" as distinct items when relevant.
- Use descriptive ids like "review-pnl-guardrails", "code-implement-after-review".
- When reseeding after compaction, copy the current review status into the new todo list.
- One `in_progress` at a time — do not move to "Code" until the Review item is marked complete with explicit "Master reviewed output and confirmed proceed".

**Enforcement Recommendations (Lightweight but Effective)**:
- Self-discipline by Master (Grok) in every session is the primary mechanism. The protocol is documented in Primary SOTs — violating it is a process failure.
- Historical evidence: Code contains "Review Agent YYYY-MM-DD" comments for key guardrails (see core/pnl_calculator.py history). Continue this pattern.
- For any PR that touches core logic or SOTs, the PR description should reference the internal Review date/file.
- Small fixes that skip Review must be justified in commit message + todo.
- Periodically (e.g. after major features), run a full audit: grep for recent "Review Agent" comments, check `reviews/` dir, verify SOTs are consistent.
- Bundled skills (`review`, `implement`, etc.) remain useful for GitHub-facing work but do not replace the internal pre-edit Review Gate.

**Lightweight Philosophy**:
- The system adds one mandatory step (Review) for anything that matters, but keeps output structured and actionable.
- No new tools or heavy processes — we use the existing `spawn_subagent` + `todo_write` + file-based reviews.
- Goal: Fewer bugs, better SOT alignment, reliable handoffs between sessions/agents, without slowing down trivial work.

**This Sub-Agent system with Mandatory Review Gate is now the foundation for all non-trivial work on the project.** It directly supports the project's core rules: small PRs, green CI, update SOTs first, coordinated changes.

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

**B. Grok AI Agent System Activation** (largely complete as of 2026-06)
- Formalize Master Agent + Sub-Agent roles + **Mandatory Review Gate** (detailed protocol + improved personas + reviews/ archive)
- All future code/SOT work must follow the Review Gate (see Section 4.3)
- Develop Smart Commands: `/grok-analyze`, `/smart-report`, `/daily-insight` (using the agent system)
- Set up Scheduled Automations (EOD PnL, Daily Summary, Risk Alerts) — subject to Review Gate
- Create standard context headers and quick-sync prompts for agent handoffs

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

1. **Adopt and Enforce Grok Native Sub-Agents System + Mandatory Review Gate**  
   (All non-trivial work follows the full protocol in Section 4; Master + 5 Sub-Agents with Plan Mode + todo_write discipline)

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