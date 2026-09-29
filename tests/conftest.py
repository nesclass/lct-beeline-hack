import pytest
from fastapi.testclient import TestClient

from app import geo, state, store
from app.geo import cache
from app.geo.haversine import Haversine
from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # тесты не должны зависеть от того, поднят ли на машине OSRM, и не должны писать
    # в рабочий кэш матриц
    monkeypatch.setattr(cache, "DIR", tmp_path / "geo")
    monkeypatch.setattr(cache, "_memo", {})
    monkeypatch.setattr(geo, "_provider", Haversine())
    monkeypatch.setenv("GEOCODER_URL", "off")           # и не должны ходить в геокодер
    # app.main читает .env: без этого тесты ходили бы в настоящую языковую модель
    for k in ("LITELLM_API_KEY", "LITELLM_MASTER_KEY"):
        monkeypatch.delenv(k, raising=False)
    state.use(store.connect(tmp_path / "api.sqlite"))
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def sid(client):
    return client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
