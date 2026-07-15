"""Sanity gate: errors block a league from publishing; warnings just log."""
from pipeline import stats_math as sm


def check_league(league_key, stats, assigned_players, previous):
    errors, warnings = [], []
    batting, pitching = stats.get("batting", []), stats.get("pitching", [])

    if not batting and not pitching:
        errors.append(f"{league_key}: both league tables empty")
        return errors, warnings

    for row in batting:
        rates = sm.batting_rates(row)
        for m in ("avg", "obp", "slg"):
            v = rates.get(m)
            if v is not None and not (0 <= v <= 1 if m != "slg" else 0 <= v <= 4):
                errors.append(f"{league_key}: {row['stats_id']} impossible {m}={v:.3f}")
    for row in pitching:
        if (row.get("er", 0) or 0) < 0 or (row.get("ip_outs", 0) or 0) < 0:
            errors.append(f"{league_key}: {row['stats_id']} negative pitching counts")

    ids = {r["stats_id"] for r in batting} | {r["stats_id"] for r in pitching}
    bat_by_id = {r["stats_id"]: r for r in batting}
    for p in assigned_players:
        sid = p["summer"]["stats_id"]
        if sid not in ids:
            warnings.append(f"{league_key}: assigned player {sid} not found in league tables")
            continue
        prev = previous.get(p["slug"])
        if prev and prev.get("hitting") and sid in bat_by_id:
            for key, old in prev["hitting"]["counting"].items():
                new = bat_by_id[sid].get(key)
                if isinstance(old, int) and isinstance(new, int) and new < old:
                    errors.append(
                        f"{league_key}: {sid} counting stat {key} decreased {old}->{new}")
    return errors, warnings
