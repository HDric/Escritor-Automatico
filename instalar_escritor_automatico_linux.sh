#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/EscritorAutomatico"
PARENT="$HOME/.local/opt"
TARGET="$PARENT/escritor-automatico"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/escritor-automatico.desktop"

if [[ ! -x "$SOURCE/EscritorAutomatico" ]]; then
  echo "No se encuentra el ejecutable empaquetado en: $SOURCE/EscritorAutomatico" >&2
  echo "Extrae el paquete Linux completo antes de ejecutar este instalador." >&2
  exit 1
fi
if [[ "$TARGET" == "$HOME" || "$TARGET" == "/" || "$TARGET" == "$PARENT" ]]; then
  echo "Destino de instalación no válido." >&2
  exit 1
fi
if [[ -e "$TARGET" || -L "$TARGET" ]]; then
  if [[ ! -d "$TARGET" || -L "$TARGET" ]]; then
    echo "El destino ya existe y no es un directorio normal: $TARGET" >&2
    exit 1
  fi
fi

mkdir -p -- "$PARENT" "$DESKTOP_DIR"
STAGING="$(mktemp -d "$PARENT/.escritor-automatico.staging.XXXXXX")"
BACKUP="$PARENT/.escritor-automatico.backup.$(date +%Y%m%d%H%M%S).$$"
HAD_OLD=0
MOVED_NEW=0

rollback_on_error() {
  status=$?
  if [[ $status -ne 0 ]]; then
    if [[ $MOVED_NEW -eq 1 && -d "$TARGET" && ! -L "$TARGET" ]]; then
      rm -rf -- "$TARGET"
    fi
    if [[ $HAD_OLD -eq 1 && -d "$BACKUP" && ! -L "$BACKUP" && ! -e "$TARGET" ]]; then
      mv -- "$BACKUP" "$TARGET" || true
    fi
    echo "La instalación no terminó. Se intentó restaurar la versión anterior." >&2
  fi
  if [[ -n "${STAGING:-}" && -d "$STAGING" && ! -L "$STAGING" ]]; then
    rm -rf -- "$STAGING"
  fi
  return "$status"
}
trap rollback_on_error EXIT

cp -a -- "$SOURCE/." "$STAGING/"
chmod u+x "$STAGING/EscritorAutomatico"

if [[ -d "$TARGET" && ! -L "$TARGET" ]]; then
  if [[ -e "$BACKUP" || -L "$BACKUP" ]]; then
    echo "La ruta de respaldo ya existe; no se sobrescribirá: $BACKUP" >&2
    exit 1
  fi
  mv -- "$TARGET" "$BACKUP"
  HAD_OLD=1
fi
mv -- "$STAGING" "$TARGET"
MOVED_NEW=1
STAGING=""

# Desktop Entry: quoted Exec argument with escaping for quotes, slashes and percent codes.
desktop_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//%/%%}"
  printf '"%s"' "$value"
}
EXEC_VALUE="$(desktop_quote "$TARGET/EscritorAutomatico")"
cat > "$DESKTOP_FILE" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Name=Escritor Automático
Comment=Escritura automática compatible con Windows/Linux
Exec=$EXEC_VALUE
Path=$TARGET
Terminal=false
Categories=Office;Utility;
StartupNotify=true
EOF_DESKTOP
chmod 0644 "$DESKTOP_FILE"

cat > "$TARGET/desinstalar.sh" <<'EOF_UNINSTALL'
#!/usr/bin/env bash
set -euo pipefail
TARGET="$HOME/.local/opt/escritor-automatico"
DESKTOP_FILE="$HOME/.local/share/applications/escritor-automatico.desktop"
if [[ -L "$TARGET" || ( -e "$TARGET" && ! -d "$TARGET" ) ]]; then
  echo "Destino de desinstalación no válido: $TARGET" >&2
  exit 1
fi
rm -f -- "$DESKTOP_FILE"
rm -rf -- "$TARGET"
echo "Escritor Automático se ha desinstalado del usuario actual."
EOF_UNINSTALL
chmod u+x "$TARGET/desinstalar.sh"

trap - EXIT
echo "Instalación completada en: $TARGET"
if [[ $HAD_OLD -eq 1 ]]; then
  echo "La versión anterior se conservó como respaldo en: $BACKUP"
fi
echo "Puedes abrirlo desde el menú de aplicaciones o ejecutar: $TARGET/EscritorAutomatico"
echo "Para desinstalarlo, ejecuta: $TARGET/desinstalar.sh"
echo "No se instaló ni modificó Python en el sistema."
