"""Límite de FPS en Roblox vía GlobalBasicSettings_*.xml (FramerateCap)."""

from __future__ import annotations

import os
import re

FRAMERATE_CAP_TAG = re.compile(
    r'(<int\s+name="FramerateCap">)\s*\d+\s*(</int>)',
    re.IGNORECASE,
)

# 0 = no modificar
FPS_PRESETS = (0, 5, 10, 15, 30, 60, 120, 144, 240)


def normalize_fps_limit(value: object) -> int:
    try:
        fps = int(value)
    except (TypeError, ValueError):
        fps = 0
    if fps <= 0:
        return 0
    return max(5, min(240, fps))


def fps_label(fps: int) -> str:
    if fps <= 0:
        return "Default"
    return f"{fps} FPS"


def global_basic_settings_paths() -> list[str]:
    roblox_dir = os.path.expandvars(r"%LOCALAPPDATA%\Roblox")
    if not os.path.isdir(roblox_dir):
        return []
    paths: list[str] = []
    for name in os.listdir(roblox_dir):
        if name.startswith("GlobalBasicSettings_") and name.lower().endswith(".xml"):
            paths.append(os.path.join(roblox_dir, name))
    paths.sort(key=lambda p: (0 if p.endswith("_13.xml") else 1, p))
    return paths


def _patch_framerate_cap_xml(content: str, fps: int) -> tuple[str, bool]:
    if FRAMERATE_CAP_TAG.search(content):
        new_content = FRAMERATE_CAP_TAG.sub(rf"\g<1>{fps}\g<2>", content, count=1)
        return new_content, True

    anchor = '<string name="DefaultCameraID"></string>'
    insert = f'{anchor}\n\t\t\t<int name="FramerateCap">{fps}</int>'
    if anchor in content:
        return content.replace(anchor, insert, 1), True

    return content, False


def apply_fps_limit(
    fps_limit: int,
    *,
    roblox_exe: str | None = None,
    debug: bool = False,
) -> tuple[bool, str | None]:
    """
    Escribe FramerateCap en GlobalBasicSettings_*.xml antes de lanzar Roblox.
    fps_limit=0 no modifica archivos.
    """
    _ = roblox_exe  # reservado; el XML es global en %LOCALAPPDATA%\\Roblox
    fps_limit = normalize_fps_limit(fps_limit)
    if fps_limit <= 0:
        return True, None

    paths = global_basic_settings_paths()
    if not paths:
        return False, "No se encontró GlobalBasicSettings_*.xml en %LOCALAPPDATA%\\Roblox"

    written: list[str] = []
    errors: list[str] = []

    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            new_content, ok = _patch_framerate_cap_xml(content, fps_limit)
            if not ok:
                errors.append(f"{path}: no se encontró FramerateCap.")
                continue
            if new_content != content:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new_content)
            written.append(path)
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    if not written:
        return False, errors[0] if errors else "No se pudo escribir GlobalBasicSettings."

    if debug:
        print(f"[fps] FramerateCap={fps_limit} en {len(written)} archivo(s).")
    return True, None
