# CareCloud — Voice AI Patient Registration

A voice AI agent that answers a real phone number, conversationally registers a
new patient (or updates an existing one), and persists the record to MongoDB
through a FastAPI REST service. Built for the Voice AI Agent / Patient
Registration take-home assessment.

**Live demo**
- Phone number: **+1 (234) 404-2250**
- API base URL: **https://carecloud-backend.onrender.com**
- Dashboard: `<fill in once the frontend is deployed - see "Deployment status" below>`

## Screenshots

See [`docs/screenshots/`](docs/screenshots/) — drop images there and they'll
render below:

```
![Vapi call logs](docs/screenshots/vapi-call-logs.png)
![Dashboard - patients](docs/screenshots/dashboard-patients.png)
![Dashboard - call logs](docs/screenshots/dashboard-calls.png)
```

## Example call (real, from testing)

This is an actual transcript from a test call against the deployed number,
lightly trimmed, showing corrections, invalid-input re-prompts, duplicate
detection, an update flow, and appointment booking in one session:

```
AI:   Hi! Thanks for calling — I can get you registered as a new patient.
      Can I grab your first and last name to start?
User: My first name is Muhammad, my last name is Shayan.
AI:   Perfect, Muhammad Shayan. Can I get your date of birth, please?
User: Ninth August, twenty twenty-eight... [garbled] ...two thousand four.
AI:   That date doesn't look quite right. Could you give me your date of
      birth again? Month, day, and year, please.
User: [corrects] August ninth two thousand four.
AI:   Just to confirm, is your date of birth August ninth two thousand four?
User: Yes.
AI:   Got it. What's your sex?
User: Male.
AI:   Can I have your phone number next?
User: One two three four five six... [incomplete]
AI:   I want to make sure I get your number right. Could you repeat all ten
      digits?
User: 222 333 1456
AI:   [duplicate check fires here] It looks like we already have a record
      for Muhammad Shayan with this number. Would you like to update your
      information instead of starting a new registration?
User: Yes, I'd like to update.
AI:   Great, what would you like to update?
User: My address.
AI:   [collects, reads back, confirms] ...You're all set, Mohammed. Your
      address has been updated. Thanks for calling, and have a great day.
User: Do I have any appointment?
AI:   I don't have access to your appointment details, but I can help you
      schedule one — would you like me to check available slots?
User: Yes.
AI:   I have slots on August 25th at 9am, 11am, or 2pm — which works?
User: The 2pm one.
AI:   You're all set. I've scheduled your appointment for August 25th at
      2pm. Thanks for calling, and have a great day.
```

**What this run surfaced and how it was fixed** (kept here rather than
polished away, since the trade-offs are part of the deliverable):
- The duplicate check happened correctly, but only after every field had
  already been collected, not right after the phone number — the original
  prompt said to check "silently," which the model treated as optional
  timing rather than a hard sequencing rule. Fixed by (a) moving phone
  number to the second question asked, right after the name, and (b)
  rewriting the instruction as an explicit blocking step: "the moment you
  have a 10-digit phone number, this is a hard rule, not a suggestion."
- The call ended with the agent saying goodbye, but Vapi reported
  `endedReason: customer-ended-call` — the human had to hang up manually.
  Fixed two ways at once: the prompt now explicitly says "immediately end
  the call" after the goodbye line, and `endCallPhrases` was added to the
  assistant config as a backstop so Vapi force-ends the call the moment it
  hears a goodbye-shaped phrase, independent of whether the model remembers
  to invoke the end-call action.
- "What's your six?" — Deepgram occasionally mishears "sex" as "six" on this
  particular voice/accent combination. Left as-is rather than "fixed": the
  model correctly recovered by asking for male/female/other/decline instead
  of failing on the field, which is the actual point of the exercise (a
  human intake coordinator would have the same problem and the same
  recovery). STT accuracy itself is Deepgram's, not something a prompt can
  fix.

## Architecture

