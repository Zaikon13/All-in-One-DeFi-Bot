#!/usr/bin/env sh
# One-step start for macOS/Linux: venv + packages once, token on first run, then the bot.
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || python3 -m venv .venv || { echo "Python 3.10+ is needed."; exit 1; }
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt || exit 1
exec .venv/bin/python start_bot.py "$@"
