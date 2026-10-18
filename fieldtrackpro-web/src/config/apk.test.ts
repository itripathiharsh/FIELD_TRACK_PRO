import { describe, it, expect } from 'vitest';
import { resolveApkUrl, formatApkMeta, isExternalApkUrl, APK_LOCAL_PATH } from './apk';

describe('apk config', () => {
  it('prefers an absolute https URL', () => {
    expect(resolveApkUrl(' https://cdn.example.com/a.apk ')).toBe('https://cdn.example.com/a.apk');
  });

  it('falls back to the bundled path for empty or non-https values', () => {
    expect(resolveApkUrl(undefined)).toBe(APK_LOCAL_PATH);
    expect(resolveApkUrl('')).toBe(APK_LOCAL_PATH);
    expect(resolveApkUrl('http://insecure.example.com/a.apk')).toBe(APK_LOCAL_PATH);
  });

  it('detects external URLs by origin', () => {
    expect(isExternalApkUrl('https://cdn.example.com/a.apk', 'https://app.example.com')).toBe(true);
    expect(isExternalApkUrl('https://app.example.com/downloads/a.apk', 'https://app.example.com')).toBe(false);
    expect(isExternalApkUrl('/downloads/a.apk', 'https://app.example.com')).toBe(false);
  });

  it('formats meta only from known facts', () => {
    expect(formatApkMeta(null)).toBeNull();
    expect(formatApkMeta({})).toBeNull();
    expect(formatApkMeta({ versionName: '1.0.2', sizeBytes: 58803524 })).toBe('v1.0.2 · 56 MB');
    expect(formatApkMeta({ versionName: '1.0.2' })).toBe('v1.0.2');
  });
});
