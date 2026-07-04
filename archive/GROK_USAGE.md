# GROK_USAGE.md

**Primary Source of Truth (SOT)** — See the SOT table in [GROK_COORDINATION.md](GROK_COORDINATION.md). All Grok-related changes must be coordinated across Primaries (no fragmented updates).

**Purpose**: This is the **Complete Guide to GitHub and Grok AI Features** for the All-in-One-DeFi-Bot project. It serves as the canonical, comprehensive map of **all** Grok integrations (Python runtime call sites, CI workflows, prompts/contracts, quality gates, dependencies) **and** how they synergize with native GitHub platform features (PRs, Actions, Issues, Secrets, branching, reviews). Primary SOT (see GROK_COORDINATION.md).

**Last Updated**: 2026-06-09 (SOT Coordinated PR Helper first inc + Phase 2 worker EOD guard) by Grok AI Coordinator (completed as full guide: confirmed CI unification, added dedicated GitHub + Grok synergies section, marked recent EOD/market analysis complete, updated roadmap with priorities, aligned with project-status.md and Review Agent decisions) (Phase 2: commit 61059a6 addresses reviews/2026-06-09-worker-persistence-phase2.md) (Railway Volume attachment for worker: worker-persistence, 5GB at /data, ID c13adabe-5db7-4050-8d46-2c7c0fa58876)

**See also**:
- [GROK_COORDINATION.md](GROK_COORDINATION.md) (central hub + SOT definitions + coordination protocol)
- [project-awareness.md](project-awareness.md) (agent system, Review Gate protocol, personas, action plans)
- [docs/project-status.md](docs/project-status.md) (health + workflows status)
- [AGENTS.md](AGENTS.md) (ownership & responsibilities)

**Standard header used on Primary SOTs**: See GROK_COORDINATION.md SOT table.

---

## 1. Overview of Grok Usage

- **Model**: grok-4.3 (via xAI API)
- **Endpoint**: https://api.x.ai/v1/chat/completions
- **Secret**: `GROK_API_KEY` (required env; see DEPLOYMENT_SOP.md, .env.example, GitHub Secrets)
- **Core Principle**: `core/grok_client.py` is the **Single Source of Truth (SOT)** for all Python runtime Grok calls, prompt loading, and quality gates. All Python code **must** import from here. **CI workflows are fully unified** (completed June 2026) to reuse the same client via `.github/scripts/call_grok.py` (no more inline curl or duplicated logic).
- **Safe Patterns** (enforced everywhere):
  - `continue-on-error: true` for advisory Grok steps
  - Centralized quality gates + graceful fallbacks
  - Strict prompt contracts (GROK OUTPUT CONTRACT + TELEGRAM MARKDOWN SAFETY)
  - Pre-compute all data/summaries in Python; Grok provides **qualitative insight only**
  - Smallest correct change + Review Gate for all edits

---

## 2. Python Runtime Integrations (SOT: core/grok_client.py)

### 2.1 Core Client (SOT)
- **File**: `core/grok_client.py`
- **Functions**:
  - `load_prompt(filename: str, **kwargs) -> str`: Loads from `prompts/{filename}`, formats with kwargs. Returns error strings on failure.
  - `call_grok(prompt: str, timeout: float = 45.0) -> str`: Async httpx POST to xAI. Supports caller-controlled timeout. Fixed params: model="grok-4.3", max_tokens=600, temperature=0.2, user-only message. Returns error strings on failure.
  - `is_valid_grok_response(text: str | None) -> bool`: **Centralized quality gate**. True only for good, substantial (len > 15), non-error responses. Replaces all previous duplicated checks.
- **Constants**: `GROK_ERROR_PREFIXES` (the 4 error strings).
- **Config**: `GROK_API_KEY = os.getenv("GROK_API_KEY")` (after load_dotenv()).
- **SOT Comments**: Explicitly marked. "All Python runtime code must use this module".

