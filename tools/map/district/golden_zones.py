#!/usr/bin/env python3
"""Golden · level 2 · zone plan of the whole district (w50), imported by golden_net.py (local street grid) and golden_build.py.

Zones = the approved level-0 scheme (district/golden_v0.json, 31 zones, several of them made of many parts) as flat simple
polygons (the v0 file kept a list of rings per zone, which net_osm.load and the land tools cannot read); a zone listed earlier
in the scheme wins where two overlap (as the scheme was drawn: water, villages and parks first). Changes against the scheme:
  * Z-W (water + 35 m strip) is a park, not «waterfront»: land_util counts waterfront as housing land, the strip is not;
  * the 212 ha the scheme left uncovered at Әли (city.json gave it to Golden after the scheme): the village's houses are a
    village zone, the land west of them a logistics zone like Z-L3 «склады у полигона Әли» (no housing by the landfill).
Each zone gets the v1 rules (CONTRACT §3) of its use; densities start from the scheme's and are scaled in golden_build.py to
the district targets. Changes are listed in SCHEME_CHANGES (shown in the spec).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from shapely.geometry import Point, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import golden_common as GC  # noqa: E402

V0 = GC.V0
GOLDEN = GC.GOLDEN
rules = GC.rules

# grid of local streets per use: (spacing along the grid's first axis, spacing across), metres between street axes (as Gate)
GRID = {"residential_high": (165.0, 150.0), "residential_mid": (190.0, 160.0), "residential_low": (170.0, 125.0),
        "business": (165.0, 150.0), "mixed_centre": (165.0, 150.0), "medical": (330.0, 330.0),
        "logistics": (430.0, 300.0), "campus": (300.0, 300.0)}
DEV_USES = set(GRID) | {"industry", "sport"}


def use_rules(use, d):
    """v1 rules of a zone from its use and the scheme density d (homes_per_ha, jobs_per_ha as given; scaled later)."""
    h, j = d.get("homes_per_ha"), d.get("jobs_per_ha")
    if use == "residential_high":
        return rules([9, 14], 50, 1.8, [110, 150], "perimeter", "underground", h or 165, j or 25)
    if use == "residential_mid":
        return rules([5, 9], 32, 1.1, [120, 180], "perimeter", "multi", h or 115, j or 15)
    if use == "residential_low":
        return rules([2, 4], 15, 0.55, [80, 150], "rows", "multi", h or 65, j or 6)
    if use == "business":
        return rules([4, 10], 40, 1.3, [110, 160], "perimeter", "multi", h or 0, j or 130)
    if use == "mixed_centre":
        return rules([5, 12], 45, 1.9, [110, 160], "perimeter", "underground", h or 110, j or 120)
    if use == "medical":
        return rules([3, 9], 35, 1.2, [200, 400], "campus", "multi", 0, j or 140)
    if use == "campus":
        return rules([3, 9], 35, 0.9, [200, 400], "campus", "multi", h or 0, j or 30)
    if use == "logistics":
        return rules([1, 2], 18, 0.45, [250, 450], "industrial", "multi", 0, j or 30, setback=10.0)
    if use == "sport":
        return {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": j or 8}
    if use == "village_existing":
        return {"lot_split": "houses", "floors": [1, 2], "height_cap_m": 9, "far": 0.25, "block_side_m": None, "setback_m": 3,
                "parking": {"per_home": 1.0, "type": "surface"}, "homes_per_ha": None, "jobs_per_ha": None}
    return {"lot_split": "none"}


SCHEME_CHANGES = [
    ("Z-W", "зона воды и водоохранной полосы 35 м — парк (use park), не «waterfront»: land_util считает waterfront землёй "
            "жилья, а полоса — зелень без застройки"),
    ("residential_low, logistics, campus, medical", "стоянки модели — в многоуровневых паркингах, не открытыми полями"),
]
ALI_AT = (898.0, -4764.0)


def _ali_notch(taken):
    """The land of Golden the scheme did not cover at Әли: (village part, the rest)."""
    gap = GOLDEN.difference(taken).buffer(0)
    parts = [q for q in getattr(gap, "geoms", [gap]) if q.geom_type == "Polygon" and q.area > 50e4]
    notch = next((q for q in parts if q.buffer(5).contains(Point(ALI_AT)) or q.distance(Point(ALI_AT)) < 50), None)
    if notch is None:
        return None, None
    from gen_blocks_lots import existing_houses
    hs = [h["fp"] for h in existing_houses(notch.buffer(20), Polygon()) if notch.contains(h["fp"].centroid)]
    vil = unary_union([h.buffer(40.0) for h in hs]).buffer(-15.0).intersection(notch).buffer(0) if hs else Polygon()
    vil = unary_union([q for q in getattr(vil, "geoms", [vil]) if q.area > 2000.0]) if not vil.is_empty else vil
    rest = notch.difference(vil).buffer(0)
    return vil, rest


def plan():
    """[{id, use, name_ru, poly, years, rules, why, density, src}] covering the district without overlaps."""
    out = []
    taken = Polygon()
    for z in V0["zones"]:
        p = unary_union(GC.v0_polys(z)).buffer(0).intersection(GOLDEN).difference(taken).buffer(0)
        taken = taken.union(p)
        if p.area < 200.0:
            continue
        d = dict(z.get("density") or {})
        use = z["use"]
        why = z.get("why", "схема уровня 0")
        if z["id"] == "Z-W":
            use = "park"
            why = (why + "; " if why else "") + "уровень 2: use park вместо waterfront (вода и полоса 35 м — без застройки)"
        r = use_rules(use, d)
        out.append({"id": z["id"], "use": use, "name_ru": z["name_ru"], "poly": p, "years": z["years"],
                    "rules": r, "why": why, "density": d, "src": "v0"})
    vil, rest = _ali_notch(taken)
    if vil is not None:
        if not vil.is_empty:
            out.append({"id": "Z-V4", "use": "village_existing", "name_ru": "Әли (существующий)", "poly": vil, "years": [2025, 2050],
                        "rules": use_rules("village_existing", {}), "density": {"floors_typical": "1–2"}, "src": "v0",
                        "why": "существующие дома посёлка Әли (OSM / двойник) — как есть; земли не было в схеме уровня 0"})
            SCHEME_CHANGES.append(("Z-V4", f"посёлок Әли ({vil.area / 1e4:.0f} га вокруг существующих домов) — зона села: "
                                           "в схеме уровня 0 этой земли не было (city.json отдал её Golden позже)"))
        if rest is not None and rest.area > 1e4:
            L3 = next(z for z in V0["zones"] if z["id"] == "Z-L3")
            d = dict(L3.get("density") or {})
            out.append({"id": "Z-L3e", "use": "logistics", "name_ru": "Склады у полигона Әли (запад)", "poly": rest,
                        "years": L3["years"], "rules": use_rules("logistics", d), "density": d, "src": "v0",
                        "why": GC.MODEL + ": земля между Z-L3, ЛРТ и посёлком Әли, которой не было в схеме уровня 0; "
                                          "как Z-L3 — склады, без жилья (рядом полигон Әли)"})
            SCHEME_CHANGES.append(("Z-L3e", f"{rest.area / 1e4:.0f} га без зоны в схеме у Әли — склады, как соседняя Z-L3 "
                                            "(жильё у полигона не ставится)"))
    return out


ZPLAN = plan()
ZBY = {z["id"]: z for z in ZPLAN}
# the scheme's zones were drawn one by one: two built zones can miss each other by a few cm along a shared border (Z-B1 /
# Z-R2N at x −1090…−1212); the crack would split the quarter and an edge street would run up and down it — closed (1 m)
DEV = unary_union([z["poly"] for z in ZPLAN if z["use"] in GRID]).buffer(1.0, join_style=2).buffer(-1.0, join_style=2)
VILL = unary_union([z["poly"] for z in ZPLAN if z["use"] == "village_existing"])

if __name__ == "__main__":
    from collections import Counter
    c = Counter()
    for z in ZPLAN:
        c[z["use"]] += z["poly"].area / 1e4
    for k, v in sorted(c.items(), key=lambda t: -t[1]):
        print(f"  {k:18s} {v:8.1f} ha")
    print("zones", len(ZPLAN), "dev ha", round(DEV.area / 1e4), "uncovered ha",
          round(GOLDEN.difference(unary_union([z["poly"] for z in ZPLAN])).area / 1e4, 1))
