#!/usr/bin/env python3
"""Firma SHA256SUMS.txt con la clave Ed25519 guardada como secreto en GitHub Actions."""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from update_security import public_key_raw  # noqa: E402


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Uso: python tools/sign_release_manifest.py SHA256SUMS.txt [SHA256SUMS.txt.sig]", file=sys.stderr)
        return 2
    secret = os.environ.get("UPDATE_SIGNING_PRIVATE_KEY_B64", "").strip()
    if not secret:
        print("Falta el secreto UPDATE_SIGNING_PRIVATE_KEY_B64.", file=sys.stderr)
        return 2
    try:
        from cryptography.hazmat.primitives import serialization
        private_bytes = base64.b64decode(secret, validate=True)
        private_key = serialization.load_pem_private_key(private_bytes, password=None)
        derived = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        if derived != public_key_raw():
            raise ValueError("La clave privada no corresponde a la clave pública de esta versión.")
        manifest = Path(sys.argv[1]).read_bytes()
        signature = private_key.sign(manifest)
        output = Path(sys.argv[2]) if len(sys.argv) == 3 else Path(str(sys.argv[1]) + ".sig")
        output.write_bytes(signature)
        print(f"Firma Ed25519 creada: {output}")
        return 0
    except Exception as exc:
        print(f"No se pudo firmar el manifiesto: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
