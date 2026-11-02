"""Streets of gen_network (w43): synthetic cases built through gen_network → validate_map (rules 0, 5–11) on flat
ground far outside the twin (as test_templates):

* kink    — a divided street continued by another divided street with a 2.5° bend: the carriageway ends of the two
            streets are joined (no `end` nodes 0.4 m apart);
* t21     — a divided arterial ending obliquely (21°) on an undivided road: both carriageways end on the host;
* t30     — a wider divided street (8 m median) ending at 30° on an undivided road: both carriageways end on it;
* riro    — a divided arterial ending at a right_in_right_out node at 23° on a short host (a local road between two
            cross streets), its line drawn 6 m past the host axis: both carriageways are trimmed to the host;
* bridge  — a divided street with a spec `struct` bridge over a stream drawn as a line (not in the water polygons):
            its segments carry the bridge, the deck clears the ground under it by the water clearance + deck depth,
            and the at-grade runs either side of it are split by mid-block crossings (rule 10);
* short   — a 7 m lane from a free end on to a street: kept at its length, no crash;
* ysplit  — a divided street ending in 2028 at a signal where it continues in 2029, a divided arterial starting
            there (2028): the arterial's far carriageway reaches the street in 2028 (no one-year blind end);
* tsnap   — an oblique divided street split 2035 / 2036 with a local street of 2035 ending at the split from the
            side: both carriageways of 2035 and the local street meet in 2035;
* rail    — a street with a spec `struct` overpass over three railway tracks (synthetic, in place of osm/rail.geojson):
            an overpass run over each track and the underside of the deck ≥ bridges.rail_clearance_m over it;
* railx   — a new local street crossing a track in one level: the generator logs an error and rule 6 reports one
            (the only errors of the case);
* ring    — a local street drawn as a closed ring (first point = last point, w50 golden e_p03_0_0) crossed by a
            straight street: the network keeps the whole ring (its closing piece too), no `end` node;
* loopend — a turning ring drawn as a closed one-way street (streets[].oneway true, R 16 m, as w47 gate_trial
            s_griffin_ring) with a street ending on it at a spec crossing node (the ray of snap_street_ends meets the
            ring twice): the street ends on the ring's near side, no segment runs across the island; the ring is
            one-way from streets[].oneway; the street's own oneway true against profile.oneway false keeps the
            profile (two-way) and logs it;
* chain   — a kept existing interchange (params.keep_existing, w53 Growing-E ic_a3_km44) whose two OSM ramp pieces
            (synthetic, in place of osm/roads.geojson) meet end to start with nobody else there, each a keep_existing
            spec street of its own: net_osm chains them into one way, yet every segment carries the street and OSM id
            of the piece it lies on and rule 7 finds both ramps on their lines (no error);
* lrtx    — a ground LRT line crossing a local street 8 m from its junction with another (w50 golden s774) and both
            carriageways of a continuous arterial: the junction is the level crossing (crossing_signal, `lrt`), the
            arterial crossings are errors of the generator log and of rule 6 (the only errors of the case).

    python3 tools/map/tests/test_streets.py [--out OUT] [--only t21,riro]

Writes OUT/_tools/streets/se_<case>/{network.json, report.*}. Exit code 0 when every case passes: no `end` node,
every carriageway end of the divided street is a node of the host (or of the continuing street), no carriageway of it
reaches past the host (the bridge: a bridge run on each carriageway, deck high enough; ysplit, tsnap: no node is a
dead end in any year of any scenario and joined later), 0 validator errors.
"""
import argparse
import io
import json
import math
import os
import sys
import tempfile
from contextlib import redirect_stdout

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
sys.path.insert(0, MAP)
sys.path.insert(0, os.path.join(MAP, "gen"))
sys.path.insert(0, os.path.join(MAP, "validate"))
from lib import paths  # noqa: E402

C = (30000.0, 30000.0)
HALF = 1500.0
YEARS = [2030, 2029, 2033, 2030]


