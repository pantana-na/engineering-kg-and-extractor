"""Zero-Trust IAP JWT verification, rate limiting, and deterministic HITL gates.

Implements SPEC-20261120-UNIFIED-WORKBENCH-V2 Section 3.2 & Rule 10 (Pattern 1B Direct Cloud Run IAP).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

IAP_ISSUER = "https://cloud.google.com/iap"
IAP_JWKS_URI = "https://www.gstatic.com/iap/verify/public_key-jwk"
PURGE_CONFIRM_HEADER = "X-Confirm-Purge"
PURGE_CONFIRM_VALUE = "CONFIRMED"
IDEMPOTENCY_HEADER = "X-Idempotency-Key"


@dataclass(frozen=True)
class VerifiedPrincipal:
    """Authenticated caller identity extracted from verified IAP JWT or local dev context."""

    email: str
    subject: str
    auth_mode: str  # "iap_jwt" | "local_dev"


def is_iap_jwt_enforced() -> bool:
    """Return True when cryptographic `x-goog-iap-jwt-assertion` enforcement is enabled."""
    raw = os.getenv("IAP_JWT_ENFORCEMENT", "").strip().lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    # Auto-enforce on Cloud Run when security mode is 'iap' and audience is configured
    on_cloud_run = bool(os.getenv("K_SERVICE", "").strip())
    sec_mode = os.getenv("CLOUD_RUN_SECURITY_MODE", "iap").strip().lower()
    audience = os.getenv("IAP_JWT_AUDIENCE", "").strip()
    return on_cloud_run and sec_mode == "iap" and bool(audience)


def verify_iap_jwt_assertion(
    token: str,
    *,
    expected_audience: str | None = None,
    verifier: Callable[..., dict[str, Any]] | None = None,
) -> VerifiedPrincipal:
    """Cryptographically verify Google Cloud IAP `x-goog-iap-jwt-assertion` JWT."""
    cleaned = (token or "").strip()
    if not cleaned:
        raise HTTPException(
            status_code=401,
            detail="Missing x-goog-iap-jwt-assertion header.",
        )

    audience = (expected_audience or os.getenv("IAP_JWT_AUDIENCE", "")).strip() or None

    try:
        if verifier is not None:
            claims = verifier(cleaned, audience=audience)
        else:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

            claims = id_token.verify_token(
                cleaned,
                google_requests.Request(),
                audience=audience,
                certs_url=IAP_JWKS_URI,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("IAP JWT cryptographic verification failed: %s", exc)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired IAP JWT assertion.",
        ) from exc

    iss = str(claims.get("iss") or "")
    if iss != IAP_ISSUER:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid IAP JWT issuer: expected '{IAP_ISSUER}'.",
        )

    email = str(claims.get("email") or "").strip()
    sub = str(claims.get("sub") or "").strip()
    if not email and not sub:
        raise HTTPException(
            status_code=401,
            detail="IAP JWT missing principal identity claims.",
        )

    return VerifiedPrincipal(
        email=email or sub,
        subject=sub or email,
        auth_mode="iap_jwt",
    )


def resolve_request_principal(
    request: Request,
    *,
    verifier: Callable[..., dict[str, Any]] | None = None,
) -> VerifiedPrincipal:
    """Resolve authenticated principal for an incoming FastAPI request."""
    jwt_token = request.headers.get("x-goog-iap-jwt-assertion", "").strip()
    if is_iap_jwt_enforced():
        return verify_iap_jwt_assertion(jwt_token, verifier=verifier)

    if jwt_token:
        return verify_iap_jwt_assertion(jwt_token, verifier=verifier)

    return VerifiedPrincipal(
        email="local-dev@workbench.local",
        subject="local-dev",
        auth_mode="local_dev",
    )


def enforce_purge_hitl_gate(
    *,
    purge: bool,
    confirm_header: str | None,
    idempotency_key: str | None,
) -> None:
    """Deterministic externalized HITL gate for destructive Spanner purge (`SAIF RAC`)."""
    if not purge:
        return
    clean_confirm = (confirm_header or "").strip()
    if clean_confirm != PURGE_CONFIRM_VALUE:
        raise HTTPException(
            status_code=400,
            detail=(
                "Destructive Spanner purge requires explicit human confirmation header "
                f"'{PURGE_CONFIRM_HEADER}: {PURGE_CONFIRM_VALUE}'."
            ),
        )
    clean_idem = (idempotency_key or "").strip()
    if not clean_idem or len(clean_idem) < 8:
        raise HTTPException(
            status_code=400,
            detail=(
                "Destructive Spanner purge requires a valid non-empty "
                f"'{IDEMPOTENCY_HEADER}' header (>= 8 characters)."
            ),
        )


class SlidingWindowRateLimiter:
    """In-process per-principal sliding-window rate limiter compensating for Pattern 1B."""

    def __init__(self, *, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max(1, int(max_requests))
        self.window_seconds = max(1.0, float(window_seconds))
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._buckets.setdefault(key, deque())
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Rate limit exceeded ({self.max_requests} requests per "
                        f"{int(self.window_seconds)}s). Please retry shortly."
                    ),
                )
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
