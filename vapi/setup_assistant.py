"""
One-shot script to create (or update) the Vapi assistant and provision a
phone number, wiring together OpenRouter (LLM) + ElevenLabs (voice) +
our FastAPI backend (tool webhooks).

This is a convenience script, not the only way to do this - everything it
does can also be clicked through in the Vapi dashboard (Assistants -> Create
Assistant). Vapi's exact request/response shape has shifted across API
versions; if a call here 404s or rejects a field, check https://docs.vapi.ai
and adjust - the assistant JSON body is intentionally kept in one place
(build_assistant_payload) so that's a small, obvious fix.

Usage:
    cd vapi
    pip install httpx python-dotenv
    cp .env.example .env   # fill in the values
    python setup_assistant.py create      # first time
    python setup_assistant.py update <assistant_id>   # after editing the prompt/tools
    python setup_assistant.py phone <assistant_id>    # provision + attach a free number
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from tools import TOOLS  # noqa: E402

load_dotenv(Path(__file__).parent / ".env")

VAPI_API_KEY = os.environ["VAPI_API_KEY"]
BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
VAPI_WEBHOOK_SECRET = os.environ["VAPI_WEBHOOK_SECRET"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
# A second real voice from the same account, used as a fallback if the
# primary voiceId ever fails mid-call (see the fallbackPlan comment below).
ELEVENLABS_FALLBACK_VOICE_ID = os.environ.get(
    "ELEVENLABS_FALLBACK_VOICE_ID", "CwhRBWXzGAHq8TQ4Fs17"
)

BASE = "https://api.vapi.ai"
HEADERS = {"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"}

SYSTEM_PROMPT_FILE = Path(__file__).parent / "system_prompt.md"


def _load_system_prompt() -> str:
    text = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    # Pull just the fenced prompt block out of the markdown doc so the
    # dashboard-configured prompt and the documented one can never drift.
    start = text.index("```\n") + len("```\n")
    end = text.index("\n```", start)
    return text[start:end].strip()


def build_assistant_payload() -> dict:
    return {
        "name": "CareCloud Patient Intake",
        "firstMessage": (
            "Hi! I can get you registered as a new patient — can I grab "
            "your first and last name to start?"
        ),
        "model": {
            # Vapi has a native "openrouter" model provider - it reads the
            # OpenRouter key from a Credential (provider "openrouter") added
            # to the org via POST /credential or the dashboard's Integrations
            # tab, matched automatically by provider name.
            "provider": "openrouter",
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "system", "content": _load_system_prompt()}],
            "tools": TOOLS,
        },
        "voice": {
            "provider": "11labs",
            "voiceId": ELEVENLABS_VOICE_ID,
            # "flash" is ElevenLabs' lowest-latency model - trades a sliver
            # of audio quality for materially faster time-to-first-audio,
            # which matters more for a phone call than for a narration.
            "model": "eleven_flash_v2_5",
            # This is the fix for a real failure seen in testing: an invalid/
            # unavailable voiceId (ElevenLabs occasionally retires a default
            # voice from an account's library) killed the call outright with
            # `pipeline-error-eleven-labs-voice-failed`. A second, different
            # voice from the same account means one bad voice/model
            # combination no longer takes the whole call down with it.
            "fallbackPlan": {
                "voices": [
                    {
                        "provider": "11labs",
                        "voiceId": ELEVENLABS_FALLBACK_VOICE_ID,
                        "model": "eleven_flash_v2_5",
                    }
                ]
            },
        },
        "serverUrl": f"{BACKEND_URL}/vapi/tool-calls",
        "serverUrlSecret": VAPI_WEBHOOK_SECRET,
        "endCallFunctionEnabled": True,
        # Backstop for the "call completion" bug: if the model says goodbye
        # but forgets to invoke the end-call action, Vapi force-ends the call
        # itself as soon as it hears one of these phrases, instead of leaving
        # the caller to hang up manually.
        #
        # CRITICAL: every phrase here is matched as a substring against
        # anything the assistant says, at any point in the call - including
        # the first message. "thanks for calling" used to be in this list
        # AND in the first message, so Vapi force-ended every call the
        # instant it finished the greeting. Only put a phrase here if it
        # could never plausibly appear anywhere except a genuine goodbye -
        # cross-check the firstMessage and every prompt example above
        # before adding one.
        "endCallPhrases": [
            "have a great day",
            "have a wonderful day",
        ],
        "silenceTimeoutSeconds": 20,
        "maxDurationSeconds": 900,
        "analysisPlan": {
            # Vapi's dashboard flags plain-text Summary as deprecated in
            # favor of structured outputs - kept enabled anyway (it's free,
            # still works, and gives call_logs a human-readable fallback)
            # alongside the two structured plans below, which are the
            # forward-looking replacement.
            "summaryPlan": {"enabled": True},
            # Machine-readable extraction stored in the end-of-call-report
            # as message.analysis.structuredData - lets call_logs answer
            # "what actually happened on this call" without parsing prose.
            "structuredDataPlan": {
                "enabled": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "patient_first_name": {"type": "string"},
                        "patient_last_name": {"type": "string"},
                        "caller_intent": {
                            "type": "string",
                            "enum": [
                                "new_registration",
                                "update_existing",
                                "appointment_only",
                                "other",
                            ],
                        },
                        "registration_completed": {"type": "boolean"},
                        "existing_patient_recognized": {"type": "boolean"},
                        "appointment_booked": {"type": "boolean"},
                    },
                },
            },
            # Stored as message.analysis.successEvaluation - a quick pass/
            # fail signal for dashboards/alerting without reading a
            # transcript, distinct from "did the call error" (ended_reason
            # already covers that).
            "successEvaluationPlan": {
                "enabled": True,
                "rubric": "PassFail",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Return true only if the caller's registration or "
                            "update was completed successfully, or they were "
                            "clearly told why not, before the call ended. "
                            "Return false if the call dropped, errored, or "
                            "ended without a resolution."
                        ),
                    }
                ],
            },
        },
    }


def _credential_note():
    print(
        "\nNOTE: this assumes an 'openrouter' credential (your OpenRouter API key) "
        "and an '11labs' credential (your ElevenLabs API key) already exist on this "
        "Vapi org - create them once via:\n"
        '  curl -X POST https://api.vapi.ai/credential -H "Authorization: Bearer $VAPI_API_KEY" '
        '-H "Content-Type: application/json" -d \'{"provider": "openrouter", "apiKey": "..."}\'\n'
        "(same shape for provider 'elevenlabs' / '11labs'). Vapi matches an assistant's "
        "model/voice provider to an org credential automatically - no credentialId "
        "needed on the assistant itself.\n"
    )


def create_assistant():
    payload = build_assistant_payload()
    resp = httpx.post(f"{BASE}/assistant", headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data, indent=2))
    print(f"\nCreated assistant id: {data.get('id')}")
    _credential_note()


def update_assistant(assistant_id: str):
    payload = build_assistant_payload()
    resp = httpx.patch(
        f"{BASE}/assistant/{assistant_id}", headers=HEADERS, json=payload, timeout=30
    )
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2))
    _credential_note()


def provision_phone_number(assistant_id: str):
    # Vapi can hand out a free trial number directly (no Twilio account
    # needed) via provider "vapi". Area code is best-effort.
    payload = {"provider": "vapi", "assistantId": assistant_id}
    area_code = os.environ.get("PHONE_AREA_CODE")
    if area_code:
        payload["numberDesiredAreaCode"] = area_code

    resp = httpx.post(f"{BASE}/phone-number", headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data, indent=2))
    print(f"\nDialable number: {data.get('number')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    if action == "create":
        create_assistant()
    elif action == "update":
        update_assistant(sys.argv[2])
    elif action == "phone":
        provision_phone_number(sys.argv[2])
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
