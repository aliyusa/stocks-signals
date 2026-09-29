import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def register(client, email="aliyu@example.com", password="StrongPass123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": "Aliyu"})
    assert r.status_code == 201, r.text
    return r


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("hss_csrf")}
