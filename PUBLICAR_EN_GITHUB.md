# Publicar este proyecto en GitHub como código abierto

## Antes de publicar

1. Abre `LICENSE` y sustituye `[Nombre del titular]` por tu nombre o el nombre del titular de los derechos.
2. Confirma que tienes derecho a publicar el código fuente y licenciar los archivos incluidos.
3. Revisa `INFORME_SEGURIDAD.md` y `web_extension/manifest.json`. La extensión tiene permisos amplios de páginas web, que deben explicarse a quienes la instalen.
4. No añadas claves privadas, tokens, contraseñas, documentos personales, logs ni ejecutables generados.

## Método con Git Bash

Este proyecto también puede publicarse sin GitHub Desktop. Extrae el ZIP, abre Git Bash en la carpeta y ejecuta `git init -b main`, `git add .`, `git status`, `git commit -m "Publicación inicial"`, añade el remoto con `git remote add origin https://github.com/USUARIO/escritor-automatico.git` y publica con `git push -u origin main`. Antes del push, revisa `git status` para no incluir información privada.

## Método recomendado: GitHub Desktop

1. Descarga e instala GitHub Desktop desde https://desktop.github.com/ e inicia sesión.
2. Extrae este proyecto en una carpeta permanente, por ejemplo `Documentos/EscritorAutomatico`.
3. En GitHub Desktop, selecciona **File → Add Local Repository** y elige esa carpeta. Si indica que no es un repositorio Git, selecciona la opción para crear un repositorio allí. No crees otro README si ya existe uno.
4. Revisa la pestaña **Changes** y confirma que aparecen `README.md`, `LICENSE`, `.gitignore`, `CONTRIBUTING.md`, `SECURITY.md` y el código fuente; que no aparecen archivos privados ni ejecutables compilados.
5. Escribe un mensaje de commit, por ejemplo `Publicar Escritor Automático v1.0.0`, y pulsa **Commit to main**.
6. Pulsa **Publish repository**. Usa como nombre `escritor-automatico`, añade una descripción y desmarca **Keep this code private** para que el repositorio sea público.
7. Visita el repositorio en GitHub y verifica que se vean el README y la licencia MIT. El código no se considera plenamente abierto solo por ser público; necesita una licencia y este paquete usa una plantilla MIT que debes completar antes de publicar.

## Método desde la web

1. En GitHub, pulsa **New repository** y usa el nombre `escritor-automatico`.
2. Elige **Public**. Como ya tienes los archivos, no inicialices otro README, `.gitignore` ni licencia en la página.
3. En el repositorio nuevo, utiliza **Add file → Upload files** y arrastra el contenido de esta carpeta. La carga web es apropiada para pocos archivos; para el proyecto completo, GitHub Desktop es más cómodo y evita límites de carga.
4. Escribe un mensaje de commit y pulsa **Commit changes**.
5. Revisa que la pestaña Actions muestre el flujo de compilación y ejecútalo con **Run workflow** si no se inició automáticamente.

## Qué no subir

No subas `dist/`, `build/`, instaladores `.exe`, paquetes `.zip` de distribución, credenciales, claves privadas ni logs locales. Los instaladores se generan como artefactos de GitHub Actions; para versiones permanentes, usa GitHub Releases y publica el SHA-256 correspondiente.

## Crear la primera versión pública 1.0.0

Después de subir el código y comprobar que Actions compila correctamente, verifica que `version.json` indique `1.0.0` y ejecuta desde Git Bash:

```bash
git tag v1.0.0
git push origin v1.0.0
```

El flujo de GitHub Actions debe terminar correctamente para publicar la Release con ambos paquetes y `SHA256SUMS.txt`.
