from fastapi import APIRouter, Response

from app.api.schemas import fail, ok
from app.services import appointment_service, patient_service

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("/slots")
async def available_slots():
    slots = await appointment_service.get_available_slots()
    return ok(
        [{"slot_id": s["slot_id"], "start_time": s["start_time"].isoformat()} for s in slots]
    )


@router.post("")
async def create_appointment(payload: dict, response: Response):
    patient_id = payload.get("patient_id")
    slot_id = payload.get("slot_id")
    if not patient_id or not slot_id:
        response.status_code = 400
        return fail("BAD_REQUEST", "patient_id and slot_id are required")

    patient = await patient_service.get_patient(patient_id)
    if not patient:
        response.status_code = 404
        return fail("NOT_FOUND", "No patient with that id")

    appt = await appointment_service.book_appointment(
        patient_id=patient_id, slot_id=slot_id, reason=payload.get("reason")
    )
    return ok(
        {
            "appointment_id": appt["appointment_id"],
            "patient_id": patient_id,
            "start_time": appt["start_time"].isoformat(),
            "reason": appt["reason"],
            "status": appt["status"],
        }
    )
