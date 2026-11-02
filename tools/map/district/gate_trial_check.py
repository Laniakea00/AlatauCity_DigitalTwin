#!/usr/bin/env python3
"""Self-check of tools/map/spec/gate_trial.json (w47, phase A). Not the validator: a cartographer's own gate before the tools run.

    python3 -I tools/map/district/gate_trial_check.py [spec.json]

Checks: the spec loads and uses the contract vocabulary; everything lies inside `area`; every street end is a node, a joint
or an allowed dead end; no new street enters the keep polygon (only at its attach points); every registry row inside the
area is in `objects`; no new street, ramp hint, LRT line or new lot runs through an existing building (Overture/OSM).
Exit code 0 only when every check passes.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from shapely.geometry import LineString, Point, Polygon, shape  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

import gate_common as C  # noqa: E402

V0_KEYS = ["district", "boundary", "targets", "centres", "axes", "zones", "lrt", "objects", "phases", "joints", "checks"]
V1_KEYS = ["area", "edge_joints", "streets", "nodes", "keep", "views"]
EXTRA_NODE_KINDS = {"end", "joint", "edge", "merge", "diverge", "ic"}
STRUCT = {"ground", "embankment", "cut", "bridge", "overpass", "tunnel"}
LOT_USES = {"mixed_centre", "business", "residential_high", "residential_mid", "residential_low", "village_existing", "campus",
            "medical", "industry", "logistics", "utility", "park", "waterfront", "sport", "reserve", "school", "kindergarten",
            "polyclinic", "hospital", "clinic", "pharmacy_shop", "college", "university", "fire_station", "police",
            "sport_ground", "square", "playground", "parking", "substation", "transit", "worship", "culture", "landmark"}
HALF_W = {"expressway": 12.0, "arterial_regulated": 14.0, "arterial_road_regulated": 14.0, "arterial_continuous": 14.0,
          "district_transport": 9.0, "district_pedestrian": 8.0, "local": 5.0, "local_secondary": 4.0, "industrial": 5.0,
          "park_road": 3.0, "driveway_main": 3.0, "driveway_secondary": 2.5, "village_main": 3.0, "village_secondary": 3.0,
          "village_lane": 1.5, "pedestrian_street": 3.0, "boulevard": 12.0, "bike_path": 1.5, "ramp": 4.0}


def _res(issues, n, note=None):
    r = {"ok": not issues, "n": n, "issues": issues[:25]}
    if len(issues) > 25:
        r["more"] = len(issues) - 25
    if note:
        r["note"] = note
    return r


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
    iss = [f"нет ключа {k}" for k in V0_KEYS + V1_KEYS if k not in spec]
    if spec.get("version") != 1 or spec.get("district") != "gate_trial":
        iss.append("version/district")
    ids = [s["id"] for s in streets]
    iss += [f"повтор id улицы {i}" for i in set(ids) if ids.count(i) > 1]
    nids = [n["id"] for n in nodes]
    iss += [f"повтор id узла {i}" for i in set(nids) if nids.count(i) > 1]
    for s in streets:
        if s["class"] not in classes:
            iss.append(f"{s['id']}: класс {s['class']} не из norms")
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
    for ln in spec["lrt"]["lines"]:
        if len(ln["years"]) != 4:
            iss.append(f"{ln['id']}: years")
    out["loads"] = _res(iss, len(streets) + len(nodes))

    # 2 — inside the area
    iss = []
    for s in streets:
        L = LineString(s["line"])
        if not A1.contains(L):
            iss.append(f"улица {s['id']} выходит за area на {L.difference(A1).length:.1f} м")
    for n in nodes:
        if not A1.contains(Point(n["x"], n["z"])):
            iss.append(f"узел {n['id']} вне area")
    for z in spec["zones"]:
        p = Polygon(z["polygon"]).buffer(0)
        if p.difference(A1).area > 1.0:
            iss.append(f"зона {z['id']} вне area: {p.difference(A1).area:.0f} м²")
    for o in spec["objects"]:
        if o.get("footprint") and Polygon(o["footprint"]).difference(A1).area > 1.0:
            iss.append(f"участок {o['registry_id']} вне area")
        if o.get("to") and not A1.contains(Point(o["to"])):
            iss.append(f"объект {o['registry_id']} вне area")
    for ln in spec["lrt"]["lines"]:
        if not A1.contains(LineString(ln["line"])):
            iss.append(f"ЛРТ {ln['id']} вне area")
        for st in ln["stations"]:
            if not A1.contains(Point(st["x"], st["z"])):
                iss.append(f"станция {st['id']} вне area")
    for k in spec["keep"]:
        if Polygon(k["polygon"]).difference(A1).area > 1.0:
            iss.append(f"keep {k['id']} вне area")
    for v in spec["views"]:
        a = v["apex"]; t = math.radians(v["dir_deg"])
        tip = (a[0] + v["len_m"] * math.sin(t), a[1] + v["len_m"] * math.cos(t))
        if not A1.contains(Point(a)) or not A1.contains(Point(tip)):
            iss.append(f"сектор {v['id']} вне area")
    for ej in spec["edge_joints"]:
        if area.exterior.distance(Point(ej["x"], ej["z"])) > 1.0:
            iss.append(f"{ej['id']} не на краю area")
    out["inside_area"] = _res(iss, len(streets) + len(nodes) + len(spec["zones"]) + len(spec["objects"]))

    # 2b — zones do not overlap and cover the area
    iss = []
    zp = [(z["id"], Polygon(z["polygon"]).buffer(0)) for z in spec["zones"]]
    for i in range(len(zp)):
        for j in range(i + 1, len(zp)):
            a = zp[i][1].intersection(zp[j][1]).area
            if a > 50.0:
                iss.append(f"зоны {zp[i][0]} и {zp[j][0]} перекрываются на {a:.0f} м²")
    from shapely.ops import unary_union
    cover = unary_union([p for _, p in zp])
    gap = area.difference(cover).area
    out["zones_disjoint"] = _res(iss, len(zp), f"не покрыто зонами {gap / 1e4:.2f} га (обрезки < 500 м²)")

    # 3 — every street end is a node, joint or allowed dead end
    iss = []
    ej_pts = [(e["x"], e["z"]) for e in spec["edge_joints"] if e.get("street")]
    for s in streets:
        for p in (s["line"][0], s["line"][-1]):
            hit = [n for n in nodes if math.hypot(n["x"] - p[0], n["z"] - p[1]) <= 1.5]
            if hit:
                if not any(s["id"] in n["streets"] for n in hit):
                    iss.append(f"{s['id']}: конец ({p[0]:.0f}, {p[1]:.0f}) у узла {hit[0]['id']}, но улица не в его списке")
                continue
            if any(math.hypot(x - p[0], z - p[1]) <= 1.5 for x, z in ej_pts):
                continue
            iss.append(f"{s['id']}: свободный конец ({p[0]:.0f}, {p[1]:.0f})")
    ends = sum(1 for n in nodes if n["type"] == "end")
    out["street_ends"] = _res(iss, 2 * len(streets), f"узлов-тупиков (end) {ends}")

    # 4 — keep polygon not crossed by new streets
    iss = []
    for k in spec["keep"]:
        K0 = Polygon(k["polygon"])
        K = K0.buffer(-1.0)
        # an attach point is the quarter's own street end, a few metres inside the rim: the new street may run from it
        # straight out to the rim (disc = distance to the rim + 3 m)
        att = [Point(a["x"], a["z"]).buffer(max(4.0, K0.exterior.distance(Point(a["x"], a["z"])) + 3.0)) for a in k["attach"]]
        for s in streets:
            if s["source"] != "new":
                continue
            L = LineString(s["line"])
            for a in att:
                L = L.difference(a)
            if L.intersects(K):
                iss.append(f"{s['id']} входит в {k['id']} на {L.intersection(K).length:.1f} м")
        for s in streets:
            if s["source"] != "new":
                continue
            for p in (s["line"][0], s["line"][-1]):
                if K.contains(Point(p)) and not any(a.contains(Point(p)) for a in att):
                    iss.append(f"{s['id']}: конец внутри квартала не в точке примыкания")
    out["keep_not_crossed"] = _res(iss, len(streets))

    # 5 — registry rows inside the area are all in objects
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
        if any(g.intersects(area) for g in geoms):
            n_in += 1
            if r["id"] not in have:
                iss.append(f"строка реестра {r['id']} ({r.get('name_ru', '')[:40]}) в area, но нет в objects")
    out["registry_present"] = _res(iss, n_in)

    # 6 — no new street / ramp / LRT / lot through an existing building
    iss = []
    blds = [g for g, p in C.layer_in("buildings", area.buffer(60))]
    tree = STRtree(blds)

    def hits(geom):
        return [blds[i] for i in tree.query(geom) if blds[i].intersects(geom)]

    for s in streets:
        if s["source"] != "new":
            continue
        g = LineString(s["line"]).buffer(HALF_W.get(s["class"], 5.0), cap_style=2)
        for b in hits(g):
            c = b.centroid
            iss.append(f"улица {s['id']} задевает здание у ({c.x:.0f}, {c.y:.0f}), {b.area:.0f} м²")
    for n in nodes:
        for k, line in (n.get("params", {}).get("ramps_hint") or {}).items():
            g = LineString(line).buffer(5.0, cap_style=2)
            for b in hits(g):
                c = b.centroid
                iss.append(f"съезд {n['id']}/{k} задевает здание у ({c.x:.0f}, {c.y:.0f})")
    for ln in spec["lrt"]["lines"]:
        for b in hits(LineString(ln["line"]).buffer(5.0)):
            c = b.centroid
            iss.append(f"ЛРТ задевает здание у ({c.x:.0f}, {c.y:.0f})")
    for o in spec["objects"]:
        if o.get("footprint") and o.get("action") == "by_rule":
            for b in hits(Polygon(o["footprint"])):
                c = b.centroid
                iss.append(f"участок {o['registry_id']} задевает здание у ({c.x:.0f}, {c.y:.0f})")
    out["no_street_through_house"] = _res(iss, len(blds), f"зданий Overture/OSM в area+60 м: {len(blds)}")

    # info (not gating): interchange spacing, LRT stations between cross streets, LRT crossings
    info = {}
    ics = [n for n in nodes if n["type"] in ("diamond", "partial_cloverleaf", "cloverleaf", "trumpet", "directional")]
    for i in range(len(ics)):
        for j in range(i + 1, len(ics)):
            a, b = ics[i], ics[j]
            info[f"spacing_{a['id']}__{b['id']}_m"] = round(math.hypot(a["x"] - b["x"], a["z"] - b["z"]))
    for ln in spec["lrt"]["lines"]:
        L = LineString(ln["line"])
        ch = sorted(round(L.project(Point(st["x"], st["z"]))) for st in ln["stations"])
        info[f"{ln['id']}_station_chainage_m"] = ch
        info[f"{ln['id']}_station_spacing_m"] = [b - a for a, b in zip(ch, ch[1:])]
        elev = [LineString([sec["from"], sec["to"]]) for sec in ln["sections"] if sec["kind"] == "elevated"]
        xs = []
        for s in streets:
            if s["id"] == "s_east":
                continue
            x = LineString(s["line"]).intersection(L)
            for p in ([x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"]):
                s_m = L.project(p)
                kind = next((sec["kind"] for sec in ln["sections"]
                             if L.project(Point(sec["from"])) - 1 <= s_m <= L.project(Point(sec["to"])) + 1), "?")
                xs.append(f"{s['id']}@{s_m:.0f}м:{kind}")
        info[f"{ln['id']}_crossings"] = xs
    out["info"] = info
    out["passed"] = all(v["ok"] for k, v in out.items() if isinstance(v, dict) and "ok" in v)
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    path = argv[0] if argv else os.path.join(C.SPEC_DIR, "gate_trial.json")
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    res = run(spec)
    for k, v in res.items():
        if isinstance(v, dict) and "ok" in v:
            print(f"{'OK ' if v['ok'] else 'ERR'} {k}: n={v['n']}" + (f" · {v['note']}" if v.get("note") else ""))
            for i in v["issues"]:
                print("     ", i)
    for k, v in res["info"].items():
        print("  info", k, v)
    print("PASSED" if res["passed"] else "FAILED")
    return res["passed"]


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
