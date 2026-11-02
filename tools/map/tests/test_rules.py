"""Unit checks of single validator rules on hand-made data (w43). No files are read or written except the norms.

    python3 tools/map/tests/test_rules.py

Rule 25 grade: centimetre rounding of rail heights on a line designed just under lrt.ramp_slope_max_pct never gives
an error (the w47 gate_trial case: 6.1 % on a 1.8 m vertex pair), while a real over-slope (sustained a little over the
norm, steep over 100 m, or a short step) is still an error. Exit code 0 when every check passes.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
sys.path.insert(0, MAP)
sys.path.insert(0, os.path.join(MAP, "validate"))
sys.path.insert(0, os.path.join(MAP, "gen"))
from lib import geom as G  # noqa: E402
from lib import norms  # noqa: E402
from context import Ctx  # noqa: E402
from rules import lrt as R25  # noqa: E402


class FakeCtx(Ctx):
    """A context with only the norms and an lrt.json (no network, no spec)."""
    def __init__(self, lines):
        self.N = norms.get()
        self.network = None
        self.lrt = {"lines": lines, "depots": []}


def line(pts, lid="t"):
    return {"id": lid, "pts": [list(map(float, p)) for p in pts], "sections": [], "stations": [],
            "ends": [{"kind": "joint", "id": "j0"}, {"kind": "joint", "id": "j1"}]}


def ramp(chain, grade, y0=600.0, rnd=True):
    """Straight line along −z with rail height y0 + grade·s, heights rounded to 1 cm as in lrt.json."""
    y = y0 + grade * np.asarray(chain, float)
    if rnd:
        y = np.round(y, 2)
    return [[-3097.0, -19700.0 - s, h] for s, h in zip(chain, y)]


def slope_issues(lines):
    return [i for i in R25.rule25(FakeCtx(lines)) if "уклон" in i["what_ru"]]


# ------------------------------------------------------------------ land rules on hand-made land (rules 12, 14, 24)
Y4 = [2030, 2029, 2033, 2030]


def _rect(x0, z0, x1, z1):
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


class LandCtx(Ctx):
    """A context over hand-made network / lots / buildings / driveways (flat ground far outside the twin)."""
    def __init__(self, network=None, lots=None, blocks=None, buildings=None, driveways=None, spec=None, area=None):
        import json
        import shapely
        from lib import paths
        self.N = norms.get()
        self.norms = json.load(open(os.path.join(paths.SPEC, "norms.json"), encoding="utf-8"))
        self.rules = json.load(open(os.path.join(paths.SPEC, "rules.json"), encoding="utf-8"))
        self._rules_by_no = {r["id"]: r for r in self.rules["rules"]}
        self.spec, self.city = spec or {"zones": []}, {}
        self.network, self.lots, self.blocks, self.buildings = network, lots, blocks, buildings
        self.driveways, self.features, self.lrt = driveways, None, None
        self.area = shapely.Polygon(area or _rect(29000.0, 29000.0, 33000.0, 31000.0))
        self.years = list(self.N.norm("validator.years"))
        self._water = self._flood = self._houses = None


def _seg(sid, a, b, cls, pts, years=Y4):
    return {"id": sid, "a": a, "b": b, "class": cls, "pid": None, "oneway": False, "struct": [], "years": list(years),
            "pts": [[float(x), float(z), 500.0] for x, z in pts]}


def _bld(bid, x0, z0, x1, z1, h, years=Y4, source="model", use="business", lot="L1", homes=0, jobs=0):
    return {"id": bid, "footprint": _rect(x0, z0, x1, z1), "height_m": float(h), "floors": max(1, int(h // 3.6)), "use": use,
            "kind": use, "source": source, "lot": lot, "years": list(years), "homes": homes, "jobs": jobs,
            "gfa_m2": (x1 - x0) * (z1 - z0) * max(1, int(h // 3.6))}


def rule12_cases():
    """Rule 12 from the footprints alone: the 5–8 m drive band of a 10–28 m building with no street within 25 m, no
    access at all, no access standing in the opening year, and the 22 m gap between two buildings over 28 m."""
    import land_util as U
    from rules import buildings as RB
    N = U.Norms()
    half = U.carriage_half(U.profile_from_norms(N, "driveway_main"))
    x0, z0 = 30000.0, 30000.0
    net = {"segments": [_seg("s1", "n1", "n2", "local", [(x0 - 100.0, z0), (x0 + 1600.0, z0)])], "profiles": {}}
    blds, dsegs, dnodes, pads = [], [], [], []
    k = 0

    def drive(x, z_edge, years=Y4):
        """A drive from the street up 20 m west of a 30 m wide building, then along its street-side wall with its edge at
        z_edge, on to a turnaround pad 10 m past the building's east end (the leg up and the pad are out of the band)."""
        nonlocal k
        k += 1
        zc = z_edge - half
        a, m, b = f"dn{k}a", f"dn{k}m", f"dn{k}b"
        dnodes.extend([{"id": a, "x": x - 20.0, "z": z0, "attach": {"segment": "s1"}}, {"id": m, "x": x - 20.0, "z": zc},
                       {"id": b, "x": x + 40.0, "z": zc}])
        dsegs.extend([_seg(f"ds{k}a", a, m, "driveway_main", [(x - 20.0, z0), (x - 20.0, zc)], years),
                      _seg(f"ds{k}b", m, b, "driveway_main", [(x - 20.0, zc), (x + 40.0, zc)], years)])
        pads.append({"node": b, "polygon": _rect(x + 40.0, zc - 7.5, x + 55.0, zc + 7.5), "years": list(years)})

    wall = z0 + 60.0                                  # the walls facing the street are 60 m off it
    cases = {"ok_6m": (13.0, 6.0), "near_2m": (13.0, 2.0), "far_12m": (13.0, 12.0), "low_12m": (7.0, 12.0)}
    for i, (name, (h, gap)) in enumerate(cases.items()):
        x = x0 + 150.0 * i
        blds.append(_bld(name, x, wall, x + 30.0, wall + 12.0, h))
        drive(x, wall - gap)
    x = x0 + 600.0
    blds.append(_bld("street_20m", x, z0 + 20.0 + 3.5, x + 30.0, z0 + 35.0, 13.0))       # a street within 25 m serves it
    blds.append(_bld("none", x0 + 750.0, wall, x0 + 780.0, wall + 12.0, 7.0))             # nothing within 25 m
    blds.append(_bld("year", x0 + 900.0, wall, x0 + 930.0, wall + 12.0, 7.0, years=[2030] * 4))
    drive(x0 + 900.0, wall - 6.0, years=[2040] * 4)                                       # its drive opens ten years later
    for j, (gap, tag) in enumerate(((20.0, "t20"), (23.0, "t23"))):                      # two pairs of 40 m towers
        x = x0 + 1050.0 + 250.0 * j
        blds.append(_bld(tag + "a", x, wall, x + 20.0, wall + 20.0, 40.0))
        blds.append(_bld(tag + "b", x + 20.0 + gap, wall, x + 40.0 + gap, wall + 20.0, 40.0))
    # a 40 m tower 6 m from the registry footprint of L7 (a 100 m Unity model, no buildings.json row), one 23 m from it
    x = x0 + 1400.0
    blds.append(_bld("lm6", x, wall, x + 20.0, wall + 20.0, 40.0))
    blds.append(_bld("lm23", x + 20.0 + 6.0 + 60.0 + 23.0, wall, x + 60.0 + 6.0 + 60.0 + 23.0, wall + 20.0, 40.0))
    spec = {"zones": [], "objects": [{"registry_id": "l7_lotte", "kind": "business",
                                      "footprint": _rect(x + 26.0, wall, x + 86.0, wall + 40.0)}]}
    lots = {"lots": [{"id": "L1", "use": "business", "block": "B1", "polygon": _rect(x0 - 50.0, z0 + 12.0, x0 + 1550.0, z0 + 300.0),
                      "capacity": {}, "years": Y4, "access": "s1", "source": "rule"}]}
    blocks = {"blocks": [{"id": "B1", "polygon": _rect(x0 - 50.0, z0 + 12.0, x0 + 1550.0, z0 + 300.0), "zone": None, "use": "business"}]}
    # two blocks 500 m from any street: a 2025 farmstead (existing houses only, as OSM has it) and one with a new house
    for bk, src in (("Bfarm", "existing_osm"), ("Bnew", "model")):
        xb = x0 + (100.0 if bk == "Bfarm" else 400.0)
        lid = "L" + bk
        lots["lots"].append({"id": lid, "use": "village_existing" if src == "existing_osm" else "housing", "block": bk,
                             "polygon": _rect(xb, z0 + 480.0, xb + 100.0, z0 + 580.0), "capacity": {}, "years": Y4,
                             "access": None, "source": "existing" if src == "existing_osm" else "rule"})
        blocks["blocks"].append({"id": bk, "polygon": _rect(xb, z0 + 480.0, xb + 100.0, z0 + 580.0), "zone": None, "use": "housing"})
        blds.append(_bld("h_" + bk, xb + 40.0, z0 + 520.0, xb + 52.0, z0 + 530.0, 6.0, source=src, use="housing", lot=lid, homes=1))
    dv = {"segments": dsegs, "nodes": dnodes, "pads": pads, "profiles": {}}
    ctx = LandCtx(net, lots, blocks, {"buildings": blds}, dv, spec)
    ALIVE.append(ctx)
    iss = RB.check_12(ctx)
    by = {}
    for i in iss:
        for bid in i["ids"]:
            by.setdefault(bid, []).append(i)
    return by, half


