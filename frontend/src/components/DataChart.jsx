import React, { useMemo } from 'react';

export default function DataChart({ data }) {
  const chartConfig = useMemo(() => {
    if (!data || !Array.isArray(data) || data.length === 0) return null;

    // Detect numeric and label columns
    const firstRow = data[0];
    const keys = Object.keys(firstRow);
    
    let labelColumn = '';
    let valueColumn = '';

    // Simple heuristic: First string/date column is the label, first numeric column is the value
    for (const key of keys) {
      const val = firstRow[key];
      const isNum = typeof val === 'number' || (!isNaN(parseFloat(val)) && isFinite(val));
      
      if (isNum && !valueColumn && key.toLowerCase() !== 'id') {
        valueColumn = key;
      } else if (!isNum && !labelColumn) {
        labelColumn = key;
      }
    }

    // Fallbacks if heuristics fail
    if (!labelColumn) labelColumn = keys[0];
    if (!valueColumn) {
      // Find any column that isn't the label column
      valueColumn = keys.find(k => k !== labelColumn) || keys[0];
    }

    // Process rows into clean visual components
    const points = data.map((row) => {
      const rawVal = row[valueColumn];
      const numVal = parseFloat(rawVal) || 0;
      return {
        label: String(row[labelColumn] || 'Unknown'),
        value: numVal,
        displayValue: rawVal
      };
    });

    // Find max value to determine percentages
    const maxVal = Math.max(...points.map(p => p.value), 1);

    return {
      points,
      maxVal,
      labelColumn,
      valueColumn
    };
  }, [data]);

  if (!chartConfig || chartConfig.points.length === 0) {
    return <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Insufficient numeric data to plot chart.</div>;
  }

  const { points, maxVal, labelColumn, valueColumn } = chartConfig;

  return (
    <div className="chart-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
        <h4 style={{ fontSize: '0.85rem', fontWeight: '600', color: 'var(--text-secondary)' }}>
          Chart: {valueColumn} by {labelColumn}
        </h4>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Auto-Visualized</span>
      </div>
      
      <div className="custom-bar-chart">
        {points.slice(0, 10).map((point, index) => {
          // Cap at 10 items for readability
          const fillPercentage = Math.min((point.value / maxVal) * 100, 100);
          
          return (
            <div key={index} className="chart-bar-row">
              <div className="bar-label-group">
                <span className="bar-label" style={{ fontWeight: '500' }}>{point.label}</span>
                <span className="bar-value" style={{ fontFamily: 'monospace', color: 'var(--accent-secondary)' }}>
                  {point.displayValue}
                </span>
              </div>
              <div className="bar-track">
                <div 
                  className="bar-fill" 
                  style={{ width: `${fillPercentage}%` }}
                />
              </div>
            </div>
          );
        })}
        {points.length > 10 && (
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '4px' }}>
            + {points.length - 10} more rows (capped at top 10 rows for display)
          </div>
        )}
      </div>
    </div>
  );
}
