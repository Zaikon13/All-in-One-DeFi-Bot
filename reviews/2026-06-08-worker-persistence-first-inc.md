# Review Agent 2026-06-08: Worker Persistence First Increment (High Risk)

**Source**: Spawned via full Review Gate protocol after `todo_write` (review-gate item in_progress). Master provided full `review-agent.md` persona prepended, all required Primary SOTs (GROK_COORDINATION.md, project-awareness.md, AGENTS.md + GROK_USAGE.md, project_context.md), current todo list, exact proposed scope, and specific focus questions.

**Proposed Scope (as provided to Review Agent)**: First minimal increment for Worker Loop persistence using **file/JSON only** (no DB/external):
- known_pairs (enhance existing basic JSON set persistence at "data/known_pairs.json").
- Add last_seen timestamps.
- Improved change detection for new pairs/alerts.
- Basic EOD PnL (reuse `get_daily_pnl_report()` exactly; minimal state if needed for reliability).
- Explicit Railway ephemeral FS handling (data loss on redeploy without Volume; no durability assumptions).
- Strictly worker.py only. Follow existing patterns (lazy, env-gate, continue-on-error, pre-compute, 25s+is_valid where Grok, ZoneInfo, Review comments).

**Risk**: High (per project-awareness.md 4.3.0 — worker.py persistence/known_pairs logic + EOD scheduling).

---

## Review Summary
Overall assessment: Needs work  
Risk Level: **High** (as classified by Master per project-awareness.md 4.3.0; worker.py persistence/known_pairs logic + EOD scheduling explicitly listed as high-risk)  
Recommendation: **Approve with minor revisions**

## Key Strengths
- The proposed scope is correctly and ruthlessly minimal: **only** changes inside `worker.py`; no modifications whatsoever to `core/pnl_calculator.py`, `prompts/grok_daily_pnl.txt`, `core/`, `app/main.py`, `telegram/handlers.py`, or any Primary SOT files in this increment.
- Explicit respect for Railway ephemeral FS constraints (no DB, no external services, no new deps, file/JSON only under `data/`, strong TODO for future Volume).
- Reuses `get_daily_pnl_report()` *exactly* (lazy import inside the send block, as already implemented).
- Builds directly on proven patterns already present in the current `worker.py`: env-gating (EOD_PNL_ENABLED + MARKET_ANALYSIS_ENABLED default false), lazy imports for heavy modules, continue-on-error, pre-compute summaries in Python before any Grok, 25s timeouts + `is_valid_grok_response` where applicable (via existing market helpers), Review Agent attribution comments, ZoneInfo("Europe/Athens") + target recalc logic.
- Current code already contains basic known_pairs JSON load/save (KNOWN_PAIRS_FILE="data/known_pairs.json", `load_known_pairs`/`save_known_pairs`, immediate save on detection, load in `main()`) + full `scheduled_eod_pnl()` scheduler with proper DST-safe target calculation and header. The "first inc" is therefore a hardening/improvement (last_seen + change detection + minimal EOD reliability state) rather than greenfield.
- No impact on legacy paths (Covalent remains confined to `telegram/handlers.py`; production async Etherscan V2 stays in `core/pnl_calculator.py`). Good separation.
- Prior related high-risk worker reviews (e.g. 2026-06-XX-worker-market-analysis-eod.md and market analysis reviews) established excellent 12-condition discipline that this can extend.
- Primary SOTs + persona were read by Master before spawning (GROK_COORDINATION.md, project-awareness.md, AGENTS.md, GROK_USAGE.md, project_context.md + review-agent.md).

## Issues Found

