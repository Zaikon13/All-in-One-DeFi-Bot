# GROK_USAGE.md

**Primary Source of Truth (SOT)** — See the SOT table in [GROK_COORDINATION.md](GROK_COORDINATION.md). All Grok-related changes must be coordinated across Primaries (no fragmented updates).

**Purpose**: Complete, canonical map of **all** Grok integrations in the repository (Python runtime call sites, CI workflows, prompts with contracts, quality gates, dependencies, pending items). This is a **Primary SOT** (see GROK_COORDINATION.md SOT table).

**Last Updated**: 2026-06 (coordinated docs update for Grok SOT structure)

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
  - Legacy sync path (`telegram/handlers.py` -> old `calculate_daily_pnl`) is **untouched** (protected per Review gates).
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
  - Trigger: PR opened/synchronize/reopened.
  - Gets diff (truncated), calls via script + `prompts/grok_code_review.txt` (loaded with {diff}).
  - Posts review as PR comment via github-script.
  - `continue-on-error: true`.

- **.github/workflows/health-check.yml**:
  - Trigger: schedule + workflow_dispatch.
  - Checks Railway /health.
  - On failure: calls via script + `prompts/grok_health_check.txt` (loaded with {status}).
  - Creates GitHub Issue with analysis (via github-script).
  - Optional Telegram notify.
  - `continue-on-error: true` (on Grok step + Issue creation).

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

---

## 6. Pending / Incomplete Grok Integrations

- **Runtime**:
  - Full EOD PnL scheduling + reports (worker + Grok).
  - More smart commands: `/smart-report`, `/daily-insight`.
  - Scheduled automations (EOD PnL, Daily Summary, Risk Alerts).
  - Worker integration for Grok (currently indirect via PnL reports).
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