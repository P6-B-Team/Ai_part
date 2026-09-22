"""
Internal service-to-service authentication.

Per AI_Service_Blueprint.pdf section 4: "Internal Auth Token — Secures
inter-service communication between Node.js and Python." This is NOT
end-user auth (the Backend already handles that with real users/roles) —
it's a shared secret so this AI service only accepts calls from the
Backend, not from the open internet.
"""
from fastapi import Header, HTTPException

from app import config


async def verify_internal_token(x_internal_token: str | None = Header(default=None)):
    """
    FastAPI dependency. Raises 401 per blueprint section 8
    ("401 Unauthorized — Invalid internal API key") if the header is
    missing or wrong.
    """
    if x_internal_token != config.INTERNAL_AI_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing internal API token")
