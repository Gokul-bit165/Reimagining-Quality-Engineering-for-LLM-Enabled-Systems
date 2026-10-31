import React from 'react';
import type { Rate } from '../types/api';
import { pct } from './IntervalBar';

interface MiniBarProps {
  rate: Rate;
}

export const MiniBar: React.FC<MiniBarProps> = ({ rate }) => {
  const W = 220;
  const pad = 4;
  const x = (v: number) => pad + v * (W - 2 * pad);

  const titleText = `Failure rate ${pct(rate.point)}, 95% interval ${pct(rate.lower)} to ${pct(rate.upper)}`;

  return (
    <svg viewBox={`0 0 ${W} 20`} className="mini" role="img" aria-label={titleText}>
      <title>{titleText}</title>
      <line className="axis" x1={pad} x2={W - pad} y1={10} y2={10} />
      <rect
        className="range"
        x={x(rate.lower)}
        y={5}
        width={Math.max(2, x(rate.upper) - x(rate.lower))}
        height={10}
      />
      <circle className="point" cx={x(rate.point)} cy={10} r={3.5} />
    </svg>
  );
};

