import React from 'react';

interface FactsProps {
  rows: [string, React.ReactNode][];
}

export const Facts: React.FC<FactsProps> = ({ rows }) => {
  return (
    <dl className="facts">
      {rows.map(([k, v], i) => (
        <React.Fragment key={i}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
};

