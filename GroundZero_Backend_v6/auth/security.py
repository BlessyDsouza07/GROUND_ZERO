"""Password hashing and signed tokens using only the Python standard library.

Passwords: scrypt with a per-user random salt.
Tokens: a compact HMAC-signed, JWT-shaped token (header.payload.signature).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_cached_secret: str | None = None


def _secret() -> bytes:
    """Resolve the signing key.

    Order: real environment variable -> AUTH_SECRET_KEY in the backend's
    .env file (python-dotenv is only used by Layer 3 / Live Events for
    their own .env files, so this file was never loaded into os.environ
    on Windows, where run_server.sh's `source .env` doesn't exist) ->
    development only: a random key generated once and stored in
    .dev_auth_secret so logins survive restarts. Production/staging with
    no key still fails loudly.
    """
    global _cached_secret
    if _cached_secret:
        return _cached_secret.encode()
    key = os.environ.get("AUTH_SECRET_KEY", "")
    if len(key) < 32:
        try:
            from dotenv import dotenv_values

            key = (dotenv_values(_BACKEND_ROOT / ".env").get("AUTH_SECRET_KEY") or "").strip()
        except Exception:
            key = ""
    if len(key) < 32 and os.environ.get("ENVIRONMENT", _env_file_environment()) == "development":
        secret_file = _BACKEND_ROOT / ".dev_auth_secret"
        try:
            key = secret_file.read_text().strip() if secret_file.exists() else ""
            if len(key) < 32:
                key = secrets.token_urlsafe(48)
                secret_file.write_text(key)
        except OSError:
            key = secrets.token_urlsafe(48)  # read-only disk: key lasts for this process only
    if len(key) < 32:
        raise RuntimeError(
            "AUTH_SECRET_KEY must be set (32+ chars). Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    _cached_secret = key
    return key.encode()


def _env_file_environment() -> str:
    try:
        from dotenv import dotenv_values

        return (dotenv_values(_BACKEND_ROOT / ".env").get("ENVIRONMENT") or "development").strip()
    except Exception:
        return "development"


def create_token(user_id: str, ttl_seconds: int = 60 * 60 * 24 * 7) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    now = int(time.time())
    body = _b64(
        json.dumps({"sub": user_id, "iat": now, "exp": now + ttl_seconds}, separators=(",", ":")).encode()
    )
    sig = _b64(hmac.new(_secret(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def decode_token(token: str) -> str | None:
    """Return the user id if the token is valid and unexpired, else None."""
    try:
        header, body, sig = token.split(".")
        expected = _b64(hmac.new(_secret(), f"{header}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if int(payload["exp"]) < time.time():
            return None
        return str(payload["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
