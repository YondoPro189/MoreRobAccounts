"""
Inicio de sesion seguro: el usuario inicia sesion en roblox.com dentro de un
navegador aislado. La cookie .ROBLOSECURITY nunca pasa por el portapapeles.
"""

from __future__ import annotations

import os
import sys
import time

import requests

ROBLOX_LOGIN_URL = "https://www.roblox.com/login"
AUTH_CHECK_URL = "https://users.roblox.com/v1/users/authenticated"

WIN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
)

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
"""


def _browser_launch_channels() -> tuple[str | None, ...]:
    if sys.platform == "win32":
        return ("msedge", "chrome", None)
    return (None, "msedge")


def is_browser_login_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def _pick_roblosecurity(cookies: list[dict]) -> str | None:
    for cookie in cookies:
        if cookie.get("name") == ".ROBLOSECURITY":
            value = cookie.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _gather_roblosecurity(context) -> str | None:
    """Busca la cookie en todos los dominios conocidos de Roblox."""
    urls = (
        "https://www.roblox.com",
        "https://roblox.com",
        "https://auth.roblox.com",
    )
    seen: set[str] = set()
    candidates: list[str] = []

    for url in urls:
        try:
            batch = context.cookies(url)
        except Exception:
            batch = []
        cookie = _pick_roblosecurity(batch)
        if cookie and cookie not in seen:
            seen.add(cookie)
            candidates.append(cookie)

    try:
        cookie = _pick_roblosecurity(context.cookies())
    except Exception:
        cookie = None
    if cookie and cookie not in seen:
        candidates.append(cookie)

    return candidates[-1] if candidates else None


def _verify_session(cookie: str, *, attempts: int = 4) -> str | None:
    """Devuelve el nombre de usuario de Roblox si la cookie es valida."""
    headers = {
        "Referer": "https://www.roblox.com/",
        "User-Agent": WIN_USER_AGENT,
        "Accept": "application/json",
    }
    cookies = {".ROBLOSECURITY": cookie}

    for attempt in range(attempts):
        try:
            resp = requests.get(
                AUTH_CHECK_URL,
                cookies=cookies,
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        except requests.RequestException:
            pass
        if attempt + 1 < attempts:
            time.sleep(1.2)
    return None


def _page_looks_logged_in(page) -> bool:
    url = page.url.lower()
    if "/login" in url or "/signup" in url or "/createaccount" in url:
        return False
    return "roblox.com" in url


def _launch_browser(playwright):
    launch_errors: list[str] = []
    launch_kwargs = {
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled"],
        "ignore_default_args": ["--enable-automation"],
    }

    for channel in _browser_launch_channels():
        try:
            if channel:
                return playwright.chromium.launch(channel=channel, **launch_kwargs), None
            return playwright.chromium.launch(**launch_kwargs), None
        except Exception as exc:
            launch_errors.append(f"{channel or 'chromium'}: {exc}")

    hint = "No se pudo abrir el navegador."
    if sys.platform == "win32":
        hint += "\nAsegurate de tener Microsoft Edge o Google Chrome instalado."
    else:
        hint += "\nPrueba: playwright install chromium"
    if launch_errors:
        hint += f"\n\nDetalle: {launch_errors[-1]}"
    return None, hint


def _write_login_log(message: str) -> None:
    try:
        from launcher import get_app_dir

        path = os.path.join(get_app_dir(), "login_debug.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def login_via_browser(*, timeout_sec: int = 300) -> tuple[str | None, str | None, str | None]:
    """
    Abre un navegador para iniciar sesion en Roblox.

    Returns:
        (cookie, roblox_username, error_message)
    """
    if not is_browser_login_available():
        return (
            None,
            None,
            "Login por navegador no disponible.\n"
            "Descarga la version COMPLETA (no la LITE) desde GitHub Releases.",
        )

    from playwright.sync_api import sync_playwright

    browser = None
    try:
        with sync_playwright() as playwright:
            browser, launch_error = _launch_browser(playwright)
            if browser is None:
                _write_login_log(launch_error or "launch failed")
                return None, None, launch_error

            context = browser.new_context(
                viewport={"width": 1100, "height": 780},
                locale="es-ES",
                user_agent=WIN_USER_AGENT,
            )
            context.add_init_script(STEALTH_INIT_SCRIPT)
            page = context.new_page()
            page.goto(ROBLOX_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

            deadline = time.time() + timeout_sec
            last_cookie: str | None = None
            logged_in_page = False

            while time.time() < deadline:
                if page.is_closed():
                    return None, None, "Ventana de inicio de sesion cerrada."

                if _page_looks_logged_in(page):
                    logged_in_page = True

                cookie = _gather_roblosecurity(context)
                if cookie and (cookie != last_cookie or logged_in_page):
                    username = _verify_session(cookie)
                    if username:
                        _write_login_log(f"login ok user={username}")
                        return cookie, username, None
                    last_cookie = cookie

                time.sleep(0.6)

            _write_login_log("timeout waiting for session")
            return None, None, (
                "Tiempo de espera agotado.\n"
                "Completa el inicio de sesion en el navegador e intenta de nuevo."
            )
    except Exception as exc:
        _write_login_log(f"exception: {exc}")
        return None, None, f"Error durante el inicio de sesion:\n{exc}"
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
