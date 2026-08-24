import os

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/testdb")
os.environ.setdefault("VAPI_WEBHOOK_SECRET", "test-secret")

import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.db import mongo as mongo_module


@pytest.fixture(autouse=True)
def use_mock_db(monkeypatch):
    client = AsyncMongoMockClient()
    db = client["carecloud_test"]
    mongo_module.set_db(db)
    yield db


@pytest.fixture
async def app():
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_patient_payload():
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": "01/15/1990",
        "sex": "Female",
        "phone_number": "5551234567",
        "email": "jane.doe@example.com",
        "address_line_1": "123 Main St",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62704",
    }