```
Caller
  │  (PSTN call)
  ▼
Vapi  ───────────────► OpenRouter (LLM: nvidia/nemotron-3-super-120b-a12b:free)
  │  transcriber: Deepgram (Vapi default)
  │  voice: ElevenLabs (eleven_flash_v2_5 primary + a fallback voice)
  │
  │  function/tool calls + end-of-call-report over HTTPS webhook
  ▼
FastAPI backend (Render)  ─────►  MongoDB Atlas
  │  (app/api, app/services, app/db)         (patients, call_logs,
  │                                            call_sessions, appointments)
  ▼
REST API (/patients, /appointments, /call-logs)
  ▲
  │  fetch()
Next.js dashboard (bonus) — patients + stats, appointments, call logs,
                            patient detail with call/appointment history
```

Layers are kept deliberately separate:
- **Telephony/voice** (Vapi config, `vapi/`) knows nothing about MongoDB or
  HTTP status codes - it only knows the conversation and which tool to call.
- **API layer** (`backend/app/api/`) handles HTTP concerns: status codes,
  request parsing, the `{data, error}` envelope.
- **Service layer** (`backend/app/services/`) holds the actual business logic
  (duplicate detection, soft delete, partial updates, appointment slots) so
  it's identical whether invoked from a REST call or a Vapi tool call.
- **Data layer** (`backend/app/db/`, `app/models/`) owns the Mongo schema and
  Pydantic validation.

## Tech stack & why

| Layer | Choice | Why |
|---|---|---|
| Telephony + orchestration | **Vapi** | Provisions a real number and handles STT + call orchestration + function-calling out of the box. |
| LLM | **OpenRouter** | One API key, model-agnostic. Reached through Vapi's native `openrouter` model provider (a Vapi Credential holds the key; the assistant just names a model). Pinned to `nvidia/nemotron-3-super-120b-a12b:free` - verified against a real tool-calling prompt before committing to it (see "Known limitations" for the trade-off). |
| Voice | **ElevenLabs** | Natural-sounding TTS; `eleven_flash_v2_5` specifically for lower per-turn latency, plus a second voice configured as `fallbackPlan` so one bad voice/model combination can't take the whole call down (see "Known limitations"). |
| Backend | **FastAPI (Python)** | Async, first-class Pydantic validation reused for both API input and Vapi tool-argument validation. |
| Database | **MongoDB Atlas (free M0)** | Document model suits the mostly-optional-field patient schema well. Motor gives async access from FastAPI. |
| Backend hosting | **Render (free tier)** | Deployed straight from GitHub via Render's API; free and persistent (cold-starts after idle, see "Known limitations"). |
| Frontend (bonus) | **Next.js** | Small App Router dashboard reading directly from the REST API. |

## Repository layout

```
backend/    FastAPI service - API, service layer, Mongo access, tests
vapi/       Assistant system prompt, tool schemas, and a setup script
frontend/   Next.js dashboard (bonus): patient list, detail, call logs
docs/       Screenshots referenced from this README
```

## Setup

### 1. MongoDB
Create a free M0 cluster on MongoDB Atlas, add a database user, allow network
access from anywhere (0.0.0.0/0 is fine for this assessment), and grab the
connection string from **Connect → Drivers**.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env            # fill in MONGODB_URI and VAPI_WEBHOOK_SECRET
uvicorn app.main:app --port 8000
```

Optional seed data:
```bash
python -m scripts.seed_data
```

Run tests (35 tests, uses an in-memory mock Mongo - no real cluster needed):
```bash
pytest -q
```

Expose it publicly for Vapi's webhook during development:
```bash
ngrok http 8000
```

**Permanent deployment (Render, free tier):** push the repo to GitHub, then
either connect it in the Render dashboard (New → Web Service → pick the
repo, root directory `backend`, build command `pip install -r
requirements.txt`, start command `uvicorn app.main:app --host 0.0.0.0 --port
$PORT`, plan Free) or create it via the API:
```bash
curl -X POST https://api.render.com/v1/services -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" -d '{
    "type": "web_service", "name": "carecloud-backend", "ownerId": "<your owner id>",
    "repo": "https://github.com/<you>/<repo>", "branch": "main", "autoDeploy": "yes",
    "rootDir": "backend",
    "serviceDetails": {"env": "python", "region": "oregon", "plan": "free",
      "envSpecificDetails": {"buildCommand": "pip install -r requirements.txt",
        "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT"}}
  }'
