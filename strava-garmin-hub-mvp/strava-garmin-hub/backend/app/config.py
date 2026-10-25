from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://hub:change-me@localhost:5432/traininghub"
    hub_api_key: str = "change-this-before-use"
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/api/v1/connections/strava/callback"
    strava_scopes: str = "read,activity:read_all,profile:read_all"
    public_base_url: str = "http://localhost:8000"
    sync_page_size: int = 100
    sync_request_delay_seconds: float = 1.0
    cors_origins: str = "http://localhost:8080"
    token_encryption_key: str = ""

settings = Settings()
