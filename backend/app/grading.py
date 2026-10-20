"""Predefined student-grading implementations for PROOFLOOP Phase 1 MVP.

Requirement under verification:
    A student passes only if every subject mark is at least 40.

Security note:
    Only these fixed, predefined implementations may be invoked by the verification engine.
    No arbitrary or visitor-supplied Python code execution is permitted.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Callable, Sequence

PASS_MARK_THRESHOLD: int = 40


def grade_student_correct(marks: Sequence[int | float]) -> bool:
    """Correct implementation: a student passes iff every subject mark is at least 40.

    Args:
        marks: Non-empty sequence of subject marks.

    Returns:
        True if the student passes (all marks >= 40), False otherwise.

    Raises:
        ValueError: If the marks sequence is empty.
        TypeError: If any mark is not an int or float (excluding booleans).
    """
    if not isinstance(marks, (list, tuple)):
        raise TypeError("Marks must be provided as a list or tuple.")
    if len(marks) == 0:
        raise ValueError("Subject marks list must not be empty.")
    for mark in marks:
        if isinstance(mark, bool) or not isinstance(mark, (int, float)):
            raise TypeError(f"Each subject mark must be numeric; got {type(mark).__name__}.")
    return all(mark >= PASS_MARK_THRESHOLD for mark in marks)


def grade_student_faulty_average(marks: Sequence[int | float]) -> bool:
    """Intentionally faulty implementation: checks only whether the average mark is >= 40.

    Fault exposed by PROOFLOOP:
        A student with marks [39, 80, 90] has an average of 69.67 (>= 40) and is
        incorrectly marked as passing (True), even though the first subject mark (39)
        is below the minimum threshold of 40.
    """
    return (sum(marks) / len(marks)) >= PASS_MARK_THRESHOLD


@dataclass(frozen=True)
class ImplementationSpec:
    """Metadata and callable reference for a predefined sample implementation."""

    implementation_id: str
    name: str
    short_label: str
    description: str
    is_reference_correct: bool
    fn: Callable[[Sequence[int | float]], bool]
    source_code: str


IMPLEMENTATIONS: dict[str, ImplementationSpec] = {
    "correct_all_subjects": ImplementationSpec(
        implementation_id="correct_all_subjects",
        name="Correct Implementation (Every Subject >= 40)",
        short_label="grade_student_correct",
        description=(
            "Validates non-empty numeric marks and checks that every individual "
            "subject mark is at least 40."
        ),
        is_reference_correct=True,
        fn=grade_student_correct,
        source_code=inspect.getsource(grade_student_correct),
    ),
    "faulty_average_only": ImplementationSpec(
        implementation_id="faulty_average_only",
        name="Faulty Implementation (Average >= 40 Only)",
        short_label="grade_student_faulty_average",
        description=(
            "Intentionally faulty baseline that checks only whether the arithmetic "
            "mean of marks is at least 40, ignoring individual subject failures."
        ),
        is_reference_correct=False,
        fn=grade_student_faulty_average,
        source_code=inspect.getsource(grade_student_faulty_average),
    ),
}
