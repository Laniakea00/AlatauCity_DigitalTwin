"""The 4 scenario years [base, fast, slow, infra] (UnityProject/Tools/twin_gen/twin_common.py, TwinScenario.EffectiveYear)."""
Y0, Y1, AFTER = 2025, 2050, 2099
SCENARIOS = ["base", "fast", "slow", "infra"]
EXISTING = [2025, 2025, 2025, 2025]
CHECK_YEARS = [2026, 2030, 2034, 2040, 2050]


def effective_year(year, use="road", source="new", scenario="base"):
    """Exact port of twin_common.effective_year (keep in sync)."""
    if year <= Y0 or source == "existing_osm":
        return year
    dy = year - Y0
    if scenario == "fast":
        return Y0 + max(1, int(round(dy * 0.75)))
    if scenario == "slow":
        e = Y0 + int(round(dy * 1.3))
        return AFTER if e > Y1 else e
    if scenario == "infra":
        return year + 2 if use == "housing" and year <= 2036 else year
    return year


def years4(base, use="road", source="new"):
    """[base, fast, slow, infra] for an object whose base-scenario year is `base`."""
    if base is None:
        return list(EXISTING)
    base = int(base)
    if base <= Y0:
        return list(EXISTING)
    return [effective_year(base, use, source, s) for s in SCENARIOS]


def norm4(y, use="road"):
    """Any year spec (int, [y0, y1] of a level-0 axis, or 4 values) → 4 scenario years."""
    if y is None:
        return list(EXISTING)
    if isinstance(y, (int, float)):
        return years4(int(y), use)
    y = list(y)
    if len(y) == 4:
        return [int(v) for v in y]
    return years4(int(y[0]), use)


def standing(y4, year, scenario=0):
    """Is an object with years y4 standing in `year` (scenario index 0..3)?"""
    return y4 is not None and int(y4[scenario]) <= year


def earliest(*ys):
    """Element-wise minimum of several 4-year lists."""
    ys = [y for y in ys if y]
    return [min(v[i] for v in ys) for i in range(4)] if ys else list(EXISTING)


def latest(*ys):
    ys = [y for y in ys if y]
    return [max(v[i] for v in ys) for i in range(4)] if ys else list(EXISTING)
