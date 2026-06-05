@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM === Configura tu repo de GitHub ===
REM Puedes: editar aqui, o antes en CMD: set GITHUB_USER=tuusuario
if not defined GITHUB_USER set GITHUB_USER=YondoPro189
if not "%~1"=="" set GITHUB_USER=%~1
set REPO_NAME=MoreRobAccounts
set VERSION=1.0
set TAG=v%VERSION%

set ZIP=release\MoreRobAccounts-v%VERSION%-win64.zip

echo.
echo === MoreRobAccounts - Subir a GitHub ===
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo Git no esta en el PATH. Cierra y abre CMD de nuevo, o instala con:
    echo   winget install Git.Git
    pause
    exit /b 1
)

where gh >nul 2>&1
if errorlevel 1 (
    echo GitHub CLI no esta en el PATH. Cierra y abre CMD de nuevo, o instala con:
    echo   winget install GitHub.cli
    pause
    exit /b 1
)

if not exist "%ZIP%" (
    echo No existe el ZIP completo. Compilando primero...
    call make_release.bat
    if errorlevel 1 exit /b 1
)

gh auth status >nul 2>&1
if errorlevel 1 (
    echo.
    echo Primero inicia sesion en GitHub ^(se abrira el navegador^):
    gh auth login -w -p https
    if errorlevel 1 (
        echo Error al iniciar sesion.
        pause
        exit /b 1
    )
)

if "%GITHUB_USER%"=="" (
    echo.
    echo Falta tu usuario de GitHub. Ejemplo:
    echo   set GITHUB_USER=miusuario
    echo   subir_github.bat
    pause
    exit /b 1
)
echo Usuario: %GITHUB_USER%  Repo: %REPO_NAME%
echo.

if not exist .git (
    echo === Inicializando repositorio ===
    git init
    git branch -M main
)

gh repo view %GITHUB_USER%/%REPO_NAME% >nul 2>&1
if errorlevel 1 (
    echo === Creando repo en GitHub ===
    gh repo create %REPO_NAME% --public --source=. --remote=origin --description "Lanzador multi-cuenta de Roblox para Windows"
) else (
    git remote get-url origin >nul 2>&1
    if errorlevel 1 git remote add origin https://github.com/%GITHUB_USER%/%REPO_NAME%.git
)

echo === Subiendo codigo fuente ===
git add .
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "MoreRobAccounts v%VERSION%"
) else (
    echo Sin cambios nuevos en el codigo.
)

git push -u origin main
if errorlevel 1 (
    echo Si falla el push, prueba: git push -u origin main --force
    pause
    exit /b 1
)

echo === Creando release con ZIP completo (~52 MB^) ===
gh release view %TAG% >nul 2>&1
if errorlevel 1 (
    gh release create %TAG% "%ZIP%" ^
        --title "MoreRobAccounts v%VERSION%" ^
        --notes "Version completa con login por navegador. Descomprime el ZIP y ejecuta MoreRobAccountsUI.exe. Requiere Roblox instalado en Windows."
) else (
    echo La release %TAG% ya existe. Subiendo/actualizando el ZIP...
    gh release upload %TAG% "%ZIP%" --clobber
)

echo.
echo === Listo ===
for /f "delims=" %%u in ('gh release view %TAG% --json url -q .url') do set RELEASE_URL=%%u
echo Release: !RELEASE_URL!
echo Comparte ese enlace para que otros descarguen la version completa.
echo.
pause
