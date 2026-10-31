# Corrección del fallo Ed25519 en GitHub Actions para Windows (v1.0.2)

## Causa

El trabajo de Windows ejecutaba `unittest` antes de instalar las dependencias de `requirements.txt`.
La función `verify_release_manifest()` importa `cryptography` de forma diferida y devuelve `False`
si esa dependencia no está disponible. Por eso la prueba de firma válida fallaba con `AssertionError:
False is not true`, aunque la clave pública y el vector de prueba fueran correctos.

El trabajo de Linux pasaba porque el entorno del runner ya tenía disponible `cryptography`; no era
una dependencia garantizada por el paso de pruebas. El resultado dependía accidentalmente de lo
preinstalado en cada runner.

## Corrección

El workflow instala explícitamente `cryptography==50.0.2` (la misma versión fijada en
`requirements.txt`) antes de ejecutar las pruebas de Windows y comprueba que la API Ed25519 esté
importable. La instalación utiliza wheels y no compila código nativo desde un sdist.

No se modifica la clave pública, la clave privada, la firma de prueba ni el protocolo Ed25519.

## Aplicación en la rama beta/v1.0.2

1. Extraer este ZIP en la raíz del repositorio, conservando la estructura de carpetas.
2. Confirmar que se actualizó `.github/workflows/build-installer.yml`.
3. En Git Bash ejecutar:

   ```bash
   git status
   git diff --check
   git diff -- .github/workflows/build-installer.yml
   git add .github/workflows/build-installer.yml LEEME_CORRECCION_FALLO_ED25519_WINDOWS.md
   git commit -m "Fix Ed25519 test dependency on Windows runner"
   git push origin beta/v1.0.2
   ```

4. Revisar la nueva ejecución de GitHub Actions. El Pull Request debe permanecer en Draft.

## Validación local en este entorno

Se ejecutó la suite disponible con Python local: 24 pruebas superadas. También se comprobó la
sintaxis del workflow YAML. La compilación real de Windows debe confirmarse en GitHub Actions.
