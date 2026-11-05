#!/usr/bin/env python3
"""Industry to the edges of the city (owner 05.11.2026: «промышленные объекты не должны находиться внутри города или близко к жилому
району … исправь это так, чтобы эти районы были по краям города и не мешали жилому району»).

Runs over the district specs after their *_build.py (it edits spec/<district>.json in place, so run it again after a rebuild):
  - housing = the zones where people live or stay: residential_*, mixed_centre, campus, medical, resort (all districts at once, so a
    plant at a district border sees the houses of the neighbour; existing villages are not counted — they stay as they are);
  - an industry zone keeps only its land at least IND_KEEP_M from housing (СП РК / СанПиН: a class I–II plant needs 500–1000 m);
    its land nearer than IND_GREEN_M becomes a planted sanitary gap (park), the band between becomes a technopark (offices, R&D,
    clean assembly: no emissions, so no SZZ);
  - a logistics zone the same with LOG_KEEP_M / LOG_GREEN_M (warehouses are class V, 50 m, but trucks and noise: 500 m);
  - registry objects with a footprint (named plants: Mars Petcare, KNAUF, OIZ TULIP …) and existing plants (lot_split none) keep
    their land and their use: real places are not moved by a rule. Their distance to housing is listed in the report.
Pieces under MIN_PIECE_HA join the neighbouring new use. New zone ids: <zone>_tp (technopark), <zone>_gb (green gap).
Writes a report to stdout and tools/map/out/szz_edges.json.

usage: python tools/map/district/szz_edges.py [--dry]"""
import json
import os
import sys

import shapely
from shapely.geometry import Polygon, MultiPolygon, mapping
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "..", "spec")
OUT = os.environ.get("ALATAU_OUT") or os.path.join(HERE, "..", "out")
DISTRICTS = ("gate", "golden", "green", "growing_w", "growing_e")
EDIT = ("golden", "growing_w", "growing_e")          # Gate is «ideal» by the owner's decision: reported, not edited
HOUSING = ("residential_low", "residential_mid", "residential_high", "mixed_centre", "campus", "medical", "resort")
IND_KEEP_M, IND_GREEN_M = 1000.0, 300.0
LOG_KEEP_M, LOG_GREEN_M = 500.0, 150.0
MIN_PIECE_HA = 0.8
MODEL = "модель qTwin"

TP_RULES = {"floors": [2, 5], "height_cap_m": 30, "far": 0.8, "block_side_m": [150, 300], "setback_m": 8.0, "lot_split": "industrial",
            "parking": {"per_home": 1.0, "per_100m2_office": None, "per_100m2_retail": None, "type": "surface"},
            "homes_per_ha": 0, "jobs_per_ha": 95.0}


def poly_of(z):
    return shapely.make_valid(Polygon([p[:2] for p in z["polygon"]])).buffer(0)


