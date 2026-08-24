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
