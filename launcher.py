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

import json
import os
import sys
import time
import subprocess
import threading
import argparse
import requests
from urllib.parse import quote

import app_storage
import roblox_fps
from app_storage import ACCOUNTS_FORMAT_VERSION
from security import SecurityError, decrypt_secret, encrypt_secret, is_encryption_available

try:
    import win32event
    import win32api
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
    """Busca el launcher de Roblox en las ubicaciones conocidas de Windows."""
    candidates = [
        ROBLOX_LAUNCHER,
        # Versiones instaladas en carpetas versionadas
        *[
            os.path.join(root, f)
            for root, dirs, files in os.walk(
                os.path.expandvars(r"%LOCALAPPDATA%\Roblox\Versions")
            )
            if os.path.isdir(os.path.expandvars(r"%LOCALAPPDATA%\Roblox\Versions"))
            for f in files
            if f == "RobloxPlayerBeta.exe"
        ],
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
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
    Devuelve (estado, mensaje) donde estado es 'ok', 'already' o 'fail'.
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

    try:
        payload = resp.json()
        errors = payload.get("errors") or []
        for err in errors:
            if not isinstance(err, dict):
                continue
            message = str(err.get("message", "")).lower()
            if "already" in message or "follow" in message and "invalid" not in message:
                return "already", None
    except ValueError:
        payload = None

    body = (resp.text or "").lower()
    if resp.status_code == 400 and "already" in body:
        return "already", None

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
        else:
            fail_names.append(name)
            prog = "failed"
            if debug and msg:
                print(f"[{name}] follow error: {msg}")

        if on_progress:
            on_progress(i + 1, total, name, prog)

    if on_progress and display_name:
        on_progress(total, total, display_name, "done")

    return ok_names, already_names, fail_names, None


def compute_launch_delay(index: int, total: int, settings: dict | None = None) -> float:
    """Espera entre lanzamientos. Tras N cuentas (default 3) usa delay configurable."""
    cfg = settings or app_storage.get_settings()
    threshold = cfg.get("delay_after_accounts", 3)
    delay_sec = float(cfg.get("launch_delay_sec", 3))
    if index <= 0:
        return 0.0
    if total > threshold:
        return delay_sec
    return 0.5


def open_roblox_player_uri(uri: str) -> bool:
    """
    Abre el esquema roblox-player: usando el manejador registrado en Windows.
    """
    try:
        os.startfile(uri)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


# Los handles se guardan aquí para que no sean garbage-collected
# mientras el launcher esté abierto.
_singleton_handles: list = []
_singleton_lock = threading.Lock()


def grab_roblox_singleton() -> bool:
    """
    Crea o toma los objetos del sistema con los que Roblox detecta si ya
    hay una instancia corriendo (ROBLOX_singletonMutex y ROBLOX_singletonEvent).
    Al tenerlos nosotros primero, Roblox no puede usarlos para impedir la
    segunda instancia.
    Devuelve True si pywin32 está disponible, False si no.
    """
    if not _WIN32_AVAILABLE:
        return False

    with _singleton_lock:
        for name in ("ROBLOX_singletonMutex", "ROBLOX_singletonEvent"):
            try:
                h = win32event.CreateMutex(None, False, name)
                # Si ya existe (ERROR_ALREADY_EXISTS) igual guardamos el handle
                # para que permanezca abierto durante todo el proceso.
                _singleton_handles.append(h)
            except Exception:
                pass
    return True


def launch_account(
    account: dict,
    roblox_exe: str,
    *,
    place_id: str,
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

    if delay:
        time.sleep(delay)

    print(f"[{name}] Obteniendo auth ticket...")
    ticket = get_auth_ticket(cookie, debug=debug, max_retries=max_retries)
    if not ticket:
        print(
            f"[{name}] ERROR: No se pudo obtener el auth ticket. "
            f"Revisa que la cookie sea correcta/este vigente."
        )
        return False

    place_launcher_url = (
        f"https://assetgame.roblox.com/game/PlaceLauncher.ashx"
        f"?request=RequestGame&browserTrackerId=0&placeId={place_id}&isPlayTogetherGame=false"
    )
    encoded_place_launcher_url = quote(place_launcher_url, safe="")

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

        singleton_ok = grab_roblox_singleton()
        if debug:
            if singleton_ok:
                print(f"[{name}] singleton mutex/event tomados OK.")
            else:
                print(f"[{name}] AVISO: pywin32 no disponible, singleton no bloqueado.")

        time.sleep(0.5)

        opened = open_roblox_player_uri(roblox_url)
        if not opened:
            subprocess.Popen([roblox_exe, roblox_url])

        print(f"[{name}] Instancia iniciada correctamente.")
        return True
    except Exception as e:
        print(f"[{name}] ERROR al iniciar: {e}")
        return False


def launch_accounts(
    accounts: list[dict],
    roblox_exe: str,
    *,
    place_id: str,
    fps_limit: int = 0,
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
