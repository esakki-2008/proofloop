import React, { useEffect, useMemo, useState } from 'react';
import {
  fetchCatalog,
  fetchLedger,
  fetchVoiceStatus,
  resetBaselineLedger,
  triggerVerificationRun,
} from './api';
import {
  CatalogResponse,
  CheckEvidence,
  EvidenceLedger,
  GnaniConfigStatus,
  VerificationRunReport,
  VerificationStatus,
} from './types';
import { VoicePanel } from './VoicePanel';
import './App.css';

const STATUS_ICONS: Record<VerificationStatus, string> = {
  PASS: '✓',
  FAIL: '✗',
  UNKNOWN: '?',
};

export function StatusBadge({
  status,
  prefix,
}: {
  status: VerificationStatus;
  prefix?: string;
}) {
  return (
    <span
      className={`status-badge status-${status}`}
      data-testid={`status-badge-${status}`}
    >
      <span aria-hidden="true">{STATUS_ICONS[status]}</span>
      <span>{prefix ? `${prefix}: ${status}` : status}</span>
    </span>
  );
}

export function MarksInputDisplay({ marks }: { marks: number[] }) {
  if (marks.length === 0) {
    return <span className="mono">[] (Empty List)</span>;
  }
  return (
    <span className="mono" aria-label={`Input marks [${marks.join(', ')}]`}>
      [
      {marks.map((mark, idx) => (
        <React.Fragment key={`${idx}-${mark}`}>
          <span
            className={`mark-chip ${mark < 40 ? 'mark-below' : ''}`}
            title={mark < 40 ? `Mark ${mark} is below threshold 40` : `Mark ${mark} >= 40`}
          >
            {mark}
          </span>
          {idx < marks.length - 1 ? ', ' : ''}
        </React.Fragment>
      ))}
      ]
    </span>
  );
}

