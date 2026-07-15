import { describe, expect, it } from 'vitest';
import { percentileColor } from '../src/lib/colors';

describe('percentileColor', () => {
  it('hits the anchor colors', () => {
    expect(percentileColor(0)).toBe('#4a7de0');
    expect(percentileColor(50)).toBe('#8e9bb0');
    expect(percentileColor(100)).toBe('#d93025');
  });

  it('interpolates between anchors', () => {
    const c25 = percentileColor(25);
    expect(c25).toMatch(/^#[0-9a-f]{6}$/);
    expect(c25).not.toBe('#4a7de0');
    expect(c25).not.toBe('#8e9bb0');
  });

  it('clamps out-of-range input', () => {
    expect(percentileColor(-5)).toBe('#4a7de0');
    expect(percentileColor(120)).toBe('#d93025');
  });
});
