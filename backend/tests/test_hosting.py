"""Hosted mode: URL normalisation for Supabase/Render and serving the built frontend from FastAPI."""

import importlib

from fastapi.testclient import TestClient

from app.core.db import normalise_url


def test_normalise_url_accepts_supabase_formats():
    raw = "postgres.abcd:p%40ss@aws-0-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require"
    assert normalise_url("postgresql://" + raw) == "postgresql+psycopg://" + raw
    assert normalise_url("postgres://" + raw) == "postgresql+psycopg://" + raw
    assert normalise_url("postgresql+psycopg://x@y/z") == "postgresql+psycopg://x@y/z"
    assert normalise_url("sqlite:///./dev.db") == "sqlite:///./dev.db"


def test_spa_served_with_security_headers(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>HSS</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    from app.core import config

    config.get_settings.cache_clear()
    import app.main as main

    try:
        main = importlib.reload(main)
        c = TestClient(main.app)
        r = c.get("/stocks/XNSA/DANGCEM")  # client-side route falls back to index.html
        assert r.status_code == 200 and "<title>HSS</title>" in r.text
        assert "default-src 'self'" in r.headers["content-security-policy"]
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").status_code == 200
        assert c.get("/api/nope").status_code == 404  # unknown API paths are not swallowed by the SPA
        assert c.get("/api/health").json()["status"] in ("ok", "degraded")
        assert "strict-transport-security" in c.get("/", headers={"x-forwarded-proto": "https"}).headers
    finally:
        monkeypatch.delenv("STATIC_DIR")
        config.get_settings.cache_clear()
        importlib.reload(main)
