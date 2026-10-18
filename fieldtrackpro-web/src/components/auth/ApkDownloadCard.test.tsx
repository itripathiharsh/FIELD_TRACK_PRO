import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ApkDownloadCard } from './ApkDownloadCard';

const headers = (type: string) => ({
  get: (k: string) => (k.toLowerCase() === 'content-type' ? type : null),
});

describe('ApkDownloadCard', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('offers a real download link with a clean filename and meta from the APK', async () => {
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input === '/downloads/apk-meta.json') {
        return {
          ok: true,
          headers: headers('application/json'),
          json: async () => ({ versionName: '1.0.2', sizeBytes: 58803524 }),
        };
      }
      expect(init?.method).toBe('HEAD');
      return { ok: true, type: 'basic', headers: headers('application/vnd.android.package-archive') };
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<ApkDownloadCard url="/downloads/FieldTrackPro.apk" />);
    const link = await screen.findByRole('link', { name: /download apk/i });
    expect(link).toHaveAttribute('href', '/downloads/FieldTrackPro.apk');
    expect(link).toHaveAttribute('download', 'FieldTrack-Pro.apk');
    expect(await screen.findByText('v1.0.2 · 56 MB')).toBeInTheDocument();
  });

  it('shows a disabled state when the file is missing (SPA fallback returns HTML)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, type: 'basic', headers: headers('text/html') })),
    );
    render(<ApkDownloadCard url="/downloads/FieldTrackPro.apk" />);
    const btn = await screen.findByRole('button', { name: /apk not available yet/i });
    expect(btn).toBeDisabled();
    expect(screen.queryByRole('link', { name: /download apk/i })).not.toBeInTheDocument();
  });

  it('shows a disabled state when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('network');
      }),
    );
    render(<ApkDownloadCard url="https://cdn.example.com/app.apk" />);
    expect(await screen.findByRole('button', { name: /apk not available yet/i })).toBeDisabled();
  });

  it('links to an external https URL when the host answers (opaque no-cors response)', async () => {
    const fetchMock = vi.fn(async () => ({ ok: false, type: 'opaque', headers: headers('') }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ApkDownloadCard url="https://cdn.example.com/app.apk" />);
    const link = await screen.findByRole('link', { name: /download apk/i });
    expect(link).toHaveAttribute('href', 'https://cdn.example.com/app.apk');
    expect(fetchMock).toHaveBeenCalledWith(
      'https://cdn.example.com/app.apk',
      expect.objectContaining({ mode: 'no-cors', method: 'HEAD' }),
    );
  });

  it('an opaque cross-origin response is "unknown": button enabled, honest label, noopener noreferrer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, type: 'opaque', headers: headers('') })));
    render(<ApkDownloadCard url="https://cdn.example.com/app.apk" />);
    const link = await screen.findByRole('link', { name: /download apk/i });
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).not.toHaveAttribute('download');
    expect(screen.getByTestId('apk-unverified')).toHaveTextContent(/cannot be verified/i);
    expect(screen.queryByText(/v\d/)).not.toBeInTheDocument(); // no invented version/size
  });

  it('a verified same-origin APK has no unverified notice and no external rel/target', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string) =>
      input.endsWith('.json')
        ? { ok: false, headers: headers('text/html') }
        : { ok: true, type: 'basic', headers: headers('application/vnd.android.package-archive') },
    ));
    render(<ApkDownloadCard url="/downloads/FieldTrackPro.apk" />);
    const link = await screen.findByRole('link', { name: /download apk/i });
    expect(link).not.toHaveAttribute('target');
    expect(link).not.toHaveAttribute('rel');
    expect(screen.queryByTestId('apk-unverified')).not.toBeInTheDocument();
  });

  describe('production behaviour (hideWhenUnavailable)', () => {
    it('renders nothing when the APK file is absent (SPA HTML fallback)', async () => {
      const fetchMock = vi.fn(async () => ({ ok: true, type: 'basic', headers: headers('text/html') }));
      vi.stubGlobal('fetch', fetchMock);
      const { container } = render(<ApkDownloadCard url="/downloads/FieldTrackPro.apk" hideWhenUnavailable />);
      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      await waitFor(() => expect(container).toBeEmptyDOMElement());
      expect(screen.queryByTestId('apk-card')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /apk not available yet/i })).not.toBeInTheDocument();
    });

    it('renders nothing when an external host is unreachable', async () => {
      vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network'); }));
      const { container } = render(<ApkDownloadCard url="https://cdn.example.com/app.apk" hideWhenUnavailable />);
      await waitFor(() => expect(container).toBeEmptyDOMElement());
    });

    it('shows the card when the APK exists', async () => {
      vi.stubGlobal('fetch', vi.fn(async (input: string) =>
        input.endsWith('.json')
          ? { ok: false, headers: headers('text/html') }
          : { ok: true, type: 'basic', headers: headers('application/vnd.android.package-archive') },
      ));
      render(<ApkDownloadCard url="/downloads/FieldTrackPro.apk" hideWhenUnavailable />);
      expect(await screen.findByTestId('apk-card')).toBeInTheDocument();
    });
  });
});
