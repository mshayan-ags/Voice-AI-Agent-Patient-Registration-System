from datetime import date, timedelta

import pytest

from app.utils.validators import (
    ValidationError,
    normalize_phone,
    parse_date_of_birth,
    validate_insurance_member_id,
    validate_name,
    validate_sex,
    validate_state,
    validate_zip,
)


def test_normalize_phone_strips_formatting():
    assert normalize_phone("phone", "(555) 123-4567") == "5551234567"


def test_normalize_phone_strips_leading_country_code():
    assert normalize_phone("phone", "1-555-123-4567") == "5551234567"


def test_normalize_phone_rejects_short_number():
    with pytest.raises(ValidationError):
        normalize_phone("phone", "123")


def test_dob_rejects_future_date():
    future = (date.today() + timedelta(days=1)).strftime("%m/%d/%Y")
    with pytest.raises(ValidationError):
        parse_date_of_birth("dob", future)


def test_dob_accepts_valid_date():
    assert parse_date_of_birth("dob", "01/15/1990") == date(1990, 1, 15)


def test_validate_state_rejects_invalid():
    with pytest.raises(ValidationError):
        validate_state("state", "ZZ")


def test_validate_state_normalizes_case():
    assert validate_state("state", "il") == "IL"


def test_validate_zip_accepts_zip_plus_4():
    assert validate_zip("zip", "62704-1234") == "62704-1234"


def test_validate_zip_rejects_bad_format():
    with pytest.raises(ValidationError):
        validate_zip("zip", "abc")


def test_validate_name_rejects_numbers():
    with pytest.raises(ValidationError):
        validate_name("first_name", "Jane1")


def test_validate_name_allows_hyphen_and_apostrophe():
    assert validate_name("last_name", "O'Brien-Smith") == "O'Brien-Smith"


def test_validate_sex_normalizes_casing():
    assert validate_sex("sex", "female") == "Female"
    assert validate_sex("sex", "decline to answer") == "Decline to Answer"


def test_validate_sex_rejects_invalid():
    with pytest.raises(ValidationError):
        validate_sex("sex", "Unknown")


def test_validate_insurance_member_id_accepts_alphanumeric():
    assert validate_insurance_member_id("insurance_member_id", "BX992134") == "BX992134"


def test_validate_insurance_member_id_rejects_special_chars():
    with pytest.raises(ValidationError):
        validate_insurance_member_id("insurance_member_id", "BX 992134!")
