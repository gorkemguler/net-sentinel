def test_healthz_is_public(client):
    client.headers.pop("Authorization", None)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["role"] == "hub"


def test_ingest_requires_token(client):
    client.headers.pop("Authorization", None)
    r = client.post("/api/ingest", json={"sensor_id": "s1"})
    assert r.status_code == 401


def test_ingest_and_query_roundtrip(client):
    payload = {
        "sensor_id": "s1",
        "devices": [{"mac": "B8:27:EB:DE:AD:01", "ip": "192.168.1.77", "hostname": "nas"}],
        "dns": [{"client_ip": "192.168.1.10", "qname": "example.com", "answer": "93.184.216.34"}],
    }
    r = client.post("/api/ingest", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["devices_upserted"] == 1

    devices = client.get("/api/devices").json()
    assert any(d["hostname"] == "nas" for d in devices)

    top = client.get("/api/dns/top").json()
    assert any(row["qname"] == "example.com" for row in top)

    stats = client.get("/api/stats").json()
    assert stats["devices_total"] == 1


def test_alert_ack_flow(client):
    client.post(
        "/api/ingest",
        json={"sensor_id": "s1", "devices": [{"mac": "B8:27:EB:DE:AD:02", "ip": "192.168.1.78"}]},
    )
    alerts = client.get("/api/alerts").json()
    assert alerts and alerts[0]["acknowledged"] is False
    aid = alerts[0]["id"]

    r = client.post(f"/api/alerts/{aid}/ack")
    assert r.status_code == 200 and r.json()["acknowledged"] is True

    open_only = client.get("/api/alerts", params={"unacknowledged_only": True}).json()
    assert all(a["id"] != aid for a in open_only)


def test_dashboard_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "NetSentinel" in r.text