### 2.2 Call Sites (must use client + is_valid_grok_response)
- **app/main.py** (HTTP/Telegram surface):
  - `/grok-analyze` (Telegram command + HTTP `/grok/analyze`).
  - Fetches live wallet data via `core/wallet.py`, compacts summaries.
  - Loads `prompts/grok_wallet_analysis.txt` with context.
  - Calls Grok (timeout 25s). Uses quality gate; falls back to raw summary if invalid.
  - Telegram: immediate feedback + background task.
  - HTTP: returns JSON.
- **core/pnl_calculator.py** (via `app/main.py` for `/daily_pnl`):
  - Pre-computes trade/mover summaries.
  - Loads `prompts/grok_daily_pnl.txt` (strict 3-6 sentence qualitative only contract).
  - Calls Grok. Appends as "🤖 **Grok Daily Insight:**" if valid.
  - Production path is FastAPI webhook in main.py (legacy telegram/handlers.py polling deprecated).
- **Imports**: Always `from core.grok_client import call_grok, load_prompt, is_valid_grok_response`.

### 2.3 Prompts (loaded exclusively via client)
- `prompts/grok_daily_pnl.txt`: Strict GROK OUTPUT CONTRACT + TELEGRAM MARKDOWN SAFETY (only **bold** + simple bullets).
- `prompts/grok_wallet_analysis.txt`: Structured **Portfolio Overview** + **Key Observations / Risks** (bullets) + **Actionable Recommendations** (numbered). Base **strictly on live data only**. Same safety rules.

---

## 3. CI / GitHub Actions Integrations (Fully Unified)

Both Grok-calling workflows reuse the centralized Python client (no inline curl).

- **.github/scripts/call_grok.py** (added 2026-06):
  - CLI wrapper reusing `core.grok_client` functions + error handling.
  - Supports `prompts/<name>.txt --var key=value` (repeatable).
  - Example: `PYTHONPATH=. python .github/scripts/call_grok.py grok_code_review.txt --var "diff=..." --timeout 60`
  - Outputs to stdout for $GITHUB_OUTPUT capture. Graceful fallback on error.
  - Workflow setup: actions/setup-python@v5 + pip install requirements.

- **.github/workflows/grok-code-review.yml**:
  - **Trigger**: `pull_request` to `main` (opened/synchronize/reopened) + paths filter (`**/*.py`, `.github/workflows/**`, `prompts/**`, `core/**`, `app/**`, `worker.py`, `requirements*.txt`, `railway.toml`, `docs/**`).
  - Gets PR diff (truncated), calls via script + `prompts/grok_code_review.txt`.
  - Enforces strict **GROK CODE REVIEW CONTRACT** (redesigned 2026-06 per Review Agent Approved with Conditions - High Risk): Critical/High/Medium issues with file:line, SOT & Coordination Alignment, Documentation & Primary SOT Impact, High-Risk Files, Project Rule Violations (Review Gate, core/ reuse, UTC, Railway ephemeral FS, legacy protection, smallest correct change, etc.), Actionable Recommendations.
  - Posts as PR comment via github-script.
  - `continue-on-error: true` (advisory only). The **true mandatory gate is the internal Review Agent** (project-awareness.md).
  - Expanded triggers/paths per Review Agent decision. Supports (does not replace) Review Gate.

- **.github/workflows/health-check.yml**:
  - **Trigger**: schedule + `workflow_dispatch` + `workflow_call` (post-deploy support).
  - Checks Railway `/health` (web service liveness; worker service gap explicitly noted).
  - On failure or scheduled: calls via script + `prompts/grok_health_check.txt` (strict CONTRACT redesigned 2026-06): Health Summary, Root Cause (Railway), Bot vs Worker Impact, prioritized Action Items, SOT Alignment.
  - Creates GitHub Issue with Grok analysis.
  - Sends enriched, safe Markdown v1 report to Telegram.
  - `continue-on-error: true` (advisory).

