# GROK_USAGE.md

**Primary Source of Truth (SOT)** — See the SOT table in [GROK_COORDINATION.md](GROK_COORDINATION.md). All Grok-related changes must be coordinated across Primaries (no fragmented updates).

**Purpose**: Complete, canonical map of **all** Grok integrations in the repository (Python runtime call sites, CI workflows, prompts with contracts, quality gates, dependencies, pending items). This is a **Primary SOT** (see GROK_COORDINATION.md SOT table).

**Last Updated**: 2026-06-09 (SOT Coordinated PR Helper first inc) (structured Grok market analysis output per Review Agent 2026-06 Approved with Conditions (High risk): 6-section Markdown; analysis only, renamed watchpoints, all 12 conditions + new artifact; Primary SOTs read) (coordinated docs update for Grok SOT structure)

**See also**:
- GROK_COORDINATION.md (central hub + SOT definitions)
- project-awareness.md (agent system + protocols)
- docs/project-status.md (health + workflows)
- AGENTS.md (ownership)

**Standard header used on Primary SOTs**: See GROK_COORDINATION.md SOT table and this GROK_USAGE.md for Grok integrations.

---

## 1. Overview of Grok Usage

- **Model**: grok-4.3 (via xAI API)
- **Endpoint**: https://api.x.ai/v1/chat/completions
- **Secret**: `GROK_API_KEY` (required env; see DEPLOYMENT_SOP.md, .env.example)
- **Core Principle**: `core/grok_client.py` is the **Single Source of Truth (SOT)** for all Python runtime Grok calls, prompt loading, and quality gates. All Python code **must** import from here. CI workflows currently use direct curl (not yet unified).
- **Safe Patterns**: `continue-on-error: true`, quality gates + fallbacks, strict prompt contracts (GROK OUTPUT CONTRACT + TELEGRAM MARKDOWN SAFETY), pre-computed data in Python before prompt.

---

## 2. Python Runtime Integrations (SOT: core/grok_client.py)

### 2.1 Core Client (SOT)
- **File**: `core/grok_client.py`
- **Functions**:
  - `load_prompt(filename: str, **kwargs) -> str`: Loads from `prompts/{filename}`, formats with kwargs. Returns error strings on failure.
  - `call_grok(prompt: str, timeout: float = 45.0) -> str`: Async httpx POST to xAI. Supports caller-controlled timeout. Fixed: model="grok-4.3", max_tokens=600, temperature=0.2, user-only message. Returns error strings on failure (e.g. "Grok API error: ...", "Error calling Grok: ...", "GROK_API_KEY not configured in Railway.").
  - `is_valid_grok_response(text: str | None) -> bool`: **Centralized quality gate**. True only for good, substantial (len > 15), non-error responses. Replaces all previous duplicated startswith checks.
- **Constants**: `GROK_ERROR_PREFIXES` (the 4 error strings above).
- **Config**: `GROK_API_KEY = os.getenv("GROK_API_KEY")` (after load_dotenv()).
- **SOT Comments**: Explicitly marked as SOT for calls, prompts, gates. "All Python runtime code must use this module".

### 2.2 Call Sites (must use client + is_valid_grok_response)
- **app/main.py** (HTTP/Telegram surface):
  - `/grok-analyze` (Telegram command + `/grok/analyze` HTTP endpoint).
  - Fetches live data: `get_wallet_balances` + `get_recent_transactions` (from core/wallet.py).
  - Compacts into summaries (`_get_grok_live_context`).
  - `load_prompt("grok_wallet_analysis.txt", wallet_preview=..., balances_summary=..., recent_txs_summary=...)`.
  - `call_grok(..., timeout=25.0)`.
  - Quality: `if is_valid_grok_response(insight):` else fallback to raw data summary.
  - Telegram path: Immediate "🔄 Generating live Grok analysis..." + `background_tasks.add_task(process_grok_analyze, chat_id)`.
  - HTTP: Direct, returns JSON with `live_context_used`.
