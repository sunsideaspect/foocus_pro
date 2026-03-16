import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:////tmp/identity_studio_test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
import app.main as app_main  # noqa: E402


class DummyRedis:
    def ping(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_main, "enqueue_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "get_redis", lambda: DummyRedis())
    with TestClient(app) as c:
        yield c
