"""Primitivas de autenticación HMAC para el puente local Chromium ↔ Escritor Automático."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
from pathlib import Path

PAIRING_DOMAIN_CLIENT = b"EscritorAutomatico-Bridge-Client-v1\x00"
PAIRING_DOMAIN_SERVER = b"EscritorAutomatico-Bridge-Server-v1\x00"


def decode_pairing_code(code: str) -> bytes:
    if not isinstance(code, str) or len(code) > 128:
        raise ValueError("Código de vinculación no válido.")
    normalized = code.strip()
    if not normalized:
        raise ValueError("El código de vinculación está vacío.")
    try:
        raw = base64.b64decode(
            normalized + "=" * (-len(normalized) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error) as exc:
        raise ValueError("El código de vinculación no está codificado correctamente.") from exc
    if len(raw) != 32:
        raise ValueError("El código de vinculación debe contener 256 bits.")
    return raw


def encode_nonce(value: bytes) -> str:
    if not isinstance(value, bytes) or len(value) != 32:
        raise ValueError("El nonce debe contener 32 bytes.")
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_nonce(value: str) -> bytes:
    raw = decode_pairing_code(value)
    return raw


def make_client_proof(secret: bytes, server_nonce: bytes, client_nonce: bytes) -> bytes:
    if len(secret) != 32 or len(server_nonce) != 32 or len(client_nonce) != 32:
        raise ValueError("Datos de autenticación de longitud incorrecta.")
    return hmac.new(secret, PAIRING_DOMAIN_CLIENT + server_nonce + client_nonce, hashlib.sha256).digest()


def make_server_proof(secret: bytes, server_nonce: bytes, client_nonce: bytes) -> bytes:
    if len(secret) != 32 or len(server_nonce) != 32 or len(client_nonce) != 32:
        raise ValueError("Datos de autenticación de longitud incorrecta.")
    return hmac.new(secret, PAIRING_DOMAIN_SERVER + server_nonce + client_nonce, hashlib.sha256).digest()


def verify_client_proof(secret: bytes, server_nonce: bytes, client_nonce: bytes, proof: bytes) -> bool:
    try:
        return hmac.compare_digest(make_client_proof(secret, server_nonce, client_nonce), proof)
    except (TypeError, ValueError):
        return False


def load_or_create_pairing_code(path: Path) -> str:
    """Carga o genera un secreto persistente por usuario con permisos restrictivos."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    if path.is_symlink():
        raise OSError("El archivo de vinculación no puede ser un enlace simbólico.")
    if path.exists():
        if not path.is_file():
            raise OSError("El archivo de vinculación no es un archivo regular.")
        code = path.read_text(encoding="ascii").strip()
        decode_pairing_code(code)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return code
    code = encode_nonce(os.urandom(32))
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink(missing_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii") as stream:
        stream.write(code + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return code