**CI Prompts** (alongside runtime, loaded via SOT client):
- `grok_code_review.txt`
- `grok_health_check.txt`

Other workflows (ci.yml, sync-check.yml, dependabot.yml, etc.) have no direct Grok but benefit from Grok reviews and clean CI enforcement.

See `.github/scripts/call_grok.py` and the two workflows for implementation.

---

## 3.5 GitHub Platform Features & Grok AI Integration (Complete Synergy)

This section makes GROK_USAGE.md the **complete guide** by mapping native GitHub capabilities to Grok AI orchestration throughout the full development and operations lifecycle.

### 3.5.1 Pull Requests, Branching & Review Process
- **Branching Strategy**: Feature branches (`feature/`, `docs/`, `fix/`) from `main`. All changes via Pull Requests. Protected `main` (implied by workflow triggers).
- **Smallest Correct Change Principle**: Enforced by Grok reviews, Review Gate, and project rules. One logical change per PR.
- **Mandatory Internal Review Gate** (`project-awareness.md` Section 4.3): Non-bypassable pre-edit step. Master (Grok) + Sub-Agent Review (persona) + `todo_write` + full SOT/persona context before **any** code or Primary SOT edit. Recorded in `reviews/` archive. High-risk changes (funds, core, SOTs, workflows, secrets paths) require explicit Review Agent approval.
- **CI Grok Code Review**: Automated on relevant PRs (advisory layer that reinforces the gate). Structured output per CONTRACT.
- **SOT Coordinated PR Helper** (orchestrator --sot-pr-helper): Advisory tool to generate ready-to-paste update text for the other Primary SOTs when one is changed.

### 3.5.2 GitHub Actions CI/CD + Grok
- Core workflows enhanced or reviewed by Grok: `grok-code-review.yml`, `health-check.yml`, `sync-check.yml`, `ci.yml`.
- Common patterns: `actions/checkout@v5`, `actions/setup-python@v5`, `continue-on-error: true` for non-blocking Grok steps, Python 3.12, Railway deployment integration.
- **Dependabot** (weekly pip/Actions/Docker PRs) + **dependency-check** (security/outdated audit creating Issues): Synergize with Grok reviews to catch issues early.
- **workflow_call** support in health-check for post-deploy validation.

### 3.5.3 Issues, Notifications & Observability
- Health failures or scheduled checks → GitHub Issue (with Grok root-cause + action items) + Telegram alert (enriched Grok Markdown).
- On-demand Grok insights delivered via Telegram bot (`@AllInOneDeFiBot`) and HTTP endpoints.
- Worker heartbeat + new-pair alerts + PnL reports can incorporate optional Grok qualitative layers (env-gated).

### 3.5.4 Secrets, Security & Compliance
- All sensitive values (`GROK_API_KEY`, Railway tokens, Telegram bot token/chat_id, etc.) stored exclusively in **GitHub Secrets** and **Railway Variables**. Never committed to repo.
- Grok reviews explicitly check for secret leaks, unsafe patterns, missing dry_run/simulation, missing slippage controls, etc.
- Code Sentinel / PEP 8 patterns + DeFi hardening rules applied via Review Gate + CI.
- Repo Guardian-inspired health scoring, manifest maintenance, and drift detection adapted into the agent system.

### 3.5.5 Documentation as Code & AI Context
- Primary SOTs kept in sync (this file + GROK_COORDINATION.md + project-awareness.md + project-status.md + AGENTS.md).
- `MANIFEST.md` + `repomix-output.md` (inspired by repo-guardian) for full repo context to AI agents.
- Prompts, personas, and contracts versioned alongside code.
- All autonomous agent actions logged with Review Agent attribution.

