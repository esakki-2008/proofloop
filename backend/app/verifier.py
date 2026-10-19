"""Deterministic verification engine and JSON evidence ledger manager for PROOFLOOP."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.grading import IMPLEMENTATIONS, PASS_MARK_THRESHOLD
from app.models import (
    CheckEvidenceRecord,
    CheckExplanationRecord,
    EvidenceLedger,
    RequirementEvaluationRecord,
    RequirementSpecModel,
    RunSummaryCounts,
    TestCaseSpecModel,
    VerificationRunReport,
    VerificationStatus,
)

EPISTEMIC_PRINCIPLE: str = (
    "A passing test suite is execution evidence for the specific checks run, "
    "never a proof of universal correctness. Missing, timed-out, or unexecuted "
    "checks are marked UNKNOWN and never assumed to pass."
)

REQUIREMENTS_CATALOG: list[RequirementSpecModel] = [
    RequirementSpecModel(
        requirement_id="REQ-01",
        title="Minimum Per-Subject Threshold (Every Subject >= 40)",
        statement=(
            "A student passes only when every individual subject mark is at least 40. "
            "Any single subject mark below 40 must result in failure (False), even when "
            "the overall arithmetic average across subjects is well above 40."
        ),
        required_test_ids=["TC-01", "TC-02", "TC-06"],
    ),
    RequirementSpecModel(
        requirement_id="REQ-02",
        title="Boundary Precision Around Passing Mark (39 vs 40)",
        statement=(
            "Boundary values at 39 (highest integer failing mark) and 40 (lowest passing mark) "
            "must be evaluated accurately across uniform and mixed subject mark combinations."
        ),
        required_test_ids=["TC-03", "TC-04", "TC-05", "TC-07"],
    ),
    RequirementSpecModel(
        requirement_id="REQ-03",
        title="Empty Marks Input Rejection",
        statement=(
            "An empty marks list ([]) must raise a ValueError rather than vacuously returning "
            "True (all([]) == True) or crashing with an unhandled ZeroDivisionError."
        ),
        required_test_ids=["TC-08"],
    ),
]

TEST_CASES_CATALOG: list[TestCaseSpecModel] = [
    TestCaseSpecModel(
        test_id="TC-01",
        requirement_id="REQ-01",
        name="Standard passing marks above threshold",
        category="Standard",
        input_marks=[40, 50, 60],
        expected_return=True,
        expected_exception=None,
        expected_output_display="True (PASS)",
        design_note="All subject marks are >= 40 (min = 40, average = 50.00). Student should pass.",
    ),
    TestCaseSpecModel(
        test_id="TC-02",
        requirement_id="REQ-01",
        name="High average with single failing subject [39, 80, 90]",
        category="Fault-Exposing",
        input_marks=[39, 80, 90],
        expected_return=False,
        expected_exception=None,
        expected_output_display="False (FAIL)",
        design_note=(
            "Critical counterexample from MVP scope: average is 69.67 (>= 40), "
            "but subject 1 is 39 (< 40). Exposes average-only implementations."
        ),
    ),
    TestCaseSpecModel(
        test_id="TC-03",
        requirement_id="REQ-02",
        name="Exact lower passing boundary across all subjects [40, 40, 40]",
        category="Boundary",
        input_marks=[40, 40, 40],
        expected_return=True,
        expected_exception=None,
        expected_output_display="True (PASS)",
        design_note="Every subject mark sits on the exact passing boundary of 40 (min = 40, average = 40.00).",
    ),
    TestCaseSpecModel(
        test_id="TC-04",
        requirement_id="REQ-02",
        name="Just below passing boundary across all subjects [39, 39, 39]",
        category="Boundary",
        input_marks=[39, 39, 39],
        expected_return=False,
        expected_exception=None,
        expected_output_display="False (FAIL)",
        design_note="Every subject mark is 39, one point below the passing threshold (min = 39, average = 39.00).",
    ),
    TestCaseSpecModel(
        test_id="TC-05",
        requirement_id="REQ-02",
        name="Boundary straddle with exact 40.0 average [39, 40, 41]",
        category="Boundary / Fault-Exposing",
        input_marks=[39, 40, 41],
        expected_return=False,
        expected_exception=None,
        expected_output_display="False (FAIL)",
        design_note=(
            "Tests boundary values 39 and 40 simultaneously while keeping the arithmetic "
            "average at exactly 40.00. Subject 1 (39) must cause a failure."
        ),
    ),
    TestCaseSpecModel(
        test_id="TC-06",
        requirement_id="REQ-01",
        name="Trailing subject failure with high overall average [95, 88, 39]",
        category="Fault-Exposing",
        input_marks=[95, 88, 39],
        expected_return=False,
        expected_exception=None,
        expected_output_display="False (FAIL)",
        design_note=(
            "Ensures all positions in the marks list are checked. Average is 74.00 (>= 40), "
            "but the final subject mark is 39 (< 40)."
        ),
    ),
    TestCaseSpecModel(
        test_id="TC-07",
        requirement_id="REQ-02",
        name="Single subject at exact threshold with high peers [40, 100, 100]",
        category="Boundary",
        input_marks=[40, 100, 100],
        expected_return=True,
        expected_exception=None,
        expected_output_display="True (PASS)",
        design_note="Verifies that a mark of exactly 40 is treated as inclusive (>= 40, not > 40).",
    ),
    TestCaseSpecModel(
        test_id="TC-08",
        requirement_id="REQ-03",
        name="Empty subject marks list []",
        category="Validation",
        input_marks=[],
        expected_return=None,
        expected_exception="ValueError",
        expected_output_display="Exception: ValueError",
        design_note=(
            "Guards against Python's vacuous truth (`all([]) == True`) and unhandled "
            "`ZeroDivisionError` when computing an average on empty input."
        ),
    ),
]

REQUIREMENTS_BY_ID: dict[str, RequirementSpecModel] = {
    req.requirement_id: req for req in REQUIREMENTS_CATALOG
}
TEST_CASES_BY_ID: dict[str, TestCaseSpecModel] = {
    tc.test_id: tc for tc in TEST_CASES_CATALOG
}

LEDGER_FILE_PATH: Path = Path(__file__).resolve().parent / "data" / "evidence_ledger.json"


def format_return_value(value: bool) -> str:
    """Format boolean grading return value with explicit student pass/fail meaning."""
    return "True (PASS)" if value is True else "False (FAIL)"


def format_input_metrics(marks: list[float]) -> str:
    """Compute factual summary metrics for an input marks list."""
    if not marks:
        return "count=0 (empty list)"
    minimum = min(marks)
    maximum = max(marks)
    average = sum(marks) / len(marks)
    below_threshold = [m for m in marks if m < PASS_MARK_THRESHOLD]
    return (
        f"count={len(marks)}, min={minimum}, max={maximum}, "
        f"avg={average:.2f}, marks_below_40={below_threshold}"
    )


def evaluate_requirement_status(
    requirement: RequirementSpecModel,
    evidence_by_test_id: dict[str, CheckEvidenceRecord],
) -> RequirementEvaluationRecord:
    """Evaluate a requirement's status strictly from its linked check execution evidence.

    Rules from docs/MVP_SCOPE.md:
    - Mark a requirement PASS only when its required checks have run and passed.
    - Mark a requirement FAIL if any required check fails.
    - Mark a requirement UNKNOWN if checks could not run or coverage is incomplete.
    """
    executed_ids: list[str] = []
    passed_ids: list[str] = []
    failed_ids: list[str] = []
    unknown_ids: list[str] = []

    for test_id in requirement.required_test_ids:
        ev = evidence_by_test_id.get(test_id)
        if ev is None or not ev.executed or ev.timed_out:
            unknown_ids.append(test_id)
            continue

        executed_ids.append(test_id)
        if ev.observed_result == VerificationStatus.PASS:
            passed_ids.append(test_id)
        elif ev.observed_result == VerificationStatus.FAIL:
            failed_ids.append(test_id)
        else:
            unknown_ids.append(test_id)

    total_required = len(requirement.required_test_ids)

    if total_required == 0:
        status = VerificationStatus.UNKNOWN
        summary = "UNKNOWN: No required checks are linked to this requirement."
    elif len(failed_ids) > 0:
        status = VerificationStatus.FAIL
        summary = (
            f"FAIL: {len(failed_ids)} of {total_required} required check(s) failed "
            f"({', '.join(failed_ids)})."
        )
    elif len(unknown_ids) > 0 or len(passed_ids) < total_required:
        status = VerificationStatus.UNKNOWN
        summary = (
            f"UNKNOWN: Coverage incomplete — {len(executed_ids)} of {total_required} required "
            f"check(s) executed; unexecuted/missing: {', '.join(unknown_ids)}."
        )
    else:
        status = VerificationStatus.PASS
        summary = (
            f"PASS: All {total_required} required check(s) ({', '.join(passed_ids)}) "
            f"executed and matched expected outputs."
        )

    return RequirementEvaluationRecord(
        requirement_id=requirement.requirement_id,
        title=requirement.title,
        statement=requirement.statement,
        required_test_ids=list(requirement.required_test_ids),
        executed_test_ids=executed_ids,
        passed_test_ids=passed_ids,
        failed_test_ids=failed_ids,
        unknown_test_ids=unknown_ids,
        status=status,
        evidence_summary=summary,
    )


def execute_verification_run(
    implementation_id: str,
    selected_test_ids: Optional[list[str]] = None,
    simulated_timeout_test_ids: Optional[list[str]] = None,
    run_id: Optional[str] = None,
    run_label: Optional[str] = None,
) -> VerificationRunReport:
    """Execute predefined test cases against a predefined implementation and record evidence."""
    if implementation_id not in IMPLEMENTATIONS:
        raise ValueError(
            f"Unknown implementation_id '{implementation_id}'. "
            f"Allowed values: {list(IMPLEMENTATIONS.keys())}"
        )

    impl = IMPLEMENTATIONS[implementation_id]

    if selected_test_ids is None:
        active_test_ids = [tc.test_id for tc in TEST_CASES_CATALOG]
    else:
        unknown_selections = [tid for tid in selected_test_ids if tid not in TEST_CASES_BY_ID]
        if unknown_selections:
            raise ValueError(
                f"Unrecognized test_id(s): {unknown_selections}. "
                f"Allowed values: {list(TEST_CASES_BY_ID.keys())}"
            )
        active_test_ids = list(dict.fromkeys(selected_test_ids))

    timeout_set = set(simulated_timeout_test_ids or [])
    active_set = set(active_test_ids)

    evidence_records: list[CheckEvidenceRecord] = []
    explanation_records: list[CheckExplanationRecord] = []
    evidence_by_test_id: dict[str, CheckEvidenceRecord] = {}

    for tc in TEST_CASES_CATALOG:
        metrics_str = format_input_metrics(tc.input_marks)

        if tc.test_id in timeout_set:
            ev = CheckEvidenceRecord(
                requirement_id=tc.requirement_id,
                test_id=tc.test_id,
                test_name=tc.name,
                category=tc.category,
                implementation_id=implementation_id,
                input=list(tc.input_marks),
                expected_output=tc.expected_output_display,
                expected_return=tc.expected_return,
                expected_exception=tc.expected_exception,
                actual_output="TIMEOUT (Check did not complete)",
                actual_return=None,
                exception_raised="TimeoutError",
                executed=False,
                timed_out=True,
                observed_result=VerificationStatus.UNKNOWN,
                execution_time_ms=None,
            )
            diag = (
                f"Check {tc.test_id} timed out before producing a result. "
                "Timed-out checks are classified as UNKNOWN and never treated as passing."
            )
        elif tc.test_id not in active_set:
            ev = CheckEvidenceRecord(
                requirement_id=tc.requirement_id,
                test_id=tc.test_id,
                test_name=tc.name,
                category=tc.category,
                implementation_id=implementation_id,
                input=list(tc.input_marks),
                expected_output=tc.expected_output_display,
                expected_return=tc.expected_return,
                expected_exception=tc.expected_exception,
                actual_output=None,
                actual_return=None,
                exception_raised=None,
                executed=False,
                timed_out=False,
                observed_result=VerificationStatus.UNKNOWN,
                execution_time_ms=None,
            )
            diag = (
                f"Check {tc.test_id} was not executed in this run. "
                "Uninitialized or skipped checks remain UNKNOWN."
            )
        else:
            start_ns = time.perf_counter_ns()
            actual_return: Optional[bool] = None
            exception_name: Optional[str] = None
            actual_display: str

            try:
                raw_result = impl.fn(list(tc.input_marks))
                elapsed_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000, 4)
                actual_return = bool(raw_result)
                actual_display = format_return_value(actual_return)
            except Exception as exc:  # noqa: BLE001 - intentionally capturing implementation exceptions as test evidence
                elapsed_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000, 4)
                exception_name = type(exc).__name__
                actual_display = f"Exception: {exception_name} ({exc})"

            if tc.expected_exception is not None:
                if exception_name == tc.expected_exception:
                    observed = VerificationStatus.PASS
                    diag = (
                        f"Implementation raised expected {exception_name} on input {tc.input_marks}."
                    )
                else:
                    observed = VerificationStatus.FAIL
                    diag = (
                        f"Expected exception {tc.expected_exception} on input {tc.input_marks}, "
                        f"but observed {actual_display}."
                    )
            else:
                if exception_name is None and actual_return is tc.expected_return:
                    observed = VerificationStatus.PASS
                    diag = (
                        f"Observed output {actual_display} matches expected {tc.expected_output_display} "
                        f"for input {tc.input_marks} ({metrics_str})."
                    )
                else:
                    observed = VerificationStatus.FAIL
                    diag = (
                        f"Discrepancy detected: expected {tc.expected_output_display} but "
                        f"implementation produced {actual_display} for input {tc.input_marks} "
                        f"({metrics_str})."
                    )

            ev = CheckEvidenceRecord(
                requirement_id=tc.requirement_id,
                test_id=tc.test_id,
                test_name=tc.name,
                category=tc.category,
                implementation_id=implementation_id,
                input=list(tc.input_marks),
                expected_output=tc.expected_output_display,
                expected_return=tc.expected_return,
                expected_exception=tc.expected_exception,
                actual_output=actual_display,
                actual_return=actual_return,
                exception_raised=exception_name,
                executed=True,
                timed_out=False,
                observed_result=observed,
                execution_time_ms=elapsed_ms,
            )

        evidence_records.append(ev)
        evidence_by_test_id[tc.test_id] = ev
        explanation_records.append(
            CheckExplanationRecord(
                test_id=tc.test_id,
                requirement_id=tc.requirement_id,
                implementation_id=implementation_id,
                input_metrics=metrics_str,
                design_note=tc.design_note,
                diagnostic_explanation=diag,
            )
        )

    requirement_evaluations = [
        evaluate_requirement_status(req, evidence_by_test_id)
        for req in REQUIREMENTS_CATALOG
    ]

    passed_checks = sum(1 for e in evidence_records if e.observed_result == VerificationStatus.PASS)
    failed_checks = sum(1 for e in evidence_records if e.observed_result == VerificationStatus.FAIL)
    unknown_checks = sum(1 for e in evidence_records if e.observed_result == VerificationStatus.UNKNOWN)
    executed_checks = sum(1 for e in evidence_records if e.executed)

    passed_reqs = sum(1 for r in requirement_evaluations if r.status == VerificationStatus.PASS)
    failed_reqs = sum(1 for r in requirement_evaluations if r.status == VerificationStatus.FAIL)
    unknown_reqs = sum(1 for r in requirement_evaluations if r.status == VerificationStatus.UNKNOWN)

    if failed_reqs > 0 or failed_checks > 0:
        overall_status = VerificationStatus.FAIL
    elif unknown_reqs > 0 or unknown_checks > 0 or len(requirement_evaluations) == 0:
        overall_status = VerificationStatus.UNKNOWN
    else:
        overall_status = VerificationStatus.PASS

    timestamp = datetime.now(timezone.utc).isoformat()
    effective_run_id = run_id or f"run_{implementation_id}_{int(time.time() * 1000)}"
    effective_label = run_label or f"{impl.name} ({len(active_test_ids)}/{len(TEST_CASES_CATALOG)} checks)"

    return VerificationRunReport(
        run_id=effective_run_id,
        run_label=effective_label,
        timestamp=timestamp,
        implementation_id=implementation_id,
        implementation_name=impl.name,
        implementation_short_label=impl.short_label,
        implementation_description=impl.description,
        source_code=impl.source_code,
        selected_test_ids=active_test_ids,
        overall_status=overall_status,
        counts=RunSummaryCounts(
            total_checks=len(evidence_records),
            executed_checks=executed_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            unknown_checks=unknown_checks,
            total_requirements=len(requirement_evaluations),
            passed_requirements=passed_reqs,
            failed_requirements=failed_reqs,
            unknown_requirements=unknown_reqs,
        ),
        requirements=requirement_evaluations,
        evidence=evidence_records,
        explanations=explanation_records,
        scope_disclaimer=EPISTEMIC_PRINCIPLE,
    )


def build_default_ledger(persist: bool = True) -> EvidenceLedger:
    """Run the standard verification scenarios and optionally persist to JSON."""
    correct_full = execute_verification_run(
        implementation_id="correct_all_subjects",
        selected_test_ids=None,
        run_id="correct_full",
        run_label="Correct Implementation — Full Suite (All 8 Checks)",
    )
    faulty_full = execute_verification_run(
        implementation_id="faulty_average_only",
        selected_test_ids=None,
        run_id="faulty_full",
        run_label="Faulty Average-Only Implementation — Full Suite (Exposes Faults)",
    )
    faulty_incomplete = execute_verification_run(
        implementation_id="faulty_average_only",
        selected_test_ids=["TC-01", "TC-03", "TC-04", "TC-07"],
        run_id="incomplete_coverage_demo",
        run_label="Incomplete Coverage Run — Unexecuted Counterexamples (Demonstrates UNKNOWN)",
    )

    ledger = EvidenceLedger(
        schema_version="1.0.0",
        generated_at=datetime.now(timezone.utc).isoformat(),
        epistemic_principle=EPISTEMIC_PRINCIPLE,
        requirements_catalog=REQUIREMENTS_CATALOG,
        test_cases_catalog=TEST_CASES_CATALOG,
        runs={
            "correct_full": correct_full,
            "faulty_full": faulty_full,
            "incomplete_coverage_demo": faulty_incomplete,
        },
    )

    if persist:
        save_ledger(ledger)

    return ledger


def save_ledger(ledger: EvidenceLedger, path: Path = LEDGER_FILE_PATH) -> None:
    """Persist the evidence ledger to disk as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ledger.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def load_or_create_ledger(path: Path = LEDGER_FILE_PATH) -> EvidenceLedger:
    """Load the persisted JSON evidence ledger, or generate it if missing."""
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return EvidenceLedger.model_validate(raw)
        except Exception:  # noqa: BLE001
            return build_default_ledger(persist=True)
    return build_default_ledger(persist=True)
