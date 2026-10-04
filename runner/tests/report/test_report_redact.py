"""Removing key material from free text. Key-shaped test strings are assembled at run time, so this file itself
holds nothing the repository's secrets check would flag."""

from __future__ import annotations

from markupsafe import Markup

from inji_conformance.report.redact import REDACTED, redact, redact_value

BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
END = "-----END " + "PRIVATE KEY-----"
BODY = "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg" * 2
D_VALUE = "q1w2e3r4t5y6u7i8o9p0a1s2d3f4g5h6"


def test_pem_private_key_is_removed():
    text = f"config was {BEGIN}\n{BODY}\n{END} end"
    out = redact(text)
    assert BODY not in out and "BEGIN" not in out.replace(REDACTED, "")
    assert out.startswith("config was ") and out.endswith(" end")


def test_pem_private_key_without_end_line():
    assert BODY not in redact(f"{BEGIN}\n{BODY}")


def test_ec_and_rsa_labels():
    for label in ("EC PRIVATE KEY", "RSA PRIVATE KEY", "ENCRYPTED PRIVATE KEY"):
        text = f"-----BEGIN {label}-----\n{BODY}\n-----END {label}-----"
        assert BODY not in redact(text)


def test_private_jwk_members_are_removed_and_public_ones_kept():
    jwk = '{"kty":"EC","crv":"P-256","x":"' + D_VALUE + '","d":"' + D_VALUE[::-1] + '"}'
    out = redact(jwk)
    assert D_VALUE[::-1] not in out
    assert f'"x":"{D_VALUE}"' in out and f'"d":"{REDACTED}"' in out


def test_jwk_quoted_inside_a_json_string():
    escaped = '{\\"kty\\":\\"RSA\\",\\"p\\":\\"' + D_VALUE + '\\"}'
    assert D_VALUE not in redact(escaped)


def test_form_secrets_are_removed():
    out = redact("POST /token client_id=abc&client" + "_secret=s3cr3tv4lue&grant_type=x")
    assert "s3cr3tv4lue" not in out and "client_id=abc" in out and "grant_type=x" in out


def test_ordinary_text_is_unchanged():
    text = "POST to request_uri returned HTTP 405; d is short"
    assert redact(text) == text
    assert redact("") == ""


def test_redact_value_leaves_markup_and_non_strings_alone():
    markup = Markup("<b>" + BEGIN + "</b>")
    assert redact_value(markup) is markup
    assert redact_value(42) == 42
    assert BODY not in redact_value(f"{BEGIN}\n{BODY}\n{END}")
