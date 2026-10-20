import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';
import * as api from './api';
import { CatalogResponse, EvidenceLedger, GnaniConfigStatus } from './types';

const mockVoiceConfigured: GnaniConfigStatus = {
  configured: true,
  provider: 'Gnani AI',
  base_url: 'https://api.vachana.ai',
  stt_endpoint: '/stt/v3',
  tts_endpoint: '/api/v1/tts/inference',
  required_env_vars: ['GNANI_API_KEY'],
  missing_env_vars: [],
  default_stt_language: 'en-IN',
  supported_stt_languages: ['en-IN', 'hi-IN', 'ta-IN'],
  supported_audio_formats: ['wav', 'mp3', 'ogg', 'flac', 'aac', 'm4a'],
  max_audio_bytes: 5242880,
  default_tts_model: 'timbre-v2.5',
  default_tts_voice: 'Kaveri',
  message: 'Gnani AI Prisma STT and Timbre TTS are configured.',
};

const mockVoiceUnconfigured: GnaniConfigStatus = {
  ...mockVoiceConfigured,
  configured: false,
  missing_env_vars: ['GNANI_API_KEY'],
  message: 'Gnani AI credentials are not configured (GNANI_API_KEY is unset).',
};

const mockCatalog: CatalogResponse = {
  pass_mark_threshold: 40,
  epistemic_principle:
    'A passing test suite is execution evidence for the specific checks run, never a proof of universal correctness.',
  implementations: [
    {
      implementation_id: 'correct_all_subjects',
      name: 'Correct Implementation (Every Subject >= 40)',
      short_label: 'grade_student_correct',
      description: 'Checks all marks >= 40',
      is_reference_correct: true,
      source_code: 'def grade_student_correct(marks): return all(m >= 40 for m in marks)',
    },
    {
      implementation_id: 'faulty_average_only',
      name: 'Faulty Implementation (Average >= 40 Only)',
      short_label: 'grade_student_faulty_average',
      description: 'Checks average >= 40',
      is_reference_correct: false,
      source_code: 'def grade_student_faulty_average(marks): return sum(marks)/len(marks) >= 40',
    },
  ],
  requirements: [
    {
      requirement_id: 'REQ-01',
      title: 'Minimum Per-Subject Threshold (Every Subject >= 40)',
      statement: 'A student passes only when every individual subject mark is at least 40.',
      required_test_ids: ['TC-01', 'TC-02'],
    },
  ],
  test_cases: [
    {
      test_id: 'TC-01',
      requirement_id: 'REQ-01',
      name: 'Standard passing marks above threshold',
      category: 'Standard',
      input_marks: [40, 50, 60],
      expected_return: true,
      expected_exception: null,
      expected_output_display: 'True (PASS)',
      design_note: 'All >= 40',
    },
    {
      test_id: 'TC-02',
      requirement_id: 'REQ-01',
      name: 'High average with single failing subject [39, 80, 90]',
      category: 'Fault-Exposing',
      input_marks: [39, 80, 90],
      expected_return: false,
      expected_exception: null,
      expected_output_display: 'False (FAIL)',
      design_note: 'Average 69.67 >= 40, subject 1 is 39 < 40',
    },
  ],
};

