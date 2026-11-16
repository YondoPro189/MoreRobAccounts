"""
MoreRobAccounts - Lanzador multi-cuenta de Roblox
--------------------------------------------------
Abre varias instancias de Roblox simultáneamente, cada una
autenticada con una cuenta distinta usando su cookie .ROBLOSECURITY.

Requisitos:
  pip install requests

Uso:
  python launcher.py                  -> lanza todas las cuentas
  python launcher.py --list           -> lista las cuentas guardadas
  python launcher.py --add            -> agrega una cuenta interactivamente
  python launcher.py --account Cuenta1 Cuenta2  -> lanza solo esas cuentas
"""

import base64
import ctypes
from ctypes import wintypes
import json
import os
import queue
import sys
import time
import subprocess
import threading
import argparse
import requests
from urllib.parse import quote

import app_storage
import roblox_fps
import roblox_servers
from app_storage import ACCOUNTS_FORMAT_VERSION
from security import SecurityError, decrypt_secret, encrypt_secret, is_encryption_available

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]

try:
    import win32event
    import win32api
    import win32crypt
    import winerror
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

ACCOUNTS_FORMAT_VERSION = app_storage.ACCOUNTS_FORMAT_VERSION  # noqa: F811

def get_app_dir() -> str:
    """Carpeta del .exe (empaquetado) o del script (desarrollo)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def is_frozen_app() -> bool:
    return getattr(sys, "frozen", False)


def get_icon_path(ext: str = "ico") -> str | None:
    """Ruta a assets/icon.ico o icon.png (desarrollo o empaquetado)."""
    name = f"icon.{ext.lower().lstrip('.')}"
    candidates: list[str] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(os.path.join(meipass, "assets", name))
        candidates.append(os.path.join(get_app_dir(), "assets", name))

    project_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(project_dir, "assets", name))

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def get_accounts_file() -> str:
    return os.path.join(get_app_dir(), "accounts.json")


ACCOUNTS_FILE = get_accounts_file()

# Ruta por defecto del launcher de Roblox en Windows
ROBLOX_LAUNCHER = os.path.expandvars(
    r"%LOCALAPPDATA%\Roblox\Versions\RobloxPlayerLauncher.exe"
)


# ---------------------------------------------------------------------------
# Gestión de cuentas (delegado a app_storage v3)
# ---------------------------------------------------------------------------

def load_accounts(*, migrate_plaintext: bool = True) -> list[dict]:
    return app_storage.load_accounts(migrate_plaintext=migrate_plaintext)


def save_accounts(accounts: list[dict]) -> None:
    app_storage.save_accounts(accounts)


def add_account_interactive() -> None:
    accounts = load_accounts()
    print("\n=== Agregar cuenta ===")
    print("1) Inicio de sesion seguro (navegador) [recomendado]")
    print("2) Pegar cookie manualmente [avanzado]")
    choice = input("Elige 1 o 2 [1]: ").strip() or "1"

    name = input("Nombre (opcional, Enter para auto): ").strip()
    cookie: str | None = None
    roblox_user: str | None = None

    if choice == "1":
        try:
            from secure_login import login_via_browser
        except ImportError:
            print("Instala: pip install -r requirements-browser.txt")
            print("         playwright install chromium")
            return
        print("\nSe abrira Roblox en el navegador. Inicia sesion y espera...")
        cookie, roblox_user, error = login_via_browser(timeout_sec=300)
        if error or not cookie:
            print(f"Error: {error or 'sin sesion'}")
            return
        if not name:
            name = roblox_user or "Cuenta"
    else:
        if not name:
            name = input("Nombre (ej. MiCuenta1): ").strip()
            if not name:
                print("El nombre no puede estar vacio.")
                return
        print(
            "\nPara obtener tu cookie .ROBLOSECURITY:\n"
            "  1. Abre roblox.com en tu navegador e inicia sesion.\n"
            "  2. Abre DevTools (F12) > Application > Cookies > https://www.roblox.com\n"
            "  3. Copia el valor de '.ROBLOSECURITY'\n"
        )
        cookie = input("Pega la cookie aqui: ").strip()
        if len(cookie) >= 2 and cookie[0] in ("'", '"') and cookie[-1] == cookie[0]:
            cookie = cookie[1:-1].strip()

    if not cookie:
        print("Cookie vacia, operacion cancelada.")
        return
    if any(a["name"] == name for a in accounts):
        print(f"Ya existe una cuenta llamada '{name}'.")
        return
    accounts.append({"name": name, "roblosecurity": cookie, "group": ""})
    save_accounts(accounts)
    print(f"Cuenta '{name}' guardada (cifrada).")


def remove_accounts(names: list[str]) -> tuple[list[str], list[str]]:
    """
    Elimina cuentas por nombre.
    Devuelve (eliminadas, no_encontradas).
    """
    names_set = {n.strip() for n in names if n.strip()}
    if not names_set:
        return [], []

    accounts = load_accounts()
    removed: list[str] = []
    remaining: list[dict] = []

    for acc in accounts:
        if acc.get("name") in names_set:
            removed.append(acc["name"])
            names_set.discard(acc["name"])
        else:
            remaining.append(acc)

    not_found = sorted(names_set)
    if removed:
        save_accounts(remaining)
    return removed, not_found


# ---------------------------------------------------------------------------
# Autenticación y obtención del Auth Ticket
# ---------------------------------------------------------------------------

def get_auth_ticket(
    roblosecurity: str,
    *,
    debug: bool = False,
    max_retries: int = 1,
) -> str | None:
    """
    Obtiene un Auth Ticket de un solo uso desde la API de Roblox.
    """
    attempts = max(1, min(5, max_retries))
    for attempt in range(attempts):
        ticket = _get_auth_ticket_once(roblosecurity, debug=debug, attempt=attempt + 1)
        if ticket:
            return ticket
        if attempt + 1 < attempts:
            time.sleep(1.5)
    return None


def _get_auth_ticket_once(roblosecurity: str, *, debug: bool = False, attempt: int = 1) -> str | None:
    url = "https://auth.roblox.com/v1/authentication-ticket"
    cookies = {".ROBLOSECURITY": roblosecurity}

    session = requests.Session()
    base_headers = {
        "Referer": "https://www.roblox.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*",
        "Content-Type": "application/json",
    }

    def extract_ticket(r: requests.Response) -> str | None:
        # Normalmente viene en un header con este nombre exacto.
        ticket = r.headers.get("rbx-authentication-ticket")
        if ticket:
            return ticket
        # Fallback por si Roblox devuelve JSON (por cambios de backend).
        try:
            data = r.json()
        except ValueError:
            return None
        for key in ("ticket", "authenticationTicket", "rbx-authentication-ticket"):
            v = data.get(key)
            if isinstance(v, str) and v:
                return v
        return None

    # 1) Intento: pedir/forzar CSRF con "fetch" y mandar body JSON válido.
    headers1 = dict(base_headers)
    headers1["X-CSRF-TOKEN"] = "fetch"
    resp = session.post(url, cookies=cookies, headers=headers1, json={}, timeout=15)
    ticket = extract_ticket(resp)
    if resp.status_code == 200 and ticket:
        if debug:
            print("[auth] HTTP 200. ticket_obtenido=True (sin retry).")
        return ticket

    # 2) Si rechaza por CSRF, prueba con token de la respuesta o "fetch".
    # Nota: algunos casos devuelven x-csrf-token y otros no.
    csrf = resp.headers.get("x-csrf-token") or resp.headers.get("X-CSRF-Token")
    retry_headers = dict(base_headers)
    if csrf:
        retry_headers["X-CSRF-TOKEN"] = csrf
    else:
        retry_headers["X-CSRF-TOKEN"] = "fetch"

    if debug:
        preview = (resp.text or "").strip()
        if len(preview) > 200:
            preview = preview[:200] + "..."
        if attempt > 1:
            print(f"[auth] reintento #{attempt}")
        print(
            f"[auth] intento#1 HTTP {resp.status_code}. csrf_header_present={bool(csrf)}. "
            f"resp_preview={preview!r} (esto suele ser el desafio CSRF)"
        )

    resp2 = session.post(url, cookies=cookies, headers=retry_headers, json={}, timeout=15)
    ticket2 = extract_ticket(resp2)
    if resp2.status_code == 200 and ticket2:
        if debug:
            print("[auth] intento#2 HTTP 200. ticket_obtenido=True (retry OK).")
        return ticket2

    if debug:
        preview2 = (resp2.text or "").strip()
        if len(preview2) > 200:
            preview2 = preview2[:200] + "..."
        print(
            f"[auth] intento#2 HTTP {resp2.status_code}. csrf_header_present={bool(resp2.headers.get('x-csrf-token'))}. "
            f"resp_preview={preview2!r}"
        )

    return None


# ---------------------------------------------------------------------------
# Lanzamiento de instancias
# ---------------------------------------------------------------------------

def find_roblox_launcher() -> str | None:
    """Busca el ejecutable más reciente de Roblox en Windows."""
    if winreg is not None and sys.platform == "win32":
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\ROBLOX Corporation\Environments\roblox-player",
            ) as key:
                client_exe, _ = winreg.QueryValueEx(key, "clientExe")
                if isinstance(client_exe, str) and os.path.isfile(client_exe):
                    return client_exe
        except OSError:
            pass

    versions_dir = os.path.expandvars(r"%LOCALAPPDATA%\Roblox\Versions")
    beta_exes: list[str] = []
    if os.path.isdir(versions_dir):
        for root, _dirs, files in os.walk(versions_dir):
            if "RobloxPlayerBeta.exe" in files:
                full = os.path.join(root, "RobloxPlayerBeta.exe")
                if os.path.isfile(full):
                    beta_exes.append(full)

    if beta_exes:
        beta_exes.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return beta_exes[0]

    if os.path.isfile(ROBLOX_LAUNCHER):
        return ROBLOX_LAUNCHER
    return None


def is_roblox_installed() -> tuple[bool, str | None]:
    path = find_roblox_launcher()
    return (path is not None, path)


def validate_account_session(account: dict) -> tuple[bool, str | None]:
    """Devuelve (valida, nombre_roblox)."""
    cookie = account.get("roblosecurity", "")
    if not isinstance(cookie, str) or not cookie.strip():
        return False, None
    try:
        from secure_login import verify_roblox_session

        username = verify_roblox_session(cookie)
        return (username is not None, username)
    except Exception:
        return False, None


def validate_accounts(accounts: list[dict]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for acc in accounts:
        ok, _ = validate_account_session(acc)
        result[acc["name"]] = ok
    return result


# ---------------------------------------------------------------------------
# Seguir usuarios (Friends API)
# ---------------------------------------------------------------------------

_ROBLOX_API_HEADERS = {
    "Referer": "https://www.roblox.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def resolve_roblox_user_id(username: str) -> tuple[int | None, str | None, str | None]:
    """
    Resuelve un username de Roblox a userId.
    Devuelve (user_id, display_name, error).
    """
    name = username.strip()
    if not name:
        return None, None, "Username vacío."
    if len(name) > 20:
        return None, None, "Username demasiado largo."

    try:
        resp = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [name], "excludeBannedUsers": True},
            headers=_ROBLOX_API_HEADERS,
            timeout=15,
        )
    except requests.RequestException as exc:
        return None, None, f"Error de red: {exc}"

    if resp.status_code != 200:
        return None, None, f"No se pudo buscar el usuario (HTTP {resp.status_code})."

    try:
        data = resp.json().get("data") or []
    except ValueError:
        return None, None, "Respuesta inválida de Roblox."

    if not data:
        return None, None, f"Usuario '{name}' no encontrado."

    entry = data[0]
    user_id = entry.get("id")
    if not isinstance(user_id, int):
        return None, None, f"Usuario '{name}' no encontrado."

    display = entry.get("displayName") or entry.get("name") or name
    return user_id, str(display), None


def _fetch_csrf_token(session: requests.Session, cookies: dict, method_url: str) -> str | None:
    headers = dict(_ROBLOX_API_HEADERS)
    headers["X-CSRF-TOKEN"] = "fetch"
    try:
        resp = session.post(method_url, cookies=cookies, headers=headers, json={}, timeout=15)
    except requests.RequestException:
        return None
    return resp.headers.get("x-csrf-token") or resp.headers.get("X-CSRF-Token")


def follow_roblox_user(roblosecurity: str, target_user_id: int, *, debug: bool = False) -> tuple[str, str | None]:
    """
    Sigue a un usuario con la cookie dada.
    Devuelve (estado, mensaje) donde estado es 'ok', 'already', 'challenge' o 'fail'.
    """
    cookies = {".ROBLOSECURITY": roblosecurity}
    url = f"https://friends.roblox.com/v1/users/{target_user_id}/follow"
    session = requests.Session()

    csrf = _fetch_csrf_token(session, cookies, url)
    if not csrf:
        return "fail", "No se pudo obtener token CSRF."

    headers = dict(_ROBLOX_API_HEADERS)
    headers["X-CSRF-TOKEN"] = csrf

    try:
        resp = session.post(url, cookies=cookies, headers=headers, json={}, timeout=15)
    except requests.RequestException as exc:
        return "fail", f"Error de red: {exc}"

    if resp.status_code == 200:
        return "ok", None

    challenge_type = resp.headers.get("rblx-challenge-type") or resp.headers.get("Rblx-Challenge-Type")
    challenge_id = resp.headers.get("rblx-challenge-id") or resp.headers.get("Rblx-Challenge-Id")

    try:
        payload = resp.json()
        errors = payload.get("errors") or []
        for err in errors:
            if not isinstance(err, dict):
                continue
            message = str(err.get("message", "")).lower()
            if "challenge is required" in message:
                return (
                    "challenge",
                    "Roblox requiere verificación anti-bot (Challenge/Captcha) en el navegador para seguir usuarios.",
                )
            if "already" in message or ("follow" in message and "invalid" not in message and "challenge" not in message):
                return "already", None
    except ValueError:
        payload = None

    body = (resp.text or "").lower()
    if resp.status_code == 400 and "already" in body:
        return "already", None

    if challenge_type or challenge_id or "challenge is required" in body:
        return (
            "challenge",
            "Roblox requiere verificación anti-bot (Challenge/Captcha) en el navegador para seguir usuarios.",
        )

    if resp.status_code == 403:
        return "fail", "No permitido (privacidad del usuario o cuenta)."

    if debug:
        preview = (resp.text or "")[:200]
        return "fail", f"HTTP {resp.status_code}: {preview}"

    return "fail", f"HTTP {resp.status_code}"


def follow_accounts_to_user(
    accounts: list[dict],
    username: str,
    *,
    debug: bool = False,
    delay_sec: float = 0.6,
    on_progress=None,
) -> tuple[list[str], list[str], list[str], str | None]:
    """
    Cada cuenta en `accounts` sigue al username indicado.
    Devuelve (exitosas, ya_seguían, fallidas, error_global).
    """
    user_id, display_name, error = resolve_roblox_user_id(username)
    if error or user_id is None:
        return [], [], [], error or "Usuario no encontrado."

    ok_names: list[str] = []
    already_names: list[str] = []
    fail_names: list[str] = []
    challenge_msg: str | None = None
    total = len(accounts)

    for i, account in enumerate(accounts):
        name = account["name"]
        cookie = account.get("roblosecurity", "")
        if on_progress:
            on_progress(i, total, name, "following")

        if not isinstance(cookie, str) or not cookie.strip():
            fail_names.append(name)
            if on_progress:
                on_progress(i + 1, total, name, "failed")
            continue

        if i > 0 and delay_sec > 0:
            time.sleep(delay_sec)

        status, msg = follow_roblox_user(cookie, user_id, debug=debug)
        if status == "ok":
            ok_names.append(name)
            prog = "ok"
        elif status == "already":
            already_names.append(name)
            prog = "already"
        elif status == "challenge":
            fail_names.append(name)
            challenge_msg = msg
            if on_progress:
                on_progress(i + 1, total, name, "failed")
            break
        else:
            fail_names.append(name)
            prog = "failed"
            if debug and msg:
                print(f"[{name}] follow error: {msg}")

        if on_progress:
            on_progress(i + 1, total, name, prog)

    if on_progress and display_name:
        on_progress(total, total, display_name, "done")

    if challenge_msg and not ok_names and not already_names:
        return ok_names, already_names, fail_names, challenge_msg

    return ok_names, already_names, fail_names, None


def compute_launch_delay(index: int, total: int, settings: dict | None = None) -> float:
    """
    Espera entre lanzamientos para evitar que dos instancias pisen RobloxCookies.dat
    mientras Roblox canjea el ticket de autenticación (~4-5s en Roblox 0.747+).
    """
    cfg = settings or app_storage.get_settings()
    delay_sec = float(cfg.get("launch_delay_sec", 6))
    if index <= 0:
        return 0.0
    return max(5.5, delay_sec)


def build_place_launcher_url(place_id: str, job_id: str | None = None) -> str:
    """URL de PlaceLauncher para unirse a un place o a un servidor concreto (JobId)."""
    base = "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
    if job_id:
        return (
            f"{base}?request=RequestGameJob&browserTrackerId=0"
            f"&placeId={place_id}&gameId={job_id}&isPlayTogetherGame=false"
        )
    return (
        f"{base}?request=RequestGame&browserTrackerId=0"
        f"&placeId={place_id}&isPlayTogetherGame=false"
    )


def open_roblox_player_uri(uri: str) -> bool:
    """
    Abre el esquema roblox-player: usando el manejador registrado en Windows.
    """
    try:
        os.startfile(uri)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Gestión de procesos de Roblox, System Tray y Singletons (Multi-Instancia)
# ---------------------------------------------------------------------------

class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class _UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(_UNICODE_STRING)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", wintypes.LPVOID),
        ("SecurityQualityOfService", wintypes.LPVOID),
    ]


class _OBJECT_DIRECTORY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Name", _UNICODE_STRING),
        ("TypeName", _UNICODE_STRING),
    ]


_last_valid_game_shm: bytes | None = None


def _find_live_game_window(game_pids: set[int]) -> tuple[int, int] | None:
    """Devuelve (hwnd, pid) de una ventana visible de Roblox perteneciente a game_pids."""
    if sys.platform != "win32" or not game_pids:
        return None
    try:
        user32 = ctypes.WinDLL("user32")
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        found: list[tuple[int, int]] = []
        fallback: list[tuple[int, int]] = []

        def _cb(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
            p_val = int(pid.value)
            if p_val not in game_pids:
                return True
            buf = ctypes.create_unicode_buffer(128)
            user32.GetWindowTextW(wintypes.HWND(hwnd), buf, 128)
            if buf.value == "Roblox":
                found.append((int(hwnd), p_val))
                return False
            fallback.append((int(hwnd), p_val))
            return True

        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        if found:
            return found[0]
        if fallback:
            return fallback[0]
    except Exception:
        pass
    return None


def clear_roblox_shared_memory(roblox_exe: str | None = None, *, debug: bool = False) -> int:
    """
    Repara las secciones de memoria compartida (.shm y RBXMAINWND-*) de Roblox en RAM
    SIN cerrar las ventanas de juego abiertas y SIN poner el HWND en 0 (poner HWND=0
    cuando .shm ya existe provoca que SingleInstanceGuard aborte tras 1.5s con
    'Invalid active client info').
    Si una ventana o proceso de bandeja murió dejando su HWND inválido mientras otra
    ventana de juego sigue abierta, restaura en .shm el HWND y PID de la ventana activa.
    """
    global _last_valid_game_shm
    if sys.platform != "win32":
        return 0

    game_pids: set[int] = set()
    for pid in list_roblox_pids():
        cmd = get_process_cmdline(pid)
        if cmd is None or "--launch-to-tray" not in cmd.lower():
            game_pids.add(pid)

    # Si no hay ventanas de juego abiertas, no tocar .shm (al cerrar el proceso de bandeja
    # Windows destruye la sección automáticamente).
    if not game_pids:
        return 0

    live_target = _find_live_game_window(game_pids)

    candidates: set[str] = {"RBXMAINWND-4DAAC10B-9C9A-4471-9218-07310329FD0D"}
    exe_path = roblox_exe or find_roblox_launcher()
    if exe_path:
        norm_exe = os.path.abspath(exe_path)
        candidates.add(norm_exe.replace("\\", "_") + ".shm")
        if len(norm_exe) >= 2 and norm_exe[1] == ":":
            alt_exe = (norm_exe[0].swapcase() + norm_exe[1:]).replace("\\", "_") + ".shm"
            candidates.add(alt_exe)

    repaired = 0
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenFileMappingW.restype = wintypes.HANDLE
        kernel32.MapViewOfFile.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_size_t,
        ]
        kernel32.MapViewOfFile.restype = wintypes.LPVOID
        kernel32.UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
        kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        user32 = ctypes.WinDLL("user32")
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL

        for name in candidates:
            is_shm = name.lower().endswith(".shm")
            h_mtx = 0
            mtx_acquired = False
            if is_shm:
                mtx_name = name[:-4] + ".mtx"
                # SYNCHRONIZE | MUTEX_MODIFY_STATE (0x00100001) para poder hacer ReleaseMutex
                h_mtx = kernel32.OpenMutexW(0x00100001, False, mtx_name)
                if h_mtx:
                    res = kernel32.WaitForSingleObject(h_mtx, 150)
                    mtx_acquired = res in (0x00000000, 0x00000080)
                    if not mtx_acquired:
                        kernel32.CloseHandle(h_mtx)
                        continue
            try:
                h_map = kernel32.OpenFileMappingW(0x0002 | 0x0004, False, name)  # WRITE | READ
                if h_map:
                    try:
                        ptr = kernel32.MapViewOfFile(h_map, 0x0002 | 0x0004, 0, 0, 64)
                        if ptr:
                            try:
                                hwnd = ctypes.c_uint64.from_address(ptr).value
                                pid = ctypes.c_uint32.from_address(ptr + 8).value if is_shm else 0
                                if is_shm and hwnd != 0 and pid in game_pids and user32.IsWindow(hwnd):
                                    # La sección .shm tiene una instancia de juego válida y viva:
                                    # guardar respaldo y NO modificarla.
                                    _last_valid_game_shm = bytes(ctypes.string_at(ptr, 64))
                                elif live_target is not None:
                                    live_hwnd, live_pid = live_target
                                    stale = (
                                        hwnd == 0
                                        or not user32.IsWindow(hwnd)
                                        or (is_shm and pid not in game_pids)
                                    )
                                    if stale:
                                        if is_shm:
                                            if _last_valid_game_shm and len(_last_valid_game_shm) == 64:
                                                ctypes.memmove(ptr, _last_valid_game_shm, 64)
                                            ctypes.c_uint64.from_address(ptr).value = live_hwnd
                                            ctypes.c_uint32.from_address(ptr + 8).value = live_pid
                                        else:
                                            ctypes.c_uint64.from_address(ptr).value = live_hwnd
                                        repaired += 1
                                        if debug:
                                            print(f"[shm] Restaurado HWND activo ({hex(live_hwnd)}) en: {name}")
                            finally:
                                kernel32.UnmapViewOfFile(ptr)
                    finally:
                        kernel32.CloseHandle(h_map)
            finally:
                if h_mtx:
                    if mtx_acquired:
                        kernel32.ReleaseMutex(h_mtx)
                    kernel32.CloseHandle(h_mtx)
    except Exception as exc:
        if debug:
            print(f"[shm] Aviso al verificar memoria compartida: {exc}")

    return repaired


def list_roblox_pids() -> list[int]:
    """Devuelve la lista de PIDs de procesos RobloxPlayerBeta.exe activos."""
    if sys.platform != "win32":
        return []
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
        if snap == wintypes.HANDLE(-1).value or not snap:
            return []
        pids: list[int] = []
        try:
            pe = _PROCESSENTRY32W()
            pe.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
                while True:
                    if pe.szExeFile.lower() == "robloxplayerbeta.exe":
                        pids.append(int(pe.th32ProcessID))
                    if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                        break
        finally:
            kernel32.CloseHandle(snap)
        return pids
    except Exception:
        return []


def get_process_cmdline(pid: int) -> str | None:
    """Obtiene la línea de comandos de un proceso usando NtQueryInformationProcess."""
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
        h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            buf = ctypes.create_string_buffer(16384)
            ret_len = wintypes.ULONG()
            # ProcessCommandLineInformation = 60
            status = ntdll.NtQueryInformationProcess(h, 60, buf, len(buf), ctypes.byref(ret_len))
            if status != 0:
                return None
            ustr = _UNICODE_STRING.from_buffer(buf)
            if not ustr.Buffer or ustr.Length == 0:
                return ""
            return ustr.Buffer[: ustr.Length // 2]
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return None


def disable_roblox_tray_autostart() -> None:
    """
    Desactiva el modo bandeja (MinimizeToTray / LaunchAtStartup) en appStorage.json
    y elimina la entrada '--launch-to-tray' de Roblox en el Registro de Windows.
    """
    if sys.platform != "win32":
        return
    if winreg is not None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            ) as key:
                val, _ = winreg.QueryValueEx(key, "RobloxPlayerBeta")
                if isinstance(val, str) and "--launch-to-tray" in val.lower():
                    winreg.DeleteValue(key, "RobloxPlayerBeta")
        except OSError:
            pass

    app_storage_path = os.path.expandvars(r"%LOCALAPPDATA%\Roblox\LocalStorage\appStorage.json")
    if os.path.isfile(app_storage_path):
        try:
            with open(app_storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                desired = {
                    "MinimizeToTray": "false",
                    "LaunchAtStartup": "false",
                    "LaunchAtStartupInitialized": "true",
                    "SystemTrayModalShown": "true",
                }
                if any(data.get(k) != v for k, v in desired.items()):
                    data.update(desired)
                    tmp = app_storage_path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, separators=(",", ":"))
                    os.replace(tmp, app_storage_path)
        except Exception:
            pass


def _terminate_pid(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if h:
            try:
                ok = bool(kernel32.TerminateProcess(h, 0))
                if ok:
                    return True
            finally:
                kernel32.CloseHandle(h)
    except Exception:
        pass
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=5,
        )
        return True
    except Exception:
        return False


def kill_roblox_tray_processes(debug: bool = False) -> int:
    """
    Termina procesos de RobloxPlayerBeta.exe que corren en modo bandeja (--launch-to-tray)
    y que acaparan ROBLOX_singletonEvent / ROBLOX_singletonMutex en segundo plano.
    """
    if sys.platform != "win32":
        return 0
    disable_roblox_tray_autostart()
    killed: list[int] = []
    for pid in list_roblox_pids():
        cmd = get_process_cmdline(pid)
        if cmd is not None and "--launch-to-tray" in cmd.lower():
            if debug:
                print(f"[singleton] Cerrando proceso de bandeja de Roblox (PID {pid})...")
            if _terminate_pid(pid):
                killed.append(pid)

    if killed:
        deadline = time.time() + 1.5
        while time.time() < deadline:
            remaining = set(list_roblox_pids()) & set(killed)
            if not remaining:
                break
            time.sleep(0.05)
    # Limpiar siempre la memoria compartida (.shm) por si el proceso de bandeja dejó su HWND muerto
    clear_roblox_shared_memory(debug=debug)
    return len(killed)


def close_all_roblox_processes() -> int:
    """Termina todos los procesos RobloxPlayerBeta.exe activos y espera su cierre."""
    pids = list_roblox_pids()
    if not pids:
        return 0
    for pid in pids:
        _terminate_pid(pid)
    deadline = time.time() + 2.5
    while time.time() < deadline:
        if not list_roblox_pids():
            break
        time.sleep(0.05)
    return len(pids)


# Hilo dedicado y persistente para mantener la propiedad (ownership) de los Mutex de Windows.
# En Windows, un Mutex pertenece al hilo que lo adquiere; si ese hilo termina, el sistema
# operativo lo marca como WAIT_ABANDONED (0x80) y Roblox lo toma inmediatamente.
_singleton_handles: list = []
_singleton_handles_map: dict[str, int] = {}
_singleton_event_locked: bool = False
_singleton_lock = threading.Lock()
_singleton_cmd_queue: "queue.Queue[tuple[str, queue.Queue]] | None" = None
_singleton_thread: threading.Thread | None = None


def _singleton_thread_loop(cmd_q: "queue.Queue[tuple[str, queue.Queue]]") -> None:
    global _singleton_event_locked
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    while True:
        cmd, reply_q = cmd_q.get()
        if cmd == "acquire":
            kill_roblox_tray_processes()
            for name in ("ROBLOX_singletonMutex", "ROBLOX_singletonEvent"):
                existing = _singleton_handles_map.get(name, 0)
                if existing:
                    # Asegurar que este hilo sea el propietario si estaba libre/abandonado
                    kernel32.WaitForSingleObject(existing, 0)
                    continue
                ctypes.set_last_error(0)
                h = kernel32.CreateMutexW(None, True, name)
                err = ctypes.get_last_error()
                if h:
                    if err == 183:  # ERROR_ALREADY_EXISTS
                        kernel32.WaitForSingleObject(h, 0)
                    _singleton_handles_map[name] = int(h)
                    if int(h) not in _singleton_handles:
                        _singleton_handles.append(int(h))

            _singleton_event_locked = (
                "ROBLOX_singletonMutex" in _singleton_handles_map
                and "ROBLOX_singletonEvent" in _singleton_handles_map
            )
            reply_q.put(_singleton_event_locked)


def _ensure_singleton_thread() -> "queue.Queue[tuple[str, queue.Queue]]":
    global _singleton_cmd_queue, _singleton_thread
    with _singleton_lock:
        if _singleton_thread is None or not _singleton_thread.is_alive() or _singleton_cmd_queue is None:
            _singleton_cmd_queue = queue.Queue()
            _singleton_thread = threading.Thread(
                target=_singleton_thread_loop,
                args=(_singleton_cmd_queue,),
                name="RobloxSingletonHolder",
                daemon=True,
            )
            _singleton_thread.start()
        return _singleton_cmd_queue


def grab_roblox_singleton() -> bool:
    """
    Toma y mantiene en un hilo persistente los objetos ROBLOX_singletonMutex y
    ROBLOX_singletonEvent como Mutexes para impedir que Roblox cierre otras instancias.
    Devuelve True si ambos singletons quedaron bloqueados por este proceso.
    """
    if sys.platform != "win32":
        return False
    try:
        cmd_q = _ensure_singleton_thread()
        reply_q: queue.Queue = queue.Queue()
        cmd_q.put(("acquire", reply_q))
        return bool(reply_q.get(timeout=5.0))
    except Exception:
        return False


def is_singleton_locked() -> bool:
    """Devuelve True si ROBLOX_singletonMutex y ROBLOX_singletonEvent están bloqueados."""
    return bool(_singleton_event_locked)


def has_blocking_roblox_process() -> bool:
    """
    Devuelve True si hay un RobloxPlayerBeta.exe abierto ANTES que este lanzador
    que mantiene ROBLOX_singletonEvent como Event e impide el modo multi-cuenta.
    """
    if grab_roblox_singleton():
        return False
    return len(list_roblox_pids()) > 0


def ensure_roblox_singleton(*, force_close_existing: bool = False) -> bool:
    """
    Asegura que los singletons de Roblox estén bloqueados por este proceso.
    Si force_close_existing=True, cierra cualquier Roblox previo para poder tomarlos.
    """
    if grab_roblox_singleton():
        return True
    if force_close_existing:
        close_all_roblox_processes()
        time.sleep(0.2)
        clear_roblox_shared_memory()
        return grab_roblox_singleton()
    return False


def repair_multi_instance_state(
    roblox_exe: str | None = None,
    *,
    debug: bool = False,
) -> tuple[bool, int, int]:
    """
    Repara el estado multi-cuenta SIN cerrar las ventanas de juego ya abiertas:
    1) Cierra procesos invisibles de bandeja (--launch-to-tray).
    2) Limpia las secciones de memoria compartida (.shm / RBXMAINWND) con HWNDs muertos.
    3) Re-adquiere los singletons (ROBLOX_singletonMutex y ROBLOX_singletonEvent).
    Devuelve (singleton_ok, tray_cerrados, shm_limpiados).
    """
    tray_killed = kill_roblox_tray_processes(debug=debug)
    shm_cleared = clear_roblox_shared_memory(roblox_exe, debug=debug)
    singleton_ok = grab_roblox_singleton()
    return singleton_ok, tray_killed, shm_cleared


def sync_roblox_cookies_dat(roblosecurity: str, *, debug: bool = False) -> bool:
    """
    Actualiza %LOCALAPPDATA%\\Roblox\\LocalStorage\\RobloxCookies.dat con la cookie
    .ROBLOSECURITY de la cuenta que se va a lanzar (cifrada con DPAPI).
    En Roblox 0.747+, DataModelStarterModule lee RobloxCookies.dat al arrancar (~0.8s)
    antes de que termine el canje de +gameinfo:{ticket} (~3.7s). Si RobloxCookies.dat
    tenía la cookie de la cuenta anterior, la nueva instancia se une con la cuenta equivocada.
    """
    if not _WIN32_AVAILABLE or sys.platform != "win32":
        return False
    cookie = roblosecurity.strip()
    if not cookie:
        return False

    cookies_path = os.path.expandvars(r"%LOCALAPPDATA%\Roblox\LocalStorage\RobloxCookies.dat")
    local_storage_dir = os.path.dirname(cookies_path)
    try:
        os.makedirs(local_storage_dir, exist_ok=True)
    except OSError:
        return False

    kept_entries: list[str] = []
    if os.path.isfile(cookies_path):
        try:
            with open(cookies_path, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
            b64_data = raw_json.get("CookiesData", "")
            if b64_data:
                _, dec_bytes = win32crypt.CryptUnprotectData(
                    base64.b64decode(b64_data), None, None, None, 0
                )
                text = dec_bytes.decode("utf-8", errors="replace")
                for part in text.split("; "):
                    part_s = part.strip()
                    if not part_s:
                        continue
                    cols = part_s.split("\t")
                    # Descartar .ROBLOSECURITY y RBXEventTrackerV2 de la cuenta anterior
                    if len(cols) >= 6 and cols[5] in (".ROBLOSECURITY", "RBXEventTrackerV2"):
                        continue
                    kept_entries.append(part_s)
        except Exception:
            kept_entries = []

    expiry = int(time.time()) + 31536000
    kept_entries.append(
        f"#HttpOnly_.roblox.com\tTRUE\t/\tTRUE\t{expiry}\t.ROBLOSECURITY\t{cookie}"
    )
    new_text = "; ".join(kept_entries)
    try:
        enc_bytes = win32crypt.CryptProtectData(
            new_text.encode("utf-8"), "", None, None, None, 0
        )
        payload = {
            "CookiesVersion": "1",
            "CookiesData": base64.b64encode(enc_bytes).decode("ascii"),
        }
        tmp_path = cookies_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp_path, cookies_path)
        if debug:
            print("[cookies] RobloxCookies.dat sincronizado para la cuenta actual.")
        return True
    except Exception as exc:
        if debug:
            print(f"[cookies] No se pudo actualizar RobloxCookies.dat: {exc}")
        return False


def launch_account(
    account: dict,
    roblox_exe: str,
    *,
    place_id: str,
    job_id: str | None = None,
    delay: float = 0.0,
    debug: bool = False,
    max_retries: int = 2,
) -> bool:
    """Lanza una instancia de Roblox autenticada para la cuenta dada."""
    name = account["name"]
    cookie = account["roblosecurity"]

    if not isinstance(cookie, str) or not cookie.strip():
        print(f"[{name}] ERROR: cookie vacía.")
        return False
    if "TU_COOKIE_AQUI" in cookie or "TU_COOKIE" in cookie:
        print(
            f"[{name}] ERROR: cookie parece placeholder. "
            f"Cambiala por tu .ROBLOSECURITY real."
        )
        return False

    if delay > 0:
        time.sleep(delay)

    singleton_ok = grab_roblox_singleton()
    if debug:
        if singleton_ok:
            print(f"[{name}] singleton mutex/event bloqueados OK.")
        else:
            print(f"[{name}] AVISO: singleton no pudo bloquearse (¿Roblox ya estaba abierto antes?).")

    print(f"[{name}] Obteniendo auth ticket...")
    ticket = get_auth_ticket(cookie, debug=debug, max_retries=max_retries)
    if not ticket:
        print(
            f"[{name}] ERROR: No se pudo obtener el auth ticket. "
            f"Revisa que la cookie sea correcta/este vigente."
        )
        return False

    place_launcher_url = build_place_launcher_url(place_id, job_id)
    encoded_place_launcher_url = quote(place_launcher_url, safe="")

    for launch_try in range(2):
        if launch_try > 0:
            if debug:
                print(f"[{name}] Reintentando inicio tras reparar estado multi-instancia...")
            repair_multi_instance_state(roblox_exe, debug=debug)
            ticket = get_auth_ticket(cookie, debug=debug, max_retries=max_retries)
            if not ticket:
                return False

        roblox_url = (
            f"roblox-player:1+launchmode:play"
            f"+gameinfo:{ticket}"
            f"+launchtime:{int(time.time() * 1000)}"
            f"+placelauncherurl:{encoded_place_launcher_url}"
            f"+browsertrackerid:0+robloxLocale:en_us+gameLocale:en_us"
        )

        try:
            if debug:
                print(f"[{name}] Lanzando via protocolo roblox-player (ticket oculto).")

            clear_roblox_shared_memory(roblox_exe, debug=debug)
            sync_roblox_cookies_dat(cookie, debug=debug)
            pids_before = set(list_roblox_pids())

            opened = open_roblox_player_uri(roblox_url)
            if not opened:
                subprocess.Popen([roblox_exe, roblox_url])

            # Esperar a que el nuevo proceso RobloxPlayerBeta.exe aparezca y lea RobloxCookies.dat
            spawn_deadline = time.time() + 3.5
            spawned_pid: int | None = None
            while time.time() < spawn_deadline:
                new_pids = set(list_roblox_pids()) - pids_before
                if new_pids:
                    spawned_pid = next(iter(new_pids))
                    break
                time.sleep(0.1)

            if spawned_pid is not None:
                # Dar margen para que el nuevo proceso cree su ventana (~1.8s) y complete loadAuthTokenFromDisk
                time.sleep(2.2)
                if spawned_pid not in set(list_roblox_pids()):
                    # El proceso se cerró prematuramente (ej. colisión de .shm con proceso de bandeja)
                    if launch_try == 0:
                        continue
                    print(f"[{name}] ERROR: el proceso de Roblox se cerró al iniciar.")
                    return False
                # Guardar respaldo del .shm válido recién escrito por esta instancia de juego
                clear_roblox_shared_memory(roblox_exe, debug=debug)
            else:
                time.sleep(1.0)
                if launch_try == 0:
                    continue

            print(f"[{name}] Instancia iniciada correctamente.")
            return True
        except Exception as e:
            print(f"[{name}] ERROR al iniciar: {e}")
            return False

    return False


def launch_accounts(
    accounts: list[dict],
    roblox_exe: str,
    *,
    place_id: str,
    fps_limit: int = 0,
    auto_join: dict | None = None,
    debug: bool = False,
    settings: dict | None = None,
    on_progress=None,
) -> tuple[list[str], list[str]]:
    """
    Lanza cuentas secuencialmente con delay configurable.
    on_progress(index, total, account_name, status) opcional.
    Devuelve (exitosas, fallidas).
    """
    cfg = settings or app_storage.get_settings()
    max_retries = cfg.get("auth_max_retries", 2)
    ok_names: list[str] = []
    fail_names: list[str] = []
    total = len(accounts)
    fps_limit = roblox_fps.normalize_fps_limit(fps_limit)
    join_cfg = roblox_servers.normalize_auto_join(auto_join)

    shared_job_id: str | None = None
    if join_cfg.get("enabled") and str(place_id).strip() not in ("", "0"):
        max_wait_sec = max(0, min(600, int(cfg.get("auto_join_wait_sec", 60) or 60)))
        poll_sec = max(2, min(20, int(cfg.get("auto_join_poll_sec", 5) or 5)))
        deadline = time.time() + max_wait_sec
        attempt = 0
        last_err: str | None = None

        while True:
            attempt += 1
            if on_progress:
                on_progress(0, total, "", f"finding_server (try {attempt})")

            shared_job_id, join_err = roblox_servers.find_best_job_id(
                place_id,
                join_cfg,
                debug=debug,
            )
            if shared_job_id:
                break

            last_err = join_err or "No se pudo elegir servidor."
            now = time.time()
            if now >= deadline:
                break

            # Si el usuario no fijó límite de jugadores, no tiene sentido reintentar.
            if int(join_cfg.get("max_players", 0) or 0) <= 0:
                break

            remaining = int(max(0, deadline - now))
            if debug:
                print(f"[auto-join] intento {attempt} sin éxito: {last_err}. Reintentando en {poll_sec}s...")
            if on_progress:
                on_progress(0, total, "", f"waiting_server ({remaining}s left)")
            time.sleep(poll_sec)

        if not shared_job_id:
            reason = last_err or "No se encontró servidor compatible."
            print(f"[auto-join] AVISO: {reason} — uniendo a servidor aleatorio.")

    for i, account in enumerate(accounts):
        name = account["name"]
        if on_progress:
            on_progress(i, total, name, "launching")

        if fps_limit > 0:
            ok_fps, fps_err = roblox_fps.apply_fps_limit(fps_limit, roblox_exe=roblox_exe, debug=debug)
            if not ok_fps and debug and fps_err:
                print(f"[{name}] AVISO FPS: {fps_err}")

        delay = compute_launch_delay(i, total, cfg)
        success = launch_account(
            account,
            roblox_exe,
            place_id=place_id,
            job_id=shared_job_id,
            delay=delay,
            debug=debug,
            max_retries=max_retries,
        )
        if success:
            ok_names.append(name)
            status = "ok"
        else:
            fail_names.append(name)
            status = "failed"

        if on_progress:
            on_progress(i + 1, total, name, status)

    return ok_names, fail_names


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MoreRobAccounts — lanzador multi-cuenta de Roblox"
    )
    parser.add_argument("--list", action="store_true", help="Lista las cuentas guardadas")
    parser.add_argument("--add", action="store_true", help="Agrega una cuenta interactivamente")
    parser.add_argument(
        "--login-browser",
        action="store_true",
        help="Inicio de sesion seguro en navegador (sin pegar cookie)",
    )
    parser.add_argument(
        "--remove",
        nargs="+",
        metavar="NOMBRE",
        help="Elimina una o mas cuentas por nombre",
    )
    parser.add_argument("--debug", action="store_true", help="Muestra detalles del error de auth ticket")
    parser.add_argument(
        "--place-id",
        default="0",
        help="PlaceId del juego al que entrar (ej. 1234). Si no lo sabes, ponlo en 0 y prueba, pero puede no funcionar.",
    )
    parser.add_argument(
        "--account",
        nargs="+",
        metavar="NOMBRE",
        help="Lanza solo las cuentas especificadas",
    )
    args = parser.parse_args()

    if args.add or args.login_browser:
        add_account_interactive()
        return

    if args.remove:
        removed, not_found = remove_accounts(args.remove)
        if removed:
            print("Cuentas eliminadas:")
            for name in removed:
                print(f"  - {name}")
        if not_found:
            print("No encontradas:")
            for name in not_found:
                print(f"  - {name}")
        if not removed and not not_found:
            print("No se especificaron nombres para eliminar.")
        return

    accounts = load_accounts()

    if args.list:
        if not accounts:
            print("No hay cuentas guardadas. Usa --add para agregar una.")
        else:
            print("\nCuentas guardadas (cookies cifradas en disco):")
            for a in accounts:
                print(f"  - {a['name']}")
        return

    if args.account:
        names = set(args.account)
        accounts = [a for a in accounts if a["name"] in names]
        missing = names - {a["name"] for a in accounts}
        if missing:
            print(f"Advertencia: cuentas no encontradas: {', '.join(missing)}")

    if not accounts:
        print("No hay cuentas para lanzar. Usa --add para agregar cuentas.")
        sys.exit(1)

    roblox_exe = find_roblox_launcher()
    if not roblox_exe:
        print(
            "ERROR: No se encontró el ejecutable de Roblox.\n"
            "Asegúrate de que Roblox esté instalado en tu PC."
        )
        sys.exit(1)

    print(f"Roblox encontrado en: {roblox_exe}")
    print(f"Lanzando {len(accounts)} cuenta(s)...\n")
    ok, fail = launch_accounts(accounts, roblox_exe, place_id=args.place_id, debug=args.debug)
    print(f"\nCompletado: {len(ok)} OK, {len(fail)} fallidas.")
    if fail:
        print("Fallidas:", ", ".join(fail))

    # IMPORTANTE: mantener el script vivo mientras haya instancias de Roblox
    # abiertas. Los mutex/event handles se liberan al cerrarse este proceso,
    # lo que haría que Roblox detecte la restriccion de instancia unica.
    if _WIN32_AVAILABLE and _singleton_handles:
        print("Manteniendo singleton activo. Cierra esta ventana cuando quieras cerrar Roblox.")
        print("(Ctrl+C para salir)")
        try:
            roblox_running = True
            while roblox_running:
                time.sleep(5)
                procs = [p for p in subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq RobloxPlayerBeta.exe", "/NH", "/FO", "CSV"],
                    capture_output=True, text=True
                ).stdout.splitlines() if "RobloxPlayerBeta" in p]
                if not procs:
                    print("\nTodas las instancias de Roblox se cerraron. Saliendo.")
                    roblox_running = False
        except KeyboardInterrupt:
            print("\nScript detenido por el usuario.")


if __name__ == "__main__":
    main()
