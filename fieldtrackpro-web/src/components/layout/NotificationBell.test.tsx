import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { NotificationBell } from './NotificationBell';
import { apiClient } from '../../api/client';

const items = [
  { id: 'n1', user_id: 'u', payment_id: 'p1', visit_id: null, type: 'REMINDER', title: 'Tally post failed', message: 'x', is_read: false, sent_at: '2026-10-10T10:00:00Z' },
  { id: 'n2', user_id: 'u', payment_id: null, visit_id: 'v1', type: 'REMINDER', title: 'Ad-hoc visit outside assignment', message: 'y', is_read: false, sent_at: '2026-10-10T10:00:00Z' },
  { id: 'n3', user_id: 'u', payment_id: null, visit_id: 'v2', type: 'REMINDER', title: 'Visit reminder', message: 'z', is_read: false, sent_at: '2026-10-10T10:00:00Z' },
];

vi.mock('../../api/client', () => ({
  apiClient: {
    getUnreadNotificationCount: vi.fn().mockResolvedValue({ unread_count: 3 }),
    getMyNotifications: vi.fn(async () => items),
    markNotificationRead: vi.fn().mockResolvedValue(undefined),
    markAllNotificationsRead: vi.fn().mockResolvedValue(undefined),
  },
}));

const Where = () => <div data-testid="loc">{useLocation().pathname}</div>;

function setup() {
  render(
    <MemoryRouter initialEntries={['/']}>
      <NotificationBell />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function openBell() {
  fireEvent.click(screen.getByRole('button', { name: /notification/i }));
  await screen.findByText('Tally post failed');
}

describe('NotificationBell navigation', () => {
  beforeEach(() => {
    vi.mocked(apiClient.getUnreadNotificationCount).mockResolvedValue({ unread_count: 3 });
    vi.mocked(apiClient.getMyNotifications).mockResolvedValue(items as never);
    vi.mocked(apiClient.markNotificationRead).mockResolvedValue(undefined as never);
    vi.mocked(apiClient.markAllNotificationsRead).mockResolvedValue(undefined as never);
  });

  it('payment alerts open /payments', async () => {
    setup();
    await openBell();
    fireEvent.click(screen.getByText('Tally post failed'));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/payments'));
  });

  it('ad-hoc outside-assignment alerts open /visits/adhoc-review', async () => {
    setup();
    await openBell();
    fireEvent.click(screen.getByText('Ad-hoc visit outside assignment'));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/visits/adhoc-review'));
  });

  it('other notifications do not navigate', async () => {
    setup();
    await openBell();
    fireEvent.click(screen.getByText('Visit reminder'));
    expect(screen.getByTestId('loc').textContent).toBe('/');
  });
});
