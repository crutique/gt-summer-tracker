import json
from pipeline import build_data


def test_full_build_happy_path(tmp_path):
    out, hist = tmp_path / "data", tmp_path / "history"
    result = build_data.build("pipeline/players.yaml", "pipeline/leagues.yaml",
                              out, hist, today="2026-07-14")
    assert result.failures == []
    assert "mlb_draft" in result.skipped            # platform: pending
    players = {r["slug"]: r for r in json.loads((out / "players.json").read_text())}
    assert len(players) == 42
    jb = players["jackson-blakely"]
    assert jb["asOf"] == "2026-07-14"
    metrics = [s["metric"] for s in jb["pitching"]["sliders"]]
    assert metrics == ["era", "whip", "kPct", "bbPct", "hr9", "oppAvg"]
    assert players["caden-spivey"]["pitching"] is None       # pending platform, no previous
    assert players["will-baker"]["summer"]["status"] == "unassigned"
    log = json.loads((out / "gamelogs" / "jackson-blakely.json").read_text())
    assert log[0]["date"] >= log[-1]["date"]                  # newest first


def test_failed_league_carries_forward(tmp_path):
    out, hist = tmp_path / "data", tmp_path / "history"
    build_data.build("pipeline/players.yaml", "pipeline/leagues.yaml", out, hist,
                     today="2026-07-14")
    log_path = out / "gamelogs" / "jackson-blakely.json"
    log_before = log_path.read_text()
    # break the league: point fixture_dir somewhere empty
    leagues = tmp_path / "leagues.yaml"
    leagues.write_text(
        "northwoods:\n  name: Northwoods League\n  abbrev: NWL\n"
        "  official_url: https://northwoodsleague.com\n  platform: fixture\n"
        "  tier: 1\n  fixture_dir: /nonexistent\n"
        "mlb_draft:\n  name: MLB Draft League\n  abbrev: MLBDL\n"
        "  official_url: https://www.mlbdraftleague.com\n  platform: pending\n  tier: null\n")
    result = build_data.build("pipeline/players.yaml", str(leagues), out, hist,
                              today="2026-07-15")
    assert [f[0] for f in result.failures] == ["northwoods"]
    players = {r["slug"]: r for r in json.loads((out / "players.json").read_text())}
    jb = players["jackson-blakely"]
    assert jb["asOf"] == "2026-07-14"                 # yesterday's data survived
    assert jb["pitching"]["counting"]["g"] == 7
    assert log_path.read_text() == log_before        # stale-but-correct gamelog untouched
    assert (hist / "2026-07-15" / "gamelogs" / "jackson-blakely.json").exists()
