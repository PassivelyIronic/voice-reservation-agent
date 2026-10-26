import pytest
from pydantic import ValidationError

from voice_agent.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("VOICE_PROFILE", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def _settings() -> Settings:
    # Ignore a developer's local .env so tests are deterministic.
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_default_profile_is_cloud() -> None:
    assert _settings().voice_profile == "cloud"


def test_profile_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_PROFILE", "cpu")
    assert _settings().voice_profile == "cpu"


def test_invalid_profile_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_PROFILE", "gpu-cluster")
    with pytest.raises(ValidationError):
        _settings()


def test_api_key_not_leaked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake_secret")
    settings = _settings()
    assert "gsk_fake_secret" not in repr(settings)
    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "gsk_fake_secret"
