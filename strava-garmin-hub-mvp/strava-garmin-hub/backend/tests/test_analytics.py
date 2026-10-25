from app.analytics.core import STALE_HOURS

def test_stale_threshold_is_explicit():
    assert STALE_HOURS == 36
