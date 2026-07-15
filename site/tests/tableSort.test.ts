import { describe, expect, it } from 'vitest';
import { compareCells } from '../src/lib/tableSort';

describe('compareCells', () => {
  it('sorts numerically when numeric', () => {
    expect(compareCells('9', '10', true, 'asc')).toBeLessThan(0);
    expect(compareCells('9', '10', true, 'desc')).toBeGreaterThan(0);
  });

  it('sorts strings case-insensitively', () => {
    expect(compareCells('alpha', 'Beta', false, 'asc')).toBeLessThan(0);
  });

  it('always sorts missing values ("—" or empty) last', () => {
    expect(compareCells('—', '5', true, 'asc')).toBeGreaterThan(0);
    expect(compareCells('—', '5', true, 'desc')).toBeGreaterThan(0);
    expect(compareCells('', 'abc', false, 'asc')).toBeGreaterThan(0);
  });
});
