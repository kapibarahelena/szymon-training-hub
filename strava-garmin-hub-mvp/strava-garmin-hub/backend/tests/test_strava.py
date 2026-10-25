from datetime import timezone
from app.connectors.strava import parse_start_time

def test_parse_zulu_time():
    dt = parse_start_time("2024-01-02T03:04:05Z")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0

def test_parse_offset_time():
    dt = parse_start_time("2024-01-02T04:04:05+01:00")
    assert dt.astimezone(timezone.utc).hour == 3


def test_import_activities_is_idempotent_and_tracks_history():
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import Activity, SourceConnection
    from app.connectors.strava import import_activities

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    class FakeClient:
        def __init__(self):
            self.calls = 0
        def get(self, path, access_token, params=None):
            self.calls += 1
            if self.calls == 1:
                return [{"id": 123, "name": "Easy run", "sport_type": "Run",
                         "start_date": "2026-10-20T07:00:00Z", "elapsed_time": 1800,
                         "moving_time": 1750, "distance": 5000, "total_elevation_gain": 20}]
            return []

    with Session() as db:
        result = import_activities(db, FakeClient(), "token", page_size=100)
        assert result["imported_or_updated"] == 1
        assert result["history_start"].startswith("2026-10-20T07:00:00")
        assert db.scalar(select(func.count()).select_from(Activity)) == 1
        # A repeated import of the same activity updates, rather than duplicates, it.
        result2 = import_activities(db, FakeClient(), "token", page_size=100)
        assert result2["imported_or_updated"] == 1
        assert db.scalar(select(func.count()).select_from(Activity)) == 1
        connection = db.scalar(select(SourceConnection).where(SourceConnection.source == "strava"))
        assert connection.status == "connected"
        assert connection.history_end is not None


def test_import_failure_sets_connection_error_state():
    from sqlalchemy import select
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import SourceConnection
    from app.connectors.strava import StravaError, import_activities

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    class FailingClient:
        def get(self, path, access_token, params=None):
            raise StravaError("rate limit reached")

    with Session() as db:
        try:
            import_activities(db, FailingClient(), "token")
            assert False, "Expected StravaError"
        except StravaError:
            pass
        connection = db.scalar(select(SourceConnection).where(SourceConnection.source == "strava"))
        assert connection.status == "error"
        assert "rate limit" in connection.last_error
