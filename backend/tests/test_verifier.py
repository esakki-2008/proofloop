"""Tests for the PROOFLOOP verification engine, requirement linking, and tri-state logic."""

from __future__ import annotations

from pathlib import Path

from app.models import VerificationStatus
from app.verifier import (
    REQUIREMENTS_CATALOG,
    TEST_CASES_CATALOG,
    build_default_ledger,
    execute_verification_run,
    load_or_create_ledger,
    save_ledger,
)


def test_correct_implementation_passes_every_defined_test_and_requirement() -> None:
    report = execute_verification_run(implementation_id="correct_all_subjects")

    assert report.overall_status == VerificationStatus.PASS
    assert report.counts.total_checks == len(TEST_CASES_CATALOG) == 8
    assert report.counts.executed_checks == 8
    assert report.counts.passed_checks == 8
    assert report.counts.failed_checks == 0
    assert report.counts.unknown_checks == 0

    for ev in report.evidence:
        assert ev.executed is True
        assert ev.observed_result == VerificationStatus.PASS
        assert ev.requirement_id in {r.requirement_id for r in REQUIREMENTS_CATALOG}

    for req in report.requirements:
        assert req.status == VerificationStatus.PASS
        assert req.failed_test_ids == []
        assert req.unknown_test_ids == []
        assert req.passed_test_ids == req.required_test_ids


def test_faulty_implementation_fails_39_80_90_and_linked_requirements() -> None:
    report = execute_verification_run(implementation_id="faulty_average_only")

    assert report.overall_status == VerificationStatus.FAIL

    by_test_id = {ev.test_id: ev for ev in report.evidence}
    tc02 = by_test_id["TC-02"]
    assert tc02.input == [39, 80, 90]
    assert tc02.requirement_id == "REQ-01"
    assert tc02.expected_return is False
    assert tc02.actual_return is True
    assert tc02.expected_output == "False (FAIL)"
    assert tc02.actual_output == "True (PASS)"
    assert tc02.observed_result == VerificationStatus.FAIL

    req_by_id = {r.requirement_id: r for r in report.requirements}
    assert req_by_id["REQ-01"].status == VerificationStatus.FAIL
    assert "TC-02" in req_by_id["REQ-01"].failed_test_ids
    assert req_by_id["REQ-02"].status == VerificationStatus.FAIL
    assert "TC-05" in req_by_id["REQ-02"].failed_test_ids
    assert req_by_id["REQ-03"].status == VerificationStatus.FAIL
    assert "TC-08" in req_by_id["REQ-03"].failed_test_ids


def test_incomplete_coverage_marks_unexecuted_checks_and_requirements_unknown() -> None:
    """Even if all executed checks pass, missing required checks must yield UNKNOWN, never PASS."""
    report = execute_verification_run(
        implementation_id="faulty_average_only",
        selected_test_ids=["TC-01", "TC-03", "TC-04", "TC-07"],
    )

    assert report.counts.executed_checks == 4
    assert report.counts.passed_checks == 4
    assert report.counts.failed_checks == 0
    assert report.counts.unknown_checks == 4
    assert report.overall_status == VerificationStatus.UNKNOWN

    by_test_id = {ev.test_id: ev for ev in report.evidence}
    assert by_test_id["TC-02"].executed is False
    assert by_test_id["TC-02"].actual_output is None
    assert by_test_id["TC-02"].observed_result == VerificationStatus.UNKNOWN

    for req in report.requirements:
        assert req.status == VerificationStatus.UNKNOWN
        assert len(req.unknown_test_ids) > 0


def test_timed_out_check_never_appears_as_passing() -> None:
    report = execute_verification_run(
        implementation_id="correct_all_subjects",
        simulated_timeout_test_ids=["TC-02"],
    )

    by_test_id = {ev.test_id: ev for ev in report.evidence}
    assert by_test_id["TC-02"].timed_out is True
    assert by_test_id["TC-02"].executed is False
    assert by_test_id["TC-02"].observed_result == VerificationStatus.UNKNOWN

    req_by_id = {r.requirement_id: r for r in report.requirements}
    assert req_by_id["REQ-01"].status == VerificationStatus.UNKNOWN
    assert req_by_id["REQ-02"].status == VerificationStatus.PASS
    assert req_by_id["REQ-03"].status == VerificationStatus.PASS
    assert report.overall_status == VerificationStatus.UNKNOWN


def test_explanations_are_stored_separately_from_execution_evidence(tmp_path: Path) -> None:
    ledger = build_default_ledger(persist=False)
    temp_ledger_path = tmp_path / "evidence_ledger.json"
    save_ledger(ledger, path=temp_ledger_path)

    reloaded = load_or_create_ledger(path=temp_ledger_path)
    correct_run = reloaded.runs["correct_full"]

    assert len(correct_run.evidence) == 8
    assert len(correct_run.explanations) == 8

    evidence_fields = set(correct_run.evidence[0].model_dump().keys())
    assert "design_note" not in evidence_fields
    assert "diagnostic_explanation" not in evidence_fields
    assert {
        "requirement_id",
        "test_id",
        "input",
        "expected_output",
        "actual_output",
        "observed_result",
    }.issubset(evidence_fields)
