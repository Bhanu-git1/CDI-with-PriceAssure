import React, { useState, useMemo, useRef } from 'react';

// Curated harmonious color palette matching modern commercial intelligence themes
const PALETTE = [
  '#0176d3', '#00a1e0', '#8b5cf6', '#10b981', '#f59e0b',
  '#ec4899', '#3b82f6', '#6366f1', '#14b8a6', '#f97316',
  '#84cc16', '#a855f7', '#06b6d4', '#e11d48', '#d97706',
  '#059669', '#4f46e5', '#7c3aed', '#db2777', '#2563eb'
];

export default function DataChart({ data, userPrompt = '' }) {
  // Determine default chart type based on user prompt (e.g. "show me as pie chart")
  const defaultChartType = useMemo(() => {
    const p = (userPrompt || '').toLowerCase();
    if (p.includes('pie') || p.includes('donut')) return 'pie';
    if (p.includes('bar')) return 'bar';
    return 'pie'; // Default to Pie chart for distribution breakdowns
  }, [userPrompt]);

  const [chartType, setChartType] = useState(defaultChartType); // 'pie' | 'donut' | 'bar'
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [selectedLabelCol, setSelectedLabelCol] = useState('');
  const [selectedValueCol, setSelectedValueCol] = useState('');
  const [downloading, setDownloading] = useState(false);

  const svgRef = useRef(null);

  // Column identification & configuration
  const columnsInfo = useMemo(() => {
    if (!data || !Array.isArray(data) || data.length === 0) return { labelCols: [], numCols: [] };

    const firstRow = data[0];
    const keys = Object.keys(firstRow);
    const labelCols = [];
    const numCols = [];

    keys.forEach((key) => {
      const val = firstRow[key];
      const isNumeric = typeof val === 'number' || (!isNaN(parseFloat(val)) && isFinite(val));
      if (isNumeric && key.toLowerCase() !== 'id') {
        numCols.push(key);
      } else {
        labelCols.push(key);
      }
    });

    if (numCols.length === 0 && keys.length > 0) {
      numCols.push(keys[keys.length - 1]);
    }
    if (labelCols.length === 0 && keys.length > 0) {
      labelCols.push(keys[0]);
    }

    return { labelCols, numCols };
  }, [data]);

  const activeLabelCol = selectedLabelCol || columnsInfo.labelCols[0] || Object.keys(data?.[0] || {})[0] || 'Category';
  const activeValueCol = selectedValueCol || columnsInfo.numCols[0] || Object.keys(data?.[0] || {})[1] || 'Value';

  // Process data points and aggregate if necessary
  const chartData = useMemo(() => {
    if (!data || !Array.isArray(data) || data.length === 0) return { points: [], totalValue: 0 };

    // Group / map points
    const pointsMap = new Map();
    data.forEach((row) => {
      const label = String(row[activeLabelCol] != null ? row[activeLabelCol] : 'Unknown').trim() || 'Unknown';
      const rawVal = row[activeValueCol];
      const numVal = parseFloat(rawVal) || 0;

      if (pointsMap.has(label)) {
        pointsMap.set(label, pointsMap.get(label) + numVal);
      } else {
        pointsMap.set(label, numVal);
      }
    });

    // Sort descending by value
    let points = Array.from(pointsMap.entries()).map(([label, value], idx) => ({
      label,
      value: Math.max(0, value),
      color: PALETTE[idx % PALETTE.length]
    })).sort((a, b) => b.value - a.value);

    // If more than 10 categories, group smaller tail into "Other"
    const maxSlices = 9;
    if (points.length > maxSlices) {
      const topSlices = points.slice(0, maxSlices);
      const otherValue = points.slice(maxSlices).reduce((sum, p) => sum + p.value, 0);
      if (otherValue > 0) {
        topSlices.push({
          label: 'Other',
          value: otherValue,
          color: '#94a3b8'
        });
      }
      points = topSlices;
    }

    const totalValue = points.reduce((sum, p) => sum + p.value, 0);

    // Calculate angles & percentages
    let currentAngle = -Math.PI / 2; // Start from top (12 o'clock)
    const pointsWithAngles = points.map((p) => {
      const percentage = totalValue > 0 ? (p.value / totalValue) * 100 : 0;
      const angleSpan = totalValue > 0 ? (p.value / totalValue) * 2 * Math.PI : 0;
      const startAngle = currentAngle;
      const endAngle = currentAngle + angleSpan;
      const middleAngle = startAngle + angleSpan / 2;
      currentAngle = endAngle;

      return {
        ...p,
        percentage,
        startAngle,
        endAngle,
        middleAngle
      };
    });

    return {
      points: pointsWithAngles,
      totalValue,
      maxVal: Math.max(...points.map((p) => p.value), 1)
    };
  }, [data, activeLabelCol, activeValueCol]);

  // SVG dimensions for Pie & Donut
  const size = 320;
  const center = size / 2;
  const radius = size * 0.42;
  const innerRadius = chartType === 'donut' ? radius * 0.58 : 0;

  // Helper to generate SVG pie/donut slice arc path
  const getSlicePath = (point, isHovered) => {
    const { startAngle, endAngle, middleAngle } = point;
    // Explode slice outward slightly when hovered
    const offset = isHovered ? 8 : 0;
    const offsetX = Math.cos(middleAngle) * offset;
    const offsetY = Math.sin(middleAngle) * offset;

    const cx = center + offsetX;
    const cy = center + offsetY;

    // Handle full circle 100% case
    if (endAngle - startAngle >= 2 * Math.PI - 0.001) {
      if (chartType === 'donut') {
        return `M ${cx} ${cy - radius} A ${radius} ${radius} 0 1 0 ${cx} ${cy + radius} A ${radius} ${radius} 0 1 0 ${cx} ${cy - radius} M ${cx} ${cy - innerRadius} A ${innerRadius} ${innerRadius} 0 1 1 ${cx} ${cy + innerRadius} A ${innerRadius} ${innerRadius} 0 1 1 ${cx} ${cy - innerRadius} Z`;
      }
      return `M ${cx} ${cy - radius} A ${radius} ${radius} 0 1 0 ${cx} ${cy + radius} A ${radius} ${radius} 0 1 0 ${cx} ${cy - radius} Z`;
    }

    const x1 = cx + radius * Math.cos(startAngle);
    const y1 = cy + radius * Math.sin(startAngle);
    const x2 = cx + radius * Math.cos(endAngle);
    const y2 = cy + radius * Math.sin(endAngle);

    const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;

    if (chartType === 'donut') {
      const ix1 = cx + innerRadius * Math.cos(endAngle);
      const iy1 = cy + innerRadius * Math.sin(endAngle);
      const ix2 = cx + innerRadius * Math.cos(startAngle);
      const iy2 = cy + innerRadius * Math.sin(startAngle);

      return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} L ${ix1} ${iy1} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${ix2} ${iy2} Z`;
    }

    return `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`;
  };

  // Download chart as high-resolution PNG image
  const handleDownloadPng = () => {
    setDownloading(true);
    try {
      const width = 850;
      const height = 560;
      const canvas = document.createElement('canvas');
      canvas.width = width * 2; // 2x for sharp retina rendering
      canvas.height = height * 2;
      const ctx = canvas.getContext('2d');
      ctx.scale(2, 2);

      // Background
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);

      // Header border & title
      ctx.fillStyle = '#0f172a';
      ctx.font = 'bold 18px Inter, system-ui, sans-serif';
      ctx.fillText(`${activeValueCol} by ${activeLabelCol}`, 32, 40);

      ctx.fillStyle = '#64748b';
      ctx.font = '12px Inter, system-ui, sans-serif';
      ctx.fillText(`Total: ${chartData.totalValue.toLocaleString()} | Mode: ${chartType.toUpperCase()} CHART`, 32, 60);

      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(32, 75);
      ctx.lineTo(width - 32, 75);
      ctx.stroke();

      if (chartType === 'bar') {
        // Render Bar Chart to Canvas
        const barStartX = 240;
        const barWidth = width - barStartX - 100;
        const rowHeight = 36;
        const startY = 105;

        chartData.points.forEach((p, idx) => {
          const y = startY + idx * rowHeight;
          const pct = chartData.maxVal > 0 ? p.value / chartData.maxVal : 0;
          const currentBarW = Math.max(4, pct * barWidth);

          // Label
          ctx.fillStyle = '#334155';
          ctx.font = '500 12px Inter, system-ui, sans-serif';
          ctx.textAlign = 'right';
          const truncatedLabel = p.label.length > 26 ? p.label.substring(0, 24) + '...' : p.label;
          ctx.fillText(truncatedLabel, barStartX - 14, y + 14);

          // Track
          ctx.fillStyle = '#f1f5f9';
          ctx.beginPath();
          ctx.roundRect(barStartX, y, barWidth, 18, 4);
          ctx.fill();

          // Bar
          ctx.fillStyle = p.color;
          ctx.beginPath();
          ctx.roundRect(barStartX, y, currentBarW, 18, 4);
          ctx.fill();

          // Value
          ctx.textAlign = 'left';
          ctx.fillStyle = '#0f172a';
          ctx.font = '600 11px monospace';
          ctx.fillText(`${p.value.toLocaleString()} (${p.percentage.toFixed(1)}%)`, barStartX + currentBarW + 8, y + 14);
        });
      } else {
        // Render Pie / Donut to Canvas
        const pieCenterX = 230;
        const pieCenterY = 285;
        const pieRadius = 150;
        const pieInnerR = chartType === 'donut' ? pieRadius * 0.58 : 0;

        // Draw Slices
        chartData.points.forEach((p) => {
          ctx.beginPath();
          ctx.fillStyle = p.color;
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2;

          if (chartType === 'donut') {
            ctx.arc(pieCenterX, pieCenterY, pieRadius, p.startAngle, p.endAngle, false);
            ctx.arc(pieCenterX, pieCenterY, pieInnerR, p.endAngle, p.startAngle, true);
          } else {
            ctx.moveTo(pieCenterX, pieCenterY);
            ctx.arc(pieCenterX, pieCenterY, pieRadius, p.startAngle, p.endAngle, false);
          }
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
        });

        // Center Donut text
        if (chartType === 'donut') {
          ctx.fillStyle = '#0f172a';
          ctx.font = 'bold 20px Inter, system-ui, sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(chartData.totalValue.toLocaleString(), pieCenterX, pieCenterY + 4);
          ctx.fillStyle = '#64748b';
          ctx.font = '10px Inter, system-ui, sans-serif';
          ctx.fillText('TOTAL', pieCenterX, pieCenterY + 20);
        }

        // Legend on right
        const legendStartX = 460;
        const legendStartY = 110;
        const legendRowH = 34;

        chartData.points.forEach((p, idx) => {
          const ly = legendStartY + idx * legendRowH;

          // Color Swatch
          ctx.fillStyle = p.color;
          ctx.beginPath();
          ctx.roundRect(legendStartX, ly + 2, 14, 14, 3);
          ctx.fill();

          // Label
          ctx.textAlign = 'left';
          ctx.fillStyle = '#1e293b';
          ctx.font = '600 12px Inter, system-ui, sans-serif';
          const labelText = p.label.length > 24 ? p.label.substring(0, 22) + '...' : p.label;
          ctx.fillText(labelText, legendStartX + 22, ly + 14);

          // Value & Pct
          ctx.textAlign = 'right';
          ctx.fillStyle = '#64748b';
          ctx.font = '500 11px monospace';
          ctx.fillText(`${p.value.toLocaleString()} (${p.percentage.toFixed(1)}%)`, width - 36, ly + 14);
        });
      }

      // Footer
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px Inter, system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText('Generated by Commercial Decision Intelligence Platform', 32, height - 18);

      // Trigger download
      const pngUrl = canvas.toDataURL('image/png');
      const a = document.createElement('a');
      a.href = pngUrl;
      a.download = `pie_chart_${activeLabelCol.toLowerCase()}_${Date.now()}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      console.error('Failed to export chart image:', err);
    } finally {
      setDownloading(false);
    }
  };

  // Download SVG file
  const handleDownloadSvg = () => {
    if (!svgRef.current) return;
    try {
      const svgText = new XMLSerializer().serializeToString(svgRef.current);
      const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pie_chart_${activeLabelCol.toLowerCase()}_${Date.now()}.svg`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export SVG:', err);
    }
  };

  if (!data || !Array.isArray(data) || data.length === 0 || chartData.points.length === 0) {
    return (
      <div className="chart-empty-state">
        <span>⚠️ Insufficient numeric data to generate a chart.</span>
      </div>
    );
  }

  const activeHoveredPoint = hoveredIndex !== null ? chartData.points[hoveredIndex] : null;

  return (
    <div className="data-chart-wrapper">
      {/* Top Controls Bar */}
      <div className="data-chart-header">
        <div className="data-chart-type-picker">
          <button
            type="button"
            className={`chart-type-btn ${chartType === 'pie' ? 'active' : ''}`}
            onClick={() => setChartType('pie')}
            title="Switch to Pie Chart"
          >
            🥧 Pie Chart
          </button>
          <button
            type="button"
            className={`chart-type-btn ${chartType === 'donut' ? 'active' : ''}`}
            onClick={() => setChartType('donut')}
            title="Switch to Donut Chart"
          >
            🍩 Donut
          </button>
          <button
            type="button"
            className={`chart-type-btn ${chartType === 'bar' ? 'active' : ''}`}
            onClick={() => setChartType('bar')}
            title="Switch to Bar Chart"
          >
            📊 Bar Chart
          </button>
        </div>

        {/* Column Pickers if multiple columns exist */}
        <div className="data-chart-selectors">
          {columnsInfo.labelCols.length > 1 && (
            <div className="chart-select-group">
              <label>Category:</label>
              <select value={activeLabelCol} onChange={(e) => setSelectedLabelCol(e.target.value)}>
                {columnsInfo.labelCols.map((col) => (
                  <option key={col} value={col}>{col}</option>
                ))}
              </select>
            </div>
          )}

          {columnsInfo.numCols.length > 1 && (
            <div className="chart-select-group">
              <label>Metric:</label>
              <select value={activeValueCol} onChange={(e) => setSelectedValueCol(e.target.value)}>
                {columnsInfo.numCols.map((col) => (
                  <option key={col} value={col}>{col}</option>
                ))}
              </select>
            </div>
          )}

          {/* Download Action Buttons */}
          <div className="chart-download-actions">
            <button
              type="button"
              className="chart-download-btn primary"
              onClick={handleDownloadPng}
              disabled={downloading}
              title="Save chart as PNG image to your computer"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              <span>{downloading ? 'Saving...' : 'Download PNG'}</span>
            </button>

            <button
              type="button"
              className="chart-download-btn secondary"
              onClick={handleDownloadSvg}
              title="Save chart as SVG vector file"
            >
              SVG
            </button>
          </div>
        </div>
      </div>

      {/* Main Chart Body */}
      <div className="data-chart-body">
        {chartType === 'bar' ? (
          /* Bar Chart View */
          <div className="chart-bar-container">
            <div className="chart-title-sub">
              <strong>{activeValueCol}</strong> grouped by <strong>{activeLabelCol}</strong>
            </div>
            <div className="chart-bar-list">
              {chartData.points.map((p, idx) => {
                const fillPct = chartData.maxVal > 0 ? (p.value / chartData.maxVal) * 100 : 0;
                return (
                  <div
                    key={idx}
                    className={`chart-bar-item ${hoveredIndex === idx ? 'highlight' : ''}`}
                    onMouseEnter={() => setHoveredIndex(idx)}
                    onMouseLeave={() => setHoveredIndex(null)}
                  >
                    <div className="chart-bar-label-line">
                      <span className="chart-bar-name" title={p.label}>{p.label}</span>
                      <span className="chart-bar-num">
                        {p.value.toLocaleString()} <small>({p.percentage.toFixed(1)}%)</small>
                      </span>
                    </div>
                    <div className="chart-bar-track">
                      <div
                        className="chart-bar-fill"
                        style={{ width: `${fillPct}%`, backgroundColor: p.color }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          /* Pie / Donut Chart View */
          <div className="chart-pie-layout">
            {/* SVG Pie graphic */}
            <div className="chart-svg-pane">
              <svg
                ref={svgRef}
                viewBox={`0 0 ${size} ${size}`}
                width={size}
                height={size}
                className="chart-pie-svg"
              >
                {/* Render Pie Slices */}
                {chartData.points.map((point, idx) => {
                  const isHovered = hoveredIndex === idx;
                  return (
                    <path
                      key={idx}
                      d={getSlicePath(point, isHovered)}
                      fill={point.color}
                      stroke="#ffffff"
                      strokeWidth="2"
                      className="pie-slice-path"
                      style={{
                        transition: 'transform 0.2s ease, opacity 0.2s ease',
                        cursor: 'pointer',
                        opacity: hoveredIndex !== null && !isHovered ? 0.6 : 1
                      }}
                      onMouseEnter={() => setHoveredIndex(idx)}
                      onMouseLeave={() => setHoveredIndex(null)}
                    />
                  );
                })}

                {/* Donut Center Hole Text */}
                {chartType === 'donut' && (
                  <g className="donut-center-group">
                    <circle cx={center} cy={center} r={innerRadius - 1} fill="#ffffff" />
                    <text
                      x={center}
                      y={activeHoveredPoint ? center - 6 : center + 2}
                      textAnchor="middle"
                      className="donut-total-val"
                      fill="#0f172a"
                      fontWeight="700"
                      fontSize="18"
                    >
                      {activeHoveredPoint
                        ? activeHoveredPoint.value.toLocaleString()
                        : chartData.totalValue.toLocaleString()}
                    </text>
                    <text
                      x={center}
                      y={activeHoveredPoint ? center + 14 : center + 20}
                      textAnchor="middle"
                      className="donut-total-label"
                      fill="#64748b"
                      fontSize="10"
                      fontWeight="600"
                    >
                      {activeHoveredPoint
                        ? `${activeHoveredPoint.percentage.toFixed(1)}%`
                        : 'TOTAL'}
                    </text>
                  </g>
                )}
              </svg>

              {/* Floating Tooltip if hovering a slice */}
              {activeHoveredPoint && (
                <div className="pie-slice-tooltip">
                  <div className="tooltip-color-dot" style={{ backgroundColor: activeHoveredPoint.color }} />
                  <div className="tooltip-content">
                    <div className="tooltip-title">{activeHoveredPoint.label}</div>
                    <div className="tooltip-val">
                      {activeHoveredPoint.value.toLocaleString()} ({activeHoveredPoint.percentage.toFixed(1)}%)
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Legend List */}
            <div className="chart-legend-pane">
              <div className="chart-legend-title">
                <span>Category Breakdown ({chartData.points.length})</span>
                <span className="chart-legend-total">Total: {chartData.totalValue.toLocaleString()}</span>
              </div>
              <div className="chart-legend-list">
                {chartData.points.map((point, idx) => (
                  <div
                    key={idx}
                    className={`legend-item ${hoveredIndex === idx ? 'hovered' : ''}`}
                    onMouseEnter={() => setHoveredIndex(idx)}
                    onMouseLeave={() => setHoveredIndex(null)}
                  >
                    <span className="legend-dot" style={{ backgroundColor: point.color }} />
                    <span className="legend-name" title={point.label}>{point.label}</span>
                    <span className="legend-pct">{point.percentage.toFixed(1)}%</span>
                    <span className="legend-val">{point.value.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
