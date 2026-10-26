#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/EscritorAutomatico"
TARGET="$HOME/.local/opt/escritor-automatico"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/escritor-automatico.desktop"
if [[ ! -x "$SOURCE/EscritorAutomatico" ]]; then
  echo "No se encuentra el ejecutable empaquetado en: $SOURCE/EscritorAutomatico"
  echo "Extrae EscritorAutomatico-v1.0.0-linux-x86_64.tar.gz completo antes de ejecutar este instalador."
  exit 1
fi
mkdir -p "$HOME/.local/opt" "$DESKTOP_DIR"
rm -rf -- "$TARGET"
mkdir -p "$TARGET"
cp -a "$SOURCE/." "$TARGET/"
chmod u+x "$TARGET/EscritorAutomatico"
cat > "$DESKTOP_FILE" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Name=Escritor Automático
Comment=Escritura automática compatible con Windows/Linux
Exec="$TARGET/EscritorAutomatico"
Path="$TARGET"
Terminal=false
Categories=Office;Utility;
StartupNotify=true
EOF_DESKTOP
cat > "$TARGET/desinstalar.sh" <<'EOF_UNINSTALL'
#!/usr/bin/env bash
set -euo pipefail
TARGET="$HOME/.local/opt/escritor-automatico"
DESKTOP_FILE="$HOME/.local/share/applications/escritor-automatico.desktop"
rm -f -- "$DESKTOP_FILE"
rm -rf -- "$TARGET"
echo "Escritor Automático se ha desinstalado del usuario actual."
EOF_UNINSTALL
chmod u+x "$TARGET/desinstalar.sh"
echo "Instalación completada en: $TARGET"
echo "Puedes abrirlo desde el menú de aplicaciones o ejecutar: $TARGET/EscritorAutomatico"
echo "Para desinstalarlo, ejecuta: $TARGET/desinstalar.sh"
echo "No se instaló ni modificó Python en el sistema."
