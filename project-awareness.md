# project-awareness.md

**Primary Source of Truth (SOT)** — See the SOT table in [GROK_COORDINATION.md](GROK_COORDINATION.md). All Grok-related changes must be coordinated across Primaries (no fragmented updates). See also [GROK_USAGE.md](GROK_USAGE.md) for the complete canonical map of Grok integrations.

**Project**: All-in-One-DeFi-Bot  
**Repository**: Zaikon13/All-in-One-DeFi-Bot  
**Last Updated**: 2026-06-08 (SOT Coordinated PR Helper first inc) (structured Grok market analysis output per Review Agent 2026-06 Approved with Conditions (High risk): 6-section Markdown enrichment; analysis only, renamed watchpoints section per conditions, all prior 12 + new artifact; Primary SOTs read) (coordinated docs update for Grok SOT structure)  
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
- `/daily_pnl`: Production implementation is in `app/main.py` (FastAPI webhook handler at /telegram/webhook, process_daily_pnl() calls core.pnl_calculator.get_daily_pnl_report() for Etherscan V2 async path with Grok-enhanced report + Top Movers + reliable fallback, 25s timeout + quality gate). telegram/handlers.py is legacy polling code and NOT used in production (per Railway deployment analysis June 2026). Previous unification view (bd487f5) was based on incomplete architecture. Legacy sync Covalent calc functions deprecated (format_pnl_report retained for internal fallback in production path). Basic net-delta only.

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

This protocol uses a **risk-based, smart & balanced** approach. The goal is strong protection for the parts of the system that are hardest to recover from (core logic, legacy boundaries, SOT consistency, state management, external API safety) while keeping friction low for safe, low-impact work. Master retains flexibility for borderline cases but must document decisions for traceability.

#### 4.3.0 Risk-Based Classification

**High-Risk Changes (Review is Mandatory — routine skips not accepted):**
- Any modification to files under `core/` (grok_client.py, pnl_calculator.py, wallet.py, dexscreener.py and related helpers).
- `worker.py` (WorkerLoop class, polling, wallet monitoring, persistence/known_pairs logic, heartbeat).
- `app/main.py` (webhook handling, command dispatch, process_* functions, Grok call sites and live context).
- `telegram/handlers.py` (legacy polling code, not used in production; see Railway analysis June 2026 - especially anything touching the legacy Covalent sync path or command routing).
- All Primary SOT files: GROK_COORDINATION.md, project-awareness.md, docs/project-status.md, GROK_USAGE.md, AGENTS.md.
- `agents/personas/` (particularly review-agent.md and code-agent.md).
- `.github/workflows/` (any workflow, especially those involving Grok, health, deploy, CI).
- New external API integrations or changes that affect prompt contracts, Grok output safety (Markdown rules), or call patterns.
- Architecture decisions, major refactors, or new features that touch state, reliability, or coordination rules.

For high-risk changes, the Code Agent persona will refuse to implement without explicit Review approval (or an exceptional documented Master override with strong rationale). Skips are exceptional only.

**Low-Risk Changes (Review strongly recommended but skippable with short justification):**
- Pure spelling, grammar, formatting, or minor wording fixes in non-SOT documentation (e.g. WORKER.md examples, README clarifications that do not change rules or behavior descriptions).
- Very small non-behavioral additions: comments, docstrings, or type hints (< 5 lines, no logic change) outside high-risk files.
- Cosmetic / non-functional changes with zero impact on behavior, SOTs, legacy paths, or external calls (e.g. consistent variable naming in an isolated supporting script).

For low-risk: Master may skip Review. Justification is required for traceability (see 4.3.2).

**Medium / Borderline (Review strongly encouraged):**
- Small bug fixes or improvements outside the high-risk list.
- Updates to supporting docs that describe existing behavior.
- Minor safe refactors in non-core areas.

Master has discretion to classify borderline items and must record the classification + whether Review was performed or skipped (with justification) in the todo list.

**Master Flexibility**: In truly ambiguous cases, Master decides the tier and documents the reasoning. The system is designed to protect what matters most without blocking useful small progress.

