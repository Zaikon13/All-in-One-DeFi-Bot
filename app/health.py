from fastapi import APIRouter
from typing import Dict

router = APIRouter()

@router.get("/health")
def health() -> Dict[str, bool]:
    """
    Minimal liveness endpoint used for uptime checks and webhook diagnostics.
    Returns 200 with {"ok": true} when the web service is up.
    """
    return {"ok": True}
