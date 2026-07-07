import React from 'react';

export default function DataTable({ data }) {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No tabular results available.</div>;
  }

  // Get table column headers dynamically from object keys
  const headers = Object.keys(data[0]);

  return (
    <div style={{ overflowX: 'auto', width: '100%' }}>
      <table className="custom-table">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <tr key={index}>
              {headers.map((header) => (
                <td key={header}>
                  {row[header] === null || row[header] === undefined 
                    ? <em style={{ color: 'var(--text-muted)' }}>null</em> 
                    : String(row[header])
                  }
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: '8px', fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'right' }}>
        Showing {data.length} row(s)
      </div>
    </div>
  );
}
