# Informe de seguridad — Escritor Automático v1.0.2

**Alcance:** revisión estática del código y pruebas automatizadas del repositorio. No equivale a una certificación, auditoría externa, pentest ni validación de los instaladores compilados en Windows y Linux.

## Controles incorporados en esta versión

### Puente local y extensión Chromium

- El servidor WebSocket escucha únicamente en `127.0.0.1:8765` y conserva la validación del origen de la extensión.
- Antes de procesar mensajes, la extensión y la aplicación realizan un intercambio HMAC-SHA-256 con nonces aleatorios de 256 bits en ambas direcciones. Se rechazan conexiones que no demuestren conocer el código de vinculación.
- El código de vinculación se genera aleatoriamente, se conserva en la configuración del usuario y en sistemas POSIX se escribe con permisos `0600` dentro de un directorio `0700`.
- Solo se mantiene un cliente autenticado y se limitan los intentos de autenticación simultáneos.
- La cola de eventos limita simultáneamente el número de elementos, el tamaño máximo por evento y el presupuesto de memoria encolada. Se aplica límite de tamaño, estructura y frecuencia a los mensajes entrantes.
- La extensión ya no declara acceso a todas las páginas como permiso obligatorio. Los permisos `tabs`, `scripting`, `webNavigation` y los orígenes HTTP/HTTPS se solicitan mediante una acción explícita del usuario.
- Las URLs enviadas en la lista de pestañas y en la previsualización eliminan consulta y fragmento. Se muestran metadatos de pestaña y campos compatibles; no se lee el valor que el usuario ya haya escrito en esos campos.
- La previsualización de pantalla requiere confirmación desde la aplicación. La escritura web también solicita confirmación con el dominio y el campo destino.

**Limitación:** este puente sigue usando WebSocket en loopback, no Native Messaging. Un proceso malicioso ejecutado bajo la misma cuenta podría intentar leer el código de vinculación de la configuración de usuario o del perfil de extensión, manipular el navegador o interferir con la aplicación. No compartas el código de vinculación y no ejecutes el programa con privilegios elevados. Para separar mejor los límites de confianza, Native Messaging sigue siendo la evolución recomendada.

### Actualizador y publicaciones

- Las descargas usan HTTPS y un manejador que valida el esquema y el host de cada redirección antes de seguirla.
- Se validan el repositorio, la etiqueta, los nombres y las rutas de descarga de los artefactos para exigir los enlaces de la Release esperada.
- La lista `SHA256SUMS.txt` debe venir acompañada de `SHA256SUMS.txt.sig`. La firma Ed25519 se verifica con una clave pública integrada en la aplicación, independiente del contenido publicado en la Release.
- El actualizador verifica el SHA-256 del instalador descargado. Vuelve a comprobar el paquete inmediatamente antes de ejecutarlo y comprueba también el hash del script Linux extraído.
- La caché de actualización se limita a una carpeta de versión y se crean archivos con permisos restrictivos cuando el sistema operativo lo permite.
- El flujo de GitHub Actions firma el manifiesto con el secreto `UPDATE_SIGNING_PRIVATE_KEY_B64`. La clave privada no forma parte del repositorio, de los artefactos ni de las Releases.
- Las Releases existentes no se sobrescriben. La publicación exige crear una nueva etiqueta y adjunta el manifiesto, su firma, los paquetes y SBOMs CycloneDX.
- Las acciones de GitHub usadas en el workflow están fijadas por SHA completo. El compilador Inno Setup instalado por CI se fija a una versión concreta.
- CI ejecuta `pip-audit` sobre las dependencias de ejecución y de compilación y genera SBOMs.

**Limitaciones:** la firma de la Release autentica los manifiestos y paquetes frente a la clave pública integrada, pero no es una firma Authenticode del instalador de Windows. La clave de firma debe protegerse como secreto de GitHub con acceso mínimo, autenticación multifactor y revisión de permisos. La rotación de la clave pública requiere publicar una versión de la aplicación que confíe en la nueva clave. Una cuenta de GitHub comprometida con acceso a la clave podría firmar artefactos maliciosos.

### Importación de documentos

- Los archivos TXT, HTML y DOCX se limitan a 25 MiB de tamaño comprimido.
- Para DOCX se limitan el número de componentes ZIP y el volumen descomprimido antes de abrirlo con `python-docx`.
- El XML del tema DOCX se analiza con `defusedxml`.
- La extracción de estilos CSS por clase evita la expresión regular sobre el documento completo y trunca entradas superiores a 5 millones de caracteres.

