"""Unit tests for credential encryption at rest (model registry API keys).

Pure unit tests — no running server, no DB. Exercises secret_box.py directly,
the same style as test_model_registry.py / test_llm_gateway.py.
"""
import pytest
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.infrastructure.security import secret_box


@pytest.fixture(autouse=True)
def _reset_secret_box(monkeypatch):
    """Each test starts with a fresh cipher and a known key setting."""
    secret_box.invalidate_cipher_cache()
    yield
    secret_box.invalidate_cipher_cache()


@pytest.fixture
def valid_key(monkeypatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), "model_encryption_key", key)
    secret_box.invalidate_cipher_cache()
    return key


class TestRoundTrip:
    def test_encrypt_then_decrypt_returns_original(self, valid_key):
        secret = "sk-proj-abc123def456"
        token = secret_box.encrypt(secret)
        assert secret_box.decrypt(token) == secret

    def test_ciphertext_does_not_contain_plaintext(self, valid_key):
        """The stored bytes must not leak the credential to anyone reading Mongo."""
        secret = "sk-proj-abc123def456"
        token = secret_box.encrypt(secret)
        assert b"sk-proj" not in token
        assert secret.encode() not in token

    def test_same_plaintext_encrypts_differently_each_time(self, valid_key):
        """Fernet embeds a random IV — identical keys must not look identical."""
        a = secret_box.encrypt("same-value")
        b = secret_box.encrypt("same-value")
        assert a != b
        assert secret_box.decrypt(a) == secret_box.decrypt(b) == "same-value"

    def test_unicode_secret_survives_round_trip(self, valid_key):
        secret = "chave-com-acentuação-e-emoji-🔑"
        assert secret_box.decrypt(secret_box.encrypt(secret)) == secret


class TestMissingKey:
    def test_encrypt_without_key_raises_with_actionable_message(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "model_encryption_key", None)
        secret_box.invalidate_cipher_cache()
        with pytest.raises(secret_box.EncryptionKeyMissingError) as exc:
            secret_box.encrypt("sk-whatever")
        # The message must tell an operator how to fix it, not just fail.
        assert "MODEL_ENCRYPTION_KEY" in str(exc.value)
        assert "Fernet.generate_key()" in str(exc.value)

    def test_decrypt_without_key_raises(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "model_encryption_key", None)
        secret_box.invalidate_cipher_cache()
        with pytest.raises(secret_box.EncryptionKeyMissingError):
            secret_box.decrypt(b"gAAAAA-anything")

    def test_blank_key_is_treated_as_missing(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "model_encryption_key", "   ")
        secret_box.invalidate_cipher_cache()
        with pytest.raises(secret_box.EncryptionKeyMissingError):
            secret_box.encrypt("sk-whatever")

    def test_is_configured_reflects_key_presence(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "model_encryption_key", None)
        secret_box.invalidate_cipher_cache()
        assert secret_box.is_configured() is False

        monkeypatch.setattr(get_settings(), "model_encryption_key", Fernet.generate_key().decode())
        secret_box.invalidate_cipher_cache()
        assert secret_box.is_configured() is True


class TestInvalidKeyOrToken:
    def test_malformed_key_raises_actionable_error(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "model_encryption_key", "not-a-valid-fernet-key")
        secret_box.invalidate_cipher_cache()
        with pytest.raises(secret_box.EncryptionKeyInvalidError):
            secret_box.encrypt("sk-whatever")

    def test_decrypt_with_a_different_key_fails(self, valid_key, monkeypatch):
        token = secret_box.encrypt("sk-original")
        monkeypatch.setattr(get_settings(), "model_encryption_key", Fernet.generate_key().decode())
        secret_box.invalidate_cipher_cache()
        with pytest.raises(secret_box.SecretDecryptionError):
            secret_box.decrypt(token)

    def test_decrypt_tampered_ciphertext_fails(self, valid_key):
        token = bytearray(secret_box.encrypt("sk-original"))
        token[-1] = token[-1] ^ 0xFF  # flip the last byte
        with pytest.raises(secret_box.SecretDecryptionError):
            secret_box.decrypt(bytes(token))


class TestHint:
    def test_hint_shows_only_a_short_suffix(self):
        assert secret_box.build_hint("sk-proj-abcdefgh1234wxyz") == "…wxyz"

    def test_hint_of_short_secret_does_not_leak_it_whole(self):
        """A 4-char key must not round-trip through the hint verbatim."""
        assert secret_box.build_hint("abcd") == "…"

    def test_hint_of_empty_or_none_is_empty(self):
        assert secret_box.build_hint("") == ""
        assert secret_box.build_hint(None) == ""
