#!/usr/bin/env python3
"""CI wrapper that routes GitHub Actions prompts to Claude (Anthropic).

Claude-native replacement for the old .github/scripts/call_grok.py.
Reuses core/claude_client.py so CI and runtime share one client, one quality gate.

Usage:
    PYTHONPATH=. python .github/scripts/call_claude.py <prompt_file> \\
        --var key=value [--var key2=value2 ...] [--timeout 60]

Reads prompts from prompts/<prompt_file>. Prints the result to stdout for
capture into $GITHUB_OUTPUT. Requires ANTHROPIC_API_KEY in the environment.
"""
import argparse
import asyncio
import sys

from core.claude_client import call_claude, load_prompt


def parse_vars(pairs):
    out = {}
    for p in pairs:
        if "=" not in p:
            print(f"[ERROR] bad --var '{p}', expected KEY=VALUE", file=sys.stderr)
            sys.exit(2)
        k, v = p.split("=", 1)
        out[k] = v
    return out


async def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", help="Prompt filename inside prompts/")
    ap.add_argument("--var", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    text = load_prompt(args.prompt, **parse_vars(args.var))
    if text.startswith("[ERROR]"):
        print(text, file=sys.stderr)
        print(text)
        sys.exit(1)

    result = await call_claude(text, timeout=args.timeout)
    print(result)


def main():
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
