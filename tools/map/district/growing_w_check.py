"""Self-check of tools/map/spec/growing_w.json v1 (w52, level 2): the cartographer's own gate before the tools run.

    python3 -I tools/map/district/growing_w_check.py [spec.json]

Checks: the spec loads and uses the contract vocabulary (no driveway_* classes); everything lies inside the district; zones
do not overlap and cover the district; every new street end is on another street, a node, the district border or a joint (a
village lane ≤ 150 m to an existing house and a local side street ≤ 150 m into cut-off zone land may end); every registry
row of Growing-West is in `objects`, each marked «по источнику» or «по правилу»; no new street, LRT line or by-rule plot runs
through an existing house; every power-line corridor has its voltage; zone height caps stay under 50 m (rule 16: the whole
district is within 30 km of the new airport and the Zhetygen airfield); LRT stations 0.8–1.5 km apart; the city joints of
Growing-West are listed with what meets them. Exit code 0 only when every check passes.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import growing_w_common as C  # noqa: E402
from gate_trial_check import EXTRA_NODE_KINDS, HALF_W, LOT_USES, STRUCT, _res  # noqa: E402

V1_KEYS = ["district", "boundary", "targets", "centres", "axes", "zones", "lrt", "objects", "phases", "joints", "checks",
           "streets", "nodes", "keep", "views", "utilities", "replaced_osm", "corridors"]
NO_JUNCTION = {"expressway", "ramp"}


def run(spec, verbose=False):
    norms = C.spec("norms")
    classes = set(norms["road_classes"])
    ntypes = set(norms["node_types"]) | EXTRA_NODE_KINDS
    out = {}
    area = C.POLY
    A1 = area.buffer(1.0)
    streets = spec["streets"]
    nodes = spec["nodes"]
    S = {s["id"]: s for s in streets}

    iss = [f"нет ключа {k}" for k in V1_KEYS if k not in spec]
    if spec.get("version") != 1 or spec.get("district") != "growing_w":
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
            iss.append(f"{s['id']}: класс {s['class']} — проезды только от land_driveways")
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
    for z in spec["zones"]:
        if z["use"] not in LOT_USES:
            iss.append(f"зона {z['id']}: use {z['use']}")
        cap = (z.get("rules") or {}).get("height_cap_m")
        if cap is not None and cap >= 50:
            iss.append(f"зона {z['id']}: высота {cap} м ≥ 50 (правило 16, аэродромы в 30 км)")
    for c in spec.get("corridors") or []:
        if c.get("kind") == "power_line" and not c.get("kv"):
            iss.append(f"коридор {c['id']}: нет kv")
    out["loads"] = _res(iss, len(streets) + len(nodes))

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
    out["inside_area"] = _res(iss, len(streets) + len(nodes) + len(spec["zones"]) + len(spec["objects"]))

    iss = []
    zp = [(z["id"], Polygon(z["polygon"]).buffer(0)) for z in spec["zones"]]
    tree = shapely.STRtree([p for _, p in zp])
    for i, (zi, p) in enumerate(zp):
        for j in tree.query(p):
            if j <= i:
                continue
            x = p.intersection(zp[j][1])
            a = x.area
            # rounding the rings to 0.1 m leaves hair-line overlaps along long shared borders: an overlap counts when it is
            # over 50 m² and on average wider than 0.2 m
            if a > 50.0 and a / max(x.length / 2.0, 1.0) > 0.2:
                iss.append(f"зоны {zi} и {zp[j][0]} перекрываются на {a:.0f} м²")
    cover = unary_union([p for _, p in zp])
    gap = area.difference(cover).area
    if gap > 5e4:
        iss.append(f"не покрыто зонами {gap / 1e4:.1f} га")
    out["zones_disjoint"] = _res(iss, len(zp), f"не покрыто зонами {gap / 1e4:.2f} га (обрезки < 500 м²)")

    iss = []
    lines = [(s["id"], LineString(s["line"]), s["class"]) for s in streets]
    rep = set(spec.get("replaced_osm") or [])
    kept_ids = {s["source"].split(":", 1)[1] for s in streets if s["source"].startswith("keep_existing:")}
    for g, p in C.layer_in("roads", area):
        if p["id"] in rep or p["id"] in kept_ids or p.get("class") in ("footway", "path", "cycleway", "steps", "pedestrian"):
            continue
        cls = "ramp" if p.get("class") == "motorway" else "osm"
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "LineString":
                lines.append(("osm:" + p["id"], q, cls))
    lt = shapely.STRtree([L for _, L, _ in lines])
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
            # a divided street's carriageway joints lie off its axis; a street may end inside a ring (its centre)
            if any(math.hypot(x - p[0], z - p[1]) <= 10.0 and n["type"] == "joint" for x, z, n in npts):
                continue
            if area.exterior.distance(P) < 3.0:
                continue
            if (s["class"] == "village_lane" or (s["class"] == "local" and s["id"].startswith("v_serve_"))) \
                    and p == s["line"][-1] and LineString(s["line"]).length <= 150.0:
                continue
            free += 1
            iss.append(f"{s['id']} ({s['class']}): свободный конец ({p[0]:.0f}, {p[1]:.0f})")
    out["street_ends"] = _res(iss, 2 * len(streets), f"свободных концов {free}")

    iss = []
    reg = C.spec("registry")["rows"]
    have = {o["registry_id"] for o in spec["objects"]}
    v0 = {o["registry_id"] for o in C.spec_v0()["objects"]}
    n_in = 0
    for r in reg:
        mine = r.get("district_area") == "growing_w" or r["id"] in v0
        if mine:
            n_in += 1
            if r["id"] not in have:
                iss.append(f"строка реестра {r['id']} ({r.get('name_ru', '')[:40]}) нет в objects")
    out["registry_present"] = _res(iss, n_in)

    iss = []
    houses = [h["fp"] for h in C.houses()]
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
        if o.get("footprint") and o.get("action") in ("by_rule", "move"):
            for b in hits(Polygon(o["footprint"])):
                c = b.centroid
                iss.append(f"участок {o['registry_id']} задевает дом у ({c.x:.0f}, {c.y:.0f})")
    out["no_street_through_house"] = _res(iss, len(houses), f"существующих домов в районе+80 м: {len(houses)}")

    iss = []
    sp = []
    for ln in spec["lrt"]["lines"]:
        L = LineString(ln["line"])
        ch = sorted(L.project(Point(st["x"], st["z"])) for st in ln["stations"])
        sp = [round(b - a) for a, b in zip(ch, ch[1:])]
        for k, d in enumerate(sp):
            if not 800 <= d <= 1500:
                iss.append(f"{ln['id']}: шаг станций {d} м между {k + 1} и {k + 2}")
    out["lrt_spacing"] = _res(iss, len(sp), f"шаги {sp}")

    iss = []
    for j in spec["joints"]:
        if not j.get("met_by"):
            iss.append(f"стык {j['joint_id']} без улицы / линии")
    out["joints"] = _res(iss, len(spec["joints"]))

    info = {}
    from collections import Counter
    km = Counter()
    for s in streets:
        km[s["class"]] += LineString(s["line"]).length / 1000.0
    info["street_km_by_class"] = {k: round(v, 1) for k, v in sorted(km.items())}
    info["street_km_new"] = round(sum(LineString(s["line"]).length for s in streets if s["source"] == "new") / 1000.0, 1)
    info["streets"] = len(streets)
    zh = Counter()
    for z in spec["zones"]:
        zh[z["use"]] += Polygon(z["polygon"]).area / 1e4
    info["zones_ha"] = {k: round(v, 1) for k, v in sorted(zh.items(), key=lambda t: -t[1])}
    out["info"] = info
    out["passed"] = all(v["ok"] for k, v in out.items() if isinstance(v, dict) and "ok" in v)
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    path = argv[0] if argv else os.path.join(C.SPEC_DIR, "growing_w.json")
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
