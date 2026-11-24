/** 'ALL' / '' <-> [] and 'a,b' <-> ['a', 'b'] (multi-select filter state is kept as one comma-joined string). */
export const splitMulti = (v: string | null | undefined): string[] =>
  !v || v === 'ALL' ? [] : v.split(',').map((s) => s.trim()).filter(Boolean);
export const joinMulti = (vs: string[]): string => (vs.length ? vs.join(',') : 'ALL');
