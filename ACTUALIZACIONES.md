# Actualizaciones voluntarias

## v1.0.1 — Optimización de rendimiento

- Se optimizó el contador de caracteres y líneas del editor para evitar copiar todo el documento a Python en cada actualización.
- Se aumentó el intervalo de actualización del contador de 180 a 300 ms para reducir el trabajo repetitivo al escribir textos grandes.
- Se ajustó la compresión del instalador de Windows (`lzma2/fast` y `SolidCompression=no`) para priorizar la generación y extracción más ágiles frente al tamaño mínimo del instalador.
- Esta versión no garantiza resolver todos los tirones de la aplicación: los retrasos al abrir documentos, aplicar formato o ejecutar escritura automática pueden requerir optimizaciones adicionales.

## Primera publicación

La primera versión pública está definida como `1.0.0` en `version.json`. Tras publicar el código en `main`, comprueba que la compilación funciona y crea la etiqueta `v1.0.0` para generar la GitHub Release inicial. Las siguientes correcciones pueden publicarse como `1.0.1`, nuevas funciones compatibles como `1.1.0` y cambios incompatibles como `2.0.0`.

## Comportamiento para el usuario

- El programa busca la última GitHub Release en segundo plano al iniciar si la casilla **Comprobar actualizaciones automáticamente al iniciar** está marcada.
- También puede pulsar **Buscar actualizaciones** en cualquier momento.
- Si hay una versión más reciente, se muestran el número y las notas de lanzamiento.
- No se descarga ni instala nada hasta que el usuario pulsa **Descargar actualización**.
- Después de descargar, el programa compara el SHA-256 del paquete con `SHA256SUMS.txt` de la Release. Solo si coincide pregunta si debe ejecutar el instalador.
- En Windows se inicia el instalador Inno Setup por usuario. En Linux el actualizador prepara el paquete, cierra la aplicación y ejecuta el instalador del usuario tras esperar a que el proceso termine.
- El usuario puede desactivar comprobaciones automáticas o ignorar una versión. Siempre puede consultar manualmente.

## Publicar una actualización

1. Actualiza código, pruebas y la versión de `version.json` (ejemplo: `1.0.1`).
2. Actualiza los textos de documentación si corresponde.
3. Ejecuta las comprobaciones locales:

   ```bash
   python -m unittest discover -s tests -v
   python preflight.py
   ```

   `preflight.py` necesita los archivos de la extensión y las dependencias declaradas; algunas verificaciones adicionales dependen de Node.js.
4. Haz commit y push al repositorio.
5. Crea y publica una etiqueta que coincida con la versión:

   ```bash
   git tag v1.0.1
   git push origin v1.0.1
   ```

6. El workflow `.github/workflows/build-installer.yml` compilará Windows y Linux, calculará sus SHA-256 y publicará una GitHub Release con ambos instaladores y `SHA256SUMS.txt`.
7. Comprueba la ejecución en **Actions** y prueba ambos instaladores antes de anunciar la versión.

El workflow rellena `update_config.json` durante la compilación con el nombre real del repositorio (`OWNER/REPOSITORY`), así que no hace falta codificar el usuario de GitHub en el código fuente. Una compilación local con `repository` vacío podrá ejecutarse, pero el comprobador de actualizaciones indicará que no está configurado.

## Limitaciones de seguridad

- Se aceptan versiones estables semánticas `X.Y.Z`; las prereleases no se buscan por el endpoint `releases/latest`.
- Las descargas usan HTTPS, límites de tamaño, nombres y hosts permitidos, y validación SHA-256.
- El instalador se ejecuta solo tras confirmación explícita del usuario.
- La suma SHA-256 publicada en la misma Release detecta daños y errores de publicación, pero no equivale a una firma independiente. Para una distribución más sensible, se recomienda firmar el instalador de Windows y publicar hashes por un canal adicional.
- El actualizador Linux extrae únicamente directorios y archivos regulares y rechaza rutas fuera del directorio temporal, enlaces simbólicos y hard links.

## Primera actualización desde una versión anterior

Las versiones instaladas que no incluyen `updater.py` y la interfaz de actualización (por ejemplo, la distribución versión anterior sin actualizador) no pueden detectar ni instalar por sí mismas esta nueva función. Para habilitarla, el usuario debe instalar manualmente una vez la versión v1.0.0. Después de esa instalación, el programa podrá revisar las GitHub Releases futuras y siempre pedirá permiso antes de descargar y ejecutar una actualización.

## Preferencia del usuario

La comprobación automática está activada inicialmente, pero puede desactivarse desde la casilla de la ventana principal. La búsqueda manual sigue disponible con **Buscar actualizaciones**. Encontrar una versión nueva no instala nada: se requiere elegir **Descargar actualización** y después aprobar **Instalar ahora**.
