from tests.conftest import register


def test_dashboard_requires_auth(client):
    assert client.get("/api/dashboard").status_code == 401


def test_dashboard_reports_unavailable_not_fabricated(client):
    register(client)
    d = client.get("/api/dashboard").json()
    assert len(d["index_cards"]) == 3
    for card in d["index_cards"]:
        dp = card["change_pct"]
        assert dp["status"] == "UNAVAILABLE"
        assert dp["value"] is None
        assert dp["note"]  # explains why
    assert d["counts"]["potential_setups"] == 0
    assert d["top_setups"] == []
    assert all(s["status"] == "UNAVAILABLE" for s in d["data_sources"])


def test_reference_data_seeded_without_prices(client):
    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models.entities import PriceHistory

    register(client)
    markets = client.get("/api/markets").json()
    codes = {m["code"] for m in markets}
    assert {"NG", "US", "UK", "GCC", "MY"} <= codes
    ng = next(m for m in markets if m["code"] == "NG")
    assert ng["exchanges"][0]["code"] == "XNSA"
    meths = client.get("/api/shariah/methodologies").json()
    assert {m["code"] for m in meths} == {"aaoifi_based", "total_assets_33"}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PriceHistory)) == 0


def test_disclaimer(client):
    assert "not guarantees" in client.get("/api/disclaimer").json()["text"]