### Critical / High
- **worker.py:38-73 (KNOWN_PAIRS_FILE, load/save_known_pairs) + 231-233 (main load) + 94-96 (poll_dexscreener save)**: Basic persistence exists but uses a plain `set` of addresses serialized as JSON list. No `last_seen` timestamps, no atomic writes (direct `open(..., "w")` + `json.dump` with no temp/rename/fsync), and no explicit runtime warning on startup when running without a Railway Volume. Data loss on redeploy is a documented risk but not strongly enforced in logs or guards. Partial write corruption risk is real on crash/restart. Suggestion: Strengthen with explicit "ephemeral warning" logs at startup + on every load/save if no volume mount detected; add atomic save pattern (write to .tmp then os.replace); document in code.
- **SOT / coordination risk (GROK_COORDINATION.md:215, project-awareness.md:53-57 + 131, AGENTS.md:12, GROK_USAGE.md:160, project_context.md:13)**: All Primary SOTs and supporting docs still describe persistence/EOD as "Partially Functional", "Missing", "Remaining", or "pending". Proposal states "No SOT updates in this inc (use SOT Coordinated PR Helper later)". This is borderline for high-risk worker.py changes per project-awareness.md 4.3.0/4.3.1 and GROK_COORDINATION.md "update SOTs first" + "coordinated single PR" rules. Even a pure hardening change that improves reliability can make status claims inaccurate. Suggestion: Master must either (a) accept that a later coordinated SOT PR (via orchestrator --sot-pr-helper) is mandatory before merge, or (b) include the minimal status update language in the plan. Record this explicitly.
- **worker.py:23 (global seen_pairs), 83-132 (poll_dexscreener), 159-224 (scheduled_eod_pnl), 226-253 (main + gather)**: Adding `last_seen` (and optional last-EOD-run) requires a clear migration/backward-compat strategy for the existing list JSON. Current load only handles list. Restart behavior around EOD boundary or repeated Dexscreener sightings can still produce duplicate alerts or missed reports without time-based logic. Global mutable state across asyncio tasks lacks any defensive comment/locking note (even if asyncio is single-threaded in practice). Suggestion: Define smallest structure (e.g. dict of addr -> {"last_seen": ISO-UTC} with list-compat loader that migrates on first load); use UTC ISO strings only; add explicit last-EOD timestamp in the same file only if it meaningfully prevents dups (the existing target recalc already helps); add comments on async mutation safety.
- **Railway ephemeral + data/ (worker.py:47, .gitignore:6, RAILWAY.md:33, WORKER.md:18, Dockerfile/railway.toml context)**: `data/` is gitignored and created on-demand. No code path respects `RAILWAY_VOLUME_MOUNT_PATH` even optionally in this inc (only TODO). Startup does not emit a clear "WARNING: persistence is not durable across Railway redeploys without Volume" when `data/known_pairs.json` is absent or on every save. This is the #1 data-loss scenario repeatedly called out in SOTs and prior reviews. Suggestion: Add optional volume-aware path resolution (with fallback to "data/") + loud warning logs.

### Medium
- Change detection improvement via last_seen is valuable for reducing restart noise and better dedup, but introduces new failure modes (clock skew on container, malformed timestamps, comparison logic bugs). Must stay defensive (e.g. treat missing/invalid last_seen as "new").
- EOD state: The proposal allows "minimal file/JSON state if needed for EOD reliability (e.g. last EOD run timestamp)". Existing scheduler logic (lines 165-170) already does target recalc on every cycle/start. Adding state is optional hardening only; confirm it is the smallest possible and lives in the same known_pairs/worker_state structure. Never touches the report function.
- `core/dexscreener.py:24-60` implements parallel `get_new_cronos_pairs(known_pairs: set)` that mutates a set in-place. Worker uses its own inline `poll_dexscreener`. Adding richer structure in worker increases divergence risk (future unification will be harder). Scope correctly forbids touching core/, but note the duplication in review for traceability.
- No explicit tests or load/save roundtrip verification for the persistence functions (defensive code only).

### Low / Nits
- Startup logging (lines 232-233) only reports count; should also note persistence path and durability status for ops visibility.
- WORKER.md and RAILWAY.md already claim "basic persistence" and the ephemeral caveat — they will need light refresh after this inc, but proposal defers (acceptable for this small code-only step if later coordinated).
- Global `seen_pairs` + `last_wallet_state` at module level is existing pattern; keep for smallest change.

## SOT & Rule Alignment
- **Primary SOTs referenced**: GROK_COORDINATION.md (full), project-awareness.md (full + 4.3 Review Gate + 4.3.0 high-risk worker list + 4.3.5 recording), AGENTS.md (full), GROK_USAGE.md (full + pending worker items + strict grok_client patterns), agents/memory/project_context.md (full), agents/personas/review-agent.md (full).
- **Violations or concerns**: "No SOT updates in this inc" is the main coordination concern (see High issues). Otherwise strong alignment: small scoped change (worker.py only), Review Gate followed via todo_write + full persona + SOT refs + spawn, no legacy path bypass, no core duplication in the proposed scope, Railway honesty emphasized, Grok usage remains analysis-only + via existing helpers (no new prompts or direct calls).
- **Alignment with coordination rules**: Protocol followed (todo list opened with review-gate item in_progress before this spawn). Small-PR discipline respected. "Update SOTs first" is the only area needing explicit Master plan for the follow-on coordinated PR (via existing --sot-pr-helper or manual). "Grok Native Sub-Agents" rules respected (Review is the mandatory gate; Master retains authority; no bypass).

