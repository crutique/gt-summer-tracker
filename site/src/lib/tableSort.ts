export type SortDir = 'asc' | 'desc';

const MISSING = new Set(['', '—']);

/** Compare two cell strings for table sorting. Missing values sort last in either direction. */
export function compareCells(a: string, b: string, numeric: boolean, dir: SortDir): number {
  const aMiss = MISSING.has(a.trim());
  const bMiss = MISSING.has(b.trim());
  if (aMiss || bMiss) return Number(aMiss) - Number(bMiss);
  let cmp: number;
  if (numeric) {
    cmp = parseFloat(a) - parseFloat(b);
  } else {
    cmp = a.toLowerCase().localeCompare(b.toLowerCase());
  }
  return dir === 'asc' ? cmp : -cmp;
}
