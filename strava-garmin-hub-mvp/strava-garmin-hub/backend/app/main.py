from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.config import settings
from app.db import Base, engine, get_db
from app.models import Activity, MetricSample, SourceConnection, PlannedWorkout
from app.credentials import new_oauth_state, consume_oauth_state, save_credentials, load_credentials, CredentialError
from app.security import require_api_key
from app.connectors.strava import StravaClient, StravaError, import_activities
from app.analytics.core import dashboard, load_summary, latest_metrics
import secrets

from pydantic import BaseModel, Field
from typing import Literal

class MetricIngestItem(BaseModel):
    metric: str = Field(min_length=1, max_length=100)
    value: float
    unit: str = Field(default="", max_length=40)
    measured_at: datetime
    source_entity_id: str = Field(min_length=1, max_length=255)
    quality: str = Field(default="observed", max_length=30)
    attributes: dict = Field(default_factory=dict)

class MetricIngestRequest(BaseModel):
    source: Literal["home_assistant", "health_connect", "garmin_export"] = "home_assistant"
    items: list[MetricIngestItem] = Field(min_length=1, max_length=100)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # MVP convenience. Production deployments should use Alembic migrations.
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Szymon Training Hub API", version="0.1.3", description="Personal training analytics backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()], allow_credentials=False, allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Hub-API-Key"])
@app.get("/health")
def health(): return {"status": "ok", "service": "training-hub-api", "version": app.version}

@app.get("/api/v1/dashboard", dependencies=[Depends(require_api_key)])
def get_dashboard(db: Session = Depends(get_db)): return dashboard(db)

@app.get("/api/v1/activities", dependencies=[Depends(require_api_key)])
def list_activities(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 200)
    rows = db.scalars(select(Activity).order_by(Activity.started_at.desc()).offset(max(offset, 0)).limit(limit)).all()
    count = db.scalar(select(func.count()).select_from(Activity)) or 0
    return {"total": count, "limit": limit, "offset": max(offset, 0), "items": [{"id": a.id, "source": a.source, "source_id": a.source_id, "name": a.name, "sport_type": a.sport_type, "started_at": a.started_at.isoformat(), "elapsed_seconds": a.elapsed_seconds, "distance_m": a.distance_m, "average_hr": a.average_hr} for a in rows]}

@app.get("/api/v1/metrics/daily", dependencies=[Depends(require_api_key)])
def get_metrics(db: Session = Depends(get_db)): return {"items": latest_metrics(db)}

