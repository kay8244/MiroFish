"""
인증 API + 전역 게이트 integration tests (Phase 9).

Flask test client 로 로그인 세션 쿠키를 유지한 상태의 요청을 시뮬레이트.
Tier A — offline 전용.
"""


class TestLoginEndpoint:
    def test_login_success(self, client, admin_user):
        resp = client.post(
            "/api/auth/login",
            json={"email": "admin@test.local", "password": "testpass123"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["user"] == {"id": admin_user.id, "email": "admin@test.local", "role": "admin"}

    def test_login_email_case_insensitive(self, client, admin_user):
        resp = client.post(
            "/api/auth/login",
            json={"email": "ADMIN@test.local", "password": "testpass123"},
        )
        assert resp.status_code == 200

    def test_login_wrong_password(self, client, admin_user):
        resp = client.post(
            "/api/auth/login",
            json={"email": "admin@test.local", "password": "WRONG"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid credentials"

    def test_login_unknown_email_returns_same_error(self, client, admin_user):
        """미존재 이메일은 오타비번과 동일한 401 — 이메일 존재 여부 누설 방지."""
        resp = client.post(
            "/api/auth/login",
            json={"email": "nobody@test.local", "password": "testpass123"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid credentials"

    def test_login_missing_fields(self, client):
        for payload in [{}, {"email": "a@x.com"}, {"password": "x"}]:
            resp = client.post("/api/auth/login", json=payload)
            assert resp.status_code == 400

    def test_login_sets_session_cookie(self, client, admin_user):
        resp = client.post(
            "/api/auth/login",
            json={"email": "admin@test.local", "password": "testpass123"},
        )
        # Flask-Login 은 login_user(remember=True) 시 session + remember_token 둘 다 셋
        cookies = resp.headers.getlist("Set-Cookie")
        joined = " | ".join(cookies)
        assert "session=" in joined or "remember_token=" in joined
        # HttpOnly 는 모든 auth 쿠키에 붙어있어야 함
        auth_cookies = [c for c in cookies if "session=" in c or "remember_token=" in c]
        assert auth_cookies, f"no auth cookie found: {cookies}"
        for c in auth_cookies:
            assert "HttpOnly" in c, f"HttpOnly missing on: {c}"


class TestMeEndpoint:
    def test_me_unauth(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "unauthorized"

    def test_me_after_login(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.get_json()["user"]["email"] == "admin@test.local"


class TestLogoutEndpoint:
    def test_logout_ends_session(self, client, admin_user, login_as):
        login_as("admin@test.local")
        assert client.get("/api/auth/me").status_code == 200
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        # 재조회 시 미인증
        assert client.get("/api/auth/me").status_code == 401

    def test_logout_requires_auth(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401


class TestGate:
    """app.before_request(enforce_auth) 동작 검증."""

    def test_health_is_public(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_api_requires_auth(self, client):
        resp = client.get("/api/graph/project/list")
        assert resp.status_code == 401

    def test_api_allows_authenticated(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.get("/api/graph/project/list")
        # 인증 통과 시 API 레벨 응답. 빈 프로젝트여도 200 OK.
        assert resp.status_code == 200

    def test_options_preflight_bypasses_gate(self, client):
        resp = client.options("/api/graph/project/list")
        # CORS preflight 는 401 이면 안 됨
        assert resp.status_code != 401


class TestRoleGate:
    """쓰기 메서드(POST/PUT/DELETE/PATCH)는 admin/builder 만."""

    def test_viewer_get_allowed(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/graph/project/list")
        assert resp.status_code == 200

    def test_viewer_post_forbidden(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.post("/api/graph/build", json={})
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "forbidden"
        assert body["required_roles"] == ["admin", "builder"]

    def test_viewer_delete_forbidden(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.delete("/api/graph/project/nonexistent")
        assert resp.status_code == 403

    def test_builder_post_passes_auth(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/graph/build", json={})
        # auth 통과 이후 body 검증 단계에서 400 (project_id 누락) — 403/401 은 아니어야 함
        assert resp.status_code != 403
        assert resp.status_code != 401

    def test_admin_post_passes_auth(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.post("/api/graph/build", json={})
        assert resp.status_code != 403
        assert resp.status_code != 401


# ============================================================================
# 비밀번호 변경 (본인)
# ============================================================================

class TestChangeOwnPassword:
    def test_requires_auth(self, client):
        resp = client.post("/api/auth/password", json={
            "old_password": "x", "new_password": "y"
        })
        assert resp.status_code == 401

    def test_missing_fields(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/auth/password", json={})
        assert resp.status_code == 400

    def test_wrong_old_password(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/auth/password", json={
            "old_password": "wrong",
            "new_password": "newpass123",
        })
        assert resp.status_code == 401

    def test_short_new_password_rejected(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/auth/password", json={
            "old_password": "testpass123",
            "new_password": "short",
        })
        assert resp.status_code == 400

    def test_happy_path_then_login_with_new_password(
        self, client, builder_user, login_as
    ):
        login_as("builder@test.local")
        # 변경
        resp = client.post("/api/auth/password", json={
            "old_password": "testpass123",
            "new_password": "newpass1234",
        })
        assert resp.status_code == 200
        # logout 후 새 비밀번호로 로그인 검증
        client.post("/api/auth/logout")
        ok = client.post("/api/auth/login", json={
            "email": "builder@test.local",
            "password": "newpass1234",
        })
        assert ok.status_code == 200
        # 옛 비밀번호는 거부
        client.post("/api/auth/logout")
        bad = client.post("/api/auth/login", json={
            "email": "builder@test.local",
            "password": "testpass123",
        })
        assert bad.status_code == 401


# ============================================================================
# 사용자 관리 (admin only)
# ============================================================================

class TestListUsers:
    def test_requires_admin(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.get("/api/auth/users")
        assert resp.status_code == 403

    def test_admin_lists_users(self, client, admin_user, builder_user, login_as):
        login_as("admin@test.local")
        resp = client.get("/api/auth/users")
        assert resp.status_code == 200
        body = resp.get_json()
        emails = {u["email"] for u in body["users"]}
        assert "admin@test.local" in emails
        assert "builder@test.local" in emails
        # password_hash 누설 안 됨
        for u in body["users"]:
            assert "password_hash" not in u


class TestCreateUser:
    def test_requires_admin(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/auth/users", json={
            "email": "x@y.z", "password": "abcd1234", "role": "viewer"
        })
        assert resp.status_code == 403

    def test_missing_fields(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.post("/api/auth/users", json={"email": "x@y.z"})
        assert resp.status_code == 400

    def test_invalid_role(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.post("/api/auth/users", json={
            "email": "x@y.z", "password": "abcd1234", "role": "superuser"
        })
        assert resp.status_code == 400
        assert "role" in resp.get_json()["error"]

    def test_duplicate_email_409(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.post("/api/auth/users", json={
            "email": "admin@test.local",
            "password": "newpass1234",
            "role": "viewer",
        })
        assert resp.status_code == 409

    def test_happy_path(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.post("/api/auth/users", json={
            "email": "newbie@test.local",
            "password": "abcd1234",
            "role": "viewer",
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["user"]["email"] == "newbie@test.local"
        assert body["user"]["role"] == "viewer"

    def test_short_password_rejected(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.post("/api/auth/users", json={
            "email": "x@y.z", "password": "short", "role": "viewer"
        })
        assert resp.status_code == 400


class TestDeleteUser:
    def test_requires_admin(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.delete("/api/auth/users/999")
        assert resp.status_code == 403

    def test_cannot_delete_self(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.delete(f"/api/auth/users/{admin_user.id}")
        assert resp.status_code == 400
        assert "yourself" in resp.get_json()["error"]

    def test_unknown_user_404(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.delete("/api/auth/users/9999")
        assert resp.status_code == 404

    def test_happy_path(self, client, admin_user, builder_user, login_as):
        login_as("admin@test.local")
        resp = client.delete(f"/api/auth/users/{builder_user.id}")
        assert resp.status_code == 200
        # 다시 삭제하면 404
        resp2 = client.delete(f"/api/auth/users/{builder_user.id}")
        assert resp2.status_code == 404


class TestUpdateRole:
    def test_requires_admin(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.patch("/api/auth/users/1/role", json={"role": "admin"})
        assert resp.status_code == 403

    def test_invalid_role(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.patch(f"/api/auth/users/{admin_user.id}/role", json={"role": "ghost"})
        assert resp.status_code == 400

    def test_unknown_user_404(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.patch("/api/auth/users/9999/role", json={"role": "viewer"})
        assert resp.status_code == 404

    def test_promote_viewer_to_builder(
        self, client, admin_user, viewer_user, login_as
    ):
        login_as("admin@test.local")
        resp = client.patch(
            f"/api/auth/users/{viewer_user.id}/role", json={"role": "builder"}
        )
        assert resp.status_code == 200

    def test_cannot_demote_last_admin(self, client, admin_user, login_as):
        login_as("admin@test.local")
        # 시스템에 admin 이 1명만 있을 때 자기 자신을 강등 시도
        resp = client.patch(
            f"/api/auth/users/{admin_user.id}/role", json={"role": "viewer"}
        )
        assert resp.status_code == 400
        assert "last admin" in resp.get_json()["error"]


class TestAdminResetPassword:
    def test_requires_admin(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/auth/users/1/password", json={"password": "abcd1234"})
        assert resp.status_code == 403

    def test_missing_password(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.post(f"/api/auth/users/{admin_user.id}/password", json={})
        assert resp.status_code == 400

    def test_short_password_rejected(self, client, admin_user, builder_user, login_as):
        login_as("admin@test.local")
        resp = client.post(
            f"/api/auth/users/{builder_user.id}/password",
            json={"password": "short"},
        )
        assert resp.status_code == 400

    def test_unknown_user_404(self, client, admin_user, login_as):
        login_as("admin@test.local")
        resp = client.post(
            "/api/auth/users/9999/password", json={"password": "abcd1234"}
        )
        assert resp.status_code == 404

    def test_happy_path_then_user_can_login(
        self, client, admin_user, builder_user, login_as
    ):
        login_as("admin@test.local")
        resp = client.post(
            f"/api/auth/users/{builder_user.id}/password",
            json={"password": "resetpass1"},
        )
        assert resp.status_code == 200
        # 새 비밀번호로 로그인 가능
        client.post("/api/auth/logout")
        ok = client.post("/api/auth/login", json={
            "email": "builder@test.local",
            "password": "resetpass1",
        })
        assert ok.status_code == 200
