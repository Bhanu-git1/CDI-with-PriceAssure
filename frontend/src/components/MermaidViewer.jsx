import React, { useEffect, useRef, useState, useId } from 'react';
import mermaid from 'mermaid';

// Initialize mermaid once with custom theme settings
mermaid.initialize({
  startOnLoad: false,
  theme: 'neutral',
  securityLevel: 'loose',
  fontFamily: 'inherit',
  er: {
    useMaxWidth: true,
    entityPadding: 15,
    stroke: '#0176d3',
    fill: '#f0f7ff',
    fontSize: 12
  },
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true,
    curve: 'basis'
  }
});

export default function MermaidViewer({ code }) {
  const [svgContent, setSvgContent] = useState('');
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  
  const rawId = useId().replace(/:/g, '_');
  const containerId = `mermaid_${rawId}`;
  const containerRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    setError(null);

    const cleanCode = (code || '').trim();
    if (!cleanCode) return;

    const renderDiagram = async () => {
      try {
        // Clean out any accidental markdown fences if passed raw
        const codeToRender = cleanCode
          .replace(/^```mermaid\s*/i, '')
          .replace(/^```\s*/, '')
          .replace(/```$/, '')
          .trim();

        const uniqueRenderId = `mermaid_svg_${rawId}_${Date.now()}`;
        const { svg } = await mermaid.render(uniqueRenderId, codeToRender);
        
        if (isMounted) {
          setSvgContent(svg);
          setError(null);
        }
      } catch (err) {
        console.error('Mermaid render error:', err);
        if (isMounted) {
          setError(err.message || 'Could not parse diagram syntax');
        }
      }
    };

    renderDiagram();

    return () => {
      isMounted = false;
    };
  }, [code, rawId]);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadSvg = () => {
    if (!svgContent) return;
    const blob = new Blob([svgContent], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `diagram_${Date.now()}.svg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleZoomIn = () => setZoom((z) => Math.min(z + 0.2, 2.5));
  const handleZoomOut = () => setZoom((z) => Math.max(z - 0.2, 0.4));
  const handleResetZoom = () => setZoom(1);

  if (error) {
    return (
      <div className="mermaid-error-container">
        <div className="mermaid-error-header">
          <span>⚠️ Diagram Rendering Error</span>
          <button onClick={handleCopy} className="mermaid-btn-sm">
            {copied ? 'Copied' : 'Copy Code'}
          </button>
        </div>
        <pre className="mermaid-raw-code">{code}</pre>
        <div className="mermaid-error-detail">{error}</div>
      </div>
    );
  }

  return (
    <div className={`mermaid-wrapper ${isFullscreen ? 'mermaid-fullscreen' : ''}`}>
      {/* Diagram Toolbar */}
      <div className="mermaid-toolbar">
        <div className="mermaid-toolbar-left">
          <span className="mermaid-badge">📐 Visual Diagram</span>
        </div>
        <div className="mermaid-toolbar-right">
          <div className="mermaid-zoom-controls">
            <button
              type="button"
              className="mermaid-btn"
              onClick={handleZoomOut}
              title="Zoom Out"
            >
              −
            </button>
            <button
              type="button"
              className="mermaid-btn zoom-indicator"
              onClick={handleResetZoom}
              title="Reset Zoom"
            >
              {Math.round(zoom * 100)}%
            </button>
            <button
              type="button"
              className="mermaid-btn"
              onClick={handleZoomIn}
              title="Zoom In"
            >
              +
            </button>
          </div>

          <button
            type="button"
            className="mermaid-btn"
            onClick={handleDownloadSvg}
            title="Download SVG Diagram"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            SVG
          </button>

          <button
            type="button"
            className="mermaid-btn"
            onClick={handleCopy}
            title="Copy Diagram Definition"
          >
            {copied ? '✓ Copied' : '📋 Copy'}
          </button>

          <button
            type="button"
            className="mermaid-btn"
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? '✕ Close' : '⛶ Fullscreen'}
          </button>
        </div>
      </div>

      {/* Rendered SVG Canvas */}
      <div className="mermaid-canvas-scroll" ref={containerRef}>
        <div
          id={containerId}
          className="mermaid-svg-container"
          style={{ transform: `scale(${zoom})`, transformOrigin: 'top center' }}
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
      </div>
    </div>
  );
}