@app.get("/api/v1/metrics/history", dependencies=[Depends(require_api_key)])
def get_metric_history(
    metric: str | None = None,
    source: str | None = None,
    source_entity_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Read stored measurements chronologically-filtered, newest first.

    This endpoint exposes only normalized fields, never raw attributes or secrets.
    It supports pagination so Android can retrieve long histories without oversized
    responses. Timestamps without an offset are interpreted as UTC.
    """
    query = select(MetricSample)
    if metric:
        query = query.where(MetricSample.metric == metric)
    if source:
        query = query.where(MetricSample.source == source)
    if source_entity_id:
        query = query.where(MetricSample.source_entity_id == source_entity_id)
    if start:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        query = query.where(MetricSample.measured_at >= start)
    if end:
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        query = query.where(MetricSample.measured_at <= end)
    safe_limit = min(max(limit, 1), 500)
    safe_offset = max(offset, 0)
    total_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(total_query) or 0
    rows = db.scalars(query.order_by(MetricSample.measured_at.desc(), MetricSample.id.desc()).offset(safe_offset).limit(safe_limit)).all()
    return {"total": total, "limit": safe_limit, "offset": safe_offset, "items": [
        {"id": row.id, "metric": row.metric, "value": row.value, "unit": row.unit,
         "measured_at": row.measured_at.isoformat(), "received_at": row.received_at.isoformat() if row.received_at else None,
         "source": row.source, "source_entity_id": row.source_entity_id, "quality": row.quality}
        for row in rows
    ]}

@app.post("/api/v1/metrics/ingest", dependencies=[Depends(require_api_key)])
def ingest_metrics(payload: MetricIngestRequest, db: Session = Depends(get_db)):
    """Ingest normalized measurements pushed by trusted Home Assistant integrations.

    Repeated polls of an unchanged HA state update the existing sample instead of
    filling the database with duplicate rows. Historical backfill can send older
    measured_at values in batches.
    """
    inserted = updated = ignored = 0
    for item in payload.items:
        measured_at = item.measured_at
        if measured_at.tzinfo is None:
            measured_at = measured_at.replace(tzinfo=timezone.utc)
        existing = db.scalar(select(MetricSample).where(
            MetricSample.source == payload.source,
            MetricSample.source_entity_id == item.source_entity_id,
            MetricSample.metric == item.metric,
            MetricSample.measured_at == measured_at,
        ))
        if existing:
            existing.value = item.value
            existing.unit = item.unit
            existing.quality = item.quality
            existing.raw_payload = item.attributes
            existing.received_at = datetime.now(timezone.utc)
            updated += 1
        else:
            db.add(MetricSample(metric=item.metric, value=item.value, unit=item.unit,
                measured_at=measured_at, received_at=datetime.now(timezone.utc),
                source=payload.source, source_entity_id=item.source_entity_id,
                quality=item.quality, raw_payload=item.attributes))
            inserted += 1
    conn = db.scalar(select(SourceConnection).where(SourceConnection.source == payload.source))
    now = datetime.now(timezone.utc)
    if not conn:
        conn = SourceConnection(source=payload.source)
        db.add(conn)
    conn.status = "connected"
    conn.last_success_at = now
    conn.last_attempt_at = now
    conn.last_error = None
    timestamps = [x.measured_at if x.measured_at.tzinfo else x.measured_at.replace(tzinfo=timezone.utc) for x in payload.items]
    batch_start, batch_end = min(timestamps), max(timestamps)
    old_start = conn.history_start
    old_end = conn.history_end
    if old_start is not None and old_start.tzinfo is None:
        old_start = old_start.replace(tzinfo=timezone.utc)
    if old_end is not None and old_end.tzinfo is None:
        old_end = old_end.replace(tzinfo=timezone.utc)
    conn.history_start = min([x for x in (old_start, batch_start) if x is not None])
    conn.history_end = max([x for x in (old_end, batch_end) if x is not None])
    db.commit()
    return {"source": payload.source, "received": len(payload.items), "inserted": inserted, "updated": updated, "ignored": ignored, "history_start": conn.history_start.isoformat(), "history_end": conn.history_end.isoformat()}

@app.get("/api/v1/analytics/load", dependencies=[Depends(require_api_key)])
def get_load(db: Session = Depends(get_db)): return load_summary(db)

@app.get("/api/v1/integrations/status", dependencies=[Depends(require_api_key)])
def integration_status(db: Session = Depends(get_db)):
    rows = db.scalars(select(SourceConnection)).all()
    known = {r.source: r for r in rows}
    return {"items": [{"source": source, "status": known[source].status if source in known else "not_configured", "last_success_at": known[source].last_success_at.isoformat() if source in known and known[source].last_success_at else None, "last_error": known[source].last_error if source in known else None, "history_start": known[source].history_start.isoformat() if source in known and known[source].history_start else None, "history_end": known[source].history_end.isoformat() if source in known and known[source].history_end else None} for source in ["strava", "home_assistant", "health_connect", "garmin_export"]]}

@app.get("/api/v1/connections/strava/authorize", dependencies=[Depends(require_api_key)])
def strava_authorize(db: Session = Depends(get_db)):
    try:
        state = new_oauth_state(db)
        return {"authorization_url": StravaClient().authorization_url(state), "note": "Open authorization_url in a browser and approve requested scopes."}
    except (StravaError, CredentialError) as exc:
        raise HTTPException(503, detail=str(exc))

@app.get("/api/v1/connections/strava/callback")
def strava_callback(code: str | None = None, error: str | None = None, state: str | None = None, db: Session = Depends(get_db)):
    if error: raise HTTPException(400, detail=f"Strava authorization denied: {error}")
    if not code or not state: raise HTTPException(400, detail="Missing OAuth code or state")
    if not consume_oauth_state(db, state): raise HTTPException(400, detail="Invalid or expired OAuth state")
    try:
        token_data = StravaClient().exchange_code(code)
        save_credentials(db, "strava", token_data)
        conn = db.scalar(select(SourceConnection).where(SourceConnection.source == "strava"))
        if not conn: db.add(SourceConnection(source="strava", status="connected"))
        else: conn.status, conn.last_error = "connected", None
        db.commit()
        return {"status": "connected", "athlete_id": token_data.get("athlete", {}).get("id"), "message": "Strava połączona. Token zapisano w zaszyfrowanej postaci."}
    except (StravaError, CredentialError) as exc:
        raise HTTPException(502, detail=str(exc))

@app.post("/api/v1/sync/strava", dependencies=[Depends(require_api_key)])
def sync_strava(db: Session = Depends(get_db)):
    try:
        token = load_credentials(db, "strava")
        if not token: raise HTTPException(409, detail="Strava is not connected; call /api/v1/connections/strava/authorize first")
        client = StravaClient()
        refreshed = client.refresh(token["refresh_token"])
        save_credentials(db, "strava", refreshed)
        # First sync imports all history available to the Strava account. Later runs
        # re-read a 7-day overlap so late edits/backfilled activities are not missed.
        connection = db.scalar(select(SourceConnection).where(SourceConnection.source == "strava"))
        latest = db.scalar(select(func.max(Activity.started_at)).where(Activity.source == "strava"))
        after_epoch = None
        if latest is not None:
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            after_epoch = int((latest - timedelta(days=7)).timestamp())
        result = import_activities(db, client, refreshed["access_token"], after_epoch=after_epoch, page_size=settings.sync_page_size)
        result["sync_mode"] = "full_history" if after_epoch is None else "incremental_with_7_day_overlap"
        result["history_start"] = connection.history_start.isoformat() if connection and connection.history_start else None
        result["history_end"] = connection.history_end.isoformat() if connection and connection.history_end else None
        return result
    except HTTPException: raise
    except (StravaError, CredentialError) as exc:
        conn = db.scalar(select(SourceConnection).where(SourceConnection.source == "strava"))
        if conn: conn.status, conn.last_error = "error", str(exc); db.commit()
        raise HTTPException(502, detail=str(exc))

@app.get("/api/v1/plan", dependencies=[Depends(require_api_key)])
def get_plan(db: Session = Depends(get_db)):
    rows = db.scalars(select(PlannedWorkout).order_by(PlannedWorkout.scheduled_date)).all()
    return {"items": [{"id": x.id, "plan_id": x.plan_id, "scheduled_date": x.scheduled_date, "title": x.title, "sport": x.sport, "status": x.status, "duration_minutes": x.duration_minutes, "intensity": x.intensity, "adaptation_reason": x.adaptation_reason, "version": x.version} for x in rows]}

@app.post("/api/v1/plan/workouts/{workout_id}/{action}", dependencies=[Depends(require_api_key)])
def update_workout(workout_id: int, action: str, db: Session = Depends(get_db)):
    if action not in ("complete", "skip"): raise HTTPException(404, detail="Action must be complete or skip")
    row = db.get(PlannedWorkout, workout_id)
    if not row: raise HTTPException(404, detail="Workout not found")
    row.status = "completed" if action == "complete" else "skipped"
    row.version += 1
    db.commit()
    return {"id": row.id, "status": row.status, "version": row.version, "adaptation": "Plan recalculation is queued for the next implementation slice."}
