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
- Both are advisory (`continue-on-error: true`).

## 4. Prompts (`prompts/`)

- `claude_code_review.txt` — CLAUDE CODE REVIEW CONTRACT.
- `claude_health_check.txt` — CLAUDE HEALTH CHECK CONTRACT.
- (Legacy `grok_*.txt` prompts are provider-agnostic and can be reused or renamed.)

## 5. Agent system (`.claude/agents/`)

Four Claude Code subagents replace the old Grok personas:
- **reviewer** — mandatory quality gate (read-only).
- **implementer** — makes the approved change (can edit).
- **investigator** — evidence-based debugging (read-only + safe diagnostics).
- **researcher** — external research translated to this stack (read-only + web).

## 6. Environment variables

- `ANTHROPIC_API_KEY` — required for all Claude features (runtime + CI).
- `GROK_API_KEY` — only needed if the legacy Grok CI is kept; not needed once fully on Claude.

## 7. Migration status

Runtime is on Claude. CI moves to Claude via the files in this scaffold. Once
`.github/scripts/call_claude.py` + the two Claude workflows replace the Grok ones and nothing
imports `core/grok_client.py`, delete `grok_client.py` and drop `GROK_API_KEY`.
