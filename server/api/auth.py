"""API key authentication middleware.

The tvOS app authenticates with a shared secret in the Authorization header:
    Authorization: Bearer {BRG_API_KEY}

Validated with constant-time comparison to prevent timing attacks.
"""

import hmac

from fastapi import Request, HTTPException


def verify_api_key(request: Request) -> None:
    """FastAPI dependency that validates the API key from the Authorization header."""
    expected_key: str = request.app.state.api_key
    if not expected_key:
        # No API key configured — skip auth (development mode)
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    provided_key = auth_header[7:]  # Strip "Bearer "
    if not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