Y1 = [2028, 2027, 2029, 2028]           # a year split between two stage years of the validator (2026, 2030, …)
Y2 = [2029, 2028, 2030, 2029]
Y3 = [2035, 2033, 2038, 2035]
Y4 = [2036, 2033, 2039, 2036]


def _st(sid, cls, line, profile=None, years=None):
    return {"id": sid, "class": cls, "line": [[round(float(x), 2), round(float(z), 2)] for x, z in line],
            "name_ru": sid, "years": list(years or YEARS), "source": "new", "profile": profile or {}}


def _dir(deg):
    return np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg))])


def spec_for(case):
    x0, z0 = C
    c = np.array(C)
    area = [[x0 - HALF, z0 - HALF], [x0 + HALF, z0 - HALF], [x0 + HALF, z0 + HALF], [x0 - HALF, z0 + HALF]]
    nodes = []
    if case == "kink":
        d = _dir(90.0 - 2.5)
        sts = [_st("A", "district_transport", [(x0, z0 - HALF), (x0, z0)], {"median_w": 8.0, "lanes": [2, 2]}),
               _st("B", "district_transport", [c, c + d * (HALF / d[1] - 0.5)], {"median_w": 8.0, "lanes": [2, 2]})]
        street, host = "A", "B"
    elif case in ("t21", "t30"):
        ang = 21.0 if case == "t21" else 30.0
        prof = {} if case == "t21" else {"median_w": 8.0, "lanes": [2, 2]}
        cls = "arterial_regulated" if case == "t21" else "district_transport"
        sts = [_st("H", "district_transport", [(x0 - HALF, z0), (x0 + HALF, z0)]),
               _st("S", cls, [c - _dir(ang) * (HALF / _dir(ang)[0] - 0.5), c], prof)]
        street, host = "S", "H"
    elif case == "bridge":
        st = _st("S", "district_transport", [(x0 - HALF + 0.5, z0), (x0 + HALF - 0.5, z0)], {"median_w": 8.0, "lanes": [2, 2]})
        st["struct"] = [{"from": [x0 - 12.0, z0], "to": [x0 + 12.0, z0], "kind": "bridge"}]
        sts = [st]
        street, host = "S", None
    elif case == "riro":
        ang = 23.0
        sts = [_st("K1", "district_transport", [(x0 - 80.0, z0 - HALF), (x0 - 80.0, z0 + HALF)]),
               _st("K2", "district_transport", [(x0 + 80.0, z0 - HALF), (x0 + 80.0, z0 + HALF)]),
               _st("H", "local", [(x0 - 80.0, z0), (x0 + 80.0, z0)]),
               _st("S", "arterial_regulated", [c - _dir(ang) * (HALF / _dir(ang)[0] - 0.5), c + _dir(ang) * 6.0])]
        nodes = [{"id": "n_riro", "x": x0, "z": z0, "type": "right_in_right_out", "streets": ["S", "H"]}]
        street, host = "S", "H"
    elif case == "short":
        # a 7 m lane from a free end on to a street (gate.json v_link_22 left the dead end of an OSM village street this
        # way): the free end looks back along the lane onto that street, its own other end; trimming to it would leave a
        # point and stop the run
        sts = [_st("N", "local", [(x0 + 7.0, z0 - HALF + 0.5), (x0 + 7.0, z0 + HALF - 0.5)]),
               _st("L", "village_lane", [(x0, z0), (x0 + 7.0, z0)])]
        street, host = "L", "N"
    elif case == "ysplit":
        # gate.json s_east (2028) / s_east_m (2029) at Проспект Ворот: a divided street ends at a signal where it is
        # continued a year later; a divided arterial starts there eastwards and a pedestrian street westwards. The
        # arterial's far carriageway lies 4.5 m past the axis split, on the next year's piece of the street
        prof = {"median_w": 8.0, "lanes": [2, 2]}
        sts = [_st("E", "district_transport", [(x0, z0 + HALF - 0.5), (x0, z0)], prof, Y1),
               _st("Em", "district_transport", [(x0, z0), (x0, z0 - HALF + 0.5)], prof, Y2),
               _st("A", "arterial_regulated", [(x0, z0), (x0 + HALF - 0.5, z0)], None, Y1),
               _st("P", "pedestrian_street", [(x0, z0), (x0 - HALF + 0.5, z0)], None, Y1)]
        nodes = [{"id": "n_split", "x": x0, "z": z0, "type": "crossing_signal", "streets": ["E", "A", "Em", "P"]}]
        street, host = "E", "A"
    elif case == "tsnap":
        # gate.json s_east_n_y2 (2035) / s_east_n_y3 (2036), 12.5° off the z axis, with a local street of 2035 ending at
        # the split from the side: the local street T-snaps to the far carriageway, which crosses its line on the
        # 2036 piece, and the near-side carriageway's 2035 end stops 1.7 m short of it
        prof = {"median_w": 8.0, "lanes": [2, 2]}
        d = _dir(90.0 - 12.5)
        L = (HALF - 0.5) / d[1]
        sts = [_st("D1", "district_transport", [c - d * L, c], prof, Y3),
               _st("D2", "district_transport", [c, c + d * L], prof, Y4),
               _st("T", "local", [(x0 - HALF + 0.5, z0), c], None, Y3)]
        street, host = "T", "D1"
    elif case == "ring":
        sq = [(x0 - 60.0, z0 - 40.0), (x0 + 60.0, z0 - 40.0), (x0 + 60.0, z0 + 40.0), (x0 - 60.0, z0 + 40.0), (x0 - 60.0, z0 - 40.0)]
        sts = [_st("R", "local", sq), _st("X", "local", [(x0, z0 - HALF + 0.5), (x0, z0 + HALF - 0.5)])]
        street, host = "R", "X"
    elif case == "loopend":
        R = 16.0
        ring = [(x0 + R * math.cos(math.radians(a)), z0 + R * math.sin(math.radians(a))) for a in range(0, 360, 15)]
        ring.append(ring[0])
        st_r = _st("R", "industrial", ring)
        st_r["oneway"] = True
        st_s = _st("S", "industrial", [(x0 + HALF, z0), (x0 + R, z0)], {"oneway": False})
        st_s["oneway"] = True
        sts = [st_r, st_s]
        nodes = [{"id": "n_in", "x": x0 + R, "z": z0, "type": "crossing", "streets": ["S", "R"]}]
        street, host = "S", "R"
    elif case == "chain":
        ex = [2025] * 4
        sts = []
        for oid, P in chain_osm().items():
            st = _st("k_" + oid[:8], "ramp", P, None, ex)
            st.update(source=f"keep_existing:{oid}", oneway=True)
            sts.append(st)
        nodes = [{"id": "ic_keep", "x": x0, "z": z0, "type": "diamond", "streets": [],
                  "params": {"keep_existing": True, "osm_ids": list(chain_osm()), "radius_m": 350.0}}]
        street, host = None, None
    elif case == "lrtx":
        sts = [_st("L", "local", [(x0 - HALF + 0.5, z0), (x0 + HALF - 0.5, z0)]),
               _st("K", "local", [(x0 + 8.0, z0 - 100.0), (x0 + 8.0, z0 + 100.0)]),
               _st("A", "arterial_continuous", [(x0 - HALF + 0.5, z0 + 400.0), (x0 + HALF - 0.5, z0 + 400.0)],
                   {"sidewalk_w": [0.0, 0.0]})]
        street, host = None, None
    elif case in ("rail", "railx"):
        cls = "district_transport" if case == "rail" else "local"
        st = _st("S", cls, [(x0 - HALF + 0.5, z0), (x0 + HALF - 0.5, z0)])
        if case == "rail":
            st["struct"] = [{"from": [x0 - 60.0, z0], "to": [x0 + 60.0, z0], "kind": "overpass"}]
        sts = [st]
        street, host = "S", None
    else:
        raise KeyError(case)
    spec = {"district": f"se_{case}", "version": 1, "level": 1, "made_by": "w43 tests", "area": area, "boundary": area,
            "area_ignores_boundary": True, "zones": [], "streets": sts, "nodes": nodes, "lrt": {}, "edge_joints": [],
            "keep": []}
    if case == "lrtx":
        spec["lrt"] = {"lines": [{"id": "lrt_t", "name_ru": "ЛРТ (тест)", "line": [[x0, z0 - HALF], [x0, z0 + HALF]],
                                  "sections": [], "stations": [], "years": YEARS}]}
    return spec, street, host


