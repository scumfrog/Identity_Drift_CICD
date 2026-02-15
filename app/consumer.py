from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import FastAPI, Header, HTTPException
from jose import jwt

from policies import EXPECTED, evaluate_policies

app = FastAPI(title="CI OIDC Consumer Lab")

_JWKS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_DISCOVERY_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}

DEFAULT_ISSUER = "https://token.actions.githubusercontent.com"
CACHE_TTL_SECONDS = 3600
ALLOWED_JWT_ALGS = ["RS256"]


async def fetch_json(url: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def get_discovery(issuer: str) -> Dict[str, Any]:
    now = time.time()
    if issuer in _DISCOVERY_CACHE and now - _DISCOVERY_CACHE[issuer][0] < CACHE_TTL_SECONDS:
        return _DISCOVERY_CACHE[issuer][1]
    doc = await fetch_json(f"{issuer}/.well-known/openid-configuration")
    _DISCOVERY_CACHE[issuer] = (now, doc)
    return doc


async def get_jwks(issuer: str) -> Dict[str, Any]:
    now = time.time()
    if issuer in _JWKS_CACHE and now - _JWKS_CACHE[issuer][0] < CACHE_TTL_SECONDS:
        return _JWKS_CACHE[issuer][1]
    discovery = await get_discovery(issuer)
    jwks_uri = discovery.get("jwks_uri")
    if not jwks_uri:
        raise RuntimeError("No jwks_uri in discovery document")
    jwks = await fetch_json(jwks_uri)
    _JWKS_CACHE[issuer] = (now, jwks)
    return jwks


def _get_unverified_claims(token: str) -> Dict[str, Any]:
    return jwt.get_unverified_claims(token)


def _select_jwk(jwks: Dict[str, Any], token: str) -> Dict[str, Any]:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    alg = header.get("alg")
    if alg not in ALLOWED_JWT_ALGS:
        raise ValueError(f"alg_not_allowed: {alg}")
    keys = jwks.get("keys") or []
    for k in keys:
        if not isinstance(k, dict):
            continue
        if kid and k.get("kid") == kid:
            return k
    raise ValueError(f"kid_not_found: {kid}")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/policies")
def policies() -> Dict[str, Any]:
    return {"expected": EXPECTED, "notes": "Ajusta con env vars (EXPECTED_REPOSITORY, ALLOWED_WORKFLOWS, etc.)."}


@app.post("/introspect")
async def introspect(
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty Bearer token")

    # 1) Unverified claims to discover the issuer
    try:
        unverified = _get_unverified_claims(token)
        issuer = unverified.get("iss") or DEFAULT_ISSUER
    except Exception as e:
        # Avoid 500s on garbage tokens: the lab should return stable JSON.
        return {
            "ok": False,
            "error": f"jwt_unverified_claims_failed: {type(e).__name__}: {str(e)}",
        }

    # 2) Verify signature + exp/nbf + issuer. Audience is handled in policies.
    jwks = await get_jwks(issuer)
    try:
        jwk_key = _select_jwk(jwks, token)
        verified_claims = jwt.decode(
            token,
            jwk_key,
            algorithms=ALLOWED_JWT_ALGS,
            options={"verify_aud": False},
            issuer=issuer,
        )
    except Exception as e:
        return {
            "ok": False,
            "error": f"jwt_decode_failed: {type(e).__name__}: {str(e)}",
            "issuer": issuer,
            "unverified": unverified,
        }

    # 3) Evaluate policies (lax vs strict)
    policy_results = evaluate_policies(verified_claims)

    return {
        "ok": True,
        "issuer": issuer,
        "claims": verified_claims,
        "policy_results": policy_results,
    }
