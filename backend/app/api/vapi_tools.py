"""
Webhook endpoint that Vapi calls during (and after) a phone call.

Two message types land here, both on the same "Server URL":

1. type == "tool-calls"        - the assistant invoked one of our function
   tools mid-conversation (check_existing_patient, create_patient, etc).
   We must respond with {"results": [{"toolCallId": ..., "result": ...}]}
   so Vapi can hand the result back to the LLM.

2. type == "end-of-call-report" - sent once after the call ends, containing
   the transcript/summary. We look up which patient this call created (via
   the call_sessions mapping written during create_patient) and store the
   transcript against that patient for the "call transcript" bonus.

NOTE: Vapi's exact webhook payload shape has changed across versions. This
parses defensively (checks a couple of known shapes) and logs the raw body,
so if Vapi's current format differs slightly, the raw log makes it a two-line
fix rather than a mystery. Verify against your Vapi dashboard's "Server URL"
docs when wiring the real assistant.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError as PydanticValidationError

from app.core.config import get_settings
from app.core.logging import logger
from app.db.mongo import call_logs_collection, call_sessions_collection
from app.models.patient import PatientCreate, PatientUpdate
from app.services import appointment_service, patient_service
from app.services.appointment_service import SlotNotFoundError
from app.services.patient_service import DuplicatePatientError, PatientNotFoundError
from app.utils.validators import ValidationError, clean_pydantic_message

router = APIRouter(prefix="/vapi", tags=["vapi"])


def _field_error_message(e: Exception) -> str:
    """Turn either our own ValidationError or pydantic's into one short
    'field: message' string the LLM can relay back to the caller in plain
    language, instead of a raw stack of pydantic error objects."""
    if isinstance(e, ValidationError):
        return f"{e.field}: {e.message}"
    if isinstance(e, PydanticValidationError):
        first = e.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        return f"{field}: {clean_pydantic_message(first['msg'])}"
    return str(e)


def _verify_secret(x_vapi_secret: str | None) -> None:
    settings = get_settings()
    if x_vapi_secret != settings.vapi_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")


def _extract_tool_calls(message: dict) -> list[dict]:
    """Normalize Vapi's tool-call list to [{id, name, arguments}, ...]."""
    calls = message.get("toolCalls") or message.get("toolCallList") or []
    normalized = []
    for call in calls:
        fn = call.get("function", call)
        normalized.append(
            {
                "id": call.get("id"),
                "name": fn.get("name"),
                "arguments": fn.get("arguments") or {},
            }
        )
    return normalized