def rail_tracks(case):
    """Synthetic tracks of the rail cases (lib.rail.tracks format), along z through the street: three at x0 − 6, x0,
    x0 + 6 under the overpass; one at x0 for the crossing in one level."""
    x0, z0 = C
    xs = (-6.0, 0.0, 6.0) if case == "rail" else (0.0,)
    return [{"id": f"track{k}", "piece": "0.0", "P": np.array([[x0 + dx, z0 - 400.0], [x0 + dx, z0 + 400.0]]), "up": False,
             "name": f"путь {k}"} for k, dx in enumerate(xs)]


def chain_osm():
    """{Overture id: line} of the chain case: two ramp pieces, the first ending where the second starts (x0, z0)."""
    x0, z0 = C
    return {"71dada4c-test-0000-0000-000000000001": [(x0 - 100.0, z0 - 180.0), (x0 - 60.0, z0 - 60.0), (x0, z0)],
            "c5dc1f4a-test-0000-0000-000000000002": [(x0, z0), (x0 - 35.0, z0 + 25.0), (x0 - 30.0, z0 + 200.0)]}


def chain_geojson(orig):
    """jio.load_geojson with osm/roads.geojson and connectors.geojson replaced by the chain case's pieces."""
    pieces = list(chain_osm().items())
    ends = []
    for _, P in pieces:
        for p in (P[0], P[-1]):
            if p not in ends:
                ends.append(p)
    roads = [{"type": "Feature", "properties": {"id": oid, "class": "motorway", "sub": "link", "name": "",
                                                "conn": [ends.index(P[0]), ends.index(P[-1])]},
              "geometry": {"type": "LineString", "coordinates": [list(p) for p in P]}} for oid, P in pieces]
    conns = [{"type": "Feature", "properties": {"i": i}, "geometry": {"type": "Point", "coordinates": list(p)}}
             for i, p in enumerate(ends)]

    def load(path, *a, **kw):
        if os.path.abspath(path) == os.path.abspath(paths.w34("osm", "roads.geojson")):
            return roads
        if os.path.abspath(path) == os.path.abspath(paths.w34("osm", "connectors.geojson")):
            return conns
        return orig(path, *a, **kw)
    return load


