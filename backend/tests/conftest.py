"""
공용 pytest fixtures.

- tmp_db: 테스트마다 격리된 SQLite 파일. User._db_path 와
  pipeline_orchestrator._db_path 를 둘 다 monkeypatch.
- app / client: Flask 테스트 클라이언트. 쿠키 세션 유지됨.
- admin_user / builder_user / viewer_user: 해당 롤 사용자 fixture.
"""

import os
import sys
from pathlib import Path

import pytest

# backend/tests/ → backend/ 를 sys.path 에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """테스트용 임시 SQLite 파일. User + pipeline 두 경로 모두 리다이렉트."""
    db_file = tmp_path / "test.sqlite3"

    from app.models import user as user_mod
    from app.services import pipeline_orchestrator as pipeline_mod

    monkeypatch.setattr(user_mod, "_db_path", lambda: db_file)
    monkeypatch.setattr(pipeline_mod, "_db_path", lambda: db_file)
    return db_file


@pytest.fixture
def app(tmp_db, monkeypatch):
    """Flask app instance (격리 DB 위에서). TESTING 모드."""
    # 세션 쿠키 서명을 위해 고정 키 (test client 안에서 persist)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-phase9-auth")
    monkeypatch.setenv("FLASK_DEBUG", "False")
    monkeypatch.setenv("LLM_API_KEY", "test-dummy")  # validate() 경고 억제

    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_user(app):
    from app.models.user import User

    return User.create(
        email="admin@test.local",
        password="testpass123",
        role="admin",
    )


@pytest.fixture
def builder_user(app):
    from app.models.user import User

    return User.create(
        email="builder@test.local",
        password="testpass123",
        role="builder",
    )


@pytest.fixture
def viewer_user(app):
    from app.models.user import User

    return User.create(
        email="viewer@test.local",
        password="testpass123",
        role="viewer",
    )


@pytest.fixture
def login_as(client):
    """client.post /api/auth/login 헬퍼. 세션 쿠키는 client 에 자동 저장."""

    def _login(email: str, password: str = "testpass123"):
        resp = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        return resp

    return _login