export function App() {
  const [ledger, setLedger] = useState<EvidenceLedger | null>(null);
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<GnaniConfigStatus | null>(null);
  const [activeRunKey, setActiveRunKey] = useState<string>('faulty_full');
  const [reqFilter, setReqFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Controlled runner state
  const [runnerImplId, setRunnerImplId] = useState<string>('faulty_average_only');
  const [runnerTestIds, setRunnerTestIds] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function loadInitialData() {
      try {
        const [catalogData, ledgerData, voiceData] = await Promise.all([
          fetchCatalog(),
          fetchLedger(),
          fetchVoiceStatus().catch(() => null),
        ]);
        if (!mounted) return;
        setCatalog(catalogData);
        setLedger(ledgerData);
        setVoiceStatus(voiceData);
        setRunnerTestIds(catalogData.test_cases.map((tc) => tc.test_id));
      } catch (err) {
        if (!mounted) return;
        setErrorMessage(
          err instanceof Error ? err.message : 'Unable to connect to PROOFLOOP API',
        );
      }
    }
    loadInitialData();
    return () => {
      mounted = false;
    };
  }, []);

  const activeRun: VerificationRunReport | null = useMemo(() => {
    if (!ledger) return null;
    return (
      ledger.runs[activeRunKey] ||
      ledger.runs.faulty_full ||
      ledger.runs.correct_full ||
      Object.values(ledger.runs)[0] ||
      null
    );
  }, [ledger, activeRunKey]);

  const evidenceByTestIdForActiveRun = useMemo(() => {
    const map: Record<string, CheckEvidence> = {};
    if (activeRun) {
      for (const ev of activeRun.evidence) {
        map[ev.test_id] = ev;
      }
    }
    return map;
  }, [activeRun]);

  const filteredEvidence = useMemo(() => {
    if (!activeRun) return [];
    return activeRun.evidence.filter((ev) => {
      if (reqFilter !== 'ALL' && ev.requirement_id !== reqFilter) {
        return false;
      }
      if (statusFilter !== 'ALL' && ev.observed_result !== statusFilter) {
        return false;
      }
      return true;
    });
  }, [activeRun, reqFilter, statusFilter]);

  const handleToggleTestId = (testId: string) => {
    setRunnerTestIds((prev) =>
      prev.includes(testId) ? prev.filter((id) => id !== testId) : [...prev, testId],
    );
  };

  const handleExecuteCustomRun = async () => {
    setIsRunning(true);
    setErrorMessage(null);
    try {
      const report = await triggerVerificationRun(
        runnerImplId,
        runnerTestIds,
        `Custom Run: ${runnerImplId} (${runnerTestIds.length} selected checks)`,
      );
      const updatedLedger = await fetchLedger();
      updatedLedger.runs.custom_run = report;
      setLedger(updatedLedger);
      setActiveRunKey('custom_run');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Execution failed');
    } finally {
      setIsRunning(false);
    }
  };

  const handleResetBaseline = async () => {
    setIsRunning(true);
    setErrorMessage(null);
    try {
      const freshLedger = await resetBaselineLedger();
      setLedger(freshLedger);
      setActiveRunKey('faulty_full');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setIsRunning(false);
    }
  };

  if (errorMessage && !ledger) {
    return (
      <div className="app-container">
        <div className="runner-panel" role="alert">
          <h2>PROOFLOOP Backend Connection Error</h2>
          <p>{errorMessage}</p>
        </div>
      </div>
    );
  }

  if (!ledger || !activeRun) {
    return (
      <div className="app-container">
        <p>Loading PROOFLOOP Evidence Ledger...</p>
      </div>
    );
  }

  const correctRun = ledger.runs.correct_full;
  const faultyRun = ledger.runs.faulty_full;

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div>
          <div className="brand-eyebrow">Phase 1 MVP • Evidence-Based Verification</div>
          <h1 className="brand-title">PROOFLOOP Evidence Ledger</h1>
          <p className="brand-tagline">
            <strong>Don&apos;t trust the claim. Inspect the proof.</strong> Task: A student
            passes only if every subject mark is at least 40.
          </p>
        </div>
        <div className="security-pills">
          <span className="security-pill">Predefined Implementations Only</span>
          <span className="security-pill">Arbitrary Code Execution: Disabled</span>
          <span className="security-pill">Voice Provider: Gnani AI Only</span>
        </div>
      </header>

      {/* Epistemic Principle Banner (Rule 7) */}
      <section className="epistemic-banner" aria-label="Epistemic Verification Notice">
        <div>
          <strong>Epistemic Principle:</strong> {ledger.epistemic_principle}
        </div>
        <div style={{ display: 'flex', gap: '0.45rem', flexShrink: 0 }}>
          <StatusBadge status="PASS" />
          <StatusBadge status="FAIL" />
          <StatusBadge status="UNKNOWN" />
        </div>
      </section>

      {errorMessage && (
        <div
          className="runner-panel"
          role="alert"
          style={{ borderColor: 'var(--fail-border)', marginBottom: '1rem' }}
        >
          <strong>Error:</strong> {errorMessage}
        </div>
      )}

      {/* Gnani AI Voice Interface (STT + Editable Transcript + TTS Summary) */}
      <VoicePanel voiceStatus={voiceStatus} activeRun={activeRun} />

      {/* Scenario Switcher: Compare PASS, FAIL, and UNKNOWN */}
      <section aria-labelledby="scenarios-heading">
        <div className="section-header">
          <div>
            <h2 id="scenarios-heading" className="section-title">
              1. Verification Scenarios (PASS vs. FAIL vs. UNKNOWN)
            </h2>
            <p className="section-subtitle">
              Select a verification run to inspect its requirement evaluations and check-level
              execution evidence.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleResetBaseline}
            disabled={isRunning}
          >
            Re-run Deterministic Baseline Suite
          </button>
        </div>

        <div className="scenario-grid">
          {Object.entries(ledger.runs).map(([runKey, runReport]) => (
            <button
              key={runKey}
              type="button"
              data-testid={`scenario-card-${runKey}`}
              className={`scenario-card ${activeRunKey === runKey ? 'active' : ''}`}
              onClick={() => setActiveRunKey(runKey)}
            >
              <div className="scenario-card-top">
                <span className="scenario-card-title">{runReport.run_label}</span>
                <StatusBadge status={runReport.overall_status} />
              </div>
              <div className="scenario-card-desc">
                Function: <code className="mono">{runReport.implementation_short_label}</code>
              </div>
              <div className="scenario-metrics">
                <span>
                  Checks: {runReport.counts.passed_checks} PASS /{' '}
                  {runReport.counts.failed_checks} FAIL /{' '}
                  {runReport.counts.unknown_checks} UNKNOWN
                </span>
                <span>
                  Reqs: {runReport.counts.passed_requirements} PASS /{' '}
                  {runReport.counts.failed_requirements} FAIL /{' '}
                  {runReport.counts.unknown_requirements} UNKNOWN
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Requirement-to-Test Evidence Linking (Requirement 6 & 7) */}
      <section aria-labelledby="requirements-heading">
        <div className="section-header">
          <div>
            <h2 id="requirements-heading" className="section-title">
              2. Requirement Traceability &amp; Status ({activeRun.implementation_name})
            </h2>
            <p className="section-subtitle">
              A requirement is marked <strong>PASS</strong> only when all of its required checks
              have executed and passed, <strong>FAIL</strong> if any required check fails, and{' '}
              <strong>UNKNOWN</strong> if coverage is incomplete or checks did not run.
            </p>
          </div>
          <StatusBadge status={activeRun.overall_status} prefix="Run Status" />
        </div>

        <div className="req-grid">
          {activeRun.requirements.map((req) => (
            <div
              key={req.requirement_id}
              className="req-card"
              data-testid={`requirement-card-${req.requirement_id}`}
            >
              <div className="req-card-header">
                <div>
                  <div className="req-id">{req.requirement_id}</div>
                  <h3 className="req-title">{req.title}</h3>
                </div>
                <StatusBadge status={req.status} />
              </div>
              <p className="req-statement">{req.statement}</p>
              <div className="req-links">
                <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                  Linked Checks:
                </span>
                {req.required_test_ids.map((tid) => {
                  const ev = evidenceByTestIdForActiveRun[tid];
                  const pillStatus: VerificationStatus = ev ? ev.observed_result : 'UNKNOWN';
                  return (
                    <span
                      key={tid}
                      className={`test-pill pill-${pillStatus}`}
                      title={`${tid}: ${pillStatus}`}
                    >
                      {tid}: {pillStatus}
                    </span>
                  );
                })}
              </div>
              <div className="req-summary mono">{req.evidence_summary}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Execution Evidence Ledger Table (Requirement 5, 6, 7, and Rule 8) */}
      <section className="ledger-panel" aria-labelledby="evidence-ledger-heading">
        <div className="section-header">
          <div>
            <h2 id="evidence-ledger-heading" className="section-title">
              3. Execution Evidence Ledger — {activeRun.run_label}
            </h2>
            <p className="section-subtitle">
              Strictly factual execution records (Test ID, Requirement ID, Input, Expected Output,
              Actual Output, and Observed Result). Kept separate from diagnostic explanations.
            </p>
          </div>

          <div className="filter-bar">
            <label htmlFor="req-filter" style={{ fontSize: '0.8rem' }}>
              Requirement:
            </label>
            <select
              id="req-filter"
              className="runner-select"
              value={reqFilter}
              onChange={(e) => setReqFilter(e.target.value)}
            >
              <option value="ALL">All Requirements</option>
              {ledger.requirements_catalog.map((r) => (
                <option key={r.requirement_id} value={r.requirement_id}>
                  {r.requirement_id} — {r.title}
                </option>
              ))}
            </select>

            <label htmlFor="status-filter" style={{ fontSize: '0.8rem' }}>
              Result:
            </label>
            <select
              id="status-filter"
              className="runner-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="PASS">PASS Only</option>
              <option value="FAIL">FAIL Only</option>
              <option value="UNKNOWN">UNKNOWN Only</option>
            </select>
          </div>
        </div>

        <div className="table-wrapper">
          <table className="evidence-table" data-testid="evidence-ledger-table">
            <thead>
              <tr>
                <th>Test ID</th>
                <th>Requirement</th>
                <th>Category</th>
                <th>Test Input (Subject Marks)</th>
                <th>Expected Output</th>
                <th>Actual Output (Observed)</th>
                <th>Executed</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvidence.map((ev) => (
                <tr
                  key={ev.test_id}
                  className={`row-${ev.observed_result}`}
                  data-testid={`evidence-row-${ev.test_id}`}
                >
                  <td className="mono">
                    <strong>{ev.test_id}</strong>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      {ev.test_name}
                    </div>
                  </td>
                  <td className="mono">{ev.requirement_id}</td>
                  <td>{ev.category}</td>
                  <td>
                    <MarksInputDisplay marks={ev.input} />
                  </td>
                  <td className="mono" data-testid={`expected-${ev.test_id}`}>
                    {ev.expected_output}
                  </td>
                  <td className="mono" data-testid={`actual-${ev.test_id}`}>
                    {ev.actual_output !== null ? (
                      ev.actual_output
                    ) : (
                      <span style={{ color: 'var(--unknown-text)' }}>
                        NOT EXECUTED (No Observation)
                      </span>
                    )}
                  </td>
                  <td className="mono">
                    {ev.executed ? (
                      <span>
                        Yes{' '}
                        {ev.execution_time_ms !== null ? `(${ev.execution_time_ms} ms)` : ''}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--unknown-text)' }}>No</span>
                    )}
                  </td>
                  <td data-testid={`result-${ev.test_id}`}>
                    <StatusBadge status={ev.observed_result} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Side-by-Side Comparison Matrix: Correct vs Faulty Average-Only */}
      {correctRun && faultyRun && (
        <section className="ledger-panel" aria-labelledby="comparison-matrix-heading">
          <div className="section-header">
            <div>
              <h2 id="comparison-matrix-heading" className="section-title">
                4. Direct Comparison Matrix: Correct vs. Faulty Average-Only Implementation
              </h2>
              <p className="section-subtitle">
                Highlights how counterexample <code className="mono">[39, 80, 90]</code> (average =
                69.67 &ge; 40, subject 1 = 39 &lt; 40) and boundary checks expose the average-only
                defect.
              </p>
            </div>
          </div>

          <div className="table-wrapper">
            <table className="evidence-table" data-testid="comparison-matrix-table">
              <thead>
                <tr>
                  <th>Test ID</th>
                  <th>Req ID</th>
                  <th>Input Marks</th>
                  <th>Expected Output</th>
                  <th>Correct Impl Output</th>
                  <th>Correct Status</th>
                  <th>Faulty Avg-Only Output</th>
                  <th>Faulty Status</th>
                </tr>
              </thead>
              <tbody>
                {correctRun.evidence.map((correctEv, idx) => {
                  const faultyEv = faultyRun.evidence[idx];
                  return (
                    <tr
                      key={correctEv.test_id}
                      className={
                        faultyEv?.observed_result === 'FAIL' ? 'row-FAIL' : 'row-PASS'
                      }
                    >
                      <td className="mono">
                        <strong>{correctEv.test_id}</strong>
                      </td>
                      <td className="mono">{correctEv.requirement_id}</td>
                      <td>
                        <MarksInputDisplay marks={correctEv.input} />
                      </td>
                      <td className="mono">{correctEv.expected_output}</td>
                      <td className="mono">{correctEv.actual_output}</td>
                      <td>
                        <StatusBadge status={correctEv.observed_result} />
                      </td>
                      <td className="mono">{faultyEv?.actual_output ?? 'N/A'}</td>
                      <td>
                        {faultyEv ? (
                          <StatusBadge status={faultyEv.observed_result} />
                        ) : (
                          <StatusBadge status="UNKNOWN" />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Controlled Verification Runner (Predefined Implementations & Fixtures) */}
      {catalog && (
        <section className="runner-panel" aria-labelledby="runner-heading">
          <div className="section-header">
            <div>
              <h2 id="runner-heading" className="section-title">
                5. Controlled Verification Runner (Experiment with Coverage &amp; UNKNOWN State)
              </h2>
              <p className="section-subtitle">
                Select a predefined implementation and choose which fixed test cases to execute.
                Unchecking any test case leaves it unexecuted (<strong>UNKNOWN</strong>) and
                prevents its linked requirement from claiming <strong>PASS</strong>.
              </p>
            </div>
          </div>

          <div className="runner-controls">
            <label htmlFor="impl-select">
              <strong>Predefined Implementation:</strong>
            </label>
            <select
              id="impl-select"
              className="runner-select"
              value={runnerImplId}
              onChange={(e) => setRunnerImplId(e.target.value)}
            >
              {catalog.implementations.map((impl) => (
                <option key={impl.implementation_id} value={impl.implementation_id}>
                  {impl.name} ({impl.short_label})
                </option>
              ))}
            </select>

            <button
              type="button"
              className="btn"
              onClick={handleExecuteCustomRun}
              disabled={isRunning}
            >
              {isRunning ? 'Executing...' : 'Execute Selected Checks'}
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={() =>
                setRunnerTestIds(catalog.test_cases.map((tc) => tc.test_id))
              }
            >
              Select All 8 Checks
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setRunnerTestIds(['TC-01', 'TC-03', 'TC-04', 'TC-07'])}
            >
              Select Only Uniform/Happy-Path Checks (Demo UNKNOWN)
            </button>
          </div>

          <div className="test-checkbox-grid">
            {catalog.test_cases.map((tc) => (
              <label key={tc.test_id} className="test-checkbox-item">
                <input
                  type="checkbox"
                  checked={runnerTestIds.includes(tc.test_id)}
                  onChange={() => handleToggleTestId(tc.test_id)}
                />
                <div>
                  <div className="mono">
                    <strong>{tc.test_id}</strong> ({tc.requirement_id}) — [
                    {tc.input_marks.join(', ')}]
                  </div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                    Expected: {tc.expected_output_display}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </section>
      )}

      {/* Separate Explanations Panel (Rule 8: Keep explanations separate from execution evidence) */}
      <section className="explanations-panel" aria-labelledby="explanations-heading">
        <div className="section-header">
          <div>
            <h2 id="explanations-heading" className="section-title">
              6. Diagnostic Explanations &amp; Input Analysis (Separated from Execution Evidence)
            </h2>
            <p className="section-subtitle">
              Per PROOFLOOP MVP Scope Rule 8, human-readable explanations and test rationales are
              stored and rendered separately from the factual execution evidence ledger above.
            </p>
          </div>
        </div>

        <div className="explanation-list">
          {activeRun.explanations.map((exp) => (
            <div key={exp.test_id} className="explanation-card">
              <div
                className="mono"
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginBottom: '0.35rem',
                  color: 'var(--accent-blue)',
                }}
              >
                <strong>
                  {exp.test_id} ({exp.requirement_id})
                </strong>
                <span>{exp.input_metrics}</span>
              </div>
              <p style={{ margin: '0.25rem 0', color: 'var(--text-secondary)' }}>
                <strong>Fixture Rationale:</strong> {exp.design_note}
              </p>
              <p style={{ margin: '0.35rem 0 0', color: 'var(--text-primary)' }}>
                <strong>Diagnostic Note:</strong> {exp.diagnostic_explanation}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Read-Only Predefined Implementation Source Code */}
      {catalog && (
        <section className="ledger-panel" aria-labelledby="source-code-heading">
          <div className="section-header">
            <div>
              <h2 id="source-code-heading" className="section-title">
                7. Predefined Sample Implementations (Read-Only Inspection)
              </h2>
              <p className="section-subtitle">
                Fixed Python implementations registered in{' '}
                <code className="mono">backend/app/grading.py</code>.
              </p>
            </div>
          </div>

          <div className="code-grid">
            {catalog.implementations.map((impl) => (
              <div key={impl.implementation_id}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '0.4rem',
                  }}
                >
                  <strong>{impl.name}</strong>
                  <span className="mono" style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    {impl.short_label}
                  </span>
                </div>
                <pre className="code-block">
                  <code>{impl.source_code}</code>
                </pre>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default App;
