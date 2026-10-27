"""
Admin authentication (blueprint's "Admin Protection" requirement).

A security audit found NO authentication anywhere on /admin/* — any
caller with network access could trigger the ingestion pipeline or
approve/reject community submissions. This is a shared-secret API key
check, appropriate for a small internal admin surface (not a public
multi-tenant API needing OAuth2/per-user accounts, which the blueprint
doesn't call for): every /admin/* request must carry a correct
`X-Admin-Api-Key` header matching `ADMIN_API_KEY` in the environment.

Deliberately fails closed: if ADMIN_API_KEY is unset/empty, every admin
request is rejected with a clear 500 explaining why, rather than silently
running with no auth (which is exactly the bug this module fixes).
"""
from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from shared.config import Settings, get_settings

_api_key_header = APIKeyHeader(name="X-Admin-Api-Key", auto_error=False)


async def require_admin_api_key(
    provided_key: str | None = Security(_api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_API_KEY is not configured on the server — refusing to run with no admin "
            "authentication. Set ADMIN_API_KEY in the environment.",
        )
    if not provided_key:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Api-Key header.")
    # Constant-time comparison — a naive `==` here would leak timing
    # information about how many leading characters of the key are
    # correct, which is a real (if narrow) attack surface for a secret
    # compared over the network.
    if not hmac.compare_digest(provided_key, settings.admin_api_key):
        raise HTTPException(status_code=403, detail="Invalid admin API key.")
