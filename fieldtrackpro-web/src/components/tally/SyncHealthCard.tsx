import React from 'react';
import { Activity } from 'lucide-react';
import type { SyncState, TallyIntegrationStatus } from '../../types';

const STATE: Record<SyncState, { label: string; cls: string; help: string }> = {
  OK: { label: 'Syncing normally', cls: 'bg-emerald-100 text-emerald-900 border-emerald-300', help: 'Last cycle completed on time.' },
  SYNCING: { label: 'Initial load / manifest running', cls: 'bg-sky-100 text-sky-900 border-sky-300', help: 'A long read of Tally is in progress; the agent is alive.' },
  DEGRADED: { label: 'Degraded', cls: 'bg-amber-100 text-amber-900 border-amber-300', help: 'Data is flowing but something needs attention (queue, quarantine or last error).' },
  STALLED: { label: 'Stalled', cls: 'bg-rose-100 text-rose-900 border-rose-300', help: 'The agent is alive but has not completed a sync cycle in 3 intervals.' },
  TALLY_UNAVAILABLE: { label: 'Tally unavailable', cls: 'bg-amber-100 text-amber-900 border-amber-300', help: 'TallyPrime is closed or port 9000 is unreachable; the agent resumes automatically.' },
  OFFLINE: { label: 'Agent offline', cls: 'bg-rose-100 text-rose-900 border-rose-300', help: 'No heartbeat for 3 minutes.' },
  NOT_CONFIGURED: { label: 'Not configured', cls: 'bg-slate-100 text-slate-700 border-slate-300', help: 'No sync agent registered.' },
};

const fmt = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
const age = (s?: number | null) => (s == null ? '—' : s < 120 ? `${Math.round(s)} s` : s < 7200 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

/** 2.1.0: agent sync health (heartbeat liveness is not data sync - both are shown separately). */
export const SyncHealthCard: React.FC<{ status: TallyIntegrationStatus | null }> = ({ status }) => {
  if (!status || !status.sync_state) return null;
  const st = STATE[status.sync_state] ?? STATE.NOT_CONFIGURED;
  const h = status.health ?? null;
  const q = h?.retry_queue;
  const streams = ['vouchers', 'masters', 'ledgers', 'bills', 'manifest'] as const;
  return (
    <div data-testid="sync-health" className="p-4 rounded-xl border border-surface-container-highest bg-surface-container-low space-y-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Activity className="w-4 h-4 text-primary" />
        <span className="font-bold text-on-surface">Sync health</span>
        <span data-testid="sync-state" className={`px-2 py-0.5 rounded border font-bold ${st.cls}`}>{st.label}</span>
        <span className="text-on-surface-variant">{st.help}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <div>
          <p className="text-on-surface-variant">Agent</p>
          <p className="font-semibold">
            {h?.agent_version ?? status.agent_version ?? '—'}
            {h?.instance && h.instance !== 'default' ? ` · instance ${h.instance}` : ''}
          </p>
          <p className="text-on-surface-variant">Last heartbeat: {fmt(status.last_heartbeat_at)}</p>
        </div>
        <div>
          <p className="text-on-surface-variant">Last sync cycle</p>
          <p className="font-semibold">
            {fmt(h?.last_cycle_completed_at)} {h?.last_cycle_status ? `· ${h.last_cycle_status}` : ''}
            {h?.last_cycle_duration_seconds != null ? ` · ${h.last_cycle_duration_seconds.toFixed(1)} s` : ''}
          </p>
          {h?.phase && h.phase !== 'IDLE' && (
            <p data-testid="sync-phase" className="text-sky-800">
              Now: {h.phase_detail || h.phase}
              {h.cycle_running_seconds ? ` (${age(h.cycle_running_seconds)})` : ''}
            </p>
          )}
        </div>
        <div>
          <p className="text-on-surface-variant">Retry queue</p>
          <p data-testid="retry-queue" className={`font-semibold ${(q?.pending ?? 0) > 0 ? 'text-amber-800' : ''}`}>
            {q ? `${q.pending} pending · oldest ${age(q.oldest_age_seconds)}${q.rejected_4xx ? ` · ${q.rejected_4xx} rejected` : ''}` : '—'}
          </p>
          <p className="text-on-surface-variant">Quarantined vouchers: {h?.quarantine?.unresolved ?? '—'}</p>
        </div>
      </div>
      {h && (
        <div className="flex flex-wrap gap-3" data-testid="last-success">
          {streams.map((s) => (
            <span key={s}>
              <span className="text-on-surface-variant capitalize">{s}:</span> {fmt(h.last_success?.[s])}
            </span>
          ))}
        </div>
      )}
      {h?.last_error && (
        <p data-testid="last-error" className="text-rose-700">
          Last error {fmt(h.last_error.at)}: {h.last_error.message}
        </p>
      )}
      {q?.last_error && <p className="text-amber-800">Queue: {q.last_error}</p>}
      {!h && <p className="text-on-surface-variant">This agent version does not report detailed health.</p>}
    </div>
  );
};
