# GT Summer Tracker — Plan 3: Real Scraper, Cutover & Nightly Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixture Northwoods data with the league's real Scorebook API, execute the sample-data cutover reset, fetch player headshots, and ship the nightly GitHub Actions refresh — making the site truthful and self-updating.

**Architecture:** New `scorebook` platform scraper (pure JSON API — no HTML parsing) normalizing to the canonical row contract, with native PA/BF passthrough so derived-flags become honest. Orchestrator tests get decoupled from production config BEFORE cutover (so the suite never hits the network). Cutover deletes all committed sample data (spec handoff condition 2), flips `leagues.yaml`, and publishes real data. Photos come from Scorebook's hosted images. Nightly workflow follows the spec note: commit step survives failed-partial exit.

**Tech Stack:** Python 3.12 (`.venv` — NEVER bare `python3`, it's 3.7), requests (new dep), pytest; existing Astro site untouched except its data-layer tests. GitHub Actions for cron.

**Verified live API facts (scouted 2026-07-15, this plan is written against them):**
- `GET https://scorebook.northwoodsleague.com/api/statistics/all/0?general=true` → `{statistics: {info: {season_name: "2026 - Regular Season", teams: {...}}, types: {batting: {keys, stats[680], totals}, pitching: {keys, stats[837], totals}, fielding: {...}}}}`.
  Batting row keys incl.: `firstname, lastname, player_id, team, team_abv, position, G, PA, AB, R, H, 2B, 3B, HR, RBI, BB, HBP, K, SF, SH, SB, CS` (+rates we ignore). Pitching row keys incl.: `G, GS, IP ("32.1" string), W, L, SV, H, R, ER, BB, K, HB, HR, BF` (+rates we ignore; **no HLD** — holds default to 0).
- `GET https://scorebook.northwoodsleague.com/api/statistics/player/{player_id}` → `{playerStats: {player: {...}, types: {pitching|batting: {stats, games: {"2026": [{gameid, date: "Jul 13", team, home_team, visitor_team, IP, H, R, ER, BB, K, W, L, SV, BF, ...}]}, totals}}}}`. 404s for unknown ids.
- `GET https://scorebook.northwoodsleague.com/api/player/{player_id}` → bio incl. `college` ("Georgia Tech") and `photo` (hosted JPG URL).
- Confirmed GT players in live data: Jamie Vicens `player_id=10352`, Riley Hasenstab `player_id=10225` (both Willmar/WIL). **Jackson Blakely is NOT in the league stats** — keep him assigned with his placeholder stats_id; the pipeline warns and the site shows "awaiting stats" until roster research resolves him.

---

## File structure

```
pipeline/
  scrapers/scorebook.py            # NEW platform scraper (JSON API)
  scrapers/__init__.py             # register "scorebook"
  fixtures/scorebook_nwl/          # NEW trimmed captures of the real API (Task 1)
    statistics_all.json  player_10225.json  player_10352.json
  stats_math.py                    # native pa/bf passthrough + ip_str_to_outs (Task 2)
  compute.py                       # honest derived flags (Task 3)
  validate.py                      # reuse ip_str_to_outs + malformed-ip guard (Task 2)
  build_data.py                    # skip empty gamelog writes (Task 5)
  fetch_photos.py                  # NEW one-time headshot fetcher (Task 7)
  tests/test_scorebook.py          # NEW
  tests/test_build_data.py         # REWRITTEN off production config (Task 5)
  players.yaml / leagues.yaml      # cutover edits (Task 6)
site/tests/data.test.ts            # cutover-adjusted expectations (Task 6)
site/public/headshots/             # downloaded images (Task 7)
.github/workflows/nightly.yml      # NEW (Task 8)
requirements.txt                   # + requests
```

All commands run from the repo root (quote the path — it contains spaces). Current suite: **47 pytest / 19 vitest**.

---

### Task 1: Capture real-API fixtures

**Files:**
- Create: `pipeline/fixtures/scorebook_nwl/statistics_all.json`, `player_10225.json`, `player_10352.json`

- [ ] **Step 1: Capture and trim.** Run this from the repo root (it fetches live data, trims the league stats to a testable subset that KEEPS both GT pitchers, and pretty-prints):

```bash
mkdir -p pipeline/fixtures/scorebook_nwl
curl -s "https://scorebook.northwoodsleague.com/api/statistics/player/10225" -o pipeline/fixtures/scorebook_nwl/player_10225.json
curl -s "https://scorebook.northwoodsleague.com/api/statistics/player/10352" -o pipeline/fixtures/scorebook_nwl/player_10352.json
curl -s "https://scorebook.northwoodsleague.com/api/statistics/all/0?general=true" -o /tmp/sb_all.json
.venv/bin/python - <<'EOF'
import json
d = json.load(open("/tmp/sb_all.json"))
types = d["statistics"]["types"]
keep_pit = [r for r in types["pitching"]["stats"] if r["player_id"] in (10225, 10352)]
keep_pit += [r for r in types["pitching"]["stats"] if r["player_id"] not in (10225, 10352)][:10]
types["pitching"]["stats"] = keep_pit
types["batting"]["stats"] = types["batting"]["stats"][:12]
types.pop("fielding", None)
json.dump(d, open("pipeline/fixtures/scorebook_nwl/statistics_all.json", "w"), indent=1)
EOF
.venv/bin/python -c "
import json
d = json.load(open('pipeline/fixtures/scorebook_nwl/statistics_all.json'))
pit = d['statistics']['types']['batting']['stats'], d['statistics']['types']['pitching']['stats']
print('batters:', len(pit[0]), 'pitchers:', len(pit[1]))
ids = [r['player_id'] for r in pit[1]]
assert 10225 in ids and 10352 in ids, 'GT pitchers missing'
print('GT pitchers present OK')
"
```
Expected: `batters: 12 pitchers: 12` and `GT pitchers present OK`. Also verify the player files parse: `.venv/bin/python -c "import json; [json.load(open(f'pipeline/fixtures/scorebook_nwl/player_{i}.json')) for i in (10225, 10352)]; print('ok')"`.

- [ ] **Step 2: Sanity-inspect** — confirm `player_10225.json` has `playerStats.types.pitching.games` with a `"2026"` list whose entries carry `date` ("Jul 13" style), `team`, `home_team`, `visitor_team`, `IP`, `H`, `R`, `ER`, `BB`, `K`, `W`, `L`, `SV`. Report the first entry in your task report.

- [ ] **Step 3: Commit**

```bash
git add pipeline/fixtures/scorebook_nwl
git commit -m "test: capture trimmed scorebook API fixtures (real NWL responses)"
```

---

### Task 2: stats_math — native PA/BF passthrough + ip_str_to_outs (+ validate hardening)

**Files:**
- Modify: `pipeline/stats_math.py`, `pipeline/validate.py`
- Test: `pipeline/tests/test_stats_math.py`, `pipeline/tests/test_validate.py`

- [ ] **Step 1: Write the failing tests.** Add to `pipeline/tests/test_stats_math.py`:

```python
def test_native_pa_bf_passthrough():
    assert sm.pa({"pa": 140, "ab": 1, "bb": 1, "hbp": 0, "sf": 0, "sh": 0}) == 140
    assert sm.bf({"bf": 190, "ip_outs": 1, "h": 1, "bb": 1, "hb": 0}) == 190
    # zero/missing native values fall back to derivation
    assert sm.pa({"pa": 0, "ab": 10, "bb": 2, "hbp": 1, "sf": 0, "sh": 0}) == 13
    assert sm.bf({"ip_outs": 30, "h": 8, "bb": 4, "hb": 1}) == 43


def test_ip_str_to_outs():
    assert sm.ip_str_to_outs("32.1") == 97
    assert sm.ip_str_to_outs("6.0") == 18
    assert sm.ip_str_to_outs(7) == 21
    assert sm.ip_str_to_outs("10,005.1") == 30016
    assert sm.ip_str_to_outs("") == 0
```

Add to `pipeline/tests/test_validate.py`:

```python
def test_decrease_check_skips_malformed_previous_ip():
    prev = {"p": {"summer": {"leagueKey": "lg"},
                  "pitching": {"counting": {"ip": "not-a-number", "g": 1}}}}
    errors, warnings = validate.check_league(
        "lg", {"batting": GOOD_BAT, "pitching": GOOD_PIT},
        [_assigned("p", "pitcher")], previous=prev)
    assert errors == []          # malformed previous ip is skipped, not a crash
```

- [ ] **Step 2: Run to verify failures**

Run: `.venv/bin/pytest pipeline/tests/test_stats_math.py pipeline/tests/test_validate.py -q`
Expected: 3 failures (AttributeError `ip_str_to_outs`, passthrough assertion, ValueError from malformed ip), rest pass.

- [ ] **Step 3: Implement.** In `pipeline/stats_math.py`, change `pa` and `bf` to prefer native fields and add the parser:

```python
def pa(b):
    native = _get(b, "pa")
    if native:
        return native
    return _get(b, "ab") + _get(b, "bb") + _get(b, "hbp") + _get(b, "sf") + _get(b, "sh")


def bf(p):
    native = _get(p, "bf")
    if native:
        return native
    # BF approx = outs (3*IP) + H + BB + HB  (spec: Percentile engine / derived inputs)
    return _get(p, "ip_outs") + _get(p, "h") + _get(p, "bb") + _get(p, "hb")


def ip_str_to_outs(ip):
    """'32.1' -> 97 outs. Accepts int/float-ish strings; commas stripped; '' -> 0."""
    s = str(ip).replace(",", "").strip()
    if not s:
        return 0
    whole, _, frac = s.partition(".")
    return int(whole) * 3 + (int(frac) if frac else 0)
```

In `pipeline/validate.py`: replace the private `_ip_str_to_outs` helper with `sm.ip_str_to_outs` at its call site, wrapping the comparison in a guard so malformed previous values are skipped:

```python
            if key == "ip":
                try:
                    old_cmp, new_cmp = sm.ip_str_to_outs(old), bat_or_pit_row.get("ip_outs")
                except (ValueError, TypeError):
                    continue
```
(Adapt to the file's existing structure — the intent: any ValueError/TypeError parsing the previous `ip` means skip that key, never crash the gate. Keep all existing messages/behavior otherwise. Delete `_ip_str_to_outs` if now unused.)

- [ ] **Step 4: Full suite**

Run: `.venv/bin/pytest -q`
Expected: `50 passed` (47 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add pipeline/stats_math.py pipeline/validate.py pipeline/tests/test_stats_math.py pipeline/tests/test_validate.py
git commit -m "feat: native PA/BF passthrough, shared ip parser, validate hardening"
```

---

### Task 3: compute — honest derived flags

When a platform supplies PA/BF natively, kPct/bbPct are no longer "derived". oppAvg stays derived always (its AB-faced denominator is still approximated).

**Files:**
- Modify: `pipeline/compute.py`
- Test: `pipeline/tests/test_compute.py`

- [ ] **Step 1: Write the failing test.** Add to `pipeline/tests/test_compute.py`:

```python
def test_derived_false_with_native_denominators():
    batting = [dict(r, pa=r["ab"] + r["bb"] + r["hbp"] + r["sf"] + r["sh"]) for r in BATTING]
    pitching = [dict(p, bf=200) for p in PITCHING]
    bundle = compute.league_bundle(CFG, {"batting": batting, "pitching": pitching},
                                   {}, wanted={"a", "p1"})
    hs = {s["metric"]: s for s in bundle["a"]["hitting"]["sliders"]}
    assert hs["kPct"]["derived"] is False and hs["bbPct"]["derived"] is False
    ps = {s["metric"]: s for s in bundle["p1"]["pitching"]["sliders"]}
    assert ps["kPct"]["derived"] is False and ps["bbPct"]["derived"] is False
    assert ps["oppAvg"]["derived"] is True   # still an approximation even with native BF
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest pipeline/tests/test_compute.py -q`
Expected: 1 failed (derived is True), rest pass — including the existing `test_derived_flag_set_when_pa_not_native`, which must KEEP passing (fixture rows lack `pa`).

- [ ] **Step 3: Implement.** In `pipeline/compute.py`:
- Change `_sliders(side, metrics, my_rates, all_rates, lg_avgs, tier)` to accept an extra `native_denoms: bool` parameter; the derived line becomes:

```python
            "derived": m in _DERIVED[side] and not (native_denoms and m != "oppAvg"),
```

- `_hitting_block(row, ...)` passes `native_denoms=bool(row.get("pa"))`; `_pitching_block(row, ...)` passes `native_denoms=bool(row.get("bf"))`. (Keep `_DERIVED` unchanged; oppAvg stays derived because `m != "oppAvg"` excludes it from the native exemption.)

- [ ] **Step 4: Full suite**

Run: `.venv/bin/pytest -q`
Expected: `51 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/compute.py pipeline/tests/test_compute.py
git commit -m "feat: derived flag honest when platform supplies native PA/BF"
```

---

### Task 4: scorebook scraper

**Files:**
- Create: `pipeline/scrapers/scorebook.py`
- Modify: `pipeline/scrapers/__init__.py`, `requirements.txt`
- Test: `pipeline/tests/test_scorebook.py`

- [ ] **Step 1: Add dependency.** Append to `requirements.txt`: `requests==2.32.3` then `.venv/bin/pip install -r requirements.txt -q`.

- [ ] **Step 2: Write the failing tests** — `pipeline/tests/test_scorebook.py`:

```python
import json
from pathlib import Path

import pytest

from pipeline.scrapers import SCRAPERS, scorebook

FIX = Path("pipeline/fixtures/scorebook_nwl")
CFG = {"api_base": "https://scorebook.example/api"}


def _fake_get_json(monkeypatch):
    def fake(url):
        if url.endswith("/statistics/all/0?general=true"):
            return json.loads((FIX / "statistics_all.json").read_text())
        for pid in ("10225", "10352"):
            if url.endswith(f"/statistics/player/{pid}"):
                return json.loads((FIX / f"player_{pid}.json").read_text())
        import requests
        resp = requests.Response()
        resp.status_code = 404
        raise requests.HTTPError(response=resp)
    monkeypatch.setattr(scorebook, "_get_json", fake)
    monkeypatch.setattr(scorebook.time, "sleep", lambda s: None)


def test_registered():
    assert SCRAPERS["scorebook"] is scorebook


def test_league_stats_normalized(monkeypatch):
    _fake_get_json(monkeypatch)
    stats = scorebook.fetch_league_stats(CFG)
    assert len(stats["batting"]) == 12 and len(stats["pitching"]) == 12
    bat_keys = {"stats_id", "name", "team", "g", "ab", "r", "h", "d", "t", "hr",
                "rbi", "bb", "k", "hbp", "sb", "cs", "sf", "sh", "pa"}
    pit_keys = {"stats_id", "name", "team", "g", "gs", "ip_outs", "w", "l", "sv",
                "hld", "h", "r", "er", "bb", "k", "hb", "hr", "bf"}
    assert set(stats["batting"][0]) == bat_keys
    assert set(stats["pitching"][0]) == pit_keys
    riley = next(r for r in stats["pitching"] if r["stats_id"] == "10225")
    assert riley["name"] == "Riley Hasenstab"
    assert riley["ip_outs"] == 97          # "32.1" -> 97 (live value at capture time)
    assert riley["bf"] > 0 and riley["hld"] == 0
    assert all(isinstance(r["stats_id"], str) for r in stats["pitching"])


def test_game_logs(monkeypatch):
    _fake_get_json(monkeypatch)
    logs = scorebook.fetch_game_logs(CFG, ["10225", "jackson-blakely", "99999999"])
    assert logs["jackson-blakely"] == []       # non-numeric placeholder id
    assert logs["99999999"] == []              # 404 -> empty
    riley = logs["10225"]
    assert len(riley) >= 2
    dates = [g["date"] for g in riley]
    assert dates == sorted(dates, reverse=True)          # newest first
    assert all(d.startswith("2026-") and len(d) == 10 for d in dates)
    g = riley[0]
    assert set(g) == {"date", "opponent", "ip_outs", "h", "r", "er", "bb", "k", "hr", "dec"}
    assert g["opponent"].startswith(("vs ", "at "))
    assert g["dec"] in ("W", "L", "SV", "")
```

Note on `riley["ip_outs"] == 97`: this pins the value captured in Task 1's fixture ("32.1" IP at capture time). If your captured fixture shows a different IP for player 10225, adjust this single assertion to `sm.ip_str_to_outs(<the fixture's IP string>)` — the point is the conversion, not the specific game count.

- [ ] **Step 3: Run to verify failures**

Run: `.venv/bin/pytest pipeline/tests/test_scorebook.py -q`
Expected: FAIL — ImportError (no scorebook module).

- [ ] **Step 4: Implement**

`pipeline/scrapers/scorebook.py`:
```python
"""Scraper for the Northwoods League 'Scorebook' stats platform (pure JSON API).

League stats:  GET {api_base}/statistics/all/0?general=true
Player + log:  GET {api_base}/statistics/player/{player_id}   (404 for unknown ids)
"""
import time

import requests

from pipeline import stats_math as sm

_TIMEOUT = 30
_THROTTLE_S = 1.0
_HEADERS = {"User-Agent": "GT-Summer-Tracker/1.0 (unofficial fan project)"}


def _get_json(url):
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _name(r):
    return f"{r.get('firstname', '')} {r.get('lastname', '')}".strip()


def _norm_bat(r):
    return {
        "stats_id": str(r["player_id"]), "name": _name(r), "team": r.get("team", ""),
        "g": r.get("G", 0), "ab": r.get("AB", 0), "r": r.get("R", 0), "h": r.get("H", 0),
        "d": r.get("2B", 0), "t": r.get("3B", 0), "hr": r.get("HR", 0),
        "rbi": r.get("RBI", 0), "bb": r.get("BB", 0), "k": r.get("K", 0),
        "hbp": r.get("HBP", 0), "sb": r.get("SB", 0), "cs": r.get("CS", 0),
        "sf": r.get("SF", 0), "sh": r.get("SH", 0), "pa": r.get("PA", 0),
    }


def _norm_pit(r):
    return {
        "stats_id": str(r["player_id"]), "name": _name(r), "team": r.get("team", ""),
        "g": r.get("G", 0), "gs": r.get("GS", 0),
        "ip_outs": sm.ip_str_to_outs(r.get("IP", 0)),
        "w": r.get("W", 0), "l": r.get("L", 0), "sv": r.get("SV", 0), "hld": 0,
        "h": r.get("H", 0), "r": r.get("R", 0), "er": r.get("ER", 0),
        "bb": r.get("BB", 0), "k": r.get("K", 0), "hb": r.get("HB", 0),
        "hr": r.get("HR", 0), "bf": r.get("BF", 0),
    }


def fetch_league_stats(league_cfg):
    data = _get_json(f"{league_cfg['api_base']}/statistics/all/0?general=true")
    types = data["statistics"]["types"]
    return {
        "batting": [_norm_bat(r) for r in types["batting"]["stats"]],
        "pitching": [_norm_pit(r) for r in types["pitching"]["stats"]],
    }


_MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
           "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _iso_date(short, year):
    parts = str(short).split()
    mon = _MONTHS[parts[0][:3]]
    day = int("".join(ch for ch in parts[1] if ch.isdigit()))
    return f"{year}-{mon:02d}-{day:02d}"


def _dec(g):
    if g.get("W"):
        return "W"
    if g.get("L"):
        return "L"
    if g.get("SV"):
        return "SV"
    return ""


def _opponent(g):
    if g.get("team") == g.get("home_team"):
        return f"vs {g.get('visitor_team', '')}"
    return f"at {g.get('home_team', '')}"


def _pit_game(g, year):
    return {"date": _iso_date(g["date"], year), "opponent": _opponent(g),
            "ip_outs": sm.ip_str_to_outs(g.get("IP", 0)), "h": g.get("H", 0),
            "r": g.get("R", 0), "er": g.get("ER", 0), "bb": g.get("BB", 0),
            "k": g.get("K", 0), "hr": g.get("HR", 0), "dec": _dec(g)}


def _hit_game(g, year):
    return {"date": _iso_date(g["date"], year), "opponent": _opponent(g),
            "ab": g.get("AB", 0), "r": g.get("R", 0), "h": g.get("H", 0),
            "d": g.get("2B", 0), "t": g.get("3B", 0), "hr": g.get("HR", 0),
            "rbi": g.get("RBI", 0), "bb": g.get("BB", 0), "k": g.get("K", 0),
            "sb": g.get("SB", 0)}


def _player_games(payload):
    types = payload.get("playerStats", {}).get("types", {})
    out = []
    for side, mk in (("pitching", _pit_game), ("batting", _hit_game)):
        games_by_year = (types.get(side) or {}).get("games") or {}
        if not games_by_year:
            continue
        year = max(games_by_year, key=int)
        out.extend(mk(g, year) for g in games_by_year[year])
    out.sort(key=lambda e: e["date"], reverse=True)
    return out


def fetch_game_logs(league_cfg, stats_ids):
    logs = {}
    for sid in stats_ids:
        if not str(sid).isdigit():
            logs[sid] = []   # placeholder id — player not yet located on this platform
            continue
        try:
            payload = _get_json(f"{league_cfg['api_base']}/statistics/player/{sid}")
            logs[sid] = _player_games(payload)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logs[sid] = []
            else:
                raise
        time.sleep(_THROTTLE_S)
    return logs
```

`pipeline/scrapers/__init__.py` (replace content):
```python
"""Platform-name → scraper-module map."""
from pipeline.scrapers import fixture, scorebook

SCRAPERS = {"fixture": fixture, "scorebook": scorebook}
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest pipeline/tests/test_scorebook.py -q` → `3 passed`; full suite `.venv/bin/pytest -q` → `54 passed`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/scrapers/scorebook.py pipeline/scrapers/__init__.py requirements.txt pipeline/tests/test_scorebook.py
git commit -m "feat: scorebook platform scraper (Northwoods JSON API)"
```

---

### Task 5: Decouple orchestrator tests from production config + skip empty gamelog writes

CRITICAL ordering: this must land BEFORE the cutover (Task 6), or `pytest` would hit the live API. Also implements spec handoff condition 3 (empty log fetch must not clobber an existing gamelog file).

**Files:**
- Modify: `pipeline/build_data.py` (one-line gate change)
- Rewrite: `pipeline/tests/test_build_data.py`

- [ ] **Step 1: Implement the empty-log gate.** In `pipeline/build_data.py`, change the gamelog population loop to also require a non-empty log:

```python
            for p in assigned:
                sid = p["summer"]["stats_id"]
                if sid in league_bundles[key] and logs.get(sid):
                    gamelogs_by_slug[p["slug"]] = logs[sid]
```
(A player with stats but a transiently-empty log fetch keeps their existing gamelog file on disk; a player who genuinely has no games yet simply gets no file — the site treats no-file as an empty log.)

- [ ] **Step 2: Rewrite `pipeline/tests/test_build_data.py`** with this exact content (all builds now use tmp-file registries pointing at the committed FIXTURE platform — no production YAML, no network):

```python
import json
import shutil
from pathlib import Path

from pipeline import build_data

LEAGUES_TEMPLATE = (
    "northwoods:\n  name: Northwoods League\n  abbrev: NWL\n"
    "  official_url: https://northwoodsleague.com\n  platform: fixture\n"
    "  tier: 1\n  fixture_dir: {fixture_dir}\n"
    "mlb_draft:\n  name: MLB Draft League\n  abbrev: MLBDL\n"
    "  official_url: https://www.mlbdraftleague.com\n  platform: pending\n  tier: null\n")

PLAYERS_YAML = (
    "- {name: Jackson Blakely, slug: jackson-blakely, gt_status: returning, player_type: pitcher, position: P,"
    " summer: {status: assigned, team: Willmar Stingers, league: northwoods, stats_id: jackson-blakely}}\n"
    "- {name: Jamie Vicens, slug: jamie-vicens, gt_status: returning, player_type: pitcher, position: P,"
    " summer: {status: assigned, team: Willmar Stingers, league: northwoods, stats_id: jamie-vicens}}\n"
    "- {name: Riley Hasenstab, slug: riley-hasenstab, gt_status: returning, player_type: pitcher, position: P,"
    " summer: {status: assigned, team: Willmar Stingers, league: northwoods, stats_id: riley-hasenstab}}\n"
    "- {name: Caden Spivey, slug: caden-spivey, gt_status: returning, player_type: pitcher, position: P,"
    " summer: {status: assigned, team: Trenton Thunder, league: mlb_draft, stats_id: caden-spivey}}\n"
    "- {name: Will Baker, slug: will-baker, gt_status: returning, player_type: hitter, position: \"\","
    " summer: {status: unassigned}}\n")


def _setup(tmp_path, fixture_dir=None):
    fixture_dir = fixture_dir or _copy_fixture(tmp_path)
    players = tmp_path / "players.yaml"
    players.write_text(PLAYERS_YAML)
    leagues = tmp_path / "leagues.yaml"
    leagues.write_text(LEAGUES_TEMPLATE.format(fixture_dir=fixture_dir))
    return str(players), str(leagues), fixture_dir


def _copy_fixture(tmp_path):
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(exist_ok=True)
    src = Path("pipeline/fixtures/northwoods_sample")
    for name in ("batting.json", "pitching.json", "gamelogs.json"):
        shutil.copy(src / name, fixture_dir / name)
    return fixture_dir


def test_full_build_happy_path(tmp_path):
    out, hist = tmp_path / "data", tmp_path / "history"
    players, leagues, _ = _setup(tmp_path)
    result = build_data.build(players, leagues, out, hist, today="2026-07-14")
    assert result.failures == []
    assert "mlb_draft" in result.skipped
    recs = {r["slug"]: r for r in json.loads((out / "players.json").read_text())}
    assert len(recs) == 5
    jb = recs["jackson-blakely"]
    assert jb["asOf"] == "2026-07-14"
    metrics = [s["metric"] for s in jb["pitching"]["sliders"]]
    assert metrics == ["era", "whip", "kPct", "bbPct", "hr9", "oppAvg"]
    assert recs["caden-spivey"]["pitching"] is None
    assert recs["will-baker"]["summer"]["status"] == "unassigned"
    log = json.loads((out / "gamelogs" / "jackson-blakely.json").read_text())
    assert log[0]["date"] >= log[-1]["date"]


def test_failed_league_carries_forward(tmp_path):
    out, hist = tmp_path / "data", tmp_path / "history"
    players, leagues_ok, _ = _setup(tmp_path)
    build_data.build(players, leagues_ok, out, hist, today="2026-07-14")
    log_path = out / "gamelogs" / "jackson-blakely.json"
    log_before = log_path.read_text()
    broken = tmp_path / "leagues_broken.yaml"
    broken.write_text(LEAGUES_TEMPLATE.format(fixture_dir="/nonexistent"))
    result = build_data.build(players, str(broken), out, hist, today="2026-07-15")
    assert [f[0] for f in result.failures] == ["northwoods"]
    recs = {r["slug"]: r for r in json.loads((out / "players.json").read_text())}
    jb = recs["jackson-blakely"]
    assert jb["asOf"] == "2026-07-14"
    assert jb["pitching"]["counting"]["g"] == 7
    assert log_path.read_text() == log_before
    assert (hist / "2026-07-15" / "gamelogs" / "jackson-blakely.json").exists()


def test_validation_error_fails_league(tmp_path):
    out, hist = tmp_path / "data", tmp_path / "history"
    fixture_dir = _copy_fixture(tmp_path)
    batting = json.loads((fixture_dir / "batting.json").read_text())
    batting[0]["h"] = batting[0]["ab"] + 10
    (fixture_dir / "batting.json").write_text(json.dumps(batting))
    players, leagues, _ = _setup(tmp_path, fixture_dir=fixture_dir)
    result = build_data.build(players, leagues, out, hist, today="2026-07-14")
    assert len(result.failures) == 1 and result.failures[0][0] == "northwoods"
    assert "impossible" in result.failures[0][1]


def test_missing_player_keeps_gamelog_in_healthy_league(tmp_path):
    out, hist = tmp_path / "data", tmp_path / "history"
    players, leagues_ok, _ = _setup(tmp_path)
    build_data.build(players, leagues_ok, out, hist, today="2026-07-14")
    log_path = out / "gamelogs" / "jackson-blakely.json"
    log_before = log_path.read_text()
    fixture_dir = tmp_path / "fixture2"
    fixture_dir.mkdir()
    src = Path("pipeline/fixtures/northwoods_sample")
    for name in ("batting.json", "pitching.json", "gamelogs.json"):
        shutil.copy(src / name, fixture_dir / name)
    pitching = json.loads((fixture_dir / "pitching.json").read_text())
    pitching = [r for r in pitching if r["stats_id"] != "jackson-blakely"]
    (fixture_dir / "pitching.json").write_text(json.dumps(pitching))
    leagues2 = tmp_path / "leagues2.yaml"
    leagues2.write_text(LEAGUES_TEMPLATE.format(fixture_dir=fixture_dir))
    result = build_data.build(players, str(leagues2), out, hist, today="2026-07-15")
    assert result.failures == []
    assert any("jackson-blakely" in w for w in result.warnings)
    recs = {r["slug"]: r for r in json.loads((out / "players.json").read_text())}
    assert recs["jackson-blakely"]["asOf"] == "2026-07-14"
    assert log_path.read_text() == log_before


def test_player_missing_from_stats_and_gamelogs_keeps_gamelog(tmp_path):
    out, hist = tmp_path / "data", tmp_path / "history"
    players, leagues_ok, _ = _setup(tmp_path)
    build_data.build(players, leagues_ok, out, hist, today="2026-07-14")
    log_path = out / "gamelogs" / "jackson-blakely.json"
    log_before = log_path.read_text()
    fixture_dir = tmp_path / "fixture3"
    fixture_dir.mkdir()
    src = Path("pipeline/fixtures/northwoods_sample")
    for name in ("batting.json", "pitching.json", "gamelogs.json"):
        shutil.copy(src / name, fixture_dir / name)
    pitching = json.loads((fixture_dir / "pitching.json").read_text())
    pitching = [r for r in pitching if r["stats_id"] != "jackson-blakely"]
    (fixture_dir / "pitching.json").write_text(json.dumps(pitching))
    gamelogs = json.loads((fixture_dir / "gamelogs.json").read_text())
    gamelogs.pop("jackson-blakely")
    (fixture_dir / "gamelogs.json").write_text(json.dumps(gamelogs))
    leagues3 = tmp_path / "leagues3.yaml"
    leagues3.write_text(LEAGUES_TEMPLATE.format(fixture_dir=fixture_dir))
    result = build_data.build(players, str(leagues3), out, hist, today="2026-07-15")
    assert result.failures == []
    assert log_path.read_text() == log_before


def test_present_player_empty_log_fetch_keeps_existing_file(tmp_path):
    out, hist = tmp_path / "data", tmp_path / "history"
    players, leagues_ok, _ = _setup(tmp_path)
    build_data.build(players, leagues_ok, out, hist, today="2026-07-14")
    log_path = out / "gamelogs" / "jackson-blakely.json"
    log_before = log_path.read_text()
    fixture_dir = tmp_path / "fixture4"
    fixture_dir.mkdir()
    src = Path("pipeline/fixtures/northwoods_sample")
    for name in ("batting.json", "pitching.json", "gamelogs.json"):
        shutil.copy(src / name, fixture_dir / name)
    gamelogs = json.loads((fixture_dir / "gamelogs.json").read_text())
    gamelogs["jackson-blakely"] = []            # still in stats tables, log fetch empty
    (fixture_dir / "gamelogs.json").write_text(json.dumps(gamelogs))
    leagues4 = tmp_path / "leagues4.yaml"
    leagues4.write_text(LEAGUES_TEMPLATE.format(fixture_dir=fixture_dir))
    result = build_data.build(players, str(leagues4), out, hist, today="2026-07-15")
    assert result.failures == []
    recs = {r["slug"]: r for r in json.loads((out / "players.json").read_text())}
    assert recs["jackson-blakely"]["asOf"] == "2026-07-15"   # stats ARE fresh
    assert log_path.read_text() == log_before                # log file untouched
```

- [ ] **Step 3: TDD check.** Before applying the Step 1 gate change, run the new test file — `test_present_player_empty_log_fetch_keeps_existing_file` must FAIL (file overwritten with `[]`); after applying Step 1 it must pass. Report both observations. (Order within this task: write tests → observe the failure → apply the gate → observe green.)

- [ ] **Step 4: Full suite**

Run: `.venv/bin/pytest -q`
Expected: `55 passed` (54 + rewritten file has 6 tests vs prior 5).

- [ ] **Step 5: Commit**

```bash
git add pipeline/build_data.py pipeline/tests/test_build_data.py
git commit -m "fix: orchestrator tests offline-only; empty log fetch never clobbers files"
```

---

### Task 6: THE CUTOVER — real data replaces sample data

Executes spec handoff conditions 1 & 2. This task touches config, deletes committed sample outputs, runs a LIVE build (network required), and updates site tests.

**Files:**
- Modify: `pipeline/leagues.yaml`, `pipeline/players.yaml`, `site/tests/data.test.ts`, `docs/superpowers/specs/2026-07-14-gt-summer-tracker-design.md`
- Delete + regenerate: `site/src/data/*`, `data/history/*`

- [ ] **Step 1: Flip the league config.** `pipeline/leagues.yaml` northwoods entry becomes:

```yaml
northwoods:
  name: Northwoods League
  abbrev: NWL
  official_url: https://northwoodsleague.com
  platform: scorebook
  api_base: https://scorebook.northwoodsleague.com/api
  tier: 1
```
(`fixture_dir` removed; the fixture platform and `pipeline/fixtures/northwoods_sample/` stay in the repo for tests only. `mlb_draft` unchanged.)

- [ ] **Step 2: Real stats_ids.** In `pipeline/players.yaml`: jamie-vicens `stats_id: "10352"`, riley-hasenstab `stats_id: "10225"` (quoted strings). Jackson Blakely KEEPS `stats_id: jackson-blakely` with a trailing comment `# not found in NWL stats as of 2026-07-15 — pending roster research`.

- [ ] **Step 3: The reset (handoff condition 2).**

```bash
rm -rf site/src/data data/history
.venv/bin/python -m pipeline.build_data
```
Expected output: the `mlb_draft ... skipping` notice, ONE warning (`northwoods: assigned player jackson-blakely not found in league tables`), and the summary `[build] wrote 42 players; 0 league failure(s), 1 skipped, 1 warning(s)`, exit 0. Takes ~5s (two live gamelog calls + throttle).

- [ ] **Step 4: Spot-check real data.**

```bash
.venv/bin/python -c "
import json
d = {p['slug']: p for p in json.load(open('site/src/data/players.json'))}
rh = d['riley-hasenstab']
assert rh['pitching']['sliders'] and len(rh['pitching']['sliders']) == 6
assert rh['pitching']['counting']['g'] >= 8
assert d['jackson-blakely']['pitching'] is None       # awaiting stats
assert d['jamie-vicens']['pitching']['counting']['g'] >= 10
print('cutover data OK:', rh['pitching']['counting']['ip'], 'IP for Hasenstab')
"
ls site/src/data/gamelogs
```
Expected: assertion passes; gamelogs dir contains `jamie-vicens.json` and `riley-hasenstab.json` (NO blakely file).

- [ ] **Step 5: Update site data tests.** In `site/tests/data.test.ts`, replace the three now-false expectations:
- `'exposes sliders with leagueAvgPercentile'`: use `getPlayer('riley-hasenstab')` instead of jackson-blakely.
- `'flags fixture-platform leagues as sample data'`: rename to `'no leagues are sample data after cutover'` and assert `isSampleLeague('northwoods')` is `false` and `isSampleLeague('mlb_draft')` is `false`.
- `'loads gamelogs by slug, empty for missing'`: use `getGamelog('riley-hasenstab')` for the non-empty case; add `expect(getGamelog('jackson-blakely')).toEqual([])`.
All other tests unchanged (42 players, assigned set, league order still hold).

- [ ] **Step 6: Mark handoff conditions in the spec.** In the spec's "Handoff conditions" section, prefix items 1 and 2 with `**[SATISFIED 2026-07-15]**` and item 3 with `**[SATISFIED 2026-07-15 — empty-fetch gate in build_data]**`, and add one line at the section top: `The Northwoods cutover happened 2026-07-15 (platform: scorebook). The fixture platform remains for tests only and is not referenced by leagues.yaml.`

- [ ] **Step 7: Verify everything.**

```bash
.venv/bin/pytest -q                              # 55 passed, no network (scorebook tests are monkeypatched)
cd site && npx vitest run && npm run build       # 19 passed; build OK
grep -c "Sample data" dist/players/riley-hasenstab/index.html || true   # 0 — banner gone
grep -c "coming online soon" dist/players/jackson-blakely/index.html    # 1 — awaiting stats
```

- [ ] **Step 8: Commit**

```bash
git add pipeline/leagues.yaml pipeline/players.yaml site/src/data data/history site/tests/data.test.ts docs/superpowers/specs/2026-07-14-gt-summer-tracker-design.md
git commit -m "feat!: cutover to live Northwoods data (scorebook) — sample data retired"
```

---

### Task 7: Headshots from Scorebook

**Files:**
- Create: `pipeline/fetch_photos.py`, `site/public/headshots/` (downloaded images)
- Modify: `pipeline/players.yaml` (photo fields), regenerate `site/src/data`
- Test: `pipeline/tests/test_fetch_photos.py`

- [ ] **Step 1: Write the failing test** — `pipeline/tests/test_fetch_photos.py`:

```python
from pipeline import fetch_photos

PLAYERS = [
    {"slug": "a", "summer": {"status": "assigned", "league": "nw", "stats_id": "123"}},
    {"slug": "b", "summer": {"status": "assigned", "league": "nw", "stats_id": "not-numeric"}},
    {"slug": "c", "summer": {"status": "assigned", "league": "other", "stats_id": "9"}},
    {"slug": "d", "summer": {"status": "unassigned"}},
]
LEAGUES = {"nw": {"platform": "scorebook", "api_base": "https://x/api"},
           "other": {"platform": "pending"}}


def test_photo_targets_filters_to_scorebook_numeric_ids():
    targets = fetch_photos.photo_targets(PLAYERS, LEAGUES)
    assert targets == [("a", "https://x/api/player/123")]
```

- [ ] **Step 2: Verify failure**, then **implement** `pipeline/fetch_photos.py`:

```python
"""One-time headshot fetcher.

Downloads player photos hosted by the Scorebook platform into
site/public/headshots/{slug}.jpg and prints the players.yaml lines to add.
Players on other platforms keep the initials placeholder until sourced
(GT athletics / previous-school photos are a manual research task).

Usage: .venv/bin/python -m pipeline.fetch_photos
"""
import sys
import time
from pathlib import Path

import requests

from pipeline import registry

_HEADERS = {"User-Agent": "GT-Summer-Tracker/1.0 (unofficial fan project)"}


def photo_targets(players, leagues):
    out = []
    for p in players:
        summer = p["summer"]
        if summer.get("status") != "assigned":
            continue
        cfg = leagues.get(summer.get("league"), {})
        sid = str(summer.get("stats_id", ""))
        if cfg.get("platform") == "scorebook" and sid.isdigit():
            out.append((p["slug"], f"{cfg['api_base']}/player/{sid}"))
    return out


def main():
    players, leagues = registry.load_all("pipeline/players.yaml", "pipeline/leagues.yaml")
    dest = Path("site/public/headshots")
    dest.mkdir(parents=True, exist_ok=True)
    for slug, url in photo_targets(players, leagues):
        payload = requests.get(url, headers=_HEADERS, timeout=30).json()
        photo_url = (payload.get("player") or {}).get("photo")
        if not photo_url:
            print(f"{slug}: no photo on platform", file=sys.stderr)
            continue
        img = requests.get(photo_url, headers=_HEADERS, timeout=30)
        img.raise_for_status()
        (dest / f"{slug}.jpg").write_bytes(img.content)
        print(f"{slug}: saved -> add to players.yaml:  photo: /headshots/{slug}.jpg")
        time.sleep(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it live**

Run: `.venv/bin/python -m pipeline.fetch_photos`
Expected: two lines (jamie-vicens, riley-hasenstab) with saved photos; verify both JPGs exist and are >5KB (`ls -la site/public/headshots`).

- [ ] **Step 4: Wire the photos.** Add to the two players in `pipeline/players.yaml`: `photo: /headshots/jamie-vicens.jpg` / `photo: /headshots/riley-hasenstab.jpg` (top-level key on each player entry, alongside `position`). Regenerate: `.venv/bin/python -m pipeline.build_data`. Spot-check: `grep -o '"photo": "[^"]*"' site/src/data/players.json | sort -u | head` shows the two paths.

- [ ] **Step 5: Verify site renders photos.** `cd site && npm run build && grep -c 'headshots/riley-hasenstab.jpg' dist/players/riley-hasenstab/index.html` → ≥1 (also appears in roster table + league page).

- [ ] **Step 6: Full suites** — `.venv/bin/pytest -q` → `56 passed`; `cd site && npx vitest run` → 19 passed.

- [ ] **Step 7: Commit**

```bash
git add pipeline/fetch_photos.py pipeline/tests/test_fetch_photos.py pipeline/players.yaml site/public/headshots site/src/data data/history
git commit -m "feat: scorebook headshot fetcher; real photos for active NWL players"
```

---

### Task 8: Nightly GitHub Actions workflow

**Files:**
- Create: `.github/workflows/nightly.yml`

- [ ] **Step 1: Create the workflow** (implements the spec's workflow-authoring note: the commit step must survive a failed-partial build):

```yaml
name: Nightly stats refresh

on:
  schedule:
    - cron: "0 8 * * *"        # ~4am ET, all leagues' games finished
  workflow_dispatch:

concurrency:
  group: nightly
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Tests (offline, must pass before publishing)
        run: python -m pytest -q
      - name: Build data
        id: build
        run: python -m pipeline.build_data
        continue-on-error: true    # failed-partial still wrote carried-forward outputs
      - name: Commit refreshed data
        if: always()
        run: |
          git config user.name "gt-summer-tracker-bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add site/src/data data/history
          if git diff --cached --quiet; then
            echo "No data changes tonight."
          else
            git commit -m "data: nightly refresh $(date -u +%F)"
            git push
          fi
      - name: Surface failed-partial
        if: steps.build.outcome == 'failure'
        run: |
          echo "::warning::build_data exited failed-partial — some league kept previous data. See build step logs."
          exit 1
```

- [ ] **Step 2: Validate the YAML parses**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/nightly.yml')); print('yaml ok')"`
Expected: `yaml ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/nightly.yml
git commit -m "ci: nightly data refresh workflow (publish survives failed-partial)"
```

---

## Activation checklist (user actions — NOT executable tasks)

The workflow and deploy only go live once the repo is hosted. These need Cole's accounts and consent; the coordinator asks before doing any of them:

1. **GitHub:** create a repo (e.g. `gt-summer-tracker`) and push `main`. (`gh repo create` if authed, else manual.) The nightly workflow activates automatically; run it once via *Actions → Nightly stats refresh → Run workflow* to verify.
2. **Vercel:** import the GitHub repo; set **Root Directory = `site`** (framework: Astro, auto-detected). Every nightly data commit then auto-deploys.
3. Optional: custom domain on Vercel.

## Explicitly out of scope for this plan

- **Roster research pass** (the other ~38 players' summer teams, incl. resolving Jackson Blakely) — a research effort, not code; the registry + scorebook scraper accept new assignments as one-line YAML edits. Tip recorded: NWL's `/api/player/{id}` exposes `college`, so a scripted sweep of NWL rosters can find GT players cheaply once roster endpoints are mapped; other leagues need their own scouting first (each league = its own platform investigation + possible new scraper module).
- Additional league scrapers (MLB Draft League for Spivey, etc.) — same pattern as Tasks 1+4 per platform, once scouted.
- GT athletics / previous-school headshots for non-NWL players.

---

## Self-review checklist (run after writing, fixed inline)

1. **Spec coverage:** handoff condition 1 (banner keyed on platform — auto-clears at cutover, verified in Task 6 Step 7) ✓; condition 2 (reset before first real build — Task 6 Step 3) ✓; condition 3 (empty-fetch gate — Task 5) ✓; nightly workflow `if: always()` note ✓ (Task 8); polite scraping (1 rps throttle, UA header) ✓; fixtures-not-live-HTTP testing ✓ (monkeypatched `_get_json`); Tier semantics unchanged (NWL stays tier 1 with full tables confirmed).
2. **Placeholder scan:** Task 2 Step 3's validate snippet says "adapt to the file's existing structure" — acceptable because the exact current shape came from a review-fix commit; the intent, exception types, and behavior are fully specified. No TBDs elsewhere.
3. **Type consistency:** canonical rows gain optional `pa`/`bf` keys (Tasks 2-4 agree); `ip_str_to_outs` name consistent across stats_math/validate/scorebook; `SCRAPERS["scorebook"]` key matches leagues.yaml `platform: scorebook` (Task 6); site `data.test.ts` uses only existing accessors. Test-count ledger: 47 → T2: 50 → T3: 51 → T4: 54 → T5: 55 → T7: 56.
