"""Anti-AFK para Roblox: envía pulsaciones de tecla periódicas a ventanas de Roblox."""

from __future__ import annotations

import threading
import time
from typing import Callable

try:
    import win32api
    import win32con
    import win32gui
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

# Roblox kickea por inactividad ~20 min; 4 min de intervalo es más que suficiente.
DEFAULT_INTERVAL_SEC = 240

_VK_SPACE = 0x20

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_lock = threading.Lock()


def is_available() -> bool:
    """Verdadero si pywin32 está disponible (siempre lo está en esta app)."""
    return _WIN32_AVAILABLE


def is_running() -> bool:
    """Verdadero si el anti-AFK está activo en este momento."""
    with _lock:
        return _thread is not None and _thread.is_alive()


def _find_roblox_windows() -> list[int]:
    """Devuelve los handles de las ventanas visibles cuyo título es 'Roblox'."""
    handles: list[int] = []

    def _cb(hwnd: int, _lp: object) -> bool:
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == "Roblox":
            handles.append(hwnd)
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return handles


def _send_space(hwnd: int) -> None:
    """Envía WM_KEYDOWN + WM_KEYUP de Space a la ventana indicada."""
    scan = win32api.MapVirtualKey(_VK_SPACE, 0)
    lp_down = 1 | (scan << 16)
    lp_up = 1 | (scan << 16) | (1 << 30) | (1 << 31)
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, _VK_SPACE, lp_down)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, _VK_SPACE, lp_up)


def _worker(interval_sec: float, on_tick: Callable[[int], None] | None) -> None:
    """Hilo del anti-AFK: espera el intervalo y pulsa Space en cada ventana."""
    while not _stop_event.wait(interval_sec):
        windows = _find_roblox_windows()
        for hwnd in windows:
            try:
                _send_space(hwnd)
            except Exception:
                pass
        if on_tick:
            try:
                on_tick(len(windows))
            except Exception:
                pass


def start(
    interval_sec: float = DEFAULT_INTERVAL_SEC,
    on_tick: Callable[[int], None] | None = None,
) -> bool:
    """
    Inicia el anti-AFK en un hilo daemon.
    Devuelve False si pywin32 no está disponible o si ya estaba corriendo.
    """
    if not _WIN32_AVAILABLE:
        return False
    with _lock:
        global _thread
        if _thread is not None and _thread.is_alive():
            return False
        _stop_event.clear()
        _thread = threading.Thread(
            target=_worker,
            args=(interval_sec, on_tick),
            daemon=True,
            name="anti-afk",
        )
        _thread.start()
    return True


def stop() -> None:
    """Detiene el anti-AFK (la señal llega en el próximo intervalo de espera)."""
    _stop_event.set()
    with _lock:
        global _thread
        _thread = None
