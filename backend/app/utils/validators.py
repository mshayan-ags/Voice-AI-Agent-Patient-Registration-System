import re
from datetime import date, datetime

NAME_RE = re.compile(r"^[A-Za-z'-]{1,50}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
# Spec: "Alphanumeric member/subscriber ID" - real insurance IDs sometimes
# include a hyphen, so it's allowed alongside letters/digits rather than
# enforcing a stricter alphanumeric-only read of the spec.
INSURANCE_MEMBER_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,30}$")

# USPS 2-letter state/territory abbreviations
VALID_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP",
}

VALID_SEX = {"Male", "Female", "Other", "Decline to Answer"}


class ValidationError(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


_PYDANTIC_VALUE_ERROR_PREFIX = "Value error, "


def clean_pydantic_message(msg: str) -> str:
    """Pydantic prefixes any ValueError raised inside a field_validator with
    'Value error, ' - strip it so field-level messages (which already say
    'field: ...') don't read as 'Value error, field: ...' to API clients or
    to the LLM relaying it to a caller."""
    if msg.startswith(_PYDANTIC_VALUE_ERROR_PREFIX):
        return msg[len(_PYDANTIC_VALUE_ERROR_PREFIX):]
    return msg


def validate_name(field: str, value: str) -> str:
    value = value.strip()
    if not NAME_RE.match(value):
        raise ValidationError(
            field, "must be 1-50 alphabetic characters (hyphens/apostrophes allowed)"
        )
    return value


def normalize_phone(field: str, value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValidationError(field, "must be a valid U.S. 10-digit phone number")
    return digits


def validate_zip(field: str, value: str) -> str:
    value = value.strip()
    if not ZIP_RE.match(value):
        raise ValidationError(field, "must be a 5-digit or ZIP+4 U.S. zip code")
    return value


def validate_insurance_member_id(field: str, value: str) -> str:
    value = value.strip()
    if not INSURANCE_MEMBER_ID_RE.match(value):
        raise ValidationError(field, "must be an alphanumeric member/subscriber ID")
    return value


def validate_state(field: str, value: str) -> str:
    value = value.strip().upper()
    if value not in VALID_STATES:
        raise ValidationError(field, "must be a valid 2-letter U.S. state abbreviation")
    return value


def validate_sex(field: str, value: str) -> str:
    # Accept common casing variants a voice agent might send.
    normalized = value.strip().title() if value else value
    if normalized == "Decline To Answer":
        normalized = "Decline to Answer"
    if normalized not in VALID_SEX:
        raise ValidationError(field, f"must be one of {sorted(VALID_SEX)}")
    return normalized


def parse_date_of_birth(field: str, value: str | date) -> date:
    if isinstance(value, date):
        parsed = value
    else:
        value = value.strip()
        parsed = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValidationError(field, "must be a valid date in MM/DD/YYYY format")

    if parsed > date.today():
        raise ValidationError(field, "cannot be in the future")
    if parsed.year < 1900:
        raise ValidationError(field, "must be a plausible date of birth")
    return parsed
