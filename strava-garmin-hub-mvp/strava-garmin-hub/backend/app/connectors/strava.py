from datetime import datetime, timezone
from typing import Any
import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Activity, SourceConnection

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_URL = "https://www.strava.com/api/v3"

class StravaError(RuntimeError): pass

class StravaClient:
    """Small synchronous client. Secrets stay server-side; callers own retries/checkpoints."""
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=25.0)

    def authorization_url(self, state: str) -> str:
        if not settings.strava_client_id: raise StravaError("STRAVA_CLIENT_ID is not configured")
        params = {"client_id": settings.strava_client_id, "response_type": "code", "redirect_uri": settings.strava_redirect_uri, "approval_prompt": "auto", "scope": settings.strava_scopes, "state": state}
        return str(httpx.URL(AUTH_URL).copy_merge_params(params))

    def exchange_code(self, code: str) -> dict[str, Any]:
        return self._token_request({"code": code, "grant_type": "authorization_code"})

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        return self._token_request({"refresh_token": refresh_token, "grant_type": "refresh_token"})

    def _token_request(self, payload: dict) -> dict[str, Any]:
        if not settings.strava_client_id or not settings.strava_client_secret: raise StravaError("Strava credentials not configured")
        r = self.http.post(TOKEN_URL, data={**payload, "client_id": settings.strava_client_id, "client_secret": settings.strava_client_secret})
        if r.status_code >= 400: raise StravaError(f"Strava token endpoint HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        if not data.get("access_token") or not data.get("refresh_token"): raise StravaError("Invalid token response from Strava")
        return data

    def get(self, path: str, access_token: str, params: dict | None = None) -> Any:
        r = self.http.get(f"{API_URL}/{path.lstrip('/')}", headers={"Authorization": f"Bearer {access_token}"}, params=params)
        if r.status_code == 429: raise StravaError("Strava API rate limit reached; retry later")
        if r.status_code >= 400: raise StravaError(f"Strava API HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

def parse_start_time(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def upsert_activity(db: Session, item: dict[str, Any]) -> None:
    row = {
        "source": "strava", "source_id": str(item["id"]), "name": item.get("name") or "Activity",
        "sport_type": item.get("sport_type") or item.get("type") or "unknown",
        "started_at": parse_start_time(item["start_date"]), "elapsed_seconds": item.get("elapsed_time"),
        "moving_seconds": item.get("moving_time"), "distance_m": item.get("distance"),
        "elevation_gain_m": item.get("total_elevation_gain"), "average_hr": item.get("average_heartrate"),
        "max_hr": item.get("max_heartrate"), "average_speed_mps": item.get("average_speed"),
        "calories_kcal": item.get("calories"), "raw_payload": item,
    }
    # Portable update avoids dialect-specific upsert assumptions and preserves idempotence.
    existing = db.scalar(select(Activity).where(Activity.source == "strava", Activity.source_id == row["source_id"]))
    if existing:
        for key, value in row.items():
            if key not in ("source", "source_id"): setattr(existing, key, value)
    else:
        db.add(Activity(**row))

def import_activities(db: Session, client: StravaClient, access_token: str, after_epoch: int | None = None, page_size: int = 100, max_pages: int = 10000) -> dict[str, Any]:
    """Import available Strava activity history, committing each page for durable progress.

    Re-running the same range is safe because activities are upserted by source/id.
    The caller chooses a full-history (after_epoch=None) or incremental overlap window.
    """
    page, imported = 1, 0
    conn = db.scalar(select(SourceConnection).where(SourceConnection.source == "strava"))
    if not conn:
        conn = SourceConnection(source="strava", status="syncing")
        db.add(conn)
        db.flush()
    conn.status, conn.last_error = "syncing", None
    conn.last_attempt_at = datetime.now(timezone.utc)
    db.commit()
    min_start: datetime | None = None
    max_start: datetime | None = None
    try:
        while page <= max_pages:
            params = {"page": page, "per_page": min(max(page_size, 1), 200)}
            if after_epoch is not None:
                params["after"] = after_epoch
            items = client.get("athlete/activities", access_token, params)
            if not isinstance(items, list):
                raise StravaError("Unexpected activities response")
            if not items:
                break
            for item in items:
                if not item.get("id") or not item.get("start_date"):
                    continue
                started = parse_start_time(item["start_date"])
                min_start = started if min_start is None or started < min_start else min_start
                max_start = started if max_start is None or started > max_start else max_start
                upsert_activity(db, item)
                imported += 1
            conn.cursor = str(page + 1)
            db.commit()
            if len(items) < params["per_page"]:
                break
            page += 1
        conn.status = "connected"
        conn.last_success_at = datetime.now(timezone.utc)
        conn.last_error = None
        conn.cursor = None
        # Keep the broadest known imported range across repeated incremental syncs.
        known_start = conn.history_start
        known_end = conn.history_end
        if known_start is not None and known_start.tzinfo is None:
            known_start = known_start.replace(tzinfo=timezone.utc)
        if known_end is not None and known_end.tzinfo is None:
            known_end = known_end.replace(tzinfo=timezone.utc)
        if min_start is not None and (known_start is None or min_start < known_start):
            conn.history_start = min_start
        if max_start is not None and (known_end is None or max_start > known_end):
            conn.history_end = max_start
        db.commit()
        return {"imported_or_updated": imported, "pages_read": min(page, max_pages), "status": conn.status,
                "history_start": conn.history_start.isoformat() if conn.history_start else None,
                "history_end": conn.history_end.isoformat() if conn.history_end else None,
                "after_epoch": after_epoch}
    except Exception as exc:
        db.rollback()
        conn = db.scalar(select(SourceConnection).where(SourceConnection.source == "strava"))
        if conn:
            conn.status = "error"
            conn.last_error = str(exc)[:1000]
            conn.last_attempt_at = datetime.now(timezone.utc)
            db.commit()
        raise
