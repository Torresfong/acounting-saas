import pytest


@pytest.mark.django_db
def test_health_page_reports_app_and_database_up(client):
    response = client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
