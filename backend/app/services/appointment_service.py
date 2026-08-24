import uuid
from datetime import datetime, timedelta, timezone

from app.db.mongo import appointments_collection

# Bonus feature: appointment scheduling. There's no real scheduling system to
# integrate with in 3 hours, so this hands back a small set of mock open slots
# and "books" whichever one the caller/agent picks. Good enough to demonstrate
# the pattern; a real implementation would call an actual scheduling API.
_MOCK_SLOT_HOURS = [9, 11, 14, 16]


class SlotNotFoundError(Exception):
    """Raised when book_appointment is given a slot_id that doesn't match one
    of the currently-offered slots. The caller (Vapi tool handler) must
    surface this as a real error rather than silently booking something
    different from what the caller agreed to - a wrong appointment time is
    worse than no appointment at all."""


def _format_slot_label(dt: datetime) -> str:
    # strftime's no-leading-zero flags ('%-d' / '%-I') are POSIX-only and
    # raise on Windows, so the day/hour are formatted manually to stay
    # portable between local (Windows) dev and Linux deployment.
    hour_12 = dt.hour % 12 or 12
    am_pm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%A, %B')} {dt.day} at {hour_12}:{dt.minute:02d} {am_pm}"


def _mock_open_slots(days_ahead: int = 7) -> list[dict]:
    slots = []
    base = datetime.now(timezone.utc) + timedelta(days=1)
    for day_offset in range(days_ahead):
        day = base + timedelta(days=day_offset)
        if day.weekday() >= 5:  # skip weekends
            continue
        for hour in _MOCK_SLOT_HOURS:
            slot_time = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            slots.append(
                {
                    "slot_id": slot_time.strftime("%Y%m%dT%H%M"),
                    "start_time": slot_time,
                    # Human-readable label, generated once here so the LLM's
                    # read-back and the slot_id it sends to book_appointment
                    # always refer to the exact same slot - no re-deriving
                    # "Tuesday at 9am" from a raw timestamp on either side.
                    "label": _format_slot_label(slot_time),
                }
            )
    return slots


async def get_available_slots(limit: int = 3) -> list[dict]:
    return _mock_open_slots()[:limit]


async def get_upcoming_appointments(patient_id: str, limit: int = 3) -> list[dict]:
    """Used for the 'do I already have an appointment' proactive check -
    surfaced as soon as an existing patient is identified by phone number,
    not just after a fresh booking."""
    now = datetime.now(timezone.utc)
    cursor = (
        appointments_collection()
        .find({"patient_id": patient_id, "status": "scheduled", "start_time": {"$gte": now}})
        .sort("start_time", 1)
        .limit(limit)
    )
    appointments = []
    async for doc in cursor:
        doc.pop("_id", None)
        # Defensive: appointments booked before `label` was added to the
        # stored document (or written by some other path) shouldn't blow up
        # every subsequent lookup - derive one on the fly instead.
        if not doc.get("label"):
            doc["label"] = _format_slot_label(doc["start_time"])
        appointments.append(doc)
    return appointments


async def book_appointment(patient_id: str, slot_id: str, reason: str | None = None) -> dict:
    slots = {s["slot_id"]: s for s in _mock_open_slots()}
    slot = slots.get(slot_id)
    if slot is None:
        raise SlotNotFoundError(f"'{slot_id}' is not one of the currently offered slots")

    appointment = {
        "appointment_id": str(uuid.uuid4()),
        "patient_id": patient_id,
        "start_time": slot["start_time"],
        "label": slot["label"],
        "reason": reason,
        "status": "scheduled",
        "created_at": datetime.now(timezone.utc),
    }
    await appointments_collection().insert_one(dict(appointment))
    return appointment
