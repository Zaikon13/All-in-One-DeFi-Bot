"""One-step setup + start for the standalone bot (Windows / macOS / Linux).

    Windows: double-click start_bot.bat      macOS/Linux: ./start_bot.sh

First run asks for the bot token (BotFather → your bot → "API Token"), then
finds YOUR chat id by itself: you press Start in Telegram, it shows who wrote
and asks you to confirm. Everything is saved to the local .env file (gitignored,
never uploaded). It sends you a "connected" message right away and starts
run_local.py. Later runs start immediately. `python start_bot.py --reset`
asks again.
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
API = "https://api.telegram.org/bot{token}/{method}"
TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
WALLET_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


# --- pure helpers (unit-tested) ----------------------------------------------------

def read_env(path: str) -> dict:
    """KEY=value lines of a .env file (comments/blank lines ignored)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


def upsert_env_text(text: str, updates: dict) -> str:
    """Return .env text with `updates` applied: existing keys replaced in place,
    comments and other lines kept, missing keys appended."""
    lines = text.splitlines()
    done = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in updates:
                lines[i] = f"{k}={updates[k]}"
                done.add(k)
    for k, v in updates.items():
        if k not in done:
            lines.append(f"{k}={v}")
    return "\n".join(lines).rstrip("\n") + "\n"


def find_private_chat(payload: dict):
    """From a getUpdates reply, the newest private chat that wrote to the bot:
    (chat_id:str, display_name:str, next_offset:int) or None."""
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    found = None
    for upd in payload.get("result") or []:
        if not isinstance(upd, dict):
            continue
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        if chat.get("type") == "private" and chat.get("id") is not None:
            name = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or "?"
            if chat.get("username"):
                name += f" (@{chat['username']})"
            found = (str(chat["id"]), name, int(upd.get("update_id", 0)))
    return found


def token_looks_valid(token: str) -> bool:
    return bool(TOKEN_RE.match((token or "").strip()))


# --- interactive setup ----------------------------------------------------------------

def _tg(client, token, method, **params):
    try:
        r = client.post(API.format(token=token, method=method), json=params or None, timeout=30)
        return r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def setup(reset: bool = False) -> list:
    """Make sure .env has a working token + chat id. Returns extra run_local args."""
    import httpx
    env = read_env(ENV_PATH)
    updates, extra = {}, []
    token = "" if reset else env.get("TELEGRAM_BOT_TOKEN", "")
    with httpx.Client() as client:
        me = None
        while True:
            if not token:
                print("\n1) Telegram → @BotFather → your bot → 'API Token' → copy it.")
                token = _ask("   Paste the token here and press Enter: ")
            if not token_looks_valid(token):
                print("   That doesn't look like a bot token (it is like 123456789:AA...). Try again.")
                token = ""
                continue
            me = _tg(client, token, "getMe")
            if me.get("ok"):
                break
            print(f"   Telegram refused this token ({me.get('description', 'unknown error')}). Try again.")
            token = ""
        bot = me["result"].get("username", "?")
        print(f"   ✓ Bot @{bot} found.")
        updates["TELEGRAM_BOT_TOKEN"] = token

        hook = (_tg(client, token, "getWebhookInfo").get("result") or {}).get("url") or ""
        if hook:
            print(f"\n   ⚠ @{bot} is currently connected to another program (webhook).")
            if _ask("   Disconnect it and use the bot for the DeFi bot? [y/N]: ").lower() == "y":
                extra.append("--take-over-webhook")
            else:
                print("   OK — create a separate bot in @BotFather (/newbot) and run this again.")
                sys.exit(1)

        chat_id = "" if reset else env.get("TELEGRAM_CHAT_ID", "")
        if not chat_id:
            if hook and extra:  # getUpdates only works without a webhook
                _tg(client, token, "deleteWebhook")
            print(f"\n2) Open Telegram, find @{bot} and press START (or send /start).")
            print("   Waiting up to 3 minutes…")
            deadline = time.time() + 180
            while time.time() < deadline and not chat_id:
                res = _tg(client, token, "getUpdates", timeout=20)
                if not res.get("ok") and res.get("error_code") == 409:
                    print("   ⚠ Another program is reading this bot right now. Close it (or use a new bot) and run again.")
                    sys.exit(1)
                hit = find_private_chat(res)
                if hit:
                    cid, name, _ = hit
                    if _ask(f"   Message from {name}. Is that you? [Y/n]: ").lower() in ("", "y", "yes"):
                        chat_id = cid
            if not chat_id:
                print("   No message arrived. Press START on the bot in Telegram and run this again.")
                sys.exit(1)
        updates["TELEGRAM_CHAT_ID"] = chat_id

        if not env.get("WALLET_ADDRESS") or reset:
            w = _ask("\n3) (optional) Your Cronos wallet address for /wallet — Enter to skip: ")
            if WALLET_RE.match(w):
                updates["WALLET_ADDRESS"] = w
                if not env.get("CRONOS_EXPLORER_API_KEY"):
                    k = _ask("   (optional) Cronos Explorer API key — Enter to skip: ")
                    if k:
                        updates["CRONOS_EXPLORER_API_KEY"] = k
            elif w:
                print("   Not a 0x… address — skipped.")

        old = open(ENV_PATH, encoding="utf-8").read() if os.path.exists(ENV_PATH) else ""
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(upsert_env_text(old, updates))
        sent = _tg(client, token, "sendMessage", chat_id=chat_id,
                   text="✅ Connected! The DeFi bot is starting. Type /start for the menu.")
        print("\n   ✓ Saved to .env (stays on this computer)." +
              (" ✓ Check Telegram — you got a message." if sent.get("ok") else ""))
    return extra


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    reset = "--reset" in argv
    argv = [a for a in argv if a != "--reset"]
    extra = setup(reset=reset)
    print("\nStarting the bot (Ctrl+C to stop)…\n")
    rc = subprocess.call([sys.executable, "-u", os.path.join(HERE, "run_local.py")] + extra + argv, cwd=HERE)
    if rc:
        print(f"\nThe bot stopped (exit code {rc}). See the messages above.")
    sys.exit(rc)


if __name__ == "__main__":
    main()
