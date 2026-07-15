from pipeline import validate

GOOD_BAT = [{"stats_id": "a", "name": "A", "team": "T", "g": 10, "ab": 40, "r": 5, "h": 12,
             "d": 2, "t": 0, "hr": 1, "rbi": 6, "bb": 4, "k": 9, "hbp": 1, "sb": 2, "cs": 0,
             "sf": 0, "sh": 0}]
GOOD_PIT = [{"stats_id": "p", "name": "P", "team": "T", "g": 5, "gs": 5, "ip_outs": 90,
             "w": 2, "l": 1, "sv": 0, "hld": 0, "h": 25, "r": 10, "er": 9, "bb": 8, "k": 30,
             "hb": 1, "hr": 2}]


def _assigned(sid, ptype):
    return {"slug": sid, "summer": {"stats_id": sid, "status": "assigned"},
            "player_type": ptype}


def test_happy_path_no_errors():
    errors, warnings = validate.check_league(
        "lg", {"batting": GOOD_BAT, "pitching": GOOD_PIT},
        [_assigned("a", "hitter")], previous={})
    assert errors == [] and warnings == []


def test_empty_tables_is_error():
    errors, _ = validate.check_league("lg", {"batting": [], "pitching": []}, [], previous={})
    assert any("empty" in e for e in errors)


def test_impossible_rate_is_error():
    bad = [dict(GOOD_BAT[0], h=50)]  # 50 hits in 40 AB -> AVG > 1
    errors, _ = validate.check_league("lg", {"batting": bad, "pitching": GOOD_PIT},
                                      [], previous={})
    assert any("avg" in e for e in errors)


def test_counting_stat_decrease_is_error():
    prev = {"a": {"summer": {"leagueKey": "lg"},
                  "hitting": {"counting": {"g": 12, "h": 15}}}}
    errors, _ = validate.check_league("lg", {"batting": GOOD_BAT, "pitching": GOOD_PIT},
                                      [_assigned("a", "hitter")], previous=prev)
    assert any("decreased" in e for e in errors)


def test_missing_assigned_player_is_warning_not_error():
    errors, warnings = validate.check_league(
        "lg", {"batting": GOOD_BAT, "pitching": GOOD_PIT},
        [_assigned("ghost", "hitter")], previous={})
    assert errors == []
    assert any("ghost" in w for w in warnings)
