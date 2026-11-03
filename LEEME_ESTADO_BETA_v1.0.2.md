# Estado del proyecto — beta v1.0.2

Este paquete reúne las correcciones acumuladas para la rama `beta/v1.0.2`.

## Cambios incluidos en esta entrega

- Se conserva el verificador de Inno Setup 6.7.1 basado en `DisplayVersion` e `InstallLocation`, que valida también que la ruta registrada corresponda al `ISCC.exe` usado.
- `requirements.txt` fija `cffi==2.1.1` y `pycparser==3.12`, necesarias para que el `pip check` del entorno Windows funcione cuando las dependencias se instalan con `--no-deps`.
- El workflow mantiene la instalación explícita de `cryptography==50.0.2` antes de ejecutar las pruebas Ed25519 con el Python global de Windows.
- Se elimina `beta/v1.0.2` del disparador `push`. Como la beta se valida mediante su Pull Request hacia `main`, las actualizaciones de la rama disparan el workflow mediante `pull_request` y evitan la ejecución duplicada por `push` y `pull_request`.

## Aplicación sobre el repositorio local

1. Conserva la rama `beta/v1.0.2`.
2. Extrae el contenido de este paquete sobre la carpeta del repositorio, permitiendo reemplazar archivos existentes. No reemplaces ni elimines la carpeta `.git`.
3. Revisa `git status`, `git diff --check` y `git diff`.
4. Comprueba que `.github/workflows/build-installer.yml` conserva el paso `Instalar dependencia Ed25519 para las pruebas`, que no incluye `beta/v1.0.2` bajo `push`, y que `requirements.txt` incluye `cffi` y `pycparser`.
5. Crea un commit y súbelo a `beta/v1.0.2`. El Pull Request debe permanecer en Draft durante la revisión.

## Seguridad de claves

Este paquete no contiene la clave privada de firma de actualizaciones. No añadas claves privadas, tokens, archivos `.pem` o secretos al repositorio. La clave privada debe mantenerse en un secreto protegido de GitHub Actions.

## Validación pendiente

La detección Inno Setup ya mostró `Inno Setup validado: versión 6.7.1` en el registro aportado. Las pruebas completas y la compilación final Windows deben volver a ejecutarse en GitHub Actions después de subir este conjunto integrado. No se declara aquí una compilación Windows exitosa hasta recibir ese resultado.
