/**
 * APK download configuration for the login page.
 *
 * VITE_APK_DOWNLOAD_URL (absolute https URL) takes priority; otherwise the
 * app serves /downloads/FieldTrackPro.apk from public/downloads/.
 */
export const APK_LOCAL_PATH = '/downloads/FieldTrackPro.apk';
export const APK_META_PATH = '/downloads/apk-meta.json';
export const APK_DOWNLOAD_FILENAME = 'FieldTrack-Pro.apk';

export function resolveApkUrl(raw: string | undefined): string {
  const configured = (raw ?? '').trim();
  return /^https:\/\//i.test(configured) ? configured : APK_LOCAL_PATH;
}

/** True when the URL points at another origin (e.g. a CDN / release host), not this site's /downloads. */
export function isExternalApkUrl(url: string, currentOrigin?: string): boolean {
  if (!/^https?:\/\//i.test(url)) return false;
  const origin = currentOrigin ?? (typeof window !== 'undefined' ? window.location.origin : '');
  try {
    return new URL(url).origin !== origin;
  } catch {
    return false;
  }
}

export const APK_DOWNLOAD_URL = resolveApkUrl(import.meta.env.VITE_APK_DOWNLOAD_URL);

export interface ApkMeta {
  versionName?: string;
  sizeBytes?: number;
}

export function formatApkMeta(meta: ApkMeta | null): string | null {
  if (!meta) return null;
  const parts: string[] = [];
  if (meta.versionName) parts.push(`v${meta.versionName}`);
  if (meta.sizeBytes && meta.sizeBytes > 0) parts.push(`${Math.round(meta.sizeBytes / (1024 * 1024))} MB`);
  return parts.length ? parts.join(' · ') : null;
}