### 3.5.6 External Integrations Orchestrated via GitHub + Grok
- **Railway**: Deployment of web (FastAPI/uvicorn) + worker. Health checks + post-deploy workflow_call.
- **Telegram**: Webhook at `/telegram/webhook`, bot commands for Grok features, safe Markdown alerts.
- **xAI API**: Centralized through `core/grok_client.py` for runtime and CI.
- **MCP / GitHub Tools**: `grok_com_github` mentioned for potential deeper GitHub ops (issues, PRs, etc.).

### 3.5.7 Best Practices & Guardrails (Grok-Enforced)
- Repo-first via small, targeted PRs. Keep CI green always.
- Update `docs/project-status.md` (and other SOTs) on status changes.
- Pre- and post-change checks: clean diff (no secrets), CI green, Railway healthy, webhook valid, SOTs aligned.
- Simulate all on-chain actions; use dry_run where applicable.
- Log every action (timestamp | action | status | details | tx | PnL impact).
- High-risk changes → Review Gate + coordinated SOT update.
- Follow DeFi safety (circuit breakers, position sizing, MEV protection, nonce management) — cross-reference `defi-bot` skill patterns.

This synergy turns GitHub into a **Grok-augmented development platform** with autonomous quality, safety, and documentation alignment.

---

## 4. Dependencies and Environment

- **Required Env**: `GROK_API_KEY` (no fallback; client returns error string).
  - Declared in: `DEPLOYMENT_SOP.md`, `.env.example`, GitHub repo secrets, Railway variables.
- **Docs References**: All Primary SOTs and coordination files reference Grok usage and require reading this guide + personas for any agent work.
- **Other**: Centralized error handling in client now covers all paths.

---

## 5. Agent & Sub-Agent Usage of Grok

- **System**: Master Agent (Grok) + Sub-Agents. **Review** is the mandatory non-bypassable gate before any code or Primary SOT edit.
- **Handoff Protocol**: Always prepend full persona from `agents/personas/`. Include Primary SOT refs + current todo context. Use `spawn_subagent`.
- **Review Gate**: Full protocol, output format, `reviews/` recording, and "addressed before proceed" rule in `project-awareness.md` Section 4.3.
- **Personas**: Single source of truth for each agent's rules and templates. Master must include the full persona text.
- **Orchestrator** (`agents/orchestrator.py` + `agents/memory/`): Master planning, improvement proposals (proposals-only), drift detection, SOT PR helper. Uses `core/grok_client.py` exclusively + dedicated prompts (`grok_orchestrator_plan.txt`, `grok_improvement_proposer.txt`, `grok_drift_detector.txt`).
- **Phase 1 (Foundation)**: Basic orchestration, committed memory, high-risk → Review first. Master authority preserved.
- **Phase 2 Increments (Gated Self-Improvement)**: Improvement Proposer, Drift Detection (v1 + v2), SOT Coordinated PR Helper. All proposals-only, full Review Gate language embedded in every output, minimal high-risk memory append-only, coordinated Primary SOT updates, ruthlessly scoped. All Review Agent "Approved with Conditions" (High/Medium-High risk) decisions followed exactly (see individual reviews/2026-06-XX-*.md files).

  **SOT Coordinated PR Helper (first inc, 2026-06 per Review Agent Approved with Conditions, High risk)**: feat(worker): Phase 1 persistence hardening (commit 30521a3). Still 'Partially Functional'. Volume still REQUIRED for production durability. No SOT changes in this commit (deferred to follow-on via --sot-pr-helper).. Advisory only (orchestrator --sot-pr-helper). See GROK_COORDINATION.md and reviews/ for usage + 12 conditions.

  **SOT Coordinated PR Helper (Phase 2, 2026-06 per Review Agent "Approve with minor revisions")**: feat(worker): Phase 2 EOD PnL guard hardening + startup sanity (commit 61059a6). Addresses Review Agent 2026-06-09-worker-persistence-phase2.md (all 3 Medium issues addressed). EOD PnL guard + startup sanity hardening only (in-process / local-restart behavior only). Still 'Partially Functional'. Volume still REQUIRED for production durability. No over-claims on EOD completeness. Scheduler/target/sleep/report generation and core/ untouched. No SOT changes in this commit (deferred to follow-on via --sot-pr-helper).. Advisory only (orchestrator --sot-pr-helper). See GROK_COORDINATION.md and reviews/ for usage + 12 conditions.

  **Railway Volume (worker)**: Volume attached (5GB at /data). Persistence now survives redeploys as long as the Volume remains attached. Still 'Partially Functional'. Full durability depends on Volume + active subscription.
