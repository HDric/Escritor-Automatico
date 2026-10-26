# Escritor Automático

**Versión inicial pública: 1.0.0**. Las futuras versiones seguirán el esquema semántico `X.Y.Z`.

Aplicación de escritorio multiplataforma para escribir texto de forma progresiva en aplicaciones y páginas web. Detecta si se ejecuta en Windows o Linux y habilita las funciones disponibles en ese sistema.

> **Estado del proyecto:** primera versión pública. Antes de usarlo con documentos importantes, revisa los permisos de la extensión y prueba la aplicación en un entorno controlado. La compatibilidad con Google Docs y con sesiones Linux bajo Wayland puede ser limitada.

## Funciones

- Editor de texto con opciones de formato básico.
- Importación de documentos DOCX, HTML y TXT y exportación HTML.
- Escritura progresiva con velocidad configurable, cuenta regresiva, pausa y detención.
- Detección del sistema operativo Windows o Linux.
- Extensión de navegador para Brave, Chrome y Edge que detecta pestañas y campos web compatibles.
- Vista previa de páginas y campos detectados.
- Flujos de GitHub Actions para compilar paquetes de Windows x64 y Linux x86_64.
- Comprobación opcional de nuevas versiones mediante GitHub Releases, con descarga y SHA-256 verificado antes de ofrecer la instalación.

Algunas funciones son específicas del sistema: automatización COM de Microsoft Word y escritura Win32 en segundo plano solo funcionan en Windows. En Linux, la escritura mediante teclado depende del entorno de escritorio; X11/Xorg suele ofrecer mejor compatibilidad que Wayland.

## Descargas compiladas

Este repositorio contiene el código fuente y la configuración de compilación. Los instaladores no están versionados dentro del repositorio. Para generarlos:

1. Abre la pestaña **Actions** del repositorio en GitHub.
2. Selecciona **Construir paquetes Windows y Linux de Escritor Automático**.
3. Pulsa **Run workflow** y espera a que termine correctamente.
4. Descarga los artefactos `escritorio-automatico-windows-x64` y `escritorio-automatico-linux-x86_64` desde la ejecución.

Los artefactos del flujo tienen retención limitada. Para publicar una versión que detecte el actualizador:

1. Cambia el número de versión en `version.json` usando el formato `X.Y.Z` (por ejemplo, `1.0.1`).
2. Haz commit y push de los cambios.
3. Crea una etiqueta que coincida exactamente con ese número y publícala:

   ```bash
   git tag v1.0.1
   git push origin v1.0.1
   ```

4. GitHub Actions compilará ambos paquetes y publicará una GitHub Release con los instaladores y `SHA256SUMS.txt`.

No basta con hacer push a `main`: el actualizador consulta la última **Release publicada**, no las compilaciones de prueba. La etiqueta debe coincidir con `version.json`.

## Requisitos para desarrollo

- Python 3.12 recomendado para la compilación automatizada.
- Windows: Inno Setup para compilar el instalador localmente.
- Linux: entorno gráfico compatible. X11/Xorg es el entorno recomendado para la escritura mediante teclado; Wayland puede restringir la entrada global.
- Navegador Chromium compatible (Brave, Chrome o Edge) para usar la extensión.

Las dependencias de la aplicación están en `requirements.txt`; las herramientas de construcción están en `requirements-build.txt`.

## Ejecutar desde el código fuente

### Windows

1. Instala una versión compatible de Python.
2. Crea y activa un entorno virtual:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --only-binary=:all: -r requirements.txt
   python escritor_automatico.py
   ```

   Para compilar el instalador utiliza `CREAR_INSTALADOR.bat` y consulta `LEEME_INSTALADOR.txt`.

### Linux

1. Instala Python, Tkinter y herramientas de entorno virtual desde el gestor de paquetes de tu distribución.
2. Crea un entorno virtual e instala dependencias:

   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install --only-binary=:all: -r requirements.txt
   python escritor_automatico.py
   ```

   Si tu distribución no incluye Tkinter o las bibliotecas de entrada, instálalas con el gestor de paquetes del sistema. Consulta `LEEME_LINUX.txt`.

## Instalar la extensión

1. Extrae o conserva la carpeta `web_extension`.
2. Abre la página de extensiones del navegador:
   - Brave: `brave://extensions/`
   - Chrome: `chrome://extensions/`
   - Edge: `edge://extensions/`
3. Activa el **Modo de desarrollador** y pulsa **Cargar descomprimida**.
4. Selecciona la carpeta `web_extension`.
5. Ejecuta la aplicación de escritorio y comprueba que el puente web se conecte.

La extensión solicita permisos de acceso a páginas HTTP/HTTPS para detectar campos editables y sincronizar pestañas. Estos permisos son amplios: instala la extensión solo si confías en el código y desactívala cuando no la necesites. No escribas contraseñas ni datos sensibles con la automatización activa.

## Seguridad y privacidad

- El puente local de la aplicación está diseñado para escuchar en `127.0.0.1`; no debe exponerse a una red pública.
- El actualizador consulta únicamente el repositorio configurado en `update_config.json`, utiliza HTTPS y exige `SHA256SUMS.txt`. No instala automáticamente: el usuario debe iniciar la descarga y volver a confirmar la ejecución del instalador.
- La opción **Comprobar actualizaciones automáticamente al iniciar** puede desactivarse desde la interfaz. Las preferencias se guardan en el perfil del usuario, fuera de la carpeta de instalación.
- SHA-256 detecta corrupción o discrepancias, pero no sustituye una firma de código ni protege frente a una cuenta de publicación comprometida. Revisa el código y protege la cuenta/repositorio de GitHub.
- La extensión requiere permisos amplios de navegador para su función de detección. Revisa `web_extension/manifest.json` antes de instalarla.
- No se deben subir tokens, contraseñas, claves privadas, archivos `.env`, datos personales, documentos de usuarios, logs locales ni ejecutables generados.
- Lee `INFORME_SEGURIDAD.md` antes de usar o modificar el programa. El informe documenta limitaciones y comprobaciones pendientes; no es una certificación de seguridad.
- Para comunicar una vulnerabilidad, usa la opción **Report a vulnerability** de la pestaña **Security** del repositorio, si está habilitada, y no publiques detalles explotables en una incidencia pública.

## Licencia

Este proyecto incluye una plantilla de licencia MIT en `LICENSE`. **Antes de publicar**, reemplaza `[Nombre del titular]` por el nombre del titular de los derechos y confirma que tienes derecho a licenciar todos los archivos incluidos. Revisa también las licencias de las dependencias de terceros.

## Contribuciones

Las contribuciones pueden proponerse mediante issues y pull requests. Incluye pasos para reproducir errores, sistema operativo, versión de Python y registros redactados para no exponer datos privados.