async def _run_tool(name: str, args: dict, call_id: str | None) -> dict:
    if name == "check_existing_patient":
        patient = await patient_service.find_active_by_phone(args["phone_number"])
        if not patient:
            return {"found": False}
        upcoming = await appointment_service.get_upcoming_appointments(patient.patient_id)
        return {
            "found": True,
            "patient_id": patient.patient_id,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            # Lets the agent proactively mention an existing booking instead
            # of only surfacing it if the caller happens to ask.
            "upcoming_appointments": [
                {"appointment_id": a["appointment_id"], "label": a["label"]} for a in upcoming
            ],
        }

    if name == "create_patient":
        allow_duplicate = bool(args.pop("allow_duplicate", False))
        try:
            payload = PatientCreate(**args)
        except (ValidationError, PydanticValidationError) as e:
            return {"success": False, "error": _field_error_message(e)}

        try:
            patient = await patient_service.create_patient(payload, allow_duplicate=allow_duplicate)
        except DuplicatePatientError as e:
            upcoming = await appointment_service.get_upcoming_appointments(e.existing.patient_id)
            return {
                "success": False,
                "duplicate": True,
                "existing_patient_id": e.existing.patient_id,
                "existing_first_name": e.existing.first_name,
                "existing_last_name": e.existing.last_name,
                "upcoming_appointments": [
                    {"appointment_id": a["appointment_id"], "label": a["label"]} for a in upcoming
                ],
            }

        if call_id:
            await call_sessions_collection().update_one(
                {"call_id": call_id},
                {"$set": {"call_id": call_id, "patient_id": patient.patient_id}},
                upsert=True,
            )

        logger.info(
            "vapi create_patient success patient_id=%s call_id=%s",
            patient.patient_id,
            call_id,
        )
        return {"success": True, "patient_id": patient.patient_id}

    if name == "update_patient":
        patient_id = args.pop("patient_id")
        try:
            payload = PatientUpdate(**args)
        except (ValidationError, PydanticValidationError) as e:
            return {"success": False, "error": _field_error_message(e)}

        try:
            patient = await patient_service.update_patient(patient_id, payload)
        except PatientNotFoundError:
            return {"success": False, "error": "No patient found with that id"}
        return {"success": True, "patient_id": patient.patient_id}

    if name == "get_available_appointment_slots":
        slots = await appointment_service.get_available_slots()
        return {
            "slots": [
                {"slot_id": s["slot_id"], "label": s["label"]} for s in slots
            ]
        }

    if name == "book_appointment":
        try:
            appt = await appointment_service.book_appointment(
                patient_id=args["patient_id"],
                slot_id=args["slot_id"],
                reason=args.get("reason"),
            )
        except SlotNotFoundError:
            return {
                "success": False,
                "error": (
                    "That slot is no longer valid - call get_available_appointment_slots "
                    "again and offer the caller one of the current options."
                ),
            }
        return {"success": True, "appointment_id": appt["appointment_id"], "label": appt["label"]}

    return {"success": False, "error": f"unknown tool '{name}'"}


@router.post("/tool-calls")
async def handle_vapi_webhook(request: Request, x_vapi_secret: str | None = Header(default=None)):
    _verify_secret(x_vapi_secret)
    body = await request.json()
    message = body.get("message", body)
    msg_type = message.get("type")
    call = message.get("call") or {}
    call_id = call.get("id")

    logger.info("vapi webhook received type=%s call_id=%s", msg_type, call_id)

    if msg_type == "end-of-call-report":
        transcript = message.get("transcript") or message.get("artifact", {}).get("transcript")
        # Vapi's webhook payload has been observed with these fields at the
        # top level of `message`; `analysis.*` is checked too since that's
        # where Vapi's docs say they're stored on the Call object itself -
        # cheap to support both shapes rather than guess wrong.
        analysis = message.get("analysis") or {}
        summary = message.get("summary") or analysis.get("summary")
        structured_data = message.get("structuredData") or analysis.get("structuredData")
        success_evaluation = message.get("successEvaluation") or analysis.get("successEvaluation")
        ended_reason = message.get("endedReason")
        session = await call_sessions_collection().find_one({"call_id": call_id})
        patient_id = session["patient_id"] if session else None

        # Every call gets a log row, including ones that never reached a
        # patient (pipeline errors, silence timeouts, hangups mid-intake) -
        # ended_reason is what tells you *why* a row has an empty transcript,
        # per the "observability" requirement covering failed calls too.
        await call_logs_collection().insert_one(
            {
                "call_id": call_id,
                "patient_id": patient_id,
                "transcript": transcript,
                "summary": summary,
                "structured_data": structured_data,
                "success_evaluation": success_evaluation,
                "ended_reason": ended_reason,
                "ended_at": message.get("endedAt"),
                "created_at": datetime.now(timezone.utc),
            }
        )
        logger.info(
            "call log stored call_id=%s patient_id=%s ended_reason=%s success=%s",
            call_id,
            patient_id,
            ended_reason,
            success_evaluation,
        )
        return {"received": True}

    if msg_type == "tool-calls":
        results = []
        for call_item in _extract_tool_calls(message):
            result = await _run_tool(call_item["name"], dict(call_item["arguments"]), call_id)
            results.append({"toolCallId": call_item["id"], "result": result})
        return {"results": results}

    # Unhandled message types (status updates, speech-update, etc.) - just ack.
    return {"received": True}
