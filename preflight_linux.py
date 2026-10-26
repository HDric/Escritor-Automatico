#!/usr/bin/env python3
"""Validaciones ligeras antes de construir el paquete Linux de v1.0.0."""
from __future__ import annotations
import base64, hashlib, json, re, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
EXPECTED_EXTENSION_ID = "gokleoeeegcjpahldnbmepeeokjafodl"
REQUIRED = ["escritor_automatico.py", "updater.py", "version.json", "update_config.json", "requirements.txt", "requirements-build.txt", "web_extension/manifest.json",
            "web_extension/service_worker.js", "web_extension/content.js", "web_extension/popup.html", "web_extension/popup.js",
            "LEEME.txt", "LEEME_LINUX.txt", "POST_INSTALACION_LINUX.txt", "instalar_escritor_automatico_linux.sh"]
def fail(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr); raise SystemExit(1)
def main() -> int:
    if sys.platform != "linux": fail("El paquete Linux debe construirse en un runner Linux.")
    for item in REQUIRED:
        if not (ROOT / item).is_file(): fail(f"Falta el archivo requerido: {item}")
    version_data = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    version_value = version_data.get("version")
    if not isinstance(version_value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version_value):
        fail("version.json debe contener una versión X.Y.Z.")
    updater_source = (ROOT / "updater.py").read_text(encoding="utf-8")
    try: compile(updater_source, str(ROOT / "updater.py"), "exec")
    except SyntaxError as exc: fail(f"Sintaxis inválida en updater.py línea {exc.lineno}: {exc.msg}")
    print(f"OK: actualizador opcional y versión {version_value}")
    source_path = ROOT / "escritor_automatico.py"
    source = source_path.read_text(encoding="utf-8")
    try: compile(source, str(source_path), "exec")
    except SyntaxError as exc: fail(f"Error de sintaxis Python en línea {exc.lineno}: {exc.msg}")
    for marker in ('IS_LINUX', 'create_keyboard_backend', 'Sistema detectado automáticamente', 'class LinuxKeyboard'):
        if marker not in source: fail(f"No se encontró la función multiplataforma: {marker}")
    manifest = json.loads((ROOT / "web_extension/manifest.json").read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 3: fail("La extensión no usa Manifest V3.")
    key = manifest.get("key")
    if not isinstance(key, str) or not key: fail("Falta la clave pública fija de la extensión.")
    public_key = base64.b64decode(key, validate=True)
    digest = hashlib.sha256(public_key).hexdigest()[:32]
    extension_id = "".join(chr(ord("a") + int(ch, 16)) for ch in digest)
    if extension_id != EXPECTED_EXTENSION_ID: fail(f"ID de extensión inesperado: {extension_id}")
    if f'WEB_EXTENSION_ID = "{EXPECTED_EXTENSION_ID}"' not in source: fail("ID en Python no coincide con el manifiesto.")
    if "_check_for_updates" not in source or "Comprobar actualizaciones automáticamente al iniciar" not in source:
        fail("No se encontró la interfaz de actualización opcional.")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package, version in {"python-docx":"1.2.0", "lxml":"6.1.3", "typing_extensions":"4.16.0", "websockets":"17.3", "Pillow":"13.0.0", "pynput":"1.8.2"}.items():
        if not re.search(rf"(?im)^\s*{re.escape(package)}=={re.escape(version)}(?:\s*;.*)?\s*$", requirements): fail(f"{package} no está fijado a {version}")
    node = shutil.which("node")
    if node:
        for js_file in sorted((ROOT / "web_extension").glob("*.js")):
            result = subprocess.run([node, "--check", str(js_file)], capture_output=True, text=True)
            if result.returncode: fail(f"Sintaxis JavaScript inválida en {js_file.name}: {result.stderr or result.stdout}")
        print("OK: sintaxis JavaScript de la extensión")
    else: print("AVISO: Node.js no está disponible; no se comprobó la sintaxis JS en este runner.")
    print(f"OK: sintaxis Python, detección Linux y manifiesto; ID {extension_id}")
    return 0
if __name__ == "__main__": raise SystemExit(main())
