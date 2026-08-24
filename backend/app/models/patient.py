"""
Pydantic schemas for the patient data model, per the assessment's required
field list. Validation rules (name format, phone normalization, state/zip
format, DOB not in the future) live in app/utils/validators.py and are
applied here via field_validator so both PatientCreate (full record) and
PatientUpdate (all-optional, for partial PUTs) enforce identical rules
without repeating the logic twice.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.validators import (
    ValidationError,
    normalize_phone,
    parse_date_of_birth,
    validate_name,
    validate_sex,
    validate_state,
    validate_zip,
)


class PatientBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: Optional[EmailStr] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, v: str) -> str:
        return validate_name("first_name", v)

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, v: str) -> str:
        return validate_name("last_name", v)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, v) -> date:
        return parse_date_of_birth("date_of_birth", v)

    @field_validator("sex")
    @classmethod
    def _sex(cls, v: str) -> str:
        return validate_sex("sex", v)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone("phone_number", v)

    @field_validator("emergency_contact_phone")
    @classmethod
    def _emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return normalize_phone("emergency_contact_phone", v)

    @field_validator("city")
    @classmethod
    def _city(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 100):
            raise ValidationError("city", "must be 1-100 characters")
        return v

    @field_validator("address_line_1")
    @classmethod
    def _address_line_1(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValidationError("address_line_1", "is required")
        return v

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        return validate_state("state", v)

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, v: str) -> str:
        return validate_zip("zip_code", v)


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    """Every field optional - PUT allows partial updates."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, v):
        return None if v is None else validate_name("first_name", v)

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, v):
        return None if v is None else validate_name("last_name", v)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, v):
        return None if v in (None, "") else parse_date_of_birth("date_of_birth", v)

    @field_validator("sex")
    @classmethod
    def _sex(cls, v):
        return None if v is None else validate_sex("sex", v)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v):
        return None if v is None else normalize_phone("phone_number", v)

    @field_validator("emergency_contact_phone")
    @classmethod
    def _emergency_phone(cls, v):
        return None if v in (None, "") else normalize_phone("emergency_contact_phone", v)

    @field_validator("state")
    @classmethod
    def _state(cls, v):
        return None if v is None else validate_state("state", v)

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, v):
        return None if v is None else validate_zip("zip_code", v)

    def to_update_dict(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class PatientOut(PatientBase):
    patient_id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
