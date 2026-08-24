"""
Lazily-initialized Motor client/database, module-level singletons so every
request reuses the same connection pool instead of opening a new one per
call. `set_db` exists purely so tests can swap in a mongomock database
before any collection accessor below is first used - production code never
calls it.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        settings = get_settings()
        _db = get_client()[settings.mongodb_db_name]
    return _db


def set_db(db: AsyncIOMotorDatabase) -> None:
    """Test hook - lets pytest swap in a mongomock database."""
    global _db
    _db = db


def patients_collection():
    return get_db()["patients"]


def call_logs_collection():
    return get_db()["call_logs"]


def call_sessions_collection():
    return get_db()["call_sessions"]


def appointments_collection():
    return get_db()["appointments"]


async def ensure_indexes() -> None:
    """Run once at startup (see app/main.py's lifespan). create_index is a
    no-op if the index already exists, so this is safe to call on every
    boot rather than needing a separate migration step."""
    patients = patients_collection()
    await patients.create_index("patient_id", unique=True)
    # phone_number, last_name, date_of_birth back the three GET /patients
    # filters plus the duplicate-detection lookup by phone.
    await patients.create_index("phone_number")
    await patients.create_index("last_name")
    await patients.create_index("date_of_birth")
    await patients.create_index("deleted_at")

    await call_logs_collection().create_index("patient_id")
    # call_id is unique because it's how a mid-call tool-call's create_patient
    # result gets correlated with that same call's later end-of-call-report.
    await call_sessions_collection().create_index("call_id", unique=True)
    await appointments_collection().create_index("patient_id")