def check_chain(net, rep):
    """Both pieces are in the network, each segment with its piece's street and OSM id; the two were chained into one
    way (log); rule 7 reports no error and finds 2 of 2 OSM roads on their lines."""
    import shapely
    bad = []
    lines = {oid: shapely.LineString(P) for oid, P in chain_osm().items()}
    got = {}
    for s in net["segments"]:
        Q = shapely.LineString([p[:2] for p in s["pts"]])
        oid = min(lines, key=lambda k: lines[k].distance(Q.interpolate(0.5, normalized=True)))
        got[oid] = got.get(oid, 0.0) + Q.length
        if s.get("street") != "k_" + oid[:8] or s.get("source") != f"osm:{oid}":
            bad.append(f"{s['id']} на линии osm:{oid[:8]}: street {s.get('street')}, source {s.get('source')}")
    for oid, g in lines.items():
        if abs(got.get(oid, 0.0) - g.length) > 1.0:
            bad.append(f"osm:{oid[:8]}: в сети {got.get(oid, 0.0):.1f} м из {g.length:.1f} м")
    if not any(e["what"].startswith("OSM: части одной дороги соединены") for e in net.get("log", [])):
        bad.append("части не соединены в одну дорогу (случай не проверяет _chain)")
    info = [i["what_ru"] for i in rep["issues"] if i["rule"] == 7 and i["sev"] == "info"]
    if not any("2 из 2 дорог OSM на своих линиях" in t for t in info):
        bad.append("правило 7: " + "; ".join(info or ["нет записи о развязке keep_existing"]))
    print(f"      цепочка: отрезков {len(net['segments'])}, улицы {sorted({s.get('street') for s in net['segments']})}")
    return _result(net, rep, bad)