ALIVE = []      # land_rulekit caches its geometry by id(ctx): contexts of finished checks stay alive so no id is reused


class SlopeCtx(LandCtx):
    """Hand-made land on a plane falling 10 % along x."""
    def h(self, x, z):
        return 500.0 - 0.1 * (np.asarray(x, float) - 30000.0)


def rule3_plinth():
    """Rule 3: a new building whose ground falls more than validator.grading cut_fill_max_m under it needs a plinth
    (tester item 74); with one it passes."""
    from rules import land as RL
    x0, z0 = 30000.0, 30000.0
    lot = {"id": "L3", "use": "business", "block": "B1", "polygon": _rect(x0 - 10, z0 - 10, x0 + 200, z0 + 60), "grade_y": 495.0,
           "capacity": {}, "years": Y4, "source": "rule", "terraces": [{"polygon": _rect(x0 - 10, z0 - 10, x0 + 200, z0 + 60),
                                                                        "grade_y": 497.0, "cut_fill_m": 1.0}]}
    blds = [_bld("fall", x0, z0, x0 + 30.0, z0 + 20.0, 13.0, lot="L3"),          # 3 m fall over 30 m
            _bld("plinthed", x0 + 60.0, z0, x0 + 90.0, z0 + 20.0, 13.0, lot="L3"),
            _bld("flat", x0 + 120.0, z0, x0 + 130.0, z0 + 20.0, 7.0, lot="L3")]      # 1 m fall over 10 m
    for b in blds:
        b["base_y"] = 497.0
    blds[1]["plinth"] = {"from_y": 491.0, "h_m": 6.0, "slope_pct": 10.0}
    ctx = SlopeCtx(None, {"lots": [lot]}, {"blocks": []}, {"buildings": blds}, None)
    ALIVE.append(ctx)
    return {bid: [i for i in RL.check_3(ctx) if bid in i["ids"] and "падает" in i["what_ru"]] for bid in ("fall", "plinthed", "flat")}


def rule15_rail():
    """Rule 15: a house with homes nearer than szz.rail_m to a railway track: error when new, warning when existing; none
    at 150 m. The track is synthetic (lib.rail.tracks replaced for the check)."""
    from lib import rail
    from rules import buildings as RB
    x0, z0 = 30000.0, 30000.0
    track = [{"id": "track0", "piece": "0.0", "P": np.array([[x0 - 500.0, z0], [x0 + 500.0, z0]]), "up": False, "name": "путь"}]
    blds = [_bld("new60", x0, z0 + 60.0, x0 + 20.0, z0 + 72.0, 13.0, use="housing", homes=20),
            _bld("old60", x0 + 100.0, z0 + 60.0, x0 + 110.0, z0 + 70.0, 3.6, source="existing_osm", use="existing", homes=1,
                 years=[2025] * 4),
            _bld("new150", x0 + 200.0, z0 + 150.0, x0 + 220.0, z0 + 162.0, 13.0, use="housing", homes=20),
            _bld("office60", x0 + 300.0, z0 + 60.0, x0 + 320.0, z0 + 72.0, 13.0)]
    keep = rail._all
    rail._all = lambda: track
    try:
        ctx = LandCtx(None, {"lots": []}, {"blocks": []}, {"buildings": blds}, None)
        ALIVE.append(ctx)
        iss = RB.check_15(ctx)
    finally:
        rail._all = keep
    return {bid: [i["sev"] for i in iss if bid in i["ids"]] for bid in ("new60", "old60", "new150", "office60")}


