# Informe técnico — corrección de conexión v1.0.3

## Hallazgo

En la fuente v1.0.2 revisada, `web_extension/service_worker.js` abría automáticamente `ws://127.0.0.1:8765` desde el service worker de Manifest V3. Las versiones recientes de Chromium aplican controles de acceso a redes locales y de bucle invertido a conexiones WebSocket. La guía actual de Chrome advierte que la primera solicitud que requiera permiso no debe iniciarse desde un Service Worker, porque no tiene un documento asociado para presentar la solicitud al usuario.

## Cambio

- El WebSocket ahora se abre desde `web_extension/connection.html` y `connection.js`, una página de la extensión que el usuario abre desde el popup y activa con el botón «Conectar».
- El service worker se conserva como ejecutor de comandos de pestañas/contenido; intercambia mensajes con la página de conexión mediante `chrome.runtime`.
- Se conserva el protocolo de autenticación HMAC-SHA256 de doble sentido, los nonces aleatorios y el origen fijo `chrome-extension://gokleoeeegcjpahldnbmepeeokjafodl`.
- La interfaz informa que la página de conexión debe mantenerse abierta mientras se use la escritura web.
- El preflight comprueba que el WebSocket ya no se cree desde el service worker y valida la sintaxis de los archivos JS cuando Node.js está disponible.

## Validación pendiente en navegador real

Las pruebas automatizadas no pueden confirmar por sí solas la solicitud de permiso Local Network Access, el comportamiento de la conexión WebSocket en Chrome/Edge/Brave, ni la interacción con las páginas del usuario. Debe validarse en al menos un navegador Chromium actualizado y, si se soporta, en los otros navegadores objetivo.
