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
  CheckExplanation,
  EvidenceLedger,
  GnaniConfigStatus,
  VerificationRunReport,
  VerificationStatus,
} from './types';
import { VoicePanel } from './VoicePanel';
import './App.css';

export type PrimaryDestination =
  | 'verify'
  | 'results'
  | 'evidence'
  | 'history'
  | 'settings';

const STATUS_LABELS: Record<VerificationStatus, string> = {
  PASS: 'PASS',
  FAIL: 'FAIL',
  UNKNOWN: 'UNKNOWN',
};

const VERDICT_DEFINITIONS: Record<VerificationStatus, string> = {
  PASS: 'All required supported checks executed and passed.',
  FAIL: 'One or more executed checks demonstrated a failure against the stated requirement.',
  UNKNOWN:
    'The available evidence or test coverage is insufficient to establish a reliable conclusion.',
};

const DEFAULT_REQUIREMENT_STATEMENT =
  'A student passes only when every individual subject mark is at least 40. Any single subject mark below 40 must result in failure (False), even when the arithmetic average across subjects is at least 40.';

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
      <span>{prefix ? `${prefix}: ${STATUS_LABELS[status]}` : STATUS_LABELS[status]}</span>
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

  const [activeDestination, setActiveDestination] =
    useState<PrimaryDestination>('verify');
  const [activeRunKey, setActiveRunKey] = useState<string>('faulty_full');
  const [isEvidenceInspectorOpen, setIsEvidenceInspectorOpen] =
    useState<boolean>(true);
  const [showCheckSelector, setShowCheckSelector] = useState<boolean>(false);
  const [showSourceCode, setShowSourceCode] = useState<boolean>(false);

  // Evidence Inspector filters
  const [reqFilter, setReqFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [historySearchQuery, setHistorySearchQuery] = useState<string>('');
  const [expandedTestIds, setExpandedTestIds] = useState<string[]>(['TC-02']);
  const [voiceLanguage, setVoiceLanguage] = useState<string>('en-IN');

  // Verify workflow controls
  const [requirementInput, setRequirementInput] = useState<string>(
    DEFAULT_REQUIREMENT_STATEMENT,
  );
  const [runnerImplId, setRunnerImplId] = useState<string>('faulty_average_only');
  const [runnerTestIds, setRunnerTestIds] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastRunNotice, setLastRunNotice] = useState<string | null>(null);

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
        if (voiceData?.default_stt_language) {
          setVoiceLanguage(voiceData.default_stt_language);
        }
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

  const explanationByTestIdForActiveRun = useMemo(() => {
    const map: Record<string, CheckExplanation> = {};
    if (activeRun) {
      for (const exp of activeRun.explanations) {
        map[exp.test_id] = exp;
      }
    }
    return map;
  }, [activeRun]);

  const filteredEvidence = useMemo(() => {
    if (!activeRun) return [];
    const normalizedQuery = searchQuery.trim().toLowerCase();
    return activeRun.evidence.filter((ev) => {
      if (reqFilter !== 'ALL' && ev.requirement_id !== reqFilter) {
        return false;
      }
      if (statusFilter !== 'ALL' && ev.observed_result !== statusFilter) {
        return false;
      }
      if (normalizedQuery) {
        const hay = `${ev.test_id} ${ev.requirement_id} ${ev.test_name} ${ev.category} [${ev.input.join(', ')}] ${ev.expected_output} ${ev.actual_output ?? ''}`.toLowerCase();
        if (!hay.includes(normalizedQuery)) {
          return false;
        }
      }
      return true;
    });
  }, [activeRun, reqFilter, statusFilter, searchQuery]);

  const failedEvidenceList = useMemo(() => {
    if (!activeRun) return [];
    return activeRun.evidence.filter((ev) => ev.observed_result === 'FAIL');
  }, [activeRun]);

  const unknownEvidenceList = useMemo(() => {
    if (!activeRun) return [];
    return activeRun.evidence.filter((ev) => ev.observed_result === 'UNKNOWN');
  }, [activeRun]);

  const filteredHistoryEntries = useMemo(() => {
    if (!ledger) return [];
    const q = historySearchQuery.trim().toLowerCase();
    return Object.entries(ledger.runs).filter(([runKey, report]) => {
      if (!q) return true;
      const hay = `${runKey} ${report.run_label} ${report.implementation_name} ${report.implementation_short_label} ${report.overall_status}`.toLowerCase();
      return hay.includes(q);
    });
  }, [ledger, historySearchQuery]);

  const handleToggleTestId = (testId: string) => {
    setRunnerTestIds((prev) =>
      prev.includes(testId) ? prev.filter((id) => id !== testId) : [...prev, testId],
    );
  };

  const handleToggleExpandEvidence = (testId: string) => {
    setExpandedTestIds((prev) =>
      prev.includes(testId) ? prev.filter((id) => id !== testId) : [...prev, testId],
    );
  };

  const handleSelectScenarioPreset = (
    runKey: string,
    implId: string,
    testIds: string[],
  ) => {
    setActiveRunKey(runKey);
    setRunnerImplId(implId);
    setRunnerTestIds(testIds);
    setErrorMessage(null);
  };

  const handleRunVerification = async () => {
    if (isRunning) return;
    setIsRunning(true);
    setErrorMessage(null);
    setLastRunNotice(null);
    try {
      const report = await triggerVerificationRun(
        runnerImplId,
        runnerTestIds,
        `Verification Run: ${runnerImplId} (${runnerTestIds.length} selected checks)`,
      );
      const updatedLedger = await fetchLedger();
      updatedLedger.runs.custom_run = report;
      setLedger(updatedLedger);
      setActiveRunKey('custom_run');
      setLastRunNotice(
        `Verification completed: verdict is ${report.overall_status} (${report.counts.executed_checks}/${report.counts.total_checks} checks executed: ${report.counts.passed_checks} PASS, ${report.counts.failed_checks} FAIL, ${report.counts.unknown_checks} UNKNOWN).`,
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : 'Verification request failed.',
      );
    } finally {
      setIsRunning(false);
    }
  };

  const handleResetBaseline = async () => {
    if (isRunning) return;
    setIsRunning(true);
    setErrorMessage(null);
    setLastRunNotice(null);
    try {
      const freshLedger = await resetBaselineLedger();
      setLedger(freshLedger);
      setActiveRunKey('faulty_full');
      if (catalog) {
        setRunnerTestIds(catalog.test_cases.map((tc) => tc.test_id));
      }
      setLastRunNotice('Baseline verification scenarios restored from deterministic runner.');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Reset failed.');
    } finally {
      setIsRunning(false);
    }
  };

  if (errorMessage && !ledger) {
    return (
      <div className="app-container">
        <div className="surface-card" role="alert">
          <h2>PROOFLOOP Backend Connection Error</h2>
          <p>{errorMessage}</p>
        </div>
      </div>
    );
  }

  if (!ledger || !activeRun) {
    return (
      <div className="app-container" role="status" aria-live="polite">
        <div className="surface-card loading-state-card">
          <div className="loading-spinner" aria-hidden="true" />
          <p>Loading PROOFLOOP verification workspace...</p>
        </div>
      </div>
    );
  }

  const allCatalogTestIds = catalog
    ? catalog.test_cases.map((tc) => tc.test_id)
    : ['TC-01', 'TC-02', 'TC-03', 'TC-04', 'TC-05', 'TC-06', 'TC-07', 'TC-08'];

  const primaryCounterexample = failedEvidenceList[0] ?? null;
  const primaryUnknownCheck = unknownEvidenceList[0] ?? null;

  const renderVerifySection = () => (
    <section
      className="surface-card verify-workspace-card"
      aria-labelledby="verify-heading"
      data-testid="verify-section"
    >
      <div className="section-header">
        <div>
          <div className="eyebrow-tag">Step 1 • Supported Verification Scope</div>
          <h2 id="verify-heading" className="section-title-lg">
            Verify before you trust.
          </h2>
          <p className="section-subtitle">
            PROOFLOOP executes deterministic verification checks against registered Python
            implementations (<code className="mono">backend/app/grading.py</code>) for the
            requirement: <strong>a student passes only when every subject mark is at least 40</strong>.
            Arbitrary code execution and unverified claims are rejected.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleResetBaseline}
          disabled={isRunning}
        >
          Restore Baseline Scenarios
        </button>
      </div>

      {/* Demonstration Scenarios (Scenario A, Scenario B, Scenario C) */}
      <div className="scenario-block">
        <div className="field-label">
          Select a Demonstration Scenario or Active Ledger Run:
        </div>
        <div className="scenario-grid">
          {Object.entries(ledger.runs).map(([runKey, runReport]) => {
            const scenarioTag =
              runKey === 'faulty_full'
                ? 'Scenario A — Faulty Implementation'
                : runKey === 'correct_full'
                  ? 'Scenario B — Correct Implementation'
                  : runKey === 'incomplete_coverage_demo'
                    ? 'Scenario C — Incomplete Verification'
                    : 'Custom Verification Run';
            return (
              <button
                key={runKey}
                type="button"
                data-testid={`scenario-card-${runKey}`}
                className={`scenario-card ${activeRunKey === runKey ? 'active' : ''}`}
                onClick={() =>
                  handleSelectScenarioPreset(
                    runKey,
                    runReport.implementation_id,
                    runReport.selected_test_ids,
                  )
                }
              >
                <div className="scenario-card-top">
                  <span className="eyebrow-tag">{scenarioTag}</span>
                  <StatusBadge status={runReport.overall_status} />
                </div>
                <div className="scenario-card-title">{runReport.run_label}</div>
                <div className="scenario-card-desc">
                  Function: <code className="mono">{runReport.implementation_short_label}</code>
                </div>
                <div className="scenario-metrics">
                  <span>
                    Executed: {runReport.counts.executed_checks}/{runReport.counts.total_checks}
                  </span>
                  <span>
                    {runReport.counts.passed_checks} PASS / {runReport.counts.failed_checks} FAIL /{' '}
                    {runReport.counts.unknown_checks} UNKNOWN
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Verification Input & Target Controls */}
      {catalog && (
        <div className="verify-controls-panel">
          <div className="verify-form-grid">
            <div className="field-block">
              <label htmlFor="verify-requirement-input" className="field-label">
                Stated Requirement Under Verification (Read/Review Context):
              </label>
              <textarea
                id="verify-requirement-input"
                data-testid="verify-requirement-input"
                className="control-textarea"
                rows={2}
                value={requirementInput}
                onChange={(e) => setRequirementInput(e.target.value)}
              />
            </div>

            <div className="field-block">
              <label htmlFor="impl-select" className="field-label">
                Supported Verification Target (<code className="mono">backend/app/grading.py</code>):
              </label>
              <select
                id="impl-select"
                data-testid="target-impl-select"
                className="control-select full-width"
                value={runnerImplId}
                onChange={(e) => setRunnerImplId(e.target.value)}
                disabled={isRunning}
              >
                {catalog.implementations.map((impl) => (
                  <option key={impl.implementation_id} value={impl.implementation_id}>
                    {impl.name} ({impl.short_label})
                  </option>
                ))}
              </select>
              <div className="check-plan-summary mono">
                Checks to execute: <strong>{runnerTestIds.length}</strong> of{' '}
                <strong>{catalog.test_cases.length}</strong> predefined checks
                {runnerTestIds.length < catalog.test_cases.length
                  ? ` (${catalog.test_cases.length - runnerTestIds.length} unexecuted check(s) will be recorded as UNKNOWN)`
                  : ' (full coverage across REQ-01, REQ-02, REQ-03)'}
              </div>
            </div>
          </div>

          <div className="verify-actions-bar">
            <div className="preset-buttons-group">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setRunnerTestIds(allCatalogTestIds)}
                disabled={isRunning}
              >
                Select All 8 Checks
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setRunnerTestIds(['TC-01', 'TC-03', 'TC-04', 'TC-07'])}
                disabled={isRunning}
              >
                Select Incomplete Subset (4/8 Checks → UNKNOWN)
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                data-testid="toggle-check-selector-btn"
                aria-expanded={showCheckSelector}
                onClick={() => setShowCheckSelector((prev) => !prev)}
              >
                {showCheckSelector ? 'Hide Check Selection' : 'Customize Checks'}
              </button>
            </div>

            <button
              type="button"
              className="btn btn-primary-cta"
              data-testid="run-verification-btn"
              onClick={handleRunVerification}
              disabled={isRunning}
            >
              {isRunning ? 'Running verification...' : 'Run verification'}
            </button>
          </div>

          {showCheckSelector && (
            <div className="test-checkbox-grid" data-testid="check-selector-drawer">
              {catalog.test_cases.map((tc) => (
                <label key={tc.test_id} className="test-checkbox-item">
                  <input
                    type="checkbox"
                    checked={runnerTestIds.includes(tc.test_id)}
                    onChange={() => handleToggleTestId(tc.test_id)}
                    disabled={isRunning}
                  />
                  <div>
                    <div className="mono">
                      <strong>{tc.test_id}</strong> ({tc.requirement_id}) — [
                      {tc.input_marks.join(', ')}]
                    </div>
                    <div className="table-subtext">
                      Expected: {tc.expected_output_display} • {tc.category}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );

  const renderResultsSection = () => (
    <section
      className={`surface-card verdict-card verdict-border-${activeRun.overall_status}`}
      aria-labelledby="results-heading"
      data-testid="results-section"
    >
      <div className="section-header">
        <div>
          <div className="eyebrow-tag">Step 2 • Verification Verdict &amp; Findings</div>
          <h2 id="results-heading" className="section-title-lg">
            Verdict: {activeRun.overall_status} — {activeRun.implementation_name}
          </h2>
          <p className="section-subtitle">{VERDICT_DEFINITIONS[activeRun.overall_status]}</p>
        </div>
        <StatusBadge status={activeRun.overall_status} prefix="Overall Verdict" />
      </div>

      {/* Concise factual metrics row */}
      <div className="verdict-metrics-strip" data-testid="verdict-metrics-strip">
        <div className="verdict-metric-box">
          <span className="verdict-metric-label">Checks Executed</span>
          <strong className="mono verdict-metric-val">
            {activeRun.counts.executed_checks} / {activeRun.counts.total_checks}
          </strong>
        </div>
        <div className="verdict-metric-box">
          <span className="verdict-metric-label">Passed Checks</span>
          <strong className="mono verdict-metric-val text-pass">
            {activeRun.counts.passed_checks}
          </strong>
        </div>
        <div className="verdict-metric-box">
          <span className="verdict-metric-label">Failed Checks</span>
          <strong className="mono verdict-metric-val text-fail">
            {activeRun.counts.failed_checks}
          </strong>
        </div>
        <div className="verdict-metric-box">
          <span className="verdict-metric-label">Unknown / Unexecuted</span>
          <strong className="mono verdict-metric-val text-unknown">
            {activeRun.counts.unknown_checks}
          </strong>
        </div>
        <div className="verdict-metric-box">
          <span className="verdict-metric-label">Requirements Verified</span>
          <strong className="mono verdict-metric-val">
            {activeRun.counts.passed_requirements} / {activeRun.counts.total_requirements} PASS
          </strong>
        </div>
      </div>

      {/* Primary Counterexample or Evidence Gap Callout */}
      {primaryCounterexample && (
        <div
          className="primary-finding-callout callout-fail"
          data-testid="primary-counterexample-callout"
        >
          <div className="callout-header">
            <strong>
              Primary Counterexample Identified: {primaryCounterexample.test_id} (
              {primaryCounterexample.requirement_id})
            </strong>
            <StatusBadge status="FAIL" />
          </div>
          <p className="callout-body">
            For input marks <code className="mono">[{primaryCounterexample.input.join(', ')}]</code>{' '}
            ({primaryCounterexample.test_name}), the requirement expects{' '}
            <code className="mono">{primaryCounterexample.expected_output}</code>, but{' '}
            <code className="mono">{activeRun.implementation_short_label}</code> returned{' '}
            <code className="mono">{primaryCounterexample.actual_output}</code>.
            {failedEvidenceList.length > 1 &&
              ` (${failedEvidenceList.length - 1} additional check(s) also failed: ${failedEvidenceList
                .slice(1)
                .map((e) => e.test_id)
                .join(', ')}.)`}
          </p>
        </div>
      )}

      {!primaryCounterexample && primaryUnknownCheck && (
        <div
          className="primary-finding-callout callout-unknown"
          data-testid="primary-unknown-callout"
        >
          <div className="callout-header">
            <strong>
              Insufficient Coverage: {unknownEvidenceList.length} Required Check(s) Unexecuted (
              {unknownEvidenceList.map((e) => e.test_id).join(', ')})
            </strong>
            <StatusBadge status="UNKNOWN" />
          </div>
          <p className="callout-body">
            Although {activeRun.counts.passed_checks} executed check(s) passed, critical fault-exposing
            and boundary checks (starting with <code className="mono">{primaryUnknownCheck.test_id}</code>{' '}
            on input <code className="mono">[{primaryUnknownCheck.input.join(', ')}]</code>) were not
            executed. PROOFLOOP marks the result <strong>UNKNOWN</strong> rather than assuming
            untested cases pass.
          </p>
        </div>
      )}

      {!primaryCounterexample && !primaryUnknownCheck && (
        <div
          className="primary-finding-callout callout-pass"
          data-testid="primary-pass-callout"
        >
          <div className="callout-header">
            <strong>
              All {activeRun.counts.total_checks} Predefined Checks &amp;{' '}
              {activeRun.counts.total_requirements} Linked Requirements Passed
            </strong>
            <StatusBadge status="PASS" />
          </div>
          <p className="callout-body">
            Every supported check — including counterexample{' '}
            <code className="mono">TC-02 ([39, 80, 90])</code>, boundary checks at{' '}
            <code className="mono">39</code> and <code className="mono">40</code>, and empty-input
            rejection <code className="mono">[]</code> — executed and matched expected outputs.
          </p>
        </div>
      )}

      {/* Why this verdict was reached */}
      <div className="verdict-rationale-block">
        <div className="field-label">Why this verdict was reached:</div>
        <ul className="rationale-list">
          {activeRun.requirements.map((req) => (
            <li key={req.requirement_id}>
              <strong className="mono">{req.requirement_id}</strong> ({req.title}):{' '}
              <span className="mono">{req.evidence_summary}</span>
            </li>
          ))}
        </ul>
        <p className="epistemic-footnote">{activeRun.scope_disclaimer}</p>
      </div>

      <div className="verdict-footer-actions">
        <button
          type="button"
          className="btn btn-secondary"
          data-testid="inspect-evidence-btn"
          aria-expanded={isEvidenceInspectorOpen}
          onClick={() => {
            setIsEvidenceInspectorOpen(true);
            if (activeDestination === 'results') {
              setActiveDestination('evidence');
            }
          }}
        >
          Inspect evidence ({activeRun.counts.total_checks} checks)
        </button>
      </div>
    </section>
  );

  const renderEvidenceInspectorSection = () => (
    <section
      className="surface-card evidence-inspector-card"
      aria-labelledby="evidence-ledger-heading"
      data-testid="evidence-inspector-panel"
    >
      <div className="section-header">
        <div>
          <div className="eyebrow-tag">Step 3 • Evidence Inspector</div>
          <h2 id="evidence-ledger-heading" className="section-title-lg">
            Evidence Inspector — {activeRun.run_label}
          </h2>
          <p className="section-subtitle">
            Inspect the requirement traceability gates and individual check execution records
            from the backend verifier. Select any check to view its input metrics, source
            reference, and diagnostic rationale.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          data-testid="toggle-source-code-btn"
          onClick={() => setShowSourceCode((prev) => !prev)}
        >
          {showSourceCode ? 'Hide Implementation Source' : 'View Implementation Source'}
        </button>
      </div>

      {showSourceCode && (
        <div className="source-inspector-drawer" data-testid="source-code-drawer">
          <div className="drawer-meta-row mono">
            <span>
              <strong>Source File:</strong> backend/app/grading.py ::{' '}
              {activeRun.implementation_short_label}
            </span>
            <span>
              <strong>Run ID:</strong> {activeRun.run_id}
            </span>
          </div>
          <pre className="code-block">
            <code>{activeRun.source_code}</code>
          </pre>
        </div>
      )}

      {/* Requirement Traceability Cards */}
      <div className="req-grid">
        {activeRun.requirements.map((req) => (
          <div
            key={req.requirement_id}
            className="req-card"
            data-testid={`requirement-card-${req.requirement_id}`}
          >
            <div className="req-card-header">
              <div>
                <div className="req-id">
                  {req.requirement_id} • <span className="muted-meta">docs/MVP_SCOPE.md</span>
                </div>
                <h3 className="req-title">{req.title}</h3>
              </div>
              <StatusBadge status={req.status} />
            </div>
            <p className="req-statement">{req.statement}</p>
            <div className="req-links">
              <span className="control-label">Linked Checks:</span>
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

      {/* Filter Bar */}
      <div className="inspector-filter-bar">
        <input
          type="search"
          className="control-input"
          aria-label="Search evidence checks"
          data-testid="ledger-search-input"
          placeholder="Search check ID, input mark, or description..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <div className="inline-control-group">
          <label htmlFor="req-filter" className="control-label">
            Requirement:
          </label>
          <select
            id="req-filter"
            className="control-select"
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
        </div>
        <div className="inline-control-group">
          <label htmlFor="status-filter" className="control-label">
            Status:
          </label>
          <select
            id="status-filter"
            className="control-select"
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

      {filteredEvidence.length === 0 ? (
        <div className="empty-state-box" data-testid="ledger-empty-state">
          <p>No check evidence records match the current filter criteria.</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setReqFilter('ALL');
              setStatusFilter('ALL');
              setSearchQuery('');
            }}
          >
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="evidence-table" data-testid="evidence-ledger-table">
            <thead>
              <tr>
                <th>Check</th>
                <th>Req ID</th>
                <th>Input Marks</th>
                <th>Expected Result</th>
                <th>Actual Result</th>
                <th>Status</th>
                <th>Evidence Detail</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvidence.map((ev) => {
                const isExpanded = expandedTestIds.includes(ev.test_id);
                const exp = explanationByTestIdForActiveRun[ev.test_id];
                return (
                  <React.Fragment key={ev.test_id}>
                    <tr
                      className={`row-${ev.observed_result}`}
                      data-testid={`evidence-row-${ev.test_id}`}
                    >
                      <td className="mono">
                        <strong>{ev.test_id}</strong>
                        <div className="table-subtext">
                          {ev.test_name} ({ev.category})
                        </div>
                      </td>
                      <td className="mono">{ev.requirement_id}</td>
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
                          <span className="unknown-placeholder">
                            NOT EXECUTED (No Observation)
                          </span>
                        )}
                      </td>
                      <td data-testid={`result-${ev.test_id}`}>
                        <StatusBadge status={ev.observed_result} />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-link mono"
                          data-testid={`expand-evidence-${ev.test_id}`}
                          aria-expanded={isExpanded}
                          onClick={() => handleToggleExpandEvidence(ev.test_id)}
                        >
                          {isExpanded ? 'Hide detail' : 'Inspect check'}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && exp && (
                      <tr
                        className="expanded-detail-row"
                        data-testid={`expanded-detail-${ev.test_id}`}
                      >
                        <td colSpan={7}>
                          <div className="expanded-evidence-drawer">
                            <div className="drawer-meta-row mono">
                              <span>
                                <strong>Traceability &amp; Source:</strong> {ev.requirement_id}{' '}
                                • backend/app/grading.py :: {activeRun.implementation_short_label}
                              </span>
                              <span>
                                <strong>Execution:</strong>{' '}
                                {ev.executed
                                  ? `Executed (${ev.execution_time_ms ?? 0} ms)`
                                  : ev.timed_out
                                    ? 'Timed out (UNKNOWN)'
                                    : 'Unavailable / Not executed (UNKNOWN)'}
                              </span>
                              <span>
                                <strong>Input Metrics:</strong> {exp.input_metrics}
                              </span>
                            </div>
                            <p className="drawer-line">
                              <strong>Why this check exists:</strong> {exp.design_note}
                            </p>
                            <p className="drawer-line">
                              <strong>Why this check affects the verdict:</strong>{' '}
                              {exp.diagnostic_explanation}
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );

  const renderHistorySection = () => (
    <section
      className="surface-card"
      aria-labelledby="history-heading"
      data-testid="history-section"
    >
      <div className="section-header">
        <div>
          <div className="eyebrow-tag">Persisted Ledger Runs</div>
          <h2 id="history-heading" className="section-title-lg">
            Verification Run History
          </h2>
          <p className="section-subtitle">
            Inspect runs persisted in <code className="mono">backend/app/data/evidence_ledger.json</code>.
          </p>
        </div>
        <input
          type="search"
          className="control-input"
          aria-label="Search stored runs"
          data-testid="history-search-input"
          placeholder="Filter stored runs by name or verdict..."
          value={historySearchQuery}
          onChange={(e) => setHistorySearchQuery(e.target.value)}
        />
      </div>

      <div className="notice-banner notice-info" data-testid="history-storage-limitation">
        <strong>Persistence Scope Limitation:</strong> The backend JSON ledger stores the 3
        deterministic baseline scenarios (<code className="mono">faulty_full</code>,{' '}
        <code className="mono">correct_full</code>,{' '}
        <code className="mono">incomplete_coverage_demo</code>) plus a single{' '}
        <code className="mono">custom_run</code> slot. Running a new custom verification
        overwrites the previous <code className="mono">custom_run</code> entry rather than
        maintaining an unbounded multi-run database.
      </div>

      {filteredHistoryEntries.length === 0 ? (
        <div className="empty-state-box">
          <p>No stored verification runs match your search.</p>
        </div>
      ) : (
        <div className="history-list">
          {filteredHistoryEntries.map(([runKey, report]) => (
            <div
              key={runKey}
              className={`history-row-card ${activeRunKey === runKey ? 'active' : ''}`}
              data-testid={`history-item-${runKey}`}
            >
              <div>
                <div className="history-row-title">
                  <strong>{report.run_label}</strong>
                  <span className="mono muted-meta">Run ID: {report.run_id}</span>
                </div>
                <div className="mono muted-meta">
                  Target: {report.implementation_short_label} • Executed:{' '}
                  {report.counts.executed_checks}/{report.counts.total_checks} checks •{' '}
                  {report.counts.passed_checks} PASS, {report.counts.failed_checks} FAIL,{' '}
                  {report.counts.unknown_checks} UNKNOWN • Timestamp: {report.timestamp}
                </div>
              </div>
              <div className="inline-control-group">
                <StatusBadge status={report.overall_status} />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setActiveRunKey(runKey);
                    setActiveDestination('results');
                  }}
                >
                  Open Result
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );

  const renderSettingsSection = () => (
    <div data-testid="settings-section">
      <VoicePanel
        voiceStatus={voiceStatus}
        activeRun={activeRun}
        selectedLanguage={voiceLanguage}
        onLanguageChange={setVoiceLanguage}
        onTranscriptConfirmed={(t) => setRequirementInput(t)}
      />

      <section className="surface-card" aria-labelledby="settings-heading">
        <div className="section-header">
          <div>
            <div className="eyebrow-tag">Server Configuration &amp; Security Boundaries</div>
            <h2 id="settings-heading" className="section-title">
              Gnani AI &amp; Verifier Configuration Status
            </h2>
            <p className="section-subtitle">
              Real configuration status reported by <code className="mono">GET /api/voice/status</code>.
              Credentials remain strictly on the backend in environment variables.
            </p>
          </div>
          <span
            className={`status-badge ${voiceStatus?.configured ? 'status-PASS' : 'status-UNKNOWN'}`}
          >
            {voiceStatus?.configured ? 'Voice Configured' : 'Voice Unconfigured'}
          </span>
        </div>

        <dl className="settings-dl mono">
          <div>
            <dt>Speech Provider</dt>
            <dd>{voiceStatus?.provider || 'Gnani AI'}</dd>
          </div>
          <div>
            <dt>API Base URL</dt>
            <dd>{voiceStatus?.base_url || 'https://api.vachana.ai'}</dd>
          </div>
          <div>
            <dt>STT / TTS Endpoints</dt>
            <dd>
              {voiceStatus?.stt_endpoint || '/stt/v3'} •{' '}
              {voiceStatus?.tts_endpoint || '/api/v1/tts/inference'}
            </dd>
          </div>
          <div>
            <dt>Default TTS Model &amp; Voice</dt>
            <dd>
              {voiceStatus?.default_tts_model || 'timbre-v2.5'} /{' '}
              {voiceStatus?.default_tts_voice || 'Kaveri'}
            </dd>
          </div>
          <div>
            <dt>Rate Limit Safeguard</dt>
            <dd>
              {voiceStatus?.rate_limit_max_requests ?? 10} req /{' '}
              {voiceStatus?.rate_limit_window_seconds ?? 60}s (in-memory per worker)
            </dd>
          </div>
          <div>
            <dt>Server Env Variable</dt>
            <dd>
              {(voiceStatus?.required_env_vars || ['GNANI_API_KEY']).join(', ')} (server-side
              only)
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );

  return (
    <div className="proofloop-shell">
      {/* Top Navigation Header */}
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand-identity">
            <div className="brand-mark-row">
              <span className="brand-mark" aria-hidden="true">
                PL
              </span>
              <div>
                <div className="brand-eyebrow">PROOFLOOP • AI that checks its own work</div>
                <h1 className="brand-title">PROOFLOOP Evidence Ledger</h1>
              </div>
            </div>
            <p className="brand-tagline">
              PROOFLOOP verifies whether an AI-generated result is trustworthy by checking
              evidence, executing available verification checks, identifying failures, and
              exposing exactly why a result should or should not be trusted.
            </p>
          </div>

          <nav className="primary-nav" aria-label="Primary Navigation">
            <button
              type="button"
              data-testid="nav-verify"
              className={`nav-tab ${activeDestination === 'verify' ? 'active' : ''}`}
              onClick={() => setActiveDestination('verify')}
            >
              1. Verify
            </button>
            <button
              type="button"
              data-testid="nav-results"
              className={`nav-tab ${activeDestination === 'results' ? 'active' : ''}`}
              onClick={() => setActiveDestination('results')}
            >
              2. Results
            </button>
            <button
              type="button"
              data-testid="nav-evidence"
              className={`nav-tab ${activeDestination === 'evidence' ? 'active' : ''}`}
              onClick={() => {
                setIsEvidenceInspectorOpen(true);
                setActiveDestination('evidence');
              }}
            >
              3. Evidence Inspector
            </button>
            <button
              type="button"
              data-testid="nav-history"
              className={`nav-tab ${activeDestination === 'history' ? 'active' : ''}`}
              onClick={() => setActiveDestination('history')}
            >
              History ({Object.keys(ledger.runs).length})
            </button>
            <button
              type="button"
              data-testid="nav-settings"
              className={`nav-tab ${activeDestination === 'settings' ? 'active' : ''}`}
              onClick={() => setActiveDestination('settings')}
            >
              Settings &amp; Gnani AI
            </button>
          </nav>
        </div>
      </header>

      <main className="app-container">
        {/* Epistemic Principle Notice */}
        <section className="epistemic-banner" aria-label="Epistemic Verification Notice">
          <div>
            <strong>Epistemic Principle:</strong> {ledger.epistemic_principle}
          </div>
          <div className="epistemic-badges">
            <StatusBadge status="PASS" />
            <StatusBadge status="FAIL" />
            <StatusBadge status="UNKNOWN" />
          </div>
        </section>

        {errorMessage && (
          <div
            className="notice-banner notice-error error-with-retry"
            role="alert"
            data-testid="workbench-error-banner"
          >
            <div>
              <strong>Verification Error:</strong> {errorMessage}
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              data-testid="retry-verification-btn"
              onClick={handleRunVerification}
              disabled={isRunning}
            >
              Retry verification
            </button>
          </div>
        )}

        {lastRunNotice && (
          <div
            className="notice-banner notice-info"
            role="status"
            data-testid="workbench-run-notice"
          >
            {lastRunNotice}
          </div>
        )}

        {/* Primary Flow: Verify -> Results -> Inspect Evidence */}
        {activeDestination === 'verify' && (
          <div data-testid="verify-destination-view">
            {renderVerifySection()}
            {renderResultsSection()}
            {isEvidenceInspectorOpen && renderEvidenceInspectorSection()}
            <VoicePanel
              voiceStatus={voiceStatus}
              activeRun={activeRun}
              selectedLanguage={voiceLanguage}
              onLanguageChange={setVoiceLanguage}
              onTranscriptConfirmed={(t) => setRequirementInput(t)}
            />
          </div>
        )}

        {activeDestination === 'results' && (
          <div data-testid="results-destination-view">
            {renderResultsSection()}
            <VoicePanel
              voiceStatus={voiceStatus}
              activeRun={activeRun}
              selectedLanguage={voiceLanguage}
              onLanguageChange={setVoiceLanguage}
              onTranscriptConfirmed={(t) => setRequirementInput(t)}
            />
          </div>
        )}

        {activeDestination === 'evidence' && (
          <div data-testid="evidence-destination-view">
            {renderEvidenceInspectorSection()}
          </div>
        )}

        {activeDestination === 'history' && (
          <div data-testid="history-destination-view">{renderHistorySection()}</div>
        )}

        {activeDestination === 'settings' && (
          <div data-testid="settings-destination-view">{renderSettingsSection()}</div>
        )}
      </main>
    </div>
  );
}

export default App;
