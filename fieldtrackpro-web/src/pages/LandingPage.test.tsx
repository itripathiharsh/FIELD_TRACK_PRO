import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LandingPage } from './LandingPage';

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );
}

describe('LandingPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('offers "Use on web" linking to the login screen', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 404 }));
    renderLanding();
    const web = screen.getByTestId('landing-use-web');
    expect(web).toHaveTextContent(/use on web/i);
    expect(web).toHaveAttribute('href', '/login');
  });

  it('offers "Download app" pointing at the bundled APK', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 404 }));
    renderLanding();
    const links = screen.getAllByTestId('landing-download-apk');
    expect(links.length).toBeGreaterThan(0);
    for (const a of links) {
      expect(a).toHaveTextContent(/download app/i);
      expect(a).toHaveAttribute('href', '/downloads/FieldTrackPro.apk');
      expect(a).toHaveAttribute('download', 'FieldTrack-Pro.apk');
    }
  });

  it('shows the APK version, size and checksum from apk-meta.json', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ versionName: '1.2.0', versionCode: 5, sizeBytes: 66907850, sha256: 'ab'.repeat(32) }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
    renderLanding();
    await waitFor(() => expect(screen.getByText('1.2.0 (5)')).toBeInTheDocument());
    expect(screen.getByText('63.8 MB')).toBeInTheDocument();
    expect(screen.getByText('ab'.repeat(32))).toBeInTheDocument();
  });

  it('ignores the SPA HTML fallback when apk-meta.json is missing', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('<!doctype html>', { status: 200, headers: { 'content-type': 'text/html' } }));
    renderLanding();
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    expect(screen.queryByText(/SHA-256/i)).not.toBeInTheDocument();
  });

  it('shows the static map poster and no WebGL canvas when WebGL is unavailable', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 404 }));
    const { container } = renderLanding();
    expect(container.querySelector('.ftl-poster')).not.toBeNull();
    await new Promise((r) => setTimeout(r, 400));
    expect(container.querySelector('canvas')).toBeNull();
    expect(container.querySelector('.ftl-hero')?.classList.contains('is-3d')).toBe(false);
  });

  it('renders the static (reduced-motion) experience with ?motion=off', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 404 }));
    window.history.pushState({}, '', '/?motion=off');
    const { container } = renderLanding();
    expect(container.querySelector('.ftl')?.classList.contains('ftl--still')).toBe(true);
    expect(container.querySelector('.ftl-hero')?.classList.contains('is-static')).toBe(true);
    window.history.pushState({}, '', '/');
  });
});
