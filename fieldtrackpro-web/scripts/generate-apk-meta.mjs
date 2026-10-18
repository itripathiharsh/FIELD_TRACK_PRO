// Writes public/downloads/apk-meta.json from the real APK (size, sha256 and,
// when Android build-tools are available, versionName/versionCode).
// No-op when the APK is absent (e.g. CI that uses VITE_APK_DOWNLOAD_URL).
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const dir = path.resolve('public', 'downloads');
const apk = path.join(dir, 'FieldTrackPro.apk');
const out = path.join(dir, 'apk-meta.json');

if (!existsSync(apk)) {
  if (existsSync(out)) rmSync(out);
  console.log('[apk-meta] no public/downloads/FieldTrackPro.apk; skipping');
  process.exit(0);
}

function findAapt2() {
  const roots = [process.env.ANDROID_HOME, process.env.ANDROID_SDK_ROOT, 'C:/Android/sdk'].filter(Boolean);
  for (const root of roots) {
    const bt = path.join(root, 'build-tools');
    if (!existsSync(bt)) continue;
    for (const v of readdirSync(bt).sort().reverse()) {
      for (const exe of ['aapt2.exe', 'aapt2']) {
        const p = path.join(bt, v, exe);
        if (existsSync(p)) return p;
      }
    }
  }
  return null;
}

const meta = {
  sizeBytes: statSync(apk).size,
  sha256: createHash('sha256').update(readFileSync(apk)).digest('hex'),
};
const aapt2 = findAapt2();
if (aapt2) {
  try {
    const txt = execFileSync(aapt2, ['dump', 'badging', apk], { encoding: 'utf8' });
    const m = /package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'/.exec(txt);
    if (m) Object.assign(meta, { packageName: m[1], versionCode: Number(m[2]), versionName: m[3] });
  } catch (e) {
    console.warn('[apk-meta] aapt2 failed:', e.message);
  }
}
writeFileSync(out, JSON.stringify(meta, null, 2) + '\n');
console.log('[apk-meta] wrote', out);
