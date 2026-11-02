#!/usr/bin/env python3
"""Gate · level 2 · zone plan of the whole district (w47), imported by gate_net.py (local street grid) and gate_build.py.

Zones = the approved level-0 scheme (district/gate_v0.json, 95 zones that tile the district) outside the trial quarter, plus the
trial quarter's own zones inside it (level 1, gate_trial_build.py). Each zone gets the v1 rules (CONTRACT §3) of its use;
densities start from the scheme's and are scaled in gate_build.py to the district targets. Changes against the scheme are
listed in CHANGES (shown in the report).
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import gate_common as C  # noqa: E402
import gate_trial_build as T  # noqa: E402

V0 = C.spec_v0()
GATE = T.GATE_POLY
TRIAL = T.AREA
rules = T.rules

# grid of local streets per use: (spacing along the grid's first axis, spacing across), metres between street axes
GRID = {"residential_high": (165.0, 150.0), "residential_mid": (190.0, 160.0), "residential_low": (170.0, 125.0),
        "waterfront": (190.0, 160.0), "business": (165.0, 150.0), "mixed_centre": (165.0, 150.0), "medical": (330.0, 330.0),
        "logistics": (430.0, 300.0), "campus": (300.0, 300.0)}
DEV_USES = set(GRID) | {"industry", "sport"}


def use_rules(use, d):
    """v1 rules of a zone from its use and the scheme density d (homes_per_ha, jobs_per_ha as given; scaled later)."""
    h, j = d.get("homes_per_ha"), d.get("jobs_per_ha")
    if use == "residential_high":
        return rules([9, 14], 50, 1.8, [110, 150], "perimeter", "underground", h or 149, j or 30)
    if use == "residential_mid":
        return rules([5, 8], 28, 1.1, [120, 180], "perimeter", "multi", h or 72, j or 10)
    if use == "residential_low":
        return rules([2, 4], 15, 0.4, [80, 150], "rows", "multi", h or 38, j or 3)
    if use == "waterfront":
        return rules([4, 6], 21, 0.7, [120, 180], "perimeter", "multi", h or 35, j or 7)
    if use == "business":
        return rules([4, 9], 35, 1.4, [110, 160], "perimeter", "multi", h or 0, j or 120)
    if use == "mixed_centre":
        return rules([5, 12], 45, 1.8, [110, 160], "perimeter", "underground", h or 60, j or 117)
    if use == "medical":
        return rules([3, 8], 35, 0.9, [200, 400], "campus", "multi", 0, j or 110)
    if use == "logistics":
        return rules([1, 1], 18, 0.45, [250, 450], "industrial", "multi", 0, j or 40, setback=10.0)
    if use == "industry":
        return rules([1, 2], 18, 0.35, [250, 450], "industrial", "multi", 0, j or 35, setback=10.0)
    if use == "sport":
        return {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": j or 10}
    if use == "village_existing":
        return {"lot_split": "houses", "floors": [1, 2], "height_cap_m": 9, "far": 0.25, "block_side_m": None, "setback_m": 3,
                "parking": {"per_home": 1.0, "type": "surface"}, "homes_per_ha": None, "jobs_per_ha": None}
    return {"lot_split": "none"}


CHANGES = []            # trial zones changed at level 2: (id, why)
SCHEME_CHANGES = [("residential_low, logistics, industry", "стоянки модели — в многоуровневых паркингах, не открытыми полями "
                                                           "(уровень 2: модельные стоянки под землёй или в паркингах)")]
PLANT_AS_IS = {"i_pepsico": "площадка завода PepsiCo — как есть (здание OSM), без модельных цехов: зона со всех сторон "
                            "окружена жильём r_mid_s_5, СЗЗ модельных цехов (правило 15) заняла бы половину площадки"}


def plan():
    """[{id, use, name_ru, poly, years, rules, why, density, src}] covering the district without overlaps."""
    out = []
    # 1. the trial quarter's zones inside the trial area (level-1 design), except its catch-all remainder
    taken = Polygon()
    for z in T.ZONES:
        if z["id"].startswith("u_motorways"):
            continue
        p = Polygon(z["polygon"]).buffer(0)
        r = copy.deepcopy(z["rules"])
        if (r.get("parking") or {}).get("type") == "surface" and z["use"] != "village_existing":
            # level 2: model car parks of the new city go under ground or into multi-storey decks (no surface fields)
            r["parking"]["type"] = "multi"
            CHANGES.append((z["id"], "стоянка: открытая → многоуровневая (в Gate модельные стоянки — под землёй или в паркингах)"))
        out.append({"id": z["id"], "use": z["use"], "name_ru": z["name_ru"], "poly": p, "years": z["years"],
                    "rules": r, "why": z["why"], "density": z.get("density"), "src": "trial"})
        out[-1].update({k: z[k] for k in ("facility", "facilities") if z.get(k)})
        taken = taken.union(p)
    trial_rest = TRIAL.difference(taken).buffer(0)
    # 2. the scheme's zones outside the trial area
    for z in V0["zones"]:
        p = Polygon(z["polygon"]).buffer(0).difference(TRIAL).buffer(0)
        if p.area < 200.0:
            continue
        d = z.get("density") or {}
        r = use_rules(z["use"], d)
        if z["id"] in PLANT_AS_IS:
            # the existing plant's site: no model sheds around the plant (its building stays as OSM has it); the plant's
            # sanitary gap to the scheme's housing all round would take half of the site
            r.update({"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0})
            SCHEME_CHANGES.append((z["id"], PLANT_AS_IS[z["id"]]))
        out.append({"id": z["id"], "use": z["use"], "name_ru": z["name_ru"], "poly": p, "years": z["years"],
                    "rules": r, "why": z.get("why", "схема уровня 0"), "density": d, "src": "v0"})
    # 3. what is left of the trial area (expressways, interchange field, strips between zones): one utility zone, as in the trial
    out.append({"id": "u_motorways_trial", "use": "utility", "name_ru": "Полосы отвода А-3 и БАКАД, поле развязок (пробная зона)",
                "poly": trial_rest, "years": [2025, 2025], "rules": {"lot_split": "none"},
                "why": "остаток пробной зоны: проезжие части, съезды, поле клеверной развязки; блоки здесь не строятся", "src": "trial"})
    return out


ZPLAN = plan()
ZBY = {z["id"]: z for z in ZPLAN}
DEV = unary_union([z["poly"] for z in ZPLAN if z["use"] in GRID and z["src"] == "v0"])
