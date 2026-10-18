/**
 * Cross-tab coordination for the session.
 *
 * The backend rotates the refresh cookie on every /auth/refresh and revokes ALL
 * of the user's sessions when an already-rotated cookie is replayed outside a
 * short grace window. Several tabs of the same browser share one cookie jar, so
 * two tabs refreshing at once is exactly the replay pattern that logs the user
 * out everywhere. This module provides:
 *
 *  - an exclusive refresh lock (Web Locks API; localStorage lease fallback),
 *  - a BroadcastChannel to share the NEW access token between tabs (memory
 *    only - tokens are never written to storage) and to propagate logout,
 *  - a localStorage timestamp (no secrets) used as a "cookie was just rotated"
 *    signal when BroadcastChannel is unavailable.
 */

export const REFRESH_LOCK_NAME = 'fieldtrack-refresh';
export const CHANNEL_NAME = 'fieldtrack-auth';
const LEASE_KEY = 'fieldtrack_refresh_lease';
const ROTATED_AT_KEY = 'fieldtrack_refresh_rotated_at';
const LOGOUT_AT_KEY = 'fieldtrack_logout_at';

/** Lease must outlive the longest refresh attempt (REFRESH_TIMEOUT_MS in the client). */
const LEASE_TTL_MS = 30_000;
const LEASE_WAIT_MS = 30_000;

export type TabMessage =
  | { type: 'token'; token: string; from: string }
  | { type: 'logout'; from: string };

interface LockManagerLike {
  request<T>(name: string, options: { mode: 'exclusive' }, callback: () => Promise<T>): Promise<T>;
}

function getLocks(): LockManagerLike | undefined {
  if (typeof navigator === 'undefined') return undefined;
  const locks = (navigator as unknown as { locks?: LockManagerLike }).locks;
  return locks && typeof locks.request === 'function' ? locks : undefined;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readLease(): { id: string; exp: number } | null {
  try {
    const raw = localStorage.getItem(LEASE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { id?: unknown; exp?: unknown };
    if (typeof parsed.id === 'string' && typeof parsed.exp === 'number') {
      return { id: parsed.id, exp: parsed.exp };
    }
  } catch {
    // unreadable lease = no lease
  }
  return null;
}

/**
 * Fallback mutex for browsers without Web Locks: a short-lived lease in
 * localStorage (write, wait a beat, read back - if it is still ours we lead).
 * Liveness wins over perfect exclusion: after LEASE_WAIT_MS we proceed anyway,
 * and an unusable localStorage simply runs the function.
 */
async function withStorageLease<T>(fn: () => Promise<T>): Promise<T> {
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  try {
    const deadline = Date.now() + LEASE_WAIT_MS;
    for (;;) {
      const cur = readLease();
      if (!cur || cur.exp < Date.now()) {
        localStorage.setItem(LEASE_KEY, JSON.stringify({ id, exp: Date.now() + LEASE_TTL_MS }));
        await sleep(15);
        if (readLease()?.id === id) break;
      }
      if (Date.now() >= deadline) break;
      await sleep(60 + Math.floor(Math.random() * 60));
    }
  } catch {
    return fn();
  }
  try {
    return await fn();
  } finally {
    try {
      if (readLease()?.id === id) localStorage.removeItem(LEASE_KEY);
    } catch {
      // ignore
    }
  }
}

/** Run `fn` while holding the cross-tab refresh lock. */
export function withRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
  const locks = getLocks();
  if (locks) return locks.request(REFRESH_LOCK_NAME, { mode: 'exclusive' }, fn);
  return withStorageLease(fn);
}

/** Record (timestamp only, no secrets) that the refresh cookie was just rotated. */
export function markRotated(): void {
  try {
    localStorage.setItem(ROTATED_AT_KEY, String(Date.now()));
  } catch {
    // ignore
  }
}

export function lastRotatedAt(): number {
  try {
    return Number(localStorage.getItem(ROTATED_AT_KEY)) || 0;
  } catch {
    return 0;
  }
}

/** Fallback logout signal for browsers without BroadcastChannel (storage event in other tabs). */
export function markLogout(): void {
  try {
    localStorage.setItem(LOGOUT_AT_KEY, String(Date.now()));
  } catch {
    // ignore
  }
}

export interface TabChannel {
  post(message: TabMessage): void;
  close(): void;
}

/**
 * Open the auth channel and deliver messages from OTHER tabs. Uses
 * BroadcastChannel when available, otherwise listens for the `storage` event
 * on the logout timestamp (token sharing is then unavailable and a tab simply
 * re-uses the rotated cookie with one more refresh, serialised by the lock).
 */
export function openTabChannel(onMessage: (m: TabMessage) => void): TabChannel {
  if (typeof BroadcastChannel !== 'undefined') {
    const bc = new BroadcastChannel(CHANNEL_NAME);
    (bc as unknown as { unref?: () => void }).unref?.();
    bc.onmessage = (ev: MessageEvent) => {
      const data = ev.data as TabMessage | null;
      if (data && typeof data === 'object' && (data.type === 'token' || data.type === 'logout')) {
        onMessage(data);
      }
    };
    return {
      post: (m) => {
        try {
          bc.postMessage(m);
        } catch {
          // channel closed
        }
      },
      close: () => bc.close(),
    };
  }
  if (typeof window === 'undefined') return { post: () => {}, close: () => {} };
  const onStorage = (ev: StorageEvent) => {
    if (ev.key === LOGOUT_AT_KEY && ev.newValue) onMessage({ type: 'logout', from: 'storage' });
  };
  window.addEventListener('storage', onStorage);
  return {
    post: (m) => {
      if (m.type === 'logout') markLogout();
    },
    close: () => window.removeEventListener('storage', onStorage),
  };
}
