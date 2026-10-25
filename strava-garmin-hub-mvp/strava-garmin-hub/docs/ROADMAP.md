# Roadmap and acceptance gates

## Slice 1 — foundations (this repository)
- [x] FastAPI app and health endpoint
- [x] PostgreSQL schema for activities, metrics, integrations, workouts and encrypted credentials
- [x] Strava OAuth state + encrypted credential storage and paginated activity import path
- [x] Basic dashboard/list/metrics/load/status/plan endpoints
- [x] Home Assistant config flow and sensor entities
- [x] Native Android Compose shell
- [x] Documentation and starter tests

## Slice 2 — reliable sync
- [ ] Alembic migrations
- [ ] Durable job queue/checkpoint model and idempotent resume
- [ ] Retry-After + backoff and rate-limit telemetry
- [ ] Strava detailed activity and streams ingestion
- [ ] Webhook subscription and periodic reconciliation
- [ ] Test OAuth with real developer app

## Slice 3 — Garmin and HA history
- [ ] HA entity mapping config screen / config options flow
- [ ] Normalize entity state and attributes to canonical metric samples
- [ ] Recorder history import with retention/availability disclosure
- [ ] Import Garmin export FIT/CSV/JSON where supported
- [ ] Per-source history coverage report

## Slice 4 — analytics
- [ ] Transparent 7-day and 42-day load model with tests
- [ ] Pace/HR efficiency trends by sport and conditions where available
- [ ] Readiness baseline based on personal history and data quality
- [ ] Plan adaptation proposal, confirmation and rollback
- [ ] Historical recalculation by algorithm version

## Slice 5 — Android native app
- [ ] Backend URL and API key setup in encrypted storage
- [ ] Retrofit client + repository + view models
- [ ] Dashboard, history, plan, trends, integrations
- [ ] Health Connect permissions and historical read where eligible
- [ ] WorkManager sync, cache, notification permissions
- [ ] Unit and instrumentation tests; signed debug APK

## Slice 6 — reliability and release
- [ ] Backup and restore rehearsal
- [ ] API auth/rate limiting/TLS deployment guide
- [ ] Home Assistant real installation test
- [ ] Android device test
- [ ] Privacy/data deletion/export controls
- [ ] AI/nutrition/GPX modules only after core reliability

## Iteracja 0.1.1 — stabilność synchronizacji (2026-10-25)
- Pierwsze połączenie Strava wykonuje pełny import historii dostępnej przez API (`after` bez ograniczenia daty).
- Kolejne synchronizacje używają 7-dniowego okna nakładania; to pozwala aktualizować ostatnie treningi i przechwycić niedawno dopisane/zmienione wpisy bez ponownego skanowania całej historii.
- Import jest idempotentny (klucz źródło + ID aktywności), zapisuje zakres dat historii i ustawia status `error` z komunikatem, gdy API zawiedzie.
- FastAPI korzysta z lifespan zamiast przestarzałego `on_event("startup")`.
- Dodano testy regresyjne dla idempotencji importu, zakresu historii i błędów konektora.

Uwaga: to nadal synchroniczny endpoint MVP. Przed długimi importami na serwerze należy przenieść synchronizację do kolejki zadań, dodać retry/backoff i respektowanie limitów Stravy. Strava może udostępniać tylko dane dozwolone przez konto i przyznane zakresy OAuth.

## 0.1.2 — Home Assistant metric ingestion (implementation increment)

- Added authenticated `POST /api/v1/metrics/ingest` endpoint for normalized numeric measurements.
- Supports batches up to 100 samples and records source entity, unit, measurement time, quality, and optional attributes.
- Repeated polls of the same source/entity/metric/timestamp update the existing row rather than creating another sample.
- Home Assistant integration can map entity IDs using one line per entity in the config flow field `Metric entities`, format `entity_id;metric;unit`.
- Default examples: `sensor.garmin_connect_waga;weight;kg` and `sensor.szymon_czas_snu;sleep_duration;h`.
- This increment pushes current HA states when the coordinator refreshes. It does not yet backfill historical states from Recorder; current state history_start/history_end must not be interpreted as proof that all past history has been imported.
- After changing HA integration code, reload/restart Home Assistant and configure the entity mapping. Ensure the backend URL is reachable from Home Assistant and API key matches `HUB_API_KEY`.

## Implemented in 0.1.3
- Added authenticated `GET /api/v1/metrics/history` with filters for metric, source, entity, time range, and pagination (max 500 rows/page).
- History responses expose normalized measurement fields only; raw attributes are not returned by this endpoint.
- Added API tests for filtered/paginated history and authentication.
- Validation: 10 backend tests pass locally. This does not yet prove a live Home Assistant/Strava connection.

## Next
- Add a supported Home Assistant Recorder backfill workflow (not just current entity states).
- Add persistent sync jobs and retry/backoff for Strava rate limits.
- Connect Android screens to the authenticated API and add secure endpoint/API-key setup.

## 0.1.4 — Android API connection
- Added encrypted on-device storage for backend URL and API key.
- Added live API reads for dashboard, recent activities and integration statuses.
- The Android project still requires an Android SDK/Gradle build verification before APK distribution.
- Next: proper typed Retrofit models/repository, loading and empty states, history charts, and end-to-end device test.
