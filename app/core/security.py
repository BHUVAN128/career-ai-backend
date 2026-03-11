from datetime import datetime, timedelta, timezone
import hashlib, hmac, os, base64
from jose import JWTError, jwt
from app.config import settings
from app.core.exceptions import UnauthorizedError


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-SHA256 with a random salt."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return base64.b64encode(salt + dk).decode()


def verify_password(plain: str, stored: str) -> bool:
    """Verify a plain password against a stored PBKDF2-SHA256 hash."""
    try:
        raw = base64.b64decode(stored.encode())
        salt, dk = raw[:16], raw[16:]
        check = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, 260_000)
        return hmac.compare_digest(dk, check)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")


def decode_supabase_token(token: str) -> dict:
    """Decode a Supabase JWT using the Supabase JWT secret."""
    secret = settings.SUPABASE_JWT_SECRET or settings.JWT_SECRET_KEY
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM], options={"verify_aud": False})
        return payload
    except JWTError:
        raise UnauthorizedError("Invalid Supabase token")
