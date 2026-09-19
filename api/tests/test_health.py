from sqlalchemy import text
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal, engine

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_database_connectable():
    with SessionLocal() as session:
        result = session.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_engine_is_mysql():
    assert "mysql" in str(engine.url).lower()
