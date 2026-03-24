"""API key authentication middleware.

The tvOS app authenticates with a shared secret in the Authorization header:
    Authorization: Bearer {BRG_API_KEY}

Validates against the master API key first, then checks paired device keys.
Uses constant-time comparison to prevent timing attacks.
"""

import hmac

from fastapi import Request, HTTPException


def verify_api_key(request: Request) -> None:
    """FastAPI dependency that validates the API key from the Authorization header.

    Accepts either the master BRG_API_KEY or a paired device's API key.
    """
    expected_key: str = request.app.state.api_key
    if not expected_key:
        # No API key configured — skip auth (development mode)
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    provided_key = auth_header[7:]  # Strip "Bearer "

    # Check master API key first
    if hmac.compare_digest(provided_key, expected_key):
        return

    # Check paired device keys
    from api import routes as api_routes
    if api_routes.video_store:
        device = api_routes.video_store.get_device_by_api_key(provided_key)
        if device:
            # Update last_seen_at for the device
            api_routes.video_store.update_device_last_seen(device["id"])
            return

    raise HTTPException(status_code=401, detail="Invalid API key")
