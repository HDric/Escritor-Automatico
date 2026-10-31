"""Claves públicas y verificación de las firmas de actualizaciones.

La clave privada de firma solo debe existir como secreto de GitHub Actions y nunca
formar parte del repositorio, del instalador ni de una Release.
"""
from __future__ import annotations

import base64
import binascii

# Clave pública Ed25519 (32 bytes). Es pública por diseño y queda integrada en la app.
PUBLIC_KEY_RAW_B64 = "+rA7YINV/SMxBXB/ze/+4UyOo7SfLG46SZRKA0926W4="


def public_key_raw() -> bytes:
    try:
        raw = base64.b64decode(PUBLIC_KEY_RAW_B64, validate=True)
    except (ValueError, binascii.Error) as exc:  # pragma: no cover - constante interna
        raise RuntimeError("La clave pública integrada no es válida.") from exc
    if len(raw) != 32:  # pragma: no cover - constante interna
        raise RuntimeError("La clave pública Ed25519 debe tener 32 bytes.")
    return raw


def verify_release_manifest(manifest: bytes, signature: bytes) -> bool:
    """Verifica una firma Ed25519 independiente del archivo de sumas descargado."""
    if not isinstance(manifest, bytes) or not isinstance(signature, bytes) or len(signature) != 64:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(public_key_raw()).verify(signature, manifest)
        return True
    except Exception:
        return False
