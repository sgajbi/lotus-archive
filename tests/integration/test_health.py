from fastapi.testclient import TestClient
from app.main import app


def test_health_endpoints() -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_correlation_header_propagation() -> None:
    client = TestClient(app)
    response = client.get(
        "/health",
        headers={"X-Correlation-Id": "corr-123", "X-Trace-Id": "trace-456"},
    )
    assert response.status_code == 200
    assert response.headers["X-Correlation-Id"] == "corr-123"
    assert response.headers["X-Trace-Id"] == "trace-456"


def test_readiness_reports_draining_state() -> None:
    client = TestClient(app)
    app.state.is_draining = True
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "draining"
    finally:
        app.state.is_draining = False


def test_unknown_route_uses_support_safe_error_envelope() -> None:
    client = TestClient(app)
    response = client.get(
        "/documents/not-yet-implemented", headers={"X-Correlation-Id": "corr-404"}
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "The requested resource was not found.",
            "correlation_id": "corr-404",
            "service": "lotus-archive",
        }
    }
