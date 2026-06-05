import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

GROK_API_KEY = os.getenv("GROK_API_KEY")

# Single source of truth (SOT) for all Grok API calls and prompt loading.
# All Python runtime code must use this module (imports + is_valid_grok_response for gates).
GROK_ERROR_PREFIXES = (
    "Grok API error",
    "Error calling Grok",
    "[ERROR]",
    "GROK_API_KEY not configured in Railway."
)


def is_valid_grok_response(text: str | None) -> bool:
    """Centralized quality gate. Returns True only for good, substantial, non-error responses.
    Replaces duplicated startswith checks in callers (app/main.py, core/pnl_calculator.py).
    """
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if len(t) <= 15:
        return False
    return not any(t.startswith(p) for p in GROK_ERROR_PREFIXES)


def load_prompt(filename: str, **kwargs) -> str:
    """Load a prompt from the prompts/ folder and format it. (SOT)"""
    try:
        with open(f"prompts/{filename}", "r", encoding="utf-8") as f:
            content = f.read()
        return content.format(**kwargs)
    except FileNotFoundError:
        return f"[ERROR] Prompt file not found: prompts/{filename}"
    except Exception as e:
        return f"[ERROR] Failed to load prompt: {e}"


async def call_grok(prompt: str, timeout: float = 45.0) -> str:
    """Call Grok API for analysis. (SOT - use is_valid_grok_response for quality gates.)
    Supports optional timeout for caller-controlled hard limits (addresses prior review feedback on Grok timeout control for command paths).
    """
    if not GROK_API_KEY:
        return "GROK_API_KEY not configured in Railway."
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-4.3",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 600,
                    "temperature": 0.2
                }
            )
            if response.status_code != 200:
                return f"Grok API error: {response.status_code} - {response.text[:200]}"
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"Grok API exception: {e}")
        return f"Error calling Grok: {str(e)[:100]}"