def check_loopend(net, rep):
    """S ends on the ring's near side (no point of S inside the ring's island), the ring is one-way (streets[].oneway),
    S stays two-way (its profile.oneway false wins) with the conflict in the log."""
    R = 16.0
    bad = []
    s_pts = [p for s in net["segments"] if s.get("street") == "S" for p in s["pts"]]
    inside = min((math.hypot(p[0] - C[0], p[1] - C[1]) for p in s_pts), default=0.0)
    if inside < R - 1.0:
        bad.append(f"улица S заходит в островок кольца: {inside:.1f} м от центра при R {R:.0f} м")
    ring = [s for s in net["segments"] if s.get("street") == "R"]
    if not ring or not all(s["oneway"] for s in ring):
        bad.append(f"кольцо R не одностороннее (streets[].oneway): {[s['oneway'] for s in ring]}")
    if any(s["oneway"] for s in net["segments"] if s.get("street") == "S"):
        bad.append("улица S односторонняя, хотя profile.oneway false")
    if not any("oneway улицы и profile.oneway расходятся" in e["what"] for e in net.get("log", [])):
        bad.append("нет записи о расхождении oneway и profile.oneway")
    print(f"      кольцо: улица S ближе всего {inside:.1f} м от центра (R {R:.0f}), отрезков кольца {len(ring)}")
    return _result(net, rep, bad)


def check_lrtx(net, rep):
    """The ground LRT crosses L 8 m from L's junction with K: that junction is the level crossing (crossing_signal with
    `lrt`, no second node), and rule 8 accepts the signal on local × local; the crossings of both carriageways of the
    continuous arterial A are errors of the generator log and of rule 6 (no node there), and nothing else is an error."""
    bad = []
    at = {}
    for s in net["segments"]:
        for e in (s["a"], s["b"]):
            at.setdefault(e, set()).add(s.get("street"))
    lx = [n for n in net["nodes"] if n.get("lrt")]
    if len(lx) != 1:
        bad.append(f"узлов-переездов ЛРТ {len(lx)} (нужен 1, на улице L): {[(n['id'], sorted(at.get(n['id'], ()))) for n in lx]}")
    for n in lx:
        if n["kind"] != "crossing_signal" or at.get(n["id"]) != {"L", "K"} or abs(n["x"] - (C[0] + 8.0)) > 0.5:
            bad.append(f"переезд {n['id']}: {n['kind']}, улицы {sorted(at.get(n['id'], ()))}, x − x0 = {n['x'] - C[0]:.1f}")
    r = _result(net, rep, bad)
    r6 = [e for e in r["err_list"] if e.startswith("п.6:") and "ЛРТ" in e]
    na = len([s for s in net["segments"] if s.get("street") == "A" and min(p[0] for p in s["pts"]) < C[0] < max(p[0] for p in s["pts"])])
    if len(r6) != 2 or len(r["err_list"]) != len(r6):
        bad.append(f"ошибок правила 6 о ЛРТ {len(r6)} (нужно 2: обе проезжие части A, отрезков A через линию {na}); прочих "
                   f"{[e for e in r['err_list'] if e not in r6]}")
    if sum("ЛРТ на земле пересекает arterial_continuous" in g for g in r["gen_err"]) != 2:
        bad.append(f"журнал генератора: {r['gen_err']}")
    print(f"      переезды ЛРТ: узлов {len(lx)} ({', '.join(n['kind'] for n in lx)}), ошибок правила 6 {len(r6)}")
    r["expected_errors"] = True
    return r


