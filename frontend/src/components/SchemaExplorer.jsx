import React, { useMemo, useState } from 'react';

export default function SchemaExplorer({ schemaText, loading }) {
  const [expandedObject, setExpandedObject] = useState(null);

  // Parse schema string into structured table objects
  const dbTables = useMemo(() => {
    if (!schemaText) return [];
    
    const parsedTables = [];
    const lines = schemaText.split('\n');
    
    for (const line of lines) {
      const match = line.match(/^Table '(.+?)' \((\d+) rows?\): \[(.+?)\]$/);
      if (match) {
        const tableName = match[1];
        const rowCount = parseInt(match[2], 10);
        const fieldsRaw = match[3];
        
        const fields = fieldsRaw.split(', ').map(fieldStr => {
          if (fieldStr.startsWith('...')) {
            return { name: fieldStr, type: '', isOverflow: true };
          }
          const fieldParts = fieldStr.match(/^(.+?) \((.+?)\)$/);
          if (fieldParts) {
            return { name: fieldParts[1], type: fieldParts[2] };
          }
          return { name: fieldStr, type: 'unknown' };
        });
        
        parsedTables.push({
          name: tableName,
          label: `${rowCount} rows`,
          fields,
        });
      }
    }
    
    return parsedTables.sort((a, b) => a.name.localeCompare(b.name));
  }, [schemaText]);

  const toggleExpand = (tableName) => {
    if (expandedObject === tableName) {
      setExpandedObject(null);
    } else {
      setExpandedObject(tableName);
    }
  };

  const getTypeColor = (type) => {
    const lower = type.toLowerCase();
    if (lower.startsWith('int') || lower.startsWith('bigint') || lower.startsWith('smallint') || lower.startsWith('tinyint')) return '#34d399';
    if (lower.startsWith('decimal') || lower.startsWith('float') || lower.startsWith('double')) return '#34d399';
    if (lower.startsWith('date') || lower.startsWith('timestamp') || lower.startsWith('datetime')) return '#fbbf24';
    if (lower.startsWith('bool') || lower.startsWith('tinyint(1)')) return '#60a5fa';
    if (lower.startsWith('enum') || lower.startsWith('set')) return '#fb923c';
    if (lower.startsWith('varchar') || lower.startsWith('text') || lower.startsWith('char')) return '#e879f9';
    return 'var(--accent-secondary)';
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <path d="M8 12l2 2 4-4"/>
        </svg>
        <h2>DATABASE TABLES</h2>
      </div>
      
      <div className="schema-list">
        {loading ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '20px' }}>
            Reading Database Schema...
          </div>
        ) : dbTables.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '20px' }}>
            No tables discovered. Check MySQL connection.
          </div>
        ) : (
          dbTables.map((obj) => {
            const isExpanded = expandedObject === obj.name;
            return (
              <div key={obj.name} className="schema-item">
                <div 
                  className="schema-title" 
                  onClick={() => toggleExpand(obj.name)}
                >
                  <span>
                    🗃️ {obj.name}
                    <span style={{ fontSize: '0.7rem', opacity: 0.5, marginLeft: '6px' }}>
                      {obj.label}
                    </span>
                  </span>
                  <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>
                    {isExpanded ? '▼' : '▶'}
                  </span>
                </div>
                
                {isExpanded && (
                  <div className="schema-columns">
                    {obj.fields.map((field, idx) => (
                      <div key={field.name + idx} className="column-info">
                        <span className="column-name">
                          {field.isOverflow ? (
                            <em style={{ opacity: 0.6 }}>{field.name}</em>
                          ) : field.name}
                        </span>
                        {!field.isOverflow && (
                          <span 
                            className="column-type"
                            style={{ color: getTypeColor(field.type) }}
                          >
                            {field.type}
                          </span>
                        )}
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