- **core/pnl_calculator.py** (for `/daily_pnl`):
  - `get_daily_pnl_report()` (async production path).
  - Pre-computes summaries (trades, movers).
  - `load_prompt("grok_daily_pnl.txt", date=..., wallet_preview=..., total_trades=..., ...)` (from prompts/grok_daily_pnl.txt with strict "GROK OUTPUT CONTRACT" for 3-6 sentence qualitative paragraph only).
  - `call_grok(..., timeout=25.0)`.
  - Quality: `if is_valid_grok_response(insight):` (via SOT helper) then append as "🤖 **Grok Daily Insight:**" else fallback to base report.
  - Production /daily_pnl is handled inside `app/main.py` (FastAPI webhook service, process_daily_pnl() -> get_daily_pnl_report()).
    telegram/handlers.py is legacy polling code and NOT used in production (per Railway deployment analysis June 2026).
    Previous unification commit (bd487f5) was based on incomplete architecture view.
    Legacy sync calc functions (`calculate_daily_pnl`, `get_today_transactions`) deprecated but `format_pnl_report()` retained as internal fallback.
- **Imports**: Always `from core.grok_client import call_grok, load_prompt, is_valid_grok_response`.

### 2.3 Prompts (loaded exclusively via client.load_prompt)
- `prompts/grok_daily_pnl.txt`: For daily PnL insight. Strict contract: ONLY 3-6 sentence qualitative paragraph (no numbers/headers from data). Base only on provided data. TELEGRAM MARKDOWN SAFETY: only **bold** + simple bullets.
- `prompts/grok_wallet_analysis.txt`: For live /grok-analyze. Structure: **Portfolio Overview**, **Key Observations / Risks** (3-5 bullets), **Actionable Recommendations** (numbered, e.g. "Sell X%..."). Strict "base **strictly and only** on live data". No external knowledge. Same Markdown safety.

---

## 3. CI / GitHub Actions Integrations (unified to core/grok_client.py)

Both Grok-calling workflows now reuse the centralized Python client (no more inline curl + duplicated prompts).

- **.github/scripts/call_grok.py**: New CLI helper (added 2026-06).
  - Reuses `core.grok_client.load_prompt()` + `call_grok()` + error handling/quality strings.
  - Supports `prompts/<name>.txt` + `--var key=value` for dynamic context (repeatable).
  - `PYTHONPATH=. python .github/scripts/call_grok.py grok_xxx.txt --var "foo=bar" --timeout 60`
  - Outputs result to stdout (workflows capture into $GITHUB_OUTPUT); falls back gracefully on error.
  - Setup in workflows: `actions/setup-python@v5` (3.12) + `pip install -r requirements.txt python-dotenv`.

