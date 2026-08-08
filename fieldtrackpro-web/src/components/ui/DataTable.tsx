import React, { useState } from 'react';
import { Search, ChevronLeft, ChevronRight, Inbox, ArrowUpDown } from 'lucide-react';
import { Input } from './Input';
import { Button } from './Button';

export interface Column<T> {
  header: string;
  accessor: (item: T) => React.ReactNode;
  sortKey?: keyof T;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  searchPlaceholder?: string;
  searchFilter?: (item: T, query: string) => boolean;
  isLoading?: boolean;
  emptyMessage?: string;
  onRowClick?: (item: T) => void;
  actions?: React.ReactNode;
}

export function DataTable<T extends { id?: string }>({
  columns,
  data,
  searchPlaceholder = 'Search records...',
  searchFilter,
  isLoading = false,
  emptyMessage = 'No records found',
  onRowClick,
  actions,
}: DataTableProps<T>) {
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 8;

  const filteredData = searchFilter && searchQuery
    ? data.filter((item) => searchFilter(item, searchQuery))
    : data;

  const totalPages = Math.ceil(filteredData.length / pageSize) || 1;
  const paginatedData = filteredData.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <div className="bg-surface rounded-xl border border-surface-container-highest shadow-xs overflow-hidden flex flex-col transition-all duration-200">
      {/* Search & Actions Bar */}
      {(searchFilter || actions) && (
        <div className="p-space-4 border-b border-surface-container-highest flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-space-4 bg-surface">
          {searchFilter ? (
            <div className="relative flex-1 max-w-md">
              <Input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                onClear={() => {
                  setSearchQuery('');
                  setCurrentPage(1);
                }}
                placeholder={searchPlaceholder}
                icon={Search}
              />
            </div>
          ) : <div />}

          <div className="flex items-center gap-space-3 justify-between sm:justify-end">
            {actions}
            <span className="font-label-md text-xs text-on-surface-variant uppercase tracking-wider shrink-0 font-medium">
              Total: <strong className="text-primary font-bold">{filteredData.length}</strong> records
            </span>
          </div>
        </div>
      )}

      {/* Table Element */}
      <div className="overflow-x-auto min-h-[300px]">
        <table className="w-full text-left font-body-md text-on-surface">
          <thead className="bg-surface-container-low text-on-surface-variant font-label-md text-xs uppercase tracking-wider border-b border-surface-container-highest select-none">
            <tr>
              {columns.map((col, idx) => (
                <th key={idx} className="px-space-6 py-space-3.5 font-bold text-primary">
                  <div className="flex items-center gap-1.5">
                    <span>{col.header}</span>
                    {col.sortKey && <ArrowUpDown className="w-3 h-3 text-outline/60" />}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-container-highest">
            {isLoading ? (
              Array.from({ length: 5 }).map((_, rIdx) => (
                <tr key={rIdx} className="animate-pulse">
                  {columns.map((_, cIdx) => (
                    <td key={cIdx} className="px-space-6 py-space-4">
                      <div className="h-4 bg-surface-container-high rounded-md w-3/4"></div>
                    </td>
                  ))}
                </tr>
              ))
            ) : paginatedData.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-space-6 py-space-12 text-center text-on-surface-variant">
                  <div className="flex flex-col items-center justify-center py-space-6">
                    <Inbox className="w-10 h-10 text-outline mb-space-2 stroke-[1.5]" />
                    <p className="font-headline-sm text-sm text-on-surface-variant font-semibold">{emptyMessage}</p>
                    <p className="font-caption text-xs text-outline mt-1">Try refining your search query or filters.</p>
                  </div>
                </td>
              </tr>
            ) : (
              paginatedData.map((item, idx) => (
                <tr
                  key={item.id || idx}
                  onClick={() => onRowClick && onRowClick(item)}
                  className={`transition-colors duration-150 ${
                    onRowClick ? 'cursor-pointer hover:bg-surface-container-low/90 active:bg-surface-container' : 'hover:bg-surface-bright'
                  }`}
                >
                  {columns.map((col, cIdx) => (
                    <td key={cIdx} className="px-space-6 py-space-3.5 text-sm align-middle">
                      {col.accessor(item)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="px-space-6 py-space-3 border-t border-surface-container-highest flex items-center justify-between bg-surface-container-low/50">
          <span className="font-caption text-xs text-on-surface-variant">
            Page <strong className="text-primary">{currentPage}</strong> of <strong className="text-primary">{totalPages}</strong>
          </span>
          <div className="flex items-center gap-space-2">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Prev</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            >
              <span>Next</span>
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
