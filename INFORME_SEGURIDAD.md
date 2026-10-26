INFORME DE REVISIÓN DE SEGURIDAD — ESCRITOR AUTOMÁTICO v18
Fecha de revisión: 22 de octubre de 2026
Alcance: código fuente local de v17 y cambios aplicados en v18, scripts BAT, requirements.txt y extensión Manifest V3.

RESUMEN EJECUTIVO
Se revisaron las dependencias, el servidor WebSocket local, validación de mensajes, tratamiento de capturas de imagen y permisos de la extensión. No se encontró código explícito para descargar o ejecutar programas externos, ni uso de eval(), exec() de Python, subprocess u os.system en el código inspeccionado. La extensión sí usa document.execCommand("insertText"/"insertParagraph") como mecanismo de edición de texto, no para ejecutar código. Esto no equivale a una certificación ni garantiza ausencia de vulnerabilidades.

CAMBIOS APLICADOS EN V18
1. Dependencias de la aplicación fijadas: python-docx==1.2.0; lxml==6.1.3; typing_extensions==4.16.0; websockets==17.3; Pillow==13.0.0; pywin32==312 (solo Windows). El instalador también fija pip==26.2.2, publicado el 20-10-2026 con Trusted Publishing habilitado.
2. Instalación aislada en .venv, no en el Python global.
3. Límite de 6 MiB para textos enviados al modo web.
4. Instalación desde wheels para las dependencias habituales. Excepción controlada solo en Linux: `evdev==1.9.3` se construye desde el sdist oficial fijado con SHA-256, usando herramientas nativas de compilación en el runner de CI.
5. Python mínimo 3.11. Pillow 13 dejó de soportar Python 3.10 y websockets 17 requiere Python moderno; el instalador valida la versión.
6. Puente WebSocket: sigue enlazado a 127.0.0.1 y valida el origen exacto chrome-extension://gokleoeeegcjpahldnbmepeeokjafodl. Ahora rechaza tipos de mensajes no permitidos y estructuras/campos de tamaño excesivo; limita la frecuencia, tamaño y cola, y desactiva compresión.
7. Vista previa: acepta solo data:image/jpeg;base64, valida base64, limita tamaño y número de píxeles, comprueba formato e integridad antes de decodificar.
8. Extensión: valida comandos entrantes y límite de 6 MiB para texto; CSP explícita de Manifest V3. Se conserva la clave pública del manifest y el ID de extensión coincide con el configurado en Python.

RIESGOS Y LIMITACIONES RESTANTES
- La extensión pide permisos tabs, scripting, webNavigation y acceso de host a todas las URLs HTTP/HTTPS, además de insertar content.js en todos los frames HTTP/HTTPS. Es un permiso amplio y le da capacidad de inspeccionar metadatos de pestañas y detectar campos en muchas páginas. Se mantiene para no romper la función de búsqueda automática en todas las pestañas. Una futura opción de permisos por sitio reduciría privilegios, a costa de cambiar el flujo actual.
- El puente se defiende frente a páginas web comunes comprobando Origin y usando loopback, pero Origin no es autenticación criptográfica contra un proceso local malicioso que pueda conectarse y falsificar cabeceras; tampoco protege frente a malware que ya corre bajo la misma cuenta de Windows. Para un modelo de amenazas más fuerte convendría migrar a Native Messaging o a un canal con autenticación de sesión.
- Los paquetes tienen versiones fijadas (incluido pip==26.2.2), pero los wheels no están fijados por SHA-256. Para reproducibilidad/supply-chain más estricta se necesita un lockfile con hashes de cada wheel/plataforma y todas las dependencias transitivas; los hashes deben obtenerse y verificarse de PyPI y la instalación debe usar --require-hashes. La documentación oficial de pip recomienda combinar hash-checking y --only-binary=:all:.
- En los metadatos de PyPI consultados, python-docx 1.2.0, lxml 6.1.3 y pywin32 312 no muestran procedencia verificable (Trusted Publishing / attestation). Eso no demuestra que sean maliciosos, pero impide verificar de forma independiente el origen del artefacto publicado. Pillow, websockets y typing_extensions sí muestran mejor información de publicación en sus páginas de proyecto. Conviene considerar este límite antes de usar la aplicación en equipos con información sensible.
- No se probó el programa dentro de una máquina Windows real, ni con sesiones reales de Brave/Chrome/Edge/Word/Google Docs. Las pruebas de sintaxis y estructuras no equivalen a pentesting dinámico.
- El texto introducido se transmite desde la aplicación al destino que el usuario elige. El contenido preexistente no se envía al programa Python ni a servidores remotos; sin embargo, el content script puede leer localmente el valor de un input para insertar en el cursor y preservar el resto del valor. La extensión recorre metadatos de las páginas abiertas para detectar objetivos. La vista previa, cuando el usuario la solicita, envía una captura de la pestaña al programa local.

