# backend/tests/test_health.py


# No @pytest.mark.django_db — the health view does not touch the database.
# This makes the test faster and fully isolated from DB state.
def test_health_check_returns_200(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}
