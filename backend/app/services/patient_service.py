"""
Patient business logic - the one place duplicate-detection, soft-delete, and
partial-update rules live. Both the REST API (app/api/patients.py) and the
Vapi webhook (app/api/vapi_tools.py) call into these same functions, so a
patient created by the voice agent and one created via curl go through
identical validation and duplicate-checking - there's no separate "voice
agent path" that could drift from the "API path."
"""

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from app.db.mongo import patients_collection
from app.models.patient import PatientCreate, PatientOut, PatientUpdate


class DuplicatePatientError(Exception):
    """Raised by create_patient when an active (non-deleted) patient already
    has this phone number and the caller didn't explicitly opt into a
    duplicate via allow_duplicate=True. Carries the existing record so the
    caller (API layer or Vapi tool handler) can surface it without a second
    lookup."""

    def __init__(self, existing: PatientOut):
        self.existing = existing


class PatientNotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _doc_to_out(doc: dict) -> PatientOut:
    """Mongo gives back date_of_birth as a BSON datetime (Mongo has no bare
    "date" type); convert it back to a plain date so PatientOut - and every
    API response - deals in dates, not midnight-UTC timestamps."""
    doc = dict(doc)
    doc.pop("_id", None)
    dob = doc.get("date_of_birth")
    if isinstance(dob, datetime):
        doc["date_of_birth"] = dob.date()
    return PatientOut(**doc)


def _dob_to_storage(d: date) -> datetime:
    """The inverse of _doc_to_out's date_of_birth handling - stored as
    midnight UTC so date-only equality queries (list_patients' date_of_birth
    filter) work without a timezone off-by-one."""
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


async def find_active_by_phone(phone_number: str) -> Optional[PatientOut]:
    doc = await patients_collection().find_one(
        {"phone_number": phone_number, "deleted_at": None}
    )
    return _doc_to_out(doc) if doc else None


async def create_patient(payload: PatientCreate, *, allow_duplicate: bool = False) -> PatientOut:
    if not allow_duplicate:
        existing = await find_active_by_phone(payload.phone_number)
        if existing:
            raise DuplicatePatientError(existing)

    now = _now()
    doc = payload.model_dump()
    doc["date_of_birth"] = _dob_to_storage(doc["date_of_birth"])
    doc["patient_id"] = str(uuid.uuid4())
    doc["created_at"] = now
    doc["updated_at"] = now
    doc["deleted_at"] = None

    await patients_collection().insert_one(doc)
    return _doc_to_out(doc)


async def get_patient(patient_id: str) -> Optional[PatientOut]:
    doc = await patients_collection().find_one(
        {"patient_id": patient_id, "deleted_at": None}
    )
    return _doc_to_out(doc) if doc else None


async def list_patients(
    *,
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    phone_number: Optional[str] = None,
) -> list[PatientOut]:
    query: dict = {"deleted_at": None}
    if last_name:
        # re.escape prevents a caller-supplied last_name from being
        # interpreted as a regex (NoSQL injection / ReDoS via query params).
        query["last_name"] = {"$regex": f"^{re.escape(last_name)}$", "$options": "i"}
    if phone_number:
        from app.utils.validators import normalize_phone

        query["phone_number"] = normalize_phone("phone_number", phone_number)
    if date_of_birth:
        from app.utils.validators import parse_date_of_birth

        parsed = parse_date_of_birth("date_of_birth", date_of_birth)
        query["date_of_birth"] = _dob_to_storage(parsed)

    cursor = patients_collection().find(query).sort("created_at", -1)
    return [_doc_to_out(doc) async for doc in cursor]


async def update_patient(patient_id: str, payload: PatientUpdate) -> PatientOut:
    updates = payload.to_update_dict()
    if "date_of_birth" in updates:
        updates["date_of_birth"] = _dob_to_storage(updates["date_of_birth"])

    if not updates:
        # PUT with no actual fields changed (e.g. the voice agent double-
        # calling update_patient after the caller says "actually never
        # mind") - treat as a no-op success rather than a 404/error, since
        # the patient does exist.
        existing = await get_patient(patient_id)
        if not existing:
            raise PatientNotFoundError()
        return existing

    updates["updated_at"] = _now()
    result = await patients_collection().find_one_and_update(
        {"patient_id": patient_id, "deleted_at": None},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise PatientNotFoundError()
    return _doc_to_out(result)


async def soft_delete_patient(patient_id: str) -> PatientOut:
    # Per spec: set deleted_at, never actually remove the document. Every
    # other read path (get_patient, list_patients, find_active_by_phone)
    # filters on deleted_at: None, so a soft-deleted patient simply stops
    # appearing rather than needing a "WHERE NOT deleted" check duplicated
    # everywhere.
    result = await patients_collection().find_one_and_update(
        {"patient_id": patient_id, "deleted_at": None},
        {"$set": {"deleted_at": _now(), "updated_at": _now()}},
        return_document=True,
    )
    if not result:
        raise PatientNotFoundError()
    return _doc_to_out(result)
