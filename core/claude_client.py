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

DEFI_SYSTEM_PROMPT = """You are an expert DeFi portfolio analyst and trader with deep knowledge of the Cronos, Solana, and Sui ecosystems. You monitor wallets, analyse on-chain data, and provide clear, actionable trading insights.

Rules:
- Base analysis strictly on the data provided. Never invent prices or external market data.
- Be direct, practical, and concise. Avoid vague language.
- Format responses for Telegram: use **bold** and bullet points only.
- Never use tables, code blocks, or complex markdown that breaks Telegram rendering."""


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
            max_tokens=1024,
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
