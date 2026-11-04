# The agent team

How the Claude Code agents in `.claude/agents/` work together on this repo. Agents start with no
context and cannot see each other's chats. They "talk" through files: each one's output is the
next one's input, and the coordinator (the main session) passes the files along. The
coordinator also owns git: agents never commit or push.

## Roles

| Agent | Writes code? | Job | Output IDs |
|---|---|---|---|
| `investigator` | no | general evidence-based investigation, function inventories | `F1..` |
| `researcher` | no | verifies external API behaviour against official sources and grades each claim | `R1..` |
| `telegram-auditor` | no | Tier 1: delivery, formatting, routing, inbound, allow-list | `TG1..` |
| `wallet-data-auditor` | no | Tier 2: balances, prices, daily report, honesty | `WD1..` |
| `scanner-auditor` | no | Tier 3: new-pool discovery, score, alerts, /signals | `SC1..` |
| `simulation-auditor` | no | Tier 3: paper-trading integrity (booking rules → owner) | `SIM1..` |
| `runtime-auditor` | no | Tier 4: loops, schedules/DST, restarts, env, deploy/CI | `RT1..` |
| `reviewer` | no | mandatory gate: verifies every claim, decides per item, writes the work order | decisions |
| `implementer` | yes (code, docs, tests) | executes the work order exactly; suite green after each step | change report |
| `test-guardian` | tests only | turns the critical-function invariants into tests; closes coverage gaps | tests + bug findings |

The tiers are defined in `docs/CRITICAL_FUNCTIONS.md`.

## The flow

```
            ┌─ investigator / domain auditors ─┐      (parallel, read-only)
question ──►│                                  ├──► reviewer ──► implementer ──► coordinator
            └─ researcher (external facts) ────┘        │            │            (tests, commit, PR)
                                                        ▼            ▼
                                                 owner decisions  test-guardian (coverage)
```

1. **Find**: the auditors for the affected tiers, plus the Researcher if external behaviour
   matters, run in parallel. Each produces numbered findings with evidence marked verified or
   inferred.
2. **Decide**: the Reviewer reads every finding, re-checks the code, and gives each item one of
   APPROVE-NOW / OWNER-DECISION / DEFER / REJECT. It writes an ordered work order.
3. **Do**: the Implementer executes only the APPROVE-NOW items, with tests, and updates the docs
   in the same change.
4. **Guard**: the Test Guardian adds tests for critical functions still in `KNOWN_GAPS`.
5. **Ship**: the coordinator re-runs the suite, the import check and `run_local.py --selftest`,
   commits, pushes, updates the PR, and reports the OWNER-DECISION list to the owner.

## Conventions
- Outputs live in the coordinator's scratch directory: `investigator.json/.md`, `researcher.md`,
  `reviewer_work_order.md`, and so on. Repo-worthy conclusions go into `reviews/<date>-*.md`.
- Evidence first: a finding without file:line and verified/inferred marking is not actionable.
- Live APIs are usually unreachable from cloud sessions. Anything depending on them stays
  **unverified** until checked with network access.
- Financial-decision-adjacent changes (paper-trading entry, exit and booking rules) are always
  OWNER-DECISION. Real-fund execution does not exist and must not be added.
- Keep batches small, about 12 approved items per Implementer pass at most.
