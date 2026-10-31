import os
import tempfile
import unittest
from pathlib import Path

from bridge_security import (
    decode_pairing_code,
    encode_nonce,
    load_or_create_pairing_code,
    make_client_proof,
    make_server_proof,
    verify_client_proof,
)


class PairingProtocolTests(unittest.TestCase):
    def test_client_and_server_proofs_are_mutual_and_bound_to_nonces(self):
        secret = os.urandom(32)
        server_nonce = os.urandom(32)
        client_nonce = os.urandom(32)
        proof = make_client_proof(secret, server_nonce, client_nonce)
        self.assertTrue(verify_client_proof(secret, server_nonce, client_nonce, proof))
        self.assertFalse(verify_client_proof(os.urandom(32), server_nonce, client_nonce, proof))
        self.assertFalse(verify_client_proof(secret, os.urandom(32), client_nonce, proof))
        self.assertEqual(len(make_server_proof(secret, server_nonce, client_nonce)), 32)

    def test_pairing_code_is_256_bit_and_persisted_with_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bridge_pairing_code.txt"
            code = load_or_create_pairing_code(path)
            self.assertEqual(len(decode_pairing_code(code)), 32)
            self.assertEqual(load_or_create_pairing_code(path), code)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_rejects_invalid_pairing_codes(self):
        for code in ("", "abc", "!" * 43, "A" * 1000):
            with self.subTest(code=code), self.assertRaises(ValueError):
                decode_pairing_code(code)


if __name__ == "__main__":
    unittest.main()