#### 4.3.1 When Review Is Mandatory (High-Risk — Non-Skippable by Default)
- Any use of `search_replace` or `write` on high-risk files or areas listed in 4.3.0.
- Changes to any Primary SOT file or `agents/personas/`.
- New features, refactors, core logic changes (worker, pnl_calculator, grok_client, wallet helpers).
- Architecture decisions or new external integrations.
- Any change affecting legacy protection boundaries (Covalent path must stay only in legacy `telegram/handlers.py` which is not the production runtime; async Etherscan/Cronoscan logic only in `core/`). Production Telegram bot uses `app/main.py` webhook. (Reference: Railway deployment analysis June 2026).
- CI unification, prompt contract changes, new Grok call sites in production paths.

#### 4.3.2 When Review May Be Skipped (Low-Risk Only — With Justification for Traceability)
Low-risk changes (per the classification in 4.3.0) may skip the full Review Agent process.

**Standard Justification Format (required in both the current todo list and the commit message):**
```
Skipped Review (low-risk): [1-2 sentence reason, e.g. "Pure spelling/grammar fix in WORKER.md section describing existing behavior. No rules, logic, SOT claims, or external behavior changed."] Classification: low-risk per project-awareness.md 4.3.0. Impact: none on SOTs, legacy paths, core logic, state, or safety.
```

For high-risk or medium changes, skips are not routine. An exceptional override requires a much stronger justification:
```
Skipped Review (high-risk exceptional override): [detailed rationale explaining why waiting for Review would cause disproportionate harm + what mitigations are in place + explicit Master acceptance of risk]. Classification noted in todo. Will follow up with retroactive review if possible.
```

**Default Rule**: When in doubt, treat as high-risk and spawn Review. "Small PRs" does **not** mean "skip Review for small code changes in core or SOT areas." The Code Agent will refuse to proceed on high-risk items without proper Review confirmation or exceptional justification.

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
- Legacy path protection and separation of concerns (Covalent vs Etherscan, legacy handlers.py vs core/). Note: telegram/handlers.py is legacy polling and not active in production (app/main.py is the primary FastAPI webhook service per June 2026 Railway analysis). Previous view in bd487f5 was incomplete.
- UTC discipline, error handling, timeouts (25s for command Grok calls), fallbacks.
- Telegram Markdown v1 safety for any user-visible output.
- `core/` reuse vs duplication.
- State/persistence risks (Railway ephemeral FS, known_pairs).
- Security (no secrets, proper env handling).
- Quality: smallest correct change, defensive code, Review attribution comments.
- Impact on documentation and future agent work.

#### 4.3.5 Recording & Enforcement (Lightweight Traceability)
- For any Review performed (high-risk or medium): Master saves the full structured output to `reviews/<YYYY-MM-DD>-<task-slug>.md` when the output is non-trivial. Reference the file in the todo.
- Master updates the active todo list with the review status using this standard format:
  - `review-gate: pending`
  - `review-gate: received 2026-06-XX (high-risk) - summary of recommendation`
  - `review-gate: addressed (points X, Y addressed in [commit or file])`
  - `review-gate: skipped (low-risk): [exact justification sentence]`
- Code changes for high-risk items **must** include comments: `# Review Agent 2026-06-XX: [guardrail description]`.
- Commit messages for high-risk changes should note "Followed Review Gate [date]" (or the exceptional skip justification for rare cases).
- For low-risk skips: the standard justification (see 4.3.2) **must** appear in the commit message.
- Master never proceeds to Code Agent implementation edits on high-risk items until the protocol is satisfied (Code Agent persona will refuse otherwise).
- This is primarily self-enforced by the Master Agent with help from the strengthened Code Agent persona. Historical evidence of good practice appears as "Review Agent YYYY-MM-DD guardrails" comments in core code (e.g. pnl_calculator.py). Periodic light audits (grep for recent Review attributions + check reviews/ dir) are encouraged after major work.

