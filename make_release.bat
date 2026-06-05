@echo off
setlocal
cd /d "%~dp0"

set VERSION=1.0.3
set OUT=release\MoreRobAccounts-v%VERSION%-win64

echo === Compilando aplicacion (sin consola) ===
python -m PyInstaller --noconfirm MoreRobAccountsUI.spec
if errorlevel 1 (
    echo Error al compilar.
    pause
    exit /b 1
)

echo === Preparando carpeta de distribucion ===
if exist release rmdir /s /q release
mkdir "%OUT%"

copy /y "dist\MoreRobAccountsUI.exe" "%OUT%\"
copy /y "accounts.template.json" "%OUT%\accounts.json"
copy /y "LEEME.txt" "%OUT%\"

echo === Creando ZIP ===
powershell -NoProfile -Command "Compress-Archive -Path '%OUT%\*' -DestinationPath 'release\MoreRobAccounts-v%VERSION%-win64.zip' -Force"

echo.
echo Listo para compartir:
echo   Carpeta: %OUT%
echo   ZIP:     release\MoreRobAccounts-v%VERSION%-win64.zip
echo.
echo Sube el ZIP a GitHub Releases, Google Drive, etc.
pause
