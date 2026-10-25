from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Activity, MetricSample

STALE_HOURS = 36

def latest_metrics(db: Session) -> list[dict]:
    rows = db.scalars(select(MetricSample).order_by(MetricSample.measured_at.desc()).limit(1000)).all()
    latest = {}
    for r in rows:
        if r.metric not in latest: latest[r.metric] = r
    now = datetime.now(timezone.utc)
    return [{"metric": r.metric, "value": r.value, "unit": r.unit, "measured_at": r.measured_at.isoformat(), "source": r.source, "quality": r.quality, "stale": (now - (r.measured_at if r.measured_at.tzinfo else r.measured_at.replace(tzinfo=timezone.utc))).total_seconds() > STALE_HOURS*3600} for r in latest.values()]

def dashboard(db: Session) -> dict:
    activities = db.scalars(select(Activity).order_by(Activity.started_at.desc()).limit(10)).all()
    total = db.scalar(select(Activity.id).limit(1))
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "activity_count_nonzero": total is not None, "recent_activities": [{"id": a.id, "source": a.source, "source_id": a.source_id, "name": a.name, "sport_type": a.sport_type, "started_at": a.started_at.isoformat(), "distance_m": a.distance_m, "elapsed_seconds": a.elapsed_seconds, "average_hr": a.average_hr} for a in activities], "latest_metrics": latest_metrics(db), "readiness": {"status": "insufficient_data", "score": None, "reason": "Readiness scoring activates only after sufficient, fresh personal history is available."}}

def load_summary(db: Session) -> dict:
    # Transparent baseline: duration-based training minutes until an explicit sport-specific load model is calibrated.
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(Activity).where(Activity.started_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))).all()
    return {"method": "elapsed_training_minutes_v1", "today_sessions": len(rows), "today_minutes": round(sum((a.elapsed_seconds or 0) for a in rows)/60, 1), "warning": "Not a medical readiness score; sport-specific load model is not yet calibrated."}
