/** File-download helpers for authenticated blob exports. */

/** Extract the file name from a Content-Disposition header (`attachment; filename="x.xlsx"`). */
export function filenameFromContentDisposition(header: string | null | undefined): string | null {
  if (!header) return null;
  const star = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ''));
    } catch {
      /* fall through to the plain filename */
    }
  }
  const plain = /filename\s*=\s*("([^"]+)"|[^;]+)/i.exec(header);
  if (!plain) return null;
  return (plain[2] ?? plain[1]).trim() || null;
}

/** Save a blob under `filename` via a temporary anchor. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
