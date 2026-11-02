#!/usr/bin/env python3
"""Green · level 2 · zone plan of the whole district (w51), imported by green_net.py (local streets) and green_build.py.

Zones = the approved level-0 scheme (district/green_v0.json, 259 zones that tile the district). Each zone gets the v1 rules
(CONTRACT §3) of its use; densities start from the scheme's (residents_per_ha / 2.5 = homes_per_ha, jobs_per_ha) and are
scaled in green_build.py to the district targets on net block land. Floors come from the scheme's «floors_typical», the
lowest floor count kept so that floors × storey height ≤ 28 m (22 m fire gaps between buildings over 28 m, Gate lesson).
Changes against the scheme are listed in SCHEME_CHANGES (shown in the report).
"""
import copy
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import green_common as C  # noqa: E402

V0 = C.V0
GREEN = C.GREEN
rules = C.rules

# local street grid per use: (spacing along the grid's first axis, spacing across), metres between street axes
GRID = {"residential_mid": (190.0, 160.0), "residential_low": (170.0, 125.0), "business": (180.0, 160.0),
        "mixed_centre": (165.0, 150.0), "medical": (330.0, 330.0), "logistics": (430.0, 300.0)}
DEV_USES = set(GRID) | {"sport"}
RES_PER_HOME = 2.5               # rule 24: residents = GFA / 30, homes = GFA / 75 (targets.home_m2)
SCHEME_CHANGES = []


def floors_of(d, default):
    m = re.match(r"\s*(\d+)\s*[–-]\s*(\d+)", str((d or {}).get("floors_typical") or ""))
    return [int(m.group(1)), int(m.group(2))] if m else list(default)


def use_rules(zid, use, d):
    """v1 rules of a zone from its use and the scheme density d (homes = residents / 2.5; scaled later)."""
    res = float(d.get("residents_per_ha") or 0.0)
    h = round(res / RES_PER_HOME, 1) if res else 0.0
    j = float(d.get("jobs_per_ha") or 0.0)
    if use == "residential_mid":
        fl = floors_of(d, [3, 6])
        return rules(fl, round(fl[1] * 3.6 + 4), 0.9, [120, 180], "perimeter", "multi", h, j or 7)
    if use == "residential_low":
        fl = floors_of(d, [2, 4])
        return rules(fl, round(fl[1] * 3.6 + 4), 0.45, [80, 150], "rows", "multi", h, j or 5)
    if use == "business":
        fl = floors_of(d, [3, 9])
        return rules(fl, round(fl[1] * 4.43 + 4), 1.4, [110, 170], "perimeter", "multi", 0, j or 100)
    if use == "mixed_centre":
        fl = floors_of(d, [5, 12])
        return rules(fl, min(48, round(fl[1] * 3.9 + 4)), 1.8, [110, 160], "perimeter", "underground", h, j or 90)
    if use == "medical":
        fl = floors_of(d, [3, 7])
        return rules(fl, round(fl[1] * 4.0 + 4), 1.0, [200, 400], "campus", "multi", 0, j or 150)
    if use == "logistics":
        return rules([1, 2], 18, 0.45, [250, 450], "industrial", "surface", 0, j or 40, setback=10.0)
    if use == "sport":
        return {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": j}
    if use == "village_existing":
        return {"lot_split": "houses", "floors": [1, 2], "height_cap_m": 9, "far": 0.25, "block_side_m": None, "setback_m": 3,
                "parking": {"per_home": 1.0, "type": "surface"}, "homes_per_ha": None, "jobs_per_ha": None}
    return {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0}


def plan():
    """[{id, use, name_ru, poly, years, rules, why, density, src}] covering the district without overlaps."""
    out = []
    for z in V0["zones"]:
        p = Polygon(z["polygon"]).buffer(0).intersection(GREEN).buffer(0)
        if p.area < 200.0:
            continue
        d = z.get("density") or {}
        r = use_rules(z["id"], z["use"], d)
        out.append({"id": z["id"], "use": z["use"], "name_ru": z["name_ru"], "poly": p, "years": list(z["years"]),
                    "rules": r, "why": z.get("why", "схема уровня 0"), "density": d, "src": "v0"})
    return out


ZPLAN = plan()
ZBY = {z["id"]: z for z in ZPLAN}
DEV = unary_union([z["poly"] for z in ZPLAN if z["use"] in GRID])