def rule8_rings():
    """Rule 8 on rings: the classes come from the ring's arms, never from a None street ref (net_rings writes minor None,
    five_arm_rings major None too; a None ref used to match the first segment without a street, an OSM village lane).
    r1 (major A): arterial A twice, local L, industrial I → arterial × local is reported; r2 (no refs): district D and
    local L2 → nothing, and no issue names the unrelated village lane."""
    from rules import roads as RR
    nodes, segs, ics = [], [], []

    def ring(rid, cx, cz, arms, major):
        pts = {k: (cx + 30.0 * math.cos(math.radians(90 * k)), cz + 30.0 * math.sin(math.radians(90 * k))) for k in range(4)}
        for k, (x, z) in pts.items():
            nodes.append({"id": f"{rid}n{k}", "x": x, "z": z, "kind": "roundabout", "ic": rid})
        own = []
        for k in range(4):
            sid = f"{rid}arc{k}"
            sg = _seg(sid, f"{rid}n{k}", f"{rid}n{(k + 1) % 4}", "arterial_regulated", [pts[k], pts[(k + 1) % 4]])
            sg["ic"] = rid
            segs.append(sg)
            own.append(sid)
        for k, (street, cls) in enumerate(arms):
            x, z = pts[k]
            far = (cx + 300.0 * math.cos(math.radians(90 * k)), cz + 300.0 * math.sin(math.radians(90 * k)))
            nodes.append({"id": f"{rid}e{k}", "x": far[0], "z": far[1], "kind": "end"})
            sg = _seg(f"{rid}arm{k}", f"{rid}n{k}", f"{rid}e{k}", cls, [(x, z), far])
            sg["street"] = street
            segs.append(sg)
        ics.append({"id": rid, "template": "roundabout", "x": cx, "z": cz, "major": major, "minor": None, "ramps": own})
    nodes += [{"id": "v0", "x": 29000.0, "z": 29000.0, "kind": "end"}, {"id": "v1", "x": 29050.0, "z": 29000.0, "kind": "end"}]
    segs.append(_seg("osm_lane", "v0", "v1", "village_lane", [(29000.0, 29000.0), (29050.0, 29000.0)]))     # street None
    ring("r1", 30000.0, 30000.0, [("A", "arterial_regulated"), ("L", "local"), ("A", "arterial_regulated"), ("I", "industrial")], "A")
    ring("r2", 31000.0, 30000.0, [("D", "district_transport"), ("L2", "local"), ("D", "district_transport"), ("L2", "local")], None)
    ctx = LandCtx({"nodes": nodes, "segments": segs, "interchanges": ics, "profiles": {}}, None, None, None, None, {"zones": [], "axes": []})
    ALIVE.append(ctx)
    return [i for i in RR.rule8(ctx) if i["ids"] and i["ids"][0] in ("r1", "r2")]


def rule7_keep_chain(variant):
    """Rule 7 on a kept existing interchange (params.keep_existing) of two OSM ramp pieces A → B, each a keep_existing
    spec street (w53 Growing-E ic_a3_km44). variant "pieces": a segment per piece, each with its street and OSM id;
    "joined": one segment over both pieces, street of A, source "osm:A+B" (a chained way with no node between them);
    "old": a segment per piece, both with the street of A and no source (the network before the fix: B is missing).
    Returns the rule 7 issues of the interchange."""
    import shapely
    from rules import roads as RR
    A, B = "71dada4c-unit", "c5dc1f4a-unit"
    x0, z0 = 30000.0, 30000.0
    la = [(x0 - 100.0, z0 - 180.0), (x0 - 60.0, z0 - 60.0), (x0, z0)]
    lb = [(x0, z0), (x0 - 35.0, z0 + 25.0), (x0 - 30.0, z0 + 200.0)]
    nodes = [{"id": f"n{k}", "x": p[0], "z": p[1], "kind": "end"} for k, p in enumerate((la[0], la[-1], lb[-1]))]
    if variant == "joined":
        segs = [_seg("s1", "n0", "n2", "ramp", la + lb[1:], years=[2025] * 4)]
        segs[0].update(street="k_" + A[:8], source=f"osm:{A}+{B}", ic="ick")
    else:
        segs = [_seg("s1", "n0", "n1", "ramp", la, years=[2025] * 4), _seg("s2", "n1", "n2", "ramp", lb, years=[2025] * 4)]
        for sg, oid in zip(segs, (A, B)):
            sg.update(street="k_" + (oid if variant == "pieces" else A)[:8], ic="ick")
            if variant == "pieces":
                sg["source"] = f"osm:{oid}"
    ics = [{"id": "ick", "template": "diamond", "x": x0, "z": z0, "major": None, "minor": None, "ramps": ["s1", "s2"],
            "params": {"keep_existing": True, "osm_ids": [A, B]}, "existing": True}]
    spec = {"zones": [], "axes": [], "streets": [{"id": "k_" + oid[:8], "class": "ramp", "source": f"keep_existing:{oid}"}
                                                 for oid in (A, B)]}
    ctx = LandCtx({"nodes": nodes, "segments": segs, "interchanges": ics, "profiles": {}}, None, None, None, None, spec)
    ctx._osm_roads = {A: shapely.LineString(la), B: shapely.LineString(lb)}
    ALIVE.append(ctx)
    net = RR._net(ctx)
    return RR._keep_existing(ctx, net, {"ick": net.ics["ick"]})


