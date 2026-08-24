"""
Optional demo seed data - inserts two sample patients so the API/dashboard
has something to show immediately after a fresh deploy. Safe to run more
than once; skips patients whose phone number already exists.

Usage (from backend/):
    python -m scripts.seed_data
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.mongo import ensure_indexes  # noqa: E402
from app.models.patient import PatientCreate  # noqa: E402
from app.services.patient_service import DuplicatePatientError, create_patient  # noqa: E402

SEED_PATIENTS = [
    {
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": "05/12/1988",
        "sex": "Female",
        "phone_number": "5555550111",
        "email": "jane.doe@example.com",
        "address_line_1": "742 Evergreen Terrace",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62704",
        "preferred_language": "English",
    },
    {
        "first_name": "Marcus",
        "last_name": "Reed",
        "date_of_birth": "11/03/1975",
        "sex": "Male",
        "phone_number": "5555550122",
        "address_line_1": "1600 Pennsylvania Ave",
        "city": "Austin",
        "state": "TX",
        "zip_code": "73301",
        "insurance_provider": "Blue Cross",
        "insurance_member_id": "BX992134",
        "preferred_language": "English",
    },
]


async def main():
    await ensure_indexes()
    for raw in SEED_PATIENTS:
        try:
            patient = await create_patient(PatientCreate(**raw))
            print(f"created {patient.first_name} {patient.last_name} ({patient.patient_id})")
        except DuplicatePatientError:
            print(f"skipped {raw['first_name']} {raw['last_name']} - already exists")


if __name__ == "__main__":
    asyncio.run(main())
