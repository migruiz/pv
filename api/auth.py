import hmac
import os

from fastapi import Header, HTTPException


async def require_api_key(x_api_key: str = Header(...)):
    api_key = os.environ.get("API_KEY", "")
    if not api_key or x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def require_kindle_token(authorization: str = Header("")):
    """Read-only Kindle access: `Authorization: Bearer <KINDLE_TOKEN>`, separate from API_KEY."""
    token = os.environ.get("KINDLE_TOKEN", "")
    if not token or not hmac.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
        raise HTTPException(status_code=401, detail="Invalid Kindle token")
