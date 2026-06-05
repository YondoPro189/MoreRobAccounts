@echo off
setlocal
cd /d "%~dp0"

set VERSION=1.0
set OUT=release\MoreRobAccounts-LITE-v%VERSION%-win64

echo === Compilando version LITE (sin Playwright, mas pequena) ===
python -m PyInstaller --noconfirm MoreRobAccountsUI-lite.spec
if errorlevel 1 (
    echo Error al compilar.
    pause
    exit /b 1
)

echo === Preparando carpeta ===
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"

copy /y "dist\MoreRobAccountsUI.exe" "%OUT%\"
copy /y "accounts.template.json" "%OUT%\accounts.json"
copy /y "LEEME.txt" "%OUT%\"
echo Version LITE: login por navegador NO incluido. Usa "Pegar cookie (avanzado)".>> "%OUT%\LEEME.txt"

powershell -NoProfile -Command "Compress-Archive -Path '%OUT%\*' -DestinationPath 'release\MoreRobAccounts-LITE-v%VERSION%-win64.zip' -Force"

for %%F in ("release\MoreRobAccounts-LITE-v%VERSION%-win64.zip") do echo Tamano ZIP: %%~zF bytes

echo.
echo Listo: release\MoreRobAccounts-LITE-v%VERSION%-win64.zip
echo (Deberia ser menor de 25 MB para Discord)
pause