```
Then set `MONGODB_URI`, `MONGODB_DB_NAME`, `VAPI_WEBHOOK_SECRET`,
`CORS_ORIGINS` as env vars on the service (dashboard, or `PUT
/v1/services/:id/env-vars`), and add `PYTHON_VERSION=3.12.7` - Render's
default Python (3.14 at time of writing) has no prebuilt wheel yet for one
of this project's dependencies (`pydantic-core`), which fails the build
trying to compile it from source in a read-only sandbox. Pinning a version
with an available wheel is the fix (see "Known limitations").

### 3. Vapi assistant

1. Create accounts: [vapi.ai](https://vapi.ai), [openrouter.ai](https://openrouter.ai/keys),
   [elevenlabs.io](https://elevenlabs.io) (all free to start).
2. Add your OpenRouter and ElevenLabs keys as Vapi **Credentials** (one-time,
   via the dashboard's Integrations tab, or the API):
   ```bash
   curl -X POST https://api.vapi.ai/credential -H "Authorization: Bearer $VAPI_API_KEY" \
     -H "Content-Type: application/json" -d '{"provider": "openrouter", "apiKey": "..."}'
   curl -X POST https://api.vapi.ai/credential -H "Authorization: Bearer $VAPI_API_KEY" \
     -H "Content-Type: application/json" -d '{"provider": "11labs", "apiKey": "..."}'
   ```
   Vapi matches an assistant's `model`/`voice` provider name to an org
   credential automatically - no `credentialId` needed on the assistant.
3. **Pick a real voice ID from your own ElevenLabs library** —
   `GET https://api.elevenlabs.io/v1/voices?voice_type=premade` — rather than
   assuming a commonly-referenced default id like the classic "Rachel"
   (`21m00Tcm4TlvDq8ikWAM`) is available; ElevenLabs periodically refreshes
   its default catalog and an id that isn't in your account's library fails
   the call with `pipeline-error-eleven-labs-voice-failed` (this happened
   during development - see "Known limitations" below).
4. `cd vapi && pip install -r requirements.txt && cp .env.example .env`
5. Fill in `.env`: `VAPI_API_KEY`, `BACKEND_URL` (your ngrok or Render URL),
   `VAPI_WEBHOOK_SECRET` (must match `backend/.env`), `OPENROUTER_API_KEY`,
   `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` + `ELEVENLABS_FALLBACK_VOICE_ID`
   (from step 3 - pick two different voices).
6. `python setup_assistant.py create` → creates the assistant, prints its id.
7. Get a phone number:
   ```bash
   python setup_assistant.py phone <assistant_id>
   ```
   **Note:** Vapi requires a card on file before it will allocate *any*
   phone number, including the nominally "free" one - this surfaced during
   development (see "Known limitations"). Adding a card is a billing action
   only the account owner can take; if the API call rejects for that reason,
   add a payment method in the Vapi dashboard first (usage still draws from
   free trial credit) or create the number by hand in
   **Phone Numbers → Create** and attach it with:
   ```bash
   curl -X PATCH https://api.vapi.ai/phone-number/<number_id> \
     -H "Authorization: Bearer $VAPI_API_KEY" -H "Content-Type: application/json" \
     -d '{"assistantId": "<assistant_id>"}'
   ```
8. Call the number, or use the dashboard's "Talk to Assistant" button to test
   over your browser with zero telephony cost first.

If the Vapi API rejects a field (their schema shifts between API versions),
the equivalent fields can be set by hand in the Vapi dashboard - the system
prompt lives in `vapi/system_prompt.md` and the tool definitions in
`vapi/tools.py` either way, so the dashboard and the repo stay the source of
truth together (`setup_assistant.py update <id>` re-syncs them any time the
prompt or tools change).

