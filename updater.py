"""Actualizaciones opcionales y verificadas para Escritor Automático.

Solo consulta GitHub Releases. Nunca instala nada sin una acción explícita del usuario.
Las descargas están limitadas, usan HTTPS y se verifican con SHA-256 antes de usarse.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

PRODUCT_SLUG = "EscritorAutomatico"
USER_AGENT = "EscritorAutomatico-Updater"
MAX_API_BYTES = 2 * 1024 * 1024
MAX_CHECKSUM_BYTES = 64 * 1024
MAX_INSTALLER_BYTES = 512 * 1024 * 1024
MAX_TAR_MEMBERS = 15000
MAX_TAR_UNPACKED_BYTES = 900 * 1024 * 1024
ALLOWED_REDIRECT_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class UpdateError(RuntimeError):
    """Problema de conexión, configuración o verificación de actualización."""


def resource_dir() -> Path:
    """Localiza datos incluidos por PyInstaller o junto al código fuente."""
    if getattr(sys, "frozen", False):
        candidates = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass))
        candidates.append(Path(sys.executable).resolve().parent)
        for candidate in candidates:
            if (candidate / "version.json").is_file():
                return candidate
        return candidates[0] if candidates else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UpdateError(f"No se encuentra el archivo de configuración: {path.name}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateError(f"No se pudo leer {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise UpdateError(f"El archivo {path.name} debe contener un objeto JSON.")
    return value


def get_app_version() -> str:
    path = resource_dir() / "version.json"
    try:
        data = read_json_object(path)
        version = data.get("version")
        parse_version(version)
        return version
    except (UpdateError, ValueError, TypeError):
        # Permite abrir el programa si el archivo está dañado, pero el actualizador
        # también advertirá al usuario de que no puede confirmar la versión.
        return "1.0.0"


def parse_version(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ValueError("La versión debe ser texto con formato X.Y.Z.")
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Versión no válida: {value!r}. Usa el formato X.Y.Z, por ejemplo 1.0.0.")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


APP_VERSION = get_app_version()


def user_config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "EscritorAutomatico"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "escritor-automatico"


def user_cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "EscritorAutomatico" / "updates"
    base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return base / "escritor-automatico" / "updates"


def version_is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    return parse_version(candidate) > parse_version(current)


class UpdateManager:
    def __init__(self) -> None:
        self._prefs_path = user_config_dir() / "update_preferences.json"

    def _config(self) -> dict[str, Any]:
        path = resource_dir() / "update_config.json"
        if not path.is_file():
            raise UpdateError(
                "Esta compilación no tiene configurado el repositorio de actualizaciones. "
                "Compila la aplicación mediante el flujo oficial de GitHub Actions."
            )
        data = read_json_object(path)
        repo = data.get("repository", "")
        if not isinstance(repo, str) or not REPO_RE.fullmatch(repo.strip()):
            raise UpdateError(
                "El repositorio de actualizaciones no está configurado. "
                "La compilación publicada debe incluir OWNER/REPOSITORY en update_config.json."
            )
        return {"repository": repo.strip()}

    def load_preferences(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "check_on_start": True, "ignored_versions": [],
            "snoozed_version": "", "snoozed_until": 0.0,
        }
        try:
            data = read_json_object(self._prefs_path)
        except UpdateError:
            return defaults
        check_on_start = data.get("check_on_start", True)
        ignored = data.get("ignored_versions", [])
        snoozed_version = data.get("snoozed_version", "")
        snoozed_until = data.get("snoozed_until", 0.0)
        if not isinstance(check_on_start, bool):
            check_on_start = True
        if not isinstance(ignored, list):
            ignored = []
        ignored = [v for v in ignored if isinstance(v, str) and VERSION_RE.fullmatch(v)][:100]
        if not isinstance(snoozed_version, str) or not VERSION_RE.fullmatch(snoozed_version):
            snoozed_version = ""
        if not isinstance(snoozed_until, (int, float)):
            snoozed_until = 0.0
        return {
            "check_on_start": check_on_start, "ignored_versions": ignored,
            "snoozed_version": snoozed_version, "snoozed_until": float(snoozed_until),
        }

    def save_preferences(self, preferences: dict[str, Any]) -> None:
        check_on_start = preferences.get("check_on_start", True)
        ignored = preferences.get("ignored_versions", [])
        snoozed_version = preferences.get("snoozed_version", "")
        snoozed_until = preferences.get("snoozed_until", 0.0)
        if not isinstance(check_on_start, bool):
            check_on_start = True
        if not isinstance(ignored, list):
            ignored = []
        safe_ignored = [v for v in ignored if isinstance(v, str) and VERSION_RE.fullmatch(v)][:100]
        if not isinstance(snoozed_version, str) or not VERSION_RE.fullmatch(snoozed_version):
            snoozed_version = ""
        if not isinstance(snoozed_until, (int, float)):
            snoozed_until = 0.0
        target = self._prefs_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix(".json.tmp")
            temp.write_text(
                json.dumps({
                    "check_on_start": check_on_start,
                    "ignored_versions": safe_ignored,
                    "snoozed_version": snoozed_version,
                    "snoozed_until": float(snoozed_until),
                }, indent=2),
                encoding="utf-8",
            )
            try:
                os.chmod(temp, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            temp.replace(target)
        except OSError as exc:
            raise UpdateError(f"No se pudo guardar la preferencia de actualizaciones: {exc}") from exc

    @staticmethod
    def _request(url: str, max_bytes: int) -> bytes:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise UpdateError("La dirección de actualización no usa HTTPS.")
        host = parsed.hostname.lower()
        if host not in ({"api.github.com"} | ALLOWED_REDIRECT_HOSTS):
            raise UpdateError("Se rechazó una dirección de descarga fuera de GitHub.")
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                final = urllib.parse.urlsplit(response.geturl())
                if final.scheme != "https" or (final.hostname or "").lower() not in ({"api.github.com"} | ALLOWED_REDIRECT_HOSTS):
                    raise UpdateError("La descarga fue redirigida a un servidor no permitido.")
                length = response.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise UpdateError("El archivo remoto supera el tamaño máximo permitido.")
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(65536, max_bytes + 1 - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > max_bytes:
                        raise UpdateError("El archivo remoto supera el tamaño máximo permitido.")
                return b"".join(chunks)
        except UpdateError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise UpdateError(f"No se pudo conectar con GitHub: {exc}") from exc

    def check_latest_release(self) -> dict[str, Any]:
        config = self._config()
        repo = config["repository"]
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            payload = json.loads(self._request(url, MAX_API_BYTES).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise UpdateError("GitHub devolvió una respuesta que no se pudo interpretar.") from exc
        if not isinstance(payload, dict):
            raise UpdateError("La respuesta de GitHub tiene un formato inesperado.")
        tag = payload.get("tag_name")
        try:
            tag_version = parse_version(tag)
        except ValueError as exc:
            raise UpdateError("La última Release no usa una etiqueta de versión X.Y.Z (por ejemplo, v1.0.0).") from exc
        html_url = payload.get("html_url")
        parsed_release_url = urllib.parse.urlsplit(html_url or "")
        if parsed_release_url.scheme != "https" or parsed_release_url.hostname != "github.com":
            raise UpdateError("La Release contiene una dirección web que no es válida.")
        assets = payload.get("assets", [])
        if not isinstance(assets, list):
            raise UpdateError("La lista de archivos de la Release no es válida.")
        safe_assets: list[dict[str, Any]] = []
        for item in assets:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            download_url = item.get("browser_download_url")
            try:
                size = int(item.get("size", 0))
            except (TypeError, ValueError):
                continue
            parsed_asset = urllib.parse.urlsplit(download_url or "")
            if (
                isinstance(name, str)
                and ASSET_NAME_RE.fullmatch(name)
                and parsed_asset.scheme == "https"
                and parsed_asset.hostname == "github.com"
                and size >= 0
                and size <= MAX_INSTALLER_BYTES
            ):
                safe_assets.append({"name": name, "url": download_url, "size": size})
        body = payload.get("body", "")
        if not isinstance(body, str):
            body = ""
        current_tuple = parse_version(APP_VERSION)
        return {
            "version": tag.lstrip("v"),
            "tag": tag,
            "is_update": tag_version > current_tuple,
            "url": html_url,
            "body": body[:4000],
            "assets": safe_assets,
            "repository": repo,
        }

    @staticmethod
    def expected_asset_name(version: str, os_name: str | None = None) -> str:
        os_name = (os_name or platform.system()).lower()
        if os_name in ("windows", "win32"):
            return f"EscritorAutomatico-Setup-v{version}.exe"
        if os_name == "linux":
            return f"EscritorAutomatico-v{version}-linux-x86_64.tar.gz"
        raise UpdateError(f"El actualizador no admite este sistema operativo: {os_name}.")

    @staticmethod
    def _find_checksum(checksum_text: str, asset_name: str) -> str:
        for line in checksum_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Fa-f0-9]{64})\s+\*?(.+?)\s*$", line)
            if match and match.group(2).strip() == asset_name:
                return match.group(1).lower()
        raise UpdateError(f"La lista de sumas no contiene el SHA-256 de {asset_name}.")

    @staticmethod
    def _download_to_file(url: str, target: Path, max_bytes: int) -> None:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise UpdateError("La URL del instalador no pertenece a github.com.")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                final = urllib.parse.urlsplit(response.geturl())
                if final.scheme != "https" or (final.hostname or "").lower() not in ALLOWED_REDIRECT_HOSTS:
                    raise UpdateError("La descarga del instalador fue redirigida a un host no permitido.")
                length = response.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise UpdateError("El instalador supera el tamaño máximo permitido.")
                total = 0
                with temporary.open("wb") as out:
                    while True:
                        block = response.read(1024 * 256)
                        if not block:
                            break
                        total += len(block)
                        if total > max_bytes:
                            raise UpdateError("El archivo descargado supera el tamaño máximo permitido.")
                        out.write(block)
            if total == 0:
                raise UpdateError("GitHub devolvió un archivo vacío.")
            temporary.replace(target)
        except UpdateError:
            temporary.unlink(missing_ok=True)
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            raise UpdateError(f"No se pudo descargar el instalador: {exc}") from exc

    def download_and_prepare(self, release: dict[str, Any], os_name: str | None = None) -> dict[str, Any]:
        version = release.get("version")
        parse_version(version)
        asset_name = self.expected_asset_name(version, os_name)
        assets = release.get("assets", [])
        asset = next((a for a in assets if a.get("name") == asset_name), None)
        checksum_asset = next((a for a in assets if a.get("name") == "SHA256SUMS.txt"), None)
        if not asset:
            raise UpdateError(f"La Release {release.get('tag')} no contiene el instalador esperado: {asset_name}.")
        if not checksum_asset:
            raise UpdateError("La Release no incluye SHA256SUMS.txt; se rechazó la descarga por seguridad.")
        if int(asset.get("size", 0)) > MAX_INSTALLER_BYTES:
            raise UpdateError("El instalador supera el tamaño máximo permitido.")
        checksum_raw = self._request(checksum_asset["url"], MAX_CHECKSUM_BYTES)
        try:
            checksum_text = checksum_raw.decode("utf-8")
        except UnicodeError as exc:
            raise UpdateError("La lista SHA-256 no está codificada como UTF-8.") from exc
        expected_hash = self._find_checksum(checksum_text, asset_name)

        cache_base = user_cache_dir()
        cache_base.mkdir(parents=True, exist_ok=True)
        version_dir = cache_base / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)
        download_path = version_dir / asset_name
        self._download_to_file(asset["url"], download_path, MAX_INSTALLER_BYTES)
        sha = hashlib.sha256()
        with download_path.open("rb") as src:
            for block in iter(lambda: src.read(1024 * 1024), b""):
                sha.update(block)
        if sha.hexdigest().lower() != expected_hash:
            download_path.unlink(missing_ok=True)
            raise UpdateError("La verificación SHA-256 falló. El archivo descargado fue eliminado y no se ejecutará.")

        if (os_name or platform.system()).lower() in ("windows", "win32"):
            if download_path.suffix.lower() != ".exe" or download_path.stat().st_size < 100_000:
                raise UpdateError("El archivo de Windows no parece un instalador válido.")
            return {"kind": "windows", "path": download_path, "version": version, "sha256": expected_hash}

        if (os_name or platform.system()).lower() != "linux":
            raise UpdateError(f"Sistema no admitido para instalar actualizaciones: {os_name or platform.system()}.")
        extract_dir = Path(tempfile.mkdtemp(prefix=f"prepared-v{version}-", dir=str(version_dir)))
        try:
            self._safe_extract_linux_package(download_path, extract_dir)
        except Exception:
            shutil.rmtree(extract_dir, ignore_errors=True)
            raise
        installer_script = extract_dir / "instalar_escritor_automatico_linux.sh"
        executable = extract_dir / "EscritorAutomatico" / "EscritorAutomatico"
        if not installer_script.is_file() or not executable.is_file():
            shutil.rmtree(extract_dir, ignore_errors=True)
            raise UpdateError("El paquete Linux no contiene el instalador y el ejecutable esperados.")
        installer_script.chmod(installer_script.stat().st_mode | stat.S_IXUSR)
        return {
            "kind": "linux",
            "path": installer_script,
            "root": extract_dir,
            "archive": download_path,
            "version": version,
            "sha256": expected_hash,
        }

    @staticmethod
    def _safe_extract_linux_package(archive_path: Path, destination: Path) -> None:
        """Extrae solo archivos regulares/directorios, rechazando escapes y enlaces."""
        total_size = 0
        try:
            with tarfile.open(archive_path, mode="r:gz") as archive:
                member_count = 0
                for member in archive:
                    member_count += 1
                    if member_count > MAX_TAR_MEMBERS:
                        raise UpdateError("El paquete Linux contiene demasiados archivos.")
                    raw = member.name.replace("\\", "/")
                    posix = PurePosixPath(raw)
                    parts = tuple(part for part in posix.parts if part not in ("", "."))
                    if posix.is_absolute() or any(part == ".." for part in parts):
                        raise UpdateError("El paquete Linux contiene una ruta no permitida.")
                    if not parts:
                        # El tar creado por el flujo incluye la entrada raíz "./".
                        if member.isdir() and raw.rstrip("/") in ("", "."):
                            continue
                        raise UpdateError("El paquete Linux contiene una ruta vacía no permitida.")
                    if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                        raise UpdateError("El paquete Linux contiene enlaces o tipos de archivo no permitidos.")
                    target = destination.joinpath(*parts)
                    resolved_target = target.resolve()
                    if resolved_target != destination.resolve() and destination.resolve() not in resolved_target.parents:
                        raise UpdateError("Se rechazó un archivo del paquete que intenta salir de la carpeta de actualización.")
                    if member.isfile():
                        total_size += member.size
                        if member.size < 0 or total_size > MAX_TAR_UNPACKED_BYTES:
                            raise UpdateError("El paquete Linux supera el tamaño descomprimido permitido.")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        source = archive.extractfile(member)
                        if source is None:
                            raise UpdateError("No se pudo leer un archivo del paquete Linux.")
                        with source, target.open("wb") as output:
                            shutil.copyfileobj(source, output, length=1024 * 1024)
                        target.chmod(0o644)
                    else:
                        target.mkdir(parents=True, exist_ok=True)
        except UpdateError:
            raise
        except (tarfile.TarError, OSError) as exc:
            raise UpdateError(f"No se pudo validar el paquete Linux: {exc}") from exc

    @staticmethod
    def open_release_url(release: dict[str, Any]) -> str:
        url = release.get("url", "")
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise UpdateError("Se rechazó una dirección de Release no confiable.")
        return url
