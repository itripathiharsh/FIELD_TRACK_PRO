/**
 * Date and Time Utilities for FieldTrack Pro Web.
 *
 * APP-ATT-013: Formats date/time explicitly in Asia/Kolkata (IST, UTC+05:30)
 * to maintain consistent presentation with the backend and mobile apps regardless
 * of client device browser timezone.
 */

export function formatIstDateTime(dateInput: string | number | Date | null | undefined): string {
  if (!dateInput) return '—';
  try {
    const d = typeof dateInput === 'string' || typeof dateInput === 'number' ? new Date(dateInput) : dateInput;
    if (isNaN(d.getTime())) return String(dateInput);

    return d.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return String(dateInput);
  }
}

export function formatIstDate(dateInput: string | number | Date | null | undefined): string {
  if (!dateInput) return '—';
  try {
    const d = typeof dateInput === 'string' || typeof dateInput === 'number' ? new Date(dateInput) : dateInput;
    if (isNaN(d.getTime())) return String(dateInput);

    return d.toLocaleDateString('en-IN', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return String(dateInput);
  }
}
