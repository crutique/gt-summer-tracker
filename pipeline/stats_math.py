"""Rate-stat math on canonical counting rows. All derivations per spec."""


def _get(row, key):
    return row.get(key, 0) or 0


def pa(b):
    return _get(b, "ab") + _get(b, "bb") + _get(b, "hbp") + _get(b, "sf") + _get(b, "sh")


def bf(p):
    # BF approx = outs (3*IP) + H + BB + HB  (spec: Percentile engine / derived inputs)
    return _get(p, "ip_outs") + _get(p, "h") + _get(p, "bb") + _get(p, "hb")


def _div(num, den):
    return num / den if den else None


def batting_rates(b):
    ab, h = _get(b, "ab"), _get(b, "h")
    obp_den = ab + _get(b, "bb") + _get(b, "hbp") + _get(b, "sf")
    tb = h + _get(b, "d") + 2 * _get(b, "t") + 3 * _get(b, "hr")
    plate = pa(b)
    avg, obp, slg = _div(h, ab), _div(h + _get(b, "bb") + _get(b, "hbp"), obp_den), _div(tb, ab)
    return {
        "avg": avg, "obp": obp, "slg": slg,
        "ops": (obp + slg) if obp is not None and slg is not None else None,
        "kPct": _div(_get(b, "k"), plate), "bbPct": _div(_get(b, "bb"), plate),
    }


def pitching_rates(p):
    outs, faced = _get(p, "ip_outs"), bf(p)
    ip = outs / 3 if outs else 0
    ab_faced = faced - _get(p, "bb") - _get(p, "hb")
    return {
        "era": _div(9 * _get(p, "er"), ip), "whip": _div(_get(p, "bb") + _get(p, "h"), ip),
        "kPct": _div(_get(p, "k"), faced), "bbPct": _div(_get(p, "bb"), faced),
        "hr9": _div(9 * _get(p, "hr"), ip), "k9": _div(9 * _get(p, "k"), ip),
        "bb9": _div(9 * _get(p, "bb"), ip), "oppAvg": _div(_get(p, "h"), ab_faced),
    }


def outs_to_ip_str(outs):
    return f"{outs // 3}.{outs % 3}"
