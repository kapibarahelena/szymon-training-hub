# Strava connection setup

1. Create a Strava API application in your Strava developer settings.
2. Set its Authorization Callback Domain to the hostname used to reach this backend. For local development, Strava callback/domain restrictions may require a publicly reachable development URL or a suitable local tunnel; do not assume `localhost` will be accepted in every configuration.
3. Copy Client ID and Client Secret to `deploy/.env` as `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET`.
4. Generate a Fernet key and set `TOKEN_ENCRYPTION_KEY`:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
5. Set `STRAVA_REDIRECT_URI` to the exact registered callback URL.
6. Restart the API. Call `GET /api/v1/connections/strava/authorize` with `X-Hub-API-Key`; open the returned `authorization_url` and approve access.
7. Strava redirects to the callback. On success the API reports connection status and stores the token response encrypted in PostgreSQL.
8. Call `POST /api/v1/sync/strava` with `X-Hub-API-Key` to import activities.

Do not paste access tokens, refresh tokens, client secrets, or API keys into chat or screenshots. Back up `TOKEN_ENCRYPTION_KEY` separately and securely: without it saved tokens cannot be decrypted. Rotating it requires decrypt-and-reencrypt migration.

## History notes
The importer walks activity pages from newest to oldest until the API returns an empty/short page, within API access and rate limits. It imports activity summary fields available in the response. Streams and all historical wellness metrics are not automatically included in this first slice. The next slice should add durable import-job checkpoints and rate-limit-aware retry.
