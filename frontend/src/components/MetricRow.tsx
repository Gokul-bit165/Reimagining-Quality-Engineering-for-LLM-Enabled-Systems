import React from 'react';
import type { Metric } from '../types/api';
import { IntervalBar, pct } from './IntervalBar';
import { FailureExamples } from './FailureExamples';

interface MetricRowProps {
  metric: Metric;
}

const STATUS_TEXT: Record<string, string> = {
  within: 'Whole interval is within the appetite.',
  above: 'Whole interval is above the appetite.',
  straddles: 'Interval straddles the appetite: the evidence cannot settle it.',
  no_appetite: 'The policy sets no appetite for this metric.',
};

export const MetricRow: React.FC<MetricRowProps> = ({ metric: m }) => {
  const rate = m.failure_rate;

  return (
    <div className="metric">
      <div className="metric-head">
        <span className="metric-name mono">{m.metric}</span>
        <span className="metric-counts">
          {`${m.failed_cases} failed · ${m.passed_cases} passed · ${m.not_evaluable_cases} not evaluable`}
        </span>
      </div>

      {!rate ? (
        <p className="empty">No evaluable cases: interval unavailable.</p>
      ) : (
        <>
          <IntervalBar rate={rate} appetite={m.appetite} />
          <p className="metric-read">
            {`${rate.k} of ${rate.n} evaluable cases failed; ${rate.confidence * 100}% interval ` +
              `${pct(rate.lower)} to ${pct(rate.upper)} (${rate.method.replace('_', '-')}). ${
                m.status ? (STATUS_TEXT[m.status] ?? '') : ''
              }`}
          </p>
        </>
      )}

      <FailureExamples failures={m.failures} />
    </div>
  );
};

