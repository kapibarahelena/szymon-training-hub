import json, hashlib, secrets
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.config import settings
from app.models import OAuthState, SecretCredential

class CredentialError(RuntimeError): pass

def _fernet():
    key = settings.token_encryption_key.strip()
    if not key:
        raise CredentialError("TOKEN_ENCRYPTION_KEY is not configured")
    try: return Fernet(key.encode())
    except Exception as exc: raise CredentialError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc

def new_oauth_state(db: Session, source: str = "strava") -> str:
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    db.add(OAuthState(source=source, state_hash=digest)); db.commit()
    return raw

def consume_oauth_state(db: Session, raw: str, source: str = "strava") -> bool:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    row = db.scalar(select(OAuthState).where(OAuthState.source == source, OAuthState.state_hash == digest))
    if not row: return False
    # OAuth states expire after 10 minutes.
    from datetime import datetime, timezone, timedelta
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    db.delete(row); db.commit()
    return datetime.now(timezone.utc) - created <= timedelta(minutes=10)

def save_credentials(db: Session, source: str, payload: dict) -> None:
    encrypted = _fernet().encrypt(json.dumps(payload).encode()).decode()
    row = db.scalar(select(SecretCredential).where(SecretCredential.source == source))
    if row: row.encrypted_json = encrypted
    else: db.add(SecretCredential(source=source, encrypted_json=encrypted))
    db.commit()

def load_credentials(db: Session, source: str) -> dict | None:
    row = db.scalar(select(SecretCredential).where(SecretCredential.source == source))
    if not row: return None
    try: return json.loads(_fernet().decrypt(row.encrypted_json.encode()))
    except (InvalidToken, ValueError) as exc: raise CredentialError("Cannot decrypt saved credentials; check TOKEN_ENCRYPTION_KEY") from exc
