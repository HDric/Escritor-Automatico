#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ -x "./EscritorAutomatico/EscritorAutomatico" ]]; then
  exec "./EscritorAutomatico/EscritorAutomatico" "$@"
fi
if [[ -x "./.venv/bin/python" ]]; then
  exec "./.venv/bin/python" ./escritor_automatico.py "$@"
fi
if command -v python3 >/dev/null 2>&1; then
  echo "No existe el entorno .venv. Para código fuente, ejecuta primero ./instalar_dependencias_linux.sh"
else
  echo "Este paquete de código fuente necesita Python 3.11+. Para una instalación sin Python, descarga el paquete Linux compilado."
fi
exit 1