def rule6_five_arms(new_arm):
    """Rule 6, a node of 5 arms without a ring (w53 Growing-E n447 at ic_a3_km55: four kept OSM ramps and the end of
    an OSM service road): all arms existing 2025 → a warning «как в OSM»; one arm new (new_arm) → an error."""
    from rules import roads as RR
    x0, z0 = 30000.0, 30000.0
    nodes = [{"id": "c", "x": x0, "z": z0, "kind": "crossing"}]
    segs = []
    for k in range(5):
        a = math.radians(72.0 * k)
        far = (x0 + 200.0 * math.cos(a), z0 + 200.0 * math.sin(a))
        nodes.append({"id": f"e{k}", "x": far[0], "z": far[1], "kind": "end"})
        yrs = [2030, 2029, 2033, 2030] if (new_arm and k == 4) else [2025] * 4
        segs.append(_seg(f"a{k}", "c", f"e{k}", "local" if k == 4 else "ramp", [(x0, z0), far], years=yrs))
    ctx = LandCtx({"nodes": nodes, "segments": segs, "interchanges": [], "profiles": {}}, None, None, None, None,
                  {"zones": [], "axes": []})
    ALIVE.append(ctx)
    return [i for i in RR.rule6(ctx) if "лучей" in i["what_ru"]]


def rule5_lot_use(lot_use, registry_id=None):
    """Rule 5 road to nowhere (w47 gate_trial s37 to the utility lot of hv_gate): a 120 m dead-end branch off a through
    street, no building within reach of it, one lot entered from it with `lot_use` (None: no lot). Returns the «дорога
    никуда» warnings."""
    from rules import roads as RR
    x0, z0 = 30000.0, 30000.0
    nodes = [{"id": "w", "x": x0 - 500.0, "z": z0, "kind": "joint"}, {"id": "j", "x": x0, "z": z0, "kind": "crossing"},
             {"id": "e", "x": x0 + 500.0, "z": z0, "kind": "joint"}, {"id": "d", "x": x0, "z": z0 + 120.0, "kind": "end"}]
    segs = [_seg("s1", "w", "j", "local", [(x0 - 500.0, z0), (x0, z0)]), _seg("s2", "j", "e", "local", [(x0, z0), (x0 + 500.0, z0)]),
            _seg("s37", "j", "d", "local", [(x0, z0), (x0, z0 + 120.0)])]
    lots = {"lots": []}
    if lot_use is not None:
        lots["lots"].append({"id": "L1", "use": lot_use, "registry_id": registry_id, "block": "B1", "years": Y4, "access": "s37",
                             "source": "registry" if registry_id else "rule", "capacity": {},
                             "polygon": _rect(x0 + 10.0, z0 + 30.0, x0 + 110.0, z0 + 110.0)})
    blds = {"buildings": [_bld("far", x0 - 400.0, z0 + 300.0, x0 - 380.0, z0 + 320.0, 9.0, lot="Lfar")]}
    ctx = LandCtx({"nodes": nodes, "segments": segs, "interchanges": [], "profiles": {}}, lots, None, blds, None,
                  {"zones": [], "axes": []})
    ALIVE.append(ctx)
    return [i for i in RR._dead_ends_to_nowhere(ctx, RR._net(ctx)) if "никуда" in i["what_ru"]]


def rule12_keep_model():
    """Rule 12, the 22 m gap of two buildings over 28 m, one of them a block of the kept Gate District model (w47 full
    Gate b00264, 35.4 m, 6.5 m from a 30.6 m model block): a new 35 m building 6.5 m from a model block over 28 m is an
    error, one 23 m from every such block passes, two model blocks are never paired. {} when the model is not there."""
    import json
    import shapely
    from lib import paths
    from rules import buildings as RB
    blocks = [(g, h) for g, h in RB._gate_model_blocks() if h > 28.0]
    if not blocks:
        return {}
    keep = next(k for k in json.load(open(os.path.join(paths.SPEC, "gate_trial.json"), encoding="utf-8"))["keep"]
                if "gate_district.bytes" in k.get("source", ""))
    g0 = max(blocks, key=lambda b: b[0].area)[0]
    others = shapely.union_all([g for g, _ in blocks])
    picks = {}
    for tag, gap in (("near", 6.5), ("far", 23.0)):
        x0, z0, x1, z1 = g0.bounds
        for cx, cz in ((x1 + gap + 10.0, (z0 + z1) / 2), (x0 - gap - 10.0, (z0 + z1) / 2),
                       ((x0 + x1) / 2, z1 + gap + 10.0), ((x0 + x1) / 2, z0 - gap - 10.0)):
            b = shapely.box(cx - 10.0, cz - 10.0, cx + 10.0, cz + 10.0)
            d = b.distance(others)
            if (tag == "near" and 6.0 <= d <= 7.0) or (tag == "far" and 22.5 <= d <= 23.5):
                picks[tag] = (cx, cz)
                break
    iss = []
    for t, (cx, cz) in picks.items():           # one context per new building: the two are not paired with each other
        blds = [_bld(f"new_{t}", cx - 10.0, cz - 10.0, cx + 10.0, cz + 10.0, 35.0)]
        ctx = LandCtx(None, {"lots": []}, None, {"buildings": blds}, None, {"zones": [], "objects": [], "keep": [keep]})
        ALIVE.append(ctx)
        iss += RB._tall_gaps(ctx, 28.0, 22.0, "test")
    return {"picks": sorted(picks), "issues": iss}


def rule1_lrt(variant):
    """Rule 1, the ground LRT and a road on one land (w50 golden s774): "node" — a local road with a node at the
    crossing passes; "none" — the same road with no node within 30 m is an error; "forbidden" — an expressway: no rule 1
    issue, rule 6 reports the crossing. Returns (rule 1 issues of the LRT, rule 6 LRT issues)."""
    from rules import land as RL
    from rules import roads as RR
    x0, z0 = 30000.0, 30000.0
    cls = "expressway" if variant == "forbidden" else "local"
    if variant == "node":
        nodes = [{"id": "a", "x": x0 - 400.0, "z": z0, "kind": "joint"}, {"id": "x", "x": x0, "z": z0, "kind": "crossing_signal", "lrt": "L"},
                 {"id": "b", "x": x0 + 400.0, "z": z0, "kind": "joint"}]
        segs = [_seg("s1", "a", "x", cls, [(x0 - 400.0, z0), (x0, z0)]), _seg("s2", "x", "b", cls, [(x0, z0), (x0 + 400.0, z0)])]
    else:
        nodes = [{"id": "a", "x": x0 - 400.0, "z": z0, "kind": "joint"}, {"id": "b", "x": x0 + 400.0, "z": z0, "kind": "joint"}]
        segs = [_seg("s1", "a", "b", cls, [(x0 - 400.0, z0), (x0 + 400.0, z0)])]
        segs[0]["oneway"] = cls == "expressway"
    pts = [[x0, z0 - 300.0 + 10.0 * k, 500.0] for k in range(61)]
    lrt = {"lines": [{"id": "L", "pts": pts, "sections": [{"from_m": 0.0, "to_m": 600.0, "kind": "ground"}], "years": Y4}],
           "depots": []}
    ctx = LandCtx({"nodes": nodes, "segments": segs, "interchanges": [], "profiles": {}}, {"lots": []}, None, {"buildings": []},
                  None, {"zones": [], "axes": []})
    ctx.features, ctx.lrt = {}, lrt
    ALIVE.append(ctx)
    r1 = [i for i in RL.check_1(ctx) if "lrt" in i["what_ru"]]
    r6 = [i for i in RR.rule6(ctx) if "ЛРТ" in i["what_ru"]]
    return r1, r6


