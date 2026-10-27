# Escritor Automático

**Aplicación de escritorio multiplataforma — Versión 1.0.0**

Escritor Automático es una aplicación de escritorio desarrollada en Python, acompañada de una extensión para navegador. El proyecto busca facilitar las tareas de escritura automatizada mediante una interfaz de escritorio y herramientas complementarias.

Este repositorio contiene el código fuente, los recursos necesarios para la distribución, la documentación del proyecto y los archivos utilizados para generar los instaladores.

## Características principales

- **Aplicación de escritorio:** interfaz para utilizar las funciones disponibles de Escritor Automático.
- **Extensión para navegador:** componente complementario para las funciones que requieren integración con el navegador.
- **Compatibilidad multiplataforma:** el proyecto contempla distribuciones para Windows y Linux x86_64.
- **Instaladores:** paquetes preparados para facilitar la instalación sin necesidad de configurar manualmente el entorno de desarrollo.
- **Código fuente en Python:** permite revisar, mantener y ampliar el proyecto.

> Las funciones específicas pueden variar según la versión de la aplicación y la extensión instalada.

## Para usuarios

### 1. Descargar la aplicación

Descarga los instaladores desde la sección de versiones del repositorio:

**[Ver versiones y descargas](../../releases)**

Selecciona el paquete correspondiente a tu sistema operativo.

| Sistema operativo | Paquete |
|---|---|
| Windows | Instalador de Windows (`Setup.exe`) |
| Linux x86_64 | Paquete de Linux publicado en la versión correspondiente |

Se recomienda utilizar los archivos adjuntos a una versión publicada, en lugar de descargar archivos sueltos del código fuente.

### 2. Instalación en Windows

1. Descarga el instalador de Windows desde la sección de versiones.
2. Ejecuta el archivo `Setup.exe`.
3. Sigue las instrucciones del asistente de instalación.
4. Abre Escritor Automático desde el acceso directo creado por el instalador, si está disponible.

Si Windows muestra una advertencia de seguridad, comprueba que el archivo proceda del repositorio oficial del proyecto antes de continuar.

### 3. Instalación en Linux

1. Descarga el paquete de Linux correspondiente a tu arquitectura.
2. Consulta las instrucciones específicas incluidas con la distribución.
3. Instala las dependencias adicionales si fueran necesarias.
4. Inicia la aplicación siguiendo las instrucciones de la documentación de Linux.

Consulta el archivo `LEEME_LINUX.txt` y, si necesitas preparar el entorno desde el código fuente, revisa `instalar_dependencias_linux.sh`.

### 4. Uso de la aplicación

Después de instalar Escritor Automático:

1. Abre la aplicación.
2. Familiarízate con la interfaz y las opciones disponibles.
3. Configura los parámetros que necesites para la tarea que deseas realizar.
4. Utiliza las funciones disponibles en la aplicación y, cuando corresponda, en la extensión para navegador.
5. Comprueba el resultado obtenido.

Si una función requiere la extensión del navegador u otro componente, asegúrate de que esté instalado y configurado correctamente.

### 5. Problemas frecuentes

- **La aplicación no inicia:** verifica que hayas descargado el paquete adecuado para tu sistema operativo.
- **Faltan dependencias en Linux:** consulta `LEEME_LINUX.txt` y la documentación de instalación.
- **La extensión no funciona:** comprueba su instalación, configuración y compatibilidad con el navegador.
- **El instalador presenta errores:** descarga nuevamente el archivo desde la versión publicada y consulta los registros disponibles.
- **El problema persiste:** abre un reporte de incidencia en el repositorio e incluye el sistema operativo, la versión utilizada y los pasos para reproducir el problema.

## Para desarrolladores

### Tecnologías utilizadas

| Tecnología | Propósito |
|---|---|
| Python | Desarrollo de la aplicación |
| Extensión de navegador | Integración con el navegador |
| PyInstaller | Generación de ejecutables y paquetes de distribución, según la configuración |
| Inno Setup | Creación del instalador para Windows |
| Git y GitHub | Control de versiones y alojamiento del proyecto |
| GitHub Actions | Automatización de los procesos de compilación y distribución |

La configuración concreta de las herramientas puede consultarse en los archivos del repositorio y en los flujos de trabajo de GitHub Actions.

### Estructura del proyecto

Los archivos principales se organizan de acuerdo con su función:

