"""Zero-Trust IAP JWT verification, rate limiting, and deterministic HITL gates.

Implements SPEC-20261120-UNIFIED-WORKBENCH-V2 Section 3.2 & Rule 10 (Pattern 1B Direct Cloud Run IAP).
Uses RFC 7517 JWK Set (`public_key-jwk`) via PyJWT with thread-safe in-memory TTL caching,
strict ES256 signature verification, issuer pinning, and Cloud Run Native IAP audience enforcement.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

IAP_ISSUER = "https://cloud.google.com/iap"
IAP_JWKS_URI = "https://www.gstatic.com/iap/verify/public_key-jwk"
IAP_ALLOWED_ALGORITHMS = ["ES256"]
IAP_JWK_CACHE_TTL_SECONDS = 3600.0
IAP_JWK_REFRESH_COOLDOWN_SECONDS = 30.0
IAP_CLOCK_SKEW_LEEWAY_SECONDS = 30
PURGE_CONFIRM_HEADER = "X-Confirm-Purge"
PURGE_CONFIRM_VALUE = "CONFIRMED"
IDEMPOTENCY_HEADER = "X-Idempotency-Key"


@dataclass(frozen=True)
class VerifiedPrincipal:
    """Authenticated caller identity extracted from verified IAP JWT or local dev context."""

    email: str
    subject: str
    auth_mode: str  # "iap_jwt" | "local_dev"


class _IapJwkCache:
    """Thread-safe TTL cache for Google IAP RFC 7517 JWK Set (`public_key-jwk`)."""

    def __init__(self, jwks_uri: str = IAP_JWKS_URI) -> None:
        self._jwks_uri = jwks_uri
        self._lock = threading.Lock()
        self._jwks_dict: dict[str, Any] | None = None
        self._fetched_at: float = 0.0

    def get_jwks(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            is_fresh = (
                self._jwks_dict is not None
                and (now - self._fetched_at) < IAP_JWK_CACHE_TTL_SECONDS
            )
            if is_fresh and not force_refresh:
                return self._jwks_dict  # type: ignore[return-value]
            if (
                force_refresh
                and self._jwks_dict is not None
                and (now - self._fetched_at) < IAP_JWK_REFRESH_COOLDOWN_SECONDS
            ):
                return self._jwks_dict

        resp = httpx.get(self._jwks_uri, timeout=5.0)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict) or "keys" not in payload:
            raise ValueError("Invalid IAP JWK Set payload: missing 'keys'.")

        with self._lock:
            self._jwks_dict = payload
            self._fetched_at = time.monotonic()
        return payload

    def clear(self) -> None:
        with self._lock:
            self._jwks_dict = None
            self._fetched_at = 0.0


_IAP_JWK_CACHE = _IapJwkCache()


def clear_iap_jwk_cache() -> None:
    """Clear the cached IAP JWK Set (primarily for tests)."""
    _IAP_JWK_CACHE.clear()


def resolve_expected_iap_audience(explicit_audience: str | None = None) -> str | None:
    """Resolve the expected IAP JWT `aud` claim.

    Priority:
    1. Explicit argument passed by caller.
    2. `IAP_JWT_AUDIENCE` environment variable.
    3. Auto-derived Cloud Run Native IAP audience:
       `/projects/<PROJECT_NUMBER>/locations/<REGION>/services/<SERVICE_NAME>`
       when running on Cloud Run (`K_SERVICE`) with a valid numeric project number.
    """
    raw = (explicit_audience or os.getenv("IAP_JWT_AUDIENCE", "")).strip()
    if raw:
        return raw

    service_name = os.getenv("K_SERVICE", "").strip()
    project_number = os.getenv("GOOGLE_CLOUD_PROJECT_NUMBER", "").strip()
    region = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip()
    if (
        service_name
        and region
        and project_number.isdigit()
        and project_number != "000000000000"
    ):
        return f"/projects/{project_number}/locations/{region}/services/{service_name}"
    return None


def is_iap_jwt_enforced() -> bool:
    """Return True when cryptographic `x-goog-iap-jwt-assertion` enforcement is enabled."""
    raw = os.getenv("IAP_JWT_ENFORCEMENT", "").strip().lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    # Auto-enforce on Cloud Run when security mode is 'iap' and audience is configured/derivable
    on_cloud_run = bool(os.getenv("K_SERVICE", "").strip())
    sec_mode = os.getenv("CLOUD_RUN_SECURITY_MODE", "iap").strip().lower()
    audience = resolve_expected_iap_audience()
    return on_cloud_run and sec_mode == "iap" and bool(audience)


def _decode_iap_jwt_with_pyjwt(
    token: str,
    *,
    audience: str | None,
    jwks_provider: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Verify an IAP ES256 JWT against Google's cached RFC 7517 JWK Set via PyJWT."""
    import jwt as pyjwt
    from jwt.api_jwk import PyJWKSet

    header = pyjwt.get_unverified_header(token)
    alg = str(header.get("alg") or "")
    if alg not in IAP_ALLOWED_ALGORITHMS:
        raise ValueError(f"Unsupported IAP JWT algorithm '{alg}'; expected {IAP_ALLOWED_ALGORITHMS}.")

    kid = header.get("kid")
    if not kid:
        raise ValueError("IAP JWT header is missing key ID ('kid').")

    fetch_fn = jwks_provider or _IAP_JWK_CACHE.get_jwks
    jwks_dict = fetch_fn(force_refresh=False)

    def _find_key(data: dict[str, Any]) -> Any:
        jwk_set = PyJWKSet.from_dict(data)
        for key in jwk_set.keys:
            if key.key_id == kid and key.public_key_use in ("sig", None):
                return key
        return None

    signing_key = _find_key(jwks_dict)
    if signing_key is None:
        # Handle key rotation by forcing a single cache refresh
        jwks_dict = fetch_fn(force_refresh=True)
        signing_key = _find_key(jwks_dict)

    if signing_key is None:
        raise ValueError(f"Unable to find matching IAP signing key for kid='{kid}'.")

    decode_options: dict[str, Any] = {
        "require": ["exp", "iat", "iss"],
        "verify_signature": True,
        "verify_exp": True,
        "verify_iat": True,
        "verify_iss": True,
        "verify_aud": bool(audience),
    }

    audience_arg: str | list[str] | None = None
    if audience:
        parts = [p.strip() for p in audience.split(",") if p.strip()]
        audience_arg = parts[0] if len(parts) == 1 else parts

    claims = pyjwt.decode(
        token,
        key=signing_key.key,
        algorithms=IAP_ALLOWED_ALGORITHMS,
        audience=audience_arg,
        issuer=IAP_ISSUER,
        leeway=IAP_CLOCK_SKEW_LEEWAY_SECONDS,
        options=decode_options,
    )
    return dict(claims)


def verify_iap_jwt_assertion(
    token: str,
    *,
    expected_audience: str | None = None,
    verifier: Callable[..., dict[str, Any]] | None = None,
    jwks_provider: Callable[..., dict[str, Any]] | None = None,
) -> VerifiedPrincipal:
    """Cryptographically verify Google Cloud IAP `x-goog-iap-jwt-assertion` JWT."""
    cleaned = (token or "").strip()
    if not cleaned:
        raise HTTPException(
            status_code=401,
            detail="Missing x-goog-iap-jwt-assertion header.",
        )

    audience = resolve_expected_iap_audience(expected_audience)

    try:
        if verifier is not None:
            claims = verifier(cleaned, audience=audience)
        else:
            claims = _decode_iap_jwt_with_pyjwt(
                cleaned,
                audience=audience,
                jwks_provider=jwks_provider,
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