const mockLedger: EvidenceLedger = {
  schema_version: '1.0.0',
  generated_at: '2026-10-19T10:00:00Z',
  epistemic_principle: mockCatalog.epistemic_principle,
  requirements_catalog: mockCatalog.requirements,
  test_cases_catalog: mockCatalog.test_cases,
  runs: {
    correct_full: {
      run_id: 'correct_full',
      run_label: 'Correct Implementation — Full Suite',
      timestamp: '2026-10-19T10:00:00Z',
      implementation_id: 'correct_all_subjects',
      implementation_name: 'Correct Implementation (Every Subject >= 40)',
      implementation_short_label: 'grade_student_correct',
      implementation_description: 'Checks all marks >= 40',
      source_code: 'def grade_student_correct(marks): ...',
      selected_test_ids: ['TC-01', 'TC-02'],
      overall_status: 'PASS',
      counts: {
        total_checks: 2,
        executed_checks: 2,
        passed_checks: 2,
        failed_checks: 0,
        unknown_checks: 0,
        total_requirements: 1,
        passed_requirements: 1,
        failed_requirements: 0,
        unknown_requirements: 0,
      },
      requirements: [
        {
          requirement_id: 'REQ-01',
          title: 'Minimum Per-Subject Threshold (Every Subject >= 40)',
          statement: 'A student passes only when every individual subject mark is at least 40.',
          required_test_ids: ['TC-01', 'TC-02'],
          executed_test_ids: ['TC-01', 'TC-02'],
          passed_test_ids: ['TC-01', 'TC-02'],
          failed_test_ids: [],
          unknown_test_ids: [],
          status: 'PASS',
          evidence_summary: 'PASS: All 2 required check(s) (TC-01, TC-02) executed and matched expected outputs.',
        },
      ],
      evidence: [
        {
          requirement_id: 'REQ-01',
          test_id: 'TC-01',
          test_name: 'Standard passing marks above threshold',
          category: 'Standard',
          implementation_id: 'correct_all_subjects',
          input: [40, 50, 60],
          expected_output: 'True (PASS)',
          expected_return: true,
          expected_exception: null,
          actual_output: 'True (PASS)',
          actual_return: true,
          exception_raised: null,
          executed: true,
          timed_out: false,
          observed_result: 'PASS',
          execution_time_ms: 0.01,
        },
        {
          requirement_id: 'REQ-01',
          test_id: 'TC-02',
          test_name: 'High average with single failing subject [39, 80, 90]',
          category: 'Fault-Exposing',
          implementation_id: 'correct_all_subjects',
          input: [39, 80, 90],
          expected_output: 'False (FAIL)',
          expected_return: false,
          expected_exception: null,
          actual_output: 'False (FAIL)',
          actual_return: false,
          exception_raised: null,
          executed: true,
          timed_out: false,
          observed_result: 'PASS',
          execution_time_ms: 0.01,
        },
      ],
      explanations: [
        {
          test_id: 'TC-02',
          requirement_id: 'REQ-01',
          implementation_id: 'correct_all_subjects',
          input_metrics: 'min=39, avg=69.67',
          design_note: 'Counterexample [39, 80, 90]',
          diagnostic_explanation: 'Matched expected False (FAIL).',
        },
      ],
      scope_disclaimer: mockCatalog.epistemic_principle,
    },
    faulty_full: {
      run_id: 'faulty_full',
      run_label: 'Faulty Average-Only Implementation — Full Suite',
      timestamp: '2026-10-19T10:00:00Z',
      implementation_id: 'faulty_average_only',
      implementation_name: 'Faulty Implementation (Average >= 40 Only)',
      implementation_short_label: 'grade_student_faulty_average',
      implementation_description: 'Checks average >= 40',
      source_code: 'def grade_student_faulty_average(marks): ...',
      selected_test_ids: ['TC-01', 'TC-02'],
      overall_status: 'FAIL',
      counts: {
        total_checks: 2,
        executed_checks: 2,
        passed_checks: 1,
        failed_checks: 1,
        unknown_checks: 0,
        total_requirements: 1,
        passed_requirements: 0,
        failed_requirements: 1,
        unknown_requirements: 0,
      },
      requirements: [
        {
          requirement_id: 'REQ-01',
          title: 'Minimum Per-Subject Threshold (Every Subject >= 40)',
          statement: 'A student passes only when every individual subject mark is at least 40.',
          required_test_ids: ['TC-01', 'TC-02'],
          executed_test_ids: ['TC-01', 'TC-02'],
          passed_test_ids: ['TC-01'],
          failed_test_ids: ['TC-02'],
          unknown_test_ids: [],
          status: 'FAIL',
          evidence_summary: 'FAIL: 1 of 2 required check(s) failed (TC-02).',
        },
      ],
      evidence: [
        {
          requirement_id: 'REQ-01',
          test_id: 'TC-01',
          test_name: 'Standard passing marks above threshold',
          category: 'Standard',
          implementation_id: 'faulty_average_only',
          input: [40, 50, 60],
          expected_output: 'True (PASS)',
          expected_return: true,
          expected_exception: null,
          actual_output: 'True (PASS)',
          actual_return: true,
          exception_raised: null,
          executed: true,
          timed_out: false,
          observed_result: 'PASS',
          execution_time_ms: 0.01,
        },
        {
          requirement_id: 'REQ-01',
          test_id: 'TC-02',
          test_name: 'High average with single failing subject [39, 80, 90]',
          category: 'Fault-Exposing',
          implementation_id: 'faulty_average_only',
          input: [39, 80, 90],
          expected_output: 'False (FAIL)',
          expected_return: false,
          expected_exception: null,
          actual_output: 'True (PASS)',
          actual_return: true,
          exception_raised: null,
          executed: true,
          timed_out: false,
          observed_result: 'FAIL',
          execution_time_ms: 0.01,
        },
      ],
      explanations: [
        {
          test_id: 'TC-02',
          requirement_id: 'REQ-01',
          implementation_id: 'faulty_average_only',
          input_metrics: 'min=39, avg=69.67',
          design_note: 'Counterexample [39, 80, 90]',
          diagnostic_explanation: 'Discrepancy detected on [39, 80, 90].',
        },
      ],
      scope_disclaimer: mockCatalog.epistemic_principle,
    },
    incomplete_coverage_demo: {
      run_id: 'incomplete_coverage_demo',
      run_label: 'Incomplete Coverage Run (Demonstrates UNKNOWN)',
      timestamp: '2026-10-19T10:00:00Z',
      implementation_id: 'faulty_average_only',
      implementation_name: 'Faulty Implementation (Average >= 40 Only)',
      implementation_short_label: 'grade_student_faulty_average',
      implementation_description: 'Checks average >= 40',
      source_code: 'def grade_student_faulty_average(marks): ...',
      selected_test_ids: ['TC-01'],
      overall_status: 'UNKNOWN',
      counts: {
        total_checks: 2,
        executed_checks: 1,
        passed_checks: 1,
        failed_checks: 0,
        unknown_checks: 1,
        total_requirements: 1,
        passed_requirements: 0,
        failed_requirements: 0,
        unknown_requirements: 1,
      },
      requirements: [
        {
          requirement_id: 'REQ-01',
          title: 'Minimum Per-Subject Threshold (Every Subject >= 40)',
          statement: 'A student passes only when every individual subject mark is at least 40.',
          required_test_ids: ['TC-01', 'TC-02'],
          executed_test_ids: ['TC-01'],
          passed_test_ids: ['TC-01'],
          failed_test_ids: [],
          unknown_test_ids: ['TC-02'],
          status: 'UNKNOWN',
          evidence_summary: 'UNKNOWN: Coverage incomplete — 1 of 2 required check(s) executed; unexecuted/missing: TC-02.',
        },
      ],
      evidence: [
        {
          requirement_id: 'REQ-01',
          test_id: 'TC-01',
          test_name: 'Standard passing marks above threshold',
          category: 'Standard',
          implementation_id: 'faulty_average_only',
          input: [40, 50, 60],
          expected_output: 'True (PASS)',
          expected_return: true,
          expected_exception: null,
          actual_output: 'True (PASS)',
          actual_return: true,
          exception_raised: null,
          executed: true,
          timed_out: false,
          observed_result: 'PASS',
          execution_time_ms: 0.01,
        },
        {
          requirement_id: 'REQ-01',
          test_id: 'TC-02',
          test_name: 'High average with single failing subject [39, 80, 90]',
          category: 'Fault-Exposing',
          implementation_id: 'faulty_average_only',
          input: [39, 80, 90],
          expected_output: 'False (FAIL)',
          expected_return: false,
          expected_exception: null,
          actual_output: null,
          actual_return: null,
          exception_raised: null,
          executed: false,
          timed_out: false,
          observed_result: 'UNKNOWN',
          execution_time_ms: null,
        },
      ],
      explanations: [],
      scope_disclaimer: mockCatalog.epistemic_principle,
    },
  },
};

