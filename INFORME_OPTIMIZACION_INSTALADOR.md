# Informe de optimización del instalador — Escritor Automático v18

## Cambios aplicados

1. **Corregido un archivo de instalación duplicado.** `POST_INSTALACION.txt` ya se copia al directorio empaquetado antes de compilar el Setup. La versión previa también lo declaraba como una segunda entrada en `[Files]`; ahora solo se recoge desde el directorio de PyInstaller.
2. **Preflight automático.** `preflight.py` verifica archivos requeridos, sintaxis del Python, JSON del manifiesto, Manifest V3, dependencias fijadas y coherencia del ID derivado de la clave pública de la extensión frente al ID esperado por Python.
3. **Comprobación opcional de JavaScript.** Si Node.js está instalado en la máquina de compilación, comprueba los tres archivos `.js`; si no está, informa que omitió esa comprobación sin bloquear a los usuarios que no usan Node.
4. **Entorno limpio.** Cada compilación elimina solo carpetas generadas por el proceso (`.build_venv`, `build`, `dist` y `dist-installer`) y crea un entorno virtual limpio, para no reutilizar dependencias o artefactos viejos.
5. **Herramientas fijadas.** Las dependencias de compilación se enumeran en `requirements-build.txt`. Se usa `--no-deps` para evitar resolución transitiva no controlada, junto con `pip check` para revisar requisitos declarados.
6. **Solo wheels binarios.** Se conserva `--only-binary=:all:` para evitar compilar paquetes fuente durante la preparación.
7. **Paquete más selectivo.** Se cambia la recolección de `python-docx` de `--collect-all` a `--collect-data`, manteniendo Pillow con recolección amplia por su carga dinámica de complementos.
8. **Detección de Inno Setup mejorada.** Busca `ISCC.exe` en PATH y en las ubicaciones habituales de Inno Setup 6 y 7.
9. **Protección contra resultados obsoletos.** Limpia las salidas previas y comprueba que el EXE, la extensión y el manifiesto existan antes de crear el Setup.
10. **Instalación y actualización más claras.** El Setup mantiene la instalación por usuario sin elevación, conserva el directorio previo durante las actualizaciones, intenta cerrar la aplicación durante una actualización y ofrece la opción de abrir el programa al terminar.
11. **Diagnóstico y comprobación de integridad.** Guarda la salida completa en `BUILD_INSTALADOR.log`, genera `build-environment.txt` y el hash SHA-256 del Setup final.
12. **Instrucciones de extensión/desinstalación.** La guía indica que la extensión se instala manualmente y que conviene retirarla del navegador antes de eliminar su carpeta instalada.

## Validaciones ejecutadas aquí

- Sintaxis del archivo Python principal y del script de preflight.
- JSON válido y Manifest V3.
- ID derivado de la clave pública: `gokleoeeegcjpahldnbmepeeokjafodl`, coincidente con el ID usado en Python.
- Sintaxis de `content.js`, `popup.js` y `service_worker.js` con Node.js.
- Presencia de los archivos requeridos.
- Ausencia de la entrada duplicada `POST_INSTALACION.txt` en `installer.iss`.
- Integridad del ZIP de entrega.

## Lo que aún requiere Windows

No se pudo ejecutar PyInstaller, `ISCC.exe`, el instalador resultante ni su desinstalador en esta máquina. Por eso no se afirma que el `Setup.exe` haya sido compilado o probado. Antes de distribuirlo, hay que compilarlo en Windows 10/11 x64 y hacer una instalación de prueba, comprobar el acceso desde Inicio, cargar la extensión manualmente en un navegador y desinstalarlo.

## Cadena de suministro

Se fijan las versiones, pero no se incluyen hashes para cada wheel. El hash SHA-256 que genera el script cubre el `Setup.exe` producido, no prueba por sí solo el origen de los paquetes que se descargaron durante la compilación. Una mejora de seguridad posterior sería un lockfile de todos los artefactos para Windows x64/Python 3.12 con hashes SHA-256 verificados por versión.


## Extensión multiplataforma v1.0.0 (24-10-2026)

La aplicación ahora detecta el sistema operativo, cambia su backend de teclado en Windows/Linux y presenta los modos adecuados en la interfaz. Se permite el puente WebSocket local en ambos sistemas. Se añadió una dependencia fijada de `pynput==1.8.2` solo para Linux y un flujo de compilación Linux independiente. La automatización COM de Word, el portapapeles HTML Win32 y los mensajes Win32 en segundo plano continúan siendo exclusivos de Windows. La escritura con `pynput` se limita por el sistema gráfico y Wayland puede bloquear parte de la entrada global.
