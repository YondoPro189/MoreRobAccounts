# MoreRobAccounts

Lanzador multi-cuenta de Roblox para Windows. Abre varias instancias simultáneas, cada una con una cuenta distinta.

## Descargar (usuarios)

1. Ve a **[Releases](https://github.com/YondoPro189/MoreRobAccounts/releases)**.
2. Descarga **`MoreRobAccounts-v2.0.0-win64.zip`** (versión completa, ~50 MB).
3. Descomprime y ejecuta **`MoreRobAccountsUI.exe`**.

### Novedades 2.0

- **Familias** — agrupa cuentas + Place ID → botón **Lanzar Familia**
- **Historial de Place ID**
- **Grupos** por cuenta (Farm, Principal, etc.)
- **Comprobar / renovar sesiones** (inválidas en rojo)
- **Barra de progreso** y **notificaciones Windows**
- **Delay configurable** si lanzas más de 3 cuentas (3 s por defecto)

### Instalador (opcional)

Compila el instalador con [Inno Setup 6](https://jrsoftware.org/isinfo.php) y `build_installer.bat`.
Genera `MoreRobAccounts-Setup-2.0.0-win64.exe`.

### Agregar cuentas (sin cookies manuales)

1. Abre la app y pon el **Place ID** del juego.
2. Pulsa **"Iniciar sesión con Roblox"**.
3. Inicia sesión en la ventana de **Microsoft Edge** que se abre.
4. La cuenta se guarda cifrada automáticamente. Repite para cada cuenta.

No necesitas copiar cookies ni abrir DevTools.

> Descarga la versión **completa** (`MoreRobAccounts-v1.0-win64.zip`), no la LITE. La LITE es solo para Discord y requiere pegar cookies manualmente.

### Requisitos

- Windows 10/11 (64 bits)
- Roblox instalado
- Microsoft Edge (viene con Windows)

---

## Desarrollo (desde código fuente)

### Requisitos

- Python 3.10+
- Roblox instalado

### Instalación

```bat
pip install -r requirements.txt
pip install -r requirements-browser.txt
python -m playwright install chromium
```

### Ejecutar la interfaz

```bat
python ui.py
```

### Compilar ejecutable

```bat
make_release.bat
```

Genera `release\MoreRobAccounts-v1.0-win64.zip` listo para distribuir.

---

## Uso por línea de comandos

```bat
python launcher.py --add              # agregar cuenta (navegador)
python launcher.py --list             # listar cuentas
python launcher.py                    # lanzar todas
python launcher.py --account C1 C2    # lanzar cuentas específicas
```

---

## Cómo funciona

1. Guarda las sesiones cifradas en `accounts.json` (solo tu usuario de Windows puede leerlas).
2. Para cada cuenta solicita un **Auth Ticket** de un solo uso a la API de Roblox.
3. Lanza Roblox con ese ticket usando el protocolo `roblox-player:`.
