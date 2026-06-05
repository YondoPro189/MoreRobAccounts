"""
Cifrado local de secretos con Windows DPAPI (por usuario de Windows).
Las cookies solo existen en texto plano en memoria mientras la app corre.
"""

from __future__ import annotations

import base64

try:
    import win32crypt

    _DPAPI_AVAILABLE = True
except ImportError:
    win32crypt = None  # type: ignore[assignment]
    _DPAPI_AVAILABLE = False


class SecurityError(RuntimeError):
    pass


def is_encryption_available() -> bool:
    return _DPAPI_AVAILABLE


def encrypt_secret(plain_text: str) -> str:
    if not _DPAPI_AVAILABLE:
        raise SecurityError(
            "Cifrado no disponible. Instala pywin32: pip install pywin32"
        )
    data = plain_text.encode("utf-8")
    blob = win32crypt.CryptProtectData(data, "MoreRobAccounts", None, None, None, 0)
    return base64.b64encode(blob).decode("ascii")


def decrypt_secret(cipher_b64: str) -> str:
    if not _DPAPI_AVAILABLE:
        raise SecurityError(
            "Cifrado no disponible. Instala pywin32: pip install pywin32"
        )
    blob = base64.b64decode(cipher_b64.encode("ascii"))
    _, decrypted = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return decrypted.decode("utf-8")