### Instalación Linux y compilación Windows

- El instalador Linux prepara primero la nueva versión en un directorio temporal del mismo sistema de archivos, sustituye el directorio con `rename` y conserva una copia de seguridad de la instalación anterior. Si falla la sustitución, intenta restaurarla.
- La entrada `.desktop` se genera con el argumento ejecutable entrecomillado y escapado.
- El script Windows no busca `ISCC.exe` en el directorio actual ni en `PATH`; utiliza rutas absolutas habituales y valida la versión del compilador.

## Tratamiento de datos y comportamiento

- El programa realiza solicitudes HTTP(S) a GitHub para consultar y descargar Releases cuando el usuario busca actualizaciones o activa la comprobación automática. GitHub puede recibir la dirección IP y el agente de usuario de esa conexión.
- La comprobación de actualizaciones al iniciar está desactivada por defecto.
- Al conceder permisos de páginas, la extensión puede consultar pestañas HTTP/HTTPS, títulos, dominios/rutas sin query ni fragmento y metadatos de campos editables (por ejemplo, etiqueta, placeholder y geometría). La extensión no necesita enviar el texto que ya se encuentra en esos campos.
- La captura de la pestaña se solicita desde la aplicación después de una confirmación explícita del usuario.
- En Linux, el listener de atajos `pynput` puede observar eventos de teclado a bajo nivel mientras está activo; el código solo utiliza F8/F9 para detener o pausar y no almacena ni transmite el resto de teclas.
- Hay usos de `subprocess.Popen` con listas de argumentos para abrir recursos locales o iniciar instaladores. No se usa `shell=True`, `os.system`, `eval`, `exec`, `pickle` ni `innerHTML` en los flujos revisados.

## Dependencias y pruebas

- Las dependencias directas y la herramienta de compilación están fijadas por versión. La compilación CI audita los manifiestos de requisitos y genera SBOMs.
- Las pruebas cubren el protocolo HMAC, persistencia del código, límites de cola, firmas Ed25519, comparación SHA-256, redirecciones HTTPS, rechazo de firmas inválidas, extracción TAR y rechazo de rutas/enlaces peligrosos.
- La sintaxis de JavaScript se valida con Node.js en la revisión local del parche. CI además ejecuta las pruebas Python y los preflight de cada plataforma.

## Configuración obligatoria antes de publicar v1.0.2

1. Crear un secreto de repositorio llamado `UPDATE_SIGNING_PRIVATE_KEY_B64` con el contenido de `UPDATE_SIGNING_PRIVATE_KEY_B64.txt` entregado aparte. No incluir ese archivo en el ZIP del proyecto, Git, issues, commits ni Releases.
2. Restringir quién puede administrar Actions secrets y publicar etiquetas/releases. Activar MFA en las cuentas con permiso de escritura.
3. Subir `beta/v1.0.2`, ejecutar el workflow y comprobar ambas plataformas. La publicación por etiqueta `v1.0.2` fallará intencionalmente si el secreto no está configurado o no corresponde a la clave pública integrada.
4. Antes de distribuir los instaladores, probar instalación, actualización, rollback Linux, permisos de extensión y escritura real en equipos Windows y Linux.

## Riesgos residuales

- No hay Native Messaging ni un broker aislado para el puente local.
- Un proceso malicioso con el mismo usuario puede atacar o leer datos de la sesión de usuario; los permisos por usuario no protegen contra malware de esa misma cuenta.
- La extensión no está distribuida mediante Chrome Web Store o Edge Add-ons; se carga manualmente desde la carpeta del proyecto. El ZIP de extensión queda incluido en la Release y cubierto por el manifiesto firmado, pero cada usuario debe mantener esa carpeta protegida.
- El instalador Windows no tiene firma Authenticode propia; Windows puede mostrar el aviso de editor desconocido.
- El funcionamiento real de automatización, GUI, instaladores y actualizador requiere pruebas en Windows 10/11 y distribuciones Linux soportadas. Las pruebas ejecutadas en el entorno de desarrollo no prueban todos esos escenarios.
- Las pruebas automatizadas y el análisis estático no garantizan ausencia de vulnerabilidades.

## Reporte responsable

Consulta `SECURITY.md` para comunicar vulnerabilidades de manera privada. No adjuntes contraseñas, tokens, claves privadas, documentos sensibles ni capturas con información personal.
