from tests.conftest import csrf, register


def test_register_login_me(client):
    register(client)
    assert client.get("/api/auth/me").json()["email"] == "aliyu@example.com"
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "ALIYU@example.com", "password": "StrongPass123"})
    assert r.status_code == 200
    assert "hss_access" in client.cookies


def test_password_is_hashed_with_argon2(client):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.entities import User

    register(client)
    with SessionLocal() as db:
        u = db.scalar(select(User))
        assert u.password_hash.startswith("$argon2")
        assert "StrongPass123" not in u.password_hash


def test_weak_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_duplicate_email(client):
    register(client)
    client.cookies.clear()
    r = client.post("/api/auth/register", json={"email": "aliyu@example.com", "password": "StrongPass123"})
    assert r.status_code == 409


def test_wrong_password_and_lockout(client):
    register(client)
    client.cookies.clear()
    for _ in range(5):
        r = client.post("/api/auth/login", json={"email": "aliyu@example.com", "password": "WrongPass999"})
        assert r.status_code == 401
    r = client.post("/api/auth/login", json={"email": "aliyu@example.com", "password": "StrongPass123"})
    assert r.status_code == 423


def test_csrf_required_for_cookie_authenticated_writes(client):
    register(client)
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.post("/api/auth/logout", headers=csrf(client)).status_code == 200


def test_logout_all_revokes_tokens(client):
    register(client)
    old_access = client.cookies.get("hss_access")
    assert client.post("/api/auth/logout-all", headers=csrf(client)).status_code == 200
    client.cookies.set("hss_access", old_access)
    assert client.get("/api/auth/me").status_code == 401


def test_refresh(client):
    register(client)
    r = client.post("/api/auth/refresh", headers=csrf(client))
    assert r.status_code == 200


def test_audit_log_written(client):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.entities import AuditLog

    register(client)
    with SessionLocal() as db:
        actions = [a.action for a in db.scalars(select(AuditLog)).all()]
    assert "auth.register" in actions


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_registration_limited_to_allowed_emails(client, monkeypatch):
    from app.api import auth as auth_api

    monkeypatch.setattr(auth_api.settings, "allowed_emails", ["Owner@Example.com"])
    r = client.post("/api/auth/register", json={"email": "stranger@example.com", "password": "Str0ng-Passphrase-2026"})
    assert r.status_code == 403
    r = client.post("/api/auth/register", json={"email": "owner@example.com", "password": "Str0ng-Passphrase-2026"})
    assert r.status_code == 201
