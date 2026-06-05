"""
Inicio de sesion seguro: el usuario inicia sesion en roblox.com dentro de un
navegador aislado. La cookie .ROBLOSECURITY nunca pasa por el portapapeles.

Requisito opcional:
  pip install playwright
  playwright install chromium
  (si Chromium no esta instalado, se usa Edge como respaldo)
"""

from __future__ import annotations

import time

import requests

ROBLOX_LOGIN_URL = "https://www.roblox.com/login"
AUTH_CHECK_URL = "https://users.roblox.com/v1/users/authenticated"


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
            if isinstance(value, str) and value:
                return value
    return None


def _verify_session(cookie: str) -> str | None:
    """Devuelve el nombre de usuario de Roblox si la cookie es valida."""
    try:
        resp = requests.get(
            AUTH_CHECK_URL,
            cookies={".ROBLOSECURITY": cookie},
            headers={"Referer": "https://www.roblox.com/"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        name = data.get("name")
        return name if isinstance(name, str) and name else None
    except requests.RequestException:
        return None


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
            "Instala Playwright:\n  pip install playwright\n  playwright install chromium",
        )

    from playwright.sync_api import sync_playwright

    browser = None
    try:
        with sync_playwright() as playwright:
            launch_errors: list[str] = []

            # Chromium de Playwright primero; Edge solo si no tienes Chromium instalado.
            for channel in (None, "msedge"):
                try:
                    if channel:
                        browser = playwright.chromium.launch(
                            headless=False,
                            channel=channel,
                        )
                    else:
                        browser = playwright.chromium.launch(headless=False)
                    break
                except Exception as exc:
                    launch_errors.append(str(exc))
                    browser = None

            if browser is None:
                hint = (
                    "No se pudo abrir el navegador.\n"
                    "Prueba: playwright install chromium"
                )
                if launch_errors:
                    hint += f"\n\nDetalle: {launch_errors[-1]}"
                return None, None, hint

            context = browser.new_context(
                viewport={"width": 1100, "height": 780},
                locale="es-ES",
            )
            page = context.new_page()
            page.goto(ROBLOX_LOGIN_URL, wait_until="domcontentloaded")

            deadline = time.time() + timeout_sec
            last_cookie: str | None = None

            while time.time() < deadline:
                if page.is_closed():
                    return None, None, "Ventana de inicio de sesion cerrada."

                cookies = context.cookies(["https://www.roblox.com", "https://roblox.com"])
                cookie = _pick_roblosecurity(cookies)
                if cookie and cookie != last_cookie:
                    username = _verify_session(cookie)
                    if username:
                        return cookie, username, None
                    last_cookie = cookie

                time.sleep(0.8)

            return None, None, "Tiempo de espera agotado. Completa el inicio de sesion e intenta de nuevo."
    except Exception as exc:
        return None, None, f"Error durante el inicio de sesion:\n{exc}"
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