def rule11_ramp_lanes(variant):
    """Rule 11 and spec interchange `ramps` (tester item 71: the loop of interchange_a3_bakad, 2 lanes from 2035):
    "stage" — the ramp carries a 2-lane `stages` profile from 2035: passes; "none" — no stage: an error; "lost" — the key
    found no ramp (interchanges[].ramp_lanes without it): an error. Returns the rule 11 ramp issues."""
    from rules import roads as RR
    x0, z0 = 30000.0, 30000.0
    nodes = [{"id": "a", "x": x0, "z": z0, "kind": "diverge"}, {"id": "b", "x": x0 + 300.0, "z": z0 + 100.0, "kind": "merge"}]
    sg = _seg("s1", "a", "b", "ramp", [(x0, z0), (x0 + 300.0, z0 + 100.0)], years=[2025] * 4)
    sg.update(pid="ramp", oneway=True, ic="ic1")
    if variant == "stage":
        sg["stages"] = [{"years": [2035] * 4, "pid": "ramp_l2", "lanes": 2, "why_ru": "тест"}]
    prof = {"ramp": {"class": "ramp", "lanes": [1, 0], "lane_w": 5.0}, "ramp_l2": {"class": "ramp", "lanes": [2, 0], "lane_w": 3.65}}
    ic = {"id": "ic1", "template": "cloverleaf", "x": x0, "z": z0, "major": None, "minor": None, "ramps": ["s1"], "structures": []}
    if variant != "lost":
        ic["ramp_lanes"] = [{"key": "А-3 S → БАКАД E", "lanes": 2, "from_year": [2035] * 4, "segments": ["s1"]}]
    spec = {"zones": [], "axes": [], "nodes": [{"id": "ic1", "type": "cloverleaf",
                                                "ramps": {"А-3 S → БАКАД E": {"lanes": 2, "from_year": 2035}}}]}
    ctx = LandCtx({"nodes": nodes, "segments": [sg], "interchanges": [ic], "profiles": prof}, None, None, None, None, spec)
    ALIVE.append(ctx)
    return RR._ramp_lanes(ctx, RR._net(ctx))


def rule25_under_decks(variant):
    """Rule 25 under decks (w45 gate_trial: drive e17025 3.7 m under the agglomeration rail viaduct by its buffer stop): a
    street along x and a drive with a turnaround pad along z at y 500, a spec `rail` track (struct overpass) across both
    at rail head y. "low": 3.7 m clear (rail head 505.5) — the drive, its pad and the street are errors; "mid": 4.7 m —
    the drive and its pad pass fire_access.arches.height_min_m 4.5, the street not bridges.road_clearance_m 5.0; "high":
    5.5 m — nothing; "span": no rail, a street overpass (struct overpass, y 505.6, deck 1.5 m) over the drive and the
    pad's edge, 4.1 m clear — both are errors. Returns the rule25_drives issues."""
    x0, z0 = 30000.0, 30000.0
    head = {"low": 505.5, "mid": 506.5, "high": 507.3}.get(variant)
    nodes = [{"id": "a", "x": x0 - 200.0, "z": z0, "kind": "joint"}, {"id": "b", "x": x0 + 200.0, "z": z0, "kind": "joint"}]
    segs = [_seg("s1", "a", "b", "local", [(x0 - 200.0, z0), (x0 + 200.0, z0)])]
    if variant == "span":
        segs.append(_seg("s2", "c", "d", "local", [(x0 - 60.0, z0 + 40.0), (x0 + 60.0, z0 + 40.0)]))
        segs[-1]["pts"] = [[x0 - 60.0, z0 + 40.0, 505.6], [x0 + 60.0, z0 + 40.0, 505.6]]
        segs[-1]["struct"] = [{"from_m": 0.0, "to_m": 120.0, "kind": "overpass"}]
        nodes += [{"id": "c", "x": x0 - 60.0, "z": z0 + 40.0, "kind": "end"}, {"id": "d", "x": x0 + 60.0, "z": z0 + 40.0, "kind": "end"}]
    dv = {"nodes": [{"id": "dn0", "x": x0, "z": z0, "y": 500.0, "attach": {"segment": "s1", "x": x0, "z": z0}},
                    {"id": "dn1", "x": x0, "z": z0 + 50.0, "y": 500.0}],
          "segments": [{"id": "ds0", "a": "dn0", "b": "dn1", "class": "driveway_main", "pid": "driveway_main", "oneway": False,
                        "pts": [[x0, z0, 500.0], [x0, z0 + 50.0, 500.0]], "struct": [], "years": list(Y4)}],
          "pads": [{"node": "dn1", "polygon": _rect(x0 - 7.5, z0 + 42.5, x0 + 7.5, z0 + 57.5), "years": list(Y4)}]}
    spec = {"zones": [], "axes": []}
    if head is not None:
        trk = [[x0 + 30.0, z0 - 30.0, head], [x0 - 30.0, z0 + 90.0, head]]    # a diagonal over the street, the drive and its pad
        trk = [trk[0], [x0 - 2.0, z0 + 26.0, head], [x0 - 15.0, z0 + 52.0, head], trk[1]]
        spec["rail"] = {"lines": [{"id": "rl", "years": list(Y4), "tracks": [{"id": "rt", "pts": trk,
                                                                             "struct": [{"from_m": 0.0, "to_m": 200.0, "kind": "overpass"}]}]}]}
    ctx = LandCtx({"nodes": nodes, "segments": segs, "interchanges": [], "profiles": {}}, {"lots": []}, None, {"buildings": []},
                  dv, spec)
    ALIVE.append(ctx)
    return R25.rule25_drives(ctx)


