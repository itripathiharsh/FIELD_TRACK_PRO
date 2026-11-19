/**
 * Asia/Kolkata (IST) date helpers.
 *
 * Every user-facing date in FieldTrack is an IST calendar date. A visit stored
 * as 20:03 UTC on 30 Sep is 01:33 IST on 1 Oct and must be shown (and filtered)
 * as 1 Oct - never through the browser's own time zone.
 */
export const IST_TIME_ZONE = 'Asia/Kolkata';

const dateFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: IST_TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});
const timeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: IST_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const toDate = (value: string | Date | null | undefined): Date | null => {
  if (!value) return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
};

/** dd/mm/yyyy of the IST calendar day containing `value` (an instant). */
export const formatIstDate = (value: string | Date | null | undefined): string => {
  const d = toDate(value);
  return d ? dateFmt.format(d) : '-';
};

/** HH:mm (24h) in IST. */
export const formatIstTime = (value: string | Date | null | undefined): string => {
  const d = toDate(value);
  return d ? timeFmt.format(d) : '-';
};

/** dd/mm/yyyy HH:mm in IST. */
export const formatIstDateTime = (value: string | Date | null | undefined): string => {
  const d = toDate(value);
  return d ? `${dateFmt.format(d)} ${timeFmt.format(d)}` : '-';
};

/** dd/mm/yyyy from a plain calendar date `YYYY-MM-DD` (no time-zone shifting). */
export const formatCalendarDate = (value: string | null | undefined): string => {
  if (!value) return '-';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : value;
};

/** "September 2026" from `YYYY-MM`. */
export const formatMonthLabel = (month: string): string => {
  const fy = /^FY(\d{4})-(\d{2})$/.exec(month);
  if (fy) return `FY ${fy[1]}-${fy[2]} (full year)`;
  const m = /^(\d{4})-(\d{2})$/.exec(month);
  if (!m) return month;
  const names = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];
  return `${names[Number(m[2]) - 1] ?? m[2]} ${m[1]}`;
};
