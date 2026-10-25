# GitHub Actions: backend tests and Android APK

The workflow at `.github/workflows/ci.yml` runs the backend test suite and builds a debug APK on GitHub-hosted Linux runners. It does not need Strava credentials, a Home Assistant URL, or a backend API key.

## Trigger

It runs after pushes to `main` that touch `strava-garmin-hub/**` or workflow files, on matching pull requests, or manually from **Actions → Szymon Training Hub CI → Run workflow**.

## Find the APK

1. Open the repository on GitHub and choose **Actions**.
2. Open the latest **Szymon Training Hub CI** run.
3. Wait for both **Backend tests** and **Build Android debug APK** to pass.
4. At the bottom of the successful run, download the artifact named `szymon-training-hub-debug-apk`.
5. Extract the ZIP; it contains `app-debug.apk`.

This is a debug build for testing, not a signed production release. The workflow does not publish secrets and does not attempt to connect to any real accounts.

## If the build fails

Open the failed job and copy the first relevant error plus about 20 lines around it. Do not share API keys, OAuth client secrets, access tokens, or `.env` contents.
