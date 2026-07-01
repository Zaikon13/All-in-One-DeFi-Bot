# CLAUDE_INTEGRATION.md

Canonical map of all Claude AI integrations in All-in-One-DeFi-Bot. This is the Claude-native
replacement for the old `GROK_USAGE.md`. When this doc and the code disagree, the code wins —
then fix this doc.

## 1. Overview

- **Provider**: Anthropic (Claude)
- **Runtime model**: `claude-sonnet-4-6`
- **Core principle**: `core/claude_client.py` is the single source of truth for all Claude calls,
  prompt loading, and the quality gate. Both runtime and CI import from it.

## 2. Runtime integration (SOT: `core/claude_client.py`)

- `call_claude(prompt, timeout=45.0)` — async call to Anthropic.
- `load_prompt(filename, **kwargs)` — loads + formats `prompts/<filename>`.
- `is_valid_claude_response(text)` — quality gate (len > 15 and not an error prefix).
- Backward-compat aliases: `call_grok = call_claude`, `is_valid_grok_response = is_valid_claude_response`.
  These let old call sites keep working; rename them to the `claude` names over time.
- **Call sites**: `app/main.py` (Telegram `/grok-analyze` + HTTP `/grok/analyze`, daily PnL),
  `core/pnl_calculator.py` (daily PnL insight).

## 3. CI integration (`.github/scripts/call_claude.py` + workflows)

- `.github/scripts/call_claude.py` — CLI wrapper that reuses `core/claude_client.py` for Actions.
- `.github/workflows/claude-code-review.yml` — advisory PR review (Telegram-safe output).
- `.github/workflows/claude-health-check.yml` — web-service liveness check; opens an issue on failure.
- Both are advisory (`continue-on-error: true`). The legacy Grok workflows (`grok-code-review.yml`,
  `health-check.yml`) still also run alongside these — see §7.

## 4. Prompts (`prompts/`)

- `claude_code_review.txt` — CLAUDE CODE REVIEW CONTRACT.
- `claude_health_check.txt` — CLAUDE HEALTH CHECK CONTRACT.
- (Legacy `grok_*.txt` prompts are provider-agnostic and can be reused or renamed.)

## 5. Agent system (`.claude/agents/`)

Four Claude Code subagents (separate from the legacy Grok `agents/` orchestrator, which still uses
`core/grok_client.py`). They are persona files invoked when you run Claude Code on the repo — nothing
in CI or the running bot calls them automatically.

- **investigator** — evidence-based debugging; read-only + safe diagnostics. Finds the truth and proposes
  fixes; does not edit. *Start here when something is broken or behaving unexpectedly.*
- **researcher** — external research translated to this stack; read-only + web. *Use when you need outside
  knowledge (an API, library, or protocol) before deciding.*
- **reviewer** — the **mandatory quality gate**; read-only. Checks correctness, `core/` reuse, UTC,
  Telegram-Markdown safety, secret hygiene, and whether a doc must be updated. *Run before implementing
  anything non-trivial.*
- **implementer** — makes the approved change; can edit. *Only acts after the reviewer approves (or the
  change is clearly low-risk).*

**Typical sequence:** investigator / researcher (gather evidence) → **reviewer** (gate) → implementer
(apply) → reviewer (confirm). The reviewer is the gate; the implementer proceeds only on its approval.

## 6. Environment variables

- `ANTHROPIC_API_KEY` — required for all Claude features (runtime + CI).
- `GROK_API_KEY` — still required while the Grok CI workflows are kept (see §7); also read by
  `core/grok_client.py` for the gated worker market-analysis and the manual orchestrator.

## 7. Migration status (as of 2026-06-24)

Runtime is fully on Claude. **CI is not yet migrated — it runs both providers in parallel:** the two
Claude workflows (`claude-code-review.yml`, `claude-health-check.yml`) were *added*, but the Grok
workflows (`grok-code-review.yml`, `health-check.yml`) were never removed, so every PR gets both reviews
and the schedule fires both health checks (all advisory / `continue-on-error`). `core/grok_client.py`
(real Grok, `api.x.ai`) is still imported by `call_grok.py` (CI), `core/market_analysis.py` (worker EOD,
gated off by default), and `agents/orchestrator.py` (manual tool). Per standing decision both providers
stay until you explicitly approve retiring Grok; finishing the migration (repoint `call_grok.py`, drop the
Grok workflows + `GROK_API_KEY`, delete `grok_client.py`) is tracked in `IMPLEMENTATION_PLAN.md`.
