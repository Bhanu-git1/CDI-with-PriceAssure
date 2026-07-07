import React, { useMemo, useState } from 'react';

export default function SchemaExplorer({ schemaText, loading }) {
  const [expandedTable, setExpandedTable] = useState(null);

  // Parse schema string into structured objects
  const tables = useMemo(() => {
    if (!schemaText) return [];
    
    const parsedTables = [];
    const lines = schemaText.split('\n');
    
    for (const line of lines) {
      // Look for: Table 'name': [col (type), col (type)]
      const match = line.match(/^Table '(.+?)': \[(.+?)\]$/);
      if (match) {
        const tableName = match[1];
        const columnsRaw = match[2];
        
        // Parse columns e.g. "id (int), name (varchar)"
        const columns = columnsRaw.split(', ').map(col => {
          const colParts = col.split(' ');
          const name = colParts[0];
          const type = colParts.slice(1).join(' ').replace(/[()]/g, '');
          return { name, type };
        });
        
        parsedTables.push({
          name: tableName,
          columns
        });
      }
    }
    
    // Sort tables alphabetically
    return parsedTables.sort((a, b) => a.name.localeCompare(b.name));
  }, [schemaText]);

  const toggleExpand = (tableName) => {
    if (expandedTable === tableName) {
      setExpandedTable(null);
    } else {
      setExpandedTable(tableName);
    }
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
          <path d="M3 5V19A9 3 0 0 0 21 19V5"></path>
          <path d="M3 12A9 3 0 0 0 21 12"></path>
        </svg>
        <h2>SCHEMA EXPLORER</h2>
      </div>
      
      <div className="schema-list">
        {loading ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '20px' }}>
            Reading Database Schema...
          </div>
        ) : tables.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '20px' }}>
            No tables discovered. Check database connection.
          </div>
        ) : (
          tables.map((table) => {
            const isExpanded = expandedTable === table.name;
            return (
              <div key={table.name} className="schema-item">
                <div 
                  className="schema-title" 
                  onClick={() => toggleExpand(table.name)}
                >
                  <span>📋 {table.name}</span>
                  <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>
                    {isExpanded ? '▼' : '▶'}
                  </span>
                </div>
                
                {isExpanded && (
                  <div className="schema-columns">
                    {table.columns.map((col) => (
                      <div key={col.name} className="column-info">
                        <span className="column-name">{col.name}</span>
                        <span className="column-type">{col.type}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