| Archivo o directorio | Propósito |
|---|---|
| Código fuente de la aplicación | Implementación de la aplicación de escritorio |
| Código de la extensión | Funcionalidad complementaria para el navegador |
| `.github/workflows/` | Flujos automatizados de compilación y publicación |
| `requirements-build.txt` | Dependencias relacionadas con la compilación |
| `requirements-linux-source.txt` | Dependencias para el entorno Linux desde código fuente |
| `preflight.py` | Comprobaciones previas relacionadas con el proceso de preparación o compilación |
| `preflight_linux.py` | Comprobaciones previas para Linux |
| `installer.iss` | Configuración del instalador de Windows, si está presente en la raíz |
| `INFORME_MULTIPLATAFORMA.md` | Documentación sobre la compatibilidad y distribución multiplataforma |
| `INFORME_SEGURIDAD.md` | Información relacionada con la seguridad del proyecto |
| `INFORME_CORRECCION_COMPILACION_v1.0.0.md` | Registro de correcciones relacionadas con la compilación de la versión 1.0.0 |
| `LEEME_LINUX.txt` | Instrucciones específicas para Linux |

Esta tabla describe los archivos conocidos del proyecto. Consulta el árbol actual del repositorio para identificar otros módulos, pruebas y componentes.

### Preparar el entorno de desarrollo

Para trabajar con el código fuente se recomienda disponer de:

- Una versión de Python compatible con el proyecto.
- Git.
- Un entorno virtual de Python.
- Las dependencias declaradas en los archivos de requisitos.
- Las herramientas de compilación correspondientes al sistema operativo, si se desea generar instaladores.

Un procedimiento general para preparar el entorno es:

```bash
git clone URL_DEL_REPOSITORIO
cd DIRECTORIO_DEL_PROYECTO

python -m venv .venv
```

En Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements-linux-source.txt
```

En Windows, desde Git Bash o una terminal compatible:

```bash
source .venv/Scripts/activate
python -m pip install -r requirements-build.txt
```

**Importante:** los archivos de requisitos pueden tener propósitos diferentes. Antes de instalar dependencias o ejecutar la aplicación, revisa cuál corresponde al entorno que deseas preparar. Estos comandos son una guía inicial y pueden necesitar ajustes según la estructura actual del código.

### Compilación y distribución

El proyecto dispone de flujos de GitHub Actions para automatizar la generación de paquetes de Windows y Linux.

Los archivos de configuración se encuentran en:

```text
.github/
└── workflows/
    └── build-installer.yml
```

Para modificar el proceso de compilación:

1. Revisa el flujo de trabajo correspondiente.
2. Comprueba las dependencias y los archivos incluidos en cada paquete.
3. Ejecuta las verificaciones disponibles.
4. Valida que los instaladores generados funcionen en el sistema operativo correspondiente.
5. Revisa los resultados de GitHub Actions antes de publicar una versión.

La publicación de una versión y la compilación de los instaladores son operaciones distintas. Que una compilación termine correctamente no garantiza por sí solo que se haya publicado una versión en GitHub Releases.

### Buenas prácticas de desarrollo

- Mantener el código fuente separado de los archivos generados durante la compilación.
- Documentar los cambios relevantes y las nuevas dependencias.
- Evitar incluir contraseñas, tokens, claves privadas o información sensible en el repositorio.
- Comprobar los cambios antes de crear una versión.
- Probar los paquetes generados antes de distribuirlos.
- Actualizar la documentación cuando cambien las funciones, los requisitos o los procedimientos de instalación.

## Documentación del proyecto

Los documentos complementarios deben consultarse según la necesidad:

| Documento | Cuándo consultarlo |
|---|---|
| `LEEME_LINUX.txt` | Instalación y uso en Linux |
| `INFORME_MULTIPLATAFORMA.md` | Compatibilidad y distribución para distintos sistemas operativos |
| `INFORME_SEGURIDAD.md` | Consideraciones de seguridad |
| `INFORME_CORRECCION_COMPILACION_v1.0.0.md` | Antecedentes de las correcciones de compilación |
| `OBTENER_SETUP_EN_NUBE.md` | Información sobre la obtención del instalador desde los procesos de compilación, si sigue vigente |
| `README.md` | Información general para usuarios y desarrolladores |

Los documentos internos que describan procedimientos temporales de mantenimiento deben mantenerse actualizados y no sustituir las instrucciones de uso destinadas a los usuarios finales.

## Reportar problemas y proponer mejoras

Si encuentras un error o deseas proponer una mejora:

1. Comprueba si el problema ya está reportado.
2. Describe el comportamiento observado y el esperado.
3. Indica la versión de Escritor Automático y el sistema operativo.
4. Incluye los pasos necesarios para reproducir el problema.
5. Evita adjuntar contraseñas, datos personales o información confidencial.

Puedes utilizar la sección de incidencias del repositorio para comunicar errores y sugerencias.

## Licencia

Consulta el archivo `LICENSE` incluido en el repositorio para conocer las condiciones de uso, modificación y distribución del proyecto.

## Versión

**Versión documentada:** `1.0.0`

Consulta la sección de versiones del repositorio para obtener los paquetes publicados y revisar las notas de cada versión.
