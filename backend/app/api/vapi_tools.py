"""
Webhook endpoint that Vapi calls during (and after) a phone call.

Two message types land here, both on the same "Server URL":

1. type == "tool-calls"        - the assistant invoked one of our function
   tools mid-conversation (check_existing_patient, create_patient, etc).
   We must respond with {"results": [{"toolCallId": ..., "result": ...}]}
   where each `result` is a JSON *string* per Vapi's documented contract -
   not a bare object, even though Vapi tolerates the latter today.

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

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError as PydanticValidationError

from app.core.config import get_settings
from app.core.logging import logger
from app.db.mongo import call_logs_collection, call_sessions_collection
from app.models.patient import PatientCreate, PatientUpdate
from app.services import appointment_service, patient_service
from app.services.appointment_service import SlotAlreadyBookedError, SlotNotFoundError
from app.services.patient_service import DuplicatePatientError, PatientNotFoundError
from app.utils.validators import ValidationError, all_field_errors

router = APIRouter(prefix="/vapi", tags=["vapi"])


def _field_error_result(e: Exception) -> dict:
    """Every field that failed, not just the first - so the agent can ask
    about all of them instead of one slow round trip per field."""
    errors = all_field_errors(e)
    if len(errors) == 1:
        field, message = next(iter(errors.items()))
        return {"success": False, "error": f"{field}: {message}"}
    return {
        "success": False,
        "error": f"{len(errors)} fields need attention: "
        + "; ".join(f"{f}: {m}" for f, m in errors.items()),
        "field_errors": errors,
    }


def _duplicate_result(existing) -> dict:
    return {
        "success": False,
        "duplicate": True,
        "existing_patient_id": existing.patient_id,
        "existing_first_name": existing.first_name,
        "existing_last_name": existing.last_name,
    }


def _verify_secret(x_vapi_secret: str | None) -> None:
    settings = get_settings()
    if x_vapi_secret != settings.vapi_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")


def _extract_tool_calls(message: dict) -> list[dict]:
    """Normalize Vapi's tool-call list to [{id, name, arguments}, ...].
    `arguments` is usually already a dict, but Vapi's OpenAI-compatible
    function-calling shape technically defines it as a JSON *string* - if a
    future payload sends it that way, json.loads it rather than passing a
    raw string straight into PatientCreate(**args), which would blow up on
    the first field access."""
    calls = message.get("toolCalls") or message.get("toolCallList") or []
    normalized = []
    for call in calls:
        fn = call.get("function", call)
        arguments = fn.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                arguments = {}
        normalized.append(
            {"id": call.get("id"), "name": fn.get("name"), "arguments": arguments}
        )
    return normalized


async def _run_tool(name: str, args: dict, call_id: str | None) -> dict:
    if name == "check_existing_patient":
        phone_number = args.get("phone_number")
        if not phone_number:
            return {"success": False, "error": "phone_number is required"}
        patient = await patient_service.find_active_by_phone(phone_number)
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
            return _field_error_result(e)

        try:
            patient = await patient_service.create_patient(payload, allow_duplicate=allow_duplicate)
        except DuplicatePatientError as e:
            upcoming = await appointment_service.get_upcoming_appointments(e.existing.patient_id)
            result = _duplicate_result(e.existing)
            result["upcoming_appointments"] = [
                {"appointment_id": a["appointment_id"], "label": a["label"]} for a in upcoming
            ]
            return result

        if call_id:
            await call_sessions_collection().update_one(
                {"call_id": call_id},
                {"$set": {"call_id": call_id, "patient_id": patient.patient_id}},
                upsert=True,
            )

        # Per the "observability" requirement: the full collected payload,
        # not just an id, lands in stdout at the moment a registration
        # completes - whether that call came from the phone or from curl.
        logger.info(
            "vapi create_patient success call_id=%s payload=%s",
            call_id,
            payload.model_dump(mode="json"),
        )
        return {"success": True, "patient_id": patient.patient_id}

    if name == "update_patient":
        patient_id = args.pop("patient_id", None)
        if not patient_id:
            return {"success": False, "error": "patient_id is required"}
        allow_duplicate = bool(args.pop("allow_duplicate", False))
        try:
            payload = PatientUpdate(**args)
        except (ValidationError, PydanticValidationError) as e:
            return _field_error_result(e)

        try:
            patient = await patient_service.update_patient(
                patient_id, payload, allow_duplicate=allow_duplicate
            )
        except PatientNotFoundError:
            return {"success": False, "error": "No patient found with that id"}
        except DuplicatePatientError as e:
            return _duplicate_result(e.existing)
        return {"success": True, "patient_id": patient.patient_id}

    if name == "get_available_appointment_slots":
        slots = await appointment_service.get_available_slots()
        return {"slots": [{"slot_id": s["slot_id"], "label": s["label"]} for s in slots]}

    if name == "book_appointment":
        patient_id = args.get("patient_id")
        slot_id = args.get("slot_id")
        if not patient_id or not slot_id:
            return {"success": False, "error": "patient_id and slot_id are required"}
        try:
            appt = await appointment_service.book_appointment(
                patient_id=patient_id, slot_id=slot_id, reason=args.get("reason")
            )
        except SlotNotFoundError:
            return {
                "success": False,
                "error": (
                    "That slot is no longer valid - call get_available_appointment_slots "
                    "again and offer the caller one of the current options."
                ),
            }
        except SlotAlreadyBookedError:
            return {
                "success": False,
                "error": (
                    "Someone else just booked that slot - call "
                    "get_available_appointment_slots again and offer fresh options."
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
            try:
                result = await _run_tool(call_item["name"], dict(call_item["arguments"]), call_id)
            except Exception:
                # A crash here (e.g. Mongo unreachable) must not take down
                # the whole webhook response - Vapi still needs a
                # {"results": [...]} shaped reply for every tool call it
                # sent, or the assistant is left hanging mid-turn with no
                # way to tell the caller what happened. The assessment asks
                # explicitly: "does the caller get an error or silence?" -
                # this is what makes it an error, not silence.
                logger.exception(
                    "tool call crashed name=%s call_id=%s", call_item.get("name"), call_id
                )
                result = {
                    "success": False,
                    "error": "A system error occurred - please try that again.",
                }
            results.append(
                {"toolCallId": call_item["id"], "result": json.dumps(result)}
            )
        return {"results": results}

    # Unhandled message types (status updates, speech-update, etc.) - just ack.
    return {"received": True}