The emphasis is on **traceability and protection of what matters**, not on bureaucracy or punishment for honest low-risk skips.

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

### 4.6 Phase 1 Orchestrator + Shared Memory (2026-06, Review Agent "Approved with Conditions", High Risk)
- `agents/orchestrator.py` + `agents/memory/` (project_context.md + agent_memory.json) is a **tool that assists the Master**, not a replacement. Grok (Master) retains final decision authority.
- Loads committed shared context/memory to reduce repeated SOT re-reading.
- Uses `core/grok_client.py` (SOT) exclusively for Grok planning calls.
- Plans must reference the existing handoff (todo_write + full persona prepended + SOT refs + spawn_subagent).
- High-risk work: must still enforce Review Gate (spawn Review persona or require Master to run it).
- Start simple: script (manual/scheduled). No long-running autonomous daemon or self-improvement in Phase 1.
- `project_context.md` is SOT-like (committed); meaningful updates are high-risk and require Review + coordinated Primary SOT updates.
- `agent_memory.json` is committed for auditability (subject to Railway ephemeral FS risks, like worker known_pairs).
- Sub-agents/ wrappers are convenience only; use official spawn_subagent.
- Traceability: # Review Agent 2026-06 comments in new code. Save reviews to reviews/ (e.g. 2026-06-XX-orchestrator-phase1.md).
- See agents/README.md (Master-Orchestrator relationship) and GROK_COORDINATION.md Section 3.
- All 10 conditions from the Review Agent 2026-06 decision must be followed for implementation.
- Uses dedicated `prompts/grok_orchestrator_plan.txt` (strict contract) for planning (added 2026-06 per Review Agent Approved with Conditions).

### 4.7 Phase 2: Gated Self-Improvement Readiness (first scoped increment, Review Agent 2026-06 "Approved with Conditions")
**Scoped MVP (ruthlessly minimal per condition 10)**: Extend the existing `agents/orchestrator.py` with a `--propose-improvements` mode + one new focused prompt (`prompts/grok_improvement_proposer.txt`). The mode reads past Meta Notes + simple outcome data from memory (plan_outcomes, run_history, notes, last_task), calls Grok exclusively via `core/grok_client.py`, and generates structured proposals **only** for improving prompts (starting with `grok_orchestrator_plan.txt`) and memory schema.

- **Proposals only, no auto-apply (conditions 1,8)**: No code may automatically edit prompts, memory files, or any other artifact based on Meta Notes. Full proposal text lives in the printed orchestrator output + reviews/ files. Memory receives only tiny append-only records in `plan_outcomes`.
- **Review Gate enforcement in every proposal (conditions 2,9)**: The prompt contract forces Grok to embed (in every proposal section) the non-bypassable language: "THIS PROPOSAL REQUIRES A REVIEW AGENT STEP BEFORE ANY IMPLEMENTATION. Master must open todo_write (merge:false), read Primary SOTs, prepend full agents/personas/review-agent.md + todo + this reviews/ file, then call spawn_subagent. Only after Review output is read and addressed may Code edits occur. Master authority is final. No script may apply this proposal."
- **Master-driven only (conditions 4,8)**: Invocation via `python agents/orchestrator.py --propose-improvements` (manual or scheduled Execute Agent by Master). Master reviews output and controls all follow-on work.
- **Use existing mechanisms (condition 3)**: core/grok_client.py SOT only. Any real implementation follows the existing spawn_subagent + full persona + SOT handoff (no bypass, no new layers).
- **Memory schema (condition 7)**: Minimal evolution (`plan_outcomes` append-only array of tiny records). Documented high-risk in json notes, prompt, code comments, and this 4.7. Prefer simple appends + printed output over storing full proposals in memory for the first increment.
- **No production impact (condition 1)**: Zero changes to worker.py, core/, app/, workflows, or any runtime logic. Pattern for future "Improvement Curator" components is documented but not implemented.
- **Traceability (condition 5)**: All new code has `# Review Agent 2026-06` comments. This inc is covered by the prior Review decision (this review serves as the gate). Save long outputs to reviews/ (e.g. 2026-06-XX-phase2-feedback-loop.md). Coordinated updates to all 5 Primary SOTs. Future proposal-driven edits require fresh Review + todo + handoff.
- See: agents/orchestrator.py (new mode + comments), prompts/grok_improvement_proposer.txt (full contract), reviews/2026-06-XX-phase2-feedback-loop.md (10-condition compliance checklist), GROK_COORDINATION.md Section 3, GROK_USAGE.md, AGENTS.md, docs/project-status.md.

