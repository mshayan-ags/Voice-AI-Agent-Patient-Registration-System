"""
Vapi function-tool definitions for the CareCloud intake assistant.

Each entry becomes one "tool" on the Vapi assistant (type "function"). The
`function.name` here must exactly match the `name` dispatched in
backend/app/api/vapi_tools.py::_run_tool - that's the contract between the
voice agent and our backend.

Kept as plain Python (not committed JSON) so setup_assistant.py can import it
directly without the two ever drifting out of sync.
"""

PATIENT_FIELD_PROPERTIES = {
    "first_name": {"type": "string", "description": "Patient's first name"},
    "last_name": {"type": "string", "description": "Patient's last name"},
    "date_of_birth": {
        "type": "string",
        "description": "Date of birth in MM/DD/YYYY format",
    },
    "sex": {
        "type": "string",
        "enum": ["Male", "Female", "Other", "Decline to Answer"],
        "description": "Patient's sex as one of the four allowed values",
    },
    "phone_number": {
        "type": "string",
        "description": "10-digit U.S. phone number, digits only or with formatting",
    },
    "email": {"type": "string", "description": "Email address (optional)"},
    "address_line_1": {"type": "string", "description": "Street address"},
    "address_line_2": {
        "type": "string",
        "description": "Apartment/suite/unit if applicable (optional)",
    },
    "city": {"type": "string", "description": "City name"},
    "state": {"type": "string", "description": "2-letter U.S. state abbreviation"},
    "zip_code": {"type": "string", "description": "5-digit or ZIP+4 U.S. zip code"},
    "insurance_provider": {
        "type": "string",
        "description": "Name of insurance company (optional)",
    },
    "insurance_member_id": {
        "type": "string",
        "description": "Insurance member/subscriber ID (optional)",
    },
    "preferred_language": {
        "type": "string",
        "description": "Preferred language, defaults to English (optional)",
    },
    "emergency_contact_name": {
        "type": "string",
        "description": "Full name of emergency contact (optional)",
    },
    "emergency_contact_phone": {
        "type": "string",
        "description": "10-digit U.S. phone number for emergency contact (optional)",
    },
}

REQUIRED_PATIENT_FIELDS = [
    "first_name",
    "last_name",
    "date_of_birth",
    "sex",
    "phone_number",
    "address_line_1",
    "city",
    "state",
    "zip_code",
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_existing_patient",
            "description": (
                "Look up whether a patient already exists with the given phone "
                "number. Call this silently as soon as the phone number is "
                "collected - this is a mandatory, blocking step, not optional. "
                "The result includes upcoming_appointments; if non-empty, "
                "mention the appointment to the caller in the same turn you "
                "tell them you found their record, don't wait to be asked."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": PATIENT_FIELD_PROPERTIES["phone_number"],
                },
                "required": ["phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_patient",
            "description": (
                "Create a new patient record. Only call this after the caller "
                "has verbally confirmed the full read-back of their "
                "information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    **PATIENT_FIELD_PROPERTIES,
                    "allow_duplicate": {
                        "type": "boolean",
                        "description": (
                            "Set true only if the caller explicitly confirmed "
                            "this is a separate new patient despite sharing a "
                            "phone number with an existing record."
                        ),
                    },
                },
                "required": REQUIRED_PATIENT_FIELDS,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_patient",
            "description": (
                "Update fields on an existing patient record, identified by "
                "patient_id (from check_existing_patient). Only include the "
                "fields the caller actually wants changed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The existing patient's unique id",
                    },
                    **PATIENT_FIELD_PROPERTIES,
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_appointment_slots",
            "description": (
                "Get a short list of open appointment slots to offer the "
                "caller after a successful registration. Each returned slot "
                "has a slot_id and a human-readable label (e.g. 'Tuesday, "
                "August 26 at 2:00 PM') - always speak the label text "
                "verbatim, never invent your own phrasing for the time."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": (
                "Book the exact slot_id the caller chose (matching the label "
                "you read them from get_available_appointment_slots)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "slot_id": {
                        "type": "string",
                        "description": "The exact slot_id returned by get_available_appointment_slots for the slot the caller chose",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief reason for the visit, if the caller mentioned one",
                    },
                },
                "required": ["patient_id", "slot_id"],
            },
        },
    },
]
