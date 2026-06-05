# MoreRobAccounts

Lanzador multi-cuenta de Roblox para Windows. Permite abrir varias instancias simultáneas, cada una autenticada con una cuenta distinta.

## Requisitos

- Windows 10/11
- Python 3.10+ → https://www.python.org/downloads/
- Roblox instalado

## Instalación

```bat
pip install -r requirements.txt
```

## Cómo obtener tu cookie `.ROBLOSECURITY`

1. Abre [roblox.com](https://www.roblox.com) en tu navegador e inicia sesión.
2. Pulsa **F12** para abrir DevTools.
3. Ve a **Application** → **Cookies** → `https://www.roblox.com`.
4. Copia el valor de `.ROBLOSECURITY` (empieza con `_|WARNING...`).

> ⚠️ **Nunca compartas esta cookie con nadie.** Es equivalente a tu contraseña.

## Uso

### Agregar una cuenta
```bat
python launcher.py --add
```

### Ver cuentas guardadas
```bat
python launcher.py --list
```

### Lanzar todas las cuentas
```bat
python launcher.py
```

### Lanzar cuentas específicas
```bat
python launcher.py --account Cuenta1 Cuenta2
```

## Cómo funciona

1. Lee las cookies del archivo `accounts.json`.
2. Para cada cuenta solicita un **Auth Ticket** de un solo uso a la API de Roblox — esto evita pasar la cookie directamente al proceso.
3. Lanza el ejecutable de Roblox con ese ticket usando el protocolo `roblox-player:`, con un delay de 3 segundos entre instancias para evitar conflictos de inicio.