## Specific Guardrails / Project Rules Checked
- **Legacy paths protected?** Yes — zero touch to `telegram/handlers.py` Covalent code, `_aggregate_pnl`, or Etherscan-vs-Covalent separation. Production /daily_pnl path (app/main.py + core) untouched.
- **UTC / timezone discipline?** Yes for EOD (ZoneInfo("Europe/Athens") + proper target math). Any new last_seen / last_eod timestamps **must** be UTC ISO (e.g. datetime.now(timezone.utc).isoformat()).
- **Telegram Markdown safety (for any Grok output changes)?** N/A for this inc — no new Grok call sites or prompt changes. Existing market appends (new-pair + EOD post-process) already reviewed as safe (**bold** + simple bullets only).
- **Core/ reuse vs duplication?** Excellent for PnL (exact reuse of `get_daily_pnl_report`). Market context (if used) reuses existing thin helper. Note the pre-existing parallel known_pairs logic in core/dexscreener.py (out of scope).
- **Error handling / fallbacks for external calls?** Existing patterns are defensive (try/except around loads/saves, continue-on-error for EOD and market blocks, safe empty returns). Must extend to new state logic.
- **Railway ephemeral FS awareness?** Documented in code + SOTs + WORKER.md + RAILWAY.md, but runtime guards/logs are insufficient (see Critical/High).
- **Review Agent comments + traceability?** Current file already has good examples (EOD 2026-06-06, market). New changes must add `# Review Agent 2026-06-08: ...` for every guardrail.
- **Other (from persona/SOTs)**: No secrets in code; proper async; state consistency for known_pairs; smallest correct change; pre-compute before Grok; 25s + is_valid where Grok; env-gating; continue-on-error; no new autonomous loops; data/ under gitignore (confirmed).

## Final Recommendation
**Approve with minor revisions**

Master may proceed to Code Agent (or direct implementation) **only after** explicitly addressing every point below in the todo list + any Code prompt + resulting code (with Review Agent 2026-06-08 comments). Minimum required conditions for approval (10 conditions, aligned with prior high-risk worker reviews):

1. **State design (smallest correct + backward compat)**: Evolve to a dict structure supporting last_seen (e.g. `{pair_address: {"last_seen": "2026-...Z"}}` or wrapper `{"pairs": {...}, "last_eod_run": "..."}`). Loader must accept the existing plain list format and migrate in-memory (or on first save) without data loss. Document the format + migration in code comments.
2. **last_seen usage for change detection**: Use it to improve dedup (e.g. skip re-alert if seen within a short window on restart). All timestamps must be UTC ISO. Add defensive handling for missing/invalid timestamps (treat as new).
3. **EOD reliability state (minimal)**: Add a last-EOD-run timestamp (same JSON) **only if** it meaningfully hardens against duplicate sends on restart around the target hour. Confirm the existing target recalc + sleep logic is preserved unchanged. Never modify or wrap `get_daily_pnl_report()`.
4. **Stronger Railway ephemeral guards (mandatory for data-loss protection)**: At startup (after load) and on every save/load, emit clear WARNING logs if no Railway Volume mount is detected (check env or path). Make persistence path optionally respect `RAILWAY_VOLUME_MOUNT_PATH` (fallback to "data/" if unset). Add explicit "data not durable across redeploys" note in logs and comments.
5. **Atomic / safe writes**: Replace direct write in save_known_pairs (and any new state writer) with temp-file + os.replace (or equivalent) to prevent corruption on crash. Keep error handling that never crashes the loop.
6. **Startup + restart behavior hardening**: Ensure load happens before any polling/EOD tasks. Log loaded count + durability status. Re-confirm EOD scheduler target logic runs on every startup.
7. **No SOT drift**: Explicitly record in the todo and any implementation that a coordinated Primary SOT update (via SOT Coordinated PR Helper or equivalent) is required in a follow-on PR before the change can be considered complete in docs/status. Do not claim "persistence complete" in this inc.
8. **Guardrail comments + traceability**: Every behavioral addition must carry `# Review Agent 2026-06-08: [specific guardrail, e.g. "atomic write for Railway safety", "UTC last_seen + migration compat", "ephemeral volume warning log"]`. Reference this review file.
9. **Preserve all existing patterns exactly**: lazy imports, env-gating, continue-on-error (base alert/report must still fire), 25s/is_valid for any Grok paths, pre-compute in Python, no new loops, no impact on market appends.
10. **Scope + risk documentation**: Keep the inc strictly to worker.py. In implementation comments and the review record, restate the key risks (ephemeral data loss on redeploy, duplicate alerts on restart, corruption, timezone issues) and that Volume is required for production durability.
11. (Bonus/strong recommendation) Add a one-time load/save roundtrip sanity note or defensive check in main() for the new structure.
12. Master must save this full Review output to `reviews/2026-06-08-worker-persistence-first-inc.md` (or equivalent date-slug), update the active todo with `review-gate: addressed` referencing the conditions + file, and include the review reference in any Code prompt / commit.

Master must confirm (in todo or next prompt) that **all** conditions have been read and addressed before any `search_replace`/`write`/Code Agent work. Once addressed, this review serves as the gate for the increment.

This is the correct first hardening step for the top-priority Worker Loop item. With the above conditions met, the change will be safer, more honest about Railway realities, and fully aligned with project rules. 

**End of Review Agent 2026-06-08 output.**