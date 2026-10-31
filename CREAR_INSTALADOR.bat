@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Compilar instalador - Escritor Automatico
set "LOG=%CD%\BUILD_INSTALADOR.log"
set "PY="
set "ISCC="
set "APP_VERSION="
set "SETUP_FILE="

>"%LOG%" echo Registro de compilacion de Escritor Automatico
>>"%LOG%" echo Fecha: %DATE% %TIME%
>>"%LOG%" echo Carpeta: %CD%

echo ============================================================
echo COMPILADOR DEL INSTALADOR - ESCRITOR AUTOMATICO
echo ============================================================
echo Crea primero la aplicacion portable y despues un instalador por usuario.
echo El usuario final no necesita Python.
echo El registro completo se guarda en BUILD_INSTALADOR.log.
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: No se encontro py.exe. Instala Python 3.12 x64 en el equipo de compilacion.
  goto :error
)
py -3.12 -c "import sys,struct; print('Python:',sys.version.split()[0], 'bits:',struct.calcsize('P')*8); sys.exit(0 if sys.platform=='win32' and sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)" >>"%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: Se requiere Python 3.12 de 64 bits. Revisa BUILD_INSTALADOR.log.
  goto :error
)
for /f "usebackq delims=" %%V in (`py -3.12 -c "import json; print(json.load(open('version.json', encoding='utf-8'))['version'])"`) do set "APP_VERSION=%%V"
if not defined APP_VERSION (
  echo ERROR: No se pudo leer la version desde version.json.
  goto :error
)
set "SETUP_FILE=%CD%\dist-installer\EscritorAutomatico-Setup-v%APP_VERSION%.exe"
>>"%LOG%" echo Version de compilacion: %APP_VERSION%

rem Usa solo la ruta absoluta de Inno Setup 6; no busca ejecutables en el directorio del proyecto ni en PATH.
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo ERROR: No se encontro ISCC.exe de Inno Setup 6.7.1 en Program Files.
  echo Instala Inno Setup desde https://jrsoftware.org/isinfo.php y repite.
  goto :error
)
echo Compilador encontrado: "%ISCC%"
>>"%LOG%" echo Inno Setup: %ISCC%
powershell -NoProfile -NonInteractive -Command "$v = (Get-Item -LiteralPath $env:ISCC).VersionInfo.ProductVersion; if ($v -notmatch '^6\.7\.1') { Write-Error ('Version ISCC inesperada: ' + $v); exit 1 }" >>"%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: Se esperaba Inno Setup 6.7.1. Revisa BUILD_INSTALADOR.log.
  goto :error
)

 echo.
echo [1/6] Validando el proyecto y la extension...
py -3.12 preflight.py >>"%LOG%" 2>&1
if errorlevel 1 goto :error
echo Validaciones previas completadas.

 echo.
echo [2/6] Limpiando solamente las carpetas generadas por compilaciones anteriores...
for %%D in (".build_venv" "build" "dist" "dist-installer") do (
  if exist "%%~D" rmdir /s /q "%%~D" >>"%LOG%" 2>&1
  if exist "%%~D" (
    echo ERROR: No se pudo limpiar %%~D. Cierra los procesos que la esten usando.
    goto :error
  )
)
mkdir build\pyinstaller build\spec dist-installer >>"%LOG%" 2>&1
if errorlevel 1 goto :error

 echo.
echo [3/6] Creando entorno virtual limpio para la compilacion...
py -3.12 -m venv .build_venv >>"%LOG%" 2>&1
if errorlevel 1 goto :error
set "PY=%CD%\.build_venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: No se pudo crear el entorno virtual.
  goto :error
)
"%PY%" -c "import sys,struct; print('Entorno:',sys.executable); print('Python:',sys.version); sys.exit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)" >>"%LOG%" 2>&1
if errorlevel 1 goto :error

 echo.
