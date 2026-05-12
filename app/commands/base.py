import httpx
import logging

async def send_telegram_message(text: str, chat_id: str = None) -> None:
    """Shared message sender (will be used across commands)"""
    # Import from main to avoid circular imports
    from app.main import send_telegram_message as main_send
    return await main_send(text, chat_id) if 'main_send' in locals() else None