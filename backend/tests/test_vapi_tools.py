import json

SECRET = "test-secret"  # matches VAPI_WEBHOOK_SECRET set in conftest.py


def _tool_call(name, arguments, call_id="call-1", tool_call_id="tc-1"):
    return {
        "message": {
            "type": "tool-calls",
            "call": {"id": call_id},
            "toolCalls": [
                {"id": tool_call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
            ],
        }
    }


def _result(resp):
    """Vapi's documented contract is that `result` is a JSON string, not a
    bare object - every test reads through this so a future contract change
    only needs updating in one place."""
    return json.loads(resp.json()["results"][0]["result"])


async def test_webhook_rejects_wrong_secret(client):
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": "wrong"},
        json={"message": {"type": "tool-calls", "toolCalls": []}},
    )
    assert resp.status_code == 401


async def test_check_existing_patient_not_found(client):
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("check_existing_patient", {"phone_number": "5551110000"}),
    )
    assert _result(resp) == {"found": False}


async def test_check_existing_patient_missing_argument_does_not_crash(client):
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("check_existing_patient", {}),
    )
    assert resp.status_code == 200
    result = _result(resp)
    assert result["success"] is False


async def test_update_patient_missing_patient_id_does_not_crash(client):
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("update_patient", {"city": "Venice"}),
    )
    assert resp.status_code == 200
    assert _result(resp)["success"] is False


async def test_book_appointment_missing_slot_id_does_not_crash(client):
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("book_appointment", {"patient_id": "x"}),
    )
    assert resp.status_code == 200
    assert _result(resp)["success"] is False


async def test_arguments_as_json_string_are_parsed(client):
    """Vapi's OpenAI-compatible function-calling shape technically defines
    `arguments` as a JSON string, not a bare object - confirm the string
    form works exactly like the object form."""
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call(
            "check_existing_patient", json.dumps({"phone_number": "5551110000"})
        ),
    )
    assert _result(resp) == {"found": False}


async def test_create_patient_via_webhook_then_duplicate_with_appointment(client, valid_patient_payload):
    create_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", valid_patient_payload, call_id="call-2"),
    )
    result = _result(create_resp)
    assert result["success"] is True
    patient_id = result["patient_id"]

    # book_appointment for that patient so the duplicate-check surfaces it
    slots_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("get_available_appointment_slots", {}),
    )
    slot_id = _result(slots_resp)["slots"][0]["slot_id"]
    await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("book_appointment", {"patient_id": patient_id, "slot_id": slot_id}),
    )

    # check_existing_patient should now surface both the match and the appointment
    check_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call(
            "check_existing_patient", {"phone_number": valid_patient_payload["phone_number"]}
        ),
    )
    check_result = _result(check_resp)
    assert check_result["found"] is True
    assert check_result["patient_id"] == patient_id
    assert len(check_result["upcoming_appointments"]) == 1

    # create_patient again with the same phone number should report duplicate + appointment
    dup_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", valid_patient_payload, call_id="call-3"),
    )
    dup_result = _result(dup_resp)
    assert dup_result["success"] is False
    assert dup_result["duplicate"] is True
    assert len(dup_result["upcoming_appointments"]) == 1


async def test_update_patient_via_webhook(client, valid_patient_payload):
    create_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", valid_patient_payload),
    )
    patient_id = _result(create_resp)["patient_id"]

    update_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("update_patient", {"patient_id": patient_id, "city": "Newtown"}),
    )
    assert _result(update_resp)["success"] is True

    get_resp = await client.get(f"/patients/{patient_id}")
    assert get_resp.json()["data"]["city"] == "Newtown"


async def test_update_patient_rejects_phone_collision(client, valid_patient_payload):
    """The PUT/update_patient path must apply the same duplicate-phone check
    as create - otherwise two active patients can end up sharing a number,
    and find_active_by_phone becomes ambiguous for both of them forever."""
    a = (
        await client.post(
            "/vapi/tool-calls",
            headers={"x-vapi-secret": SECRET},
            json=_tool_call("create_patient", valid_patient_payload, call_id="call-a"),
        )
    )
    patient_a_id = _result(a)["patient_id"]

    b_payload = dict(valid_patient_payload, phone_number="5559998888", last_name="Other")
    b = (
        await client.post(
            "/vapi/tool-calls",
            headers={"x-vapi-secret": SECRET},
            json=_tool_call("create_patient", b_payload, call_id="call-b"),
        )
    )
    patient_b_id = _result(b)["patient_id"]

    # Try to update B's phone number to collide with A's
    update_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call(
            "update_patient",
            {"patient_id": patient_b_id, "phone_number": valid_patient_payload["phone_number"]},
        ),
    )
    result = _result(update_resp)
    assert result["success"] is False
    assert result.get("duplicate") is True
    assert result["existing_patient_id"] == patient_a_id


async def test_create_patient_via_webhook_validation_error(client, valid_patient_payload):
    bad = dict(valid_patient_payload, state="ZZ")
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", bad),
    )
    result = _result(resp)
    assert result["success"] is False
    assert "Value error" not in result["error"]  # cleaned message, no pydantic wrapper text
    assert "state" in result["error"]


async def test_create_patient_via_webhook_reports_all_invalid_fields(client, valid_patient_payload):
    bad = dict(valid_patient_payload, state="ZZ", zip_code="bad", sex="unknown")
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", bad),
    )
    result = _result(resp)
    assert result["success"] is False
    assert set(result["field_errors"].keys()) == {"state", "zip_code", "sex"}


async def test_create_patient_accepts_multi_word_name(client, valid_patient_payload):
    payload = dict(valid_patient_payload, first_name="Mary Jane", last_name="Van Der Berg")
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", payload),
    )
    assert _result(resp)["success"] is True


async def test_book_appointment_invalid_slot_via_webhook(client):
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("book_appointment", {"patient_id": "whoever", "slot_id": "bogus"}),
    )
    assert _result(resp)["success"] is False


async def test_end_of_call_report_is_stored_and_listable(client):
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call-report-1"},
                "transcript": "AI: hi\nUser: hi",
                "summary": "short call",
                "endedReason": "customer-ended-call",
            }
        },
    )
    assert resp.json() == {"received": True}

    logs = (await client.get("/call-logs")).json()["data"]
    matching = [l for l in logs if l["call_id"] == "call-report-1"]
    assert len(matching) == 1
    assert matching[0]["ended_reason"] == "customer-ended-call"
