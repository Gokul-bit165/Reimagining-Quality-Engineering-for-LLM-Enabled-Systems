import type { Report, Evaluation, EvalMetric } from '../types/api';

/**
 * Escapes values for standard RFC 4180 CSV compatible with Microsoft Excel
 */
function escapeCsv(val: any): string {
  if (val === null || val === undefined) return '""';
  const str = String(val).replace(/"/g, '""');
  return `"${str}"`;
}

function pct(n?: number | null): string {
  if (n === null || n === undefined) return 'N/A';
  return `${(n * 100).toFixed(1)}%`;
}

/**
 * Generates and downloads a rich, multi-section Excel Spreadsheet (.csv)
 * explaining the overall score, why it scored, and full evidence.
 */
export function exportToExcel(report: Report, runId: string) {
  const d = report.decision.decision;
  const isReject = d === 'REJECT';
  const isRelease = d === 'RELEASE';
  const isInsufficient = d === 'INSUFFICIENT_EVIDENCE';

  // Compute metric explanations
  const metricExplanations = report.metrics.map((m) => {
    const rate = m.failure_rate;
    const rateStr = rate ? `${pct(rate.point)} (95% CI: ${pct(rate.lower)} - ${pct(rate.upper)})` : 'N/A';
    const appStr = m.appetite !== null ? pct(m.appetite) : 'No appetite set';

    let why = '';
    if (m.status === 'above') {
      why = `BREACHED RISK APPETITE: Lower confidence bound (${pct(rate?.lower)}) exceeds the maximum tolerable threshold of ${appStr}. Immediate ship blocker.`;
    } else if (m.status === 'straddles') {
      why = `INCONCLUSIVE APPETITE: Interval (${pct(rate?.lower)} - ${pct(rate?.upper)}) straddles the appetite threshold of ${appStr}. More test evidence needed to confirm compliance.`;
    } else if (m.status === 'within') {
      why = `COMPLIANT: Entire confidence interval is within the risk appetite threshold of ${appStr}.`;
    } else {
      why = `Observed failure rate: ${rateStr}. No appetite threshold configured.`;
    }

    return {
      metric: m.metric,
      dimension: m.dimension,
      failed: m.failed_cases,
      passed: m.passed_cases,
      total: m.failed_cases + m.passed_cases,
      rateStr,
      appStr,
      status: m.status?.toUpperCase() || 'EVALUATED',
      why,
    };
  });

  const lines: string[] = [];

  // UTF-8 BOM so Excel opens special characters correctly
  lines.push('\uFEFF');

  // HEADER & METADATA
  lines.push('========================================================================================');
  lines.push(`AI SYSTEM VERIFICATION & RELEASE AUDIT REPORT: ${runId}`);
  lines.push('========================================================================================');
  lines.push(`Target Application:,${escapeCsv(report.scenario.app)}`);
  lines.push(`Variant Tested:,${escapeCsv(report.scenario.variant)}`);
  lines.push(`Risk Scenario Description:,${escapeCsv(report.scenario.text)}`);
  lines.push(`OWASP Classification:,${escapeCsv(report.scenario.taxonomy_id)}`);
  lines.push(`Execution Target Engine:,${escapeCsv(report.labels.target)}`);
  lines.push(`Policy Version:,${escapeCsv(`v${report.decision.policy_version}`)}`);
  lines.push(`Cryptographic Ledger Verified:,${escapeCsv(report.ledger.verified ? 'YES (Cryptographically Valid)' : 'NO')}`);
  lines.push(`Audit Generated At:,${escapeCsv(new Date().toISOString())}`);
  lines.push('');

  // SECTION 1: EXECUTIVE VERDICT & SCORE EXPLANATION
  lines.push('----------------------------------------------------------------------------------------');
  lines.push('1. EXECUTIVE VERDICT & WHY IT SCORED');
  lines.push('----------------------------------------------------------------------------------------');
  lines.push(`Overall Release Verdict:,${escapeCsv(d)}`);
  
  let verdictWhy = '';
  if (isReject) {
    verdictWhy = `REJECT (SHIP BLOCKER): The evaluated system failed pre-release verification. One or more failure rates statistically breached organizational risk appetite bounds.`;
  } else if (isRelease) {
    verdictWhy = `RELEASE (APPROVED): All evaluated risk dimensions are statistically verified within acceptable risk appetite bounds.`;
  } else if (isInsufficient) {
    verdictWhy = `INSUFFICIENT EVIDENCE: Statistical intervals straddle the appetite boundary. Insufficient test volume to certify release safely.`;
  } else {
    verdictWhy = `CONDITIONAL RELEASE: System passed core checks but has uncovered risks or pending governance requirements.`;
  }
  lines.push(`Verdict Justification:,${escapeCsv(verdictWhy)}`);

  if (report.decision.conditions && report.decision.conditions.length > 0) {
    lines.push(`Pre-Release Conditions:,${escapeCsv(report.decision.conditions.join('; '))}`);
  }
  if (report.decision.uncovered_risks && report.decision.uncovered_risks.length > 0) {
    lines.push(`Claims Not Made / Uncovered Risks:,${escapeCsv(report.decision.uncovered_risks.join('; '))}`);
  }
  lines.push('');

  // SECTION 2: METRICS SCORECARD & WHY EACH SCORED
  lines.push('----------------------------------------------------------------------------------------');
  lines.push('2. METRICS SCORECARD & STATISTICAL EXPLANATION');
  lines.push('----------------------------------------------------------------------------------------');
  lines.push(['Risk Metric', 'Dimension', 'Failed Cases', 'Passed Cases', 'Total Tested', 'Failure Rate (95% CI)', 'Max Appetite', 'Appetite Status', 'Why It Scored (Statistical Explanation)'].map(escapeCsv).join(','));

  metricExplanations.forEach((m) => {
    lines.push([
      escapeCsv(m.metric),
      escapeCsv(m.dimension),
      escapeCsv(m.failed),
      escapeCsv(m.passed),
      escapeCsv(m.total),
      escapeCsv(m.rateStr),
      escapeCsv(m.appStr),
      escapeCsv(m.status),
      escapeCsv(m.why),
    ].join(','));
  });
  lines.push('');

  // SECTION 3: CONCRETE FAILURE EVIDENCE REGISTRY
  lines.push('----------------------------------------------------------------------------------------');
  lines.push('3. CONCRETE FAILURE EVIDENCE REGISTRY (WHY AND WHAT FAILED)');
  lines.push('----------------------------------------------------------------------------------------');
  lines.push(['Case ID', 'Risk Metric', 'Test Prompt / Question', 'Expected Truth / Grounding', 'Observed Sandbox Output', 'Verbatim Citations / Grounding Key', 'Evaluation Reasoning'].map(escapeCsv).join(','));

  const testMap = new Map(report.generation.tests.map((t) => [t.case_id, t]));

  let evidenceCount = 0;
  report.metrics.forEach((m) => {
    m.failures.forEach((f) => {
      evidenceCount++;
      const t = testMap.get(f.case_id);
      lines.push([
        escapeCsv(f.case_id),
        escapeCsv(m.metric),
        escapeCsv(t?.question || '(test question not recorded)'),
        escapeCsv(t?.expected || '(expected behavior)'),
        escapeCsv(f.output || '(no output)'),
        escapeCsv(f.citations.join('; ') || f.evidence_key || 'N/A'),
        escapeCsv(f.detail || 'Failed oracle evaluation against ground truth policy facts'),
      ].join(','));
    });
  });

  if (evidenceCount === 0) {
    lines.push(['No failures recorded. All tests conformed to expected behavior.', '', '', '', '', '', ''].map(escapeCsv).join(','));
  }
  lines.push('');

  // SECTION 4: ADVERSARIAL PENETRATION RESULTS
  lines.push('----------------------------------------------------------------------------------------');
  lines.push('4. ADVERSARIAL JAILBREAK & INJECTION SINK ATTACKS');
  lines.push('----------------------------------------------------------------------------------------');
  lines.push(['Pair ID', 'Surface', 'Attacker Goal', 'Baseline Breached', 'Static Template Breached', 'Static Breach Step', 'Adaptive Mutation Breached', 'Adaptive Breach Step'].map(escapeCsv).join(','));

  report.attacks.rows.forEach((r) => {
    lines.push([
      escapeCsv(r.pair_id),
      escapeCsv(r.surface),
      escapeCsv(r.goal),
      escapeCsv(r.baseline_breached ? 'YES' : 'NO'),
      escapeCsv(r.static_template.breached ? 'BREACHED' : 'HELD'),
      escapeCsv(r.static_template.first_success !== null ? `@ attempt ${r.static_template.first_success}` : 'Never'),
      escapeCsv(r.adaptive_mutation.breached ? 'BREACHED' : 'HELD'),
      escapeCsv(r.adaptive_mutation.first_success !== null ? `@ attempt ${r.adaptive_mutation.first_success}` : 'Never'),
    ].join(','));
  });
  lines.push('');

  // SECTION 5: AUDIT TRAIL & GOVERNANCE SIGN-OFFS
  lines.push('----------------------------------------------------------------------------------------');
  lines.push('5. CRYPTOGRAPHIC AUDIT PROOF & GOVERNANCE SIGNOFF');
  lines.push('----------------------------------------------------------------------------------------');
  lines.push(`Ledger Events Recorded:,${escapeCsv(report.ledger.entries)}`);
  lines.push(`Ledger Hash Chain Verified:,${escapeCsv(report.ledger.verified ? 'VERIFIED' : 'FAILED')}`);
  lines.push(`Ledger Head Block Hash:,${escapeCsv(report.ledger.head)}`);
  lines.push('');
  lines.push(['Approver Name', 'Approval Status', 'Decision Reference', 'Signoff Note'].map(escapeCsv).join(','));

  if (report.human_signoff.length > 0) {
    report.human_signoff.forEach((s) => {
      lines.push([
        escapeCsv(s.approver),
        escapeCsv(s.approved ? 'APPROVED' : 'REJECTED'),
        escapeCsv(s.decision_id),
        escapeCsv(s.note || '(none)'),
      ].join(','));
    });
  } else {
    lines.push(['No human sign-off recorded yet. Pending formal governance review.', '', '', ''].map(escapeCsv).join(','));
  }

  const csvContent = lines.join('\r\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${runId}_Verification_Report.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Generates and downloads an Executive Word Document (.doc)
 * containing rich corporate styling, score analysis, and complete evidence tables.
 */
export function exportToWordDoc(report: Report, runId: string) {
  const d = report.decision.decision;
  const isReject = d === 'REJECT';
  const isRelease = d === 'RELEASE';

  const testMap = new Map(report.generation.tests.map((t) => [t.case_id, t]));

  const failuresList: {
    caseId: string;
    metric: string;
    question: string;
    expected: string;
    output: string;
    citations: string;
    detail: string;
  }[] = [];

  report.metrics.forEach((m) => {
    m.failures.forEach((f) => {
      const t = testMap.get(f.case_id);
      failuresList.push({
        caseId: f.case_id,
        metric: m.metric,
        question: t?.question || '(test question not recorded)',
        expected: t?.expected || '(expected behavior)',
        output: f.output || '(no output)',
        citations: f.citations.join('; ') || f.evidence_key || 'N/A',
        detail: f.detail || 'Failed oracle evaluation against ground truth policy facts',
      });
    });
  });

  const html = `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns="http://www.w3.org/TR/REC-html40">
<head>
  <meta charset="utf-8">
  <title>Verification Report - ${runId}</title>
  <!--[if gte mso 9]>
  <xml>
    <w:WordDocument>
      <w:View>Print</w:View>
      <w:Zoom>100</w:Zoom>
      <w:DoNotOptimizeForBrowser/>
    </w:WordDocument>
  </xml>
  <![endif]-->
  <style>
    body {
      font-family: 'Segoe UI', Calibri, Arial, sans-serif;
      font-size: 11pt;
      line-height: 1.5;
      color: #1e293b;
      margin: 36pt 48pt;
    }
    h1 {
      font-size: 22pt;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 4pt;
    }
    h2 {
      font-size: 14pt;
      font-weight: 700;
      color: #1e293b;
      margin-top: 18pt;
      margin-bottom: 6pt;
      border-bottom: 1.5pt solid #e2e8f0;
      padding-bottom: 4pt;
    }
    h3 {
      font-size: 12pt;
      font-weight: 600;
      color: #334155;
      margin-top: 12pt;
      margin-bottom: 4pt;
    }
    .badge {
      display: inline-block;
      padding: 4pt 10pt;
      border-radius: 4pt;
      font-weight: 700;
      font-size: 12pt;
      text-transform: uppercase;
      letter-spacing: 0.5pt;
    }
    .badge-reject {
      background-color: #fee2e2;
      color: #991b1b;
      border: 1pt solid #f87171;
    }
    .badge-release {
      background-color: #d1fae5;
      color: #065f46;
      border: 1pt solid #34d399;
    }
    .badge-insufficient {
      background-color: #f1f5f9;
      color: #475569;
      border: 1pt solid #94a3b8;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 8pt;
      margin-bottom: 14pt;
      font-size: 10pt;
    }
    th {
      background-color: #f8fafc;
      border: 1pt solid #cbd5e1;
      padding: 6pt 8pt;
      text-align: left;
      font-weight: 600;
      color: #0f172a;
    }
    td {
      border: 1pt solid #cbd5e1;
      padding: 6pt 8pt;
      vertical-align: top;
    }
    .callout {
      background-color: #f8fafc;
      border-left: 3pt solid #4f46e5;
      padding: 8pt 12pt;
      margin: 10pt 0;
      border-radius: 0 4pt 4pt 0;
    }
    .callout-alert {
      background-color: #fff1f2;
      border-left: 3pt solid #e11d48;
      padding: 8pt 12pt;
      margin: 10pt 0;
      border-radius: 0 4pt 4pt 0;
    }
    .code-box {
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 9.5pt;
      background-color: #f1f5f9;
      padding: 4pt 6pt;
      border-radius: 3pt;
      color: #0f172a;
    }
    .meta-table td {
      border: none;
      padding: 2pt 6pt;
      font-size: 10pt;
    }
  </style>
</head>
<body>

  <!-- HEADER -->
  <div style="border-bottom: 2pt solid #4f46e5; padding-bottom: 12pt; margin-bottom: 16pt;">
    <div style="font-size: 9pt; text-transform: uppercase; letter-spacing: 1pt; color: #64748b; font-weight: 600;">
      Pre-Release AI Quality Engineering Platform · Verification Dossier
    </div>
    <h1>Release Recommendation & Evidence Report</h1>
    <div style="font-size: 11pt; color: #64748b;">
      Execution ID: <strong>${runId}</strong> · Generated on ${new Date().toLocaleString()}
    </div>
  </div>

  <!-- EXECUTIVE SUMMARY -->
  <h2>1. Executive Summary & Why It Scored</h2>
  <div style="margin: 12pt 0;">
    <span class="badge ${isReject ? 'badge-reject' : isRelease ? 'badge-release' : 'badge-insufficient'}">
      VERDICT: ${d}
    </span>
  </div>

  <div class="${isReject ? 'callout-alert' : 'callout'}">
    <strong>Executive Decision Analysis:</strong><br>
    ${isReject
      ? `<strong>The application is BLOCKED from production release.</strong> One or more evaluated failure rates exceed the organization's maximum risk appetite threshold with 95% statistical confidence. Shipping this build introduces verified failure behaviors in customer interactions.`
      : isRelease
      ? `<strong>The application is APPROVED for release.</strong> All evaluated risk dimensions have Clopper-Pearson 95% confidence intervals fully within organizational risk tolerance boundaries.`
      : `<strong>INSUFFICIENT EVIDENCE to authorize release.</strong> Statistical uncertainty bounds straddle the appetite threshold. Further targeted test cycles must be executed to certify conformance.`
    }
  </div>

  <table class="meta-table" style="width: auto; margin-bottom: 16pt;">
    <tr><td><strong>Application:</strong></td><td>${report.scenario.app} (${report.scenario.variant})</td></tr>
    <tr><td><strong>Scenario:</strong></td><td>${report.scenario.text}</td></tr>
    <tr><td><strong>Taxonomy:</strong></td><td>${report.scenario.taxonomy_id}</td></tr>
    <tr><td><strong>Policy Version:</strong></td><td>v${report.decision.policy_version}</td></tr>
    <tr><td><strong>Hash Chain Ledger:</strong></td><td>${report.ledger.verified ? 'Verified (Tamper-evident SHA-256)' : 'Unverified'}</td></tr>
  </table>

  <!-- SECTION 2: METRICS SCORECARD -->
  <h2>2. Quantitative Scorecard & Risk Appetite Comparison</h2>
  <p>Clopper-Pearson 95% exact binomial intervals calculated against corporate risk appetite lines. No composite scores: each risk boundary stands alone.</p>

  <table>
    <thead>
      <tr>
        <th>Risk Metric</th>
        <th>Dimension</th>
        <th>Failed / Tested</th>
        <th>Observed Rate (95% CI)</th>
        <th>Appetite Limit</th>
        <th>Compliance Status</th>
        <th>Explanation</th>
      </tr>
    </thead>
    <tbody>
      ${report.metrics.map((m) => {
        const rate = m.failure_rate;
        const rateStr = rate ? `${pct(rate.point)}<br><small style="color:#64748b;">(${pct(rate.lower)} - ${pct(rate.upper)})</small>` : 'N/A';
        const appStr = m.appetite !== null ? pct(m.appetite) : 'None';
        const isBreach = m.status === 'above';
        const isStraddle = m.status === 'straddles';
        const statusText = isBreach ? 'BREACHED' : isStraddle ? 'STRADDLES' : 'WITHIN';
        const statusColor = isBreach ? '#991b1b' : isStraddle ? '#b45309' : '#065f46';
        
        let expl = '';
        if (isBreach) {
          expl = `Lower bound (${pct(rate?.lower)}) exceeds ${appStr} appetite line.`;
        } else if (isStraddle) {
          expl = `Confidence bounds span across ${appStr} limit.`;
        } else {
          expl = `Within acceptable risk appetite (${appStr}).`;
        }

        return `
          <tr>
            <td><strong>${m.metric}</strong></td>
            <td>${m.dimension}</td>
            <td>${m.failed_cases} / ${m.failed_cases + m.passed_cases}</td>
            <td>${rateStr}</td>
            <td><strong>${appStr}</strong></td>
            <td style="color: ${statusColor}; font-weight: 700;">${statusText}</td>
            <td style="font-size: 9pt;">${expl}</td>
          </tr>
        `;
      }).join('')}
    </tbody>
  </table>

  <!-- SECTION 3: EVIDENCE REGISTRY -->
  <h2>3. Concrete Failure Evidence Registry</h2>
  <p>Detailed breakdown of failing test prompts, verbatim ground truth citations, observed model sandbox outputs, and evaluation reasoning.</p>

  ${failuresList.length === 0 ? '<p><em>No failures recorded. All tests conformed to expected behavior.</em></p>' : ''}

  ${failuresList.map((f, idx) => `
    <div style="border: 1pt solid #cbd5e1; border-radius: 4pt; padding: 10pt; margin-bottom: 12pt; background-color: #ffffff;">
      <div style="display: flex; justify-content: space-between; border-bottom: 1pt solid #e2e8f0; padding-bottom: 4pt; margin-bottom: 6pt;">
        <strong>Case #${idx + 1}: ${f.caseId}</strong>
        <span style="color: #e11d48; font-weight: 600; text-transform: uppercase;">${f.metric} Failure</span>
      </div>

      <div style="margin-bottom: 6pt;">
        <span style="font-size: 9pt; color: #64748b; font-weight: 600; text-transform: uppercase;">Prompt / Question:</span><br>
        <div class="code-box">${f.question}</div>
      </div>

      <div style="margin-bottom: 6pt;">
        <span style="font-size: 9pt; color: #64748b; font-weight: 600; text-transform: uppercase;">Observed Sandbox Response:</span><br>
        <div class="code-box" style="color: #b91c1c; background-color: #fff1f2;">${f.output}</div>
      </div>

      <div style="margin-bottom: 6pt;">
        <span style="font-size: 9pt; color: #64748b; font-weight: 600; text-transform: uppercase;">Verbatim Ground Truth Evidence Citation:</span><br>
        <div style="font-size: 9.5pt; color: #334155; font-style: italic;">${f.citations}</div>
      </div>

      <div>
        <span style="font-size: 9pt; color: #64748b; font-weight: 600; text-transform: uppercase;">Evaluation Reasoning:</span><br>
        <div style="font-size: 9.5pt; color: #991b1b;">${f.detail}</div>
      </div>
    </div>
  `).join('')}

  <!-- SECTION 4: ADVERSARIAL PENETRATION -->
  <h2>4. Adversarial Penetration Testing (Jailbreak Sinks)</h2>
  <table>
    <thead>
      <tr>
        <th>Pair ID</th>
        <th>Surface</th>
        <th>Attacker Goal</th>
        <th>Static Template</th>
        <th>Adaptive Mutation</th>
      </tr>
    </thead>
    <tbody>
      ${report.attacks.rows.map((r) => `
        <tr>
          <td><code>${r.pair_id}</code></td>
          <td>${r.surface}</td>
          <td>${r.goal}</td>
          <td><span style="color: ${r.static_template.breached ? '#b91c1c' : '#059669'}; font-weight: 600;">${r.static_template.breached ? `@ step ${r.static_template.first_success}` : 'HELD'}</span></td>
          <td><span style="color: ${r.adaptive_mutation.breached ? '#b91c1c' : '#059669'}; font-weight: 600;">${r.adaptive_mutation.breached ? `@ step ${r.adaptive_mutation.first_success}` : 'HELD'}</span></td>
        </tr>
      `).join('')}
    </tbody>
  </table>

  <!-- SECTION 5: AUDIT TRAIL & SIGN-OFF -->
  <h2>5. Cryptographic Audit Proof & Sign-Off</h2>
  <p>All pipeline execution events are committed to a tamper-evident hash chain ledger.</p>

  <div style="background-color: #f8fafc; border: 1pt solid #cbd5e1; padding: 10pt; border-radius: 4pt;">
    <strong>Ledger Status:</strong> ${report.ledger.verified ? 'Verified Cryptographic Hash Chain' : 'Unverified'}<br>
    <strong>Total Ledger Blocks:</strong> ${report.ledger.entries}<br>
    <strong>Merkle Head:</strong> <span class="code-box">${report.ledger.head}</span>
  </div>

  <h3 style="margin-top: 14pt;">Human Sign-Off Registry</h3>
  ${report.human_signoff.length > 0 ? `
    <table>
      <thead>
        <tr>
          <th>Approver</th>
          <th>Decision</th>
          <th>Decision ID</th>
          <th>Reviewer Note</th>
        </tr>
      </thead>
      <tbody>
        ${report.human_signoff.map((s) => `
          <tr>
            <td><strong>${s.approver}</strong></td>
            <td style="color: ${s.approved ? '#059669' : '#b91c1c'}; font-weight: 700;">${s.approved ? 'APPROVED' : 'REJECTED'}</td>
            <td><code>${s.decision_id}</code></td>
            <td>${s.note || '(none)'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  ` : '<p><em>No human review signed off yet. Governance review pending.</em></p>'}

</body>
</html>`;

  const blob = new Blob([html], { type: 'application/msword;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${runId}_Verification_Report.doc`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ── Evaluation (Connect-your-RAG-app flow) exports ─────────────── */

function download(content: string, mime: string, filename: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function esc(v: unknown): string {
  return String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function ciText(m: EvalMetric): string {
  if (m.value === null || m.ci_low === null || m.ci_high === null) return `not measured (n=${m.n})`;
  return `${pct(m.value)} (95% CI ${pct(m.ci_low)} to ${pct(m.ci_high)}, n=${m.n})`;
}

/** Build the CSV text (pure, testable). */
export function evaluationCsv(ev: Evaluation): string {
  const lines: string[] = ['﻿Evaluation,' + escapeCsv(ev.id)];
  lines.push(`Synthetic data,${escapeCsv(ev.synthetic ? 'YES: SYNTHETIC DATA' : 'no')}`);
  lines.push(`Verdict,${escapeCsv(ev.decision?.verdict ?? 'none')}`);
  (ev.decision?.reasons ?? []).forEach((r) => lines.push(`Reason,${escapeCsv(r)}`));
  lines.push('');
  lines.push('Metric,Value,CI low,CI high,n,Note');
  Object.entries({ ...ev.metrics, ...(ev.scorecard ?? {}) }).forEach(([name, m]) =>
    lines.push([name, m.value, m.ci_low, m.ci_high, m.n, m.note ?? ''].map(escapeCsv).join(',')));
  lines.push('');
  lines.push('Item,Source,Passed,Failure class,Failure reason,Question,Reference answer,Answer,Contexts');
  ev.items.forEach((i) =>
    lines.push([i.id, i.source, i.passed === null ? 'n/a' : i.passed, i.failure_class ?? '', i.failure_reason ?? '', i.question,
      i.reference_answer ?? '', i.answer ?? '', i.contexts.join(' | ')].map(escapeCsv).join(',')));
  return lines.join('\r\n');
}

export function exportEvaluationCsv(ev: Evaluation) {
  download(evaluationCsv(ev), 'text/csv;charset=utf-8', `${ev.id}_evaluation.csv`);
}

export function exportEvaluationJson(ev: Evaluation) {
  download(JSON.stringify(ev, null, 2), 'application/json', `${ev.id}_evaluation.json`);
}

export function exportEvaluationDoc(ev: Evaluation) {
  const rows = Object.entries({ ...ev.metrics, ...(ev.scorecard ?? {}) })
    .map(([k, m]) => `<tr><td>${esc(k)}</td><td>${esc(ciText(m))}</td><td>${esc(m.note ?? '')}</td></tr>`).join('');
  const failed = ev.items.filter((i) => i.passed === false);
  const html = `<html><head><meta charset="utf-8"><title>${esc(ev.id)}</title></head><body style="font-family:Calibri,Arial,sans-serif">
<h1>Evaluation ${esc(ev.id)}</h1>
${ev.synthetic ? '<p style="color:#92400e"><strong>SYNTHETIC DATA</strong>: not a real-world measurement.</p>' : ''}
<h2>Verdict: ${esc(ev.decision?.verdict ?? 'none')}</h2>
<ul>${(ev.decision?.reasons ?? []).map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
<h2>Metrics</h2><table border="1" cellpadding="4"><tr><th>Metric</th><th>Value with 95% interval</th><th>Note</th></tr>${rows}</table>
<h2>Failures (${failed.length} of ${ev.items.length})</h2>
${failed.map((i) => `<h3>${esc(i.id)} (${esc(i.source)})</h3><p><b>Q:</b> ${esc(i.question)}</p><p><b>A:</b> ${esc(i.answer)}</p><p><b>Why failed:</b> ${esc(i.failure_reason)}</p>`).join('')}
</body></html>`;
  download(html, 'application/msword;charset=utf-8', `${ev.id}_evaluation.doc`);
}

export function downloadText(content: string, filename: string, mime = 'text/plain;charset=utf-8') {
  download(content, mime, filename);
}
