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
    result = resp.json()["results"][0]["result"]
    assert result == {"found": False}


async def test_create_patient_via_webhook_then_duplicate_with_appointment(client, valid_patient_payload):
    create_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", valid_patient_payload, call_id="call-2"),
    )
    result = create_resp.json()["results"][0]["result"]
    assert result["success"] is True
    patient_id = result["patient_id"]

    # book_appointment for that patient so the duplicate-check surfaces it
    slots_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("get_available_appointment_slots", {}),
    )
    slot_id = slots_resp.json()["results"][0]["result"]["slots"][0]["slot_id"]
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
    check_result = check_resp.json()["results"][0]["result"]
    assert check_result["found"] is True
    assert check_result["patient_id"] == patient_id
    assert len(check_result["upcoming_appointments"]) == 1

    # create_patient again with the same phone number should report duplicate + appointment
    dup_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", valid_patient_payload, call_id="call-3"),
    )
    dup_result = dup_resp.json()["results"][0]["result"]
    assert dup_result["success"] is False
    assert dup_result["duplicate"] is True
    assert len(dup_result["upcoming_appointments"]) == 1


async def test_update_patient_via_webhook(client, valid_patient_payload):
    create_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", valid_patient_payload),
    )
    patient_id = create_resp.json()["results"][0]["result"]["patient_id"]

    update_resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("update_patient", {"patient_id": patient_id, "city": "Newtown"}),
    )
    result = update_resp.json()["results"][0]["result"]
    assert result["success"] is True

    get_resp = await client.get(f"/patients/{patient_id}")
    assert get_resp.json()["data"]["city"] == "Newtown"


async def test_create_patient_via_webhook_validation_error(client, valid_patient_payload):
    bad = dict(valid_patient_payload, state="ZZ")
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("create_patient", bad),
    )
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False
    assert "Value error" not in result["error"]  # cleaned message, no pydantic wrapper text
    assert result["error"].startswith("state:")


async def test_book_appointment_invalid_slot_via_webhook(client):
    resp = await client.post(
        "/vapi/tool-calls",
        headers={"x-vapi-secret": SECRET},
        json=_tool_call("book_appointment", {"patient_id": "whoever", "slot_id": "bogus"}),
    )
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False


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
