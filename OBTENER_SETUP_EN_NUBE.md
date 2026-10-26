# Construir los paquetes de Escritor Automático v1.0.0

La detección del sistema operativo ya está integrada en la aplicación. El flujo de GitHub Actions construye por separado:

- **Windows x64:** `EscritorAutomatico-Setup-v1.0.0.exe`, un instalador tradicional que no exige Python al usuario final.
- **Linux x86_64:** `EscritorAutomatico-v1.0.0-linux-x86_64.tar.gz`, con el intérprete y dependencias empaquetados por PyInstaller, más `instalar_escritor_automatico_linux.sh` dentro del archivo.

## Cómo obtenerlos sin instalar Python en el PC de desarrollo

1. Publica esta carpeta completa en el repositorio público de GitHub si quieres distribuir el código abierto. Conserva la carpeta oculta `.github/workflows`.
2. Abre la pestaña **Actions** y ejecuta **Construir paquetes Windows y Linux de Escritor Automático** mediante **Run workflow**. También se ejecuta al hacer `push` a `main` o `master` con cambios del proyecto.
3. Al terminar, descarga los artefactos `escritorio-automatico-windows-x64` y `escritorio-automatico-linux-x86_64`.
4. Windows: ejecuta el `Setup.exe`. Linux: extrae el `.tar.gz`, cambia al directorio extraído y ejecuta `./instalar_escritor_automatico_linux.sh`.

La compilación ocurre en los runners hospedados por GitHub. El paquete Linux se compila en Ubuntu, porque PyInstaller no es un compilador cruzado y se recomienda compilar cada plataforma en su sistema operativo correspondiente: https://pyinstaller.org/en/stable/.

## Compatibilidad Linux

- La app detecta la distribución y el tipo de sesión gráfica e indica el sistema en la cabecera.
- La escritura en ventana activa y el modo web pueden funcionar en sesiones X11/Xorg.
- `pynput` se utiliza para inyectar teclas en Linux. Wayland restringe por diseño la entrada global de algunas aplicaciones; el soporte puede ser parcial en XWayland. No ejecutes la aplicación como root para intentar saltarte esas restricciones.
- El modo Word mediante COM, el portapapeles HTML Win32 y la escritura Win32 en segundo plano siguen reservados para Windows.
- Google Docs utiliza el teclado del sistema en primer plano: al terminar la cuenta regresiva, cambia a la pestaña, haz clic en el documento y mantenlo en primer plano.
- El paquete generado en Ubuntu 24.04 x86_64 está orientado a distribuciones Linux modernas compatibles con la versión de glibc del runner; no es un paquete universal para cualquier distribución o arquitectura.

## Comprobaciones

El flujo valida sintaxis Python, manifiesto e ID de la extensión, y calcula SHA-256 para cada artefacto. Aun así, el instalador final debe probarse en un Windows real y el paquete Linux en una distribución de destino, ya que no se puede validar aquí la inyección de teclas en el escritorio del usuario.


## Publicar la primera versión 1.0.0

Después de subir el código a la rama principal y de confirmar que el flujo de Actions termina correctamente, verifica que `version.json` contenga `1.0.0`. Crea la etiqueta inicial desde Git Bash:

```bash
git tag v1.0.0
git push origin v1.0.0
```

La etiqueta debe coincidir exactamente con el valor de `version.json`. El flujo publicará una GitHub Release con los instaladores de Windows y Linux y `SHA256SUMS.txt`.

## Publicar versiones actualizables

La compilación manual genera artefactos de prueba con retención limitada. Para que las aplicaciones instaladas detecten la versión, cambia `version.json` a un nuevo número `X.Y.Z`, publica los cambios en la rama principal y crea una etiqueta igual, por ejemplo:

```bash
git tag v1.0.1
git push origin v1.0.1
```

El workflow compila ambas plataformas y, al ejecutarse por una etiqueta `v*`, publica una GitHub Release con los instaladores y `SHA256SUMS.txt`. El actualizador solo consulta Releases estables publicadas; no intenta actualizar desde un simple commit de la rama. El usuario siempre debe aceptar la descarga y confirmar por separado la ejecución del instalador.