def rings(g):
    """Polygons of a geometry, largest first."""
    ps = [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon" and not q.is_empty]
    out = []
    for q in ps:
        out += [q] if q.geom_type == "Polygon" else list(q.geoms)
    return sorted(out, key=lambda q: -q.area)


def ring_list(q):
    return [[round(x, 1), round(y, 1)] for x, y in list(q.exterior.coords)[:-1]]


def main():
    dry = "--dry" in sys.argv
    specs = {d: json.load(open(os.path.join(SPEC, d + ".json"), encoding="utf-8")) for d in DISTRICTS}
    home = unary_union([poly_of(z) for d in DISTRICTS for z in specs[d]["zones"] if z["use"] in HOUSING])
    rep = {"made_by": "tools/map/district/szz_edges.py (" + MODEL + ")", "rules": {"industry_keep_m": IND_KEEP_M, "industry_green_m": IND_GREEN_M,
           "logistics_keep_m": LOG_KEEP_M, "logistics_green_m": LOG_GREEN_M}, "zones": [], "kept_objects": [], "totals": {}}
    tot = {"industry_ha_before": 0.0, "industry_ha_after": 0.0, "logistics_ha_before": 0.0, "logistics_ha_after": 0.0,
           "technopark_ha": 0.0, "green_gap_ha": 0.0}
    for d in DISTRICTS:
        s = specs[d]
        fixed = unary_union([shapely.make_valid(Polygon([p[:2] for p in o["footprint"]])).buffer(0) for o in s.get("objects", [])
                             if o.get("footprint") and len(o["footprint"]) >= 3]) if s.get("objects") else Polygon()
        new_zones = []
        for z in s["zones"]:
            if z["use"] not in ("industry", "logistics"):
                new_zones.append(z); continue
            P = poly_of(z); keep_m, green_m = (IND_KEEP_M, IND_GREEN_M) if z["use"] == "industry" else (LOG_KEEP_M, LOG_GREEN_M)
            tot[z["use"] + "_ha_before"] += P.area / 1e4
            dist = P.distance(home)
            existing = (z.get("rules") or {}).get("lot_split") == "none"
            if d not in EDIT or dist >= keep_m or existing:
                tot[z["use"] + "_ha_after"] += P.area / 1e4
                if dist < keep_m:
                    rep["kept_objects"].append({"district": d, "zone": z["id"], "name_ru": z["name_ru"], "dist_m": round(dist),
                                                "why": "Gate не правится (решение владельца)" if d not in EDIT else "существующее предприятие"})
                new_zones.append(z); continue
            near_g = home.buffer(green_m, quad_segs=8); near_k = home.buffer(keep_m, quad_segs=8)
            fixed_here = P.intersection(fixed)
            free = P.difference(fixed_here)
            gap = free.intersection(near_g)
            tp = free.intersection(near_k).difference(near_g)
            rest = P.difference(gap).difference(tp)                       # the far part and the named plants' footprints
            # small leftovers of the kept use near houses join the technopark; small gap bits join the technopark too
            kept, extra_tp = [], []
            for q in rings(rest):
                (kept if q.area >= MIN_PIECE_HA * 1e4 or q.intersects(fixed_here) else extra_tp).append(q)
            gaps = [q for q in rings(gap) if q.area >= MIN_PIECE_HA * 1e4 * 0.5]
            extra_tp += [q for q in rings(gap) if q.area < MIN_PIECE_HA * 1e4 * 0.5]
            tps = rings(unary_union(rings(tp) + extra_tp)) if (rings(tp) or extra_tp) else []
            tps = [q for q in tps if q.area >= 2000.0]
            why0 = f"{MODEL}: промзона отодвинута от жилья (решение владельца 05.11.2026)"
            for i, q in enumerate(kept):
                zz = dict(z); zz["polygon"] = ring_list(q); zz["area_ha"] = round(q.area / 1e4, 2)
                if i:
                    zz["id"] = f"{z['id']}_k{i + 1}"
                zz["why"] = z["why"] + f"; {why0}: остаётся только земля дальше {keep_m:.0f} м от жилья"
                new_zones.append(zz); tot[z["use"] + "_ha_after"] += q.area / 1e4
            for i, q in enumerate(tps):
                new_zones.append({"id": f"{z['id']}_tp" + (f"{i + 1}" if i else ""), "use": "business",
                                  "name_ru": f"Технопарк у {z['name_ru'][:60]}", "polygon": ring_list(q), "years": z["years"],
                                  "rules": json.loads(json.dumps(TP_RULES)), "area_ha": round(q.area / 1e4, 2),
                                  "why": f"{why0}: полоса {green_m:.0f}–{keep_m:.0f} м от жилья — офисы, НИОКР, чистая сборка без выбросов "
                                         f"вместо {'заводов' if z['use'] == 'industry' else 'складов'}"})
                tot["technopark_ha"] += q.area / 1e4
            for i, q in enumerate(gaps):
                new_zones.append({"id": f"{z['id']}_gb" + (f"{i + 1}" if i else ""), "use": "park",
                                  "name_ru": f"Санитарный разрыв: озеленение у {z['name_ru'][:50]}", "polygon": ring_list(q),
                                  "years": z["years"], "rules": {"lot_split": "none"}, "area_ha": round(q.area / 1e4, 2),
                                  "why": f"{why0}: первые {green_m:.0f} м от жилья — лесополоса и парк"})
                tot["green_gap_ha"] += q.area / 1e4
            rep["zones"].append({"district": d, "zone": z["id"], "use": z["use"], "ha": round(P.area / 1e4, 1), "dist_m": round(dist),
                                 "kept_ha": round(sum(q.area for q in kept) / 1e4, 1), "technopark_ha": round(sum(q.area for q in tps) / 1e4, 1),
                                 "green_ha": round(sum(q.area for q in gaps) / 1e4, 1)})
        s["zones"] = new_zones
        s.setdefault("scheme_changes", [])
        s["scheme_changes"] = [c for c in s["scheme_changes"] if c.get("id") != "szz_edges"] + [
            {"id": "szz_edges", "why": f"промзоны отодвинуты от жилья: заводы ≥ {IND_KEEP_M:.0f} м, склады ≥ {LOG_KEEP_M:.0f} м; ближняя полоса — "
                                      f"зелёный разрыв, дальше — технопарк ({MODEL}, решение владельца 05.11.2026)"}]
    rep["totals"] = {k: round(v, 1) for k, v in tot.items()}
    for r in rep["zones"]:
        print(f"  {r['district']:10s} {r['zone']:26s} {r['use']:9s} {r['ha']:7.1f} га, до жилья {r['dist_m']:5d} м → остаётся {r['kept_ha']:6.1f}, "
              f"технопарк {r['technopark_ha']:6.1f}, озеленение {r['green_ha']:6.1f}")
    for r in rep["kept_objects"]:
        print(f"  оставлено: {r['district']} {r['zone']} ({r['name_ru'][:50]}), до жилья {r['dist_m']} м — {r['why']}")
    print("итого:", rep["totals"])
    os.makedirs(OUT, exist_ok=True)
    json.dump(rep, open(os.path.join(OUT, "szz_edges.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not dry:
        for d in EDIT:
            with open(os.path.join(SPEC, d + ".json"), "w", encoding="utf-8", newline="
") as f:
                f.write(json.dumps(specs[d], ensure_ascii=False, indent=1) + "
")


if __name__ == "__main__":
    main()
