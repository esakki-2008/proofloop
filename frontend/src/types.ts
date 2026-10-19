export type VerificationStatus = 'PASS' | 'FAIL' | 'UNKNOWN';

export interface RequirementSpec {
  requirement_id: string;
  title: string;
  statement: string;
  required_test_ids: string[];
}

export interface TestCaseSpec {
  test_id: string;
  requirement_id: string;
  name: string;
  category: string;
  input_marks: number[];
  expected_return: boolean | null;
  expected_exception: string | null;
  expected_output_display: string;
  design_note: string;
}

export interface CheckEvidence {
  requirement_id: string;
  test_id: string;
  test_name: string;
  category: string;
  implementation_id: string;
  input: number[];
  expected_output: string;
  expected_return: boolean | null;
  expected_exception: string | null;
  actual_output: string | null;
  actual_return: boolean | null;
  exception_raised: string | null;
  executed: boolean;
  timed_out: boolean;
  observed_result: VerificationStatus;
  execution_time_ms: number | null;
}

export interface CheckExplanation {
  test_id: string;
  requirement_id: string;
  implementation_id: string;
  input_metrics: string;
  design_note: string;
  diagnostic_explanation: string;
}

export interface RequirementEvaluation {
  requirement_id: string;
  title: string;
  statement: string;
  required_test_ids: string[];
  executed_test_ids: string[];
  passed_test_ids: string[];
  failed_test_ids: string[];
  unknown_test_ids: string[];
  status: VerificationStatus;
  evidence_summary: string;
}

export interface RunSummaryCounts {
  total_checks: number;
  executed_checks: number;
  passed_checks: number;
  failed_checks: number;
  unknown_checks: number;
  total_requirements: number;
  passed_requirements: number;
  failed_requirements: number;
  unknown_requirements: number;
}

export interface VerificationRunReport {
  run_id: string;
  run_label: string;
  timestamp: string;
  implementation_id: string;
  implementation_name: string;
  implementation_short_label: string;
  implementation_description: string;
  source_code: string;
  selected_test_ids: string[];
  overall_status: VerificationStatus;
  counts: RunSummaryCounts;
  requirements: RequirementEvaluation[];
  evidence: CheckEvidence[];
  explanations: CheckExplanation[];
  scope_disclaimer: string;
}

export interface EvidenceLedger {
  schema_version: string;
  generated_at: string;
  epistemic_principle: string;
  requirements_catalog: RequirementSpec[];
  test_cases_catalog: TestCaseSpec[];
  runs: Record<string, VerificationRunReport>;
}

export interface ImplementationInfo {
  implementation_id: string;
  name: string;
  short_label: string;
  description: string;
  is_reference_correct: boolean;
  source_code: string;
}

export interface CatalogResponse {
  pass_mark_threshold: number;
  epistemic_principle: string;
  implementations: ImplementationInfo[];
  requirements: RequirementSpec[];
  test_cases: TestCaseSpec[];
}