### 4. Dashboard (bonus)

```bash
cd frontend
npm install
cp .env.local.example .env.local   # point at the backend URL
npm run dev
```

Visit `/` for the patient list + live stats, `/patients/:id` for full detail
plus that patient's appointments and call history, `/appointments` for every
booked appointment, or `/calls` for every logged call including ones that
never reached a patient record.

## Environment variables

| File | Variable | Required | Purpose |
|---|---|---|---|
| `backend/.env` | `MONGODB_URI` | yes | Atlas connection string |
| | `MONGODB_DB_NAME` | no (default `carecloud`) | database name |
| | `VAPI_WEBHOOK_SECRET` | yes | shared secret Vapi must send back so random internet traffic can't POST fake patients |
| | `CORS_ORIGINS` | no | comma-separated origins allowed to call the API from a browser |
| `vapi/.env` | `VAPI_API_KEY` | yes | Vapi private API key |
| | `BACKEND_URL` | yes | public HTTPS URL of the FastAPI backend |
| | `OPENROUTER_API_KEY` | yes | OpenRouter key (also registered as a Vapi Credential, see setup step 2) |
| | `OPENROUTER_MODEL` | no | model id, must support tool/function calling (default: a verified free-tier model, see "Tech stack") |
| | `ELEVENLABS_API_KEY` | yes | ElevenLabs key (also registered as a Vapi Credential) |
| | `ELEVENLABS_VOICE_ID` | no | must be a voice actually present in your ElevenLabs account - see setup step 3 |
| | `ELEVENLABS_FALLBACK_VOICE_ID` | no | a second real voice id, used only if the primary fails mid-call |
| `frontend/.env.local` | `NEXT_PUBLIC_API_BASE_URL` | yes | backend base URL |

No API key is ever hardcoded in source - everything above is read from
environment variables, and `.env` files are gitignored.

## API reference

