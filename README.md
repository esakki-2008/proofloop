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
- [ ] Gnani AI voice integration
- [ ] End-to-end validation and demo

## Phase 1 Setup & Usage

### Repository structure

- `backend/` — FastAPI verification service, predefined grading implementations (`grade_student_correct` and `grade_student_faulty_average`), deterministic verification runner, JSON evidence ledger (`backend/app/data/evidence_ledger.json`), and `pytest` test suite.
- `frontend/` — React + TypeScript + Vite Evidence Ledger UI and `vitest` test suite.
- `docs/MVP_SCOPE.md` — Phase 1 scope, required behavior, and acceptance criteria.

### 1. Backend setup & tests (Python + FastAPI + pytest)

```bash
# Install Python dependencies
pip install -r backend/requirements.txt

# Run deterministic backend tests (25 tests covering grading, verifier, and API security)
pytest -v

# Start the FastAPI backend server on port 8000
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

### 2. Frontend setup & tests (React + TypeScript + Vite)

```bash
cd frontend

# Install Node dependencies
npm install

# Run frontend unit tests
npm test

# Start the Vite development server on port 5173 (proxies /api to http://127.0.0.1:8000)
npm run dev
```

### Phase 1 Known Limitations & Operational Notes

- **Simulated Timeout Handling**: Timeout behavior (`simulated_timeout_test_ids` in `backend/app/verifier.py`) is currently a deterministic simulation used to verify that timed-out checks propagate as `UNKNOWN` rather than `PASS`; it does not enforce a real wall-clock or subprocess execution timeout.
- **Single Slot for Custom Runs (`custom_run`)**: Executing a custom verification run via `POST /api/verify` stores its report under the `custom_run` key in the ledger, overwriting any previous `custom_run` entry.
- **Local JSON File Persistence**: Verification runs are persisted to `backend/app/data/evidence_ledger.json` on the local filesystem. This persistence mechanism must be reviewed before deploying to an ephemeral or read-only host (where disk writes may fail or reset across restarts).
- **Fixed Implementations & Deferred Integrations**: Phase 1 evaluates only the predefined Python grading implementations and fixed test fixtures (`TC-01`..`TC-08`). External AI APIs and Gnani AI voice integration remain deferred.

## Project repository

https://github.com/esakki-2008/proofloop
