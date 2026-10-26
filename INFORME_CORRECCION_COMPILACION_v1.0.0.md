# Corrección de compilación v1.0.0

## Causa identificada en Windows

PyInstaller genera `build/spec/EscritorAutomatico.spec`. Las rutas relativas pasadas a `--add-data` se resolvían respecto a la carpeta del `.spec`, y por eso intentaba encontrar `build/spec/web_extension` en vez de `web_extension` en la raíz del repositorio. El flujo ahora pasa rutas absolutas a los recursos de entrada.

## Causa identificada en Linux

`pynput` requiere `evdev` en Linux, pero `evdev` publica un archivo fuente (`sdist`) en PyPI y la compilación exigía `--only-binary=:all:` para cada paquete. Por eso `pip` rechazaba la dependencia. El nuevo `requirements-linux-source.txt` fija `evdev==1.9.3` y verifica el SHA-256 publicado por PyPI (`2c140e01ac8437758fa23fe5c871397412461f42d421aa20241dc8fe8cfccbc9`). El runner instala `build-essential` y `python3.12-dev`, construye esa dependencia por separado con `--no-build-isolation`, y mantiene la política de solo wheels para el resto.

Fuente del hash: página de release de evdev 1.9.3 en PyPI: https://pypi.org/project/evdev/1.9.3/.

## Cambios adicionales

- PyInstaller recopila `evdev` además de `pynput` y `Xlib` en Linux.
- `preflight.py` y `preflight_linux.py` validan la presencia y el hash esperado del lockfile Linux.
- `instalar_dependencias_linux.sh` reproduce el mismo orden de instalación al ejecutar desde el código fuente y explica los prerrequisitos nativos.
- La versión pública continúa siendo `1.0.0`; no se incrementó el número de versión mientras se corrige la compilación inicial.

## Validaciones locales

Se ejecutarán validaciones de sintaxis, pruebas del actualizador, comprobación de manifiesto, scripts y estructura ZIP. Esta sesión no puede confirmar una compilación real en los runners hospedados de GitHub; debe ejecutarse el workflow tras subir estos cambios. Si surge un error posterior, el nuevo registro permitirá identificarlo.