**Richer-context follow-on increment (higher-quality proposals)**: Subsequent minimal evolution within the same 4.7 envelope (Review Agent 2026-06 Approved with Conditions, Medium-High risk). plan_outcomes "plan" entries may carry a tiny bounded `meta_summary` (excerpt of prior '## Meta Notes for Future Improvement'). propose_improvements now supplies the last ~8 outcomes (with meta_summary when present) and the prompt contract requires pattern detection across history + explicit citations of timestamps/entries + precise copy-paste-ready suggestions. Still strictly proposals-only, Review Gate enforcement paragraph preserved (now also references the new reviews/2026-06-XX-improve-proposer-quality.md), memory evolution remains high-risk and minimal, core/grok_client.py only, no production impact. See new review file + orchestrator.py changes for full compliance with the 9 conditions. Any use of generated proposals remains high-risk and must repeat the full Review + todo_write + coordinated SOT process.

**Agent Drift Detection (first scoped increment, Review Agent 2026-06 "Approved with Conditions", High risk)**: Master-driven only via `agents/orchestrator.py --detect-drift` (extends existing orchestrator per condition 5; no new module). Uses core/grok_client.py + new `prompts/grok_drift_detector.txt` (strict contract) to detect drift in four high-value areas only (SOT agent sections vs implementation; prompt contracts vs orchestrator code; memory schema vs memory-handling code; project_context.md vs current behavior). Produces structured proposals that contain the full non-bypassable Review Gate enforcement paragraph (condition 2). Strictly detection + proposals only (conditions 1,7). Minimal append of tiny "drift_detection" records to plan_outcomes (high-risk, condition 6; full details in printed output + reviews/). Master authority explicit. The detector/prompt/logic are themselves subject to future Improvement Proposer or --detect-drift runs (condition 10). Reuses existing load_shared_memory + handoff protocol. See new reviews/2026-06-XX-agent-drift-detection.md and the 10 mandatory conditions. Any real synchronization (especially SOT/memory changes) remains high-risk and must repeat full Review Gate + coordinated Primary SOT update.

**Drift Detection v2 (per Review Agent 2026-06 "Approved with Conditions", Medium-High risk)**:

  **SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent Approved with Conditions, High risk)**: feat(worker): Worker Persistence First Increment addressing all 12 conditions from Review Agent 2026-06-08 (commit 8d322ad). Enhanced known_pairs persistence in worker.py with last_seen timestamps + last_eod_run (backward-compatible migration from old plain list JSON), atomic writes (temp + os.replace), optional RAILWAY_VOLUME_MOUNT_PATH support (fallback 'data/'), and strong WARNING logs + documentation that data is NOT durable across Railway redeploys without attached Volume. Added all required # Review Agent 2026-06-08 comments. Per condition 7: this is a coordinated Primary SOT status update only. Worker Loop status updated to note the first increment for known_pairs (with last_seen, atomic writes, Railway guards) is now in place; remains 'Partially Functional' overall. Full durability across redeploys still requires Railway Volume. EOD scheduling enhancements are minimal reliability state only. No claim that persistence is 'complete' or production-durable.. Thin read-only extension inside orchestrator. See GROK_COORDINATION Section 3 and the helper audit.
 Modest evolution of the above (conditions 5/11: extend existing; at most 1-2 additional high-value areas justified as high-leverage, e.g. orchestrator arg parsing/mode logic vs docs + SOT cross-refs vs actual reviews/ files). Smarter bounded drift_context in detect_drift() (targeted extraction + recent plan_outcomes/drift history last 5-8 with summaries for patterns). Evolved prompt contract requires explicit citations of prior runs + stronger evidence + precise fixes (history for quality only per condition 12). Still proposals-only, full gate (refs v2 review file), tiny memory (any summary high-risk per condition 6), core client only, extend-existing. Detector (incl. v2 context builder) remains auditable by future runs (condition 10). See new reviews/2026-06-XX-drift-detection-v2.md and the 12 mandatory conditions. Any real work remains high-risk and must repeat full Review Gate + coordinated Primary SOT update.

**SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent Approved with Conditions, High risk)**: Added SOT Coordinated PR Helper (--sot-pr-helper) to agents/orchestrator.py per Review Agent Approved with Conditions (High risk). Read-only advisory only. Analyzes change to one SOT and generates ready-to-paste text for the other 4 SOTs. Reuses dry-run logic. All 12 mandatory conditions followed exactly. Primary SOTs read before implementation and on every run. Thin read-only extension inside orchestrator. See GROK_COORDINATION Section 3 and the helper audit. # Review Agent 2026-06

**Runtime Grok market/token analysis in worker (first inc, per Review Agent 2026-06 "Approved with Conditions", High risk)**: Thin core/market_analysis.py (exclusive use of grok_client SOT) + new prompts/grok_market_analysis.txt (strict contract: analysis/summarization/insights only, base strictly on pre-computed data, safe Markdown, no trading/execution language). 1 integration point in existing poll_dexscreener (new-pair alerts; optional, env-gated MARKET_ANALYSIS_ENABLED default false, 25s timeout, is_valid gate + fallback, logged, continue-on-error, lazy import). Pre-compute in Python; Grok for qualitative only (exact runtime pattern from app/main.py grok-analyze + core/pnl_calculator). No new autonomous loops, no memory bloat (plain logging + reviews/ preferred), clear separation from orchestrator/agent self-improvement (this is production runtime analysis). Full Review Gate applied; # Review Agent 2026-06 comments; coordinated SOT updates. See reviews/2026-06-XX-grok-market-analysis.md + the 12 mandatory conditions. Any expansion is high-risk and must repeat Review + todo + SOT process.

