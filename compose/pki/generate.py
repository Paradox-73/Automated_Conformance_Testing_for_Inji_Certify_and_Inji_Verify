#!/usr/bin/env python3
"""Create the harness test PKI: a test CA, TLS server certificates, the suite's mTLS client certificate and the
suite's credential signing key as a JWK with x5c.

Runs as the one-shot compose service ``pki-init`` (image python:3.12-slim, which ships the openssl command) and
writes into ``--out`` (``/pki`` in the container, ``$HARNESS_RUN_DIR/pki`` on the host). Uses only the Python
standard library and the ``openssl`` command (OpenSSL 3.0 or newer), so it also runs on a developer machine.

Everything here is test material for a local, throwaway environment. Nothing it writes may be committed.

Output layout (paths relative to ``--out``)::

    ca.crt, ca.key                        test CA (EC P-256), trust anchor for every certificate below
    tls/<host>.crt, tls/<host>.key        TLS server certificate (leaf then CA) and key for each --tls-host
    suite-mtls-client.crt, .key           client certificate for the suite's mTLS client authentication variants
    suite-signing.crt, .key               the suite's credential signing key and its certificate, issued by the CA
    suite-signing.jwk.json                that key as a private JWK (ES256) with x5c, for credential.signing_jwk
    verify-request-signing.p12            Inji Verify's request object signing key (Ed25519) with a certificate the
                                          CA issued for $PKI_VERIFY_HOST (leaf only), as PKCS#12 protected by $VERIFY_KEYSTORE_PASSWORD
    manifest.json                         written last: settings, fingerprints and creation time

A run reuses the existing files when manifest.json matches the requested settings, every file is present and the
CA stays valid for at least --min-valid-days more days. Otherwise (or with --force) it creates a new set, so keys
stay stable between runs and test results stay comparable.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Bump when the layout or the content of the generated files changes, so older sets are regenerated.
LAYOUT_VERSION = 2

DEFAULT_TLS_HOSTS = ("verify.inji.test", "certify.inji.test")
CA_SUBJECT = "/O=inji-conformance-harness/CN=inji-conformance-harness test CA"
MTLS_SUBJECT = "/O=inji-conformance-harness/CN=conformance suite test client"
SIGNING_SUBJECT = "/O=inji-conformance-harness/CN=conformance suite test credential issuer"
DEFAULT_VERIFY_HOST = "verify.inji.test"
# Inji Verify signs request objects with the first EdDSA key of its PKCS#12 file (P12KeyExtractor in verify-core) and
# sends that entry's chain as x5c. Its bundled sample keystore holds a self-signed certificate, which the suite
# rejects (ValidateRequestObjectSignatureAgainstX5cHeader: "Leaf certificate in x5c chain must not be self-signed").
VERIFY_KEYSTORE = "verify-request-signing.p12"
VERIFY_KEY_ALIAS = "verify-request-signing"

# Validity in days. Leaf certificates stay under 398 days, the limit browsers and most TLS clients enforce.
CA_DAYS = 825
LEAF_DAYS = 397

# P-256 coordinates and private scalar are 32 bytes each (RFC 7518 section 6.2.1.2 requires the full length).
P256_BYTES = 32

HOST_PATTERN = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")


class PkiError(Exception):
    """A generation step failed; the message says which one."""


def openssl(*args: str, cwd: Path) -> str:
    """Run the openssl command and return its standard output. Raises PkiError with openssl's message on failure."""
    try:
        done = subprocess.run(
            ["openssl", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise PkiError("the openssl command is not installed") from exc
    if done.returncode != 0:
        raise PkiError(f"openssl {args[0]} failed: {done.stderr.strip()}")
    return done.stdout


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def new_ec_key(path: Path, workdir: Path) -> None:
    openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", str(path), cwd=workdir)


def issue(
    workdir: Path,
    key: Path,
    cert: Path,
    subject: str,
    extensions: list[str],
    ca: tuple[Path, Path] | None,
    days: int,
) -> None:
    """Create a certificate for ``key``. With ``ca`` = (ca.crt, ca.key) the CA signs it, otherwise it is self-signed.

    ``openssl req -x509 -CA`` (OpenSSL 3.0+) signs in one step and adds the subject and authority key identifiers.
    """
    args = ["req", "-x509", "-new", "-key", str(key), "-out", str(cert), "-subj", subject, "-days", str(days),
            "-sha256", "-set_serial", "0x" + os.urandom(16).hex()]
    if ca is not None:
        args += ["-CA", str(ca[0]), "-CAkey", str(ca[1])]
    for extension in extensions:
        args += ["-addext", extension]
    openssl(*args, cwd=workdir)


def ec_private_jwk(key: Path, workdir: Path) -> dict[str, str]:
    """Read an EC P-256 private key with openssl and return it as a JWK (kty, crv, x, y, d)."""
    text = openssl("pkey", "-in", str(key), "-noout", "-text", cwd=workdir)
    if "P-256" not in text and "prime256v1" not in text:
        raise PkiError(f"{key.name} is not a P-256 key")

    def hex_block(label: str) -> bytes:
        # openssl prints "priv:" and "pub:" followed by indented lines of colon-separated hex bytes.
        match = re.search(rf"^{label}:\s*\n((?:\s+[0-9a-f:]+\n)+)", text, re.MULTILINE)
        if match is None:
            raise PkiError(f"cannot read the {label} value of {key.name} from openssl output")
        return bytes.fromhex(re.sub(r"[^0-9a-f]", "", match.group(1)))

    # The private scalar is printed as an integer: it can carry a leading zero byte or be shorter than 32 bytes.
    private = hex_block("priv").lstrip(b"\x00").rjust(P256_BYTES, b"\x00")
    public = hex_block("pub")
    if len(public) != 1 + 2 * P256_BYTES or public[0] != 0x04:
        raise PkiError(f"{key.name}: expected an uncompressed P-256 public point")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url(public[1 : 1 + P256_BYTES]),
        "y": b64url(public[1 + P256_BYTES :]),
        "d": b64url(private),
    }


def jwk_thumbprint(jwk: dict[str, str]) -> str:
    """RFC 7638 thumbprint (SHA-256) of an EC JWK: the required members in lexicographic order, no whitespace."""
    canonical = json.dumps({k: jwk[k] for k in ("crv", "kty", "x", "y")}, separators=(",", ":"), sort_keys=True)
    return b64url(hashlib.sha256(canonical.encode("ascii")).digest())


def cert_der(cert: Path, workdir: Path) -> bytes:
    pem = openssl("x509", "-in", str(cert), "-outform", "PEM", cwd=workdir)
    body = "".join(line for line in pem.splitlines() if line and not line.startswith("-----"))
    return base64.b64decode(body)


def sha256_fingerprint(cert: Path, workdir: Path) -> str:
    return hashlib.sha256(cert_der(cert, workdir)).hexdigest()


def cert_not_after(cert: Path, workdir: Path) -> dt.datetime:
    # -dateopt iso_8601 prints "notAfter=2028-01-07 10:00:00Z".
    out = openssl("x509", "-in", str(cert), "-noout", "-enddate", "-dateopt", "iso_8601", cwd=workdir).strip()
    value = out.split("=", 1)[1].strip().rstrip("Z")
    return dt.datetime.fromisoformat(value).replace(tzinfo=dt.UTC)


def expected_files(hosts: list[str]) -> list[str]:
    files = ["ca.crt", "ca.key", "suite-mtls-client.crt", "suite-mtls-client.key", "suite-signing.crt",
             "suite-signing.key", "suite-signing.jwk.json", VERIFY_KEYSTORE]
    for host in hosts:
        files += [f"tls/{host}.crt", f"tls/{host}.key"]
    return files


def settings_for(hosts: list[str], verify_host: str = DEFAULT_VERIFY_HOST) -> dict[str, object]:
    return {"layout_version": LAYOUT_VERSION, "tls_hosts": hosts, "verify_host": verify_host}


def reusable(out: Path, hosts: list[str], min_valid_days: int, verify_host: str = DEFAULT_VERIFY_HOST) -> str | None:
    """Return why the existing set cannot be reused, or None when it can."""
    manifest_path = out / "manifest.json"
    if not manifest_path.is_file():
        return "no manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"unreadable manifest.json ({exc})"
    if manifest.get("settings") != settings_for(hosts, verify_host):
        return "settings changed"
    missing = [name for name in expected_files(hosts) if not (out / name).is_file()]
    if missing:
        return "missing " + ", ".join(missing)
    try:
        not_after = cert_not_after(out / "ca.crt", out)
    except PkiError as exc:
        return str(exc)
    if not_after - dt.datetime.now(dt.UTC) < dt.timedelta(days=min_valid_days):
        return f"CA expires {not_after:%Y-%m-%d}"
    return None


def verify_keystore_password() -> str:
    password = os.environ.get("VERIFY_KEYSTORE_PASSWORD", "")
    if not password:
        raise PkiError("VERIFY_KEYSTORE_PASSWORD is not set (scripts/dc.sh generates it into env.local)")
    return password


def generate(out: Path, hosts: list[str], verify_host: str = DEFAULT_VERIFY_HOST) -> dict[str, object]:
    """Create a complete set in a temporary folder next to ``out``, then move it into place. Returns the manifest."""
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".pki-", dir=out))
    try:
        (work / "tls").mkdir()
        ca = (work / "ca.crt", work / "ca.key")
        new_ec_key(ca[1], work)
        issue(work, ca[1], ca[0], CA_SUBJECT,
              ["basicConstraints=critical,CA:TRUE,pathlen:0", "keyUsage=critical,keyCertSign,cRLSign"],
              None, CA_DAYS)

        leaf_constraints = "basicConstraints=critical,CA:FALSE"
        fingerprints: dict[str, str] = {"ca.crt": sha256_fingerprint(ca[0], work)}
        for host in hosts:
            key, cert = work / "tls" / f"{host}.key", work / "tls" / f"{host}.crt"
            new_ec_key(key, work)
            issue(work, key, cert, f"/CN={host}",
                  [leaf_constraints, "keyUsage=critical,digitalSignature", "extendedKeyUsage=serverAuth",
                   f"subjectAltName=DNS:{host}"], ca, LEAF_DAYS)
            fingerprints[f"tls/{host}.crt"] = sha256_fingerprint(cert, work)
            # nginx sends the whole file, so clients that only trust the CA can build the chain.
            cert.write_text(cert.read_text(encoding="ascii") + ca[0].read_text(encoding="ascii"), encoding="ascii")

        key, cert = work / "suite-mtls-client.key", work / "suite-mtls-client.crt"
        new_ec_key(key, work)
        issue(work, key, cert, MTLS_SUBJECT,
              [leaf_constraints, "keyUsage=critical,digitalSignature", "extendedKeyUsage=clientAuth"], ca, LEAF_DAYS)
        fingerprints["suite-mtls-client.crt"] = sha256_fingerprint(cert, work)

        key, cert = work / "suite-signing.key", work / "suite-signing.crt"
        new_ec_key(key, work)
        issue(work, key, cert, SIGNING_SUBJECT, [leaf_constraints, "keyUsage=critical,digitalSignature"], ca,
              LEAF_DAYS)
        fingerprints["suite-signing.crt"] = sha256_fingerprint(cert, work)
        jwk = ec_private_jwk(key, work)
        # x5c holds the signing certificate only (RFC 7515 section 4.1.6: the first entry holds the key). Inji
        # Verify reads the issuer key from the first x5c entry, and the suite copies x5c into the SD-JWT header.
        jwk.update({"use": "sig", "alg": "ES256", "kid": jwk_thumbprint(jwk),
                    "x5c": [base64.b64encode(cert_der(cert, work)).decode("ascii")]})
        (work / "suite-signing.jwk.json").write_text(json.dumps(jwk, indent=2) + "\n", encoding="ascii")

        key, cert = work / "verify-request-signing.key", work / "verify-request-signing.crt"
        openssl("genpkey", "-algorithm", "ED25519", "-out", str(key), cwd=work)
        issue(work, key, cert, f"/O=inji-conformance-harness/CN={verify_host}",
              [leaf_constraints, "keyUsage=critical,digitalSignature", f"subjectAltName=DNS:{verify_host}"], ca,
              LEAF_DAYS)
        fingerprints["verify-request-signing.crt"] = sha256_fingerprint(cert, work)
        env = {**os.environ, "VERIFY_KEYSTORE_PASSWORD": verify_keystore_password()}
        result = subprocess.run(
            # The leaf only: Inji Verify sends the entry's chain as x5c, and the suite rejects an x5c that includes
            # the trust anchor ("Trust anchor (self-signed root CA) must not be included in x5c chain").
            ["openssl", "pkcs12", "-export", "-inkey", str(key), "-in", str(cert),
             "-name", VERIFY_KEY_ALIAS, "-passout", "env:VERIFY_KEYSTORE_PASSWORD", "-out", str(work / VERIFY_KEYSTORE)],
            cwd=work, env=env, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise PkiError(f"openssl pkcs12 -export failed: {result.stderr.strip()}")

        for name in expected_files(hosts):
            # Private keys are for the harness containers only; certificates are public. The Verify keystore is
            # password protected and must be readable by the Inji Verify container's own user.
            os.chmod(work / name, 0o600 if name.endswith((".key", ".jwk.json")) else 0o644)

        manifest = {
            "created": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "settings": settings_for(hosts, verify_host),
            "ca_not_after": cert_not_after(ca[0], work).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "suite_signing_kid": jwk["kid"],
            "sha256_fingerprints": fingerprints,
            "note": "Test-only keys made at run time by compose/pki/generate.py. Never commit them.",
        }

        # Remove the manifest first: a set without a manifest is never reused, so an interrupted move is detected.
        (out / "manifest.json").unlink(missing_ok=True)
        (out / "tls").mkdir(exist_ok=True)
        for name in expected_files(hosts):
            os.replace(work / name, out / name)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path(os.environ.get("PKI_DIR", "/pki")),
                        help="output folder (default: $PKI_DIR or /pki)")
    parser.add_argument("--tls-host", action="append", dest="tls_hosts", metavar="HOST",
                        help="DNS name that gets a TLS server certificate; repeatable "
                             f"(default: $PKI_TLS_HOSTS or {' '.join(DEFAULT_TLS_HOSTS)})")
    parser.add_argument("--min-valid-days", type=int, default=30,
                        help="regenerate when the CA expires sooner than this (default: 30)")
    parser.add_argument("--force", action="store_true", default=os.environ.get("PKI_FORCE") == "1",
                        help="always create a new set (also PKI_FORCE=1)")
    args = parser.parse_args(argv)
    hosts = args.tls_hosts or os.environ.get("PKI_TLS_HOSTS", " ".join(DEFAULT_TLS_HOSTS)).split()
    for host in hosts:
        if not HOST_PATTERN.match(host):
            parser.error(f"not a lower-case DNS name: {host!r}")
    args.tls_hosts = sorted(set(hosts))
    args.verify_host = os.environ.get("PKI_VERIFY_HOST", DEFAULT_VERIFY_HOST)
    if not HOST_PATTERN.match(args.verify_host):
        parser.error(f"PKI_VERIFY_HOST is not a lower-case DNS name: {args.verify_host!r}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        reason = (
            "--force" if args.force else reusable(args.out, args.tls_hosts, args.min_valid_days, args.verify_host)
        )
        if reason is None:
            manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
            print(f"pki: reusing the set created {manifest['created']} in {args.out}")
            return 0
        manifest = generate(args.out, args.tls_hosts, args.verify_host)
    except PkiError as exc:
        print(f"pki: error: {exc}", file=sys.stderr)
        return 1
    print(f"pki: created a new set in {args.out} ({reason}); TLS hosts: {', '.join(args.tls_hosts)}; "
          f"signing kid {manifest['suite_signing_kid']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
