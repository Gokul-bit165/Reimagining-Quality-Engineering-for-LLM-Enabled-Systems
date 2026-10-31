import React from 'react';

interface TableProps {
  headers: string[];
  rows: React.ReactNode[][];
  ariaLabel?: string;
}

export const Table: React.FC<TableProps> = ({ headers, rows, ariaLabel = 'table' }) => {
  return (
    <div className="tbl-wrap" tabIndex={0} role="region" aria-label={ariaLabel}>
      <table className="tbl">
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th key={i} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

