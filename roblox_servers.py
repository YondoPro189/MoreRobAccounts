"""Consulta servidores públicos de Roblox y elige instancia (JobId) para auto-join."""

from __future__ import annotations

import random
from typing import Any

import requests

_ROBLOX_API_HEADERS = {
    "Referer": "https://www.roblox.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
}

AUTO_JOIN_DEFAULTS = {
    "enabled": False,
    "max_players": 0,
    "top_n": 3,
    "max_pages": 2,
}


def normalize_auto_join(raw: dict | None) -> dict:
    prefs = dict(AUTO_JOIN_DEFAULTS)
    if not isinstance(raw, dict):
        return prefs
    if "enabled" in raw:
        prefs["enabled"] = bool(raw["enabled"])
    for key in ("max_players", "top_n", "max_pages"):
        if key not in raw:
            continue
        try:
            prefs[key] = int(raw[key])
        except (TypeError, ValueError):
            pass
    prefs["max_players"] = max(0, min(200, prefs["max_players"]))
    prefs["top_n"] = max(1, min(10, prefs["top_n"]))
    prefs["max_pages"] = max(1, min(5, prefs["max_pages"]))
    return prefs


def normalize_place_id(place_id: str | int) -> tuple[int | None, str | None]:
    try:
        pid = int(place_id)
    except (TypeError, ValueError):
        return None, "Place ID invalido."
    if pid <= 0:
        return None, "Place ID debe ser mayor que 0."
    return pid, None


def fetch_public_servers(
    place_id: int,
    *,
    limit: int = 100,
    exclude_full: bool = True,
    max_pages: int = 2,
) -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0
    max_pages = max(1, min(5, max_pages))

    while pages < max_pages:
        params: dict[str, str | int] = {
            "sortOrder": "Asc",
            "limit": min(100, max(10, limit)),
            "excludeFullGames": str(exclude_full).lower(),
        }
        if cursor:
            params["cursor"] = cursor

        try:
            resp = requests.get(
                f"https://games.roblox.com/v1/games/{place_id}/servers/Public",
                params=params,
                headers=_ROBLOX_API_HEADERS,
                timeout=15,
            )
        except requests.RequestException:
            break

        if resp.status_code != 200:
            break

        try:
            payload = resp.json()
        except ValueError:
            break

        batch = payload.get("data") or []
        if isinstance(batch, list):
            servers.extend(s for s in batch if isinstance(s, dict))

        cursor = payload.get("nextPageCursor")
        pages += 1
        if not cursor:
            break

    return servers


def select_job_id(servers: list[dict[str, Any]], prefs: dict) -> str | None:
    if not servers:
        return None

    max_players_filter = int(prefs.get("max_players", 0) or 0)
    candidates: list[tuple[int, str]] = []

    for server in servers:
        job_id = server.get("id")
        if not isinstance(job_id, str) or not job_id:
            continue
        playing = int(server.get("playing", 0) or 0)
        capacity = int(server.get("maxPlayers", 0) or 0)
        if max_players_filter > 0 and playing > max_players_filter:
            continue
        if capacity > 0 and playing >= capacity:
            continue
        candidates.append((playing, job_id))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    top_n = max(1, min(10, int(prefs.get("top_n", 3) or 3)))
    pool = candidates[:top_n]
    return random.choice(pool)[1]


def server_summary(servers: list[dict[str, Any]], job_id: str) -> str:
    for server in servers:
        if server.get("id") == job_id:
            playing = int(server.get("playing", 0) or 0)
            capacity = int(server.get("maxPlayers", 0) or 0)
            if capacity > 0:
                return f"{playing}/{capacity} jugadores"
            return f"{playing} jugadores"
    return "servidor elegido"


def find_best_job_id(
    place_id: str,
    prefs: dict | None = None,
    *,
    debug: bool = False,
) -> tuple[str | None, str | None]:
    """
    Devuelve (job_id, error). Si auto-join está desactivado, (None, None).
    """
    cfg = normalize_auto_join(prefs)
    if not cfg.get("enabled"):
        return None, None

    normalized_place_id, err = normalize_place_id(place_id)
    if err or normalized_place_id is None:
        return None, err

    servers = fetch_public_servers(
        normalized_place_id,
        exclude_full=True,
        max_pages=int(cfg.get("max_pages", 2) or 2),
    )
    if not servers:
        return None, "No se encontraron servidores públicos disponibles."

    job_id = select_job_id(servers, cfg)
    if not job_id:
        max_p = int(cfg.get("max_players", 0) or 0)
        if max_p > 0:
            return None, f"Ningún servidor con ≤{max_p} jugadores."
        return None, "No se pudo elegir un servidor."

    if debug:
        summary = server_summary(servers, job_id)
        short_id = job_id[:8] + "…" if len(job_id) > 8 else job_id
        print(f"[auto-join] JobId={short_id} ({summary})")

    return job_id, None
