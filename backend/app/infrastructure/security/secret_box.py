"""Symmetric encryption for credentials stored at rest.

Model registry entries carry provider API keys. Those must never sit in
Mongo in plaintext: anyone with a database dump (backup, replica, screen
share) would otherwise walk away with every provider credential.

Uses Fernet (AES-128-CBC + HMAC-SHA256, from ``cryptography``, already a
project dependency) keyed by ``MODEL_ENCRYPTION_KEY``. The key is
**required** — there is deliberately no derive-from-JWT fallback, so that
rotating session secrets can never silently make stored credentials
unreadable, and so an operator can never accidentally run production with
credentials protected by a default value.
"""
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GENERATE_HINT = (
    "Set MODEL_ENCRYPTION_KEY in your .env. Generate one with:\n"
    "  python -c \"from cryptography.fernet import Fernet; "
    "print(Fernet.generate_key().decode())\"\n"
    "Keep it stable — rotating it makes already-stored credentials unreadable."
)


class EncryptionKeyMissingError(RuntimeError):
    """MODEL_ENCRYPTION_KEY is unset, so credentials cannot be handled."""


class EncryptionKeyInvalidError(RuntimeError):
    """MODEL_ENCRYPTION_KEY is set but is not a valid Fernet key."""


class SecretDecryptionError(RuntimeError):
    """Ciphertext could not be decrypted with the configured key.

    Usually means the key changed since the value was written, or the stored
    bytes were corrupted/tampered with.
    """


_cipher: Optional[Fernet] = None
_cipher_key: Optional[str] = None


def invalidate_cipher_cache() -> None:
    """Drop the memoized cipher. Used by tests and after config changes."""
    global _cipher, _cipher_key
    _cipher = None
    _cipher_key = None


def _configured_key() -> Optional[str]:
    raw = get_settings().model_encryption_key
    if not raw or not raw.strip():
        return None
    return raw.strip()


def is_configured() -> bool:
    """Whether a usable encryption key is present.

    Lets callers (e.g. the admin API) fail with a clear message *before*
    accepting a credential, rather than after.
    """
    return _configured_key() is not None


def _get_cipher() -> Fernet:
    global _cipher, _cipher_key

    key = _configured_key()
    if key is None:
        raise EncryptionKeyMissingError(
            "MODEL_ENCRYPTION_KEY is not configured, so provider credentials "
            f"cannot be stored or read.\n{_GENERATE_HINT}"
        )

    if _cipher is not None and _cipher_key == key:
        return _cipher

    try:
        cipher = Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as e:
        raise EncryptionKeyInvalidError(
            f"MODEL_ENCRYPTION_KEY is not a valid Fernet key ({e}).\n{_GENERATE_HINT}"
        ) from e

    _cipher = cipher
    _cipher_key = key
    return cipher


def encrypt(plaintext: str) -> bytes:
    """Encrypt a credential for storage.

    Raises:
        EncryptionKeyMissingError: when MODEL_ENCRYPTION_KEY is unset.
        EncryptionKeyInvalidError: when the configured key is malformed.
    """
    return _get_cipher().encrypt(plaintext.encode("utf-8"))


def decrypt(token: bytes) -> str:
    """Decrypt a stored credential.

    Raises:
        EncryptionKeyMissingError: when MODEL_ENCRYPTION_KEY is unset.
        EncryptionKeyInvalidError: when the configured key is malformed.
        SecretDecryptionError: when the ciphertext does not match the key.
    """
    cipher = _get_cipher()
    try:
        return cipher.decrypt(token).decode("utf-8")
    except InvalidToken as e:
        raise SecretDecryptionError(
            "Stored credential could not be decrypted with the current "
            "MODEL_ENCRYPTION_KEY. If the key was rotated, re-enter the "
            "credential for the affected model."
        ) from e


def build_hint(plaintext: Optional[str]) -> str:
    """A display-safe fragment of a credential, e.g. ``…wxyz``.

    Shown in the admin UI so an operator can tell *which* key is stored
    without the API ever returning the key itself. Secrets too short to
    partially mask are reduced to the ellipsis alone rather than leaked.
    """
    if not plaintext:
        return ""
    suffix_len = 4
    # Requiring more than 2x the suffix means a short key can never be
    # substantially reconstructed from its own hint.
    if len(plaintext) <= suffix_len * 2:
        return "…"
    return f"…{plaintext[-suffix_len:]}"
