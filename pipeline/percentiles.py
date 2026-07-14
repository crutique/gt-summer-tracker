"""Midrank percentiles, oriented so higher percentile = better (Savant convention)."""

HITTER_SLIDERS = ["ops", "avg", "obp", "slg", "kPct", "bbPct"]
PITCHER_SLIDERS = ["era", "whip", "kPct", "bbPct", "hr9", "oppAvg"]

_INVERTED = {
    "hitting": {"kPct"},
    "pitching": {"era", "whip", "bbPct", "hr9", "oppAvg"},
}


def is_inverted(side, metric):
    return metric in _INVERTED[side]


def midrank_percentile(pool, value, invert=False):
    below = sum(1 for x in pool if x < value)
    ties = sum(1 for x in pool if x == value)
    pct = (below + 0.5 * ties) / len(pool) * 100
    if invert:
        pct = 100 - pct
    return max(0, min(99, round(pct)))
