"""Shared helpers for the Alatau City synthetic-data generator (deterministic, seed-fixed)."""
import csv, json, math, os
import numpy as np

SEED = 2050
Y0, Y1 = 2025, 2050          # Y0: first year of the data tables = the existing city (C# TwinData.Y0); the timeline on screen starts in 2026
YEARS = list(range(Y0, Y1 + 1))
NY = len(YEARS)
AFTER = 2099
DISTRICTS = ["Gate", "Golden", "Growing", "Green"]
SCENARIOS = ["base", "fast", "slow", "infra"]          # same order as the C# enum Scenario {Base, Fast, Slow, InfraFirst}
DATA_VERSION = "twin-data 1.0 · seed 2050 · 06.10.2026"


def mathf_round(v):
    """Unity Mathf.RoundToInt == .NET Math.Round (banker's rounding) == Python round()."""
    return int(round(v))


def effective_year(year, use, source, scenario):
    """Exact port of TwinScenario.EffectiveYear (C#). Keep both in sync."""
    if year <= Y0 or source == "existing_osm":
        return year
    dy = year - Y0
    if scenario == "fast":
        return Y0 + max(1, mathf_round(dy * 0.75))
    if scenario == "slow":
        e = Y0 + mathf_round(dy * 1.3)
        return AFTER if e > Y1 else e
    if scenario == "infra":
        return year + 2 if use == "housing" and year <= 2036 else year
    return year


def load_buildings(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "bid": int(r["bid"]), "id": r["id"], "district": r["district"], "kind": r["kind"], "use": r["use"],
                "source": r["source"], "year": int(r["year"]), "floors": int(float(r["floors"] or 0)),
                "h": float(r["height_m"] or 0), "gfa": float(r["gfa_m2"] or 0), "x": float(r["x"]), "z": float(r["z"]),
            })
    for b in rows:
        b["eff"] = {s: effective_year(b["year"], b["use"], b["source"], s) for s in SCENARIOS}
        b["d"] = DISTRICTS.index(b["district"]) if b["district"] in DISTRICTS else -1
    return rows


def yi(y):
    return min(max(y - Y0, 0), NY - 1)


def dump(obj, path, about):
    obj = {"about": about, "version": DATA_VERSION, **obj}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path)


def r1(v):
    return float(round(float(v), 1))


def r3(v):
    return float(round(float(v), 3))