CASES = ["kink", "t21", "t30", "riro", "bridge", "short", "ysplit", "tsnap", "rail", "railx", "ring", "loopend", "chain", "lrtx"]


def run_case(case, out, tmp):
    import gen_network
    import validate_map
    spec, street, host = spec_for(case)
    path = os.path.join(tmp, f"se_{case}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    buf = io.StringIO()
    from lib import jio, rail
    import net_osm
    all_tracks, load_geojson, flags = rail._all, jio.load_geojson, net_osm._flags
    if case in ("rail", "railx"):
        rail._all = lambda: rail_tracks(case)
    if case == "chain":
        jio.load_geojson = chain_geojson(load_geojson)
        net_osm._flags = lambda ids: {}
    try:
        with redirect_stdout(buf):
            gen_network.main([path, "--out", out, "--no-village"])
            if case == "lrtx":
                import gen_lrt
                gen_lrt.main([path, "--out", out])
            validate_map.main([path, "--out", out, "--rules", "0,5,6,7,8,9,10,11"])
    finally:
        rail._all, jio.load_geojson, net_osm._flags = all_tracks, load_geojson, flags
    rep = json.load(open(os.path.join(out, f"se_{case}", "report.json"), encoding="utf-8"))
    net = json.load(open(os.path.join(out, f"se_{case}", "network.json"), encoding="utf-8"))
    if case == "short":
        return check_short(net, rep, street, host)
    if case in ("ysplit", "tsnap"):
        return check_years(net, rep)
    if case in ("rail", "railx"):
        return check_rail(net, rep, case)
    if case == "ring":
        return check_ring(net, rep, spec)
    if case == "chain":
        return check_chain(net, rep)
    if case == "loopend":
        return check_loopend(net, rep)
    if case == "lrtx":
        return check_lrtx(net, rep)
    return check_bridge(net, rep) if case == "bridge" else check(net, rep, street, host)


def check_short(net, rep, street, host):
    """The lane is kept at its drawn length (7 m) and shares a node with the street."""
    mine = [s for s in net["segments"] if s.get("street") == street]
    L = sum(float(np.hypot(*np.diff(np.array([p[:2] for p in s["pts"]]), axis=0).T).sum()) for s in mine)
    hn = {e for s in net["segments"] if s.get("street") == host for e in (s["a"], s["b"])}
    joins = sorted({e for s in mine for e in (s["a"], s["b"])} & hn)
    bad = []
    if L < 6.5:
        bad.append(f"улица {street}: {L:.1f} м из 7")
    if not joins:
        bad.append(f"улица {street} не примыкает к {host}")
    return _result(net, rep, bad, joins)


def check_years(net, rep):
    """In every year of every scenario no node is a dead end that is joined later (both carriageways of the street
    and the road ending at it meet at the year split), and both carriageways of the divided street at the split are
    nodes of the cross road in the year they are built."""
    nodes = {n["id"]: n for n in net["nodes"]}
    final = {}
    for s in net["segments"]:
        for e in (s["a"], s["b"]):
            final[e] = final.get(e, 0) + 1
    bad = []
    for k, scen in enumerate(["base", "fast", "slow", "infra"]):
        for yr in sorted({int(s["years"][k]) for s in net["segments"]}):
            deg = {}
            for s in net["segments"]:
                if int(s["years"][k]) <= yr:
                    for e in (s["a"], s["b"]):
                        deg[e] = deg.get(e, 0) + 1
            for nid, dg in deg.items():
                n = nodes[nid]
                if dg == 1 and final[nid] > 1 and n["kind"] not in ("joint", "edge"):
                    bad.append(f"{scen} {yr}: тупик {nid} ({n['x'] - C[0]:+.1f}, {n['z'] - C[1]:+.1f}), "
                               f"примыкает позже")
    joins = sorted(e for e, dg in final.items()
                   if dg > 2 and np.hypot(nodes[e]["x"] - C[0], nodes[e]["z"] - C[1]) < 30.0)
    return _result(net, rep, bad, joins)


def _result(net, rep, bad, joins=()):
    errs = [f"п.{i['rule']}: {i['what_ru']}" for i in rep["issues"] if i["sev"] == "error"]
    gerr = [e["what"] for e in net.get("log", []) if e.get("error")]
    return {"bad": bad, "errors": rep["counts"]["error"], "warnings": rep["counts"]["warning"], "err_list": errs,
            "gen_err": gerr, "segments": len(net["segments"]), "ends": sum(n["kind"] == "end" for n in net["nodes"]),
            "joins": list(joins)}


def check_bridge(net, rep):
    """Each carriageway has a bridge run over x0 ± 12 m; the deck there is ≥ ground + water clearance + deck depth."""
    from lib import model, norms, terrain
    need = float(norms.get().norm("bridges.river_clearance_m", "backwater_up_to_1m")) + model("deck_depth_m")
    bad = []
    for sgn in (+1, -1):
        runs, low = [], []
        for s in net["segments"]:
            if not s["oneway"] or (s["pts"][-1][0] - s["pts"][0][0]) * sgn <= 0:
                continue
            P = np.array(s["pts"], float)
            S = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])
            for r in s["struct"]:
                if r["kind"] != "bridge":
                    continue
                m = (S >= r["from_m"] - 1e-6) & (S <= r["to_m"] + 1e-6)
                xs = np.interp([r["from_m"], r["to_m"]], S, P[:, 0])
                runs.append((round(float(min(xs)) - C[0], 1), round(float(max(xs)) - C[0], 1)))
                dy = P[m, 2] - terrain.h(P[m, 0], P[m, 1])
                low.append(float(dy.min()) if m.any() else -1.0)
        if not runs:
            bad.append(f"проезжая часть {'+' if sgn > 0 else '-'}: нет моста")
        elif min(low) < need - 0.02:
            bad.append(f"проезжая часть {'+' if sgn > 0 else '-'}: настил над землёй {min(low):.2f} м < {need:.2f} м")
        else:
            print(f"      мост {'+' if sgn > 0 else '-'}: x {runs}, настил над землёй ≥ {min(low):.2f} м (нужно {need:.2f})")
    return _result(net, rep, bad)


