import React, { useState, useMemo } from 'react';
import * as XLSX from 'xlsx';
import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';

export default function DataTable({ data }) {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: '12px 0' }}>
        No tabular results available.
      </div>
    );
  }

  // Column headers
  const headers = useMemo(() => {
    return Object.keys(data[0] || {});
  }, [data]);

  // States: Sort, Search, Pagination
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });
  const [searchTerm, setSearchTerm] = useState('');
  const [pageSize, setPageSize] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  const [isExporting, setIsExporting] = useState(false);

  // Sorting handler
  const handleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        if (prev.direction === 'asc') return { key, direction: 'desc' };
        if (prev.direction === 'desc') return { key: null, direction: 'asc' };
      }
      return { key, direction: 'asc' };
    });
    setCurrentPage(1);
  };

  // Filter & Sort data
  const filteredSortedData = useMemo(() => {
    let result = [...data];

    // Filter
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      result = result.filter((row) =>
        headers.some((h) => {
          const val = row[h];
          return val !== null && val !== undefined && String(val).toLowerCase().includes(q);
        })
      );
    }

    // Sort
    if (sortConfig.key) {
      const { key, direction } = sortConfig;
      result.sort((a, b) => {
        let valA = a[key];
        let valB = b[key];

        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;

        // Numeric compare
        const numA = Number(valA);
        const numB = Number(valB);
        const isNumA = !isNaN(numA) && typeof valA !== 'boolean' && String(valA).trim() !== '';
        const isNumB = !isNaN(numB) && typeof valB !== 'boolean' && String(valB).trim() !== '';

        if (isNumA && isNumB) {
          return direction === 'asc' ? numA - numB : numB - numA;
        }

        // Date compare
        const dateA = Date.parse(valA);
        const dateB = Date.parse(valB);
        if (!isNaN(dateA) && !isNaN(dateB) && typeof valA === 'string' && valA.length >= 8) {
          return direction === 'asc' ? dateA - dateB : dateB - dateA;
        }

        // String compare
        const strA = String(valA).toLowerCase();
        const strB = String(valB).toLowerCase();
        return direction === 'asc' ? strA.localeCompare(strB) : strB.localeCompare(strA);
      });
    }

    return result;
  }, [data, headers, searchTerm, sortConfig]);

  // Pagination calculation
  const totalRows = filteredSortedData.length;
  const effectivePageSize = pageSize === 'all' ? totalRows : Number(pageSize);
  const totalPages = effectivePageSize > 0 ? Math.ceil(totalRows / effectivePageSize) : 1;
  const validPage = Math.min(Math.max(1, currentPage), Math.max(1, totalPages));

  const paginatedData = useMemo(() => {
    if (pageSize === 'all') return filteredSortedData;
    const start = (validPage - 1) * effectivePageSize;
    return filteredSortedData.slice(start, start + effectivePageSize);
  }, [filteredSortedData, validPage, effectivePageSize, pageSize]);

  const startIndex = totalRows === 0 ? 0 : (validPage - 1) * effectivePageSize + 1;
  const endIndex = pageSize === 'all' ? totalRows : Math.min(validPage * effectivePageSize, totalRows);

  // Export to Excel (.xlsx)
  const handleExportExcel = () => {
    try {
      setIsExporting(true);
      const ws = XLSX.utils.json_to_sheet(filteredSortedData);

      // Auto-fit column widths
      const colWidths = headers.map((h) => {
        const maxLen = Math.max(
          h.length,
          ...filteredSortedData.slice(0, 100).map((r) => String(r[h] ?? '').length)
        );
        return { wch: Math.min(Math.max(maxLen + 3, 10), 50) };
      });
      ws['!cols'] = colWidths;

      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Query Data');

      const filename = `data_export_${new Date().toISOString().slice(0, 10)}.xlsx`;
      XLSX.writeFile(wb, filename);
    } catch (err) {
      console.error('Failed to export Excel:', err);
      alert('Error exporting Excel file. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  // Export to PDF (.pdf)
  const handleExportPDF = () => {
    try {
      setIsExporting(true);
      const doc = new jsPDF({
        orientation: headers.length > 5 ? 'landscape' : 'portrait',
        unit: 'pt',
        format: 'a4',
      });

      // Branded Title Header
      doc.setFontSize(13);
      doc.setTextColor(1, 118, 211); // Blue
      doc.text('Commercial Decision Intelligence - Data Export', 40, 36);

      doc.setFontSize(8.5);
      doc.setTextColor(100, 116, 139);
      doc.text(
        `Exported: ${new Date().toLocaleString()} | Total Records: ${filteredSortedData.length}`,
        40,
        50
      );

      // Format table values
      const tableRows = filteredSortedData.map((row) =>
        headers.map((h) => (row[h] === null || row[h] === undefined ? '-' : String(row[h])))
      );

      autoTable(doc, {
        head: [headers],
        body: tableRows,
        startY: 62,
        theme: 'striped',
        headStyles: {
          fillColor: [1, 118, 211],
          textColor: 255,
          fontSize: 8,
          fontStyle: 'bold',
          halign: 'left',
        },
        bodyStyles: {
          fontSize: 7.5,
          textColor: [30, 41, 59],
        },
        alternateRowStyles: {
          fillColor: [248, 250, 252],
        },
        margin: { left: 40, right: 40, bottom: 40 },
        didDrawPage: (hookData) => {
          doc.setFontSize(7.5);
          doc.setTextColor(148, 163, 184);
          doc.text(
            `Page ${doc.internal.getNumberOfPages()}`,
            doc.internal.pageSize.width - 60,
            doc.internal.pageSize.height - 18
          );
        },
      });

      const filename = `data_export_${new Date().toISOString().slice(0, 10)}.pdf`;
      doc.save(filename);
    } catch (err) {
      console.error('Failed to export PDF:', err);
      alert('Error exporting PDF file. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  // Export to CSV (.csv)
  const handleExportCSV = () => {
    try {
      setIsExporting(true);
      const csvContent = [
        headers.map((h) => `"${String(h).replace(/"/g, '""')}"`).join(','),
        ...filteredSortedData.map((row) =>
          headers
            .map((h) => {
              const val = row[h] === null || row[h] === undefined ? '' : String(row[h]);
              return `"${val.replace(/"/g, '""')}"`;
            })
            .join(',')
        ),
      ].join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute('download', `data_export_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export CSV:', err);
    } finally {
      setIsExporting(false);
    }
  };

  // Pagination helper items
  const getPaginationItems = () => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const items = [];
    items.push(1);
    if (validPage > 3) {
      items.push('...');
    }
    const start = Math.max(2, validPage - 1);
    const end = Math.min(totalPages - 1, validPage + 1);
    for (let i = start; i <= end; i++) {
      items.push(i);
    }
    if (validPage < totalPages - 2) {
      items.push('...');
    }
    items.push(totalPages);
    return items;
  };

  return (
    <div className="data-table-container">
      {/* Table Toolbar */}
      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <div className="table-search-box">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="table-search-icon"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              placeholder="Search table rows..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              className="table-search-input"
            />
            {searchTerm && (
              <button
                type="button"
                className="table-search-clear"
                onClick={() => {
                  setSearchTerm('');
                  setCurrentPage(1);
                }}
                title="Clear search"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        <div className="table-toolbar-right">
          <div className="table-page-size-selector">
            <label htmlFor="table-page-size">Show</label>
            <select
              id="table-page-size"
              value={pageSize}
              onChange={(e) => {
                setPageSize(e.target.value === 'all' ? 'all' : Number(e.target.value));
                setCurrentPage(1);
              }}
              className="table-select-input"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value="all">All</option>
            </select>
            <span>entries</span>
          </div>

          <div className="table-export-buttons">
            <button
              type="button"
              className="table-export-btn excel"
              onClick={handleExportExcel}
              disabled={isExporting || totalRows === 0}
              title="Download table data as Microsoft Excel (.xlsx)"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="8" y1="13" x2="16" y2="13" />
                <line x1="8" y1="17" x2="16" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
              <span>Excel</span>
            </button>

            <button
              type="button"
              className="table-export-btn pdf"
              onClick={handleExportPDF}
              disabled={isExporting || totalRows === 0}
              title="Download table data as PDF document (.pdf)"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="15" y2="15" />
              </svg>
              <span>PDF</span>
            </button>

            <button
              type="button"
              className="table-export-btn csv"
              onClick={handleExportCSV}
              disabled={isExporting || totalRows === 0}
              title="Download table data as CSV file (.csv)"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              <span>CSV</span>
            </button>
          </div>
        </div>
      </div>

      {/* Table Content */}
      <div className="table-scroll-wrapper">
        <table className="custom-table sortable-table">
          <thead>
            <tr>
              {headers.map((header) => {
                const isSorted = sortConfig.key === header;
                const isAsc = isSorted && sortConfig.direction === 'asc';
                const isDesc = isSorted && sortConfig.direction === 'desc';

                return (
                  <th
                    key={header}
                    onClick={() => handleSort(header)}
                    className={`sortable-th ${isSorted ? 'sorted' : ''}`}
                    title={`Sort by ${header} (${
                      isAsc
                        ? 'Ascending → Click for Descending'
                        : isDesc
                        ? 'Descending → Click to Clear'
                        : 'Click for Ascending'
                    })`}
                  >
                    <div className="th-content">
                      <span className="th-text">{header}</span>
                      <span className={`th-sort-icon ${isSorted ? 'active' : ''}`}>
                        {isAsc ? '▲' : isDesc ? '▼' : '↕'}
                      </span>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {paginatedData.length > 0 ? (
              paginatedData.map((row, index) => (
                <tr key={index}>
                  {headers.map((header) => (
                    <td key={header}>
                      {row[header] === null || row[header] === undefined ? (
                        <em style={{ color: 'var(--text-muted)' }}>null</em>
                      ) : (
                        String(row[header])
                      )}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={headers.length} className="table-empty-row">
                  No matching records found{searchTerm ? ` for "${searchTerm}"` : ''}.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Table Pagination & Footer */}
      <div className="table-footer">
        <div className="table-info">
          {totalRows > 0 ? (
            <>
              Showing <strong>{startIndex}</strong> to <strong>{endIndex}</strong> of <strong>{totalRows}</strong> record(s)
              {searchTerm && <span className="table-filter-note"> (filtered from {data.length} total)</span>}
              {sortConfig.key && (
                <span className="table-sorted-badge">
                  Sorted by: <strong>{sortConfig.key}</strong> ({sortConfig.direction.toUpperCase()})
                  <button
                    type="button"
                    onClick={() => setSortConfig({ key: null, direction: 'asc' })}
                    title="Clear sorting"
                    className="table-sort-clear-btn"
                  >
                    ✕
                  </button>
                </span>
              )}
            </>
          ) : (
            <>Showing 0 of 0 records {searchTerm && `(filtered from ${data.length} total)`}</>
          )}
        </div>

        {pageSize !== 'all' && totalPages > 1 && (
          <div className="table-pagination">
            <button
              type="button"
              className="pagination-btn"
              onClick={() => setCurrentPage(1)}
              disabled={validPage === 1}
              title="First Page"
            >
              ⏮
            </button>
            <button
              type="button"
              className="pagination-btn"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={validPage === 1}
              title="Previous Page"
            >
              ◀ Prev
            </button>

            <div className="pagination-pages">
              {getPaginationItems().map((item, idx) => {
                if (item === '...') {
                  return (
                    <span key={`dots-${idx}`} className="pagination-ellipsis">
                      …
                    </span>
                  );
                }
                const pageNum = Number(item);
                const isActive = pageNum === validPage;
                return (
                  <button
                    key={pageNum}
                    type="button"
                    className={`pagination-num-btn ${isActive ? 'active' : ''}`}
                    onClick={() => setCurrentPage(pageNum)}
                  >
                    {pageNum}
                  </button>
                );
              })}
            </div>

            <button
              type="button"
              className="pagination-btn"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={validPage === totalPages}
              title="Next Page"
            >
              Next ▶
            </button>
            <button
              type="button"
              className="pagination-btn"
              onClick={() => setCurrentPage(totalPages)}
              disabled={validPage === totalPages}
              title="Last Page"
            >
              ⏭
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
