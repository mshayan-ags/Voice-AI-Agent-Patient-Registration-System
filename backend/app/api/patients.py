"""
REST CRUD for patients. Every handler follows the same shape: parse/validate
input (Pydantic -> app/models/patient.py), delegate to the service layer
(app/services/patient_service.py) for the actual business logic, then wrap
the result in the {"data", "error"} envelope the spec requires. HTTP status
codes are set via the injected Response object rather than raising
HTTPException, so a 422/404/409 body still uses the same envelope shape as
a 200 - no special-cased error format for FastAPI's default exception
handling to produce instead.
"""

from fastapi import APIRouter, Query, Request, Response
from pydantic import ValidationError as PydanticValidationError

from app.api.schemas import fail, ok
from app.core.logging import logger
from app.models.patient import PatientCreate, PatientUpdate
from app.services import patient_service
from app.services.patient_service import DuplicatePatientError, PatientNotFoundError
from app.utils.validators import ValidationError, all_field_errors

router = APIRouter(prefix="/patients", tags=["patients"])


def _validation_error_response(e: Exception) -> dict:
    """Builds one response carrying every failing field, not just the
    first - a form with 6 bad fields should tell the caller (or the voice
    agent relaying this) about all 6 in one round trip."""
    errors = all_field_errors(e)
    first_field, first_message = next(iter(errors.items()))
    # Single-field case keeps the simple, existing `field`/`message` shape;
    # multi-field adds `field_errors` alongside without breaking that shape.
    return fail(
        "VALIDATION_ERROR",
        first_message if len(errors) == 1 else f"{len(errors)} fields need attention",
        first_field,
        field_errors=errors if len(errors) > 1 else None,
    )


def _duplicate_response(existing) -> dict:
    # Keeps the {data, error} contract strict - exactly one populated, never
    # both - by carrying the conflicting record under error.details instead
    # of also setting top-level `data` on what is fundamentally an error.
    return fail(
        "DUPLICATE_PATIENT",
        f"A patient with this phone number already exists: "
        f"{existing.first_name} {existing.last_name}",
        details={"existing_patient": existing.model_dump(mode="json")},
    )


@router.get("")
async def list_patients(
    response: Response,
    last_name: str | None = Query(default=None),
    date_of_birth: str | None = Query(default=None),
    phone_number: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        patients, total = await patient_service.list_patients(
            last_name=last_name,
            date_of_birth=date_of_birth,
            phone_number=phone_number,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
    except ValidationError as e:
        response.status_code = 422
        return fail("VALIDATION_ERROR", e.message, e.field)
    response.headers["X-Total-Count"] = str(total)
    return ok([p.model_dump(mode="json") for p in patients])


@router.get("/{patient_id}")
async def get_patient(patient_id: str, response: Response):
    patient = await patient_service.get_patient(patient_id)
    if not patient:
        response.status_code = 404
        return fail("NOT_FOUND", "No patient with that id")
    return ok(patient.model_dump(mode="json"))


@router.post("", status_code=201)
async def create_patient(request: Request, response: Response):
    body = await request.json()
    allow_duplicate = bool(body.pop("allow_duplicate", False))

    try:
        payload = PatientCreate(**body)
    except (PydanticValidationError, ValidationError) as e:
        response.status_code = 422
        return _validation_error_response(e)

    try:
        patient = await patient_service.create_patient(payload, allow_duplicate=allow_duplicate)
    except DuplicatePatientError as e:
        response.status_code = 409
        return _duplicate_response(e.existing)

    # Per the "observability" requirement: the full collected payload, not
    # just an id, lands in stdout at the moment a registration completes.
    logger.info("patient created: %s", payload.model_dump(mode="json"))
    return ok(patient.model_dump(mode="json"))


@router.put("/{patient_id}")
async def update_patient(patient_id: str, request: Request, response: Response):
    body = await request.json()
    allow_duplicate = bool(body.pop("allow_duplicate", False))

    try:
        payload = PatientUpdate(**body)
    except (PydanticValidationError, ValidationError) as e:
        response.status_code = 422
        return _validation_error_response(e)

    try:
        patient = await patient_service.update_patient(
            patient_id, payload, allow_duplicate=allow_duplicate
        )
    except PatientNotFoundError:
        response.status_code = 404
        return fail("NOT_FOUND", "No patient with that id")
    except DuplicatePatientError as e:
        response.status_code = 409
        return _duplicate_response(e.existing)

    logger.info("patient updated: patient_id=%s fields=%s", patient_id, list(body.keys()))
    return ok(patient.model_dump(mode="json"))


@router.delete("/{patient_id}")
async def delete_patient(patient_id: str, response: Response):
    try:
        patient = await patient_service.soft_delete_patient(patient_id)
    except PatientNotFoundError:
        response.status_code = 404
        return fail("NOT_FOUND", "No patient with that id")

    logger.info("patient soft-deleted patient_id=%s", patient_id)
    return ok(patient.model_dump(mode="json"))
