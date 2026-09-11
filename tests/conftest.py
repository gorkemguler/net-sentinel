"""Shared test fixtures.

Environment variables are set *before* any ``netsentinel`` import so the cached
``Settings`` object picks up the throwaway data dir and test token.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="netsentinel-test-"))
os.environ.setdefault("NETSENTINEL_DATA_DIR", str(_TMP))
os.environ.setdefault("NETSENTINEL_API_TOKEN", "test-token-abc123")
os.environ.setdefault("NETSENTINEL_NOTIFY_BACKEND", "none")
os.environ.setdefault("NETSENTINEL_TI_ENABLED", "true")
os.environ.setdefault("NETSENTINEL_BLOCKLIST_PATH", str(_TMP / "blocklist.txt"))
(_TMP / "blocklist.txt").write_text("c2.evil.example\n198.51.100.7\n", encoding="utf-8")

import pytest  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from netsentinel import threatintel  # noqa: E402
from netsentinel.db import get_engine, init_db  # noqa: E402

TEST_TOKEN = "test-token-abc123"


@pytest.fixture(autouse=True)
def _fresh_db():
    """Give every test an empty schema."""
    threatintel._blocklist.cache_clear()
    engine = get_engine()
    SQLModel.metadata.drop_all(engine)
    init_db()
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from netsentinel.hub.app import app

    # No ``with`` block: we skip the lifespan (and its background scheduler) so
    # tests stay deterministic. The DB is already prepared by ``_fresh_db``.
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {TEST_TOKEN}"})
    return c


@pytest.fixture
def session():
    from netsentinel.db import session_scope

    with session_scope() as s:
        yield s
