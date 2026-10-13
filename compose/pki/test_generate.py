"""Tests for compose/pki/generate.py. Standard library only; needs the openssl command (OpenSSL 3.0 or newer).

    python -m unittest discover -s compose/pki -p 'test_*.py'

"bash scripts/tests/test-pki.sh" runs this file, and "bash scripts/check.sh shell" runs that script.
"""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import generate


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def run_openssl(*args: str, stdin: bytes | None = None) -> str:
    """Runs openssl; `stdin` goes in through a temporary file (`-in`), because the openssl of Git for Windows
    reads standard input in text mode and corrupts binary input such as a DER certificate."""
    if stdin is None:
        done = subprocess.run(["openssl", *args], capture_output=True, check=True)
        return done.stdout.decode("ascii")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "input"
        path.write_bytes(stdin)
        done = subprocess.run(["openssl", *args, "-in", str(path)], capture_output=True, check=True)
    return done.stdout.decode("ascii")


def public_point_of_cert(der: bytes) -> bytes:
    """Uncompressed EC public point (0x04 || x || y) of a DER certificate, read with openssl."""
    pem = run_openssl("x509", "-inform", "DER", "-noout", "-pubkey", stdin=der)
    text = run_openssl("pkey", "-pubin", "-noout", "-text", stdin=pem.encode("ascii"))
    block = text.split("pub:", 1)[1].split("ASN1 OID", 1)[0]
    return bytes.fromhex("".join(ch for ch in block if ch in "0123456789abcdef"))


class GeneratedSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "pki"
        cls.hosts = ["certify.inji.test", "verify.inji.test"]
        with mock.patch.dict("os.environ", {"VERIFY_KEYSTORE_PASSWORD": "test-only-password"}):
            cls.manifest = generate.generate(cls.out, cls.hosts)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_verify_keystore_holds_an_ed25519_key_with_a_ca_issued_chain(self) -> None:
        keystore = ["pkcs12", "-in", str(self.out / generate.VERIFY_KEYSTORE), "-passin", "pass:test-only-password"]
        certs = run_openssl(*keystore, "-nokeys")
        self.assertEqual(1, certs.count("BEGIN CERTIFICATE"),
                         "the leaf only: the suite rejects an x5c that includes the trust anchor")
        leaf = run_openssl("x509", "-noout", "-subject", "-issuer", "-ext", "subjectAltName", stdin=certs.encode("ascii"))
        self.assertIn("DNS:verify.inji.test", leaf)
        self.assertIn("inji-conformance-harness test CA", leaf.split("issuer=", 1)[1])
        # openssl pkey skips the bag attribute lines in front of the key.
        key = run_openssl("pkey", "-noout", "-text", stdin=run_openssl(*keystore, "-nocerts", "-nodes").encode("ascii"))
        self.assertIn("ED25519", key)

    def test_missing_keystore_password_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict("os.environ", {"VERIFY_KEYSTORE_PASSWORD": ""}):
            with self.assertRaisesRegex(generate.PkiError, "VERIFY_KEYSTORE_PASSWORD"):
                generate.generate(Path(folder) / "pki", self.hosts)

    def test_every_file_is_written_and_no_temporary_folder_is_left(self) -> None:
        for name in generate.expected_files(self.hosts):
            self.assertTrue((self.out / name).is_file(), name)
        self.assertEqual([], [p.name for p in self.out.iterdir() if p.name.startswith(".pki-")])
        self.assertTrue((self.out / "manifest.json").is_file())

    def test_certificates_chain_to_the_test_ca(self) -> None:
        certs = [f"tls/{h}.crt" for h in self.hosts] + ["suite-mtls-client.crt", "suite-signing.crt"]
        output = run_openssl("verify", "-CAfile", str(self.out / "ca.crt"), *(str(self.out / c) for c in certs))
        self.assertEqual(len(certs), output.count(": OK"), output)

    def test_tls_certificate_names_the_host_and_is_for_servers(self) -> None:
        text = run_openssl("x509", "-in", str(self.out / "tls/verify.inji.test.crt"), "-noout", "-text")
        self.assertIn("DNS:verify.inji.test", text)
        self.assertIn("TLS Web Server Authentication", text)
        self.assertIn("CA:FALSE", text)

    def test_tls_certificate_file_carries_the_chain(self) -> None:
        pem = (self.out / "tls/certify.inji.test.crt").read_text(encoding="ascii")
        self.assertEqual(2, pem.count("BEGIN CERTIFICATE"))
        self.assertTrue(pem.endswith((self.out / "ca.crt").read_text(encoding="ascii")))

    def test_mtls_client_certificate_is_for_clients(self) -> None:
        text = run_openssl("x509", "-in", str(self.out / "suite-mtls-client.crt"), "-noout", "-text")
        self.assertIn("TLS Web Client Authentication", text)

    def test_signing_jwk_is_a_complete_es256_key_with_x5c(self) -> None:
        jwk = json.loads((self.out / "suite-signing.jwk.json").read_text(encoding="ascii"))
        self.assertEqual(("EC", "P-256", "ES256", "sig"), (jwk["kty"], jwk["crv"], jwk["alg"], jwk["use"]))
        for member in ("x", "y", "d"):
            self.assertEqual(32, len(b64url_decode(jwk[member])), member)
        self.assertEqual(generate.jwk_thumbprint(jwk), jwk["kid"])
        self.assertEqual(self.manifest["suite_signing_kid"], jwk["kid"])
        self.assertEqual(1, len(jwk["x5c"]))

    def test_x5c_certificate_holds_the_jwk_public_key(self) -> None:
        jwk = json.loads((self.out / "suite-signing.jwk.json").read_text(encoding="ascii"))
        point = public_point_of_cert(base64.b64decode(jwk["x5c"][0]))
        self.assertEqual(b"\x04" + b64url_decode(jwk["x"]) + b64url_decode(jwk["y"]), point)

    def test_manifest_records_settings_and_fingerprints(self) -> None:
        manifest = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(generate.settings_for(self.hosts), manifest["settings"])
        self.assertEqual(
            generate.sha256_fingerprint(self.out / "ca.crt", self.out), manifest["sha256_fingerprints"]["ca.crt"]
        )
        self.assertNotIn("BEGIN", json.dumps(manifest))


class ReuseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "pki"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_main(self, *args: str) -> str:
        with mock.patch("sys.stdout") as stdout, mock.patch.dict("os.environ", {"VERIFY_KEYSTORE_PASSWORD": "pw"}):
            self.assertEqual(0, generate.main(["--out", str(self.out), *args]))
        return "".join(call.args[0] for call in stdout.write.call_args_list)

    def ca_fingerprint(self) -> str:
        return generate.sha256_fingerprint(self.out / "ca.crt", self.out)

    def test_second_run_reuses_the_set(self) -> None:
        self.assertIn("created a new set", self.run_main())
        first = self.ca_fingerprint()
        self.assertIn("reusing", self.run_main())
        self.assertEqual(first, self.ca_fingerprint())

    def test_force_creates_a_new_set(self) -> None:
        self.run_main()
        first = self.ca_fingerprint()
        self.assertIn("--force", self.run_main("--force"))
        self.assertNotEqual(first, self.ca_fingerprint())

    def test_changed_hosts_or_missing_file_create_a_new_set(self) -> None:
        self.run_main("--tls-host", "verify.inji.test")
        self.assertIn("settings changed", self.run_main("--tls-host", "verify.inji.test", "--tls-host", "x.test"))
        (self.out / "suite-signing.jwk.json").unlink()
        self.assertIn("missing suite-signing.jwk.json",
                      self.run_main("--tls-host", "verify.inji.test", "--tls-host", "x.test"))

    def test_ca_close_to_expiry_creates_a_new_set(self) -> None:
        self.run_main()
        self.assertIn("CA expires", self.run_main("--min-valid-days", "5000"))

    def test_rejects_a_host_that_is_not_a_dns_name(self) -> None:
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            generate.parse_args(["--out", str(self.out), "--tls-host", "Bad_Host"])


class PrivateJwkParsingTest(unittest.TestCase):
    """openssl prints the private scalar as an integer, so its byte length varies; the JWK needs exactly 32 bytes."""

    PUB = "04:" + ":".join(["11"] * 32) + ":" + ":".join(["22"] * 32)

    def jwk_from_priv(self, priv_bytes: list[str]) -> dict[str, str]:
        text = (f"Private-Key: (256 bit)\npriv:\n    {':'.join(priv_bytes)}\npub:\n    {self.PUB}\n"
                "ASN1 OID: prime256v1\nNIST CURVE: P-256\n")
        with mock.patch.object(generate, "openssl", return_value=text):
            return generate.ec_private_jwk(Path("k.key"), Path("."))

    def test_leading_zero_byte_is_dropped(self) -> None:
        jwk = self.jwk_from_priv(["00"] + ["ab"] * 32)
        self.assertEqual(b"\xab" * 32, b64url_decode(jwk["d"]))

    def test_short_scalar_is_left_padded(self) -> None:
        jwk = self.jwk_from_priv(["ab"] * 31)
        self.assertEqual(b"\x00" + b"\xab" * 31, b64url_decode(jwk["d"]))

    def test_coordinates_are_split_from_the_public_point(self) -> None:
        jwk = self.jwk_from_priv(["ab"] * 32)
        self.assertEqual((b"\x11" * 32, b"\x22" * 32), (b64url_decode(jwk["x"]), b64url_decode(jwk["y"])))

    def test_thumbprint_ignores_private_and_optional_members(self) -> None:
        jwk = self.jwk_from_priv(["ab"] * 32)
        public = {k: jwk[k] for k in ("kty", "crv", "x", "y")}
        self.assertEqual(generate.jwk_thumbprint(public), generate.jwk_thumbprint({**jwk, "alg": "ES256"}))


if __name__ == "__main__":
    unittest.main()