def rule24_case(totals_homes_new=None):
    """Rule 24: existing (OSM) houses and keep quarters are left out of the target comparison; totals are one number."""
    from rules import years as RY
    x0, z0 = 30000.0, 30000.0
    home_m2 = 75.0
    blds = [_bld("n1", x0, z0, x0 + 30.0, z0 + 25.0, 30.0, use="housing", homes=0),
            _bld("e1", x0 + 100.0, z0, x0 + 110.0, z0 + 10.0, 3.6, source="existing_osm", use="existing", homes=0)]
    blds[0]["homes"] = round(blds[0]["gfa_m2"] / home_m2)
    blds[1]["homes"] = 40                                               # many existing homes: the target must not see them
    lots = {"lots": [{"id": "L1", "use": "residential_mid", "block": "B1", "polygon": _rect(x0 - 10, z0 - 10, x0 + 200, z0 + 100),
                      "capacity": {"homes": blds[0]["homes"] + blds[1]["homes"], "jobs": 0}, "years": Y4, "source": "rule"}]}
    new_h = blds[0]["homes"]
    tot = {"homes": new_h + 40, "jobs": 0, "homes_existing": 40, "jobs_existing": 0, "homes_new": new_h if totals_homes_new is None else totals_homes_new}
    spec = {"zones": [], "targets": {"homes_2050": new_h, "home_m2": home_m2}}
    ctx = LandCtx(None, lots, {"blocks": []}, {"buildings": blds, "totals": tot}, None, spec)
    ALIVE.append(ctx)
    return RY.check_24(ctx), new_h


def rule14_minimums():
    """Rule 14: kindergarten / school lots below the smallest facility (city: model qTwin, warning; village: the guaranteed
    network's contingent, error) and buildings smaller than places × m² per place."""
    from rules import buildings as RB
    x0, z0 = 30000.0, 30000.0
    zones = [{"id": "zc", "use": "residential_mid", "polygon": _rect(x0 - 500, z0 - 500, x0 + 500, z0 + 500)},
             {"id": "zv", "use": "village_existing", "polygon": _rect(x0 + 600, z0 - 500, x0 + 1500, z0 + 500)}]
    blocks = {"blocks": [{"id": "Bc", "zone": "zc", "use": "residential_mid", "polygon": _rect(x0 - 400, z0 - 400, x0 + 400, z0 + 400)},
                         {"id": "Bv", "zone": "zv", "use": "village_existing", "polygon": _rect(x0 + 700, z0 - 400, x0 + 1400, z0 + 400)}]}

    def lot(lid, use, blk, x, places):
        return {"id": lid, "use": use, "block": blk, "polygon": _rect(x, z0, x + 60.0, z0 + 60.0), "capacity": {"places": places},
                "years": Y4, "source": "rule"}
    lots = {"lots": [lot("Lk20", "kindergarten", "Bc", x0 - 300, 20), lot("Lk50", "kindergarten", "Bc", x0 - 200, 50),
                     lot("Ls30", "school", "Bc", x0, 30), lot("Lv4", "kindergarten", "Bv", x0 + 800, 4),
                     lot("Lv20", "kindergarten", "Bv", x0 + 900, 20)]}
    blds = [_bld("bk50", x0 - 190, z0 + 10, x0 - 170, z0 + 30, 7.2, use="social", lot="Lk50")]       # 800 m²: 53 places at 15 m²
    blds[0]["gfa_m2"] = 600.0                                                                      # 40 places at 15 m²
    ctx = LandCtx(None, lots, blocks, {"buildings": blds}, None, {"zones": zones})
    ALIVE.append(ctx)
    small = {l["id"]: (v, vmin, key, "warning" if __import__("land_rulekit").weak(ctx, key) else "error")
             for l, _, v, vmin, key in RB.small_places(ctx)}
    short = {l["id"]: (cap, holds) for l, _, cap, g, holds, m2, key in RB.short_floor_area(ctx)}
    return small, short


