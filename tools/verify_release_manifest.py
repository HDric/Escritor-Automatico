#!/usr/bin/env python3
"""Verifica firma Ed25519 y SHA-256 de una lista de artefactos de Release."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from update_security import verify_release_manifest  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("Uso: python tools/verify_release_manifest.py SHA256SUMS.txt SHA256SUMS.txt.sig [archivo ...]")
        return 2
    manifest_path, signature_path = map(Path, sys.argv[1:3])
    manifest = manifest_path.read_bytes()
    signature = signature_path.read_bytes()
    if not verify_release_manifest(manifest, signature):
        print("ERROR: firma Ed25519 inválida.", file=sys.stderr)
        return 1
    expected = {}
    for line in manifest.decode("utf-8").splitlines():
        match = re.fullmatch(r"([A-Fa-f0-9]{64})  ([A-Za-z0-9._-]+)", line.strip())
        if not match:
            print("ERROR: formato de SHA256SUMS.txt no válido.", file=sys.stderr)
            return 1
        expected[match.group(2)] = match.group(1).lower()
    for name in sys.argv[3:]:
        path = Path(name)
        if path.name not in expected:
            print(f"ERROR: {path.name} no aparece en el manifiesto firmado.", file=sys.stderr)
            return 1
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected[path.name]:
            print(f"ERROR: SHA-256 incorrecto para {path.name}.", file=sys.stderr)
            return 1
        print(f"OK: {path.name}")
    print("Firma Ed25519 válida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