def check_ring(net, rep, spec):
    """The ring street's segments add up to its drawn length (the closing piece is kept) and no node is an end."""
    st = next(s for s in spec["streets"] if s["id"] == "R")
    P = np.array(st["line"], float)
    drawn = float(np.hypot(*np.diff(P, axis=0).T).sum())
    got = sum(float(np.hypot(*np.diff(np.array([p[:2] for p in s["pts"]]), axis=0).T).sum()) for s in net["segments"]
              if s.get("street") == "R")
    bad = [f"кольцо: в сети {got:.1f} м из {drawn:.1f} м"] if abs(got - drawn) > 1.0 else []
    bad += [f"узел end {n['id']} ({n['x']:.1f}, {n['z']:.1f})" for n in net["nodes"] if n["kind"] == "end"]
    print(f"      кольцо: в сети {got:.1f} м из {drawn:.1f} м")
    return _result(net, rep, bad)


def check_rail(net, rep, case):
    """rail: every track crossing lies on an overpass run, its underside ≥ rail clearance over the track; railx: the
    crossing is an error of the generator log and of rule 6, and nothing else is an error."""
    from lib import geom as G
    from lib import model, norms, terrain
    clear = float(norms.get().norm("bridges.rail_clearance_m"))
    depth = model("deck_depth_m")
    bad = []
    rows = []
    for t in rail_tracks(case):
        for s in net["segments"]:
            P = np.array(s["pts"], float)
            S = G.chainage(P[:, :2])
            for s1, _, pt, _ in G.crossings(P[:, :2], t["P"]):
                kind = next((r["kind"] for r in s["struct"] if r["from_m"] - 0.5 <= s1 <= r["to_m"] + 0.5 and r["kind"] != "ground"), "ground")
                under = float(np.interp(s1, S, P[:, 2])) - depth - float(terrain.h(pt[0], pt[1]))
                rows.append((t["id"], s["id"], kind, under))
    if not rows:
        bad.append("улица не пересекает пути")
    if case == "rail":
        for tid, sid, kind, under in rows:
            if kind != "overpass":
                bad.append(f"{sid} над {tid}: {kind}, не путепровод")
            elif under < clear - model("height_round_tol_m"):
                bad.append(f"{sid} над {tid}: низ пролёта {under:.2f} м < {clear:.1f} м")
        print(f"      путепровод над путями: низ пролёта {', '.join(f'{u:.2f}' for _, _, _, u in rows)} м (нужно ≥ {clear:.1f})")
        return _result(net, rep, bad)
    r = _result(net, rep, bad)
    r6 = [e for e in r["err_list"] if e.startswith("п.6:") and "ж/д" in e]
    if len(r6) != len(rows) or len(r["err_list"]) != len(r6):
        bad.append(f"ошибок правила 6 о переезде {len(r6)} из {len(rows)}; прочих ошибок {len(r['err_list']) - len(r6)}")
    if not any("ж/д в одном уровне" in g for g in r["gen_err"]):
        bad.append("генератор не записал переезд в журнал как ошибку")
    print(f"      переезд: {len(r6)} ошибка правила 6, журнал генератора: {len(r['gen_err'])}")
    r["expected_errors"] = True
    return r


