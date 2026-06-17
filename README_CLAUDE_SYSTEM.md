# Claude System — what's in this bundle

This is the Claude-native version of your old Grok agent/automation system, built to drop into the
`All-in-One-DeFi-Bot` repo. It goes alongside the `CLAUDE.md` and `IMPLEMENTATION_PLAN.md` you
already have. Together these replace the Grok-era setup.

## What each piece is (plain language)

| File / folder | What it does |
|---|---|
| `.claude/agents/` | Four Claude "team members" Claude Code can call: **reviewer** (checks work), **implementer** (makes the change), **investigator** (debugs), **researcher** (looks things up). |
| `.github/scripts/call_claude.py` | Lets your automated GitHub checks talk to Claude instead of Grok. |
| `.github/workflows/claude-code-review.yml` | Auto-reviews pull requests with Claude. |
| `.github/workflows/claude-health-check.yml` | Pings the live bot every 6 hours and opens an issue if it's down. |
| `prompts/claude_code_review.txt`, `claude_health_check.txt` | The instructions Claude follows for those two checks. |
| `docs/CLAUDE_INTEGRATION.md` | The master map of every place Claude is wired in (replaces `GROK_USAGE.md`). |

## How to install it

Copy the contents of this folder into the **root** of your repo, keeping the folder layout
(`.claude/`, `.github/`, `docs/`, `prompts/` all sit at the top level next to `requirements.txt`).
The cleanest way is to let **Claude Code** do it as part of Phase 1–2 of the implementation plan —
it can place the files, wire the workflows, and remove the old Grok ones in the same pass.

## Important

- The two workflow files are marked **TEMPLATE** at the top. Have Claude Code test them on a
  throwaway pull request before trusting them — they need the `ANTHROPIC_API_KEY` secret set in
  GitHub and a small hardening of how the PR diff is passed.
- Nothing here contains secrets.
