"""Removing key material from text before it reaches a report page.

The report never reads the rendered suite configuration, which holds the private keys of the test clients. Free
text in a results file (suite log messages, handoff details, notes) comes from the suite and from Inji, though, and
a failing condition can quote a request or a key. Every string the HTML templates print passes through
:func:`redact`, so such a quote shows as ``[redacted]`` instead of the secret.

What is removed:

- PEM private keys (``-----BEGIN ... PRIVATE KEY-----`` to the matching END line, or to the end of the text when
  the END line is missing);
- private members of a JSON Web Key (``d``, ``p``, ``q``, ``dp``, ``dq``, ``qi``, and ``k`` of a symmetric key) when
  quoted with a value of 16 or more base64url characters;
- the values of ``client_secret``, ``password``, ``access_token`` and ``refresh_token`` in query strings and form
  bodies.

Public keys, certificates and signed credentials are left alone: they are not secret, and the diagnosis of a failing
signature check often needs them.
"""

from __future__ import annotations

import re

from markupsafe import Markup

REDACTED = "[redacted]"

_PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|\Z)",
    re.DOTALL,
)
# Escaped quotes (\") appear when a JWK is quoted inside a JSON string, as in a suite log message.
_JWK_PRIVATE_MEMBER = re.compile(r'(\\?"(?:d|p|q|dp|dq|qi|k)\\?"\s*:\s*\\?")[A-Za-z0-9_-]{16,}(\\?")')
_FORM_SECRET = re.compile(r"(?i)\b(client_secret|password|access_token|refresh_token)=[^&\s\"'<>]+")


def redact(text: str) -> str:
    """``text`` with private keys and credential values replaced by ``[redacted]``."""
    if not text:
        return text
    text = _PEM_PRIVATE_KEY.sub(f"-----{REDACTED} PRIVATE KEY-----", text)
    text = _JWK_PRIVATE_MEMBER.sub(rf"\g<1>{REDACTED}\g<2>", text)
    return _FORM_SECRET.sub(rf"\g<1>={REDACTED}", text)


def redact_value(value: object) -> object:
    """:func:`redact` for plain strings; other values unchanged. Used as the template engine's output hook.

    ``Markup`` (markup the templates built themselves, such as a macro's output) is left alone: every value inside it
    already passed this hook when the macro printed it, and a regular-expression substitution would turn it back
    into a plain string that the engine then escapes a second time.
    """
    if isinstance(value, Markup) or not isinstance(value, str):
        return value
    return redact(value)