def check(net, rep, street, host):
    import shapely
    nodes = {n["id"]: n for n in net["nodes"]}
    by_node = {}
    for s in net["segments"]:
        for e in (s["a"], s["b"]):
            by_node.setdefault(e, []).append(s)
    bad = []
    ends = [n for n in net["nodes"] if n["kind"] == "end"]
    for n in ends:
        bad.append(f"узел end {n['id']} ({n['x']:.1f}, {n['z']:.1f})")
    # the street's carriageway ends near the junction: each one a node shared with the host
    host_lines = [shapely.LineString([p[:2] for p in s["pts"]]) for s in net["segments"] if s.get("street") == host]
    host_u = shapely.union_all(host_lines)
    near = []
    for nid, segs in by_node.items():
        n = nodes[nid]
        if np.hypot(n["x"] - C[0], n["z"] - C[1]) > 60.0:
            continue
        mine = [s for s in segs if s.get("street") == street]
        if mine and any(s.get("street") == host for s in segs):
            near.append(nid)
    # past the host: a carriageway point of the street on the far side of the host line (more than 0.5 m)
    far = 0
    if host != "B":
        for s in net["segments"]:
            if s.get("street") != street:
                continue
            for x, z, _ in s["pts"]:
                if np.hypot(x - C[0], z - C[1]) < 60.0 and z > C[1] + 0.5 and host_u.distance(shapely.Point(x, z)) > 0.5:
                    far += 1
        if far:
            bad.append(f"{far} точек улицы {street} за дорогой {host}")
    if len(near) < 2:
        bad.append(f"узлов улицы {street} на {host} у примыкания: {len(near)} (нужно 2)")
    return _result(net, rep, bad, near)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None)
    a = ap.parse_args(argv)
    out = os.path.join(a.out or paths.OUT, "_tools", "streets")
    os.makedirs(out, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        for case in CASES:
            if only and case not in only:
                continue
            r = run_case(case, out, tmp)
            fail = bool(r["bad"]) or (not r.get("expected_errors") and (r["errors"] > 0 or bool(r["gen_err"])))
            fails += fail
            print(f"{'ERR' if fail else 'ok '} {case:5s}: отрезков {r['segments']}, узлов end {r['ends']}, "
                  f"примыканий к дороге {len(r['joins'])} ({', '.join(r['joins'])}), ошибок {r['errors']}, "
                  f"предупреждений {r['warnings']}")
            for b in r["bad"] + r["err_list"] + [f"генератор: {g}" for g in r["gen_err"]]:
                print(f"      ! {b}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
