import pytest
from pipeline import stats_math as sm

BAT = {"g": 32, "ab": 118, "r": 27, "h": 35, "d": 8, "t": 1, "hr": 6,
       "rbi": 24, "bb": 15, "k": 28, "hbp": 4, "sb": 9, "cs": 2, "sf": 2, "sh": 1}
PIT = {"g": 9, "gs": 8, "ip_outs": 137, "w": 4, "l": 2, "sv": 0, "hld": 0,
       "h": 38, "r": 18, "er": 14, "bb": 12, "k": 51, "hb": 3, "hr": 3}


def test_pa_and_bf():
    assert sm.pa(BAT) == 118 + 15 + 4 + 2 + 1          # 140
    assert sm.bf(PIT) == 137 + 38 + 12 + 3             # 190


def test_batting_rates():
    r = sm.batting_rates(BAT)
    assert r["avg"] == pytest.approx(35 / 118, abs=1e-4)
    assert r["obp"] == pytest.approx((35 + 15 + 4) / (118 + 15 + 4 + 2), abs=1e-4)
    tb = 35 + 8 + 2 * 1 + 3 * 6  # h + d + 2t + 3hr = 63
    assert r["slg"] == pytest.approx(tb / 118, abs=1e-4)
    assert r["ops"] == pytest.approx(r["obp"] + r["slg"], abs=1e-6)
    assert r["kPct"] == pytest.approx(28 / 140, abs=1e-4)
    assert r["bbPct"] == pytest.approx(15 / 140, abs=1e-4)


def test_pitching_rates():
    r = sm.pitching_rates(PIT)
    ip = 137 / 3
    assert r["era"] == pytest.approx(9 * 14 / ip, abs=1e-3)
    assert r["whip"] == pytest.approx((12 + 38) / ip, abs=1e-3)
    assert r["kPct"] == pytest.approx(51 / 190, abs=1e-4)
    assert r["bbPct"] == pytest.approx(12 / 190, abs=1e-4)
    assert r["hr9"] == pytest.approx(9 * 3 / ip, abs=1e-3)
    assert r["k9"] == pytest.approx(9 * 51 / ip, abs=1e-3)
    assert r["bb9"] == pytest.approx(9 * 12 / ip, abs=1e-3)
    assert r["oppAvg"] == pytest.approx(38 / (190 - 12 - 3), abs=1e-4)


def test_zero_denominators_give_none():
    r = sm.batting_rates({"ab": 0, "h": 0, "d": 0, "t": 0, "hr": 0, "bb": 0,
                          "k": 0, "hbp": 0, "sf": 0, "sh": 0})
    assert r["avg"] is None and r["ops"] is None and r["kPct"] is None
    p = sm.pitching_rates({"ip_outs": 0, "h": 0, "er": 0, "bb": 0, "k": 0, "hb": 0, "hr": 0})
    assert p["era"] is None and p["kPct"] is None


def test_ip_display():
    assert sm.outs_to_ip_str(137) == "45.2"
    assert sm.outs_to_ip_str(54) == "18.0"
