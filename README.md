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
- [ ] Verification engine and sample task
- [ ] Evidence Ledger UI
- [ ] Gnani AI voice integration
- [ ] End-to-end validation and demo

## Project repository

https://github.com/esakki-2008/proofloop
