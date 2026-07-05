import os
import logging
import anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-4-6"

CLAUDE_ERROR_PREFIXES = (
    "Claude API error",
    "Error calling Claude",
    "[ERROR]",
    "ANTHROPIC_API_KEY not configured in Railway."
)

DEFI_SYSTEM_PROMPT = """You are the analyst inside All-in-One-DeFi-Bot, a Telegram bot that monitors a single Cronos wallet. You analyse the on-chain data the bot hands you — balances, transactions, daily PnL, new trading pairs — and explain what it shows in clear, plain language. The bot monitors and reports only; it does not execute trades.

Rules:
- Base analysis strictly on the data provided. If the data doesn't show it, say so — never invent prices, numbers, or external market data.
- Your observations are information, not financial advice. Do not give buy/sell/hold recommendations.
- Be direct, concrete, and concise — output is read on a phone in Telegram.
- Format for Telegram Markdown v1: **bold** and simple bullet points only. Never use tables, code blocks, or complex markdown that breaks Telegram rendering."""


def is_valid_claude_response(text: str | None) -> bool:
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if len(t) <= 15:
        return False
    return not any(t.startswith(p) for p in CLAUDE_ERROR_PREFIXES)


def load_prompt(filename: str, **kwargs) -> str:
    try:
        with open(f"prompts/{filename}", "r", encoding="utf-8") as f:
            content = f.read()
        return content.format(**kwargs)
    except FileNotFoundError:
        return f"[ERROR] Prompt file not found: prompts/{filename}"
    except Exception as e:
        return f"[ERROR] Failed to load prompt: {e}"


async def call_claude(prompt: str, timeout: float = 45.0) -> str:
    if not ANTHROPIC_API_KEY:
        return "ANTHROPIC_API_KEY not configured in Railway."
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=timeout)
        message = await client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=DEFI_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except anthropic.APIStatusError as e:
        logging.error(f"Claude API status error: {e.status_code}")
        return f"Claude API error: {e.status_code} - {str(e.message)[:200]}"
    except Exception as e:
        logging.error(f"Claude API exception: {e}")
        return f"Error calling Claude: {str(e)[:100]}"


# Migration aliases — existing code needs zero changes
call_grok = call_claude
is_valid_grok_response = is_valid_claude_response
