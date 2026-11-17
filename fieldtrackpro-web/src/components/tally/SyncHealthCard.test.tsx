import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SyncHealthCard } from './SyncHealthCard';
import type { AgentHealth, SyncState, TallyIntegrationStatus } from '../../types';

const base: TallyIntegrationStatus = {
  is_connected: true, agent_status: 'ONLINE', tally_status: 'ONLINE', agent_version: '2.1.0',
  last_heartbeat_at: '2026-11-17T10:00:00Z', total_invoices_synced: 0, total_payments_synced: 0, total_customers_synced: 0,
};
const health: AgentHealth = {
  instance: 'default', agent_version: '2.1.0', phase: 'IDLE', last_cycle_completed_at: '2026-11-17T09:59:00Z',
  last_cycle_status: 'COMPLETED', last_cycle_duration_seconds: 19.4,
  last_success: { vouchers: '2026-11-17T09:59:00Z', masters: '2026-11-17T09:59:00Z', ledgers: null, bills: null, manifest: null },
  retry_queue: { pending: 0, oldest_age_seconds: null, max_attempts: 0, rejected_4xx: 0, last_error: null },
  quarantine: { unresolved: 0, oldest_guid: null }, last_error: null, interval_seconds: 300,
};
const show = (sync_state: SyncState, h: AgentHealth | null = health) =>
  render(<SyncHealthCard status={{ ...base, sync_state, health: h }} />);

describe('SyncHealthCard', () => {
  it('renders nothing for a backend without sync_state', () => {
    const { container } = render(<SyncHealthCard status={base} />);
    expect(container).toBeEmptyDOMElement();
  });

  it.each<[SyncState, string]>([
    ['OK', 'Syncing normally'],
    ['SYNCING', 'Initial load / manifest running'],
    ['DEGRADED', 'Degraded'],
    ['STALLED', 'Stalled'],
    ['TALLY_UNAVAILABLE', 'Tally unavailable'],
    ['OFFLINE', 'Agent offline'],
    ['NOT_CONFIGURED', 'Not configured'],
  ])('shows the %s state', (state, label) => {
    show(state);
    expect(screen.getByTestId('sync-state')).toHaveTextContent(label);
  });

  it('shows last success per stream, cycle duration and an idle queue', () => {
    show('OK');
    expect(screen.getByTestId('last-success')).toHaveTextContent(/vouchers/i);
    expect(screen.getByText(/19\.4 s/)).toBeInTheDocument();
    expect(screen.getByTestId('retry-queue')).toHaveTextContent('0 pending');
    expect(screen.queryByTestId('sync-phase')).not.toBeInTheDocument();
  });

  it('shows a degraded queue, the last error and the running phase', () => {
    show('DEGRADED', {
      ...health,
      phase: 'INITIAL_LOAD', phase_detail: 'INITIAL_LOAD day 2026-06-14 (75/231)', cycle_running_seconds: 600,
      retry_queue: { pending: 3, oldest_age_seconds: 7300, max_attempts: 6, rejected_4xx: 1, last_error: 'Backend error 422' },
      last_error: { at: '2026-11-17T09:00:00Z', message: 'Backend error 422: invalid' },
    });
    expect(screen.getByTestId('retry-queue')).toHaveTextContent('3 pending · oldest 2.0 h · 1 rejected');
    expect(screen.getByTestId('last-error')).toHaveTextContent('Backend error 422: invalid');
    expect(screen.getByTestId('sync-phase')).toHaveTextContent('75/231');
  });

  it('explains when an older agent sends no health', () => {
    show('OK', null);
    expect(screen.getByText(/does not report detailed health/)).toBeInTheDocument();
  });
});
