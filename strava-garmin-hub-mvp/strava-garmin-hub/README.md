# Szymon Training Hub

Personal sports analytics hub: Strava + Garmin/Home Assistant + native Android. The backend is the source of truth; clients do not calculate separate versions of analytics.

## Repository layout
- `backend/` FastAPI API, PostgreSQL schema, Strava OAuth/import and deterministic analytics.
- `homeassistant/custom_components/szymon_training_hub/` Home Assistant custom integration (config flow + API-backed sensors).
- `android/` native Kotlin + Jetpack Compose starter.
- `deploy/` Docker Compose and environment template.
- `docs/` technical decisions, API contract, history/backfill and the original HTML source for reference.

## Run the backend locally
1. Copy `deploy/.env.example` to `deploy/.env` and set `HUB_API_KEY` and database credentials.
2. From `deploy/`: `docker compose up --build`.
3. API docs: `http://localhost:8000/docs`; health: `http://localhost:8000/health`.

The API port is published to the host so Home Assistant on the same trusted LAN can reach it; do not expose it directly to the public Internet. Use HTTPS/reverse proxy and firewall rules for remote access. The Strava connector requires your own Strava API application credentials. Configure them only in the backend environment, never in Android or Home Assistant sensor attributes. See `docs/STRAVA_SETUP.md`.

## API additions in 0.1.3
- `GET /api/v1/metrics/history` returns normalized historical measurements with optional `metric`, `source`, `source_entity_id`, `start`, `end`, `limit`, and `offset` filters. Requires `X-Hub-API-Key`.

## Current status
This is the incremental implementation scaffold, not a claim that external account connections have been verified. Strava import needs user credentials; Garmin history depends on the access path available in your account/integration. Android needs an installed Android SDK to build the APK. Run `backend/scripts/check.sh` or `pytest` after installing dependencies.


### Ostatnia iteracja 0.1.1

- Pierwsza synchronizacja Stravy pobiera całą historię udostępnioną przez API; kolejne synchronizacje używają 7-dniowego okna nakładania.
- Zapis zakresu dat importu i statusu błędu ułatwia kontrolę kompletności danych.
- Testy importu potwierdzają idempotencję oraz jawny status błędu.
- FastAPI uruchamia inicjalizację schematu przez lifespan.
- Walidacja lokalna: `6 passed`; brak testu z prawdziwym kontem Strava i brak wdrożenia na serwerze.

### Home Assistant metric mapping (0.1.2 increment)

In the Home Assistant integration config, enter one mapping per line as `entity_id;metric;unit`, for example:

```text
sensor.garmin_connect_waga;weight;kg
sensor.szymon_czas_snu;sleep_duration;h
```

The integration reads current HA states locally and sends numeric measurements to the backend's authenticated `/api/v1/metrics/ingest` endpoint. The configured backend URL and API key must be reachable/correct. This is live-state ingestion, not a complete historical Recorder backfill yet.

### Android client connection (0.1.4 increment)

The native Compose client now has a Settings tab for backend URL and API key, stores settings using Android encrypted shared preferences, and reads dashboard, activity history and integration status from the API. Use an HTTPS endpoint for normal use; the app intentionally blocks cleartext HTTP. This client has not yet been built with an Android SDK in this environment, so build it in Android Studio before installing it on your phone.

### Automated checks and Android APK (0.1.5 increment)

GitHub Actions workflow `.github/workflows/ci.yml` runs backend tests and builds a debug APK using a GitHub-hosted runner. See `docs/GITHUB_ACTIONS.md` for how to trigger a build and download the APK artifact. The APK is for testing only and is not a signed production release.
