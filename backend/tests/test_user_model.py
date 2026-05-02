"""
User 모델 unit tests (Phase 9).

Tier A — offline 전용. bcrypt 해싱과 sqlite 쓰기는 실제 수행하지만
외부 서비스(Neo4j/LLM) 의존성 0.
"""

import sqlite3

import pytest

# conftest.py 의 tmp_db / app fixture 는 자동 전파됨


class TestUserCreate:
    def test_valid_user_is_persisted(self, app):
        from app.models.user import User

        u = User.create(email="a@x.com", password="password123", role="admin")
        assert u.id > 0
        assert u.email == "a@x.com"
        assert u.role == "admin"
        # round-trip
        fetched = User.get_by_id(u.id)
        assert fetched is not None
        assert fetched.email == "a@x.com"

    def test_email_is_normalized(self, app):
        from app.models.user import User

        u = User.create(email="  Alice@X.COM ", password="password123", role="viewer")
        assert u.email == "alice@x.com"
        assert User.get_by_email("ALICE@X.COM") is not None

    def test_rejects_short_password(self, app):
        from app.models.user import User

        with pytest.raises(ValueError, match="password"):
            User.create(email="b@x.com", password="short", role="viewer")

    def test_rejects_invalid_email(self, app):
        from app.models.user import User

        with pytest.raises(ValueError, match="email"):
            User.create(email="no-at-sign", password="password123", role="viewer")
        with pytest.raises(ValueError, match="email"):
            User.create(email="", password="password123", role="viewer")

    def test_rejects_invalid_role(self, app):
        from app.models.user import User

        with pytest.raises(ValueError, match="role"):
            User.create(email="c@x.com", password="password123", role="superuser")

    def test_duplicate_email_raises(self, app):
        from app.models.user import User

        User.create(email="dup@x.com", password="password123", role="viewer")
        with pytest.raises(sqlite3.IntegrityError):
            User.create(email="dup@x.com", password="password123", role="viewer")

    def test_password_stored_as_bcrypt_hash(self, app):
        from app.models.user import User

        u = User.create(email="hash@x.com", password="password123", role="viewer")
        # 평문은 DB 에 없어야 한다
        assert u.password_hash != "password123"
        # bcrypt 해시 접두사
        assert u.password_hash.startswith("$2")


class TestCheckPassword:
    def test_correct_password(self, app):
        from app.models.user import User

        u = User.create(email="ok@x.com", password="correctpw123", role="admin")
        assert u.check_password("correctpw123") is True

    def test_wrong_password(self, app):
        from app.models.user import User

        u = User.create(email="ok@x.com", password="correctpw123", role="admin")
        assert u.check_password("wrongpw123") is False

    def test_empty_password(self, app):
        from app.models.user import User

        u = User.create(email="ok@x.com", password="correctpw123", role="admin")
        assert u.check_password("") is False

    def test_no_hash_returns_false(self, app):
        from app.models.user import User

        u = User(id=99, email="nohash@x.com", role="viewer", password_hash=None)
        assert u.check_password("anything") is False


class TestGetters:
    def test_get_by_id_miss(self, app):
        from app.models.user import User

        assert User.get_by_id(99999) is None

    def test_get_by_email_miss(self, app):
        from app.models.user import User

        assert User.get_by_email("missing@x.com") is None

    def test_count_reflects_inserts(self, app):
        from app.models.user import User

        assert User.count() == 0
        User.create(email="u1@x.com", password="password123", role="admin")
        User.create(email="u2@x.com", password="password123", role="viewer")
        assert User.count() == 2


class TestToDict:
    def test_to_dict_excludes_password_hash(self, app):
        from app.models.user import User

        u = User.create(email="d@x.com", password="password123", role="builder")
        d = u.to_dict()
        assert d == {"id": u.id, "email": "d@x.com", "role": "builder"}
        assert "password_hash" not in d
        assert "password" not in d
