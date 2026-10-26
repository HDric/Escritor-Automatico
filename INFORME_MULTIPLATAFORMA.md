# Escritor Automático v1.0.0 — detección Windows/Linux

## Qué cambia

- Detecta el sistema con `platform.system()` y `sys.platform`.
- Muestra en la cabecera la plataforma detectada; en Linux también identifica distribución y tipo de sesión gráfica cuando están disponibles.
- Usa `WindowsKeyboard` en Windows y un backend `pynput` en Linux.
- Permite el puente WebSocket local de la extensión en Windows y Linux; el identificador de extensión se mantiene igual.
- En Linux, la interfaz limita los modos a escritura en ventana activa y página web, y desactiva la importación de HTML enriquecido desde el portapapeles Win32.
- Conserva como exclusivos de Windows la automatización de Word mediante COM, el portapapeles HTML Win32 y los mensajes de teclado Win32 en segundo plano.
- GitHub Actions compila dos artefactos en entornos separados: `EscritorAutomatico-Setup-v1.0.0.exe` y `EscritorAutomatico-v1.0.0-linux-x86_64.tar.gz`.
- El paquete Linux usa PyInstaller en Ubuntu 24.04 x86_64, contiene el intérprete y las dependencias, y añade un instalador/desinstalador por usuario. No requiere Python instalado en el equipo final.

## Compatibilidad de teclado en Linux

La dependencia `pynput==1.8.2` se instala solamente en Linux. Se recomienda X11/Xorg. Wayland puede limitar la inyección de eventos de teclado, especialmente en aplicaciones nativas; el funcionamiento con XWayland es parcial. No se debe ejecutar la aplicación como root para eludir estas restricciones.

## Pruebas realizadas en este entorno

- Compilación sintáctica de `escritor_automatico.py`, `preflight.py` y `preflight_linux.py`.
- Ejecución exitosa de `preflight.py` y `preflight_linux.py`.
- Comprobación de sintaxis JavaScript de los 3 archivos `.js` de la extensión mediante Node.js.
- Validación del manifiesto y del ID de extensión `gokleoeeegcjpahldnbmepeeokjafodl`.
- Parseo YAML del flujo de GitHub Actions; se reconocieron los trabajos Windows y Linux.
- Prueba controlada con un teclado simulado de las funciones de escritura de carácter, Enter, Tab y conversión de tabulaciones a espacios.
- Prueba del script de instalación/desinstalación Linux con una aplicación simulada y un directorio `$HOME` temporal, sin permisos de administrador.

## Pruebas pendientes

- Todavía no se ha ejecutado el flujo remoto de GitHub Actions; por tanto, no se ha generado aquí un `Setup.exe` ni el tar.gz Linux compilado.
- No se ha probado la inyección real de teclas en un escritorio X11/Xorg o Wayland.
- El artefacto Linux se construye en Ubuntu 24.04 para x86_64. No debe asumirse compatibilidad con todas las distribuciones, arquitecturas o versiones de glibc sin probarlo.
- Antes de distribuir, probar en Windows real y en la distribución Linux objetivo, incluyendo instalación, inicio, modo web, Google Docs y desinstalación.

## Referencias técnicas

- PyInstaller indica que no es un compilador cruzado; se compila en el sistema operativo de destino: https://pyinstaller.org/en/stable/
- `pynput` documenta sus requisitos para Linux y las limitaciones con X11/uinput y Wayland/XWayland: https://pynput.readthedocs.io/en/latest/limitations.html


Corrección de compilación v1.0.0: se añadió `requirements-linux-source.txt` con evdev 1.9.3 y su SHA-256 oficial de PyPI. La compilación Linux construye esa dependencia desde fuente usando `build-essential` y las cabeceras de Python, antes de instalar el resto de dependencias exclusivamente desde wheels. Los argumentos `--add-data` de PyInstaller ahora usan rutas absolutas de entrada para que sigan encontrándose aunque el archivo `.spec` se genere en `build/spec` o `build/spec-linux`.
