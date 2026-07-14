import React, { useMemo, useState } from 'react';

export default function SchemaExplorer({ schemaText, loading }) {
  const [expandedObject, setExpandedObject] = useState(null);

  // Parse Salesforce schema string into structured objects
  const sfObjects = useMemo(() => {
    if (!schemaText) return [];
    
    const parsedObjects = [];
    const lines = schemaText.split('\n');
    
    for (const line of lines) {
      // Match Salesforce schema format:
      // Object 'ObjectName' (Label: 'Label'): [field1 (type), field2 (type)]
      const match = line.match(/^Object '(.+?)' \(Label: '(.+?)'\): \[(.+?)\]$/);
      if (match) {
        const objectName = match[1];
        const objectLabel = match[2];
        const fieldsRaw = match[3];
        
        // Parse fields e.g. "Id (id), Name (string), Amount (currency)"
        const fields = fieldsRaw.split(', ').map(fieldStr => {
          // Handle "... +N more fields" suffix
          if (fieldStr.startsWith('...')) {
            return { name: fieldStr, type: '', isOverflow: true };
          }
          const fieldParts = fieldStr.match(/^(.+?) \((.+?)\)$/);
          if (fieldParts) {
            return { name: fieldParts[1], type: fieldParts[2] };
          }
          return { name: fieldStr, type: 'unknown' };
        });
        
        parsedObjects.push({
          name: objectName,
          label: objectLabel,
          fields,
          isCustom: objectName.endsWith('__c')
        });
      }
    }
    
    // Sort: standard objects first, then custom objects, both alphabetically
    return parsedObjects.sort((a, b) => {
      if (a.isCustom !== b.isCustom) return a.isCustom ? 1 : -1;
      return a.name.localeCompare(b.name);
    });
  }, [schemaText]);

  const toggleExpand = (objectName) => {
    if (expandedObject === objectName) {
      setExpandedObject(null);
    } else {
      setExpandedObject(objectName);
    }
  };

  // Map Salesforce field types to color-coded badges
  const getTypeColor = (type) => {
    if (type.startsWith('reference')) return '#e879f9'; // purple for lookups
    if (['currency', 'double', 'int', 'percent'].includes(type)) return '#34d399'; // green for numbers
    if (['date', 'datetime'].includes(type)) return '#fbbf24'; // amber for dates
    if (['boolean'].includes(type)) return '#60a5fa'; // blue for booleans
    if (type.startsWith('picklist')) return '#fb923c'; // orange for picklists
    return 'var(--accent-secondary)'; // default
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <path d="M8 12l2 2 4-4"/>
        </svg>
        <h2>SALESFORCE OBJECTS</h2>
      </div>
      
      <div className="schema-list">
        {loading ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '20px' }}>
            Reading Salesforce Schema...
          </div>
        ) : sfObjects.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '20px' }}>
            No objects discovered. Check Salesforce connection.
          </div>
        ) : (
          sfObjects.map((obj) => {
            const isExpanded = expandedObject === obj.name;
            return (
              <div key={obj.name} className="schema-item">
                <div 
                  className="schema-title" 
                  onClick={() => toggleExpand(obj.name)}
                >
                  <span>
                    {obj.isCustom ? '🔧' : '☁️'} {obj.name}
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
