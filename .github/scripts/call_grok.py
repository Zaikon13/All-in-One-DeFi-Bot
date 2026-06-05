#!/usr/bin/env python3
"""
.github/scripts/call_grok.py

Centralized helper for GitHub Actions to call Grok using the project SOT
(core/grok_client.py). This unifies the previous inline curl + hardcoded
prompts in grok-code-review.yml and health-check.yml.

Usage (from repo root in GHA or locally):
  PYTHONPATH=. python .github/scripts/call_grok.py grok_code_review.txt \
      --var "diff=$(head -c 6000 pr.diff)" \
      --timeout 60

  PYTHONPATH=. python .github/scripts/call_grok.py grok_health_check.txt \
      --var "status=502" \
      --timeout 30

The script:
- Loads prompt from prompts/<name> using core.load_prompt (supports {var} placeholders)
- Calls via core.call_grok (reuses timeout, error strings, httpx logic)
- Prints the raw result to stdout (caller in workflow wraps into $GITHUB_OUTPUT)
- Exits non-zero only on prompt load errors

This makes CI Grok usage identical in behavior (error strings, quality) to runtime.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make core/ importable when running from any cwd (GHA workspace = repo root)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.grok_client import load_prompt, call_grok  # noqa: E402


def parse_vars(var_list: list[str] | None) -> dict[str, str]:
    """Parse repeatable --var key=value into dict for prompt formatting."""
    d: dict[str, str] = {}
    for item in var_list or []:
        if "=" in item:
            k, v = item.split("=", 1)
            d[k] = v
        else:
            print(f"[WARN] Ignoring malformed --var '{item}' (expected key=value)", file=sys.stderr)
    return d


async def _main_async() -> None:
    parser = argparse.ArgumentParser(
        description="Call Grok API via the centralized core/grok_client.py (for CI workflows)."
    )
    parser.add_argument(
        "prompt",
        help="Prompt filename inside prompts/ folder, e.g. grok_code_review.txt",
    )
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Variable for prompt .format() substitution. Repeatable, e.g. --var diff=... --var status=500",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds (default 60; runtime often uses 25)",
    )
    args = parser.parse_args()

    vars_dict = parse_vars(args.var)

    prompt_text = load_prompt(args.prompt, **vars_dict)

    if prompt_text.startswith("[ERROR]"):
        # Propagate load errors to stderr + stdout (so GHA step still captures something)
        print(prompt_text, file=sys.stderr)
        print(prompt_text)
        sys.exit(1)

    # Reuse the exact SOT call (includes GROK_API_KEY check, error prefix strings,
    # httpx, model=grok-4.3, max_tokens=600, temp=0.2, user-role message)
    result = await call_grok(prompt_text, timeout=args.timeout)

    # Always emit to stdout for easy capture in workflows (e.g. into GITHUB_OUTPUT)
    print(result)


def main() -> None:
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
