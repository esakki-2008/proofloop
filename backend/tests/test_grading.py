"""Deterministic unit tests for correct and faulty student-grading implementations."""

from __future__ import annotations

import pytest

from app.grading import (
    IMPLEMENTATIONS,
    PASS_MARK_THRESHOLD,
    grade_student_correct,
    grade_student_faulty_average,
)


class TestCorrectGradingImplementation:
    """Verify the reference implementation where every subject mark must be >= 40."""

    def test_threshold_constant_is_40(self) -> None:
        assert PASS_MARK_THRESHOLD == 40

    @pytest.mark.parametrize(
        ("marks", "expected"),
        [
            ([40, 50, 60], True),
            ([39, 80, 90], False),
            ([40, 40, 40], True),
            ([39, 39, 39], False),
            ([39, 40, 41], False),
            ([95, 88, 39], False),
            ([40, 100, 100], True),
        ],
    )
    def test_mvp_scope_and_boundary_cases(self, marks: list[int], expected: bool) -> None:
        assert grade_student_correct(marks) is expected

    def test_empty_marks_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            grade_student_correct([])

    @pytest.mark.parametrize("invalid_input", [[40, "50", 60], [True, 50, 60], [40, None, 60]])
    def test_non_numeric_marks_raise_type_error(self, invalid_input: list[object]) -> None:
        with pytest.raises(TypeError):
            grade_student_correct(invalid_input)  # type: ignore[arg-type]


class TestFaultyAverageOnlyImplementation:
    """Verify that the average-only implementation exhibits the expected fault."""

    def test_counterexample_39_80_90_exposes_fault(self) -> None:
        """[39, 80, 90] has average 69.67 (> 40) but subject 1 is 39 (< 40).

        The correct implementation returns False (fail), whereas the faulty
        average-only implementation returns True (pass), exposing the defect.
        """
        marks = [39, 80, 90]
        average = sum(marks) / len(marks)
        assert average > 40
        assert min(marks) == 39 < 40

        expected_output = False
        assert grade_student_correct(marks) is expected_output
        assert grade_student_faulty_average(marks) is not expected_output
        assert grade_student_faulty_average(marks) is True

    def test_boundary_straddle_39_40_41_exposes_fault_at_exact_40_average(self) -> None:
        marks = [39, 40, 41]
        assert (sum(marks) / len(marks)) == 40.0
        assert grade_student_correct(marks) is False
        assert grade_student_faulty_average(marks) is True

    def test_uniform_cases_coincidentally_match(self) -> None:
        """Shows why incomplete test suites can fail to detect the average-only bug."""
        assert grade_student_faulty_average([40, 50, 60]) is True
        assert grade_student_faulty_average([40, 40, 40]) is True
        assert grade_student_faulty_average([39, 39, 39]) is False

    def test_registry_contains_only_fixed_implementations(self) -> None:
        assert set(IMPLEMENTATIONS.keys()) == {"correct_all_subjects", "faulty_average_only"}
