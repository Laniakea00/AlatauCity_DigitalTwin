"""Rules 19–20 (w44): trees and street props on asphalt or inside buildings. Interface: CONTRACT §5.

Level 1 has no trees file (FilmTrees plants in Unity from greens, no-plant masks and road profiles), so rule 19 checks what the
data does decide: green polygons do not lie on carriageways, sidewalks, rails or buildings, and the no-plant mask holds what
must stay free of trees (surface parking, the LRT ground corridor, overhead power corridors). Rule 20 checks stops (the only
props in the data); lamps, signals and signs are Unity counters (rules 21–22 path): an info line names the log counters
(w48 trees on hard ground, w45 lamps, signals and signs per district) that must read 0."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))
import shapely  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import land_rulekit as K  # noqa: E402
import land_util as U  # noqa: E402


def _hard(ctx):
    """Level-0 hard surfaces: walkways of roads (carriageway + verges + sidewalks), buildings, ground LRT."""
    c = K.cache(ctx)
    if "hard" not in c:
        parts = [(("road", s["id"]), p) for s, p, lv in K.road_polys(ctx, "walk") if lv == 0]
        parts += [(("building", b["id"]), b["_p"]) for b in K.buildings(ctx)]
        w = K.nv(ctx, "lrt.corridor_width_m", "double_track")
        for Ln in (ctx.lrt or {}).get("lines", []):
            ls = LineString([(q[0], q[1]) for q in Ln["pts"]])
            for sec in Ln.get("sections", []):
                if sec["kind"] == "ground" and sec["to_m"] - sec["from_m"] > 1:
                    parts.append((("lrt", Ln["id"]), shapely.ops.substring(ls, max(0, sec["from_m"]), min(ls.length, sec["to_m"])).buffer(w / 2, cap_style="flat")))
        c["hard"] = parts
    return c["hard"]


def check_19(ctx):
    m = K.missing(ctx, 19, "features", "buildings", "network")
    if m:
        return m
    out = []
    tol = K.nv(ctx, "validator.occupancy_overlap_max_m2")
    hard = _hard(ctx)
    tree = shapely.STRtree([p for _, p in hard])
    for g in (ctx.features or {}).get("greens", []):
        gp = K.geom(g)
        for j in tree.query(gp, predicate="intersects"):
            (k, i), hp = hard[int(j)]
            q = gp.intersection(hp)
            a = q.area
            if a > tol:
                c = q.representative_point()
                out.append(K.issue(ctx, 19, c.x, c.y, f"зелень {g['id']} ({g['kind']}) на {k} {i}: {a:.0f} м² — деревья лягут на твёрдое", [g["id"], i]))
    noplant = unary_union([K.poly(n["polygon"]) for n in (ctx.features or {}).get("noplant", [])]) if (ctx.features or {}).get("noplant") else U.Polygon()
    # the mask grown by 0.5 m once, its parts in a tree: each item is cut by the parts near it only (the parts of one
    # valid multipolygon are disjoint, so this is the same difference; one buffer of the whole mask per item made the
    # rule quadratic, 800 s on Green)
    grown = noplant.buffer(0.5) if not noplant.is_empty else None
    grown = list(getattr(grown, "geoms", [grown])) if grown is not None else []
    gtree = shapely.STRtree(grown) if grown else None
    need = [(p_["id"], K.poly(p_["polygon"]), "стоянка") for p_ in (ctx.features or {}).get("parking", []) if p_["type"] != "underground"]
    for c_ in U.corridors(ctx.spec):
        if c_.get("state") != "cable":
            # trees out of the protected zone of an overhead line: the RK rules want a clearing (просека) along it through the
            # plantings of a settlement (utilities.power_line_protection_zone_m)
            w = U.power_zone_m(K.norms(ctx), c_)[0] if c_["kind"] == "power_line" else c_.get("width_m")
            need.append((c_["id"], LineString(c_["line"]).buffer(w if w else 1.0, cap_style="flat").intersection(ctx.area),
                         f"охранная зона ЛЭП {w:.0f} м" if w else "охранная зона ЛЭП"))
    for i, p, why in need:
        near = gtree.query(p) if gtree is not None else []
        miss = p.difference(shapely.multipolygons([grown[int(j)] for j in near])).area if len(near) else p.area
        if miss > tol:
            c = p.representative_point()
            out.append(K.issue(ctx, 19, c.x, c.y, f"{why} {i} не в маске «нельзя сажать» ({miss:.0f} м²)", [i]))
    c = ctx.area.centroid
    out.append(K.issue(ctx, 19, c.x, c.y, "уровень 1: точки деревьев проверяются в Unity (FilmTrees сажает по greens и noplant) — счётчик лога "
                       "«[Alatau] film trees on hard ground (map data): <район> N · …» по каждому району должен быть 0 (w48); "
                       "здесь проверены зелень на твёрдом и маска «нельзя сажать»", [], sev="info"))
    return out


def check_20(ctx):
    m = K.missing(ctx, 20, "features", "network", "buildings")
    if m:
        return m
    out = []
    car = [(s, p) for s, p, lv in K.road_polys(ctx, "carriage") if lv == 0]
    ct = shapely.STRtree([p for _, p in car]) if car else None
    bt = shapely.STRtree([b["_p"] for b in K.buildings(ctx)]) if K.buildings(ctx) else None
    for st in (ctx.features or {}).get("stops", []):
        if st["kind"] == "lrt":
            continue        # LRT stations stand on their platforms (w43, rule 25)
        p = Point(st["x"], st["z"])
        if ct is not None:
            hit = [car[int(j)][0]["id"] for j in ct.query(p, predicate="intersects")]
            if hit:
                out.append(K.issue(ctx, 20, p.x, p.y, f"остановка {st['id']} на проезжей части {hit[0]}", [st["id"], hit[0]]))
        if bt is not None:
            hit = [K.buildings(ctx)[int(j)]["id"] for j in bt.query(p, predicate="intersects")]
            if hit:
                out.append(K.issue(ctx, 20, p.x, p.y, f"остановка {st['id']} внутри здания {hit[0]}", [st["id"], hit[0]]))
    c = ctx.area.centroid
    out.append(K.issue(ctx, 20, c.x, c.y, "уровень 1: фонари, светофоры и знаки ставит Unity, проверяются в Unity — счётчики лога «[Alatau] film lamps: N street "
                       "lamps on M roads», «[Alatau] film traffic: N signalled junctions» и счётчики фонарей, светофоров и знаков на асфальте или в "
                       "здании по каждому району (w45) должны быть 0; здесь проверены остановки", [], sev="info"))
    return out


RULES = [
    {"no": 19, "key": "trees_on_hard", "fn": check_19, "needs": ["features", "buildings", "network"]},
    {"no": 20, "key": "props_on_hard", "fn": check_20, "needs": ["features", "network", "buildings"]},
]
