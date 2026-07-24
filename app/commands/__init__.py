# Command registry
# Note: process_daily_pnl is implemented directly in the webhook handler (app/main.py)
# for the production path. The previous `from .daily_pnl import ...` was a broken
# reference to a non-existent module and has been cleaned (per Review feedback + task).

from .balances import get_all_balances
from .paper import get_paper_status
from .signals import get_signals

__all__ = ["get_all_balances", "get_paper_status", "get_signals"]
