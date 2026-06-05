@echo off
cd /d "%~dp0"
echo Compilando MoreRobAccounts (sin consola)...
python -m PyInstaller --noconfirm MoreRobAccountsUI.spec
if errorlevel 1 (
    echo Error al compilar.
    pause
    exit /b 1
)
echo.
echo Listo: dist\MoreRobAccountsUI.exe
echo Puedes crear un acceso directo en el escritorio a ese archivo.
pause
