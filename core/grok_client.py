import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

GROK_API_KEY = os.getenv("GROK_API_KEY")


def load_prompt(filename: str, **kwargs) -> str:
    """Load a prompt from the prompts/ folder and format it."""
    try:
        with open(f"prompts/{filename}", "r", encoding="utf-8") as f:
            content = f.read()
        return content.format(**kwargs)
    except FileNotFoundError:
        return f"[ERROR] Prompt file not found: prompts/{filename}"
    except Exception as e:
        return f"[ERROR] Failed to load prompt: {e}"


async def call_grok(prompt: str) -> str:
    """Call Grok API for analysis."""
    if not GROK_API_KEY:
        return "GROK_API_KEY not configured in Railway."
    try:
        async with httpx.AsyncClient(timeout=45) as client:
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