# PROOFLOOP MVP Scope

## First end-to-end scenario

Requirement: A student passes only when every subject mark is at least 40.

Examples:
- [40, 50, 60] -> pass
- [39, 80, 90] -> fail
- [40, 40, 40] -> pass
- [39, 39, 39] -> fail

Fault to expose: a function that checks only the average can incorrectly pass a student whose mark is below 40 in one subject.

## Required behavior

1. Use predefined sample implementations and fixed test cases in the initial version.
2. Execute tests and capture actual returned values or exceptions.
3. For every check, store the requirement ID, test ID, input, expected output, actual output, and observed result.
4. Mark a requirement PASS only when its required checks have run and passed.
5. Mark a requirement FAIL if any required check fails.
6. Mark a requirement UNKNOWN if checks could not run or coverage is incomplete.
7. Do not describe passing selected tests as proof of universal correctness.
8. Keep explanations separate from execution evidence.

## Acceptance criteria

- The correct implementation passes every defined test.
- The average-only implementation fails a test where one score is below 40 while the average remains above 40.
- Boundary tests cover 39 and 40.
- Tests run deterministically without an external AI API.
- Missing, timed-out, or unexecuted checks never appear as passing.
- No unrestricted shell or public arbitrary-code execution endpoint is exposed.

## Deferred

- Autonomous code generation and repository editing
- Arbitrary code execution from public users
- Multi-agent architecture
- Mobile client
- Nonessential database
- Gnani voice integration until the core test flow is reliable
