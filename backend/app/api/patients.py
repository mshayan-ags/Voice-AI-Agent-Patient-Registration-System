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
from app.utils.validators import ValidationError, clean_pydantic_message

router = APIRouter(prefix="/patients", tags=["patients"])


def _pydantic_error(e: PydanticValidationError) -> dict:
    first = e.errors()[0]
    field = ".".join(str(p) for p in first["loc"])
    return fail("VALIDATION_ERROR", clean_pydantic_message(first["msg"]), field)


@router.get("")
async def list_patients(
    response: Response,
    last_name: str | None = Query(default=None),
    date_of_birth: str | None = Query(default=None),
    phone_number: str | None = Query(default=None),
):
    try:
        patients = await patient_service.list_patients(
            last_name=last_name, date_of_birth=date_of_birth, phone_number=phone_number
        )
    except ValidationError as e:
        response.status_code = 422
        return fail("VALIDATION_ERROR", e.message, e.field)
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
    except PydanticValidationError as e:
        response.status_code = 422
        return _pydantic_error(e)
    except ValidationError as e:
        response.status_code = 422
        return fail("VALIDATION_ERROR", e.message, e.field)

    try:
        patient = await patient_service.create_patient(payload, allow_duplicate=allow_duplicate)
    except DuplicatePatientError as e:
        response.status_code = 409
        result = fail(
            "DUPLICATE_PATIENT",
            f"A patient with this phone number already exists: "
            f"{e.existing.first_name} {e.existing.last_name}",
        )
        result["data"] = {"existing_patient": e.existing.model_dump(mode="json")}
        return result

    logger.info(
        "patient created patient_id=%s phone=%s", patient.patient_id, patient.phone_number
    )
    return ok(patient.model_dump(mode="json"))


@router.put("/{patient_id}")
async def update_patient(patient_id: str, request: Request, response: Response):
    body = await request.json()
    try:
        payload = PatientUpdate(**body)
    except PydanticValidationError as e:
        response.status_code = 422
        return _pydantic_error(e)
    except ValidationError as e:
        response.status_code = 422
        return fail("VALIDATION_ERROR", e.message, e.field)

    try:
        patient = await patient_service.update_patient(patient_id, payload)
    except PatientNotFoundError:
        response.status_code = 404
        return fail("NOT_FOUND", "No patient with that id")

    logger.info("patient updated patient_id=%s", patient_id)
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
