import React from 'react';
import type { Failure } from '../types/api';

interface FailureExamplesProps {
  failures: Failure[];
}

export const FailureExamples: React.FC<FailureExamplesProps> = ({ failures }) => {
  if (!failures?.length) return null;

  return (
    <details className="examples">
      <summary>{`${failures.length} failing case(s) with evidence`}</summary>
      {failures.map((f, i) => (
        <div key={f.case_id || i} className="example">
          <p>
            <strong>Test: </strong>
            {f.question ?? '(unknown)'}
          </p>
          <p>
            <strong>Expected: </strong>
            {f.expected ?? '(none)'}
          </p>
          <p>
            <strong>Observed: </strong>
            {f.output || '(empty)'}
          </p>
          <p className="metric-read">
            {`${f.state}${f.detail ? ` · ${f.detail}` : ''} · evidence `}
            <code>{f.evidence_key.slice(0, 40) + '…'}</code>
          </p>
        </div>
      ))}
    </details>
  );
};