**Second inc (EOD PnL market context, per Review Agent 2026-06 "Approved with Conditions", High risk)**: Exactly one additional point only (post-processing inside scheduled_eod_pnl after get_daily_pnl_report() await). Reuses *exact same* helper + prompt (no core/pnl_calculator.py or grok_daily_pnl.txt changes, no new prompts). Compact pre-computed snapshot (inline proven fetch). Appends separate **Market Context:** section (analysis/insights only). All 12 evolved mandatory conditions followed (env gate reuse, 25s/is_valid/fallback/continue-on-error/lazy, no new loops, no memory bloat, coordinated 5-SOT + new reviews/ file, # Review Agent 2026-06). See new reviews/2026-06-XX-worker-market-analysis-eod.md. Capability itself subject to future gate.

**Structured output enrichment (per Review Agent 2026-06 Approved with Conditions, High risk)**: Prompt now produces 6-section structured Markdown (Summary, Key Metrics, Market Narrative, Risk Signals, Observed Patterns & Contextual Watchpoints [renamed to avoid actionable framing], Confidence & Data Notes). Thin helper update only (docs). All prior safety + 12 conditions preserved + new ones (no execution language, safe MD only, pre-compute unchanged, no pnl changes). Coordinated 5-SOT + new reviews/2026-06-XX-grok-market-analysis-structured.md. # Review Agent 2026-06: Structured inc. The output remains analysis/summarization/insights only.

This first increment deliberately stops at proposal generation. Any expansion (actual application, broader schema, Curator component, worker integration, etc.) requires its own Review Agent cycle and will be high-risk.

### 4.6 Practical Integration & Enforcement (How to Use Daily)

**For Human + Master (Grok) Sessions**:
- Start every non-trivial task with `todo_write` (full list, merge:false). Use the standard `review-gate` status item (see 4.3.5) and include explicit steps: "1. Classify risk tier per 4.3.0, 2. Spawn Review if high-risk or desired, 3. Address or justify skip, 4. Implement via Code Agent (which will refuse if gate not satisfied), 5. Execute tests/git if needed (with destructive approval), 6. Update todos + docs/SOTs + traceability comments/commits."
- For code or SOT-impacting work: Prepare the Review prompt (full persona + diff/proposal + SOT refs) → `spawn_subagent` → read full output → address points explicitly in next prompt or saved review file.
- When prompting the Code Agent, include the exact Review confirmation or low-risk skip justification so it can comply with its preconditions.
- Save long Review outputs to `reviews/2026-06-XX-....md` and reference the path.
- In Code Agent prompts, always paste or reference the Review feedback (high-risk) or skip justification and require the Code Agent to include a gate compliance statement in its output.
- For git commits: High-risk must note Review Gate; low-risk skips must include the standard justification sentence. Keep commits small.
- After any significant work: Audit against Primary SOTs and run equivalent of sync-check / health workflows locally if possible.

**Standard `todo_write` Discipline for the Review Gate** (Required for any edit/SOT work):
- Every relevant todo list **must** include a dedicated item using one of these exact statuses (update it as work progresses):
  - `review-gate: pending (high-risk | low-risk | borderline)`
  - `review-gate: received 2026-06-XX (high-risk) - Review Agent recommendation: ... Key risks noted: ...`
  - `review-gate: addressed - all critical/high points handled in [description or reviews/ file]`
  - `review-gate: skipped (low-risk): [paste the exact 1-2 sentence justification from 4.3.2]`
- Use clear ids, e.g. `- review-gate: pending (high-risk - core/pnl changes)`
- One `in_progress` at a time. Do not advance the implementation step to "in progress" until the review-gate item shows "addressed" or "skipped with justification".
- When reseeding todos after compaction or new session, carry forward the current review-gate status.
- For pure low-risk non-code work, the skip justification can be short but must be present for traceability.

**Enforcement Recommendations (Smart, Lightweight, and Practical)**:
- Primary mechanisms: 
  1. The Code Agent persona now actively refuses to implement high-risk changes without explicit Review confirmation or proper low-risk skip justification in the prompt it receives.
  2. Standardized `review-gate` status in every relevant `todo_write` list (see above).
  3. Traceability in code comments (high-risk) and commit messages (all cases where Review was relevant or skipped).
- Self-discipline by Master remains important, but the Code Agent now provides an automated "refusal" backstop inside the agent workflow.
- Historical evidence: Code contains "Review Agent YYYY-MM-DD" comments for key guardrails (see core/pnl_calculator.py history). Continue and expand this for high-risk changes.
- For PRs touching high-risk areas, the PR description should reference the internal Review (date + reviews/ file if used).
- Low-risk skips must include the standard justification in both todo and commit message (traceability, not punishment).
- Light periodic audits after significant work: `grep -r "Review Agent" --include="*.py" core/ app/ worker.py`, check recent entries in `reviews/`, and spot-check that todo lists used the `review-gate` status.
- Bundled skills (`review`, `implement`, etc.) remain useful for GitHub-facing work but do not replace the internal pre-edit Review Gate.

**Smart & Balanced Philosophy**:
- Risk-based tiers focus strong enforcement (Review mandatory + Code Agent refusal) on high-risk areas that are expensive or dangerous to get wrong (core logic, legacy paths, SOTs, state, external safety).
- Low-risk work has a simple, documented escape hatch with mandatory short justification for traceability.
- Master keeps final judgment on borderline cases and must document the call.
- No new processes or tools: we leverage `spawn_subagent`, `todo_write`, the Code Agent persona as a gatekeeper, and simple text conventions in todos/commits/comments.
- Goal: Real protection where it counts most, minimal friction elsewhere, and clear audit trail — all while staying aligned with the project's culture of small PRs, practical engineering, and defensive coding.

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