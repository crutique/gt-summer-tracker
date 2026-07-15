import { describe, expect, it } from 'vitest';
import {
  getAssignedPlayers, getGamelog, getLeagueByKey, getLeagues,
  getPlayer, getPlayers, getUnassignedPlayers, isSampleLeague,
} from '../src/lib/data';

describe('data access', () => {
  it('loads all 42 players', () => {
    expect(getPlayers()).toHaveLength(42);
  });

  it('finds a player by slug, undefined for unknown', () => {
    expect(getPlayer('jackson-blakely')?.name).toBe('Jackson Blakely');
    expect(getPlayer('nobody')).toBeUndefined();
  });

  it('splits assigned and unassigned', () => {
    const assigned = getAssignedPlayers();
    expect(assigned.map((p) => p.slug).sort()).toEqual(
      ['caden-spivey', 'jackson-blakely', 'jamie-vicens', 'riley-hasenstab']);
    expect(getUnassignedPlayers()).toHaveLength(38);
  });

  it('exposes sliders with leagueAvgPercentile', () => {
    const jb = getPlayer('jackson-blakely')!;
    const sliders = jb.pitching!.sliders!;
    expect(sliders).toHaveLength(6);
    expect(sliders[0]).toHaveProperty('leagueAvgPercentile');
  });

  it('loads leagues sorted by player count', () => {
    const leagues = getLeagues();
    expect(leagues[0].key).toBe('northwoods');
    expect(getLeagueByKey('northwoods')?.abbrev).toBe('NWL');
    expect(getLeagueByKey('nope')).toBeUndefined();
  });

  it('flags fixture-platform leagues as sample data', () => {
    expect(isSampleLeague('northwoods')).toBe(true);
    expect(isSampleLeague('mlb_draft')).toBe(false);
  });

  it('loads gamelogs by slug, empty for missing', () => {
    expect(getGamelog('jackson-blakely').length).toBeGreaterThanOrEqual(2);
    expect(getGamelog('will-baker')).toEqual([]);
  });
});
