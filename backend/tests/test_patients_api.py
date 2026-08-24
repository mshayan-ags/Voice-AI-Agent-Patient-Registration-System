import pytest


async def test_create_patient_success(client, valid_patient_payload):
    resp = await client.post("/patients", json=valid_patient_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["first_name"] == "Jane"
    assert body["data"]["phone_number"] == "5551234567"
    assert "patient_id" in body["data"]


async def test_create_patient_validation_error(client, valid_patient_payload):
    bad = dict(valid_patient_payload, state="ZZ")
    resp = await client.post("/patients", json=bad)
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_create_patient_rejects_future_dob(client, valid_patient_payload):
    bad = dict(valid_patient_payload, date_of_birth="01/01/2999")
    resp = await client.post("/patients", json=bad)
    assert resp.status_code == 422


async def test_duplicate_phone_number_returns_409(client, valid_patient_payload):
    first = await client.post("/patients", json=valid_patient_payload)
    assert first.status_code == 201

    dup = dict(valid_patient_payload, first_name="Janet")
    resp = await client.post("/patients", json=dup)
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "DUPLICATE_PATIENT"
    assert body["data"]["existing_patient"]["first_name"] == "Jane"


async def test_get_patient_by_id(client, valid_patient_payload):
    created = (await client.post("/patients", json=valid_patient_payload)).json()["data"]
    resp = await client.get(f"/patients/{created['patient_id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["last_name"] == "Doe"


async def test_get_patient_not_found(client):
    resp = await client.get("/patients/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_list_patients_filter_by_last_name(client, valid_patient_payload):
    await client.post("/patients", json=valid_patient_payload)
    other = dict(valid_patient_payload, last_name="Smith", phone_number="5559998888")
    await client.post("/patients", json=other)

    resp = await client.get("/patients", params={"last_name": "Doe"})
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["last_name"] == "Doe"


async def test_update_patient_partial(client, valid_patient_payload):
    created = (await client.post("/patients", json=valid_patient_payload)).json()["data"]
    resp = await client.put(f"/patients/{created['patient_id']}", json={"city": "Chicago"})
    assert resp.status_code == 200
    updated = resp.json()["data"]
    assert updated["city"] == "Chicago"
    assert updated["last_name"] == "Doe"  # untouched fields survive


async def test_soft_delete_hides_patient(client, valid_patient_payload):
    created = (await client.post("/patients", json=valid_patient_payload)).json()["data"]
    patient_id = created["patient_id"]

    del_resp = await client.delete(f"/patients/{patient_id}")
    assert del_resp.status_code == 200

    get_resp = await client.get(f"/patients/{patient_id}")
    assert get_resp.status_code == 404

    list_resp = await client.get("/patients")
    assert all(p["patient_id"] != patient_id for p in list_resp.json()["data"])


async def test_data_persists_across_requests_second_call_simulation(client, valid_patient_payload):
    """Simulates 'call back later and the data is still there' from the spec."""
    created = (await client.post("/patients", json=valid_patient_payload)).json()["data"]

    lookup = await client.get("/patients", params={"phone_number": "555-123-4567"})
    data = lookup.json()["data"]
    assert len(data) == 1
    assert data[0]["patient_id"] == created["patient_id"]
