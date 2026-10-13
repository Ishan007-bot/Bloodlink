import os
from datetime import timedelta

# Tests never touch PostgreSQL: point the app at a throwaway SQLite file before it is imported.
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import utcnow  # noqa: E402


@pytest.fixture()
def client():
    """A fresh, empty schema for every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def hospital(client):
    return client.post("/api/hospitals", json={"name": "City General", "city": "Pune"}).json()


@pytest.fixture()
def stock(client):
    """Create units: stock(group, days_old=1, count=1) -> list of unit ids.

    Each unit comes from a new donor, so the 90-day donation gap never interferes.
    """
    counter = {"n": 0}

    def _make(group: str, days_old: float = 1, count: int = 1) -> list[int]:
        ids = []
        for _ in range(count):
            counter["n"] += 1
            donor = client.post(
                "/api/donors", json={"name": f"Donor {counter['n']}", "blood_group": group}
            ).json()
            collected = (utcnow() - timedelta(days=days_old)).isoformat()
            unit = client.post(
                "/api/donations", json={"donor_id": donor["id"], "collected_at": collected}
            )
            assert unit.status_code == 201, unit.text
            ids.append(unit.json()["id"])
        return ids

    return _make


@pytest.fixture()
def make_request(client, hospital):
    def _make(group: str, units: int, priority: str = "ROUTINE") -> dict:
        response = client.post(
            "/api/requests",
            json={
                "hospital_id": hospital["id"],
                "blood_group": group,
                "units_needed": units,
                "priority": priority,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _make
