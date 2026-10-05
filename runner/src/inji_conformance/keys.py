"""Run-time key material the suite configuration needs and ``pki-init`` does not provide.

The issuer plan plays a wallet with two OAuth clients (``client`` and ``client2``, the second for the
multiple-clients module); with ``client_auth_type=private_key_jwt`` each needs its own private JWK set. The keys are
made fresh for every run, written only into the staged ``certs-keys/`` folder (deleted when the run ends) and
never into the rendered configuration.

The standard library has no elliptic-curve code and the runner image should not need a native crypto package for
one key pair, so P-256 key generation is written out here (SEC 2 curve parameters, affine double-and-add). It is
not constant-time, which does not matter for throw-away test keys that never leave the run.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any

# SEC 2 v2, section 2.4.2: secp256r1 (NIST P-256), y^2 = x^3 + a*x + b over GF(p), base point G of order n.
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (
    0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
    0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
)

Point = tuple[int, int] | None  # None is the point at infinity


def on_curve(point: Point) -> bool:
    if point is None:
        return True
    x, y = point
    return (y * y - (x * x * x + A * x + B)) % P == 0


def _add(p1: Point, p2: Point) -> Point:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    slope = (
        (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P  # tangent: the point is doubled
        if p1 == p2
        else (y2 - y1) * pow(x2 - x1, -1, P) % P  # chord through two different points
    )
    x3 = (slope * slope - x1 - x2) % P
    return x3, (slope * (x1 - x3) - y1) % P


def scalar_mult(k: int, point: Point = G) -> Point:
    result: Point = None
    addend = point
    while k:
        if k & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        k >>= 1
    return result


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def p256_private_jwk(d: int | None = None, *, kid: str | None = None, alg: str = "ES256") -> dict[str, str]:
    """A P-256 private JWK; ``d`` is the private scalar (random when omitted). ``kid`` defaults to the thumbprint."""
    if d is None:
        d = secrets.randbelow(N - 1) + 1
    if not 0 < d < N:
        raise ValueError("the private scalar must be in [1, n-1]")
    point = scalar_mult(d)
    assert point is not None and on_curve(point)
    x, y = point
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url(x.to_bytes(32, "big")),
        "y": b64url(y.to_bytes(32, "big")),
    }
    jwk["kid"] = kid or thumbprint(jwk)
    jwk.update({"use": "sig", "alg": alg, "d": b64url(d.to_bytes(32, "big"))})
    return jwk


def thumbprint(jwk: dict[str, Any]) -> str:
    """RFC 7638 JWK thumbprint (SHA-256) of an EC key."""
    canonical = json.dumps({k: jwk[k] for k in ("crv", "kty", "x", "y")}, separators=(",", ":"), sort_keys=True)
    return b64url(hashlib.sha256(canonical.encode("ascii")).digest())


def new_private_jwks(kid_prefix: str) -> dict[str, list[dict[str, str]]]:
    """A JWK set with one fresh P-256 signing key, the form the suite expects in ``client.jwks``."""
    key = p256_private_jwk()
    key["kid"] = f"{kid_prefix}-{key['kid'][:16]}"
    return {"keys": [key]}
