import React from 'react';
import type { Rate } from '../types/api';

interface IntervalBarProps {
  rate: Rate;
  appetite: number | null;
}

export const pct = (x: number): string => `${(x * 100).toFixed(1)}%`;

export const IntervalBar: React.FC<IntervalBarProps> = ({ rate, appetite }) => {
  const max = Math.min(1, Math.max(rate.upper, appetite ?? 0) * 1.25 + 0.02);
  const W = 600;
  const pad = 8;
  const x = (v: number) => pad + (v / max) * (W - 2 * pad);

  const titleText = `Failure rate ${pct(rate.point)}, ${rate.confidence * 100}% interval ` +
    `${pct(rate.lower)} to ${pct(rate.upper)}` + (appetite != null ? `; policy appetite ${pct(appetite)}` : '');

  return (
    <svg viewBox={`0 0 ${W} 48`} className="interval" role="img" aria-label={titleText}>
      <title>{titleText}</title>
      <line className="axis" x1={pad} x2={W - pad} y1={30} y2={30} />
      <rect
        className="range"
        x={x(rate.lower)}
        y={22}
        width={Math.max(2, x(rate.upper) - x(rate.lower))}
        height={16}
      />
      <circle className="point" cx={x(rate.point)} cy={30} r={5} />
      {appetite != null && (
        <>
          <line className="appetite" x1={x(appetite)} x2={x(appetite)} y1={12} y2={44} />
          <text className="appetite-label" x={x(appetite) + 4} y={12}>
            {`appetite ${pct(appetite)}`}
          </text>
        </>
      )}
      <text className="tick" x={x(0)} y={47} textAnchor="start">
        {pct(0)}
      </text>
      <text className="tick" x={x(max)} y={47} textAnchor="end">
        {pct(max)}
      </text>
    </svg>
  );
};

