import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, SearchCheck } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { VisitReviewBadge } from '../components/ui/VisitReviewBadge';
import { apiClient } from '../api/client';
import { formatIstDateTime } from '../utils/date';
import { Visit } from '../types';

const PAGE_SIZE = 20;

/**
 * Admin-only review of ad-hoc (off-beat) visits: who visited which outlet, why,
 * and whether the outlet was outside the employee's assignment.
 */
export const AdhocReviewPage: React.FC = () => {
  const navigate = useNavigate();
  const [visits, setVisits] = useState<Visit[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [outsideOnly, setOutsideOnly] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await apiClient.getAdhocReviewVisits({
        outside_assignment: outsideOnly ? true : undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setVisits(resp.items);
      setTotal(resp.total);
    } catch (err) {
      setVisits([]);
      setTotal(0);
      setError(err instanceof Error ? err.message : 'Unable to load ad-hoc visits');
    } finally {
      setIsLoading(false);
    }
  }, [outsideOnly, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Ad-hoc Visit Review"
        subtitle="Off-beat visits made by field staff, with the reason given and whether the outlet is outside the employee's assignment."
      />

      {error && <ErrorBanner message={error} onRetry={load} />}

      <label className="inline-flex items-center gap-2 text-sm cursor-pointer select-none">
        <input
          type="checkbox"
          checked={outsideOnly}
          onChange={(e) => {
            setOutsideOnly(e.target.checked);
            setPage(1);
          }}
        />
        Outside assignment only
      </label>

      {isLoading ? (
        <p role="status" className="text-sm text-on-surface-variant">Loading ad-hoc visits...</p>
      ) : visits.length === 0 && !error ? (
        <EmptyState
          icon={SearchCheck}
          title="No ad-hoc visits to review"
          subtitle={outsideOnly ? 'No ad-hoc visits outside assignment.' : 'No ad-hoc visits have been recorded yet.'}
        />
      ) : (
        visits.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-outline-variant bg-surface">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-container-high/60 text-on-surface-variant uppercase text-[11px] tracking-wider">
                  <th className="py-2.5 px-3 text-left">Date</th>
                  <th className="py-2.5 px-3 text-left">Employee</th>
                  <th className="py-2.5 px-3 text-left">Outlet</th>
                  <th className="py-2.5 px-3 text-left">Reason</th>
                  <th className="py-2.5 px-3 text-left">Notes</th>
                  <th className="py-2.5 px-3 text-left">Review</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30">
                {visits.map((v) => (
                  <tr
                    key={v.id}
                    onClick={() => navigate(`/visits/${v.id}`)}
                    className="hover:bg-surface-container-low/70 cursor-pointer"
                  >
                    <td className="py-2.5 px-3 whitespace-nowrap">{formatIstDateTime(v.check_in_at ?? v.scheduled_at)}</td>
                    <td className="py-2.5 px-3">{v.employee_name || '-'}</td>
                    <td className="py-2.5 px-3">
                      <p className="font-medium">{v.customer_name || '-'}</p>
                      {v.customer_outlet_code && (
                        <p className="text-xs font-mono text-on-surface-variant">{v.customer_outlet_code}</p>
                      )}
                    </td>
                    <td className="py-2.5 px-3">{v.adhoc_reason || '-'}</td>
                    <td className="py-2.5 px-3 max-w-[280px] break-words">{v.adhoc_notes || '-'}</td>
                    <td className="py-2.5 px-3">
                      <VisitReviewBadge label={v.review_label} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {total > 0 && (
        <div className="flex items-center justify-between text-sm text-on-surface-variant">
          <span>
            Page {page} of {totalPages} · {total} ad-hoc visit{total === 1 ? '' : 's'}
          </span>
          <div className="flex gap-space-2">
            <Button
              variant="outline"
              size="sm"
              icon={ChevronLeft}
              disabled={page <= 1 || isLoading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              icon={ChevronRight}
              disabled={page >= totalPages || isLoading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
