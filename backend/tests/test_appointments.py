import pytest

from app.services import appointment_service
from app.services.appointment_service import SlotNotFoundError


async def test_available_slots_have_id_and_label():
    slots = await appointment_service.get_available_slots()
    assert len(slots) > 0
    for s in slots:
        assert s["slot_id"]
        assert s["label"]


async def test_book_appointment_with_valid_slot():
    slots = await appointment_service.get_available_slots()
    slot_id = slots[0]["slot_id"]
    appt = await appointment_service.book_appointment("patient-123", slot_id, reason="checkup")
    assert appt["patient_id"] == "patient-123"
    assert appt["label"] == slots[0]["label"]
    assert appt["status"] == "scheduled"


async def test_book_appointment_with_invalid_slot_raises():
    with pytest.raises(SlotNotFoundError):
        await appointment_service.book_appointment("patient-123", "not-a-real-slot")


async def test_upcoming_appointments_returns_booked_slot():
    slots = await appointment_service.get_available_slots()
    await appointment_service.book_appointment("patient-abc", slots[0]["slot_id"])

    upcoming = await appointment_service.get_upcoming_appointments("patient-abc")
    assert len(upcoming) == 1
    assert upcoming[0]["label"] == slots[0]["label"]


async def test_upcoming_appointments_empty_for_unknown_patient():
    upcoming = await appointment_service.get_upcoming_appointments("nobody-here")
    assert upcoming == []


async def test_list_appointments_filters_by_patient(client, valid_patient_payload):
    created = (await client.post("/patients", json=valid_patient_payload)).json()["data"]
    other = dict(valid_patient_payload, phone_number="5559991111", last_name="Other")
    other_created = (await client.post("/patients", json=other)).json()["data"]

    slots = (await client.get("/appointments/slots")).json()["data"]
    await client.post(
        "/appointments", json={"patient_id": created["patient_id"], "slot_id": slots[0]["slot_id"]}
    )
    await client.post(
        "/appointments",
        json={"patient_id": other_created["patient_id"], "slot_id": slots[1]["slot_id"]},
    )

    all_appts = (await client.get("/appointments")).json()["data"]
    assert len(all_appts) == 2

    filtered = (await client.get(f"/appointments?patient_id={created['patient_id']}")).json()["data"]
    assert len(filtered) == 1
    assert filtered[0]["patient_name"] == "Jane Doe"


async def test_book_appointment_rest_endpoint_rejects_unknown_patient(client):
    slots = (await client.get("/appointments/slots")).json()["data"]
    resp = await client.post(
        "/appointments", json={"patient_id": "does-not-exist", "slot_id": slots[0]["slot_id"]}
    )
    assert resp.status_code == 404
