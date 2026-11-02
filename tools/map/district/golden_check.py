#!/usr/bin/env python3
"""Self-check of tools/map/spec/golden.json v1 (w50, level 2; gate_check.py of w47 for Golden). Not the validator: the cartographer's own gate before the tools run.

    python3 -I tools/map/district/golden_check.py [spec.json]

Checks: the spec loads and uses the contract vocabulary (no driveway_* classes: drives come from land_driveways); everything
lies inside the district; zones do not overlap; every new street end is on another street, a node, the district border or a
keep attach point (a village lane ≤ 150 m to an existing house may end at the house, and so may a local side street
≤ 150 m into zone land the LRT corridor cuts off); no new street enters the keep polygon; every registry row of Golden is in
`objects`; no new street, LRT line or by-rule plot runs through an existing house (twin existing_osm rows and Overture
houses ≥ 25 m², as the land tools see them); the city joints of Golden lie on their axes (distances recomputed). Exit code 0 only when every check passes.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import golden_common as C  # noqa: E402
from gate_trial_check import EXTRA_NODE_KINDS, HALF_W, LOT_USES, STRUCT, _res  # noqa: E402

V1_KEYS = ["district", "boundary", "targets", "centres", "axes", "zones", "lrt", "objects", "phases", "joints", "checks",
           "area", "streets", "nodes", "keep", "views", "utilities", "replaced_osm"]
NO_JUNCTION = {"expressway", "ramp"}


def run(spec, verbose=False):
    norms = C.spec("norms")
    classes = set(norms["road_classes"])
    ntypes = set(norms["node_types"]) | EXTRA_NODE_KINDS
    out = {}
    area = Polygon(spec["area"]).buffer(0)
    A1 = area.buffer(1.0)
    streets = spec["streets"]
    nodes = spec["nodes"]
    S = {s["id"]: s for s in streets}

    # 1 — loads and vocabulary
    iss = [f"нет ключа {k}" for k in V1_KEYS if k not in spec]
    if spec.get("version") != 1 or spec.get("district") != "golden":
        iss.append("version/district")
    ids = [s["id"] for s in streets]
    if len(ids) != len(set(ids)):
        iss += [f"повтор id улицы {i}" for i in {i for i in ids if ids.count(i) > 1}]
    nids = [n["id"] for n in nodes]
    if len(nids) != len(set(nids)):
        iss += [f"повтор id узла {i}" for i in {i for i in nids if nids.count(i) > 1}]
    for s in streets:
        if s["class"] not in classes:
            iss.append(f"{s['id']}: класс {s['class']} не из norms")
        if s["class"].startswith("driveway"):
            iss.append(f"{s['id']}: класс {s['class']} — в golden.json проезды только от land_driveways")
        if len(s["years"]) != 4:
            iss.append(f"{s['id']}: years не 4 значения")
        if len(s["line"]) < 2 or LineString(s["line"]).length < 1:
            iss.append(f"{s['id']}: пустая линия")
        for st in s.get("struct", []):
            if st["kind"] not in STRUCT:
                iss.append(f"{s['id']}: struct {st['kind']}")
        if not (s["source"] == "new" or s["source"].startswith("keep_existing:")):
            iss.append(f"{s['id']}: source {s['source']}")
    for n in nodes:
        if n["type"] not in ntypes:
            iss.append(f"{n['id']}: тип {n['type']}")
        for sid in n["streets"]:
            if sid not in S:
                iss.append(f"{n['id']}: нет улицы {sid}")
    for o in spec["objects"]:
        if o.get("kind") and o["kind"] not in LOT_USES:
            iss.append(f"{o['registry_id']}: kind {o['kind']}")
        if o.get("years") and len(o["years"]) != 4:
            iss.append(f"{o['registry_id']}: years")
        if o.get("basis") not in ("по источнику", "по правилу"):
            iss.append(f"{o['registry_id']}: basis")
    for ln in spec["lrt"]["lines"]:
        if len(ln["years"]) != 4:
            iss.append(f"{ln['id']}: years")
    zids = [z["id"] for z in spec["zones"]]
    if len(zids) != len(set(zids)):
        iss.append("повтор id зоны")
    out["loads"] = _res(iss, len(streets) + len(nodes))

    # 2 — inside the district
    iss = []
    for s in streets:
        L = LineString(s["line"])
        if s["source"] == "new" and not A1.contains(L):
            iss.append(f"улица {s['id']} выходит за границу на {L.difference(A1).length:.1f} м")
    for n in nodes:
        if not A1.contains(Point(n["x"], n["z"])):
            iss.append(f"узел {n['id']} вне района")
    for z in spec["zones"]:
        p = Polygon(z["polygon"]).buffer(0)
        if p.difference(A1).area > 1.0:
            iss.append(f"зона {z['id']} вне района: {p.difference(A1).area:.0f} м²")
    for o in spec["objects"]:
        if o.get("footprint") and Polygon(o["footprint"]).difference(A1).area > 1.0:
            iss.append(f"участок {o['registry_id']} вне района")
    for ln in spec["lrt"]["lines"]:
        if LineString(ln["line"]).difference(A1).length > 1.0:
            iss.append(f"ЛРТ {ln['id']} вне района на {LineString(ln['line']).difference(A1).length:.0f} м")
        for st in ln["stations"]:
            if not A1.contains(Point(st["x"], st["z"])):
                iss.append(f"станция {st['id']} вне района")
    for k in spec["keep"]:
        if Polygon(k["polygon"]).difference(A1).area > 1.0:
            iss.append(f"keep {k['id']} вне района")
    for a in spec["axes"]:
        if a["id"] == "ax_road17":
            L = LineString(a["line"])
            if L.difference(area.buffer(-9.5)).length > 1.0:
                iss.append(f"ось ax_road17 ближе 10 м к границе на {L.difference(area.buffer(-9.5)).length:.0f} м")
    out["inside_area"] = _res(iss, len(streets) + len(nodes) + len(spec["zones"]) + len(spec["objects"]))

    # 2b — zones do not overlap
    iss = []
    zp = [(z["id"], Polygon(z["polygon"]).buffer(0)) for z in spec["zones"]]
    tree = shapely.STRtree([p for _, p in zp])
    for i, (zi, p) in enumerate(zp):
        for j in tree.query(p):
            if j <= i:
                continue
            a = p.intersection(zp[j][1]).area
            if a > 50.0:
                iss.append(f"зоны {zi} и {zp[j][0]} перекрываются на {a:.0f} м²")
    cover = unary_union([p for _, p in zp])
    gap = area.difference(cover).area
    out["zones_disjoint"] = _res(iss, len(zp), f"не покрыто зонами {gap / 1e4:.2f} га (обрезки < 500 м²)")

    # 3 — every new street end is on another street, a node, the border or a keep attach point
    iss = []
    lines = [(s["id"], LineString(s["line"]), s["class"]) for s in streets]
    # existing roads that stay (gen_network takes every OSM road of the district but the replaced ones and tracks)
    rep = set(spec.get("replaced_osm") or [])
    kept_ids = {s["source"].split(":", 1)[1] for s in streets if s["source"].startswith("keep_existing:")}
    for g, p in C.layer_in("roads", area):
        if p["id"] in rep or p["id"] in kept_ids or p.get("class") in ("track", "footway", "path", "cycleway", "steps", "pedestrian"):
            continue
        cls = "ramp" if p.get("class") == "motorway" else "osm"
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "LineString":
                lines.append(("osm:" + p["id"], q, cls))
    lt = shapely.STRtree([L for _, L, _ in lines])
    att = [(a["x"], a["z"]) for k in spec["keep"] for a in k.get("attach", [])]
    npts = [(n["x"], n["z"], n) for n in nodes]
    free = 0
    for s in streets:
        if s["source"] != "new":
            continue
        for p in (s["line"][0], s["line"][-1]):
            P = Point(p)
            if any(lines[i][0] != s["id"] and lines[i][2] not in NO_JUNCTION and lines[i][1].distance(P) < 0.5
                   for i in lt.query(P.buffer(0.6))):
                continue
            if any(math.hypot(x - p[0], z - p[1]) <= 1.5 for x, z, n in npts):
                continue
            if area.exterior.distance(P) < 3.0 or any(math.hypot(x - p[0], z - p[1]) < 30 for x, z in att):
                continue
            if (s["class"] == "village_lane" or (s["class"] == "local" and s["id"].startswith("v_serve_"))) \
                    and p == s["line"][-1] and LineString(s["line"]).length <= 150.0:
                continue          # a lane to an existing house or a side street into cut-off zone land: a dead end the class
                #                   allows (fire_access.dead_end_max_m)
            if int(s["years"][0]) <= 2025 and LineString(s["line"]).length <= 150.0:
                continue          # the part of an existing road the spec keeps (v_ccd42a63): its dead end is OSM's
            free += 1
            iss.append(f"{s['id']} ({s['class']}): свободный конец ({p[0]:.0f}, {p[1]:.0f})")
    out["street_ends"] = _res(iss, 2 * len(streets), f"свободных концов {free}")

    # 4 — keep polygon not crossed by new streets
    iss = []
    for k in spec["keep"]:
        K0 = Polygon(k["polygon"])
        K = K0.buffer(-1.0)
        att_d = [Point(a["x"], a["z"]).buffer(max(4.0, K0.exterior.distance(Point(a["x"], a["z"])) + 3.0)) for a in k["attach"]]
        for s in streets:
            if s["source"] != "new":
                continue
            L = LineString(s["line"])
            if not L.intersects(K0.buffer(5)):
                continue
            for a in att_d:
                L = L.difference(a)
            if L.intersects(K):
                iss.append(f"{s['id']} входит в {k['id']} на {L.intersection(K).length:.1f} м")
    out["keep_not_crossed"] = _res(iss, len(streets))

    # 5 — every registry row of Golden is in objects
    iss = []
    reg = C.spec("registry")["rows"]
    have = {o["registry_id"] for o in spec["objects"]}
    n_in = 0
    for r in reg:
        geoms = []
        if r.get("geom"):
            try:
                geoms.append(shape(r["geom"]))
            except Exception:
                pass
        if r.get("scheme_to"):
            geoms.append(Point(r["scheme_to"]))
        mine = "golden" in (r.get("district_area"), r.get("scheme_spec"), r.get("scheme_area")) or (
            r.get("scheme_conflict") or {}).get("owner") == "golden"
        if mine:
            n_in += 1
            if r["id"] not in have:
                iss.append(f"строка реестра {r['id']} ({r.get('name_ru', '')[:40]}) нет в objects")
    out["registry_present"] = _res(iss, n_in)

    # 6 — no new street / LRT / by-rule plot through an existing house (the land tools' house set)
    iss = []
    from gen_blocks_lots import existing_houses
    houses = [h["fp"] for h in existing_houses(area.buffer(60), Polygon())]
    ht = shapely.STRtree(houses)

    def hits(geom):
        return [houses[i] for i in ht.query(geom, predicate="intersects")]

    for s in streets:
        if s["source"] != "new":
            continue
        g = LineString(s["line"]).buffer(HALF_W.get(s["class"], 5.0), cap_style=2)
        for b in hits(g):
            c = b.centroid
            iss.append(f"улица {s['id']} задевает дом у ({c.x:.0f}, {c.y:.0f}), {b.area:.0f} м²")
    for ln in spec["lrt"]["lines"]:
        for b in hits(LineString(ln["line"]).buffer(4.0)):
            c = b.centroid
            iss.append(f"ЛРТ задевает дом у ({c.x:.0f}, {c.y:.0f})")
    for o in spec["objects"]:
        if o.get("footprint") and o.get("action") == "by_rule":
            for b in hits(Polygon(o["footprint"])):
                c = b.centroid
                iss.append(f"участок {o['registry_id']} задевает дом у ({c.x:.0f}, {c.y:.0f})")
    out["no_street_through_house"] = _res(iss, len(houses), f"существующих домов в районе+60 м: {len(houses)}")

    # 7 — city joints of Golden on their axes (distances recomputed: the level-0 values were stale)
    iss = []
    jd = []
    axes = {a["id"]: LineString(a["line"]) for a in spec["axes"]}
    v0j = {j["joint_id"]: j.get("axis") for j in (C.spec_v0().get("joints") or [])}
    for j in spec["joints"]:
        ax = v0j.get(j["joint_id"])
        if ax and ax in axes:
            d = axes[ax].distance(Point(j["x"], j["z"]))
            jd.append({"joint": j["joint_id"], "axis": ax, "dist_m": round(d, 1)})
    out["joints"] = _res(iss, len(spec["joints"]), "расстояния стыков до осей пересчитаны")
    out["joints"]["dist"] = jd

    # info
    info = {}
    for ln in spec["lrt"]["lines"]:
        L = LineString(ln["line"])
        ch = sorted(round(L.project(Point(st["x"], st["z"]))) for st in ln["stations"])
        info[f"{ln['id']}_station_chainage_m"] = ch
        info[f"{ln['id']}_station_spacing_m"] = [b - a for a, b in zip(ch, ch[1:])]
        info[f"{ln['id']}_length_m"] = round(L.length)
    from collections import Counter
    km = Counter()
    for s in streets:
        km[s["class"]] += LineString(s["line"]).length / 1000.0
    info["street_km_by_class"] = {k: round(v, 1) for k, v in sorted(km.items())}
    info["streets"] = len(streets)
    out["info"] = info
    out["passed"] = all(v["ok"] for k, v in out.items() if isinstance(v, dict) and "ok" in v)
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    path = argv[0] if argv else os.path.join(C.SPEC_DIR, "golden.json")
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    res = run(spec)
    for k, v in res.items():
        if isinstance(v, dict) and "ok" in v:
            print(f"{'OK ' if v['ok'] else 'ERR'} {k}: n={v['n']}" + (f" · {v['note']}" if v.get("note") else ""))
            for i in v["issues"]:
                print("     ", i)
            if v.get("more"):
                print("      … ещё", v["more"])
    for k, v in res["info"].items():
        print("  info", k, v)
    print("PASSED" if res["passed"] else "FAILED")
    return res["passed"]


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
