# Architecture and implementation notes

## Source-of-truth rules
1. Backend owns canonical activity/metric data and all analytics decisions.
2. Android and Home Assistant are clients; neither independently computes readiness.
3. Preserve source IDs, original payloads where permitted, measurement time, receive time, unit, provenance, and quality flags.
4. Missing values remain missing; do not substitute zero or infer measurements from unrelated sessions.
5. Store analytics algorithm version and explanation alongside recommendations.

## Current first-slice implementation
- FastAPI + SQLAlchemy + PostgreSQL schema.
- Tables: activities, metric_samples, source_connections, planned_workouts, OAuth states and encrypted credentials.
- Strava OAuth authorization state with a ten-minute lifetime; credentials are encrypted with a Fernet key in the environment.
- Strava activity import with page-level commits and idempotent source/source_id upsert.
- Dashboard, activity listing, metrics, load summary, integration status and plan endpoints.
- Home Assistant config flow + API-backed sensors.
- Native Android Compose navigation shell.

## Known gaps / next implementation slice
- Replace `Base.metadata.create_all` with Alembic migration workflow before production.
- Harden OAuth callback with reverse-proxy HTTPS, rate limits, audit logging, explicit state binding to initiating user, and test callback end-to-end.
- Add a persistent import job table and durable page cursor; current importer commits each page but restarts from page 1 after process restart.
- Add Strava rate-limit response headers, Retry-After handling and jittered exponential backoff.
- Add activity detail/stream import and webhook subscription/validation.
- Implement Garmin/HA source metric mapping UI and recorder-history backfill.
- Add proper per-user auth/session model before any multi-user use; current API key is for a single-user home deployment.
- Add Android Retrofit repository, encrypted API-key setup, offline cache, Health Connect permission flow and instrumentation tests.
- Expand readiness and load algorithms only after validating real data coverage and defining sport-specific load semantics.

## API authentication
All `/api/v1/*` endpoints except the OAuth callback currently require `X-Hub-API-Key`. Keep the API bound to localhost/LAN behind a trusted TLS reverse proxy. Never expose PostgreSQL publicly. The Home Assistant integration stores the API key in its config entry and sends it as a request header.
