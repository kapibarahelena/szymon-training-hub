import secrets
from fastapi import Header, HTTPException
from app.config import settings

def require_api_key(x_hub_api_key: str | None = Header(default=None)):
    if not x_hub_api_key or not secrets.compare_digest(x_hub_api_key, settings.hub_api_key):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Hub-API-Key")
