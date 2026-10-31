# Parche final de seguridad — Escritor Automático v1.0.2

## Cómo aplicarlo

Este ZIP es un parche de sustitución: contiene los archivos nuevos y modificados respecto al paquete `Escritor-Automatico-v1.0.2-parche-seguridad.zip` entregado anteriormente.

1. Haz una copia de seguridad de tu carpeta/repo actual.
2. Descomprime este ZIP en la raíz del repositorio, conservando la estructura de carpetas y permitiendo sobrescribir archivos.
3. Comprueba que `version.json` indique `1.0.2`.
4. Ejecuta en Git Bash: `git status --short` y revisa los cambios antes de hacer commit.
5. Sube los cambios a `beta/v1.0.2` y deja que GitHub Actions ejecute las pruebas y compilaciones.

También se entrega `Escritor-Automatico-v1.0.2-fuente-actualizada.zip`, que contiene el proyecto completo y evita tener que aplicar el parche sobre una copia previa.

## Clave de firma de actualizaciones

La Release requiere el secreto de GitHub Actions `UPDATE_SIGNING_PRIVATE_KEY_B64`. La clave privada NO forma parte del parche ni del proyecto. Usa la clave privada entregada por separado solo para crear ese secreto en Settings → Secrets and variables → Actions. No la guardes en el repositorio, no la incluyas en commits ni en Releases. La clave pública correspondiente sí está integrada en `update_security.py`.

## Cambios principales

- Autenticación mutua HMAC-SHA-256 entre el puente de la aplicación y la extensión, con nonces aleatorios por conexión y código de vinculación por usuario.
- Extensión sin permisos de páginas automáticos: el usuario debe autorizar el acceso desde su popup.
- Firma Ed25519 independiente del manifiesto SHA-256 de la Release; el actualizador rechaza manifiestos sin firma válida.
- Revalidación SHA-256 del instalador y del script Linux justo antes de ejecutarlos.
- Límites de tamaño/miembros en importación HTML y DOCX, parser CSS lineal limitado y XML endurecido.
- Límites globales de eventos/conexiones del puente, acciones de importación defensivas, redirecciones restringidas, caché y rutas de repositorio validadas.
- GitHub Actions con acciones fijadas por SHA, versiones de herramientas limitadas, `pip-audit`, SBOM y publicación sin sobrescritura de Releases existentes.
- Documentación de seguridad actualizada y pruebas negativas para autenticación, firma, redirecciones y extracción TAR.

## Verificación realizada en este entorno

- `python -m unittest discover -s tests -v`: 24 pruebas superadas.
- `python -m py_compile *.py tests/*.py tools/*.py`: correcto.
- `node --check` en `service_worker.js`, `content.js` y `popup.js`: correcto.
- `bash -n` en los scripts Linux: correcto.
- YAML del workflow interpretado correctamente.

No se ejecutó una compilación real de Inno Setup/Windows ni un empaquetado Linux de PyInstaller en GitHub Actions. Debes comprobar esos dos jobs antes de crear la etiqueta `v1.0.2`.
