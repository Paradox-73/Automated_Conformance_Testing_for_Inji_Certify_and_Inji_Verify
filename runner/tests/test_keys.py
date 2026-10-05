"""Run-time P-256 keys for the suite's wallet clients: curve arithmetic against known points, JWK members."""

from __future__ import annotations

import base64
import hashlib

import pytest

from inji_conformance import keys

# 2G on P-256, from the NIST point-multiplication test vectors for the curve.
TWO_G = (
    0x7CF27B188D034F7E8A52380304B51AC3C08969E277F21B35A60B48FC47669978,
    0x07775510DB8ED040293D9AC69F7430DBBA7DADE63CE982299E04B79D227873D1,
)


def unb64url(text: str) -> int:
    return int.from_bytes(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)), "big")


def test_base_point_and_its_multiples_are_on_the_curve():
    assert keys.on_curve(keys.G)
    assert keys.scalar_mult(1) == keys.G
    assert keys.scalar_mult(2) == TWO_G
    assert keys.on_curve(keys.scalar_mult(0xC0FFEE))
    assert not keys.on_curve((keys.G[0], keys.G[1] + 1))


def test_group_order_gives_the_point_at_infinity():
    x, y = keys.G
    assert keys.scalar_mult(keys.N - 1) == (x, keys.P - y)  # -G
    assert keys.scalar_mult(keys.N) is None
    assert keys.on_curve(None)


def test_scalar_multiplication_is_additive():
    # (a + b)G = aG + bG, checked through 5G = 2G + 3G and 5G = 4G + G.
    five = keys.scalar_mult(5)
    assert keys._add(keys.scalar_mult(2), keys.scalar_mult(3)) == five
    assert keys._add(keys.scalar_mult(4), keys.G) == five


def test_private_jwk_has_the_members_the_suite_reads():
    jwk = keys.p256_private_jwk(2)
    assert set(jwk) == {"kty", "crv", "x", "y", "kid", "use", "alg", "d"}
    assert (jwk["kty"], jwk["crv"], jwk["use"], jwk["alg"]) == ("EC", "P-256", "sig", "ES256")
    assert (unb64url(jwk["x"]), unb64url(jwk["y"]), unb64url(jwk["d"])) == (*TWO_G, 2)
    # Coordinates and the private scalar are always 32 bytes: 43 base64url characters, no padding.
    assert {len(jwk[name]) for name in ("x", "y", "d")} == {43}
    assert "=" not in jwk["x"] + jwk["y"] + jwk["d"]


def test_kid_defaults_to_the_rfc7638_thumbprint():
    jwk = keys.p256_private_jwk(2)
    canonical = f'{{"crv":"P-256","kty":"EC","x":"{jwk["x"]}","y":"{jwk["y"]}"}}'
    expected = base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()
    assert jwk["kid"] == expected == keys.thumbprint(jwk)
    assert keys.p256_private_jwk(2, kid="wallet-1")["kid"] == "wallet-1"


@pytest.mark.parametrize("d", [0, -1, keys.N, keys.N + 5])
def test_private_scalar_outside_the_group_is_rejected(d):
    with pytest.raises(ValueError, match=r"\[1, n-1\]"):
        keys.p256_private_jwk(d)


def test_new_private_jwks_is_one_fresh_signing_key():
    first, second = keys.new_private_jwks("client-jwks"), keys.new_private_jwks("client-jwks")
    assert list(first) == ["keys"] and len(first["keys"]) == 1
    key = first["keys"][0]
    assert key["kid"].startswith("client-jwks-") and len(key["kid"]) == len("client-jwks-") + 16
    point = (unb64url(key["x"]), unb64url(key["y"]))
    assert keys.on_curve(point)
    assert keys.scalar_mult(unb64url(key["d"])) == point  # the public point belongs to the private scalar
    assert key["d"] != second["keys"][0]["d"]
