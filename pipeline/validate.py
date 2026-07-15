"""Sanity gate: errors block a league from publishing; warnings just log."""
from pipeline import stats_math as sm

_PIT_COUNT_KEYS = ("g", "gs", "ip_outs", "w", "l", "sv", "hld", "h", "r", "er", "bb", "k", "hb", "hr")


def _decrease_errors(league_key, sid, prev_counting, new_row):
    errors = []
    for key, old in prev_counting.items():
        if key == "ip":
            new = new_row.get("ip_outs")
            try:
                old_outs = sm.ip_str_to_outs(old)
            except (ValueError, TypeError):
                continue          # malformed previous value — skip, never crash the gate
            if isinstance(new, int) and new < old_outs:
                errors.append(
                    f"{league_key}: {sid} counting stat ip decreased {old}->{sm.outs_to_ip_str(new)}")
            continue
        new = new_row.get(key)
        if isinstance(old, int) and isinstance(new, int) and new < old:
            errors.append(f"{league_key}: {sid} counting stat {key} decreased {old}->{new}")
    return errors


def check_league(league_key, stats, assigned_players, previous):
    errors, warnings = [], []
    batting, pitching = stats.get("batting", []), stats.get("pitching", [])

    if not batting or not pitching:
        errors.append(f"{league_key}: league table(s) empty")
        return errors, warnings

    for row in batting:
        rates = sm.batting_rates(row)
        for m in ("avg", "obp", "slg"):
            v = rates.get(m)
            if v is not None and not (0 <= v <= 1 if m != "slg" else 0 <= v <= 4):
                errors.append(f"{league_key}: {row['stats_id']} impossible {m}={v:.3f}")
    for row in pitching:
        if any((row.get(k_) or 0) < 0 for k_ in _PIT_COUNT_KEYS):
            errors.append(f"{league_key}: {row['stats_id']} negative pitching counts")

    ids = {r["stats_id"] for r in batting} | {r["stats_id"] for r in pitching}
    bat_by_id = {r["stats_id"]: r for r in batting}
    pit_by_id = {r["stats_id"]: r for r in pitching}
    for p in assigned_players:
        sid = p["summer"]["stats_id"]
        if sid not in ids:
            warnings.append(f"{league_key}: assigned player {sid} not found in league tables")
            continue
        prev = previous.get(p["slug"]) or {}
        if prev.get("hitting") and sid in bat_by_id:
            errors.extend(_decrease_errors(league_key, sid,
                                           prev["hitting"].get("counting", {}), bat_by_id[sid]))
        if prev.get("pitching") and sid in pit_by_id:
            errors.extend(_decrease_errors(league_key, sid,
                                           prev["pitching"].get("counting", {}), pit_by_id[sid]))
    return errors, warnings
