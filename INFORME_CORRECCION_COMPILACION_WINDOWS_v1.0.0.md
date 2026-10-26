# Corrección final de compilación Windows — v1.0.0

## Causa confirmada

La compilación de PyInstaller finalizaba correctamente. El fallo se producía al ejecutar Inno Setup 6.7.1 porque `installer.iss` contenía esta directiva inválida:

```ini
UninstallDisplayVersion={#AppVersion}
```

`UninstallDisplayVersion` no es una directiva reconocida en la sección `[Setup]` de Inno Setup 6. El campo de versión de la aplicación ya se configura mediante `AppVersion={#AppVersion}`; no hace falta declarar una directiva independiente para la versión de desinstalación.

## Cambios

- Se eliminó `UninstallDisplayVersion` de `installer.iss`.
- Se añadió una comprobación a `preflight.py` que rechaza esa directiva inválida antes de comenzar una compilación costosa y confirma que `AppVersion={#AppVersion}` está presente.
- Se conserva `AppVersion`, `AppVerName` y el nombre de salida `EscritorAutomatico-Setup-v1.0.0.exe`.

## Validación local realizada

Se comprobó la sintaxis de Python, la presencia y ausencia de las directivas esperadas, las pruebas unitarias del actualizador y la integridad de los archivos ZIP preparados. Este entorno no tiene Inno Setup para Windows; por tanto, la compilación final debe confirmarse de nuevo en GitHub Actions.
