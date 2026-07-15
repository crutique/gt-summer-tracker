const LOW: [number, number, number] = [0x4a, 0x7d, 0xe0];
const MID: [number, number, number] = [0x8e, 0x9b, 0xb0];
const HIGH: [number, number, number] = [0xd9, 0x30, 0x25];

function mix(a: [number, number, number], b: [number, number, number], t: number): string {
  const ch = a.map((av, i) => Math.round(av + (b[i] - av) * t));
  return `#${ch.map((c) => c.toString(16).padStart(2, '0')).join('')}`;
}

/** Percentile (0-100) → hex color on the blue→gray→red scale. Red = good. */
export function percentileColor(p: number): string {
  const c = Math.max(0, Math.min(100, p));
  return c <= 50 ? mix(LOW, MID, c / 50) : mix(MID, HIGH, (c - 50) / 50);
}