All responses use the envelope `{"data": ..., "error": null}` (or
`{"data": null, "error": {"code", "message", "field"}}`).

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/patients?last_name=&date_of_birth=&phone_number=` | list, excludes soft-deleted |
| GET | `/patients/{id}` | 404 if missing or soft-deleted |
| POST | `/patients` | 201 on success, 409 on duplicate phone number, 422 on invalid input |
| PUT | `/patients/{id}` | partial update |
| DELETE | `/patients/{id}` | soft delete (`deleted_at` set, never hard-deleted) |
| GET | `/appointments/slots` | bonus - mock open slots, each with a human-readable `label` |
| GET | `/appointments?patient_id=` | bonus - every booked appointment (with patient name joined in), `patient_id` optional |
| POST | `/appointments` | bonus - book a mock slot |
| GET | `/call-logs?patient_id=` | bonus - transcript/summary/structured_data/success_evaluation/ended_reason for every call, `patient_id` optional |
| POST | `/vapi/tool-calls` | webhook Vapi calls mid-call and at end-of-call; requires `x-vapi-secret` header |

## How the voice agent persists data

Vapi's assistant is given five function tools (`vapi/tools.py`):
`check_existing_patient`, `create_patient`, `update_patient`,
`get_available_appointment_slots`, `book_appointment`. Vapi calls our webhook
(`POST /vapi/tool-calls`) mid-conversation whenever the model decides to
invoke one; the handler runs the exact same service-layer functions the REST
API uses, so validation and duplicate-detection logic is never duplicated.

`check_existing_patient` also returns any upcoming appointment for that
patient, so a returning caller is told about it proactively in the same turn
they're recognized, not only if they think to ask.

When the call ends, Vapi's `end-of-call-report` webhook delivers a
transcript, a plain-text summary, a structured-data extraction (patient
name, caller intent, whether registration/appointment succeeded), and a
pass/fail success evaluation - all three configured via `analysisPlan` and
all stored in `call_logs` along with `ended_reason`, linked back to
whichever patient was created or updated during that call (tracked via a
`call_sessions` collection keyed by Vapi's call id). Calls that never reach
a patient - a hangup mid-intake, a pipeline failure - are still logged, with
`patient_id: null` and whatever `ended_reason` Vapi reports, so a failed call
is visible in the dashboard's `/calls` page rather than silently dropped.

## Bonuses implemented

- **Duplicate detection** - `check_existing_patient` runs immediately after
  the phone number is collected (a hard rule in the prompt, not a
  suggestion); the flow branches into an update path and proactively
  surfaces any upcoming appointment in the same turn.
- **Appointment scheduling** - mock slots with stable, LLM-safe
  `{slot_id, label}` pairs (`appointment_service.py`); `book_appointment`
  rejects an unrecognized `slot_id` explicitly instead of silently
  substituting a different time.
- **Call transcript storage** - every `end-of-call-report` (transcript,
  summary, structured data, success/fail evaluation) is stored in
  `call_logs`, including calls that failed before reaching a patient.
- **Dashboard** - Next.js app: patient list with search and live stats,
  patient detail with appointment + call history, a global appointments
  view (`/appointments`), and a global call-logs view (`/calls`) showing
  success/fail badges and extracted call data.
- **Automated tests** - `backend/tests/` (37 tests: validators, the full API
  surface including duplicate-detection and soft-delete, appointment
  booking/lookup/listing, and the Vapi webhook path itself), run against an
  in-memory mock Mongo.
- Multi-language support was explicitly scoped out for this build, per the
  project owner's instruction.

## Security

- No secret (Mongo URI, Vapi/OpenRouter/ElevenLabs keys, webhook secret) is
  hardcoded anywhere in source - all read from environment variables, `.env`
  files are gitignored.
- `POST /vapi/tool-calls` requires an `x-vapi-secret` header matching
  `VAPI_WEBHOOK_SECRET`; requests without it get a `401` before any data is
  touched, so the webhook can't be used by anyone who doesn't have that
  secret to write/read patient data.
- All patient input is validated server-side with Pydantic (name/phone/date/
  state/zip formats, enum values for `sex`) - the voice agent's own
  conversational validation is a UX nicety, not the enforcement point.
- `last_name` search is regex-escaped (`re.escape`) before being used in a
  MongoDB `$regex` query, closing a NoSQL-injection/ReDoS path where a
  caller-supplied query param could otherwise be interpreted as a regex.
- CORS is driven by an explicit allowlist config (`CORS_ORIGINS`), not
  hardcoded `*` in code - the deployed instance is currently set to `*`
  only because the dashboard doesn't have a permanent domain yet either;
  tighten this to the dashboard's real origin once it's deployed.
- Soft delete only (`deleted_at`), per the spec - no endpoint can hard-delete
  a patient record.
- Not HIPAA compliant and not intended to store real patient data, per the
  assessment's own FAQ - there's no encryption-at-rest configuration, access
  logging, or authentication on the REST API itself (open by design for this
  assessment's scope; see "Next steps").

## Observability

- Every backend event of note (patient created/updated/soft-deleted, Vapi
  webhook received, tool-call outcomes) is logged to stdout via a shared
  logger (`app/core/logging.py`).
- Every call Vapi reports - successful, hung up mid-intake, or failed in the
  voice pipeline - gets a `call_logs` row with `ended_reason`, so a bad call
  is diagnosable from the dashboard's `/calls` page or the DB directly, not
  just the successful ones.

## Known limitations / trade-offs

- **"Free" telephony still has real limits, even after switching to a $0
  LLM.** Vapi itself bills call minutes against a starter credit balance
  (roughly $0.10-0.15/min at these settings) and ElevenLabs' free tier caps
  at 10,000 characters/month - neither is avoidable without leaving Vapi/
  ElevenLabs entirely. The LLM portion, however, is genuinely $0:
  `nvidia/nemotron-3-super-120b-a12b:free` on OpenRouter. It was picked
  over other free options after actually testing tool-calling against three
  candidates - `z-ai/glm-5.2:free` and `google/gemma-4-31b-it:free` both hit
  `429`s from a congested shared free-tier pool on the exact same request
  that nemotron handled correctly. **That congestion is itself a real risk**
  for a live demo: a free model's shared pool can be temporarily unavailable
  at the exact moment someone calls in. `OPENROUTER_MODEL` in `vapi/.env` is
  a one-line swap back to a cheap paid model (e.g. `openai/gpt-4o-mini`,
  which cost $0.02 total across 66 requests in testing) if reliability ever
  matters more than the last fraction of a cent.
- **Vapi requires a card on file to allocate any phone number**, even a
  trial one - this blocked automated provisioning via `setup_assistant.py
  phone` during development. Worked around by creating the number by hand
  in the Vapi dashboard and attaching it to the assistant via a `PATCH
  /phone-number/:id` call instead (documented in Setup step 7).
- **ElevenLabs voice IDs aren't universally stable.** The commonly-referenced
  default id for the "Rachel" voice wasn't present in this account's voice
  library, which failed every call with
  `pipeline-error-eleven-labs-voice-failed` until diagnosed via
  `GET /v1/voices` and swapped for a voice id actually in the account. A
  second, different voice is now configured as `voice.fallbackPlan` so a
  similar failure mid-call falls back instead of ending the call - though
  since both the primary and fallback are ElevenLabs, a full ElevenLabs
  outage (rather than a single bad voice/model combination) would still
  take the call down; a true cross-provider fallback would need a second
  TTS vendor's API key, which wasn't in scope here.
- **STT isn't perfect**, and no prompt can fix that - Deepgram occasionally
  mishears a word ("sex" as "six" was observed in testing). The system
  is designed to recover conversationally (re-ask, don't fail silently)
  rather than to eliminate transcription errors, which aren't ours to fix.
- **~2.5s round-trip latency per turn** (STT ~0.4s + LLM ~1s + TTS ~1.2s per
  the Vapi dashboard's own breakdown at time of testing) is on the slower
  side of "natural." `eleven_flash_v2_5` was chosen specifically to shave
  voice latency; a further optimization not done here would be trimming the
  system prompt token count, which directly affects LLM time-to-first-token.
- **No retry/backoff or idempotency key on the Mongo write inside the
  tool-call handler** beyond what the prompt asks the agent to do
  conversationally (apologize, retry once). A production system would add
  an idempotency key so a Vapi-side retry of the same tool call can't
  double-insert a patient.
- **Render's free tier cold-starts.** The first tool call after ~15 minutes
  of idle can see a multi-second delay while the instance spins back up -
  the caller would experience this as a longer-than-usual pause on the
  first "one sec" of a call after a quiet period.
- **Render defaulted to a too-new Python (3.14) with no prebuilt wheel yet
  for `pydantic-core`**, which made the build try to compile it from source
  via Rust/maturin - and fail, because Render's build sandbox has a
  read-only Cargo cache directory. Fixed by pinning `PYTHON_VERSION=3.12.7`
  as an env var (documented in Setup step 2's deploy instructions) rather
  than by changing any dependency version.
- Not HIPAA compliant and not intended to store real patient data (per the
  assessment's own FAQ).

## Deployment status

Backend + phone number: **live and permanent** - the FastAPI service runs on
Render (`https://carecloud-backend.onrender.com`), and the Vapi assistant's
webhook points there, not at a local tunnel, so the number keeps working
independent of any one machine staying on. Auto-deploys on every push to
`main`.

Dashboard: not yet deployed to a permanent host - run locally per Setup
step 4 for now (`npm run dev`, pointed at the Render backend URL). Update
this section once deployed.

## Next steps (if continuing past this assessment)

- Deploy the dashboard to a permanent host (Vercel) so it doesn't need a
  local `npm run dev` process to view.
- Idempotency keys on `create_patient` tool calls.
- Real appointment system integration instead of mock slots.
- Structured, per-call transcript search on the dashboard.
- Rate limiting / API auth (currently open, per "no HIPAA" scope note).
- Trim the system prompt for lower LLM time-to-first-token, to shave the
  remaining latency budget further.
