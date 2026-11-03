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
        "mixed_centre": (165.0, 150.0), "medical": (330.0, 330.0), "logistics": (430.0, 300.0),
        "resort": (220.0, 180.0)}
DEV_USES = set(GRID) | {"sport"}
RES_PER_HOME = 2.5               # rule 24: residents = GFA / 30, homes = GFA / 75 (targets.home_m2)
SCHEME_CHANGES = []
RESORT_CAP_M = 48.0              # resort buildings under the 50 m of heights.airfield_height_threshold_m (Жетыген in 30 km)
RESORT_FROM_WATER_M = 50.0       # flood.resort_from_waterline_m: resort land keeps this far from the water (the band → shore park)

# owner 03.11.2026: the resort district receives 4 mln tourists a year by 2050 with the twin's 66 000 leisure jobs (hotels,
# resorts and attractions, ≈ 7.9 mln m² at 120 m² per job). The scheme's resort zones (built as offices before) and the two
# low-rise zones by the resorts become zones of use «resort»; their homes go to the other residential zones. Per zone: name,
# floors, lot split, block sides, and `far_dry` — the floor area per m² of its dry net land (above the design flood, off the
# 50 m shore band) that shares the district's leisure floor area among them (модель qTwin)
RESORT = {
    "ircc": ("Курортно-развлекательный центр IRCC: отели, казино, океанариум, аквапарк", [4, 12], "campus", [150, 250], 1.6,
             "генплан: 1 353 тыс. м² на 100 га, 2030–2040 — казино, океанариум, аквапарк, отели; 4–12 этажей до 48 м"),
    "resort_e": ("Отели и курорты Восточного берега", [2, 8], "campus", [150, 250], 1.0,
                 "отели и санатории вдоль Восточной береговой, пляжи — в береговом парке перед ними; 2–8 этажей"),
    "theme": ("Тематический парк: аттракционы, аквапарк, отели парка", [1, 4], "campus", [150, 250], 0.55,
              "«казахстанский аналог Диснейленда»: павильоны аттракционов, крытый аквапарк, отели парка; 1–4 этажа"),
    "res_e": ("Курортные виллы и апарт-отели Восточного берега", [2, 4], "rows", [100, 180], 0.6,
              "было малоэтажное жильё у курортов (решение владельца 03.11.2026: курортная земля) — виллы и апарт-отели 2–4 этажа"),
    "res_lake": ("Виллы и апарт-отели у залива", [2, 4], "rows", [100, 180], 0.6,
                 "было малоэтажное жильё у залива (решение владельца 03.11.2026: курортная земля) — виллы и апарт-отели 2–4 этажа"),
}
# new resort zones cut from the scheme's zones: (id, from zone, polygon, name, floors, split, block, far_dry, why)
RESORT_CUTS = [
    ("expo_hotels", "expo_1", [(3150.0, 22300.0), (3800.0, 22300.0), (3800.0, 23500.0), (3150.0, 23500.0)],
     "Отели и туристический центр у Выставки", [3, 9], "campus", [150, 250], 0.9,
     "отели и апарт-отели выставочного квартала и туристического центра Iconic Building-2, у станции «Выставка» и пристани у Конаева"),
    ("golf_club", "golf_1", [(15150.0, 16950.0), (15480.0, 16950.0), (15480.0, 17260.0), (15150.0, 17260.0)],
     "Клуб и гольф-отель Восточного гольф-клуба", [2, 4], "campus", [150, 250], 0.5,
     "клубный дом и гольф-отель у Восточной береговой (клуб выше 485 м, схема)"),
]


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
    if use == "resort":
        # hotels, resorts and attractions (jobs: the twin's leisure m² per job; no homes): floors and split per zone (RESORT),
        # FAR and jobs per ha set in green_build.py from the district's leisure floor area
        fl = list(d.get("_floors") or floors_of(d, [2, 8]))
        return rules(fl, min(RESORT_CAP_M, round(fl[1] * 3.73 + 4)), 0.9, list(d.get("_block") or [150, 250]),
                     d.get("_split") or "campus", "multi", 0, j or 60.0)
    if use == "sport":
        return {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": j}
    if use == "village_existing":
        return {"lot_split": "houses", "floors": [1, 2], "height_cap_m": 9, "far": 0.25, "block_side_m": None, "setback_m": 3,
                "parking": {"per_home": 1.0, "type": "surface"}, "homes_per_ha": None, "jobs_per_ha": None}
    return {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0}


def plan():
    """[{id, use, name_ru, poly, years, rules, why, density, src}] covering the district without overlaps."""
    out = []
    zones = []
    cuts = {}
    for cid, base, pts, *_ in RESORT_CUTS:
        cuts.setdefault(base, []).append((cid, Polygon(pts)))
    for z in V0["zones"]:
        p = Polygon(z["polygon"]).buffer(0).intersection(GREEN).buffer(0)
        z = dict(z, density=dict(z.get("density") or {}))
        for cid, box_ in cuts.get(z["id"], []):
            q = p.intersection(box_).buffer(0)
            p = p.difference(box_).buffer(0)
            rc = next(c for c in RESORT_CUTS if c[0] == cid)
            zones.append((dict(id=cid, use="resort", name_ru=rc[3], years=list(z["years"]), why=MODEL_WHY + rc[8],
                               density={"_floors": rc[4], "_split": rc[5], "_block": rc[6], "_far_dry": rc[7], "_from": z["id"]}), q))
            SCHEME_CHANGES.append((cid, f"{q.area / 1e4:.1f} га из зоны {z['id']} — курортная зона «{rc[3]}» (решение владельца "
                                        "03.11.2026: 66 тыс. мест отдыха в Green к 2050 г.)"))
        if z["id"] in RESORT:
            nm, fl, sp, bl, far_d, why = RESORT[z["id"]]
            SCHEME_CHANGES.append((z["id"], f"{z['use']} → resort «{nm}»: {why}" +
                                   ("" if "владельца" in why else " (решение владельца 03.11.2026)")))
            z = dict(z, use="resort", name_ru=nm, why=MODEL_WHY + why + "; схема: " + z.get("why", ""),
                     density={"_floors": fl, "_split": sp, "_block": bl, "_far_dry": far_d, "_was_use": z["use"]})
        zones.append((z, p))
    # the shore band of resort land (flood.resort_from_waterline_m) joins the coast park: no resort building nearer the water
    shore = None
    if any(z["use"] == "resort" for z, _ in zones):
        _w = [g for g, pp in C.layer_in("water", GREEN.buffer(200))
              if g.geom_type in ("Polygon", "MultiPolygon") and pp.get("class") != "swimming_pool"]
        shore = unary_union(_w).buffer(RESORT_FROM_WATER_M) if _w else None
    for z, p in zones:
        if p.is_empty or p.area < 200.0:
            continue
        if z["use"] == "resort" and shore is not None and p.intersects(shore):
            band = p.intersection(shore).buffer(0)
            if band.area >= 200.0:
                p = p.difference(shore).buffer(0)
                out.append({"id": z["id"] + "_shore", "use": "waterfront", "name_ru": "Береговой парк у курорта (полоса 50 м от воды)",
                            "poly": band, "years": list(z["years"]), "rules": {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0},
                            "why": f"flood.resort_from_waterline_m: курортные здания не ближе {RESORT_FROM_WATER_M:.0f} м от уреза — "
                                   "полоса у воды — набережная и пляж", "density": {}, "src": "v0"})
                SCHEME_CHANGES.append((z["id"] + "_shore", f"{band.area / 1e4:.1f} га у воды из зоны {z['id']} — береговой парк "
                                                         f"(курорт не ближе {RESORT_FROM_WATER_M:.0f} м от уреза)"))
        d = z.get("density") or {}
        r = use_rules(z["id"], z["use"], d)
        out.append({"id": z["id"], "use": z["use"], "name_ru": z["name_ru"], "poly": p, "years": list(z["years"]),
                    "rules": r, "why": z.get("why", "схема уровня 0"), "density": d, "src": "v0"})
    return out


MODEL_WHY = C.MODEL + ": "


ZPLAN = plan()
ZBY = {z["id"]: z for z in ZPLAN}
DEV = unary_union([z["poly"] for z in ZPLAN if z["use"] in GRID])