echo [4/6] Instalando dependencias exactas en formato wheel...
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_CACHE_DIR=1"
set "PYTHONNOUSERSITE=1"
"%PY%" -m pip install --disable-pip-version-check --no-cache-dir --upgrade --only-binary=:all: "pip==26.2.2" >>"%LOG%" 2>&1
if errorlevel 1 goto :error
"%PY%" -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: --no-deps --force-reinstall -r requirements-build.txt >>"%LOG%" 2>&1
if errorlevel 1 goto :error
"%PY%" -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: --no-deps --force-reinstall -r requirements.txt >>"%LOG%" 2>&1
if errorlevel 1 goto :error
"%PY%" -m pip check >>"%LOG%" 2>&1
if errorlevel 1 goto :error
echo Dependencias instaladas; pip check ha terminado correctamente.

 echo.
echo [5/6] Empaquetando el programa con PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean --windowed --onedir --contents-directory . --name EscritorAutomatico --distpath dist --workpath build\pyinstaller --specpath build\spec --add-data "%CD%\web_extension;web_extension" --add-data "%CD%\LEEME.txt;." --add-data "%CD%\INFORME_SEGURIDAD.md;." --add-data "%CD%\version.json;." --add-data "%CD%\update_config.json;." --collect-data docx --collect-all PIL --hidden-import pythoncom --hidden-import pywintypes --hidden-import win32com --hidden-import win32com.client --hidden-import websockets.sync.server --hidden-import docx.oxml.ns escritor_automatico.py >>"%LOG%" 2>&1
if errorlevel 1 goto :error
if not exist "dist\EscritorAutomatico\EscritorAutomatico.exe" (
  echo ERROR: PyInstaller no genero EscritorAutomatico.exe.
  goto :error
)
if not exist "dist\EscritorAutomatico\web_extension\manifest.json" (
  echo ERROR: La extension no se incluyo correctamente en el paquete.
  goto :error
)
if not exist "dist\EscritorAutomatico\version.json" (
  echo ERROR: No se incluyo version.json en el paquete.
  goto :error
)
if not exist "dist\EscritorAutomatico\update_config.json" (
  echo ERROR: No se incluyo update_config.json en el paquete.
  goto :error
)
copy /y POST_INSTALACION.txt "dist\EscritorAutomatico\POST_INSTALACION.txt" >>"%LOG%" 2>&1
if errorlevel 1 goto :error

 echo.
echo [6/6] Compilando el asistente de instalacion...
"%ISCC%" "/DAppVersion=%APP_VERSION%" installer.iss >>"%LOG%" 2>&1
if errorlevel 1 goto :error
if not exist "%SETUP_FILE%" (
  echo ERROR: Inno Setup no produjo el instalador esperado.
  goto :error
)

"%PY%" -m pip freeze > "dist-installer\build-environment.txt" 2>>"%LOG%"
"%PY%" -c "import hashlib,pathlib; p=pathlib.Path(r'%SETUP_FILE%'); print(hashlib.sha256(p.read_bytes()).hexdigest(), p.name)" > "dist-installer\SHA256SUMS.txt" 2>>"%LOG%"
if errorlevel 1 goto :error

echo.
echo ============================================================
echo COMPILACION TERMINADA CORRECTAMENTE
echo ============================================================
echo Version:    %APP_VERSION%
echo Instalador: %SETUP_FILE%
echo SHA-256:    %CD%\dist-installer\SHA256SUMS.txt
echo Registro:   %LOG%
echo.
echo Prueba la instalacion en Windows antes de distribuirla a otras personas.
echo La extension se carga manualmente desde la carpeta instalada.
if not defined CI pause
exit /b 0

:error
echo.
echo ============================================================
echo LA COMPILACION NO TERMINO CORRECTAMENTE
echo ============================================================
echo Revisa el registro: %LOG%
if exist "%LOG%" type "%LOG%"
echo.
if not defined CI pause
exit /b 1
