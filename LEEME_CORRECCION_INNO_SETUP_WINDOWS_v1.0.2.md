# Corrección del detector de versión de Inno Setup (Windows) — v1.0.2

## Motivo

El compilador `ISCC.exe` encontrado en GitHub Actions tiene metadatos de archivo que devuelven `ProductVersion = 0.0.0.0`. Ese campo no es una fuente fiable para comprobar la versión instalada y producía un falso error aunque Chocolatey hubiera instalado Inno Setup 6.7.1.

## Archivos del parche

- `CREAR_INSTALADOR.bat`: sustituye la comprobación de `VersionInfo.ProductVersion` por el verificador de registro.
- `tools/verify_inno_setup.ps1`: comprueba `DisplayVersion` e `InstallLocation` de la entrada estándar de desinstalación de Inno Setup y exige que coincidan con el ejecutable `ISCC.exe` que se va a usar.

La comprobación sigue siendo estricta: exige versión exacta 6.7.1 y que la ruta del compilador coincida con la instalación registrada. No omite ni desactiva la validación.

## Aplicación

1. Descomprime este ZIP en la raíz del repositorio local, encima del proyecto actual, conservando la carpeta `.git`.
2. En Git Bash, revisa los cambios:

   ```bash
   git status
   git diff --check
   git diff -- CREAR_INSTALADOR.bat
   ```

3. Sube solo los dos archivos del parche:

   ```bash
   git add CREAR_INSTALADOR.bat tools/verify_inno_setup.ps1
   git commit -m "Fix Inno Setup version detection on Windows"
   git push origin beta/v1.0.2
   ```

4. El Pull Request debe permanecer en Draft. Después de subir el commit, revisa el nuevo resultado del trabajo de Windows en GitHub Actions.

## Límite de validación

Este parche se ha comprobado por inspección de la entrada de registro que publica Inno Setup 6.7.1 y por revisión de la lógica del script. No se ha ejecutado en un runner Windows real desde este entorno; GitHub Actions debe confirmar la corrección.