DEPENDENCIAS Y MOTIVO DE ACTUALIZACIÓN
- Pillow: el requisito previo era >=10.0 y admitía versiones antiguas. Pillow 13.0.0 se publicó el 16-10-2026 e incluye correcciones de numerosas vulnerabilidades de severidad crítica/alta y otras; se fijó esa versión. Fuentes: https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html y https://github.com/python-pillow/Pillow/security/advisories
- websockets: el requisito previo era >=14,<17, que excluía la versión 17.3 publicada el 19-10-2026. El proyecto declara que solo la versión más reciente recibe actualizaciones de seguridad. Se fija 17.3. Fuentes: https://pypi.org/project/websockets/ y https://github.com/python-websockets/websockets/security
- python-docx: fijado en 1.2.0, versión estable publicada el 16-06-2025; se utiliza para importar/exportar .docx. Fuente: https://pypi.org/project/python-docx/
- lxml: fijado en 6.1.3, versión estable publicada el 02-09-2026. Fuente: https://pypi.org/project/lxml/
- typing_extensions: fijado en 4.16.0. Fuente: https://pypi.org/project/typing-extensions/
- pywin32: fijado en 312; solo se instala en Windows y sirve para automatización COM con Word. En PyPI, los archivos publicados no muestran Trusted Publishing/procedencia verificada. Fuente: https://pypi.org/project/pywin32/312/
- pip: el instalador usa pip==26.2.2 para evitar seguir una versión arbitraria en cada instalación; PyPI indica que ese lanzamiento sí cuenta con procedencia verificada. Fuente: https://pypi.org/project/pip/26.2.2/

VALIDACIONES REALIZADAS EN ESTE ENTORNO
- Sintaxis Python validada con py_compile.
- Sintaxis JavaScript validada con Node.js 22 mediante node --check para content.js, popup.js y service_worker.js.
- JSON del manifest.json validado; se comprobó que existe la clave pública y que el ID derivado corresponde al ID configurado en Python.
- Inspección estática de scripts BAT y búsqueda de patrones como subprocess, Popen, os.system, shell=True, eval(), exec(), pickle.loads y peticiones HTTP desde la aplicación; no aparecieron usos de esos patrones en el código inspeccionado.
- Se ejecutaron pruebas ligeras de validadores del puente para tipos de mensaje, campos con tamaños excesivos, datos de imagen y límites de estructura.
- La comprobación de sintaxis no equivale a instalar las dependencias en Windows. No se ejecutó pip-audit sobre un entorno instalado ni una prueba dinámica/pentest de la aplicación en Windows o Brave; debe hacerse antes de considerar el programa validado para producción.

RECOMENDACIONES PARA EL USUARIO
- Instala solo desde este ZIP y no cambies scripts ni archivos de extensión por archivos de terceros.
- Ejecuta instalar_dependencias.bat y luego iniciar.bat. No instales la extensión en perfiles que contienen sesiones muy sensibles si no necesitas que examine sus pestañas.
- Revisa los permisos en brave://extensions/, chrome://extensions/ o edge://extensions/.
- Mantén Windows, el navegador y Python actualizados.
- Para una auditoría de producción, instala la aplicación en un entorno de prueba, ejecuta pip-audit/dependency scanning, pruebas dinámicas del puente y pruebas con documentos/capturas manipulados.


## Consideraciones multiplataforma v1.0.0

En Linux se usa `pynput` versión 1.8.2 sin solicitar elevación de privilegios. La compatibilidad depende de X11/Xorg o de las restricciones del entorno Wayland/XWayland. No se recomienda ejecutar la aplicación como root para superar restricciones de entrada del escritorio. La extensión y su puente local mantienen el alcance y los límites de seguridad documentados previamente.


Excepción de compilación Linux: `evdev==1.9.3` solo se distribuye en PyPI como archivo fuente. El workflow valida su SHA-256 (hash obtenido de la página de la release en PyPI) antes de compilarlo; el resto de dependencias sigue limitado a wheels. Las compilaciones reales deben revisarse en los registros de Actions.
