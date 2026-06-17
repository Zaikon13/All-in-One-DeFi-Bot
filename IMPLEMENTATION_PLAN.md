# IMPLEMENTATION_PLAN.md

Stabilization & reconciliation plan for **All-in-One-DeFi-Bot**. Designed to be executed by
Claude Code in **Plan Mode** — research and propose the concrete diff for each phase, get
approval, then implement. Do phases in order. Keep each phase to a small, reviewable PR.

---

## Goal

Bring the repo to a clean, honest, deployable baseline:
1. Finish the Grok → Claude migration.
2. Remove the startup/build hazards.
3. Close the security exposure.
4. Make the docs match the code.
5. Tag a first release.

**Out of scope (future, separate plan):** trade execution, Solana/Sui connectors, strategy
engine. This plan is about stability and honesty, not new features.

---

## Decision checkpoint — resolve before Phase 1

The provider migration has one fork. Confirm which path with the user before doing Phase 1:

- **Path A — consolidate on Claude (recommended).** Move CI off Grok too. Result: one provider,
  one API key, no split-brain. CI review wording changes slightly. Simplest to maintain.
- **Path B — keep CI on Grok deliberately.** Runtime stays Claude, CI stays Grok. Only make the
  docs honest about the split. Choose this only if Grok's CI reviews are specifically wanted.

Phase 1 below has both variants. Phases 0, 2, 3, 4 are the same either way.

---

## Phase 0 — Safety & build (do first, blocks everything)

- **0.1 Rotate the exposed Etherscan key** *(manual — user action).* Regenerate at cronoscan.com,
  then replace the value in `.env.example` with a placeholder (`YOUR_ETHERSCAN_API_KEY_HERE`).
  Set the real new key only in Railway variables. *Claude Code: make the `.env.example` edit; the
  user does the rotation.*
- **0.2 Add `python-dotenv` to `requirements.txt`.**
- **0.3 Fix the import-time crash in `core/pnl_calculator.py`.** Do not read/raise on
  `COVALENT_API_KEY` / `ETHERSCAN_API_KEY` at module import. Read them lazily inside the functions
  that use them, and remove the dead Covalent gate.

**Acceptance:** a fresh clone `pip install`s cleanly; `python -c "import app.main"` and
`import core.pnl_calculator` succeed with **no** env vars set; `.env.example` contains no real secret.

---

## Phase 1 — Finish the provider migration

### Path A (recommended)
- **1.1** Repoint `.github/scripts/call_grok.py` to import from `core.claude_client` (the aliases
  make this a drop-in), or rename the script and update the workflows that call it.
- **1.2** Update `.github/workflows/health-check.yml` and `grok-code-review.yml` to use
  `ANTHROPIC_API_KEY` (GitHub secret). Remove the `GROK_API_KEY` requirement.
- **1.3** Once nothing imports `core/grok_client.py`, delete it.
- **1.4** *(optional tidy)* rename `call_grok` → `call_claude` at call sites and drop the aliases.

### Path B
- **1.1** Leave `core/grok_client.py` and the CI untouched.
- **1.2** Document the split clearly in the SOT docs (handled in Phase 2).

**Acceptance:** `grep -ri "api.x.ai\|grok_client"` returns only intended references; CI runs green.

---

## Phase 2 — Reconcile the docs (SOT)

- **2.1** Update `GROK_USAGE.md`, `GROK_COORDINATION.md`, `AGENTS.md`, `project-awareness.md`,
  `docs/project-status.md`, `SUMMARY.md`, `GROK_HEALTH.md` to describe the **real** provider state
  (runtime = Claude; CI = per the chosen path). Remove the false claim that `core/grok_client.py`
  is the runtime source of truth.
- **2.2** Repoint the agent personas in `agents/personas/` — they name Grok as "Master Agent."

**Acceptance:** no doc claims `grok_client.py` is the runtime SOT; docs match code.

---

## Phase 3 — Hygiene

- **3.1** Resolve the worker start-command drift: pick `worker.py` and make `railway.toml`,
  `WORKER.md`, `Procfile`, and the deployment docs all agree.
- **3.2** Remove the dead `main.py` stub and orphaned modules (`telegram/handlers.py`,
  `app/health.py`, `app/github_webhook.py`) **after** confirming nothing imports them.
- **3.3** Resolve the local `telegram/` package shadowing the pip `telegram` package (rename the
  local package, e.g. to `tg/`, and update imports).
- **3.4** Triage stale open PRs and dependency alerts: close superseded PRs, merge or dismiss alerts.
- **3.5** Tag the first release (`v0.1.0`) to mark the clean Claude baseline.

**Acceptance:** one worker start command everywhere; no orphaned modules; a tagged release exists.

---

## Phase 4 — Deploy & verify

- **4.1** Deploy to Railway with `ANTHROPIC_API_KEY` set as a variable.
- **4.2** Verify: `/health` returns `{"ok": true}`, the Telegram webhook responds, the worker
  heartbeat fires.

**Acceptance:** all three services healthy; bot responds in Telegram.

---

## Working rules (apply to every phase)

- Smallest correct change; small PRs; keep CI green.
- Reuse `core/` helpers.
- Update the relevant SOT doc in the **same** PR as the code change.
- Defensive code: timeouts + error handling on all external calls.
- This is financial-decision-adjacent infra — surface anything risky for human review before merging.

---

## Plan Mode kickoff prompt (paste into Claude Code)

> Read `CLAUDE.md` and `IMPLEMENTATION_PLAN.md` at the repo root. We are in Plan Mode. Start with
> the Decision Checkpoint, then propose a concrete diff for **Phase 0 only** — exact files and
> changes, plus how you'll verify the acceptance criteria. Do not edit anything until I approve
> the plan. Verify every claim against the actual files; the markdown SOT docs are stale.