- **.github/workflows/grok-code-review.yml**:
  - Trigger: pull_request to branches: [main], types [opened, synchronize, reopened], with paths filter for relevant changes (**.py, .github/workflows/**, prompts/**, core/**, app/**, worker.py, requirements*.txt, railway.toml, docs/**). (Updated 2026-06 per Review Agent "Approved with Conditions" - High Risk).
  - Gets diff (truncated), calls via script + `prompts/grok_code_review.txt` (loaded with {diff}).
  - Uses strict **GROK CODE REVIEW CONTRACT** (redesigned 2026-06 per Review Agent "Approved with Conditions" - High Risk): requires Critical/High/Medium with file:line, SOT & Coordination Alignment, mandatory Documentation & Primary SOT Impact section, High-Risk Files Touched, Project Rule Violations (Review Gate comments, core/ reuse, UTC, Railway ephemeral FS, legacy protection, smallest correct change, etc.), Actionable Recommendations.
  - Posts review as PR comment via github-script.
  - `continue-on-error: true` (advisory/supplementary only; the true mandatory gate is the internal Review Agent pre-edit per project-awareness.md 4.3).
  - # Review Agent 2026-06: Expanded triggers + paths filter per Review decision to run automatically on relevant PRs to main. Remains advisory. Contract enforces full alignment with Primary SOTs, personas, and coordination rules. This CI review supports (does not replace) the Review Gate.

- **.github/workflows/health-check.yml**:
  - Trigger: schedule + workflow_dispatch + workflow_call (minimal post-deploy support).
  - Checks Railway /health (bot web service liveness only; worker service not covered - explicit limitation noted).
  - On failure: calls via script + strict **GROK HEALTH CHECK CONTRACT** in `prompts/grok_health_check.txt` (redesigned 2026-06 per Review Agent "Approved with Conditions" - High Risk): requires Health Summary, Root Cause (Railway), Bot vs Worker Impact, prioritized Action Items, SOT Alignment.
  - Creates GitHub Issue with analysis.
  - Telegram now receives useful Grok-derived content (enriched report) using safe Markdown v1 only.
  - `continue-on-error: true` (advisory; true mandatory gate is internal Review Agent).
  - # Review Agent 2026-06: Contract + Telegram improvements enforce SOT alignment, Markdown safety, non-blocking behavior, and note worker visibility gap.

**Prompts for CI** (in `prompts/` alongside runtime ones, loaded via SOT):
- `grok_code_review.txt`
- `grok_health_check.txt`

Other workflows (ci.yml, sync-check.yml, etc.) have no direct Grok.

See also the implementation in `.github/scripts/call_grok.py` and the two updated workflows.

---

## 4. Dependencies and Environment

- **Required Env**: `GROK_API_KEY` (no fallback in client; error string returned).
  - Listed in: `DEPLOYMENT_SOP.md`, `.env.example`, workflow secrets.
- **Docs References**: All coordination files (see below), agent personas (research/code/review mention "xAI/Grok usage" or require reading coordination).
- **Other**: `GROK_API_KEY` in error checks (now centralized).

---

## 5. Agent & Sub-Agent Usage of Grok

- **System**: Master Agent (Grok) + Sub-Agents (Review is the **mandatory gate** before any code/SOT edit; Code, Execute, Analysis, Research).
- **Handoff**: Always prepend full persona text from `agents/personas/`. Include Primary SOT references + current todo context. Use `spawn_subagent`.
- **Review Gate**: Detailed protocol (when mandatory, output format, recording to `reviews/`, "addressed before proceed") lives in `project-awareness.md` Section 4.3.
- **Personas** (`agents/personas/`): The single source of truth for each agent's detailed rules and output templates. Master must read + include the full persona.
- **Skills**: Bundled `review` is for GitHub PR reviews. Internal Sub-Agent Review is the pre-edit gate. Other skills (pr-babysit, implement, etc.) for specific automation.
- **MCP**: grok_com_github for GitHub ops.

**Phase 1 Orchestrator (2026-06, Review Agent "Approved with Conditions", High Risk)**:
- `agents/orchestrator.py` + `agents/memory/` assists Master (Grok retains final authority; does not replace or bypass Review Gate).
- Loads committed `project_context.md` (SOT-like; meaningful updates high-risk requiring Review + coordinated SOT update) and `agent_memory.json`.
- Uses `core/grok_client.py` (SOT) exclusively for Grok planning. Now uses dedicated `prompts/grok_orchestrator_plan.txt` (strict contract + required output structure including Meta Notes for future self-improvement readiness, without consuming them in Phase 1).
- Plans reference existing handoff (todo_write + full personas + SOTs + spawn_subagent).
- High-risk: must recommend Review Agent first.
- Start simple/script (manual/scheduled). Foundation only.
- See agents/README.md, GROK_COORDINATION.md Section 3, project-awareness.md Section 4.6.
- # Review Agent 2026-06: Per Approved with Conditions. Master authority preserved. Use existing protocol. Memory committed. Coordinated SOT updates (no new Primary SOT).

**Phase 2 first scoped increment — Improvement Proposer (2026-06, Review Agent "Approved with Conditions")**:
- Master-driven only via `agents/orchestrator.py --propose-improvements` (extends the existing orchestrator per condition 10; no new component).
- Reads past Meta Notes + simple outcome data from memory; uses `core/grok_client.py` (SOT) + new focused `prompts/grok_improvement_proposer.txt` (strict "GROK IMPROVEMENT PROPOSER CONTRACT") to generate proposals **only** for prompts (grok_orchestrator_plan.txt first) and memory schema.
- **Proposals only, no auto-apply**. Every proposal section in the Grok output is required (by contract) to contain the full Review Gate enforcement language: requires Review Agent + Master todo_write (merge:false) + full persona prepend + SOT refs + spawn_subagent before any edit. Master authority explicit.
- Minimal memory schema: plan_outcomes append-only (high-risk; documented in 4.7 + notes; full proposals stay in printed output + reviews/ file).
- Scope ruthlessly limited: no worker/core/app/workflow/production changes. Aligns with existing handoff protocol for any follow-on work.
- See project-awareness.md 4.7, GROK_COORDINATION.md Section 3, reviews/2026-06-XX-phase2-feedback-loop.md, and the prompt file for the 10 mandatory conditions and compliance.
- # Review Agent 2026-06: First gated self-improvement readiness increment. "proposals only" + non-bypassable Review language in generated output + coordinated Primary SOT updates. This review decision is the gate for the inc.

**Richer-context increment (higher-quality/specific proposals)**: plan_outcomes "plan" entries may include tiny `meta_summary` (excerpt). propose_improvements passes last ~8 outcomes + meta_summary; prompt now requires pattern detection across history, explicit citations of timestamps/entries, and precise copy-paste-ready suggestions (sections + before/after). Scope and all 9 mandatory conditions preserved (proposals-only, Review Gate paragraph intact and now references new review file, high-risk minimal memory, core client only). See project-awareness.md 4.7 + reviews/2026-06-XX-improve-proposer-quality.md.
# Review Agent 2026-06: Targeted context + prompt improvements for better proposals while keeping every original guardrail.

**Agent Drift Detection (first inc, 2026-06 per Review Agent "Approved with Conditions", High risk)**: New --detect-drift mode + grok_drift_detector.txt. Detects drift vs SOT agent sections, prompt contracts, memory schema, project_context and emits proposals with full Review Gate text. Detection + proposals only. Tiny drift records in plan_outcomes (high-risk). Reuses core/grok_client.py. Detector subject to the system (condition 10). See project-awareness.md extension + reviews/2026-06-XX-agent-drift-detection.md + the 10 conditions.
# Review Agent 2026-06: Proposals-only with non-bypassable gate; Master-driven; minimal high-risk memory; coordinated SOTs.

**Drift Detection v2 (2026-06 per Review Agent "Approved with Conditions", Medium-High risk)**:

**SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent Approved with Conditions, High risk)**: feat(agent): Context Strengthening for Drift v2 + Proposer (bounded reviews/ glob+read cross-refs + structured citation-friendly history bullets + one-sentence citation format tightening). Per Review Agent 2026-06-08 (Approve with minor revisions + 5 conditions addressed exactly by Code Agent subagent). Extend-existing only (agents/orchestrator.py private helpers + 2 prompts + 1 reviews/ traceability file). No SOT edits in the inc itself (per conditions 3+5); this is the follow-on coordinated status update. New logic remains subject to condition 10. Full non-bypassable Review Gate preserved (only ref append). See reviews/2026-06-08-drift-proposer-context-strengthening.md . Master retains final authority. Honest status-only language.. Advisory only (orchestrator --sot-pr-helper). See GROK_COORDINATION.md and reviews/ for usage + 12 conditions.

  **SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent Approved with Conditions, High risk)**: feat(worker): Worker Persistence First Increment addressing all 12 conditions from Review Agent 2026-06-08 (commit 8d322ad). Enhanced known_pairs persistence in worker.py with last_seen timestamps + last_eod_run (backward-compatible migration from old plain list JSON), atomic writes (temp + os.replace), optional RAILWAY_VOLUME_MOUNT_PATH support (fallback 'data/'), and strong WARNING logs + documentation that data is NOT durable across Railway redeploys without attached Volume. Added all required # Review Agent 2026-06-08 comments. Per condition 7: this is a coordinated Primary SOT status update only. Worker Loop status updated to note the first increment for known_pairs (with last_seen, atomic writes, Railway guards) is now in place; remains 'Partially Functional' overall. Full durability across redeploys still requires Railway Volume. EOD scheduling enhancements are minimal reliability state only. No claim that persistence is 'complete' or production-durable.. Advisory only (orchestrator --sot-pr-helper). See GROK_COORDINATION.md and reviews/ for usage + 12 conditions.
 Modest evolution (extend existing; 1-2 addl high-value areas e.g. arg parsing + SOT cross-refs). Smarter bounded context (targeted extraction + recent plan_outcomes/drift summaries for patterns). Evolved prompt requires citations of prior runs + stronger evidence/precise fixes (history for quality only, condition 12). Still proposals-only, full gate (refs v2 review), tiny memory (high-risk), core client only, detector auditable (condition 10). See project-awareness.md + reviews/2026-06-XX-drift-detection-v2.md + 12 conditions.
# Review Agent 2026-06: Bounded v2 per conditions; proposals-only with non-bypassable gate; Master-driven; minimal high-risk memory; coordinated SOTs.

**SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent Approved with Conditions, High risk)**: Added SOT Coordinated PR Helper (--sot-pr-helper) to agents/orchestrator.py per Review Agent Approved with Conditions (High risk). Read-only advisory only. Analyzes change to one SOT and generates ready-to-paste text for the other 4 SOTs. Reuses dry-run logic. All 12 mandatory conditions followed exactly. Primary SOTs read before implementation and on every run. Advisory only (orchestrator --sot-pr-helper). See GROK_COORDINATION.md and reviews/ for usage + 12 conditions. # Review Agent 2026-06

---

## 6. Pending / Incomplete Grok Integrations

- **Runtime**:
  - Full EOD PnL scheduling + reports (worker + Grok).
  - More smart commands: `/smart-report`, `/daily-insight`.
  - Scheduled automations (EOD PnL, Daily Summary, Risk Alerts).
  - Worker integration for Grok (currently indirect via PnL reports + 1 low-risk optional analysis-only path + 1 additional EOD point per second inc): new-pair alerts in poll_dexscreener may append qualitative Grok insight; scheduled EOD PnL reports may append separate **Market Context** (post-process only after get_daily_pnl_report, using exact same thin core/market_analysis.py + grok_market_analysis.txt, no changes to core/pnl_calculator.py or grok_daily_pnl.txt). Env-gated via MARKET_ANALYSIS_ENABLED=false default; 25s + is_valid gate + fallback; pre-compute in Python; analysis/summarization/insights ONLY per strict CONTRACT; no decision/execution use; logged; continue-on-error. Structured 6-section Markdown output enrichment (2026-06 per Review Agent Approved with Conditions, High risk): prompt updated for Summary / Key Metrics / Market Narrative / Risk Signals / Observed Patterns & Contextual Watchpoints (renamed) / Confidence & Data Notes; all prior 12 conditions + new ones followed (analysis only, safe MD, no execution). Full Review Gate (high-risk) + # Review Agent 2026-06 + dedicated reviews/2026-06-XX-grok-market-analysis.md + reviews/2026-06-XX-worker-market-analysis-eod.md + reviews/2026-06-XX-grok-market-analysis-structured.md + coordinated 5-SOT updates (see project-awareness.md 4.7). Still pending broader EOD/smart-command worker Grok work. # Review Agent 2026-06: Structured output inc.
- **CI/Unification**:
  - (Completed) Grok CI workflows now reuse `core/grok_client.py` via `.github/scripts/call_grok.py` + dedicated prompts.
- **Docs/Agent**:
  - (Largely complete) Sub-Agent system + Mandatory Review Gate formalized in Primary SOTs + personas. All future work must follow the protocol.
  - Continue using the system for Worker Loop, smart commands, etc. Update `reviews/` and code comments with Review Agent attributions.
- **Other**:
  - Smart alert filtering using Grok.
  - Better error handling/retry in Grok paths.
  - Tests for Grok (mock client).

**See project-awareness.md Action Plan B and Top Priorities for details.**

---

## 7. Quality Gates & Contracts (Centralized in Client)

- All runtime Grok calls use `is_valid_grok_response(insight)` (len>15 + not error prefix).
- Fallbacks always provided (never worse UX).
- Prompts enforce "GROK OUTPUT CONTRACT (MANDATORY)" + "TELEGRAM MARKDOWN SAFETY (MANDATORY)" (only **bold** + simple •/- bullets; no tables/links/underscores/etc. that break parse_mode="Markdown").
- Callers pre-compute data/summaries in Python; Grok does qualitative insight only.

---

*This file is a Primary SOT. Update in coordination with other Primaries (GROK_COORDINATION.md, project-awareness.md, docs/project-status.md, AGENTS.md). All Grok code changes must keep this map accurate. After changes, re-verify call sites via grep and update "Last Updated".*

**End of GROK_USAGE.md**