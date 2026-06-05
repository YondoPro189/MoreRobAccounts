"""Persistencia unificada: cuentas, familias, historial Place ID y ajustes."""

from __future__ import annotations

import json
import os
from copy import deepcopy

from security import SecurityError, decrypt_secret, encrypt_secret, is_encryption_available

ACCOUNTS_FORMAT_VERSION = 3
MAX_PLACE_HISTORY = 20

DEFAULT_SETTINGS = {
    "launch_delay_sec": 3,
    "delay_after_accounts": 3,
    "auth_max_retries": 2,
    "use_family_place_id": True,
}


def _accounts_file() -> str:
    from launcher import get_accounts_file

    return get_accounts_file()


def default_app_data() -> dict:
    return {
        "version": ACCOUNTS_FORMAT_VERSION,
        "settings": deepcopy(DEFAULT_SETTINGS),
        "place_history": [],
        "families": [],
        "accounts": [],
    }


def _normalize_settings(raw: dict | None) -> dict:
    settings = deepcopy(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        for key in ("launch_delay_sec", "delay_after_accounts", "auth_max_retries"):
            if key in raw:
                try:
                    settings[key] = int(raw[key])
                except (TypeError, ValueError):
                    pass
        if "use_family_place_id" in raw:
            settings["use_family_place_id"] = bool(raw["use_family_place_id"])
    settings["auth_max_retries"] = max(1, min(5, settings["auth_max_retries"]))
    settings["launch_delay_sec"] = max(0, min(60, settings["launch_delay_sec"]))
    settings["delay_after_accounts"] = max(1, min(20, settings["delay_after_accounts"]))
    return settings


def _normalize_family(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    name = str(entry.get("name", "")).strip()
    if not name:
        return None
    place_id = str(entry.get("place_id", "0")).strip() or "0"
    accounts_raw = entry.get("accounts", [])
    if not isinstance(accounts_raw, list):
        accounts_raw = []
    accounts = [str(a).strip() for a in accounts_raw if str(a).strip()]
    return {"name": name, "place_id": place_id, "accounts": accounts}


def read_raw_app_data() -> object | None:
    path = _accounts_file()
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_to_v3(raw: object) -> dict:
    data = default_app_data()

    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("accounts"), list):
            entries = raw["accounts"]
        else:
            entries = []
        data["settings"] = _normalize_settings(raw.get("settings"))
        if isinstance(raw.get("place_history"), list):
            data["place_history"] = [
                str(p).strip() for p in raw["place_history"] if str(p).strip()
            ][:MAX_PLACE_HISTORY]
        if isinstance(raw.get("families"), list):
            for fam in raw["families"]:
                norm = _normalize_family(fam)
                if norm:
                    data["families"].append(norm)
        if raw.get("version", 1) >= ACCOUNTS_FORMAT_VERSION:
            data["version"] = ACCOUNTS_FORMAT_VERSION
    else:
        entries = []

    stored_accounts: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        group = str(entry.get("group", "")).strip()
        item: dict = {"name": name, "group": group}
        if "secret" in entry:
            item["secret"] = entry["secret"]
        elif "roblosecurity" in entry:
            item["roblosecurity"] = entry["roblosecurity"]
        else:
            continue
        stored_accounts.append(item)

    data["accounts"] = stored_accounts
    return data


def load_app_data(*, migrate: bool = True) -> dict:
    raw = read_raw_app_data()
    if raw is None:
        return default_app_data()

    data = migrate_to_v3(raw)
    needs_save = False

    if isinstance(raw, list):
        needs_save = True
    elif isinstance(raw, dict):
        if raw.get("version", 1) < ACCOUNTS_FORMAT_VERSION:
            needs_save = True
        for entry in data["accounts"]:
            if "roblosecurity" in entry:
                needs_save = True
                break

    if migrate and needs_save:
        save_app_data(data)

    return data


def account_from_storage(entry: dict) -> dict:
    name = entry.get("name", "").strip()
    if not name:
        raise SecurityError("Cuenta sin nombre en accounts.json")

    if "secret" in entry:
        cookie = decrypt_secret(entry["secret"])
    elif "roblosecurity" in entry:
        cookie = entry["roblosecurity"]
    else:
        raise SecurityError(f"Cuenta '{name}' sin datos de sesion")

    return {
        "name": name,
        "roblosecurity": cookie,
        "group": str(entry.get("group", "")).strip(),
    }


def load_accounts(*, migrate_plaintext: bool = True) -> list[dict]:
    data = load_app_data(migrate=migrate_plaintext)
    return [account_from_storage(e) for e in data.get("accounts", [])]


def accounts_to_storage(accounts: list[dict]) -> list[dict]:
    stored = []
    for acc in accounts:
        name = acc.get("name", "").strip()
        cookie = acc.get("roblosecurity", "")
        if not name or not cookie:
            continue
        stored.append(
            {
                "name": name,
                "group": str(acc.get("group", "")).strip(),
                "secret": encrypt_secret(cookie),
            }
        )
    return stored


def save_app_data(data: dict) -> None:
    if not is_encryption_available():
        raise SecurityError(
            "No se puede guardar de forma segura sin pywin32 (pip install pywin32)"
        )

    payload = default_app_data()
    payload["settings"] = _normalize_settings(data.get("settings"))
    payload["place_history"] = [
        str(p).strip() for p in data.get("place_history", []) if str(p).strip()
    ][:MAX_PLACE_HISTORY]

    families: list[dict] = []
    for fam in data.get("families", []):
        norm = _normalize_family(fam)
        if norm:
            families.append(norm)
    payload["families"] = families

    accounts_raw = data.get("accounts", [])
    if accounts_raw and isinstance(accounts_raw[0], dict) and "roblosecurity" in accounts_raw[0]:
        payload["accounts"] = accounts_to_storage(accounts_raw)
    else:
        stored = []
        for entry in accounts_raw:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            group = str(entry.get("group", "")).strip()
            if "secret" in entry:
                stored.append({"name": name, "group": group, "secret": entry["secret"]})
            elif "roblosecurity" in entry:
                stored.append(
                    {
                        "name": name,
                        "group": group,
                        "secret": encrypt_secret(entry["roblosecurity"]),
                    }
                )
        payload["accounts"] = stored

    path = _accounts_file()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(path, 0o600)
    except (AttributeError, OSError):
        pass


def save_accounts(accounts: list[dict]) -> None:
    data = load_app_data(migrate=False)
    data["accounts"] = accounts_to_storage(accounts)
    save_app_data(data)


def get_settings() -> dict:
    return _normalize_settings(load_app_data(migrate=False).get("settings"))


def save_settings(settings: dict) -> None:
    data = load_app_data(migrate=False)
    data["settings"] = _normalize_settings(settings)
    save_app_data(data)


def get_place_history() -> list[str]:
    return list(load_app_data(migrate=False).get("place_history", []))


def add_place_to_history(place_id: str) -> list[str]:
    place_id = str(place_id).strip()
    if not place_id or place_id == "0":
        return get_place_history()
    data = load_app_data(migrate=False)
    history = [p for p in data.get("place_history", []) if p != place_id]
    history.insert(0, place_id)
    data["place_history"] = history[:MAX_PLACE_HISTORY]
    save_app_data(data)
    return data["place_history"]


def get_families() -> list[dict]:
    data = load_app_data(migrate=False)
    families: list[dict] = []
    for fam in data.get("families", []):
        norm = _normalize_family(fam)
        if norm:
            families.append(norm)
    return families


def save_families(families: list[dict]) -> None:
    data = load_app_data(migrate=False)
    data["families"] = [f for f in (_normalize_family(x) for x in families) if f]
    save_app_data(data)


def get_family_by_name(name: str) -> dict | None:
    name = name.strip()
    for fam in get_families():
        if fam["name"] == name:
            return fam
    return None


def resolve_family_accounts(family: dict, all_accounts: list[dict]) -> list[dict]:
    by_name = {a["name"]: a for a in all_accounts}
    resolved: list[dict] = []
    for name in family.get("accounts", []):
        if name in by_name:
            resolved.append(by_name[name])
    return resolved


def update_account_cookie(name: str, cookie: str) -> bool:
    data = load_app_data(migrate=False)
    updated = False
    for entry in data.get("accounts", []):
        if entry.get("name") == name:
            entry["secret"] = encrypt_secret(cookie)
            if "roblosecurity" in entry:
                del entry["roblosecurity"]
            updated = True
            break
    if updated:
        save_app_data(data)
    return updated
