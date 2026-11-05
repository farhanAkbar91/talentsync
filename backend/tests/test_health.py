"""Health + error envelope (P0, dipertahankan & disesuaikan fixture baru)."""


def test_liveness_returns_200(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"
    assert resp.headers["X-Request-ID"]


def test_ready_with_dead_db_returns_503_envelope(client_dead_db):
    resp = client_dead_db.get("/api/v1/health/ready")
    assert resp.status_code == 503
    err = resp.json()["error"]
    assert err["code"] == "DEPENDENCY_UNAVAILABLE"
    assert err["request_id"]
    assert "127.0.0.1" not in resp.text


def test_unknown_route_returns_404_envelope(client):
    resp = client.get("/api/v1/tidak-ada")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_method_not_allowed_returns_405_envelope(client):
    resp = client.delete("/api/v1/health")
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_root_points_to_docs(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["docs"] == "/docs"
