import pytest
from pydantic import ValidationError

from netsentinel.config import Settings


def test_defaults_and_derived_paths(tmp_path):
    s = Settings(data_dir=tmp_path)
    assert s.role == "hub"
    assert s.db_path == tmp_path / "netsentinel.db"
    assert s.database_url.startswith("sqlite:///")


def test_role_validation():
    with pytest.raises(ValidationError):
        Settings(role="controller")
    assert Settings(role="SENSOR").role == "sensor"


def test_notify_backend_validation():
    with pytest.raises(ValidationError):
        Settings(notify_backend="carrier-pigeon")


def test_short_token_rejected():
    with pytest.raises(ValidationError):
        Settings(api_token="short")
