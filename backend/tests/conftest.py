import os

from cryptography.fernet import Fernet

os.environ.update(
    {
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET": "test-secret-test-secret-test-secret",
        "CREDENTIALS_KEY": Fernet.generate_key().decode(),
        "SCHEDULER_ENABLED": "false",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import seed  # noqa: E402

ADMIN = {"email": "me@example.com", "password": "pw-for-tests"}


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed(db, ADMIN["email"], ADMIN["password"])
    yield factory
    engine.dispose()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    res = client.post("/api/auth/login", json=ADMIN)
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
