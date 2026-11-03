# Corrección de dependencias Windows y compilaciones duplicadas — beta v1.0.2

## Archivos incluidos

- `requirements.txt`: agrega `cffi==2.1.1` y `pycparser==3.12` como dependencias fijadas.
- `.github/workflows/build-installer.yml`: elimina `beta/v1.0.2` del evento `push`.

## Motivo del fallo Windows

`CREAR_INSTALADOR.bat` crea un entorno virtual y después instala `requirements.txt` con `--no-deps` para evitar que pip resuelva dependencias transitivas no fijadas. `cryptography==50.0.2` declara `cffi` como dependencia y CFFI necesita `pycparser`. Como no estaban declaradas expresamente, `pip check` detectaba `cryptography 50.0.2 requires cffi, which is not installed` y detenía el build.

Este parche declara las dos dependencias transitivas con versiones exactas. Hay wheel de CFFI 2.1.1 para CPython 3.12 Windows x64, por lo que se mantiene la política `--only-binary=:all:` sin compilar dependencias desde código fuente.

## Motivo de las ejecuciones duplicadas

El workflow tenía dos disparadores que reaccionaban a una subida a `beta/v1.0.2`:

1. `push` sobre la rama beta.
2. `pull_request` con destino `main`, evento `synchronize` al actualizar el PR.

Como la rama beta ya tiene una Draft Pull Request hacia `main`, el evento `pull_request` es suficiente para validar cada actualización. Se quita la rama beta de `push`; se conservan `push` para `main`, `master` y etiquetas `v*`, además de `workflow_dispatch` y `pull_request` a `main`.

## Aplicación

1. Descomprime este parche en la raíz del repositorio local, conservando `.git` y permitiendo reemplazar los dos archivos.
2. Comprueba los cambios:

   ```bash
   git status --short
   git diff --check
   git diff -- requirements.txt .github/workflows/build-installer.yml
   ```

3. Confirma que `beta/v1.0.2` es la rama actual:

   ```bash
   git branch --show-current
   ```

4. Guarda y sube la corrección:

   ```bash
   git add requirements.txt .github/workflows/build-installer.yml
   git commit -m "Fix Windows CFFI dependency and avoid duplicate CI runs"
   git push origin beta/v1.0.2
   ```

5. Comprueba la Draft Pull Request: cada push nuevo a la rama debe crear una ejecución `pull_request` (sin otra ejecución adicional por `push` a la rama beta). `main` no se modifica y el PR permanece en Draft.

## Validación pendiente

El parche se construyó sobre el código fuente v1.0.2 entregado y se verificó que los dos cambios son coherentes con los comandos de instalación existentes. La compilación real en `windows-2022` debe confirmarse en GitHub Actions. No se ha ejecutado desde este entorno un runner Windows de GitHub.
