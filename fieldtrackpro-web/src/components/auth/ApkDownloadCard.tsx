import React, { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import {
  APK_DOWNLOAD_FILENAME,
  APK_DOWNLOAD_URL,
  APK_META_PATH,
  formatApkMeta,
  isExternalApkUrl,
  type ApkMeta,
} from '../../config/apk';

/**
 * 'available'   - same-origin file verified (2xx, not the SPA's HTML fallback).
 * 'unknown'     - cross-origin host answered a no-cors probe; the response is opaque so
 *                 availability cannot be proven. The button is enabled and the download
 *                 itself will surface any error.
 * 'unavailable' - verified missing / unreachable.
 */
type Availability = 'checking' | 'available' | 'unknown' | 'unavailable';

interface ApkDownloadCardProps {
  className?: string;
  /** Override for tests; defaults to the configured URL. */
  url?: string;
  /**
   * When no APK is available, render nothing at all (production) instead of a
   * disabled button shown to every visitor. Defaults to true in production
   * builds; in dev the disabled state stays visible because it explains why.
   */
  hideWhenUnavailable?: boolean;
}

const AndroidLogo: React.FC = () => (
  <svg viewBox="0 0 64 76" className="w-[50px] h-[58px] sm:w-[58px] sm:h-[68px] shrink-0" aria-hidden="true">
    <g fill="#5fa839">
      <path d="M8 28a24 24 0 0 1 48 0z" />
      <rect x="8" y="31" width="48" height="30" rx="4" />
      <rect x="0" y="31" width="6" height="24" rx="3" />
      <rect x="58" y="31" width="6" height="24" rx="3" />
      <rect x="18" y="56" width="9" height="18" rx="4.5" />
      <rect x="37" y="56" width="9" height="18" rx="4.5" />
    </g>
    <circle cx="22" cy="17" r="2.6" fill="#fff" />
    <circle cx="42" cy="17" r="2.6" fill="#fff" />
    <path d="M15 4l5 7M49 4l-5 7" stroke="#5fa839" strokeWidth="2.6" strokeLinecap="round" />
  </svg>
);

/**
 * Checks that the APK really exists (HEAD) before offering it, so the button is
 * never a dead link. Same-origin URLs must answer 2xx with a non-HTML body (the
 * SPA fallback returns index.html for unknown paths). Cross-origin URLs use a
 * no-cors HEAD: an opaque response means the host answered; a network error
 * means unavailable.
 */
export const ApkDownloadCard: React.FC<ApkDownloadCardProps> = ({
  url = APK_DOWNLOAD_URL,
  className = '',
  hideWhenUnavailable = import.meta.env.PROD,
}) => {
  const [availability, setAvailability] = useState<Availability>('checking');
  const [meta, setMeta] = useState<ApkMeta | null>(null);

  useEffect(() => {
    let cancelled = false;
    const crossOrigin = isExternalApkUrl(url);

    const check = async () => {
      try {
        const res = await fetch(url, {
          method: 'HEAD',
          cache: 'no-store',
          ...(crossOrigin ? { mode: 'no-cors' as RequestMode } : {}),
        });
        const type = res.headers.get('content-type') ?? '';
        if (crossOrigin) {
          // An opaque (no-cors) response cannot prove the file exists - only that the host answered.
          const answered = res.type === 'opaque' || res.ok;
          if (!cancelled) setAvailability(answered ? (res.ok && res.type !== 'opaque' ? 'available' : 'unknown') : 'unavailable');
          return;
        }
        const ok = res.ok && !/text\/html/i.test(type);
        if (!cancelled) setAvailability(ok ? 'available' : 'unavailable');
        if (ok) {
          const m = await fetch(APK_META_PATH, { cache: 'no-store' });
          const mType = m.headers.get('content-type') ?? '';
          if (m.ok && /json/i.test(mType)) {
            const data = (await m.json()) as ApkMeta;
            if (!cancelled) setMeta(data);
          }
        }
      } catch {
        if (!cancelled) setAvailability('unavailable');
      }
    };
    void check();
    return () => {
      cancelled = true;
    };
  }, [url]);

  const external = isExternalApkUrl(url);
  const canDownload = availability === 'available' || availability === 'unknown';
  const metaText = availability === 'available' ? formatApkMeta(meta) : null;

  // Nothing to offer (or not yet known) in production: show no card instead of a dead button.
  if (hideWhenUnavailable && !canDownload) return null;
  const buttonBase =
    'inline-flex items-center justify-center gap-3 h-[54px] px-6 rounded-lg font-portal font-semibold text-[17px] whitespace-nowrap';

  return (
    <section
      aria-label="Android app download"
      data-testid="apk-card"
      className={`rounded-xl border border-portal-card-border bg-portal-card px-5 py-5 sm:px-7 sm:py-[28px] grid grid-cols-[auto_minmax(0,1fr)] min-[1500px]:grid-cols-[auto_minmax(0,1fr)_auto] gap-x-4 sm:gap-x-[23px] gap-y-3 items-start ${className}`}
    >
      <div className="col-start-1 row-start-1 row-span-2 self-center">
        <AndroidLogo />
      </div>
      <div className="min-w-0 col-start-2 row-start-1">
        <p className="font-portal text-[11px] font-semibold tracking-[0.18em] text-[#5b6577] uppercase">
          Field Team Android App
        </p>
        <h2 className="font-portal text-lg sm:text-[20px] font-bold min-[1500px]:whitespace-nowrap text-primary leading-snug mt-1">
          Get the FieldTrack Pro App
        </h2>
      </div>
      <div className="col-span-2 row-start-3 sm:col-span-1 sm:col-start-2 sm:justify-self-start min-[1500px]:row-start-1 min-[1500px]:col-start-3 min-[1500px]:-mt-1 flex flex-col items-stretch">
        {canDownload ? (
          <a
            href={url}
            {...(external
              ? { target: '_blank', rel: 'noopener noreferrer' }
              : { download: APK_DOWNLOAD_FILENAME })}
            className={`${buttonBase} bg-[#0e1e31] text-on-primary hover:bg-primary transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary`}
          >
            <Download className="w-[19px] h-[19px]" aria-hidden="true" />
            Download APK
          </a>
        ) : (
          <button
            type="button"
            disabled
            aria-disabled="true"
            className={`${buttonBase} bg-[#0e1e31]/40 text-on-primary cursor-not-allowed`}
          >
            <Download className="w-[19px] h-[19px]" aria-hidden="true" />
            {availability === 'checking' ? 'Checking…' : 'APK not available yet'}
          </button>
        )}
      </div>
      <p className="col-start-2 row-start-2 min-[1500px]:col-span-2 font-portal text-[15px] text-[#5b6577] min-[1500px]:-mt-1 flex flex-wrap items-baseline justify-between gap-x-4">
        <span>Install on your Android device and start tracking visits.</span>
        {metaText && <span className="text-xs whitespace-nowrap">{metaText}</span>}
        {availability === 'unknown' && (
          <span className="basis-full text-xs" data-testid="apk-unverified">
            Hosted on an external site, so availability cannot be verified from here. If the download fails, ask your administrator.
          </span>
        )}
      </p>
    </section>
  );
};
