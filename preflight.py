#!/usr/bin/env python3
"""Validaciones previas a la compilación de Escritor Automático v1.0.0."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED_EXTENSION_ID = "gokleoeeegcjpahldnbmepeeokjafodl"
REQUIRED_FILES = (
    "escritor_automatico.py",
    "updater.py",
    "version.json",
    "update_config.json",
    "requirements.txt",
    "requirements-build.txt",
    "requirements-linux-source.txt",
    "installer.iss",
    "POST_INSTALACION.txt",
    "LEEME.txt",
    "INFORME_SEGURIDAD.md",
    "web_extension/manifest.json",
    "web_extension/service_worker.js",
    "web_extension/content.js",
    "web_extension/popup.html",
    "web_extension/popup.js",
    "web_extension/LEEME.txt",
)


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    print("Validando archivos y coherencia del proyecto...")
    for name in REQUIRED_FILES:
        if not (ROOT / name).is_file():
            fail(f"Falta el archivo requerido: {name}")

    version_info = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    version_value = version_info.get("version")
    if not isinstance(version_value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version_value):
        fail("version.json debe contener una versión en formato X.Y.Z.")
    config = json.loads((ROOT / "update_config.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("repository", ""), str):
        fail("update_config.json no contiene la configuración esperada.")
    updater_path = ROOT / "updater.py"
    try:
        compile(updater_path.read_text(encoding="utf-8"), str(updater_path), "exec")
    except SyntaxError as exc:
        fail(f"Error de sintaxis en updater.py línea {exc.lineno}: {exc.msg}")
    print(f"  OK: actualizador y versión {version_value}")

    source_path = ROOT / "escritor_automatico.py"
    source = source_path.read_text(encoding="utf-8")
    try:
        compile(source, str(source_path), "exec")
    except SyntaxError as exc:
        fail(f"Error de sintaxis Python en línea {exc.lineno}: {exc.msg}")
    print("  OK: sintaxis Python")

    manifest_path = ROOT / "web_extension/manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"El manifiesto de la extensión no es JSON válido: {exc}")
    if manifest.get("manifest_version") != 3:
        fail("La extensión no usa Manifest V3.")
    key = manifest.get("key")
    if not isinstance(key, str) or not key:
        fail("El manifiesto no tiene una clave pública 'key'.")
    try:
        public_key = base64.b64decode(key, validate=True)
    except (ValueError, base64.binascii.Error):
        fail("La clave pública del manifiesto no tiene base64 válido.")
    digest = hashlib.sha256(public_key).hexdigest()[:32]
    extension_id = "".join(chr(ord("a") + int(char, 16)) for char in digest)
    if extension_id != EXPECTED_EXTENSION_ID:
        fail(f"El ID derivado de la extensión es {extension_id}, no {EXPECTED_EXTENSION_ID}.")
    if f'WEB_EXTENSION_ID = "{EXPECTED_EXTENSION_ID}"' not in source:
        fail("El ID de la extensión en Python no coincide con el ID esperado.")
    worker_source = (ROOT / "web_extension/service_worker.js").read_text(encoding="utf-8")
    if "ws://127.0.0.1:8765" not in worker_source:
        fail("No se encontró la dirección local WebSocket esperada en la extensión.")
    print(f"  OK: manifiesto válido e ID de extensión coherente ({extension_id})")

    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package, version in {
        "python-docx": "1.2.0", "lxml": "6.1.3", "typing_extensions": "4.16.0",
        "websockets": "17.3", "Pillow": "13.0.0", "pywin32": "312",
        "pynput": "1.8.2",
    }.items():
        # pywin32 incluye un marcador de plataforma después de la versión.
        if not re.search(rf"(?im)^\s*{re.escape(package)}=={re.escape(version)}(?:\s*;.*)?\s*$", requirements):
            fail(f"La dependencia {package} no está fijada a {version} en requirements.txt.")
    if not re.search(r'(?im)^\s*pynput==1\.8\.2\s*;\s*sys_platform\s*==\s*"linux"\s*$', requirements):
        fail("pynput debe estar fijado a 1.8.2 y limitado a Linux.")
    linux_source_requirements = (ROOT / "requirements-linux-source.txt").read_text(encoding="utf-8")
    if "evdev==1.9.3" not in linux_source_requirements or "--hash=sha256:2c140e01ac8437758fa23fe5c871397412461f42d421aa20241dc8fe8cfccbc9" not in linux_source_requirements:
        fail("La dependencia de compilación Linux evdev no tiene la versión y el hash esperados.")
    if "IS_LINUX" not in source or "create_keyboard_backend" not in source or "Sistema detectado automáticamente" not in source:
        fail("No se encontró la selección automática Windows/Linux en el programa.")
    print("  OK: dependencias fijadas y detección de sistema operativo")

    build_requirements = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
    for package, version in {
        "altgraph": "0.17.5", "packaging": "26.3", "pefile": "2024.8.26",
        "pyinstaller-hooks-contrib": "2026.9", "pyinstaller": "6.22.3",
        "pywin32-ctypes": "0.2.3", "setuptools": "84.2.1",
    }.items():
        if not re.search(rf"(?im)^\s*{re.escape(package)}=={re.escape(version)}\s*$", build_requirements):
            fail(f"La herramienta de compilación {package} no está fijada a {version}.")
    print("  OK: herramientas y dependencias de compilación fijadas")

    build_script = (ROOT / "CREAR_INSTALADOR.bat").read_text(encoding="utf-8")
    for required_data_arg in (
        r'%CD%\web_extension;web_extension',
        r'%CD%\LEEME.txt;.',
        r'%CD%\INFORME_SEGURIDAD.md;.',
        r'%CD%\version.json;.',
        r'%CD%\update_config.json;.',
    ):
        if required_data_arg not in build_script:
            fail(f"PyInstaller debe usar rutas de entrada absolutas con --add-data: falta {required_data_arg}.")
    print("  OK: rutas absolutas de recursos para PyInstaller")

    iss = (ROOT / "installer.iss").read_text(encoding="utf-8")
    for required_setting in ("PrivilegesRequired=lowest", "CloseApplications=yes", "SetupLogging=yes", "SetupMutex=EscritorAutomaticoSetupMutex"):
        if required_setting not in iss:
            fail(f"Falta un ajuste esperado del instalador: {required_setting}")
    # POST_INSTALACION.txt se copia al bundle en el .bat; no debe declararse otra
    # vez como una fuente independiente porque colisionaría en el mismo destino.
    if re.search(r'(?im)^\s*Source:\s*"POST_INSTALACION\.txt"', iss):
        fail("installer.iss declara POST_INSTALACION.txt dos veces; elimine la fuente duplicada.")
    if 'Source: "dist\\EscritorAutomatico\\*"' not in iss:
        fail("installer.iss no incluye el directorio empaquetado de PyInstaller.")
    print("  OK: script Inno Setup sin la entrada duplicada detectada en versiones anteriores")

    node = shutil.which("node")
    if node:
        js_files = sorted((ROOT / "web_extension").glob("*.js"))
        for js_path in js_files:
            result = subprocess.run([node, "--check", str(js_path)], capture_output=True, text=True, check=False)
            if result.returncode:
                fail(f"Error de sintaxis JavaScript en {js_path.name}: {(result.stderr or result.stdout).strip()}")
        print(f"  OK: sintaxis de {len(js_files)} archivos JavaScript (Node.js)")
    else:
        print("  AVISO: Node.js no está instalado; se omite la comprobación automática de sintaxis JavaScript.")

    print("Validación previa completada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
