# Aplicar Escritor Automático v1.0.3 — diagnóstico de conexión

Esta actualización corrige el arranque del socket local (faltaba `listen()` después de `bind()`), añade controles en la aplicación y comprueba que la comunicación llega hasta el service worker de la extensión y regresa correctamente.

## Aplicar desde Git Bash

1. Actualiza `main` y crea una rama de pruebas:

   ```bash
   git checkout main
   git pull origin main
   git checkout -b beta/v1.0.3
   ```

2. Extrae el ZIP completo sobre la raíz del repositorio y permite reemplazar los archivos. No elimines ni reemplaces `.git`.
3. Revisa y confirma los cambios:

   ```bash
   git status
   git diff --check
   git diff
   git add .
   git commit -m "Add app-side extension connection diagnostics v1.0.3"
   git push -u origin beta/v1.0.3
   ```

4. Abre un Draft Pull Request hacia `main`. No publiques todavía la etiqueta `v1.0.3` ni una Release.

## Actualizar la extensión

La versión de la aplicación es **1.0.3** y la versión independiente de la extensión es **1.3.2**. En el navegador abre `chrome://extensions`, `edge://extensions` o `brave://extensions`; localiza la extensión, pulsa **Recargar** o vuelve a cargar sin empaquetar la carpeta `web_extension` de esta rama. Conserva solo una pestaña de conexión abierta.

## Probar la conexión desde la aplicación

1. Abre Escritor Automático v1.0.3 y selecciona el modo **Web**.
2. Si todavía no vinculaste la extensión, pulsa **Copiar código de vinculación** y pega el código en el popup de la extensión; pulsa Guardar.
3. En el popup, concede **Permitir acceso a páginas** y acepta los permisos que necesitas.
4. En la aplicación, pulsa **Conectar con extensión**. Esto inicia el servidor local y solicita abrir el panel de conexión.
5. En el panel del navegador pulsa **Conectar**. Si se solicita permiso para acceder a la red local, permítelo. Mantén abierta esa pestaña.
6. Al autenticarse, la aplicación ejecutará automáticamente una prueba de ida y vuelta. También puedes repetirla con **Probar conexión**.
7. El resultado correcto debe mostrar **Conexión verificada**, navegador, versión de la extensión y tiempo de respuesta en milisegundos.
8. Pulsa **Actualizar páginas**, selecciona un campo editable y realiza una escritura corta de prueba.

## Interpretar el resultado

- **No se pudo iniciar el servidor local:** revisa el mensaje de error; puede existir un problema con el puerto local 8765 o con la dependencia `websockets`. La aplicación ahora comprueba el arranque de un socket en escucha, no solo la reserva del puerto.
- **Servidor local activo, pero no hay una extensión autenticada:** el proceso Python sí está escuchando, pero el panel no se ha conectado o no completó la autenticación.
- **El canal se autenticó pero no respondió la prueba:** el WebSocket/HMAC llegó a establecerse, pero el mensaje no completó el recorrido por el service worker. Recarga la extensión, conserva una sola pestaña de conexión y prueba de nuevo.
- **Conexión verificada:** la ida y vuelta entre la aplicación, la página persistente de la extensión y el service worker funciona. Si después no aparecen páginas/campos, revisa los permisos de pestañas y sitios; es un problema distinto del enlace base.
- **Conexión interrumpida:** revisa que la pestaña de conexión siga abierta y que el navegador no la haya cerrado o descartado.

## Validación pendiente

Las pruebas automáticas validan sintaxis, el formato de los mensajes y la ruta del diagnóstico. La validación final requiere ejecutar la app y la extensión en Chrome, Edge o Brave reales, confirmar el estado **Conexión verificada**, detectar pestañas y realizar una escritura de prueba. No publiques la versión estable hasta completar ese recorrido.

No compartas el código de vinculación ni agregues claves privadas o secretos al repositorio.
