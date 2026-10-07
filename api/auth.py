import hmac
import os

from fastapi import Header, HTTPException


async def require_api_key(x_api_key: str = Header(...)):
    api_key = os.environ.get("API_KEY", "")
    if not api_key or x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def require_read_access(x_api_key: str = Header("")):
    """Readings only: the full API_KEY, or READ_API_KEY, which cannot change anything (the home's screens)."""
    keys = [os.environ.get("API_KEY", ""), os.environ.get("READ_API_KEY", "")]
    if not any(key and hmac.compare_digest(x_api_key.encode(), key.encode()) for key in keys):
        raise HTTPException(status_code=401, detail="Invalid API key")

