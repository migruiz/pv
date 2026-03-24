import os

from fastapi import Header, HTTPException


async def require_api_key(x_api_key: str = Header(...)):
    api_key = os.environ.get("API_KEY", "")
    if not api_key or x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
