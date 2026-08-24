from fastapi import APIRouter, Response

from app.api.schemas import fail, ok
from app.services import appointment_service, patient_service

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("/slots")
async def available_slots():
    slots = await appointment_service.get_available_slots()
    return ok([{"slot_id": s["slot_id"], "label": s["label"]} for s in slots])


@router.get("")
async def list_appointments(patient_id: str | None = None):
    appointments = await appointment_service.list_appointments(patient_id)
    # Light join so the dashboard doesn't need a second round-trip per row -
    # fine at this data volume; a real system would denormalize or paginate.
    enriched = []
    for a in appointments:
        patient = await patient_service.get_patient(a["patient_id"])
        enriched.append(
            {
                "appointment_id": a["appointment_id"],
                "patient_id": a["patient_id"],
                "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
                "label": a["label"],
                "reason": a.get("reason"),
                "status": a["status"],
                "created_at": a["created_at"].isoformat(),
            }
        )
    return ok(enriched)


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
            "label": appt["label"],
            "reason": appt["reason"],
            "status": appt["status"],
        }
    )
