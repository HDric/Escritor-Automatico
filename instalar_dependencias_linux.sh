#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "No se encontró Python 3. Esta opción es solo para ejecutar el código fuente."
  echo "Para usuarios finales, descarga el paquete Linux compilado que incluye Python."
  exit 1
fi
python3 -c 'import sys; print("Python compatible:", sys.version.split()[0]); sys.exit(0 if sys.version_info >= (3, 11) else "Se requiere Python 3.11 o superior.")'
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.txt
.venv/bin/python -m pip check
echo "Dependencias instaladas en .venv. Ejecuta ./iniciar_linux.sh para abrir la aplicación."
