#!/usr/bin/env python3
"""Growing-West · level 2 · zone plan (w52), imported by growing_w_net.py (local streets) and growing_w_build.py.

Zones = the approved level-0 scheme (district/growing_w_v0.json, 234 zones that tile the district). Each zone gets the v1 rules
(CONTRACT §3) of its use; densities start from the scheme's and are scaled in growing_w_build.py to the district targets.
Changes against the scheme are listed in CHANGES (shown in numbers.md).
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import growing_w_common as C  # noqa: E402

V0 = C.spec_v0()

# grid of local streets per use: (spacing along the grid's first axis, spacing across), metres between street axes
GRID = {"residential_high": (165.0, 150.0), "residential_mid": (185.0, 160.0), "residential_low": (170.0, 125.0),
        "business": (200.0, 165.0), "mixed_centre": (160.0, 140.0), "campus": (320.0, 260.0),
        "logistics": (430.0, 320.0), "industry": (450.0, 340.0)}
DEV_USES = set(GRID)
RES_USES = ("residential_high", "residential_mid", "residential_low", "mixed_centre", "waterfront")


def rules(floors, cap, far, block, split, park_type, homes, jobs, setback=6.0, per_home=1.0):
    """parking.per_home 1.0: residential.parking_per_apartment, class III min (С08-11); office / retail parking None while
    malls.parking_office / parking_mall are not_verified (CONTRACT §8 defaults)."""
    return {"floors": floors, "height_cap_m": cap, "far": far, "block_side_m": block, "setback_m": setback,
            "lot_split": split, "parking": {"per_home": per_home, "per_100m2_office": None, "per_100m2_retail": None,
                                            "type": park_type}, "homes_per_ha": homes, "jobs_per_ha": jobs}


def use_rules(use, d):
    """v1 rules of a zone from its use and the scheme density d (homes_per_ha, jobs_per_ha as given; scaled later). Every
    height cap stays under 50 m: the whole district lies within 30 km of the new airport and of the Zhetygen airfield (rule 16,
    heights.airfield_height_threshold_m) — no building needs the «нужно согласование» mark."""
    h, j = d.get("homes_per_ha"), d.get("jobs_per_ha")
    if use == "residential_high":
        return rules([6, 12], 45, 1.6, [110, 160], "perimeter", "underground", h or 94, j or 10)
    if use == "residential_mid":
        return rules([5, 8], 28, 1.1, [120, 180], "perimeter", "multi", h or 57, j or 8)
    if use == "residential_low":
        return rules([2, 3], 12, 0.4, [80, 150], "rows", "multi", h or 21, j or 4)
    if use == "business":
        return rules([3, 6], 30, 0.9, [120, 180], "perimeter", "multi", h or 0, j or 50)
    if use == "mixed_centre":
        return rules([5, 12], 45, 1.6, [110, 160], "perimeter", "underground", h or 62, j or 100)
    if use == "campus":
        return rules([3, 6], 28, 0.6, [200, 320], "campus", "multi", 0, j or 30)
    if use == "logistics":
        return rules([1, 1], 18, 0.45, [250, 450], "industrial", "multi", 0, j or 20, setback=10.0)
    if use == "industry":
        return rules([1, 2], 18, 0.35, [250, 450], "industrial", "multi", 0, j or 25, setback=10.0)
    if use == "village_existing":
        return {"lot_split": "houses", "floors": [1, 2], "height_cap_m": 9, "far": 0.25, "block_side_m": None, "setback_m": 3,
                "parking": {"per_home": 1.0, "type": "surface"}, "homes_per_ha": None, "jobs_per_ha": None}
    if use == "utility":
        return {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": j or 0}
    return {"lot_split": "none"}


CHANGES = []            # (zone ids, why) against the level-0 scheme


def plan():
    """[{id, use, name_ru, poly, years, rules, why, density, src}] of the scheme zones (v1 uses and rules), clipped to the
    district; overlaps are resolved later by the builder."""
    out = []
    river = []
    for z in V0["zones"]:
        p = Polygon(z["polygon"], z.get("holes") or []).buffer(0).intersection(C.POLY)
        if p.is_empty or p.area < 1.0:
            continue
        use = z["use"]
        why = z.get("why", "")
        if z["id"].startswith("river_kaskelen"):
            # the river zone holds no homes or jobs (scheme: «только парк, набережная и велодорожка»): a park, not the
            # residential use «waterfront» of the land tools
            use = "park"
            river.append(z["id"])
        d = dict(z.get("density") or {})
        out.append({"id": z["id"], "use": use, "name_ru": z["name_ru"], "poly": p, "years": list(z["years"]),
                    "rules": use_rules(use, d), "why": why, "density": d, "src": "v0"})
    if river:
        CHANGES.append((", ".join(river), "использование waterfront → park: в зоне реки по схеме только парк, набережная и "
                                          "велодорожка (у land waterfront — жилая зона с квартирами)"))
    import owner_reloc as OR  # noqa: E402
    OR.apply("growing_w", out, lambda zid, u, d: use_rules(u, d), CHANGES)       # owner 05.11.2026: industry to the edges
    return out


ZPLAN = plan()
DEV = unary_union([z["poly"] for z in ZPLAN if z["use"] in DEV_USES])
VILL = unary_union([z["poly"] for z in ZPLAN if z["use"] == "village_existing"])
ZID = {z["id"]: z for z in ZPLAN}
