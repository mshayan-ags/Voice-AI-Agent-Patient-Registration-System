import re
from datetime import date, datetime

from pydantic import ValidationError as PydanticValidationError

# Names may include internal spaces ("Mary Jane", "Van Der Berg", "De La
# Cruz") as well as hyphens/apostrophes - must start with a letter so pure
# punctuation/whitespace can't sneak through.
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z' -]{0,49}$")
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

# Full state names -> abbreviation. The plan puts normalization server-side
# so the model never has to format anything - a caller (or a weaker LLM
# under load) is just as likely to send "California" as "CA".
STATE_NAME_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "puerto rico": "PR",
}

VALID_SEX = {"Male", "Female", "Other", "Decline to Answer"}
SEX_ALIASES = {
    "m": "Male", "male": "Male", "man": "Male",
    "f": "Female", "female": "Female", "woman": "Female",
    "o": "Other", "other": "Other", "non-binary": "Other", "nonbinary": "Other",
    "decline": "Decline to Answer", "decline to answer": "Decline to Answer",
    "prefer not to say": "Decline to Answer", "rather not say": "Decline to Answer",
}

_ORDINAL_SUFFIX_RE = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)


class ValidationError(ValueError):
    """`.field`/`.message` are kept as separate attributes so callers can
    format 'field: message' themselves exactly once. The exception's own
    str() is just the plain message (not 'field: message') - when this is
    raised inside a Pydantic field_validator, Pydantic wraps str(exc) as
    the error's `msg` ("Value error, {str(exc)}"); if str(exc) already
    embedded the field name, every downstream caller that also prefixes
    the field ends up doubling it (e.g. "first_name: first_name: must be
    ...", which the voice agent would read aloud verbatim)."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


_PYDANTIC_VALUE_ERROR_PREFIX = "Value error, "


def clean_pydantic_message(msg: str) -> str:
    """Pydantic prefixes any ValueError raised inside a field_validator with
    'Value error, ' - strip it so field-level messages (which already say
    'field: ...') don't read as 'Value error, field: ...' to API clients or
    to the LLM relaying it to a caller."""
    if msg.startswith(_PYDANTIC_VALUE_ERROR_PREFIX):
        msg = msg[len(_PYDANTIC_VALUE_ERROR_PREFIX):]
    return msg


def validate_name(field: str, value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    if not NAME_RE.match(value):
        raise ValidationError(
            field, "must be 1-50 letters (spaces, hyphens, apostrophes allowed)"
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
    # Accept "90210 1234" or "90210" typed with extra whitespace, not just
    # the strict "90210-1234" hyphenated form.
    value = re.sub(r"\s+", "-", value.strip())
    if not ZIP_RE.match(value):
        raise ValidationError(field, "must be a 5-digit or ZIP+4 U.S. zip code")
    return value


def validate_insurance_member_id(field: str, value: str) -> str:
    value = value.strip()
    if not INSURANCE_MEMBER_ID_RE.match(value):
        raise ValidationError(field, "must be an alphanumeric member/subscriber ID")
    return value


def validate_state(field: str, value: str) -> str:
    value = value.strip()
    abbr = STATE_NAME_TO_ABBR.get(value.lower(), value.upper())
    if abbr not in VALID_STATES:
        raise ValidationError(field, "must be a valid U.S. state")
    return abbr


def validate_sex(field: str, value: str) -> str:
    key = (value or "").strip().lower()
    normalized = SEX_ALIASES.get(key)
    if normalized is None:
        raise ValidationError(field, f"must be one of {sorted(VALID_SEX)}")
    return normalized


def parse_date_of_birth(field: str, value: str | date) -> date:
    if isinstance(value, date):
        parsed = value
    else:
        # "March 4th, 1990" -> "March 4 1990": drop ordinal suffixes and
        # commas so both spelled-out and numeric dates parse the same way,
        # instead of requiring the caller (human or LLM) to hit MM/DD/YYYY
        # exactly.
        cleaned = _ORDINAL_SUFFIX_RE.sub(r"\1", value.strip()).replace(",", "")
        cleaned = re.sub(r"\s+", " ", cleaned)
        parsed = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d %Y", "%b %d %Y"):
            try:
                parsed = datetime.strptime(cleaned, fmt).date()
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


def all_field_errors(e: Exception) -> dict[str, str]:
    """Collect every failing field from a validation exception, not just the
    first. Pydantic stops at nothing - it reports all errors at once - but
    call sites were only ever reading errors()[0], turning "6 fields are
    wrong" into 6 slow one-at-a-time re-ask round trips instead of one."""
    if isinstance(e, PydanticValidationError):
        result = {}
        for err in e.errors():
            field = ".".join(str(p) for p in err["loc"])
            result[field] = clean_pydantic_message(err["msg"])
        return result
    if isinstance(e, ValidationError):
        return {e.field: e.message}
    return {"_error": str(e)}
