#!/usr/bin/env python3
"""Growing-East · level 2 · zone plan of the whole district (w53), imported by growing_e_net.py (local street grid) and
growing_e_build.py.

Zones = the approved level-0 scheme (district/growing_e_v0.json, 324 zones that tile the district). The level-0 zones carry
holes (villages and other zones inside them); v1 zones are flat rings (CONTRACT §3), so a zone with holes is the zone minus
its holes, cut into hole-free parts (`_p2`, `_p3` …). Each zone gets the v1 rules of its use; densities start from the
scheme's (residents_per_ha / 2.5 = homes_per_ha) and are scaled in growing_e_build.py to the district targets. Changes against
the scheme are listed in SCHEME_CHANGES (shown in the spec).
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import growing_e_common as C  # noqa: E402

V0 = C.V0
DIST = C.DIST
rules = C.rules
RES_PER_HOME = 2.5            # rule 24: residents = GFA / 30 m², homes = GFA / 75 m² (targets.home_m2)

# grid of local streets per use: (spacing along the grid's first axis, spacing across), metres between street axes
GRID = {"residential_high": (165.0, 150.0), "residential_mid": (190.0, 160.0), "residential_low": (170.0, 125.0),
        "business": (180.0, 160.0), "mixed_centre": (165.0, 150.0), "medical": (330.0, 330.0),
        "logistics": (480.0, 320.0), "industry": (420.0, 300.0)}
DEV_USES = set(GRID) | {"sport"}
SCHEME_CHANGES = []           # (id, why)


BIZ_CAP = 49        # business and mixed centres: up to 11 office storeys (4,43 м, twin) under the 50 m airfield limit


def use_rules(zid, use, d):
    """v1 rules of a zone from its use and the scheme density d (residents_per_ha → homes_per_ha; scaled later).
    Heights: the whole district lies within 30 km of the Zhetygen airfield control point (heights.airfield_approval_radius_km),
    so zone caps stay under 50 m except the main centre (scheme: two 16-floor towers, «нужно согласование»); lowest floors
    × storey height ≤ 28 m (fire gaps of 22 m between buildings over 28 m, w44). Business and mixed centres go to 49 m (11
    office storeys): at 35–40 m their blocks held 75–85 % of the scheme's jobs (run 2, gen_buildings totals)."""
    h = (d.get("residents_per_ha") or 0) / RES_PER_HOME or None
    j = d.get("jobs_per_ha")
    if use == "residential_high":
        return rules([8, 12], 45, 2.0, [110, 160], "perimeter", "underground", h or 54, j or 20)
    if use == "residential_mid":
        return rules([5, 8], 28, 1.4, [120, 180], "perimeter", "multi", h or 47, j or 15)
    if use == "residential_low":
        far = d.get("far") or 0.4
        return rules([2, 4], 15, max(far, 0.5), [80, 150], "rows", "surface", h or 19, j or 8)
    if use == "business":
        fl = int(d.get("floors_typical") or 4)
        return rules([3, max(11, fl + 2)], BIZ_CAP, max(1.0, (d.get("far") or 1.0) + 0.4), [110, 180], "perimeter", "multi", 0, j or 80)
    if use == "mixed_centre":
        if zid == "z_centre_main":
            return rules([6, 16], 56, 2.4, [110, 160], "perimeter", "underground", h or 24, j or 200)
        return rules([5, 11], BIZ_CAP, 1.8, [110, 160], "perimeter", "underground", h or 24, j or 120)
    if use == "medical":
        return rules([3, 8], 35, 0.9, [200, 400], "campus", "multi", 0, j or 60)
    if use == "logistics":
        return rules([1, 1], 18, 0.45, [250, 480], "industrial", "surface", 0, j or 30, setback=10.0)
    if use == "industry":
        return rules([1, 2], 18, 0.35, [250, 450], "industrial", "surface", 0, j or 35, setback=10.0)
    if use == "sport":
        return {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": j or 5}
    if use == "village_existing":
        return {"lot_split": "houses", "floors": [1, 2], "height_cap_m": 9, "far": 0.25, "block_side_m": None, "setback_m": 3,
                "parking": {"per_home": 1.0, "type": "surface"}, "homes_per_ha": None, "jobs_per_ha": None}
    return {"lot_split": "none"}


def v0_poly(z):
    p = Polygon(z["polygon"]).buffer(0)
    for h in z.get("holes") or []:
        p = p.difference(Polygon(h).buffer(0))
    return p.buffer(0).intersection(DIST).buffer(0)


def plan():
    """[{id, use, name_ru, poly, years, rules, why, density, src}] covering the district without overlaps (polygons may
    still have holes and several parts here: growing_e_build.zone_out makes them flat rings)."""
    out = []
    taken = Polygon()
    # villages first (existing houses stay as OSM has them), then everything else in scheme order
    order = sorted(V0["zones"], key=lambda z: 0 if z["use"] == "village_existing" else 1)
    for z in order:
        p = v0_poly(z).difference(taken).buffer(0)
        if p.area < 200.0:
            continue
        d = z.get("density") or {}
        out.append({"id": z["id"], "use": z["use"], "name_ru": z["name_ru"], "poly": p, "years": list(z["years"]),
                    "rules": use_rules(z["id"], z["use"], d), "why": z.get("why", "схема уровня 0"), "density": d, "src": "v0",
                    "population_existing": z.get("population_existing")})
        taken = taken.union(p)
    import owner_reloc as OR  # noqa: E402
    OR.apply("growing_e", out, use_rules, SCHEME_CHANGES)                        # owner 05.11.2026: industry to the edges
    return out


ZPLAN = plan()
ZBY = {z["id"]: z for z in ZPLAN}


def dev_union():
    return unary_union([z["poly"] for z in ZPLAN if z["use"] in GRID])


def vill_union():
    return unary_union([z["poly"] for z in ZPLAN if z["use"] == "village_existing"])


if __name__ == "__main__":
    from collections import Counter
    c = Counter()
    a = Counter()
    for z in ZPLAN:
        c[z["use"]] += 1
        a[z["use"]] += z["poly"].area / 1e4
    for k in sorted(c):
        print(f"{k:20s} {c[k]:4d} {a[k]:8.1f} ha")
    cov = unary_union([z["poly"] for z in ZPLAN])
    print("district", round(DIST.area / 1e4, 1), "covered", round(cov.area / 1e4, 1), "gap", round(DIST.difference(cov).area / 1e4, 2))
    _ = copy