describe('PROOFLOOP Evidence Ledger UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, 'fetchCatalog').mockResolvedValue(mockCatalog);
    vi.spyOn(api, 'fetchLedger').mockResolvedValue(mockLedger);
    vi.spyOn(api, 'fetchVoiceStatus').mockResolvedValue(mockVoiceConfigured);
  });

  it('renders [39, 80, 90] counterexample failure on faulty implementation and switches across PASS, FAIL, UNKNOWN scenarios', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('PROOFLOOP Evidence Ledger')).toBeInTheDocument();
    });

    // Default active run is faulty_full (FAIL)
    expect(screen.getByTestId('expected-TC-02')).toHaveTextContent('False (FAIL)');
    expect(screen.getByTestId('actual-TC-02')).toHaveTextContent('True (PASS)');
    expect(screen.getByTestId('result-TC-02')).toHaveTextContent('FAIL');

    // Switch to correct_full scenario (PASS)
    fireEvent.click(screen.getByTestId('scenario-card-correct_full'));
    expect(screen.getByTestId('expected-TC-02')).toHaveTextContent('False (FAIL)');
    expect(screen.getByTestId('actual-TC-02')).toHaveTextContent('False (FAIL)');
    expect(screen.getByTestId('result-TC-02')).toHaveTextContent('PASS');

    // Switch to incomplete_coverage_demo scenario (UNKNOWN)
    fireEvent.click(screen.getByTestId('scenario-card-incomplete_coverage_demo'));
    expect(screen.getByTestId('actual-TC-02')).toHaveTextContent('NOT EXECUTED (No Observation)');
    expect(screen.getByTestId('result-TC-02')).toHaveTextContent('UNKNOWN');
  });

  it('allows editing a transcript and requires explicit user confirmation before displaying confirmed review context', async () => {
    const verifySpy = vi.spyOn(api, 'triggerVerificationRun');
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('gnani-voice-panel')).toBeInTheDocument();
    });

    const textarea = screen.getByTestId('transcript-textarea');
    const confirmBtn = screen.getByTestId('confirm-transcript-btn');

    expect(confirmBtn).toBeDisabled();
    expect(screen.queryByTestId('confirmed-transcript-banner')).not.toBeInTheDocument();

    fireEvent.change(textarea, {
      target: { value: 'Check that every subject mark is at least 40 to pass.' },
    });
    expect(confirmBtn).not.toBeDisabled();
    // Still not confirmed until user explicitly clicks confirm
    expect(screen.queryByTestId('confirmed-transcript-banner')).not.toBeInTheDocument();

    fireEvent.click(confirmBtn);
    expect(screen.getByTestId('confirmed-transcript-banner')).toHaveTextContent(
      'Check that every subject mark is at least 40 to pass.',
    );
    expect(screen.getByTestId('confirmed-transcript-banner')).toHaveTextContent(
      'Aligned with Fixed Grading Task',
    );

    // Editing again clears confirmation until re-confirmed
    fireEvent.change(textarea, {
      target: { value: 'Generate a brand new sorting algorithm test suite.' },
    });
    expect(screen.queryByTestId('confirmed-transcript-banner')).not.toBeInTheDocument();

    fireEvent.click(confirmBtn);
    expect(screen.getByTestId('confirmed-transcript-banner')).toHaveTextContent(
      'Outside Fixed Task Scope',
    );
    // Never auto-triggers verification
    expect(verifySpy).not.toHaveBeenCalled();
  });

  it('requests Gnani TTS only on explicit user action, does not autoplay, and preserves verification status', async () => {
    const ttsSpy = vi.spyOn(api, 'synthesizeVerificationSummary').mockResolvedValue({
      summary_text:
        'PROOFLOOP verification result for Faulty Implementation (Average >= 40 Only): overall status is FAIL.',
      audio_base64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=',
      content_type: 'audio/wav',
      run_id: 'faulty_full',
      overall_status: 'FAIL',
      model: 'timbre-v2.5',
      voice: 'Kaveri',
      language: 'en-IN',
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('read-result-aloud-btn')).toBeInTheDocument();
    });

    // TTS must not be called on initial render
    expect(ttsSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('read-result-aloud-btn'));

    await waitFor(() => {
      expect(ttsSpy).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId('tts-summary-box')).toBeInTheDocument();
    });

    expect(screen.getByTestId('tts-summary-text')).toHaveTextContent('overall status is FAIL');
    const audioPlayer = screen.getByTestId('tts-audio-player') as HTMLAudioElement;
    expect(audioPlayer.autoplay).toBe(false);
    // Underlying verification status in Evidence Ledger remains FAIL
    expect(screen.getByTestId('result-TC-02')).toHaveTextContent('FAIL');
  });

  it('shows graceful unavailable state when Gnani credentials are missing and handles API errors without hiding evidence', async () => {
    vi.spyOn(api, 'fetchVoiceStatus').mockResolvedValue(mockVoiceUnconfigured);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('gnani-unconfigured-notice')).toBeInTheDocument();
    });

    expect(screen.getByTestId('speak-requirement-btn')).toBeDisabled();
    expect(screen.getByTestId('read-result-aloud-btn')).toBeDisabled();
    // Evidence ledger remains fully visible
    expect(screen.getByTestId('evidence-ledger-table')).toBeInTheDocument();
  });

  it('displays understandable error message when TTS API call fails while keeping Evidence Ledger visible', async () => {
    vi.spyOn(api, 'synthesizeVerificationSummary').mockRejectedValue(
      new Error('Gnani AI rate limit exceeded during Text-to-Speech. Please wait and retry.'),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('read-result-aloud-btn')).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('read-result-aloud-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('tts-error-message')).toHaveTextContent(
        'Gnani AI rate limit exceeded',
      );
    });

    expect(screen.getByTestId('evidence-ledger-table')).toBeInTheDocument();
    expect(screen.getByTestId('result-TC-02')).toHaveTextContent('FAIL');
  });

  it('navigates across Verify, Results, Evidence Inspector, History, and Settings views and supports expandable evidence details', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Verify before you trust.')).toBeInTheDocument();
    });

    expect(
      screen.getByText(/AI that checks its own work/i),
    ).toBeInTheDocument();

    // Results section shows verdict metrics and primary counterexample TC-02
    expect(screen.getByTestId('verdict-metrics-strip')).toBeInTheDocument();
    expect(screen.getByTestId('primary-counterexample-callout')).toHaveTextContent(
      'TC-02',
    );

    // Expandable evidence detail drawer shows source reference and diagnostic rationale
    expect(screen.getByTestId('expanded-detail-TC-02')).toHaveTextContent(
      'backend/app/grading.py',
    );
    fireEvent.click(screen.getByTestId('expand-evidence-TC-02'));
    expect(screen.queryByTestId('expanded-detail-TC-02')).not.toBeInTheDocument();

    // Source code drawer toggles cleanly
    fireEvent.click(screen.getByTestId('toggle-source-code-btn'));
    expect(screen.getByTestId('source-code-drawer')).toBeInTheDocument();

    // Empty filter state and reset
    fireEvent.change(screen.getByTestId('ledger-search-input'), {
      target: { value: 'nonexistent_check_xyz' },
    });
    expect(screen.getByTestId('ledger-empty-state')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Reset Filters'));
    expect(screen.getByTestId('evidence-ledger-table')).toBeInTheDocument();

    // Navigate to Results destination and click Inspect evidence
    fireEvent.click(screen.getByTestId('nav-results'));
    expect(screen.getByTestId('results-destination-view')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('inspect-evidence-btn'));
    expect(screen.getByTestId('evidence-destination-view')).toBeInTheDocument();

    // Navigate to History destination and verify storage limitation disclosure
    fireEvent.click(screen.getByTestId('nav-history'));
    expect(screen.getByTestId('history-destination-view')).toBeInTheDocument();
    expect(screen.getByTestId('history-storage-limitation')).toHaveTextContent(
      'single custom_run slot',
    );

    // Navigate to Settings & Gnani AI destination
    fireEvent.click(screen.getByTestId('nav-settings'));
    expect(screen.getByTestId('settings-destination-view')).toBeInTheDocument();
    expect(
      screen.getByText('Gnani AI & Verifier Configuration Status'),
    ).toBeInTheDocument();
  });

  it('executes Run verification against the backend, updates verdict, and supports retry on failure', async () => {
    const verifySpy = vi
      .spyOn(api, 'triggerVerificationRun')
      .mockRejectedValueOnce(new Error('Backend verification request timed out'))
      .mockResolvedValueOnce(mockLedger.runs.correct_full);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('run-verification-btn')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('target-impl-select'), {
      target: { value: 'correct_all_subjects' },
    });

    // First attempt fails -> shows error banner with Retry verification button
    fireEvent.click(screen.getByTestId('run-verification-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('workbench-error-banner')).toHaveTextContent(
        'Backend verification request timed out',
      );
    });

    // Clicking Retry verification succeeds and updates verdict to PASS
    fireEvent.click(screen.getByTestId('retry-verification-btn'));
    await waitFor(() => {
      expect(verifySpy).toHaveBeenCalledTimes(2);
      expect(screen.getByTestId('workbench-run-notice')).toHaveTextContent(
        'verdict is PASS',
      );
    });
  });
});

