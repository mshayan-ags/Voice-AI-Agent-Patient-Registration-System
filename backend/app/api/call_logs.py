from fastapi import APIRouter

from app.api.schemas import ok
from app.db.mongo import call_logs_collection

router = APIRouter(prefix="/call-logs", tags=["call-logs"])


@router.get("")
async def list_call_logs(patient_id: str | None = None):
    query = {"patient_id": patient_id} if patient_id else {}
    cursor = call_logs_collection().find(query).sort("created_at", -1)
    logs = []
    async for doc in cursor:
        doc.pop("_id", None)
        logs.append(doc)
    return ok(logs)
