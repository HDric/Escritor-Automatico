# Aplicar Escritor Automático v1.0.3 — corrección del puente web

Esta actualización corrige la arquitectura de conexión entre la aplicación y la extensión del navegador.

## Recomendación

Usa el ZIP de proyecto completo para que los archivos de la aplicación, la extensión, las pruebas y los flujos de compilación queden en la misma versión. El ZIP de parche contiene únicamente los archivos nuevos o modificados.

## Aplicar desde Git Bash

1. Actualiza tu copia local de `main`:

   ```bash
   git checkout main
   git pull origin main
   git checkout -b beta/v1.0.3
   ```

2. Extrae el ZIP del proyecto completo sobre la carpeta del repositorio y permite reemplazar archivos. No borres ni reemplaces `.git`. Si aplicas el ZIP de parche, extrae igualmente sobre la raíz del repositorio.
3. Revisa los cambios:

   ```bash
   git status
   git diff --check
   git diff
   ```

4. Ejecuta las pruebas en GitHub Actions mediante un Pull Request Draft desde `beta/v1.0.3` hacia `main`. No crees todavía la etiqueta `v1.0.3` ni publiques una Release.
5. Comprueba los jobs de Windows y Linux. Después instala la compilación en un equipo de prueba y valida el enlace con Chrome, Edge o Brave.

## Cambio de uso de la extensión

1. Abre Escritor Automático y pulsa «Copiar código de vinculación».
2. En el popup de la extensión, pega el código y pulsa «Guardar código y vincular».
3. Concede «Permitir acceso a páginas» y acepta los permisos solicitados.
4. Pulsa «Abrir panel de conexión» en el popup.
5. En la pestaña nueva, pulsa «Conectar». Si aparece un aviso del navegador para acceder a aplicaciones o dispositivos locales, permite la conexión.
6. Mantén abierta la pestaña de conexión mientras utilices el modo web. Después vuelve a Escritor Automático y pulsa «Actualizar páginas».

Si la pestaña de conexión se cierra, la aplicación pierde el enlace. Abre nuevamente el panel y pulsa «Conectar».

## Validación pendiente

Las pruebas automatizadas verifican sintaxis, estructura de mensajes y autenticación HMAC; no sustituyen una prueba en Chrome/Edge/Brave real. No publiques la versión estable hasta comprobar que el panel autentica la extensión, que aparecen las pestañas y campos editables y que una escritura de prueba funciona.

No compartas el código de vinculación ni agregues claves privadas o secretos al repositorio.