def main():
    smax = float(norms.get().norm("lrt.ramp_slope_max_pct")) / 100.0
    design = 0.95 * smax                     # gen_lrt designs ramps at 0.95 of the norm
    fails = []

    def check(name, ok, detail=""):
        print(f"{'ok ' if ok else 'ERR'} {name}{(': ' + detail) if detail else ''}")
        if not ok:
            fails.append(name)

    # 1. the w47 pair: −19729.01 y 638.60 → −19730.80 y 638.71 (6.1 % on 1.8 m) inside a 0.95-norm ramp
    ch = list(np.arange(0.0, 29.0, 5.0)) + [29.01, 30.80] + list(np.arange(35.0, 120.0, 5.0))
    pts = ramp(ch, design, y0=638.60 - design * 29.01)
    pts[6][2], pts[7][2] = 638.60, 638.71
    pair = (pts[7][2] - pts[6][2]) / 1.79
    iss = slope_issues([line(pts)])
    check("rule 25: w47 rounding pair (%.1f %% on 1.8 m) is not an error" % (100 * pair), not iss,
          "; ".join(i["what_ru"] for i in iss))

    # 2. random vertex spacing 0.3–6 m, design grade, 1 cm rounding: never an error
    rng = np.random.default_rng(7)
    worst_pair, n_err = 0.0, 0
    for k in range(300):
        ch = np.concatenate([[0.0], np.cumsum(rng.uniform(0.3, 6.0, 80))])
        pts = ramp(ch, design * rng.choice([1, -1]), y0=rng.uniform(470, 700))
        P = np.array(pts)
        worst_pair = max(worst_pair, float(np.max(np.abs(np.diff(P[:, 2])) / np.diff(ch))))
        n_err += bool(slope_issues([line(pts)]))
    check("rule 25: 300 rounded 0.95-norm ramps give no error", n_err == 0,
          f"worst vertex-pair grade from rounding {100 * worst_pair:.1f} %, lines with an error {n_err}")

    # 3. real over-slopes are still errors
    for name, grade, L, step in (("7 % over 100 m", 0.07, 100.0, 5.0),
                                 ("norm + 0.3 % over 60 m", smax + 0.003, 60.0, 5.0),
                                 ("norm + 0.3 % over 60 m, 1.8 m vertices", smax + 0.003, 60.0, 1.8)):
        ch = list(np.arange(0.0, 40.0, 5.0)) + list(40.0 + np.arange(0.0, L + 1e-6, step)) + \
             list(40.0 + L + np.arange(5.0, 40.0, 5.0))
        y = [600.0 + grade * min(max(s - 40.0, 0.0), L) for s in ch]
        pts = [[-3097.0, -19700.0 - s, round(h, 2)] for s, h in zip(ch, y)]
        iss = slope_issues([line(pts)])
        check(f"rule 25: real over-slope {name} is an error", bool(iss) and all(i["sev"] == "error" for i in iss),
              "; ".join(i["what_ru"] for i in iss))
    # a short step: 0.5 m up over 2 m between flat runs
    ch = list(np.arange(0.0, 50.1, 5.0)) + [52.0] + list(np.arange(57.0, 100.0, 5.0))
    pts = [[-3097.0, -19700.0 - s, 600.0 + (0.5 if s > 50.0 else 0.0)] for s in ch]
    iss = slope_issues([line(pts)])
    check("rule 25: a 0.5 m step over 2 m is an error", bool(iss), "; ".join(i["what_ru"] for i in iss))
    # 4. rule 12 from the footprints (tester items 71, 72; the drive band of fire_access.distance_to_wall_m)
    by, half = rule12_cases()

    def has(bid, text):
        return [i for i in by.get(bid, []) if text in i["what_ru"]]
    check("rule 12: a 13 m building with its drive edge 6 m from the wall passes", not by.get("ok_6m"),
          "; ".join(i["what_ru"] for i in by.get("ok_6m", [])))
    check("rule 12: a drive edge 2 m from a 13 m building's wall (and none in 5–8 m) is an error",
          bool(has("near_2m", "ближе нормы")) and has("near_2m", "ближе нормы")[0]["sev"] == "error")
    check("rule 12: a drive edge 12 m from a 13 m building's wall (no street in 25 m) is an error", bool(has("far_12m", "дальше нормы")))
    check("rule 12: a 7 m building takes no band (25 m reach only)", not by.get("low_12m"))
    check("rule 12: a street within 25 m serves a 13 m building with no drive", not by.get("street_20m"))
    check("rule 12: a building with neither a street nor a drive within 25 m is an error", bool(has("none", "ни улицы, ни проезда")))
    check("rule 12: a building opening before its only drive is an error", bool(has("year", "в год открытия")))
    check("rule 12: two buildings over 28 m 20 m apart are an error (22 m gap)", bool(has("t20a", "друг от друга")))
    check("rule 12: two buildings over 28 m 23 m apart pass the gap", not has("t23a", "друг от друга"))
    check("rule 12: a 40 m tower 6 m from the L7 landmark footprint (100 m model, no buildings.json row) is an error (tester item 108)",
          bool(has("lm6", "друг от друга")), "; ".join(i["what_ru"] for i in by.get("lm6", [])))
    check("rule 12: a 40 m tower 23 m from the L7 landmark footprint passes", not has("lm23", "друг от друга"))
    fb, nb = has("Bfarm", "без въезда"), has("Bnew", "без въезда")
    check("rule 12: a block of 2025 houses only with no street entry is a warning (as in OSM)",
          bool(fb) and fb[0]["sev"] == "warning", "; ".join(f"{i['sev']} {i['what_ru']}" for i in fb))
    check("rule 12: a block with a new house and no street entry is an error", bool(nb) and nb[0]["sev"] == "error",
          "; ".join(f"{i['sev']} {i['what_ru']}" for i in nb))
    # rule 8: ring classes from its arms (w52, growing_w n_ring_tunnel, ring_n1403, ring_n76)
    r8 = rule8_rings()
    check("rule 8: a ring of arterial, local and industrial arms (minor None) reports arterial_regulated × local",
          any(i["ids"][0] == "r1" and "arterial_regulated × local" in i["what_ru"] for i in r8), "; ".join(i["what_ru"] for i in r8))
    check("rule 8: no ring issue names the unrelated village lane (a None ref matches nothing)",
          not any("village_lane" in i["what_ru"] for i in r8), "; ".join(i["what_ru"] for i in r8))
    check("rule 8: a ring of district and local arms with no refs passes", not any(i["ids"][0] == "r2" for i in r8),
          "; ".join(i["what_ru"] for i in r8))
    # rule 6: 5 arms without a ring: existing only → warning, one new arm → error (w53 Growing-E n447)
    r6o, r6n = rule6_five_arms(False), rule6_five_arms(True)
    check("rule 6: a 5-arm node of existing 2025 roads only is a warning (as in OSM)",
          len(r6o) == 1 and r6o[0]["sev"] == "warning", "; ".join(f"{i['sev']}: {i['what_ru']}" for i in r6o))
    check("rule 6: a 5-arm node with one new arm is an error", len(r6n) == 1 and r6n[0]["sev"] == "error",
          "; ".join(f"{i['sev']}: {i['what_ru']}" for i in r6n))
    # rule 7: a kept existing interchange of two chained OSM pieces (w53 Growing-E ic_a3_km44, ic_a3_km46)
    for variant, want in (("pieces", 0), ("joined", 0), ("old", 2)):
        r7 = rule7_keep_chain(variant)
        errs = [i for i in r7 if i["sev"] == "error"]
        info = " ".join(i["what_ru"] for i in r7 if i["sev"] == "info")
        check(f"rule 7: keep_existing interchange, {variant}: {want} errors" + (" (both ramps on their OSM lines)" if not want else ""),
              len(errs) == want and (want or "2 из 2 дорог OSM" in info), "; ".join(i["what_ru"] for i in r7))
    # rule 5: a dead end serving a lot with a use but no building yet is not a road to nowhere (w47 gate_trial s37)
    for lot_use, rid, want in (("substation", "hv_test", 0), ("school", None, 0), ("reserve", None, 1), (None, None, 1)):
        r5 = rule5_lot_use(lot_use, rid)
        check(f"rule 5: a dead end to {'no lot' if lot_use is None else 'a ' + lot_use + ' lot'} without buildings is "
              + ("a road to nowhere (warning)" if want else "served"), len(r5) == want, "; ".join(i["what_ru"] for i in r5))
    # rule 12: the 22 m gap between a new building over 28 m and a block of the kept Gate District model
    km = rule12_keep_model()
    if km:
        near = [i for i in km["issues"] if "new_near" in i["ids"]]
        check("rule 12: a new 35 m building 6.5 m from a kept model block over 28 m is an error (w47 Gate b00264)",
              "near" in km["picks"] and len(near) >= 1 and all(i["sev"] == "error" for i in near) and
              any(str(x).startswith("k_gate_district:m") for i in near for x in i["ids"]), "; ".join(i["what_ru"] for i in km["issues"]))
        check("rule 12: a new 35 m building 23 m from every model block over 28 m passes",
              "far" in km["picks"] and not [i for i in km["issues"] if "new_far" in i["ids"]])
        check("rule 12: two blocks of the kept model are never paired (the model is as it is)",
              not [i for i in km["issues"] if not any(str(x).startswith("new_") for x in i["ids"])])
    else:
        print("--  rule 12: gate_district.bytes not found, the kept model check is skipped")
    # rule 1 / rule 6: the ground LRT across a road (w50 golden s774)
    for variant, want1, want6 in (("node", 0, 0), ("none", 1, 0), ("forbidden", 0, 1)):
        r1, r6 = rule1_lrt(variant)
        check(f"rule 1/6: ground LRT across {'an expressway' if variant == 'forbidden' else 'a local road'}"
              f"{' at a node' if variant == 'node' else (' with no node' if variant == 'none' else '')}: rule 1 {want1}, rule 6 {want6}",
              len(r1) == want1 and len(r6) == want6 and all(i["sev"] == "error" for i in r1 + r6),
              "; ".join(f"п.{i['rule']} {i['sev']}: {i['what_ru']}" for i in r1 + r6))
    # rule 11: spec interchange ramps (per-ramp lanes from a year, tester item 71)
    for variant, want in (("stage", 0), ("none", 1), ("lost", 1)):
        r11 = rule11_ramp_lanes(variant)
        check(f"rule 11: spec ramps 2 lanes from 2035, {variant}: {want} errors", len(r11) == want and all(i["sev"] == "error" for i in r11),
              "; ".join(i["what_ru"] for i in r11))
    # rule 25 under decks: drives and pads keep fire_access.arches.height_min_m, streets under a rail viaduct 5.0 m
    r25 = {v: rule25_under_decks(v) for v in ("low", "mid", "high", "span")}
    kinds = {v: sorted({"pad" if "площадка" in i["what_ru"] else ("drive" if "проезд" in i["what_ru"] else "street") for i in r25[v]
                        if i["sev"] == "error"}) for v in r25}
    check("rule 25: 3.7 m under a rail viaduct — the drive, its pad and the street are errors", kinds["low"] == ["drive", "pad", "street"],
          "; ".join(i["what_ru"] for i in r25["low"]))
    check("rule 25: 4.7 m — the drive and its pad pass (fire_access.arches 4.5 m), the street does not (5.0 m)", kinds["mid"] == ["street"],
          "; ".join(i["what_ru"] for i in r25["mid"]))
    check("rule 25: 5.5 m under the rail viaduct — nothing", not r25["high"], "; ".join(i["what_ru"] for i in r25["high"]))
    check("rule 25: a drive and its pad 4.1 m under a street overpass are errors", kinds["span"] == ["drive", "pad"] and len(r25["span"]) == 2,
          "; ".join(i["what_ru"] for i in r25["span"]))
    from lib import rail as LR
    rj = LR.decks({"v": 1, "lines": [{"id": "rl", "y": Y4, "tracks": [{"id": "rt", "p": [0.0, 0.0, 510.0, 100.0, 0.0, 511.0]}]}]})
    check("rule 25: a merge's rail.json track is a viaduct along its whole length (lib.rail.decks)",
          len(rj) == 1 and rj[0]["P"].shape == (2, 3) and rj[0]["years"] == Y4, str(rj))
    # rule 3: ground falling more than 1.5 m under a building without a plinth (tester item 74)
    r3 = rule3_plinth()
    check("rule 3: a 30 m building on a 3 m fall without a plinth is an error", bool(r3["fall"]) and r3["fall"][0]["sev"] == "error",
          "; ".join(i["what_ru"] for i in r3["fall"]))
    check("rule 3: the same building with a plinth passes", not r3["plinthed"])
    check("rule 3: a 1 m fall needs no plinth", not r3["flat"])
    # rule 15: housing and the railway's sanitary gap (szz.rail_m)
    r15 = rule15_rail()
    check("rule 15: a new house 60 m from a track is an error, an existing one a warning, none at 150 m or for an office",
          r15 == {"new60": ["error"], "old60": ["warning"], "new150": [], "office60": []}, str(r15))
    # 5. rule 24: the new city against the targets, totals as one number (w44 round 4)
    iss, new_h = rule24_case()
    check("rule 24: existing OSM homes are left out of the target comparison", not iss, "; ".join(i["what_ru"] for i in iss))
    iss, _ = rule24_case(totals_homes_new=new_h + 40)
    check("rule 24: buildings.json totals.homes_new that counts existing homes is an error",
          any("totals.homes_new" in i["what_ru"] for i in iss), "; ".join(i["what_ru"] for i in iss))
    # 6. rule 14: smallest kindergarten and school, floor area per place (tester item 74)
    small, short = rule14_minimums()
    check("rule 14: a 20-place city kindergarten is below the model minimum (warning)", small.get("Lk20", (0, 0, 0, ""))[3] == "warning", str(small))
    check("rule 14: a 30-place city school passes the minimum", "Ls30" not in small, str(small))
    check("rule 14: a 4-child village kindergarten is below the guaranteed network's 5 (error)", small.get("Lv4", (0, 0, 0, ""))[3] == "error", str(small))
    check("rule 14: a 20-place village kindergarten passes", "Lv20" not in small, str(small))
    check("rule 14: 50 places in 600 m² hold 40 at 15 m² per place", "Lk50" in short and round(short["Lk50"][1]) == 40, str(short))
    print("all rule checks passed" if not fails else f"FAILED: {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
