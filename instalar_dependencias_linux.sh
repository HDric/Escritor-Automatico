#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "No se encontró Python 3. Esta opción es solo para ejecutar el código fuente."
  echo "Para usuarios finales, descarga el paquete Linux compilado que incluye Python."
  exit 1
fi
python3 -c 'import sys; print("Python compatible:", sys.version.split()[0]); sys.exit(0 if sys.version_info >= (3, 11) else "Se requiere Python 3.11 o superior.")'
if ! command -v gcc >/dev/null 2>&1 || ! command -v python3-config >/dev/null 2>&1; then
  echo "Para compilar evdev desde el código fuente faltan herramientas de compilación o cabeceras de Python."
  echo "En Ubuntu/Debian instala primero: sudo apt-get install build-essential python3-dev"
  exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: --upgrade 'pip==26.2.2' 'setuptools==84.2.1'
# evdev solo publica un sdist para esta versión; su integridad se comprueba con el hash fijado.
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir --no-build-isolation --no-deps --no-binary=:all: --require-hashes -r requirements-linux-source.txt
# Las demás dependencias deben instalarse desde wheels; pynput reutiliza evdev ya compilado.
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: -r requirements.txt
.venv/bin/python -m pip check
echo "Dependencias instaladas en .venv. Ejecuta ./iniciar_linux.sh para abrir la aplicación."
