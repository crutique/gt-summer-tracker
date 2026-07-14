from pipeline import percentiles as pc


def test_midrank_basic():
    pool = [0.600, 0.700, 0.800, 0.900, 1.000]
    # .900: 3 below + half of 1 tie = 3.5/5 = 70
    assert pc.midrank_percentile(pool, 0.900) == 70


def test_midrank_ties():
    pool = [0.700, 0.800, 0.800, 0.800, 0.900]
    # .800: 1 below + 1.5 of 3 ties = 2.5/5 = 50
    assert pc.midrank_percentile(pool, 0.800) == 50


def test_inverted_flips():
    pool = [2.00, 3.00, 4.00, 5.00]
    # 2.00 is the BEST ERA: raw midrank = 0.5/4 = 12.5 -> 13; inverted -> 87
    assert pc.midrank_percentile(pool, 2.00, invert=True) == 88 or \
           pc.midrank_percentile(pool, 2.00, invert=True) == 87  # rounding boundary
    assert pc.midrank_percentile(pool, 5.00, invert=True) < 20


def test_singleton_pool_and_clamp():
    assert pc.midrank_percentile([0.5], 0.5) == 50
    assert pc.midrank_percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 10) <= 99


def test_metric_definitions():
    assert pc.HITTER_SLIDERS == ["ops", "avg", "obp", "slg", "kPct", "bbPct"]
    assert pc.PITCHER_SLIDERS == ["era", "whip", "kPct", "bbPct", "hr9", "oppAvg"]
    assert pc.is_inverted("hitting", "kPct") is True
    assert pc.is_inverted("hitting", "ops") is False
    assert pc.is_inverted("pitching", "era") is True
    assert pc.is_inverted("pitching", "kPct") is False
