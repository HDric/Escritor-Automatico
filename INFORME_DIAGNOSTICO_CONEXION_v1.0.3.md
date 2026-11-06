# Diagnóstico de conexión — Escritor Automático v1.0.3

## Objetivo

Añadir en la aplicación de escritorio controles para iniciar el servidor local y verificar de extremo a extremo la comunicación con la extensión del navegador.

## Cambios

- Corrección de la causa principal encontrada en la prueba de socket: después de `bind()` ahora se llama a `listen()` antes de pasar el socket a `websockets.sync.server.serve(sock=...)`. Antes, el programa podía marcar el puente como iniciado aunque el kernel rechazara conexiones entrantes.
- Botón **Conectar con extensión**: inicia el servidor WebSocket local y solicita abrir el panel persistente de la extensión. La conexión final sigue requiriendo el clic explícito en **Conectar** del navegador, conforme al modelo de permisos de Chromium.
- Botón **Probar conexión**: envía un identificador aleatorio de diagnóstico a la extensión.
- El service worker responde con `diagnostic_pong` a través de la página persistente de conexión.
- La aplicación valida el identificador y muestra la respuesta medida en milisegundos.
- Si no llega respuesta en seis segundos, la aplicación informa que el canal o la autenticación puede estar activo, pero que el componente de extensión no completó el recorrido.
- Se incrementó la versión independiente de la extensión en `web_extension/manifest.json` de 1.3.1 a 1.3.2; la aplicación permanece en 1.0.3.

## Qué demuestra la prueba

Una respuesta válida confirma el recorrido: aplicación → WebSocket → página de conexión de la extensión → service worker → página de conexión → WebSocket → aplicación. No confirma que todos los sitios web permitan inyección de scripts ni que todos los campos sean editables; eso se valida por separado al actualizar las páginas.

## Validación

Las pruebas automatizadas verifican el socket TCP/WebSocket real en loopback, el origen de extensión, la autenticación HMAC, la forma y límites de `diagnostic_pong` y la estructura del recorrido entre service worker y aplicación. La prueba real del navegador sigue siendo necesaria en Chrome, Edge o Brave, con la extensión cargada, código de vinculación guardado y panel de conexión abierto.
