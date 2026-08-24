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
    # Exactly one of {data, error} populated, always - the conflicting
    # record rides under error.details, not a second top-level `data`.
    assert body["data"] is None
    assert body["error"]["code"] == "DUPLICATE_PATIENT"
    assert body["error"]["details"]["existing_patient"]["first_name"] == "Jane"


async def test_update_patient_rejects_phone_collision(client, valid_patient_payload):
    a = (await client.post("/patients", json=valid_patient_payload)).json()["data"]
    b_payload = dict(valid_patient_payload, phone_number="5559998888", last_name="Other")
    b = (await client.post("/patients", json=b_payload)).json()["data"]

    resp = await client.put(
        f"/patients/{b['patient_id']}", json={"phone_number": valid_patient_payload["phone_number"]}
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["details"]["existing_patient"]["patient_id"] == a["patient_id"]


async def test_create_patient_reports_multiple_field_errors(client, valid_patient_payload):
    bad = dict(valid_patient_payload, state="ZZ", zip_code="notazip")
    resp = await client.post("/patients", json=bad)
    assert resp.status_code == 422
    body = resp.json()
    assert set(body["error"]["field_errors"].keys()) == {"state", "zip_code"}


async def test_create_patient_accepts_multi_word_name(client, valid_patient_payload):
    payload = dict(valid_patient_payload, first_name="Mary Jane", last_name="Van Der Berg")
    resp = await client.post("/patients", json=payload)
    assert resp.status_code == 201
    assert resp.json()["data"]["last_name"] == "Van Der Berg"


async def test_create_patient_rejects_unknown_field(client, valid_patient_payload):
    bad = dict(valid_patient_payload, favorite_color="blue")
    resp = await client.post("/patients", json=bad)
    assert resp.status_code == 422


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


async def test_health_check_reports_database_connected(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "connected"}


async def test_list_patients_respects_limit(client, valid_patient_payload):
    names = ["Adams", "Baker", "Carter"]
    for i, name in enumerate(names):
        payload = dict(valid_patient_payload, phone_number=f"555111000{i}", last_name=name)
        resp = await client.post("/patients", json=payload)
        assert resp.status_code == 201

    resp = await client.get("/patients", params={"limit": 2})
    assert len(resp.json()["data"]) == 2
    assert resp.headers["x-total-count"] == "3"


async def test_list_patients_excludes_deleted_by_default_and_include_deleted_shows_them(
    client, valid_patient_payload
):
    created = (await client.post("/patients", json=valid_patient_payload)).json()["data"]
    await client.delete(f"/patients/{created['patient_id']}")

    resp = await client.get("/patients")
    assert all(p["patient_id"] != created["patient_id"] for p in resp.json()["data"])

    resp_incl = await client.get("/patients", params={"include_deleted": "true"})
    assert any(p["patient_id"] == created["patient_id"] for p in resp_incl.json()["data"])


async def test_data_persists_across_requests_second_call_simulation(client, valid_patient_payload):
    """Simulates 'call back later and the data is still there' from the spec."""
    created = (await client.post("/patients", json=valid_patient_payload)).json()["data"]

    lookup = await client.get("/patients", params={"phone_number": "555-123-4567"})
    data = lookup.json()["data"]
    assert len(data) == 1
    assert data[0]["patient_id"] == created["patient_id"]
