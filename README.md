# PROOFLOOP

**Don't trust the claim. Inspect the proof.**

PROOFLOOP is an evidence-based Python verification prototype. It connects stated requirements to executable checks and records the actual evidence behind each result.

## MVP goals

- Start with a fixed Python task: a student passes only if every subject mark is at least 40.
- Compare a correct implementation with a deliberately faulty average-only implementation.
- Run controlled, predefined checks including boundary cases.
- Show each requirement, test input, expected result, actual result, and observed status.
- Clearly distinguish `PASS`, `FAIL`, and `UNKNOWN`; a passing test suite is evidence for the checks run, not a proof of universal correctness.
- Add Gnani AI Prisma speech-to-text and Timbre text-to-speech after the core verification flow works.

## Planned stack

- Frontend: React + TypeScript
- Backend: Python + FastAPI
- Test framework: pytest
- Initial evidence storage: JSON

## Security scope

The first version must use fixed sample implementations and controlled fixtures. Do not expose an unrestricted shell or execute arbitrary visitor-supplied Python on a public server. Keep API credentials on the backend in environment variables; never commit secrets.

## Development status

- [x] Repository created
- [x] Initial project brief
- [x] Verification engine and sample task
- [x] Evidence Ledger UI
- [x] Gnani AI voice integration
- [ ] End-to-end validation and demo

## Phase 1 & Phase 2 Setup & Usage

### Repository structure

- `backend/` — FastAPI verification service, predefined grading implementations (`grade_student_correct` and `grade_student_faulty_average`), deterministic verification runner, Gnani AI voice integration (`backend/app/gnani_service.py`), JSON evidence ledger (`backend/app/data/evidence_ledger.json`), and `pytest` test suite.
- `frontend/` — React + TypeScript + Vite Evidence Ledger UI, Gnani voice controls (`frontend/src/VoicePanel.tsx`), and `vitest` test suite.
- `docs/MVP_SCOPE.md` — Phase 1 scope, required behavior, and acceptance criteria.

### 1. Backend setup & tests (Python + FastAPI + pytest)

```bash
# Install Python dependencies
pip install -r backend/requirements.txt

# Run deterministic backend tests (38 tests covering grading, verifier, API security, and mocked Gnani STT/TTS)
pytest -v

# Start the FastAPI backend server on port 8000
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

### 2. Frontend setup & tests (React + TypeScript + Vite)

```bash
cd frontend

# Install Node dependencies
npm install

# Run frontend unit tests and production build
npm test && npm run build

# Start the Vite development server on port 5173 (proxies /api to http://127.0.0.1:8000)
npm run dev
```

## Phase 2: Gnani AI Voice Integration

### What Gnani STT and TTS do in PROOFLOOP

PROOFLOOP integrates **only official Gnani AI Speech APIs** (`https://api.vachana.ai`) as an additional human interface while preserving the deterministic verification engine:

1. **Speech-to-Text (`POST /api/voice/stt` → Gnani Prisma v2.5 `POST https://api.vachana.ai/stt/v3`)**:
   - Transcribes short spoken requirement clips (`WAV`, `MP3`, `OGG`, `FLAC`, `AAC`, `M4A`, up to 5 MB) into an editable text field.
   - Requires explicit operator review and confirmation (**Confirm Transcript for Review**) before use.
2. **Text-to-Speech (`POST /api/voice/tts` → Gnani Timbre v2.5/v3.0 `POST https://api.vachana.ai/api/v1/tts/inference`)**:
   - Generates a concise spoken summary directly from the actual backend verification report (`PASS`, `FAIL`, or `UNKNOWN`) when the user clicks **Read Result Aloud**, returning `audio/wav` for manual playback without autoplay.
   - Never alters the underlying verification status or replaces the visual Evidence Ledger.

### Configuring Gnani Credentials (Server-Side Only)

Set the official Gnani API key in the backend environment before starting FastAPI. Never commit `.env` files or expose credentials to browser JavaScript:

```bash
# Required for live Gnani STT and TTS API calls (sent as header X-API-Key-ID)
export GNANI_API_KEY="your_gnani_api_key_placeholder"

# Optional overrides (defaults shown)
export GNANI_BASE_URL="https://api.vachana.ai"
export GNANI_TIMEOUT_SECONDS="15.0"
```

### Features Requiring a Configured Gnani Account vs. Offline / Unconfigured Mode

- **Requires `GNANI_API_KEY`**: Live microphone transcription (**Speak Requirement**), audio clip upload transcription, and live spoken summary synthesis (**Read Result Aloud**).
- **Works without `GNANI_API_KEY`**: When `GNANI_API_KEY` is unset, `GET /api/voice/status` reports `configured: false` and the UI disables live STT/TTS calls with a clear configuration notice. Users can still type, edit, and confirm requirement text manually, run all deterministic verification scenarios (`PASS`, `FAIL`, `UNKNOWN`), and inspect the full Evidence Ledger.
- **Testing without real credentials**: Both `pytest -v` (backend) and `cd frontend && npm test` (frontend) use mocked HTTP transports (`httpx.MockTransport`) and mocked API responses, requiring no live Gnani credentials or network access.

### Audio Handling & Privacy Behavior

- Uploaded audio clips are validated for non-empty size (`<= 5 MB`) and accepted media types/extensions (`wav`, `mp3`, `ogg`, `flac`, `aac`, `m4a`) before being forwarded to Gnani AI.
- Audio recordings, synthesized speech buffers, and transcripts are processed strictly in memory and are never written to disk or application logs.
- Server error handlers redact `GNANI_API_KEY` so credentials are never leaked in error responses.

### Known Limitations & Operational Notes

- **Simulated Timeout Handling**: Timeout behavior (`simulated_timeout_test_ids` in `backend/app/verifier.py`) is currently a deterministic simulation used to verify that timed-out checks propagate as `UNKNOWN` rather than `PASS`; it does not enforce a real wall-clock or subprocess execution timeout. (Separately, outbound HTTP requests to Gnani AI apply a bounded client timeout via `GNANI_TIMEOUT_SECONDS`.)
- **Single Slot for Custom Runs (`custom_run`)**: Executing a custom verification run via `POST /api/verify` stores its report under the `custom_run` key in the ledger, overwriting any previous `custom_run` entry.
- **Local JSON File Persistence**: Verification runs are persisted to `backend/app/data/evidence_ledger.json` on the local filesystem. This persistence mechanism must be reviewed before deploying to an ephemeral or read-only host (where disk writes may fail or reset across restarts).
- **No Dynamic Test Generation from Spoken Requirements**: Phase 2 verifies only the fixed predefined Python student-grading implementations (`grade_student_correct` and `grade_student_faulty_average`) and fixed test fixtures (`TC-01`..`TC-08`). Spoken transcripts are for human review and context only and never dynamically generate test suites or execute arbitrary code.

## Project repository

https://github.com/esakki-2008/proofloop
