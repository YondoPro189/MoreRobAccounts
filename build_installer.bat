@echo off
setlocal
cd /d "%~dp0"

echo === Compilando MoreRobAccounts 2.0.0 ===
call make_release.bat
if errorlevel 1 exit /b 1

set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe

if "%ISCC%"=="" (
    echo.
    echo Inno Setup no encontrado. Instala desde: https://jrsoftware.org/isinfo.php
    echo Luego ejecuta de nuevo build_installer.bat
    echo.
    echo El ZIP portable ya esta en release\
    pause
    exit /b 0
)

echo === Creando instalador ===
"%ISCC%" installer.iss
if errorlevel 1 (
    echo Error al crear instalador.
    pause
    exit /b 1
)

echo.
echo Listo:
echo   release\MoreRobAccounts-Setup-2.0.0-win64.exe
echo   release\MoreRobAccounts-v2.0.0-win64.zip
pause