- **Skills Synergy**: Bundled skills (repo-guardian, code-sentinel, pep8-code-reviewer, orchestrator, defi-*) provide patterns and inspiration adapted here. Internal Sub-Agent Review is the project-specific gate.

All future agent work must respect the Review Gate, SOT coordination, and core client SOT.

---

## 6. Pending / Incomplete Grok Integrations & Future Roadmap

**Recently Completed (June 2026 Review Agent Approved with Conditions)**:
- Structured 6-section Grok **Market Context / EOD analysis** enrichment (Summary / Key Metrics / Market Narrative / Risk Signals / Observed Patterns & Contextual Watchpoints / Confidence & Data Notes). Worker integration path (env-gated `MARKET_ANALYSIS_ENABLED=false` default), analysis/summarization only, safe Telegram MD, pre-compute in Python, is_valid gate, continue-on-error, full Review Gate + 5-SOT coordination + dedicated review artifacts. No execution/decision use.

**Remaining Roadmap Items** (prioritized per project-awareness.md Action Plan B & Top Priorities):
- Full scheduled **EOD PnL + combined reports** (worker execution + Grok daily qualitative insight + market context) with proper persistence and change detection.
- Additional **smart Telegram commands** (`/smart-report`, `/daily-insight`) and Grok-powered alert filtering / risk signals.
- Deeper **worker integration** for new-pair alerts (optional qualitative Grok insight on high-potential pairs).
- Reliability hardening: retry logic with exponential backoff, timeout tuning, and comprehensive tests (mock `core/grok_client.py`).
- Expand sub-agent / MCP capabilities for richer GitHub automation (e.g. auto Issue/PR management beyond current).
- Weekly autonomous drift scans or improvement proposals (if confidence high and Review Gate passed).

**Guiding Rule for All Pending Work**: Proposals or implementations must follow the full Review Gate protocol, update coordinated Primary SOTs, reuse `core/grok_client.py`, stay analysis/insight-only where on-chain decisions are involved, and produce auditable artifacts in `reviews/`.

See `project-awareness.md` for detailed action plans and persona requirements.

---

## 7. Quality Gates & Contracts (Centralized in Client)

- All runtime Grok calls validated by `is_valid_grok_response(insight)` (len > 15 AND not an error prefix).
- Fallbacks always provided (never degrades UX).
- Every prompt enforces **GROK OUTPUT CONTRACT (MANDATORY)** + **TELEGRAM MARKDOWN SAFETY (MANDATORY)**: only **bold** and simple • / - bullets. No tables, links, underscores, or complex formatting that breaks `parse_mode="Markdown"`.
- Callers **always pre-compute** data and summaries in pure Python. Grok is used **exclusively for qualitative insight, observations, and recommendations**.

---

*This file (GROK_USAGE.md) is a Primary SOT and the Complete Guide to GitHub + Grok AI Features. Any change to Grok integration, prompts, client, workflows, or agent behavior must keep this document accurate and must be coordinated across all other Primary SOTs. After edits, re-verify call sites (grep), run Review Gate if high-risk, update "Last Updated", and preferably use the SOT Coordinated PR Helper. CI must remain green.*

**End of Complete Guide to GitHub and Grok AI Features (GROK_USAGE.md)**
