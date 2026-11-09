#!/usr/bin/env python3
"""Growing-East · level 2 · builder of tools/map/spec/growing_e.json v1 (w53): the whole district.

    python3 -I tools/map/district/growing_e_build.py [--no-check] [--out SPEC.json]

Builds on the approved level-0 scheme (district/growing_e_v0.json). Network: growing_e_net.py (existing roads, the frame of
the scheme axes, interchanges, local streets of every new quarter); zones: growing_e_zones.py. Here: LRT v1 (the trunk in
the medians of the OIZ street and бульвар Growing, the west branch to J062), the landmark plots of the twin models, the
registry objects (by source / by rule), sanitary gaps, targets and densities, overhead lines with their voltage, phases,
axes, joints, replaced roads, and the self-check (growing_e_check.py). Every coordinate not from a source is the
cartographer's design (label «модель qTwin»). Unity frame: X east, Z north.
"""
import copy
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
T0 = time.time()
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import substring, unary_union  # noqa: E402

import growing_e_common as C  # noqa: E402
import growing_e_net as N  # noqa: E402
import growing_e_zones as Z  # noqa: E402
import land_util as LU  # noqa: E402

SPEC_OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(C.SPEC_DIR, "growing_e.json")
MODEL = C.MODEL
Y4 = C.Y4
fillet = C.fillet
P1 = C.P1
poly_pts = C.poly_pts
CITY, REG, V0, DIST = C.CITY, C.REG, C.V0, C.DIST
LOG = [{"what": "сеть: существующие дороги и каркас", "s": round(time.time() - T0, 1)}]
MOVED = []                         # (id, было, стало, почему)
SCHEME_CHANGES = list(N.CHANGES)   # (id, why) against the level-0 scheme
JT = {j["id"]: (float(j["x"]), float(j["z"])) for j in CITY["joints"]["items"]}
J027, J046, J062 = JT["J027"], JT["J046"], JT["J062"]
LRT_W = float(LU.Norms().v("lrt.corridor_width_m", "double_track"))


def dedup(pts, tol=0.5):
    q = [tuple(map(float, pts[0]))]
    for p in pts[1:]:
        if math.dist(p, q[-1]) > tol:
            q.append(tuple(map(float, p)))
    return q


def red_w(cls, profile=None):
    return N.red_w(cls, profile)


# ===================================================================================================== 1. LRT line (frame)
OIZL = [tuple(p) for p in N.SID["s_oiz"]["line"]]
BLVDL = [tuple(p) for p in N.SID["s_blvd"]["line"]]
TAIL = [(3150.0, 11100.0), (3420.0, 12150.0), (3680.0, 12500.0), J046]          # level-0 lrt.line north of Каскелен
_head = fillet([J027, (660.0, -3500.0), OIZL[0], OIZL[1]], 300)
_join = fillet([OIZL[-2], OIZL[-1], BLVDL[1]], 150)
_tail = fillet([BLVDL[-2], BLVDL[-1]] + TAIL, 300)
LRT_PTS = dedup(_head[:-1] + OIZL[1:-1] + _join[1:-1] + BLVDL[1:-1] + _tail[1:])
L_LRT = LineString(LRT_PTS)


def chain(pt, L=None):
    return (L or L_LRT).project(Point(pt))


def at_chain(s, L=None):
    p = (L or L_LRT).interpolate(s)
    return (p.x, p.y)


# west branch (level-0 west_branch, years 2036–41): from the station «Центр Growing» on the trunk to J062 on the A-3
S_L7 = chain((2150.0, 3150.0))
B0 = at_chain(S_L7)
BR_PTS = dedup(fillet([B0, (1750.0, 2950.0), (900.0, 2680.0), J062], 300))
# the branch begins past the boulevard's red line (run 2, rule 25: its terminus L7w stood 228 m from the line's start, the
# platform pushed off the boulevard crossing): the terminus is the first 33 m platform, the walk to the trunk's L7 crosses the
# boulevard (≈ 50 m)
_blvd_red = unary_union([LineString(s_["line"]).buffer(N.red_w(s_["class"], s_.get("profile")) / 2.0 + 3.0)
                         for s_ in N.STREETS if s_.get("axis") == "ax_lrt_blvd" or s_["id"].startswith("s_blvd")])
_lb = LineString(BR_PTS)
_xb = _lb.difference(_blvd_red)
BR_CUT = min((_lb.project(Point(q.coords[0])) for q in C.lines_of(_xb) if q.length > 100.0), default=0.0)
BR_PTS = [tuple(q) for q in substring(_lb, BR_CUT, _lb.length).coords]
L_BR = LineString(BR_PTS)
# elevated sections: over the bypass railway and the river at Жанаарна (street overpass of бульвар Growing), over the river
# Каскелен before J046; the branch over the river at (900, 2680) and the A-3 to J062. The ramps (≤ 6 %) are part of the
# section (gen_lrt).
_xr = L_LRT.intersection(N.RAIL)
_cr = sorted(chain((q.x, q.y)) for q in getattr(_xr, "geoms", [_xr]) if q.geom_type == "Point")
SEC_ELEV = []
if _cr:
    # the viaduct stays up over the Южная магистраль just north of the tracks (gen_lrt: at 6 % it cannot regain the clearance
    # between the tracks and the street, level-2 run 1: s_south crossed at 3784 m inside the ramp; run 3: s_south stands there
    # on its rail-overpass embankment 4 m over the ground, so the deck needs ≈ 13 m over the ground and ≈ 230 m to come down at
    # 5,7 %: the viaduct ends 300 m past the street)
    _xs = LineString(N.SID["s_south"]["line"]).intersection(L_LRT)
    _cs = [chain((q.x, q.y)) for q in getattr(_xs, "geoms", [_xs]) if q.geom_type == "Point" and abs(chain((q.x, q.y)) - _cr[-1]) < 400.0]
    SEC_ELEV = [(_cr[0] - 230.0, max([_cr[-1] + 230.0] + [c + 300.0 for c in _cs]))]
_xw = L_LRT.intersection(N.WATER_LINE.union(N.WATER_POLY))
_cw = sorted(chain(q.centroid.coords[0]) for q in getattr(_xw, "geoms", [_xw]) if not q.is_empty)
_cw_n = [c for c in _cw if c > L_LRT.length - 400.0]
if _cw_n:
    SEC_ELEV.append((min(_cw_n) - 200.0, L_LRT.length))
_xwb = L_BR.intersection(N.WATER_LINE.union(N.WATER_POLY))
_cwb = sorted(chain(q.centroid.coords[0], L_BR) for q in getattr(_xwb, "geoms", [_xwb]) if not q.is_empty)
SEC_ELEV_BR = [(min(_cwb + [L_BR.length - 600.0]) - 180.0, L_BR.length)]
RAMP_M = 150.0
LRT_RAMPS = []
for a_, b_ in SEC_ELEV:
    LRT_RAMPS.append(substring(L_LRT, max(a_, 0.0), a_ + RAMP_M).buffer(15.0, cap_style=2))
    if b_ < L_LRT.length - 1.0:
        LRT_RAMPS.append(substring(L_LRT, b_ - RAMP_M, b_).buffer(15.0, cap_style=2))
# own right of way (not in a street median): J027 → the start of the OIZ street, Каскелен → J046, and the whole branch
S_OIZ0 = chain(OIZL[0])
S_BLVD1 = chain(BLVDL[-1])
OWN_ROW = unary_union([substring(L_LRT, 0, S_OIZ0).buffer(LRT_W / 2 + 2, cap_style=2),
                       substring(L_LRT, S_BLVD1, L_LRT.length).buffer(LRT_W / 2 + 2, cap_style=2),
                       L_BR.buffer(LRT_W / 2 + 2, cap_style=2)]).intersection(DIST.buffer(-0.5))
# stations: the level-0 points on the new line, then centred between the cross streets (section 4)
ST_V0 = [(s["id"], s["name_ru"], (float(s["x"]), float(s["z"]))) for s in V0["lrt"]["stations"]]
ST_BR = [("L7w", "Центр Growing (ветка на запад)", 20.0), ("LW1", "Западный бульвар", 1050.0 - BR_CUT)]
TERMINI = {"L7w"}       # a terminus stays at its line end (platform 3.5–36.5 m), not centred between cross streets
STATION_PTS = [at_chain(chain(xy)) for _, _, xy in ST_V0] + [at_chain(c, L_BR) for _, _, c in ST_BR]
LOG.append({"what": "ЛРТ: трасса", "trunk_m": round(L_LRT.length), "branch_m": round(L_BR.length),
            "elevated": [[round(a_), round(b_)] for a_, b_ in SEC_ELEV], "elevated_branch": [[round(a_), round(b_)] for a_, b_ in SEC_ELEV_BR]})

# ===================================================================================================== 2. landmark plots
# the twin's landmark models (gen/landmark_models.json) stand on their pads (LandmarkData.cs: PadW × PadD, yaw) in the
# industrial belt; a pad on a street, a house, water or the tracks moves to the nearest free place (moved: было → стало)
PADS = {"danaflex": (6668.0, 651.0, 300.0, 200.0, -81.7, "packaging"), "sunny_paper": (7540.0, 1468.0, 440.0, 280.0, -81.7, "paper"),
        "g_trans": (7882.0, 945.0, 290.0, 220.0, -81.7, "logistics_gtrans"), "ps_arna_twin": (1721.0, 360.0, 244.0, 164.0, 280.9, "substation"),
        # owner 02.11.2026: Mars Petcare leaves the scheme's lot at km 40 (its 300 m gap to the new quarters left 3.7 ha of
        # 32) for the nearest free place of the belt ≥ 300 m from housing (z_belt_1, west of Sunny Paper)
        "mars_petcare": (6622.0, 1300.0, 430.0, 300.0, -90.0, "food_mars")}
MARS_WHY = ("решение владельца 02.11.2026: завод перенесён с участка схемы у 40-го км А-3 (реестр, ± 500 м) в промпояс "
            "Growing-восток — на старом месте санитарный разрыв класса III (300 м) до новых кварталов оставлял 3,7 га из 32; "
            "здесь до жилья ≥ 300 м, рядом Sunny Paper и DanaFlex")
PAD_MARGIN = 12.0


def pad_rect(x, z, W, D, yaw):
    t = math.radians(yaw)
    ux, uz = math.cos(t), -math.sin(t)          # the model's local +X in the Unity frame (left-handed yaw about +Y)
    vx, vz = math.sin(t), math.cos(t)           # local +Z
    hw, hd = W / 2.0, D / 2.0
    return Polygon([(x + sx * hw * ux + sz * hd * vx, z + sx * hw * uz + sz * hd * vz)
                    for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])


def _avoid_now():
    reds = [LineString(s["line"]).buffer(red_w(s["class"], s.get("profile")) / 2.0 + 3.0, cap_style=2) for s in N.STREETS]
    reds += [q.buffer(red_w(cls) / 2.0 + 3.0, cap_style=2) for _, q, cls in N.OSM_HOST]
    return unary_union(reds + [N.WATER_STRIP, N.RAIL.buffer(30.0), L_LRT.buffer(15.0), L_BR.buffer(15.0)])


AVOID0 = _avoid_now()
shapely.prepare(AVOID0)
OK_PAD = unary_union([z["poly"] for z in Z.ZPLAN if z["use"] in ("industry", "logistics", "utility", "business")]).buffer(0)
OK_PS = DIST.difference(N.VILL).buffer(0)       # the substation stays at the twin's point («как есть с чипом модель»)
shapely.prepare(OK_PAD)
shapely.prepare(OK_PS)


def fit(poly_at, x0, z0, ok, avoid, step=20.0, rmax=900.0, extra=()):
    """The nearest offset (spiral of rings every `step` m) where poly_at(x, z) lies in `ok` and off `avoid`, houses and
    `extra` plots."""
    rings = [(0.0, 0.0)]
    r = step
    while r <= rmax:
        n = max(8, int(2 * math.pi * r / step))
        rings += [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        r += step
    for dx, dz in rings:
        P = poly_at(x0 + dx, z0 + dz)
        if not ok.contains(P) or avoid.intersects(P) or N.houses_hit(P.buffer(3.0)) or any(P.intersects(e) for e in extra):
            continue
        return P, (x0 + dx, z0 + dz)
    return None, None


PAD_FP = {}
for rid, (x, z, W, D, yaw, model_) in PADS.items():
    P, at = fit(lambda a, b: pad_rect(a, b, W + 2 * PAD_MARGIN, D + 2 * PAD_MARGIN, yaw), x, z,
                OK_PS if rid == "ps_arna_twin" else OK_PAD, AVOID0,
                extra=list(PAD_FP.values()))
    if P is None:
        LOG.append({"what": "площадка модели не нашла места", "id": rid})
        continue
    PAD_FP[rid] = P
    if math.dist(at, (x, z)) > 1.0:
        MOVED.append((rid, [x, z], [round(at[0], 1), round(at[1], 1)],
                      f"площадка модели двойника {W:.0f} × {D:.0f} м (LandmarkData) в точке двойника задевала красную линию улицы, "
                      f"дом, воду или ж/д — сдвинута на {math.dist(at, (x, z)):.0f} м к ближайшему свободному месту той же зоны"))
# the gas power plant: the whole zone is the plot (the scheme zone of the plant); Mars Petcare stands on its pad in the
# belt since 02.11.2026 — the scheme's Mars lot at km 40 is an ordinary part of the industrial park
ZB = {z["id"]: z for z in Z.ZPLAN}
ZONE_LOT = {"gtes_doosan": "z_gtes"}
ZB["z_mars"].update({"name_ru": "Индустриальный парк у 40-го км А-3 (участок Mars Petcare схемы)",
                     "rules": dict(ZB["z_mars"]["rules"], jobs_per_ha=35), "density": dict(ZB["z_mars"]["density"], jobs_per_ha=35),
                     "why": ZB["z_mars"]["why"] + "; " + MARS_WHY + " — участок отдан лёгким производствам, как OIZ TULIP"})
N.BARRIERS[:] = ([OWN_ROW] + [p.buffer(N.D_IN) for p in PAD_FP.values()] + [ZB[zid]["poly"] for zid in ZONE_LOT.values()]
                  + [Z.CORE_CIRCLE, Z.CORE_PARK])
import round_quarter as RQ  # noqa: E402
_hard = unary_union([z["poly"] for z in Z.ZPLAN if z["use"] in ("village_existing", "utility")])
# the round centre of the master plan drawing: ring and radial streets, ordinary mixed-use blocks between them
CORE_N = RQ.add(N, "s_core", Z.CORE_C, Z.CORE_RADII, 8, 2034, "Круглый центр", "чертёж генплана № 727, решение владельца 09.11.2026", avoid=_hard)

# ===================================================================================================== 3. local streets
t = time.time()
N.LRT_RAMPS[:] = LRT_RAMPS
made = N.generate_local(stations=STATION_PTS, barriers=unary_union(N.BARRIERS), lrt_line=L_LRT)
LOG.append({"what": "местные улицы сгенерированы", "n": made, "s": round(time.time() - t, 1)})
print("local streets", made, round(time.time() - t, 1), "s; total streets", len(N.STREETS), flush=True)
t = time.time()


def ext_ok(P):
    return DIST.exterior.distance(P) < 3.0 or any(math.dist((P.x, P.y), (n["x"], n["z"])) < 1.0 for n in N.NODES.values())


BARRIER_U = unary_union(N.BARRIERS)


def extend_free_ends(layers=("frame",), reach=500.0):
    """Free ends of the frame streets: on along their direction to the first street (≤ reach), never through houses."""
    out = []
    ix = N.Index()
    for s in N.STREETS:
        if s["_layer"] not in layers:
            continue
        for end in (0, -1):
            pt = s["line"][end]
            if N._attached_ix(pt, ix, s["id"], ext_ok):
                continue
            prev = s["line"][1] if end == 0 else s["line"][-2]
            d = np.array(pt, float) - np.array(prev, float)
            d /= np.linalg.norm(d)
            hosts = [L for sid, L, cls in ix.near(Point(pt).buffer(reach), skip=s["id"]) if cls not in N.NO_HOST]
            hp = N._ray_hit(tuple(pt), d, hosts, reach)
            seg = LineString([tuple(pt), hp]) if hp is not None else None
            if seg is None or N.houses_hit(seg.buffer(red_w(s["class"]) / 2.0)) or seg.intersects(BARRIER_U):
                # no street straight ahead (or it is behind houses or the LRT's own corridor): the nearest street aside
                hp = None
                for L in sorted(hosts, key=lambda L_: L_.distance(Point(pt))):
                    if L.distance(Point(pt)) > 300.0:
                        break
                    q = L.interpolate(L.project(Point(pt)))
                    sg = LineString([tuple(pt), (q.x, q.y)])
                    if sg.length < 1.0 or N.houses_hit(sg.buffer(red_w(s["class"]) / 2.0)) or sg.intersects(BARRIER_U) \
                            or sg.intersects(N.RAIL) or not DIST.buffer(0.5).contains(sg):
                        continue
                    hp, seg = (q.x, q.y), sg
                    break
            if hp is None:
                out.append({"what": "конец улицы каркаса без продолжения", "id": s["id"], "at": P1(pt)})
                continue
            if end == 0:
                s["line"].insert(0, P1(hp))
            else:
                s["line"].append(P1(hp))
            s["struct"] += [{"from": P1(a_), "to": P1(b_), "kind": k} for a_, b_, k in N.structs([tuple(pt), hp])]
            out.append({"what": "улица каркаса продолжена до ближайшей улицы", "id": s["id"], "to": P1(hp), "m": round(seg.length, 1)})
            ix = N.Index()
    return out


LOG += extend_free_ends()
TRIM_LOG = []
N.trim_free_ends(ext_ok, log=TRIM_LOG)
LOG += TRIM_LOG
N.snap_ends(tol=N.SNAP_J, log=LOG)
N.house_lanes(log=LOG)
N.link_dead_ends(log=LOG)
LOG.append({"what": "доводка сети (концы, проулки, тупики)", "s": round(time.time() - t, 1)})

LIFT_M = 40.0           # the overpass span over the tracks: half span 30 m (RAIL_CLEAR) + 10 (run 3: ends 22–27 m from the rail
#                         stayed blind, ends 50–56 m from it on the embankment were joined)
SLIDE_M = 60.0          # where the end goes when no other street meets the road on the ground on its side


def ends_off_overpass(log=None):
    """A generated street (quarter edge or grid) that ends on a street where that one is lifted over the railway cannot
    meet it (gen_network leaves the end blind: rule 5, run 3 at s_south and s_central); nor can it cross the LRT where the
    LRT climbs to its viaduct (rule 25, run 4: e_p097_1_4_y1 at (458.5, -534.1), 4.7 m under the deck). The end slides along
    the street out of that stretch: to the nearest end of another street meeting it there, else 20 m past the stretch; the
    street drops its last vertices until the new last leg meets the street at ≥ 25° without crossing the tracks."""
    hosts = []
    ramps = unary_union(LRT_RAMPS) if LRT_RAMPS else Polygon()
    for F in N.STREETS:
        if F["_layer"] in N.GEN or F["class"] in N.NO_HOST:
            continue
        g = LineString(F["line"])
        x = g.intersection(N.RAIL)
        spans = [(min(g.project(Point(t_["from"])), g.project(Point(t_["to"]))), max(g.project(Point(t_["from"])), g.project(Point(t_["to"]))))
                 for t_ in F.get("struct") or [] if t_.get("kind") in ("overpass", "bridge")]
        # only where the street is lifted over the tracks (a level crossing keeps its side streets: t_e2d0ac1b, build 9)
        cr = [g.project(q) for q in getattr(x, "geoms", [x]) if q.geom_type == "Point"
              and any(a_ - 1.0 <= g.project(q) <= b_ + 1.0 for a_, b_ in spans)]
        zones_ = [(cx - LIFT_M, cx + LIFT_M, "rail") for cx in cr]
        if not ramps.is_empty and g.intersects(ramps):
            for q in C.lines_of(g.intersection(ramps)):
                a_, b_ = sorted((g.project(Point(q.coords[0])), g.project(Point(q.coords[-1]))))
                zones_.append((a_ - 5.0, b_ + 5.0, "lrt"))
        if zones_:
            hosts.append((F, g, zones_))
    n = 0
    for s_ in N.STREETS:
        if s_["_layer"] not in N.GEN:
            continue
        for end in (0, -1):
            P = Point(s_["line"][end])
            for F, g, zones_ in hosts:
                if g.distance(P) > 1.5:
                    continue
                c = g.project(P)
                inside = [z_ for z_ in zones_ if z_[0] < c < z_[1]]
                if not inside:
                    continue
                lo, hi, why_ = inside[0]
                sd = 1.0 if (hi - c) <= (c - lo) else -1.0
                bnd = hi if sd > 0 else lo
                # other streets ending on F on this side, past the stretch
                cand = []
                for o in N.STREETS:
                    if o is s_ or o is F:
                        continue
                    for q in (o["line"][0], o["line"][-1]):
                        Q = Point(q)
                        if g.distance(Q) < 1.5:
                            cq = g.project(Q)
                            if (cq - bnd) * sd >= 0.0 and abs(cq - bnd) <= 160.0 and not any(z_[0] < cq < z_[1] for z_ in zones_):
                                cand.append(cq)
                c2 = min(cand, key=lambda v: abs(v - c)) if cand else bnd + sd * (SLIDE_M - LIFT_M)
                if not 0.0 < c2 < g.length:
                    continue
                T = g.interpolate(c2)
                pts_ = [tuple(p_) for p_ in s_["line"]]
                if end == 0:
                    pts_ = pts_[::-1]
                pts_.pop()
                fd = np.array(g.interpolate(min(c2 + 5, g.length)).coords[0]) - np.array(g.interpolate(max(c2 - 5, 0)).coords[0])
                fd /= np.linalg.norm(fd)
                ok = False
                others = [Point(q) for o in N.STREETS if o is not s_ and o is not F for q in (o["line"][0], o["line"][-1])]
                near_l = unary_union([LineString(o["line"]) for o in N.STREETS if o is not s_ and o is not F
                                      and LineString(o["line"]).distance(T) < 400.0] or [Point(0, 0).buffer(0)])
                while pts_:
                    leg = LineString([pts_[-1], (T.x, T.y)])
                    v = np.array(leg.coords[1]) - np.array(leg.coords[0])
                    ang = math.degrees(math.acos(min(1.0, abs(float(np.dot(v / max(np.linalg.norm(v), 1e-9), fd))))))
                    clear = leg.difference(T.buffer(8.0)).difference(Point(pts_[-1]).buffer(8.0)).distance(near_l) > 2.0     # not along or across another street
                    if leg.length > 20.0 and ang >= 25.0 and not leg.intersects(N.RAIL) and g.distance(Point(pts_[-1])) > 15.0 \
                            and not leg.intersects(BARRIER_U) and clear:
                        ok = True
                        break
                    if len(pts_) < 2:
                        break
                    dropped = LineString(pts_[-2:])
                    if any(dropped.distance(q) < 1.0 for q in others if q.distance(Point(pts_[-1])) < dropped.length + 2.0):
                        break                    # another street meets the stretch the end would give up: keep the street
                    pts_.pop()
                if not ok and pts_:
                    # the last kept vertex meets the street too flat: a bend D m off the street, then square onto it (build 13:
                    # e_p097_1_4 at 19°)
                    nrm = np.array([-fd[1], fd[0]])
                    sgn = 1.0 if float(np.dot(np.array(pts_[-1]) - np.array(T.coords[0]), nrm)) >= 0 else -1.0
                    for D in (35.0, 50.0, 25.0):
                        Bp = tuple(np.array(T.coords[0]) + sgn * nrm * D)
                        l1, l2 = LineString([pts_[-1], Bp]), LineString([Bp, (T.x, T.y)])
                        both = LineString([pts_[-1], Bp, (T.x, T.y)])
                        if l1.length > 10.0 and not both.intersects(N.RAIL) and not both.intersects(BARRIER_U) \
                                and both.difference(T.buffer(8.0)).difference(Point(pts_[-1]).buffer(8.0)).distance(near_l) > 2.0 \
                                and not N.houses_hit(both.buffer(4.0)):
                            pts_.append(Bp)
                            ok = True
                            break
                if not ok or len(pts_) < 1:
                    if log is not None:
                        log.append({"what": "конец улицы на путепроводе или рампе ЛРТ: обход не найден", "id": s_["id"], "on": F["id"],
                                    "at": P1((P.x, P.y))})
                    continue
                pts_.append((T.x, T.y))
                if end == 0:
                    pts_ = pts_[::-1]
                s_["line"] = [P1(p_) for p_ in pts_]
                s_["struct"] = [{"from": P1(a_), "to": P1(b_), "kind": k} for a_, b_, k in N.structs(pts_)]
                n += 1
                if log is not None:
                    log.append({"what": "конец улицы сдвинут с путепровода за насыпь" if why_ == "rail" else "конец улицы сдвинут с рампы ЛРТ",
                                "id": s_["id"], "on": F["id"],
                                "from": P1((P.x, P.y)), "to": P1((T.x, T.y)), "m": round(abs(c2 - c), 1)})
                break
    return n


print("ends off overpasses", ends_off_overpass(LOG), flush=True)


def serve_pieces(log=None, min_m2=2000.0, reach=150.0, inside=15.0):
    """Built zone land that the streets and the LRT's own corridor cut off from every street (rule 12: a block with
    buildings needs an entry): a local side street from the nearest street into the piece (≤ reach, ending `inside` m in),
    never across an expressway, a ramp, the LRT corridor, water or a house. Returns the streets made."""
    lines = [(x["id"], LineString(x["line"]), x["class"]) for x in N.STREETS]
    lines += [("osm:" + oid, q, cls) for oid, q, cls in N.OSM_HOST]
    reds = unary_union([L.buffer(red_w(c) / 2.0) for _, L, c in lines if c not in ("expressway", "ramp")]
                       + [L.buffer(N.EXP_HALF) for _, L, c in lines if c in ("expressway", "ramp")])
    acc = [(sid, L, c) for sid, L, c in lines if c not in ("expressway", "ramp", "pedestrian_street", "bike_path")]
    at = shapely.STRtree([L for _, L, _ in acc])
    barrier = unary_union([L for _, L, c in lines if c in ("expressway", "ramp")] + [OWN_ROW])
    made_ = []
    for z in Z.ZPLAN:
        if z["use"] not in Z.GRID or (z.get("rules") or {}).get("lot_split") == "none" or z["id"] in ZONE_LOT.values():
            continue
        land = z["poly"].intersection(DIST).difference(reds).difference(OWN_ROW).buffer(0)
        for q in getattr(land, "geoms", [land]):
            if q.geom_type != "Polygon" or q.area < min_m2:
                continue
            if any(acc[i][1].buffer(red_w(acc[i][2]) / 2.0 + 2.5).intersects(q) for i in at.query(q.buffer(N.EXP_HALF))):
                continue
            best = None
            for i in at.query(q.buffer(reach)):
                sid, L, c = acc[i]
                a, b = shapely.ops.nearest_points(L, q)
                d = a.distance(b)
                if d > reach - inside or (best is not None and d >= best[0]):
                    continue
                u = np.array([b.x - a.x, b.y - a.y]) / max(d, 1e-6)
                end = Point(b.x + u[0] * inside, b.y + u[1] * inside)
                sp = LineString([(a.x, a.y), (end.x, end.y)])
                if sp.crosses(barrier) or sp.intersects(OWN_ROW) or sp.intersects(N.WATER_POLY) or not DIST.contains(sp) \
                        or N.houses_hit(sp.buffer(red_w("local") / 2.0)) or not q.contains(end) or sp.intersects(N.RAIL):
                    continue
                best = (d, sid, sp)
            rec = {"zone": z["id"], "ha": round(q.area / 1e4, 2), "at": [round(v) for v in q.representative_point().coords[0]]}
            if best is None:
                if log is not None:
                    log.append({"what": "земля зоны без улицы: подъезда нет (ждёт решения)", **rec})
                continue
            sid_new = f"v_serve_{len(made_) + 1:03d}"
            N.street(sid_new, "local", best[2].coords, "въезд в квартал", int(z["years"][0]), layer="lane",
                     why=MODEL + f": земля зоны {z['id']} ({q.area / 1e4:.1f} га) отрезана от улиц линией ЛРТ, водой или "
                                 f"границами зон — въезд {best[2].length:.0f} м от {best[1]} (правило 12: у квартала со зданиями есть въезд)")
            made_.append(sid_new)
            if log is not None:
                log.append({"what": "въезд в отрезанную землю зоны", "id": sid_new, "from": best[1], "m": round(best[2].length), **rec})
    return made_


serve_pieces(log=LOG)
print("network done", len(N.STREETS), round(time.time() - T0, 1), flush=True)
t = time.time()
N.phase_years("road", log=LOG)
LOG.append({"what": "годы улиц по кускам между перекрёстками", "s": round(time.time() - t, 1)})

DIV_CLS = {"arterial_regulated", "expressway"}          # two carriageways by norm (street.<class>.carriageways = 2)
IC_TYPES = {"diamond", "partial_cloverleaf", "cloverleaf", "trumpet", "directional", "grade_separation", "roundabout", "square"}


def _divided(s_):
    return s_["class"] in DIV_CLS or float((s_.get("profile") or {}).get("median_w") or 0) > 0


def _unit(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-9)


def divided_end_tees(log=None):
    """A divided street (two carriageways) that ends where an undivided street goes on, or where its own next piece opens
    later, leaves both carriageway ends blind: gen_network joins a carriageway end only to a carriageway (≤ 10° kink) or
    moves it onto a road crossing its end (run 3, rule 5: s_oiz at (780, −3000) and (494, −742), s_central at
    (10131, 4303)). Such an end gets a short local cross street through it (the carriageways meet it as a T), and each
    undivided street that ended there ends at the cross street's end on its own side instead."""
    made_ = 0
    for s_ in list(N.STREETS):
        if not _divided(s_) or str(s_.get("source", "")).startswith("keep_existing") or s_["class"] in ("expressway", "ramp"):
            continue
        for end in (0, -1):
            E = np.array(s_["line"][end], float)
            P = Point(E)
            if DIST.exterior.distance(P) < 3.0:
                continue
            if any(n["type"] in IC_TYPES and math.dist((n["x"], n["z"]), E) < 120.0 or
                   n["type"] in ("joint", "edge", "end") and math.dist((n["x"], n["z"]), E) < 5.0 for n in N.NODES.values()):
                continue
            d = _unit(E - np.array(s_["line"][1 if end == 0 else -2], float))
            mates, inner = [], False
            for o in N.STREETS:
                if o is s_:
                    continue
                g = LineString(o["line"])
                if g.distance(P) > 1.0:
                    continue
                oe = 0 if math.dist(o["line"][0], E) < 1.0 else (-1 if math.dist(o["line"][-1], E) < 1.0 else None)
                if oe is None:
                    inner = True                 # the end meets a road through its side: gen_network snaps it there
                    break
                mates.append((o, oe))
            if inner or not mates:
                continue
            if any(str(o.get("source", "")).startswith("keep_existing") for o, _ in mates):
                continue                         # an existing road's end: gen_network joins as OSM draws it
            go_on, near_on = [], False
            for o, oe in mates:
                do = _unit(np.array(o["line"][1 if oe == 0 else -2], float) - E)
                kink = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(d, do))))))
                # (a divided piece that opens later leaves the end blind until then: run 4, s_oiz at (494, -742) in 2027)
                go_on.append(_divided(o) and kink <= 10.0 and all(a_ <= b_ for a_, b_ in zip(o["years"], s_["years"])))
                near_on |= not _divided(o) and kink < 45.0
            # a divided piece going on (from the same year: gen_network's year_gaps links the carriageways) and no undivided street
            # going on almost straight (its end is not snapped onto the carriageways): nothing to do
            if any(go_on) and not near_on:
                continue
            prof = s_.get("profile") or {}
            med = float(prof.get("median_w") or 2.0)
            lanes = prof.get("lanes") or [2, 2]
            H = med / 2.0 + 3.5 * max(lanes) + 12.0
            nrm = np.array([-d[1], d[0]])
            A, B = E + nrm * H, E - nrm * H
            tee = LineString([tuple(A), tuple(B)])
            if N.houses_hit(tee.buffer(4.0)) or not DIST.buffer(-0.5).contains(tee):
                if log is not None:
                    log.append({"what": "конец разделённой улицы: поперечная улица не помещается", "id": s_["id"], "at": P1(E)})
                continue
            tid = f"v_tee_{s_['id']}_{0 if end == 0 else 1}"
            yrs = [min(v) for v in zip(*([s_["years"]] + [o["years"] for o, _ in mates]))]
            N.street(tid, "local", [tuple(A), tuple(B)], "поперечная улица у конца " + (s_.get("name_ru") or s_["id"]), yrs[0],
                     years=yrs, layer="tee", struct=N.structs([tuple(A), tuple(B)]),
                     why=MODEL + f": разделённая улица {s_['id']} кончается здесь — обе проезжие части примыкают к поперечной "
                                 "улице (gen_network соединяет конец проезжей части только с проезжей частью или с дорогой поперёк)")
            for (o, oe), on in zip(mates, go_on):
                if _divided(o):
                    continue                     # a divided piece going on later meets the cross street the same way
                prev = np.array(o["line"][1 if oe == 0 else -2], float)
                side = A if float(np.dot(prev - E, nrm)) >= 0 else B
                o["line"][oe] = P1(side)
                o["struct"] = [{"from": P1(a_), "to": P1(b_), "kind": k} for a_, b_, k in N.structs([tuple(p_) for p_ in o["line"]])]
            made_ += 1
            if log is not None:
                log.append({"what": "конец разделённой улицы: поперечная улица", "id": tid, "for": s_["id"], "at": P1(E),
                            "mates": [o["id"] for o, _ in mates]})
    return made_


print("divided-end cross streets", divided_end_tees(LOG), flush=True)


def tidy_junctions(log=None, near=16.0, min_left=20.0):
    """Two clean-ups of the generated streets (run 3, rule 6):
    1. a street whose last stretch runs along another street (the same line twice: a split piece that kept the shared part)
       is cut back to where it meets that street (n2346 at (1632, 3192): g_p051_0_011 over g_p051_0_011_1);
    2. a street that ends on another street within `near` m of a junction already there (ends meeting on that street) ends
       at that junction when it then has at most four arms: gen_network moved such an end on along its own direction
       onto the next street (over its own continuation, (2993, 5901): «пересекаются без узла»)."""
    import shapely as _sh
    gen = [x for x in N.STREETS if x["_layer"] in N.GEN or x["_layer"] in ("tee", "lane", "link")]
    lines = [LineString(x["line"]) for x in N.STREETS]
    tree = _sh.STRtree(lines)
    n1 = n2 = 0
    for a in gen:
        for end in (0, -1):
            A = LineString(a["line"] if end == -1 else a["line"][::-1])          # runs towards the end in question
            for j in tree.query(Point(A.coords[-1]).buffer(1.0)):
                b = N.STREETS[j]
                if b is a:
                    continue
                Bb = lines[j].buffer(0.6)
                tail = A.intersection(Bb)
                part = max(C.lines_of(tail), key=lambda q: q.length, default=None)
                if part is None or part.length < 5.0 or Point(A.coords[-1]).distance(part) > 0.5:
                    continue
                s0 = min(A.project(Point(q)) for q in part.coords)
                if s0 < min_left:
                    continue
                keep = substring(A, 0.0, s0)
                pts_ = [P1(q) for q in keep.coords]
                q_ = lines[j].interpolate(lines[j].project(Point(pts_[-1])))
                pts_[-1] = P1((q_.x, q_.y))
                a["line"] = pts_ if end == -1 else pts_[::-1]
                a["struct"] = [{"from": P1(x0), "to": P1(x1), "kind": k} for x0, x1, k in N.structs([tuple(q) for q in a["line"]])]
                n1 += 1
                if log is not None:
                    log.append({"what": "улица шла поверх другой: обрезана до примыкания", "id": a["id"], "over": b["id"], "m": round(A.length - s0, 1)})
                break
    lines = [LineString(x["line"]) for x in N.STREETS]
    tree = _sh.STRtree(lines)
    ends_all = [(x, e, tuple(x["line"][e])) for x in N.STREETS for e in (0, -1)]
    etree = _sh.STRtree([Point(p_) for _, _, p_ in ends_all])

    def arms_at(p_):
        P = Point(p_)
        n = 0
        for j in tree.query(P.buffer(0.5)):
            g = lines[j]
            if g.distance(P) > 0.5:
                continue
            d0 = Point(g.coords[0]).distance(P) < 0.5
            d1 = Point(g.coords[-1]).distance(P) < 0.5
            n += 1 if (d0 or d1) else 2
        return n
    for a in gen:
        for end in (0, -1):
            E = Point(a["line"][end])
            hosts = [j for j in tree.query(E.buffer(0.5)) if N.STREETS[j] is not a and lines[j].distance(E) < 0.5
                     and Point(lines[j].coords[0]).distance(E) > 0.5 and Point(lines[j].coords[-1]).distance(E) > 0.5]
            if len(hosts) != 1:
                continue
            g = lines[hosts[0]]
            best = None
            for k in etree.query(E.buffer(near)):
                o, oe, p_ = ends_all[k]
                if o is a or o is N.STREETS[hosts[0]]:
                    continue
                Q = Point(p_)
                if Q.distance(E) < 0.5 or g.distance(Q) > 0.5 or Q.distance(E) > near:
                    continue
                if best is None or Q.distance(E) < best[0]:
                    best = (Q.distance(E), p_)
            for q in (g.coords[0], g.coords[-1]):
                if Point(q).distance(E) <= near and (best is None or Point(q).distance(E) < best[0]):
                    best = (Point(q).distance(E), tuple(q))
            if best is None or arms_at(best[1]) + 1 > 4:
                continue
            prev = a["line"][1] if end == 0 else a["line"][-2]
            if math.dist(prev, best[1]) < min_left:
                continue
            last = LineString([prev, a["line"][end]])
            on_leg = [last.project(Point(p_)) for o, oe, p_ in ends_all if o is not a and last.distance(Point(p_)) < 1.0
                      and Point(p_).distance(E) > 1.0 and math.dist(p_, prev) > 1.0]
            if on_leg:
                # another street ends on the leg that would move (build 13: g_p016_0_116_1): the line keeps a vertex there
                kq = last.interpolate(max(on_leg))
                if math.dist((kq.x, kq.y), best[1]) < min_left:
                    continue
                if end == -1:
                    a["line"].insert(len(a["line"]) - 1, P1((kq.x, kq.y)))
                else:
                    a["line"].insert(1, P1((kq.x, kq.y)))
            a["line"][end] = P1(best[1])
            a["struct"] = [{"from": P1(x0), "to": P1(x1), "kind": k} for x0, x1, k in N.structs([tuple(q) for q in a["line"]])]
            n2 += 1
            if log is not None:
                log.append({"what": "конец улицы перенесён в соседний перекрёсток", "id": a["id"], "to": P1(best[1]), "m": round(best[0], 1)})
            lines = [LineString(x["line"]) for x in N.STREETS]
            tree = _sh.STRtree(lines)
            # the moved end is where the next ones look (build 16: e_p020_0_0 and e_p024_0_0 swapped places at (513, 8191))
            ends_all = [(x, e, tuple(x["line"][e])) for x in N.STREETS for e in (0, -1)]
            etree = _sh.STRtree([Point(p_) for _, _, p_ in ends_all])
    return n1, n2


print("tidy junctions", tidy_junctions(LOG), flush=True)
# a pedestrian street opens as one piece: a later piece beyond a crossing left its first piece ending blind in the median of
# the crossing road for years (run 3: s_centre_walk in 2033–2038 at (2685, 3251), rule 5)
_ped = {}
for s_ in N.STREETS:
    if s_["class"] == "pedestrian_street":
        _ped.setdefault(s_.get("axis") or s_["id"].split("_y")[0], []).append(s_)
for _k, _ss in _ped.items():
    if len(_ss) > 1:
        _y = [min(v) for v in zip(*[x["years"] for x in _ss])]
        for x in _ss:
            if list(x["years"]) != _y:
                LOG.append({"what": "пешеходная улица открывается целиком", "id": x["id"], "years": [list(x["years"]), _y]})
                x["years"] = list(_y)


def _no_later(a, b):
    return all(x_ <= y_ for x_, y_ in zip(a["years"], b["years"]))


def ped_end_links(log=None):
    """A pedestrian street that ends on a street opening later is blind until then (run 4: s_centre_walk_y1 on e_p047_0_0,
    2033 vs 2039, at (3016, 3221)): the stretch of that street from the walk to its nearest end on a street already open
    becomes its own piece and opens with the walk."""
    n = 0
    for w in [x for x in N.STREETS if x["class"] == "pedestrian_street"]:
        for end in (0, -1):
            E = Point(w["line"][end])
            touch = [x for x in N.STREETS if x is not w and LineString(x["line"]).distance(E) < 0.5]
            if not touch or any(_no_later(x, w) for x in touch):
                continue
            done = False
            for T in touch:
                TL = LineString(T["line"])
                c = TL.project(E)
                if c < 5.0 or c > TL.length - 5.0:
                    continue
                for lo_, hi_, q_end in ((0.0, c, T["line"][0]), (c, TL.length, T["line"][-1])):
                    Q = Point(q_end)
                    if not any(_no_later(x, w) for x in N.STREETS if x is not T and x is not w and LineString(x["line"]).distance(Q) < 0.5):
                        continue
                    if hi_ - lo_ > 300.0:
                        continue
                    near_ = [tuple(q) for q in substring(TL, lo_, hi_).coords]
                    far_ = [tuple(q) for q in (substring(TL, hi_, TL.length) if lo_ == 0.0 else substring(TL, 0.0, lo_)).coords]
                    yrs = [min(a_, b_) for a_, b_ in zip(T["years"], w["years"])]
                    T["line"] = [P1(q) for q in far_]
                    T["struct"] = [{"from": P1(a_), "to": P1(b_), "kind": k} for a_, b_, k in N.structs(far_)]
                    nid = T["id"] + "_w"
                    N.street(nid, T["class"], near_, T.get("name_ru") or "", yrs[0], years=yrs, layer="link",
                             struct=N.structs(near_), profile=T.get("profile"),
                             why=MODEL + f": кусок {T['id']} от пешеходной улицы {w['id']} до открытой улицы — открывается вместе с ней")
                    n += 1
                    if log is not None:
                        log.append({"what": "кусок улицы у конца пешеходной открывается с ней", "id": nid, "walk": w["id"],
                                    "m": round(hi_ - lo_, 1), "years": yrs})
                    done = True
                    break
                if done:
                    break
    return n


print("pedestrian ends", ped_end_links(LOG), flush=True)
for s in N.STREETS:
    if s["class"].startswith("driveway"):
        s["class"] = "local"
        s["why"] = (s.get("why") or "") + "; в growing_e.json — местная улица (проезды даёт только land_driveways)"

# ===================================================================================================== 4. LRT v1
ROADS_X = {"trunk": [], "branch": []}
for s in N.STREETS:
    if s["class"] in ("expressway", "ramp"):
        continue
    for key, L in (("trunk", L_LRT), ("branch", L_BR)):
        x = LineString(s["line"]).intersection(L)
        for g in getattr(x, "geoms", [x]):
            if g.geom_type == "Point":
                ROADS_X[key].append((L.project(g), s["id"]))
# where the line enters and leaves the median of the OIZ street and the boulevard, the street's carriageways meet over the
# line: no platform there (run 3, rule 25: s_oiz_y1 over L3 at (442, -642), s_blvd_y1 over L14 at (3127, 10959))
for _c in (S_OIZ0, S_BLVD1):
    _p = Point(at_chain(_c))
    _near = [x for x in N.STREETS if x["class"] not in ("expressway", "ramp") and x.get("axis") in ("ax_oiz", "ax_lrt_blvd")
             and min(Point(x["line"][0]).distance(_p), Point(x["line"][-1]).distance(_p)) < 40.0]
    ROADS_X["trunk"].append((_c, _near[0]["id"] if _near else ("s_oiz" if _c == S_OIZ0 else "s_blvd")))
for k in ROADS_X:
    ROADS_X[k].sort()
PLAT = 33.0


def place_station(s0, L, rx):
    before = [c for c in rx if c[0] < s0 - 1]
    after = [c for c in rx if c[0] > s0 + 1]
    lo = before[-1][0] if before else 0.0
    hi = after[0][0] if after else L.length
    if hi - lo < PLAT + 20:
        return s0, hi - lo
    if (hi - lo) < 200 or abs(s0 - 0.5 * (lo + hi)) > (hi - lo) / 2 - PLAT:
        return 0.5 * (lo + hi), hi - lo
    return s0, hi - lo


def sections(L, elev):
    cuts = [0.0]
    for a_, b_ in elev:
        cuts += [max(a_, 0.0), min(b_, L.length)]
    cuts.append(L.length)
    out = []
    for k in range(len(cuts) - 1):
        a_, b_ = cuts[k], cuts[k + 1]
        if b_ - a_ < 1:
            continue
        out.append({"from": P1(at_chain(a_, L)), "to": P1(at_chain(b_, L)), "kind": "elevated" if k % 2 == 1 else "ground"})
    return out


SP_MIN, SP_MAX = 820.0, 1480.0          # lrt.station_spacing_km 0.8–1.5, 20 m to spare


def _free_intervals(L, rx, elev):
    """Where a platform centre may stand: between cross streets (a gap under 200 m only at its middle), off the viaduct
    ramps."""
    cs = sorted(c for c, _ in rx)
    b = [0.0] + cs + [L.length]
    iv = []
    for a, c in zip(b, b[1:]):
        if c - a < 2 * PLAT + 6.0:
            continue
        iv.append(((a + c) / 2, (a + c) / 2) if c - a < 200.0 else (a + PLAT + 3.0, c - PLAT - 3.0))
    bad = []
    for a_, b_ in elev:
        if a_ > 1.0:
            bad.append((a_ - PLAT, a_ + RAMP_M + PLAT))
        if b_ < L.length - 1.0:
            bad.append((b_ - RAMP_M - PLAT, b_ + PLAT))
    out = []
    for lo, hi in iv:
        pieces = [(lo, hi)]
        for x0, x1 in bad:
            nxt = []
            for p0, p1 in pieces:
                if p1 < x0 or p0 > x1:
                    nxt.append((p0, p1))
                    continue
                if p0 < x0:
                    nxt.append((p0, x0))
                if p1 > x1:
                    nxt.append((x1, p1))
            pieces = nxt
        out += [q for q in pieces if q[1] >= q[0]]
    return out


def place_all(L, plan, rx, elev):
    """Each station at the free point nearest its scheme point, in line order, 0.8–1.5 km from the one before (run 4: the
    stations centred between cross streets came 0.75 and 1.55 km apart, rule 25)."""
    iv = _free_intervals(L, rx, elev)

    def near(t, lo, hi):
        best = None
        for a, b in iv:
            a2, b2 = max(a, lo), min(b, hi)
            if a2 > b2:
                continue
            x = min(max(t, a2), b2)
            if best is None or abs(x - t) < abs(best - t):
                best = x
        return best
    pos, prev = {}, None
    for sid, nm, s0 in sorted(plan, key=lambda t: t[2]):
        if sid in TERMINI:
            x = s0
        else:
            x = near(s0, prev + SP_MIN, prev + SP_MAX) if prev is not None else near(s0, -1e9, 1e9)
            if x is None:
                LOG.append({"what": "станция ЛРТ: шаг 0,8–1,5 км не выдержан", "id": sid})
                x = near(s0, -1e9, 1e9)
            if x is None:
                x = s0
        pos[sid] = x
        prev = x
    return pos


def stations(L, plan, elev, rx):
    out = []
    pos = place_all(L, plan, rx, elev)
    for sid, nm, s0 in plan:
        sm = pos[sid]
        p = at_chain(sm, L)
        before = [c for c in rx if c[0] < sm]
        after = [c for c in rx if c[0] > sm]
        out.append({"id": sid, "name_ru": nm, "x": round(p[0], 1), "z": round(p[1], 1),
                    "between": [before[-1][1] if before else None, after[0][1] if after else None],
                    "kind": "elevated" if any(a_ <= sm <= b_ for a_, b_ in elev) else "ground", "_s": sm})
        if math.dist(p, at_chain(s0, L)) > 1.0:
            LOG.append({"what": "станция ЛРТ сдвинута между поперечными улицами", "id": sid, "m": round(math.dist(p, at_chain(s0, L))),
                        "chain": round(sm)})
    out.sort(key=lambda s_: s_["_s"])
    return out


# the branch terminus clear of the streets next to the boulevard too (build 11: e_p059_0_1 over L7w at 28 m): the line
# starts 20 m past the last street that crosses it in its first 120 m
_cut2 = max([c + 20.0 for c, _ in ROADS_X["branch"] if c < 120.0], default=0.0)
if _cut2 > 0.0:
    L_BR = substring(L_BR, _cut2, L_BR.length)
    BR_PTS = [tuple(q) for q in L_BR.coords]
    BR_CUT += _cut2
    SEC_ELEV_BR = [(a_ - _cut2, b_ - _cut2) for a_, b_ in SEC_ELEV_BR]
    ROADS_X["branch"] = [(c - _cut2, sid_) for c, sid_ in ROADS_X["branch"] if c > _cut2]
    ST_BR = [(sid_, nm_, (s0_ if sid_ in TERMINI else s0_ - _cut2)) for sid_, nm_, s0_ in ST_BR]
    LOG.append({"what": "ЛРТ: ветка начинается за улицами у бульвара", "cut_m": round(BR_CUT, 1)})
ST_T = stations(L_LRT, [(sid, nm, chain(xy)) for sid, nm, xy in ST_V0], SEC_ELEV, ROADS_X["trunk"])
ST_B = stations(L_BR, ST_BR, SEC_ELEV_BR, ROADS_X["branch"])
for st in ST_T:
    v0p = next(xy for sid, _, xy in ST_V0 if sid == st["id"])
    if math.dist(v0p, (st["x"], st["z"])) > 60.0:
        MOVED.append((f"станция ЛРТ {st['id']}", list(v0p), [st["x"], st["z"]],
                      "станция на оси линии в разделительной полосе бульвара (схема — точка у оси), платформа между поперечными улицами "
                      "(правило 25)"))


def _street_years(sids):
    ys = [int(N.SID[s]["years"][0]) for s in sids if s in N.SID]
    return max(ys) if ys else 2031


# the trunk opens with the last of the streets it runs in (бульвар Growing 2031, улица OIZ 2027), the branch as in the scheme
_in = {sid for _, sid in ROADS_X["trunk"]}
Y_TRUNK = max(2031, _street_years([s["id"] for s in N.STREETS if s.get("axis") in ("ax_lrt_blvd", "ax_oiz")]))
LRT = {
    "lines": [
        {"id": "lrt_growing_e", "name_ru": "ЛРТ Growing (участок Growing-восток)", "line": [P1(p) for p in LRT_PTS],
         "sections": sections(L_LRT, SEC_ELEV),
         "stations": [{k: v for k, v in s_.items() if not k.startswith("_")} for s_ in ST_T],
         "ends": [{"kind": "joint", "id": "J027", "to": "golden"}, {"kind": "joint", "id": "J046", "to": "green"}],
         "joints": [{"joint_id": "J027", "x": J027[0], "z": J027[1], "to": "golden"},
                    {"joint_id": "J046", "x": J046[0], "z": J046[1], "to": "green"}],
         "years": Y4(Y_TRUNK),
         "why": "ось схемы ax_lrt: от стыка J027 с Golden своей полосой до главной улицы OIZ TULIP, по разделительной полосе улицы "
                "OIZ и бульвара Growing (эстакада над обходом Жетыген – Казыбек бек и рекой у Жанаарны) через главный центр и "
                "северные кварталы до Каскелена, дальше своей полосой (мост через Каскелен) к стыку J046 с Green; станции схемы "
                "между поперечными улицами, шаг 0,8–1,5 км"},
        {"id": "lrt_growing_e_west", "name_ru": "ЛРТ Growing: ветка на запад (к аэропорту)", "line": [P1(p) for p in BR_PTS],
         "sections": sections(L_BR, SEC_ELEV_BR),
         "stations": [{k: v for k, v in s_.items() if not k.startswith("_")} for s_ in ST_B],
         "ends": [{"kind": "terminus", "id": "L7w"}, {"kind": "joint", "id": "J062", "to": "growing_w"}],
         "joints": [{"joint_id": "J062", "x": J062[0], "z": J062[1], "to": "growing_w"}],
         "years": Y4(2041),
         "why": "ветка схемы ax_lrt_west (2036–41): от станции «Центр Growing» своей полосой на запад, эстакадой над рекой и А-3 "
                "к стыку J062 (дальше — Growing-запад, к аэропорту); пересадка на ствол — у станции «Центр Growing»"}],
    "depots": []}

# ===================================================================================================== 5. zones
ZONES = []
ZIDS = set()
taken = Polygon()


def _ring_parts(q, depth=0):
    """Rings of q at 0.1 m: a ring that the rounding pinches (a narrow neck) is split into its valid lobes (build 10)."""
    pts = poly_pts(q)
    P2 = Polygon(pts)
    if P2.is_valid or depth > 3:
        return [pts]
    out = []
    for r in C.polys_of(P2.buffer(0)):
        if r.area >= 200.0:
            out += _ring_parts(r, depth + 1)
    return out


def zone_out(z, poly, rules):
    global taken
    parts = C.simple_parts(poly.buffer(0).intersection(DIST).difference(taken).buffer(0), 500.0)
    rings = []
    for q in parts:
        taken = taken.union(q)
        rings += _ring_parts(q)
    for k, ring in enumerate(rings):
        q = Polygon(ring)
        zid = z["id"] if k == 0 else f"{z['id']}_p{k + 1}"
        while zid in ZIDS:
            zid = zid + "_s"
        ZIDS.add(zid)
        d = {"id": zid, "use": z["use"], "name_ru": z["name_ru"], "polygon": ring, "years": z["years"],
             "rules": copy.deepcopy(rules), "why": z["why"], "area_ha": round(q.area / 1e4, 2), "_base": z["id"]}
        if z.get("density"):
            d["density"] = z["density"]
        if z.get("population_existing"):
            d["population_existing"] = z["population_existing"]
        d["_fit"] = z.get("fit_of") or z["id"]
        ZONES.append(d)


# landmark pads: their own zone of the model's use (a pad that lies across two scheme zones is not cut)
PAD_USE = {"danaflex": "industry", "sunny_paper": "industry", "g_trans": "logistics", "ps_arna_twin": "utility",
           "mars_petcare": "industry"}
for rid, P in PAD_FP.items():
    src = max((z for z in Z.ZPLAN if z["poly"].intersects(P)), key=lambda z: z["poly"].intersection(P).area)
    use = PAD_USE[rid]
    for z in Z.ZPLAN:
        if z["poly"].intersects(P):
            z["poly"] = z["poly"].difference(P).buffer(0)
    rules_ = copy.deepcopy(Z.use_rules(src["id"], use, src.get("density") or {})) if use != "utility" else {"lot_split": "none"}
    zid = f"lm_{rid}"
    Z.ZPLAN.append({"id": zid, "use": use, "name_ru": f"Участок модели {REG[rid]['name_ru'] if rid in REG else rid}", "poly": P,
                    "years": src["years"] if use != "utility" else [2026, 2027], "rules": rules_, "density": src.get("density"),
                    "src": "v0", "why": MODEL + f": площадка модели двойника ({PADS[rid][5]}) с запасом {PAD_MARGIN:.0f} м — свой участок "
                                                f"в зоне {src['id']}"})
    SCHEME_CHANGES.append((zid, f"площадка модели {rid} ({P.area / 1e4:.1f} га) — своя зона из {src['id']}: модель стоит на своём "
                                f"участке, улицы квартала его обходят"))

# sanitary gaps (rule 15): every industrial and logistics zone states its SZZ class; no new housing or social buildings within
# the class width w, nor within w × zone_factor in the downwind sector (szz.wind_sector_deg). The gap is planted (park zone)
# on the housing side (new quarters) or carved from the production zone (existing houses stay as they are).
_LN = LU.Norms()
SZZ_W = {k: float(v["min"]) for k, v in _LN.v("szz.class_width_m").items()}
_WS = _LN.v("szz.wind_sector_deg")
SZZ_F, SZZ_SECTOR = float(_WS["zone_factor"]), tuple(_WS["default_sector"])
SZZ_CLASS = {
    "z_mars": ("IV", MODEL + ": участок Mars Petcare схемы после переноса завода в промпояс (02.11.2026) — лёгкие и сборочные "
                     "производства, как OIZ TULIP у А-3: класс IV"),
    "lm_mars_petcare": ("III", MODEL + ": корма для животных (Mars Petcare, 100 тыс. т/год) — класс III с запасом "
                                      "(szz.class_examples: мясокомбинаты I, мельницы II; готовые корма без убоя — III)"),
    "z_belt": ("III", MODEL + ": промпояс двойника (бумага Sunny Paper, упаковка DanaFlex, машиностроение и сборка): классы "
                      "I–II в СЭЗ не ставятся (схема), принят III — 300 м"),
    "z_oiz": ("IV", MODEL + ": индустриальный парк сборочных и лёгких производств (автосборка, eVTOL), у А-3 и Жанаарны только "
                     "классы IV–V (схема)"),
    "z_kairat": ("IV", MODEL + ": модульное строительство ModeX и лёгкие производства у посёлка — класс IV"),
    "z_north_ind": ("III", MODEL + ": гипсовый завод KNAUF (szz.class_examples: ЖБИ, известь — III–II; гипс — III)"),
    "lm_danaflex": ("IV", MODEL + ": гибкая упаковка (печать, ламинирование) — класс IV"),
    "lm_sunny_paper": ("III", MODEL + ": бумажное производство из макулатуры — класс III"),
}
SZZ_DEFAULT = ("V", MODEL + ": склады и логистика готовых товаров без выбросов — наименьший класс szz.class_width_m "
                           "(в szz.class_examples складов нет)")


def szz_of(zid):
    for k, v in SZZ_CLASS.items():
        if zid == k or zid.startswith(k + "_") or (k in ("z_belt", "z_oiz", "z_kairat", "z_north_ind") and zid.startswith(k)):
            return v
    return SZZ_DEFAULT


for z in Z.ZPLAN:
    if z["use"] in ("industry", "logistics"):
        cls_, why_ = szz_of(z["id"])
        z["rules"]["szz_class"] = cls_
        z["why"] = z["why"] + f"; СЗЗ класса {cls_} ({SZZ_W[cls_]:.0f} м): {why_}"


def _wedge(poly, a0, a1, r, step=40.0):
    """Points within r of `poly` in the bearing range a0..a1 (azimuth from +z toward +x, as in rule 15)."""
    if poly.geom_type != "Polygon":                  # a zone cut in parts (owner_reloc 05.11.2026): its hull, the wider wedge
        poly = poly.convex_hull
    b = poly.exterior
    pts = [b.interpolate(t_) for t_ in np.arange(0.0, b.length, step)] + [poly.centroid]
    angs = np.radians(np.linspace(a0, a1 if a1 >= a0 else a1 + 360.0, 13))
    return unary_union([Polygon([(p.x, p.y)] + [(p.x + r * math.sin(t_), p.y + r * math.cos(t_)) for t_ in angs]) for p in pts])


def _wedge_any(g, a0, a1, r, step=40.0):
    return unary_union([_wedge(q, a0, a1, r, step) for q in C.polys_of(g)] or [Polygon()])


RES_USES = ("residential_high", "residential_mid", "residential_low", "mixed_centre")
SOC_USES = ("medical", "sport")
SZZ_LOG = []
_t = time.time()
# class bands (run 3, rule 15: 409 errors — new village schools, kindergartens and clinics and the industrial centre's fire
# stations within 300 m, or downwind within 600 m, of class III sheds in z_belt and z_north_ind): the part of a class III–IV
# zone within its class width of housing, a village or a centre (twice the width where that lies downwind of the zone) takes
# production of class V only (assembly, machining, warehouses), as the scheme has it at Daulet and at A-3 / Zhanaarna
# («только классы IV–V»); the far part keeps its class. The class V gaps (50 m, 100 m downwind) are carved below.
SENS_USES = RES_USES + SOC_USES + ("village_existing", "business")
REV_SECTOR = ((SZZ_SECTOR[0] + 180.0) % 360.0, (SZZ_SECTOR[1] + 180.0) % 360.0)
_sens = [z for z in Z.ZPLAN if z["use"] in SENS_USES]
_stree = shapely.STRtree([z["poly"] for z in _sens])
for z in list(Z.ZPLAN):
    if z["use"] not in ("industry", "logistics") or z["id"].startswith("lm_") or z["id"] in ZONE_LOT.values():
        continue
    cls_ = z["rules"].get("szz_class")
    w = SZZ_W[cls_]
    if w <= SZZ_W["V"]:
        continue
    reach = w * SZZ_F
    S_ = [_sens[int(i)]["poly"] for i in _stree.query(z["poly"].buffer(reach + 20.0))]
    S_ = unary_union([q for q in S_ if q.distance(z["poly"]) < reach + 20.0]).buffer(0) if S_ else Polygon()
    if S_.is_empty:
        continue
    far = z["poly"].difference(S_.buffer(w + 10.0).union(_wedge_any(S_.simplify(10.0), *REV_SECTOR, reach + 20.0))).buffer(0)
    far = far.buffer(-20.0).buffer(20.0).intersection(z["poly"]).buffer(0)       # no thin far tongues: they go to class V
    far = unary_union([q for q in C.polys_of(far) if q.area >= 2.0e4]) if not far.is_empty else far
    band = z["poly"].difference(far).buffer(0)
    if band.area < 2000.0:
        continue
    zv = copy.deepcopy({k: v for k, v in z.items() if k != "poly"})
    zv.update({"id": z["id"] + "_v", "poly": band, "fit_of": z["id"], "name_ru": z["name_ru"] + " (полоса класса V)"})
    zv["rules"]["szz_class"] = "V"
    zv["why"] = (z["why"].split("; СЗЗ класса")[0] + f"; полоса у жилья, сёл и центров: только производства класса V (сборка, "
                 f"механообработка, склады) — СЗЗ {SZZ_W['V']:.0f} м, по ветру {SZZ_W['V'] * SZZ_F:.0f} м; дальше — класс {cls_}")
    Z.ZPLAN.insert(Z.ZPLAN.index(z) + 1, zv)
    SCHEME_CHANGES.append((zv["id"], f"{band.area / 1e4:.1f} га зоны {z['id']} в {w:.0f} м от жилья, сёл и центров (по ветру "
                                     f"{reach:.0f} м) — производства только класса V вместо {cls_} (СЗЗ 50 м): так схема у Даулета "
                                     "и у А-3 («только классы IV–V»); новые школы, сады и поликлиники сёл — вне СЗЗ (правило 15)"))
    if far.is_empty:
        z["poly"] = Polygon()
        SZZ_LOG.append((z["id"], "весь в полосе V", cls_, round(band.area / 1e4, 1)))
    else:
        z["poly"] = far
        SZZ_LOG.append((z["id"], "полоса V", cls_, round(band.area / 1e4, 1)))
Z.ZPLAN[:] = [z for z in Z.ZPLAN if not z["poly"].is_empty]
IND = [z for z in Z.ZPLAN if z["use"] in ("industry", "logistics") and z["rules"].get("lot_split") != "none"]
_ztree = shapely.STRtree([z["poly"] for z in Z.ZPLAN])
for I in IND:
    w = SZZ_W[I["rules"]["szz_class"]]
    reach = w * SZZ_F
    near = [Z.ZPLAN[int(i)] for i in _ztree.query(I["poly"].buffer(reach))]
    wedge = None
    for R in [z for z in near if z["use"] in RES_USES + SOC_USES]:
        if I["poly"].distance(R["poly"]) >= reach:
            continue
        if wedge is None:
            wedge = I["poly"].buffer(w).union(_wedge(I["poly"].simplify(10.0), *SZZ_SECTOR, reach))
        strip = R["poly"].intersection(wedge).buffer(0)
        if strip.area < 500.0:
            continue
        cls_ = I["rules"]["szz_class"]
        gid = f"g_szz_{I['id']}_{R['id']}"
        zone_out({"id": gid, "use": "park", "years": R["years"], "name_ru": f"Санитарный разрыв {I['name_ru']} — {R['name_ru']} (озеленение)",
                  "why": f"СЗЗ класса {cls_}: {w:.0f} м, в подветренном секторе {SZZ_SECTOR[0]:.0f}–{SZZ_SECTOR[1]:.0f}° — "
                         f"{reach:.0f} м (правило 15): жильё и соцобъекты не ближе к производству"}, strip, {"lot_split": "none"})
        R["poly"] = R["poly"].difference(strip).buffer(0)
        SZZ_LOG.append((I["id"], R["id"], cls_, round(strip.area / 1e4, 2)))
        SCHEME_CHANGES.append((gid, f"санитарный разрыв класса {cls_} ({w:.0f} м, по ветру {reach:.0f} м; {strip.area / 1e4:.2f} га) "
                                    f"из зоны {R['id']}: озеленение"))
# existing villages next to production zones: the class width is carved from the production zone (the houses stay; rule 15
# counts existing houses inside the width as fine and downwind as a warning, so only the width is kept free, and never more
# than a third of a zone)
# (a village or a centre: its schools, kindergartens, clinics and fire stations stand where gen_buildings puts them, so the
# gap — the width, and twice the width where the village lies downwind of the zone — comes off the production side)
VZ = [z for z in Z.ZPLAN if z["use"] in ("village_existing", "business")]
for I in IND:
    if I["id"] in ZONE_LOT.values():
        continue
    w = SZZ_W[I["rules"]["szz_class"]]
    reach = w * SZZ_F
    vil = [R["poly"] for R in VZ if I["poly"].distance(R["poly"]) < reach]
    if not vil:
        continue
    hs = N.houses_hit(I["poly"].buffer(w))
    _V = unary_union(vil).buffer(0)
    strip = I["poly"].intersection(_V.buffer(w).union(_wedge_any(_V.simplify(10.0), *REV_SECTOR, reach))).buffer(0)
    if strip.area < 500.0:
        continue
    if I["rules"]["szz_class"] != "V" and strip.area > I["poly"].area / 3.0:
        LOG.append({"what": "СЗЗ у села больше трети зоны: разрыв не вырезан (дома существующие, правило 15 — предупреждение)",
                    "zone": I["id"], "ha": round(strip.area / 1e4, 1)})
        continue
    cls_ = I["rules"]["szz_class"]
    gid = f"g_szz_{I['id']}_houses"
    zone_out({"id": gid, "use": "park", "years": I["years"], "name_ru": f"Санитарный разрыв {I['name_ru']} — сёла и центры (озеленение)",
              "why": f"СЗЗ класса {cls_}: {w:.0f} м, в подветренном секторе {SZZ_SECTOR[0]:.0f}–{SZZ_SECTOR[1]:.0f}° — {reach:.0f} м "
                     "(правило 15) от сёл (новые школы, сады, поликлиники; дома остаются) и деловых центров"}, strip, {"lot_split": "none"})
    I["poly"] = I["poly"].difference(strip).buffer(0)
    SZZ_LOG.append((I["id"], "villages and centres", cls_, round(strip.area / 1e4, 2)))
    SCHEME_CHANGES.append((gid, f"санитарный разрыв класса {cls_} ({w:.0f} м, по ветру {reach:.0f} м; {strip.area / 1e4:.2f} га) "
                                f"из зоны {I['id']} у сёл и деловых центров (домов рядом: {len(hs)}): озеленение"))
LOG.append({"what": "санитарные разрывы (озеленение) между производством и жильём", "pairs": SZZ_LOG, "s": round(time.time() - _t, 1)})
# island quarters that no street can reach (growing_e_net.UNSERVED): reserve, not buildable
for k, P in enumerate(N.UNSERVED):
    q = P.buffer(N.D_IN + 2.0)
    zone_out({"id": f"x_unserved_{k + 1}", "use": "reserve", "years": [2050, 2050],
              "name_ru": "Резерв: участок без подъезда (между водой, трассой и сёлами)",
              "why": "ни одна улица не доходит до участка без пересечения трассы, ж/д или домов: резерв до подъезда"}, q, {"lot_split": "none"})
    LOG.append({"what": "участок без подъезда переведён в резерв", "ha": round(q.area / 1e4, 1), "at": [round(v) for v in P.centroid.coords[0]]})
    SCHEME_CHANGES.append((f"x_unserved_{k + 1}", f"{q.area / 1e4:.1f} га у ({P.centroid.x:.0f}, {P.centroid.y:.0f}) — резерв: до участка "
                                                  "не дойти улицей без пересечения трассы, ж/д или домов"))
# under the LRT viaducts on their own right of way: a green strip (gen_blocks_lots takes only the ground corridor out of the
# blocks; run 2, rule 25: the west branch viaduct through new houses at (961, 2700) and (1028, 2722))
for k_, (L_, el_, yy_) in enumerate(((L_LRT, SEC_ELEV, [2027, 2031]), (L_BR, SEC_ELEV_BR, [2036, 2041]))):
    for j_, (a_, b_) in enumerate(el_):
        q_ = substring(L_, max(a_, 0.0), min(b_, L_.length)).buffer(LRT_W / 2 + 4.0, cap_style=2).intersection(OWN_ROW.buffer(4.0))
        q_ = q_.intersection(DIST).buffer(0)
        if q_.area < 500.0:
            continue
        gid_ = f"g_lrt_viaduct_{k_ + 1}_{j_ + 1}"
        zone_out({"id": gid_, "use": "park", "years": yy_, "name_ru": "Озеленение под эстакадой ЛРТ",
                  "why": f"полоса {LRT_W / 2 + 4.0:.0f} м от оси эстакады ЛРТ на своей полосе отвода: под пролётами нет зданий "
                         "(правило 25)"}, q_, {"lot_split": "none"})
        SCHEME_CHANGES.append((gid_, f"озеленение под эстакадой ЛРТ ({q_.area / 1e4:.1f} га): дома под пролётом сняты (правило 25)"))
for z in Z.ZPLAN:
    if z["id"].startswith("lm_"):
        zone_out(z, z["poly"], z["rules"])
for z in Z.ZPLAN:
    if not z["id"].startswith("lm_"):
        zone_out(z, z["poly"], z["rules"])
# no land outside the zones: every leftover sliver joins the zone it shares the longest border with
_gap = DIST.difference(unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES]))
_ZT = shapely.STRtree([Polygon(z["polygon"]).buffer(0) for z in ZONES])
for g in [q for q in getattr(_gap, "geoms", [_gap]) if q.geom_type == "Polygon" and q.area > 1.0]:
    best, bl = None, 0.0
    for i in _ZT.query(g.buffer(0.5)):
        sh = sum(q_.exterior.intersection(g.buffer(0.5)).length for q_ in C.polys_of(Polygon(ZONES[int(i)]["polygon"]).buffer(0)))
        if sh > bl:
            best, bl = int(i), sh
    if best is None:
        continue
    m = Polygon(ZONES[best]["polygon"]).buffer(0).union(g.buffer(0.05)).buffer(0)
    others = [Polygon(ZONES[int(i)]["polygon"]).buffer(0) for i in _ZT.query(g.buffer(1.0)) if int(i) != best]
    if others:
        m = m.difference(unary_union(others)).buffer(0)
    if m.geom_type == "MultiPolygon":
        m = max(m.geoms, key=lambda q: q.area)
    if m.geom_type == "Polygon" and m.interiors:
        m = Polygon(m.exterior).difference(unary_union(others)).buffer(0) if others else Polygon(m.exterior)
        if m.geom_type == "MultiPolygon":
            m = max(m.geoms, key=lambda q: q.area)
    if m.geom_type == "Polygon" and not m.interiors and m.area >= Polygon(ZONES[best]["polygon"]).buffer(0).area - 1.0:
        ZONES[best]["polygon"] = poly_pts(m)
        ZONES[best]["area_ha"] = round(m.area / 1e4, 2)
# strict sanitary gaps (owner's request after run 5): the passes above leave production next to housing (a village strip over
# a third of the zone is not cut, the class V bands run to the village edge, the cover slivers join any neighbour; spec:
# z_mars 0 m of 300, z_belt_3_v, z_log_south, z_north_ind_1_v 0 m of 50). Last, on the final zones: every industry and
# logistics zone gives up all its land within its class width (szz.class_width_m, min) of any housing — new quarters, mixed
# centres, the waterfront, the campus and the existing villages; the gap is planted (park). Production pieces left under
# 200 m² go to the gap, gap pieces under 200 m² to the park they touch.
HOUSE_USES = ("residential_high", "residential_mid", "residential_low", "mixed_centre", "waterfront", "campus", "village_existing")
SZZ_STRICT = []
_t = time.time()
_HU = unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES if z["use"] in HOUSE_USES]).buffer(0)


def _rings_of(g, min_area=1.0):
    out = []
    for q in C.simple_parts(g, min_area):
        out += _ring_parts(q)
    return out


def _new_zone(z, zid, ring):
    while zid in ZIDS:
        zid = zid + "_s"
    ZIDS.add(zid)
    d = copy.deepcopy(z)
    d.update({"id": zid, "polygon": ring, "area_ha": round(Polygon(ring).area / 1e4, 2)})
    ZONES.append(d)
    return d


def _join_park(q):
    """A gap piece under 200 m² joins the park zone it shares the longest border with (no zones of a few m²)."""
    best, bl = None, 0.0
    for z in ZONES:
        if z["use"] != "park":
            continue
        p = Polygon(z["polygon"]).buffer(0)
        if p.distance(q) > 0.5:
            continue
        sh = p.exterior.intersection(q.buffer(0.5)).length
        if sh > bl:
            best, bl = z, sh
    if best is None:
        return False
    m = Polygon(best["polygon"]).buffer(0).union(q.buffer(0.05)).buffer(0)
    if m.geom_type != "Polygon" or m.interiors:
        return False
    best["polygon"] = poly_pts(m)
    best["area_ha"] = round(m.area / 1e4, 2)
    return True


for I in [z for z in ZONES if z["use"] in ("industry", "logistics")]:
    cls_ = I["rules"].get("szz_class") or SZZ_DEFAULT[0]
    w = SZZ_W[cls_]
    P = Polygon(I["polygon"]).buffer(0)
    if P.distance(_HU) >= w:
        continue
    gap_ = P.intersection(_HU.buffer(w + 1.0)).buffer(0)        # +1 m: buffer arcs are chords, rings round to 0.1 m
    # the zone rings carry hair-thin needles (z_belt_3_v, z_log_south, z_belt_6_v: a 1–2 m² spike 80 m long to the village
    # edge); the overlay keeps a needle as a zero-width tail, so the rest is opened by 5 cm first
    rest_ = P.difference(gap_).buffer(-0.05, join_style=2).buffer(0.05, join_style=2).intersection(P).buffer(0)
    keep = [q for q in C.polys_of(rest_) if q.area >= 200.0]
    keep_g = unary_union(keep).buffer(0) if keep else Polygon()
    gap_ = P.difference(keep_g).buffer(0) if keep else P
    if gap_.is_empty:
        continue
    k_rings = _rings_of(keep_g, 200.0) if keep else []
    if k_rings:
        I["polygon"] = k_rings[0]
        I["area_ha"] = round(Polygon(k_rings[0]).area / 1e4, 2)
        for k, ring in enumerate(k_rings[1:]):
            _new_zone(I, f"{I['id']}_p{k + 2}", ring)
    else:
        ZONES.remove(I)
    gid = f"g_szz_{I['id']}_strict"
    gz = {"use": "park", "name_ru": f"Санитарный разрыв {I['name_ru']} — жильё и сёла (озеленение)", "years": I["years"],
          "rules": {"lot_split": "none"}, "_base": gid, "_fit": gid,
          "why": f"СЗЗ класса {cls_}: {w:.0f} м (szz.class_width_m, min; правило 15) — часть зоны {I['id']} ближе {w:.0f} м к "
                 "жилью (новые кварталы, смешанные центры, существующие сёла) снята с производства и озеленена"}
    n_ = 0
    for ring in _rings_of(gap_):
        if Polygon(ring).area < 200.0 and _join_park(Polygon(ring).buffer(0)):
            continue
        _new_zone(gz, gid if n_ == 0 else f"{gid}_p{n_ + 1}", ring)
        n_ += 1
    SZZ_STRICT.append((I["id"], cls_, round(gap_.area / 1e4, 2)))
    SCHEME_CHANGES.append((gid, f"санитарный разрыв класса {cls_} ({w:.0f} м; {gap_.area / 1e4:.2f} га) из зоны {I['id']}"
                                + ("" if k_rings else " (вся зона)") + ": ни одна промышленная и складская зона не ближе ширины "
                                "СЗЗ к жилью и сёлам — озеленение"))
LOG.append({"what": "строгий санитарный разрыв: производство не ближе ширины СЗЗ к жилью и сёлам", "zones": SZZ_STRICT,
            "ha": round(sum(x[2] for x in SZZ_STRICT), 2), "s": round(time.time() - _t, 1)})
print("strict SZZ", sorted(SZZ_STRICT, key=lambda x: -x[2])[:10], flush=True)

print("zones", len(ZONES), round(time.time() - T0, 1), flush=True)
# ===================================================================================================== 6. targets and densities
RED = unary_union([LineString(s["line"]).buffer(red_w(s["class"], s.get("profile")) / 2.0, cap_style=2) for s in N.STREETS
                   if s["class"] not in ("expressway", "ramp")]
                  + [LineString(s["line"]).buffer(25.0, cap_style=2) for s in N.STREETS if s["class"] == "expressway"]
                  + [q.buffer(red_w(cls) / 2.0, cap_style=2) for _, q, cls in N.OSM_HOST])
NET_LAND = DIST.difference(RED).difference(OWN_ROW)
shapely.prepare(NET_LAND)


def net_ha(z):
    return Polygon(z["polygon"]).buffer(0).intersection(NET_LAND).area / 1e4


JOBS_GP = 206100   # генплан № 727: Growing 309,2 тыс., доля половины как в схеме
POP_PLAN, JOBS_PLAN = int(V0["targets"]["population_2050"]), JOBS_GP
RES_PER_HOME = 2.5
HOMES_T = int(round(POP_PLAN / RES_PER_HOME, -1))
JOBS_T = int(round(JOBS_PLAN, -2))
SKIP = {"village_existing"}
_t = time.time()
NETHA = {z["id"]: net_ha(z) for z in ZONES}
LOG.append({"what": "чистая площадь кварталов по зонам", "s": round(time.time() - _t, 1)})
JOBS_RES = {"residential_high": 30.0, "residential_mid": 15.0, "residential_low": 5.0}
H_SCALED = {"residential_high", "residential_mid", "residential_low", "mixed_centre"}
J_SCALED = {"business", "mixed_centre"}
FH_M = LU.floor_heights()
TALL_H = 28.0
_fl_done = {}
for z in ZONES:
    r = z["rules"]
    fl = r.get("floors")
    if not fl or z["use"] in SKIP or z["use"] in ("industry", "logistics"):
        continue
    _fh = FH_M.get("business", 4.43) if z["use"] in ("business", "mixed_centre", "medical") else FH_M.get("res_mid", 3.6)
    lo = int(TALL_H // _fh)
    if fl[0] > lo:
        r["floors"] = [lo, fl[1]]
        _fl_done.setdefault(z["_base"], f"нижняя этажность {fl[0]} → {lo} ({lo} × {_fh:.2f} м ≤ 28 м)")
for _b, _m in sorted(_fl_done.items()):
    SCHEME_CHANGES.append((_b, f"{_m}: пожарные разрывы 22 м между зданиями выше 28 м (fire_access) — из двух близких зданий выше "
                               "28 м поднимается одно, второе остаётся до 28 м"))
for _b in sorted({z["_base"] for z in ZONES if z["use"] in ("business", "mixed_centre") and z["_base"] != "z_centre_main"}):
    SCHEME_CHANGES.append((_b, f"потолок высоты {35 if Z.ZBY[_b]['use'] == 'business' else 40} → {Z.BIZ_CAP} м (до 11 офисных этажей по "
                               "4,43 м, ниже 50 м радиуса согласования аэродрома Жетыген): при 35–40 м кварталы набрали 75–85 % мест "
                               "схемы (прогон 2)"))
for z in ZONES:
    if z["use"] in JOBS_RES:
        z["rules"]["jobs_per_ha"] = max(float(z["rules"].get("jobs_per_ha") or 0), JOBS_RES[z["use"]])


def _sum(key, pick):
    return sum(NETHA[z["id"]] * (z["rules"].get(key) or 0) for z in ZONES if pick(z))


h_fix = _sum("homes_per_ha", lambda z: z["use"] not in SKIP and z["use"] not in H_SCALED)
h_var = _sum("homes_per_ha", lambda z: z["use"] in H_SCALED)
j_fix = _sum("jobs_per_ha", lambda z: z["use"] not in SKIP and z["use"] not in J_SCALED)
j_var = _sum("jobs_per_ha", lambda z: z["use"] in J_SCALED)
FH = (HOMES_T - h_fix) / h_var
FJ = (JOBS_T - j_fix) / j_var
for z in ZONES:
    if z["use"] in SKIP:
        continue
    r = z["rules"]
    if z["use"] in H_SCALED and r.get("homes_per_ha"):
        r["homes_per_ha"] = round(r["homes_per_ha"] * FH, 1)
    if z["use"] in J_SCALED and r.get("jobs_per_ha"):
        r["jobs_per_ha"] = round(r["jobs_per_ha"] * FJ, 1)

# --- what the blocks hold (district/growing_e_fit.json from a gen_buildings run, growing_e_fit.py): business, mixed,
# industry and logistics zones keep the density their blocks held (one storey of 13,6 m sheds in industry and logistics,
# 11 office storeys under the 49 m cap in the centres); a landmark lot keeps its zone density (its capacity, no rule
# buildings: the twin model stands there); the jobs left over go to the residential zones (offices and shops in the housing blocks along the
# streets, one factor FR for all), and the homes left over by the mixed centres to the residential zones (FH2)
FIT_P = os.path.join(HERE, "growing_e_fit.json")
FIT = {"zones": {}, "village_jobs": 0}
if os.path.exists(FIT_P):
    with open(FIT_P, encoding="utf-8") as _f:
        FIT = json.load(_f)
CAP_USES = {"business", "mixed_centre", "industry", "logistics", "medical"}
LM_ZONES = {z["id"] for z in ZONES if z["id"].startswith("lm_") or z["_base"] in ZONE_LOT.values()}
HELD = {}


def _fit_of(z):
    """The fit row of the zone; a zone (or zone part) the fit run did not have takes the mean share its scheme zone held."""
    f = FIT["zones"].get(z["id"])
    if f:
        return f
    b = z.get("_fit") or z["_base"]
    xs = [v for k, v in FIT["zones"].items() if k == b or k.startswith(b + "_p") or k.startswith(b + "_v")]
    if not xs:
        return None
    row = {"use": xs[0]["use"]}
    for key, rk in (("jobs_per_ha", "jobs_ratio"), ("homes_per_ha", "housing_ratio")):
        ys = [x for x in xs if x.get(rk) is not None and x.get(key)]
        if ys:
            row[key] = ys[0][key]
            row[rk] = round(sum(x[rk] for x in ys) / len(ys), 4)
    return row


for z in ZONES:
    r = z["rules"]
    if z["use"] in SKIP:
        continue
    if z["id"] in LM_ZONES:
        continue            # the landmark lot carries the zone density as its capacity (gen_blocks_lots), no rule buildings
    f = _fit_of(z)
    if not f:
        continue
    for key, rk in (("jobs_per_ha", "jobs_ratio"), ("homes_per_ha", "housing_ratio")):
        if f.get(rk) is None or not f.get(key) or not r.get(key):
            continue
        if z["use"] not in CAP_USES and f[rk] >= 0.97:
            continue            # a residential zone that held its density takes its share of the rest (FR, FH2)
        held = round(float(f[key]) * min(float(f[rk]), 1.0) * (0.98 if f[rk] < 0.97 else 1.0), 1)
        if held < r[key] or z["use"] not in CAP_USES:
            HELD.setdefault(z["id"], {})[key.split("_")[0]] = [r[key], held]
            r[key] = held
VILLAGE_JOBS = int(FIT.get("village_jobs") or 0)
RES_USES = set(JOBS_RES)


def _open(z, k):
    return z["use"] in RES_USES and k not in HELD.get(z["id"], {})


j_cap = _sum("jobs_per_ha", lambda z: z["use"] not in SKIP and not _open(z, "jobs"))
j_res = _sum("jobs_per_ha", lambda z: _open(z, "jobs"))
FR = max(1.0, (JOBS_T - VILLAGE_JOBS - j_cap) / j_res) if j_res else 1.0
h_cap = _sum("homes_per_ha", lambda z: z["use"] not in SKIP and not _open(z, "homes"))
h_res = _sum("homes_per_ha", lambda z: _open(z, "homes"))
FH2 = max(1.0, (HOMES_T - h_cap) / h_res) if h_res else 1.0
for z in ZONES:
    r = z["rules"]
    if _open(z, "jobs"):
        r["jobs_per_ha"] = round(r["jobs_per_ha"] * FR, 1)
    if _open(z, "homes") and r.get("homes_per_ha"):
        r["homes_per_ha"] = round(r["homes_per_ha"] * FH2, 1)
_by_base = {}
for zid, v in HELD.items():
    b = next(z["_base"] for z in ZONES if z["id"] == zid)
    _by_base.setdefault(b, []).append(v)
for b, vs in sorted(_by_base.items()):
    parts = []
    for k, ru in (("jobs", "мест/га"), ("homes", "кв./га")):
        xs = [v[k] for v in vs if k in v]
        if xs:
            parts.append(f"{k} {xs[0][0]:g} → {xs[0][1]:g} {ru}")
    SCHEME_CHANGES.append((b, "плотность по тому, что набрали кварталы (прогон gen_buildings, growing_e_fit.json): " + "; ".join(parts)
                           + ("; " + vs[0]["why"] if vs[0].get("why") else "")))
_res_open = sorted({z["_base"] for z in ZONES if _open(z, "jobs")})
if FR > 1.0 and _res_open:
    SCHEME_CHANGES.append(("жилые зоны", f"рабочие места в жилых кварталах ×{FR:.2f} ({len(_res_open)} зон: офисы и магазины в "
                                          "домах вдоль улиц): деловые, смешанные, промышленные и складские кварталы набрали меньше "
                                          "мест схемы (одноэтажные корпуса 13,6 м, высоты до 49 м у аэродрома), остаток цели "
                                          + f"{JOBS_T:,}".replace(",", " ") + " мест — в жилые зоны"))
LOG.append({"what": "плотности по тому, что набрали кварталы", "zones": len(HELD), "FR": round(FR, 3), "FH2": round(FH2, 3),
            "village_jobs": VILLAGE_JOBS, "fit": bool(FIT["zones"])})
for z in ZONES:
    if z["use"] in SKIP:
        continue
    r = z["rules"]
    m2j = 100.0 if z["use"] in ("logistics", "industry") else (50.0 if z["use"] == "medical" else 90.0)
    need = ((r.get("homes_per_ha") or 0) * 75.0 + (r.get("jobs_per_ha") or 0) * m2j) / 1e4
    if r.get("far") is not None and need * 1.25 > r["far"]:
        r["far"] = round(need * 1.25 + 0.05, 1)
        fl = r.get("floors") or [3, 9]
        top = max(fl[1], int(math.ceil(r["far"] / 0.28)))
        if z["use"] in ("logistics", "industry"):
            top = fl[1]
        cap = r.get("height_cap_m") or 0
        r["floors"] = [fl[0], min(top, 25, int(max(cap, 1) // 3.4) if z["_base"] != "z_centre_main" else 16)]
homes = sum(NETHA[z["id"]] * (z["rules"].get("homes_per_ha") or 0) for z in ZONES if z["use"] not in SKIP)
jobs = sum(NETHA[z["id"]] * (z["rules"].get("jobs_per_ha") or 0) for z in ZONES if z["use"] not in SKIP)
TARGETS = {"homes_2050": int(round(homes, -1)), "population_2050": int(round(homes * RES_PER_HOME, -2)),
           "jobs_2050": int(round(jobs + VILLAGE_JOBS, -2)), "home_m2": 75.0,
           "plan_row": {"population_2050": POP_PLAN, "jobs_2050": JOBS_PLAN},
           "source": V0["targets"]["source"] + ("; уровень 2: плотности схемы (homes_per_ha = residents_per_ha / 2,5, jobs_per_ha) "
                                                "умножены на общий коэффициент (квартиры ×%.3f, места делового и смешанного центров ×%.3f) "
                                                "так, чтобы плотность × чистая площадь кварталов (без красных линий и полосы ЛРТ) дала "
                                                "цель; деловые, смешанные, промышленные и складские зоны — по тому, что набрали их "
                                                "кварталы (growing_e_fit.json), остаток мест — в жилые зоны (×%.3f), остаток квартир "
                                                "смешанных центров — в жилые (×%.3f); места в новых соцобъектах сёл (%d) входят в цель, "
                                                "существующие дома сёл — сверх цели" % (FH, FJ, FR, FH2, VILLAGE_JOBS))}
LOG.append({"what": "плотности под цели", "FH": round(FH, 3), "FJ": round(FJ, 3), "FR": round(FR, 3), "FH2": round(FH2, 3),
            "homes": round(homes), "jobs": round(jobs), "village_jobs": VILLAGE_JOBS})

# ===================================================================================================== 7. objects
OBJ = []
v0obj = {o["registry_id"]: o for o in V0["objects"]}


def rname(rid):
    return REG[rid]["name_ru"] if rid in REG else v0obj.get(rid, {}).get("name_ru", rid)


def obj(rid, action, frm, to, accuracy, why, *, name_ru=None, basis="по правилу", **kw):
    o = {"registry_id": rid, "name_ru": name_ru or rname(rid), "action": action, "from": frm, "to": to,
         "yaw": kw.pop("yaw", None), "accuracy": accuracy, "why": why, "basis": basis}
    fp = kw.pop("footprint", None)
    if fp is not None:
        g = fp if isinstance(fp, Polygon) else Polygon(fp)
        g = g.buffer(0)
        if g.geom_type == "MultiPolygon":
            g = max(g.geoms, key=lambda q: q.area)
        o["footprint"] = poly_pts(g)
        o["lot_m2"] = round(g.area)
    for k, v in kw.items():
        if v is not None:
            o[k] = v
    OBJ.append(o)
    return o


def zone_net(zid):
    g = unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES if z["_base"] == zid]).difference(RED).buffer(0)
    if g.is_empty:
        return None
    return max(getattr(g, "geoms", [g]), key=lambda q: q.area)


# --- landmark lots of the twin models (no buildings by rule: Unity stands the model)
for rid, P in PAD_FP.items():
    o0 = v0obj.get(rid, {})
    c = P.centroid
    moved = [m for m in MOVED if m[0] == rid]
    x0, z0 = PADS[rid][0], PADS[rid][1]
    if rid == "mars_petcare":
        # from the scheme's lot at km 40 (the previous spec's point), by the owner's decision
        MOVED[:] = [m for m in MOVED if m[0] != rid] + [(rid, o0.get("to"), [round(c.x, 1), round(c.y, 1)], MARS_WHY)]
        obj(rid, "move", o0.get("to"), [round(c.x, 1), round(c.y, 1)], o0.get("accuracy", "none"),
            MARS_WHY + f"; участок — площадка модели {PADS[rid][2]:.0f} × {PADS[rid][3]:.0f} м с запасом {PAD_MARGIN:.0f} м "
            "(LandmarkData), без зданий по правилу", basis="по правилу", kind="landmark", footprint=P, yaw=PADS[rid][4],
            years=Y4(2026, "industry"))
        continue
    obj(rid, "keep" if not moved else "move", [x0, z0] if moved else None, [round(c.x, 1), round(c.y, 1)], o0.get("accuracy", "none"),
        (o0.get("why") or "точка двойника (модель)") + f"; участок — площадка модели {PADS[rid][2]:.0f} × {PADS[rid][3]:.0f} м с запасом "
        f"{PAD_MARGIN:.0f} м (LandmarkData), без зданий по правилу" + (f"; {moved[0][3]}" if moved else ""),
        basis="по правилу", kind="landmark", footprint=P, yaw=PADS[rid][4], years=Y4(2026, "industry") if rid != "ps_arna_twin" else Y4(2026),
        chip="модель")
for rid, zid in ZONE_LOT.items():
    o0 = v0obj[rid]
    P = zone_net(zid)
    if P is None:
        LOG.append({"what": "зона участка модели пуста", "id": rid, "zone": zid,
                    "zones": [(z["id"], z["area_ha"]) for z in ZONES if z["_base"] == zid]})
        print("EMPTY zone lot", rid, zid, [(z["id"], z["area_ha"]) for z in ZONES if z["_base"] == zid], flush=True)
        continue
    c = P.representative_point() if not P.contains(Point(o0["to"])) else Point(o0["to"])
    obj(rid, o0["action"], o0.get("from"), [round(c.x, 1), round(c.y, 1)], o0.get("accuracy"),
        o0["why"] + f"; участок — вся зона {zid} без красных линий ({P.area / 1e4:.1f} га), модель двойника без зданий по правилу",
        basis="по источнику" if rid == "mars_petcare" else "по правилу", kind="landmark", footprint=P, yaw=o0.get("yaw"),
        years=Y4(2026 if rid == "mars_petcare" else 2028, "industry"), chip="модель" if rid == "gtes_doosan" else None)
# --- Жетыген: new public buildings on free land of the village centre (by rule, «модель qTwin»)
VILL_FREE = N.VILL.difference(RED).buffer(0)
shapely.prepare(VILL_FREE)
_AV = unary_union([RED.buffer(2.0), N.WATER_STRIP, N.RAIL.buffer(30.0)])
shapely.prepare(_AV)
PL_PP = _LN.v("clinics.polyclinic_plot")
PLOTS = {}
for rid, kind, m2, cap, yr, rad in (
        ("polyclinic_250", "polyclinic", None, {"visits_per_shift": 250}, 2032, 900.0),
        ("gov_buildings_zhetygen", "business", 5000.0, None, 2030, 900.0),
        ("house_of_culture_zhetygen", "culture", 5000.0, None, 2033, 900.0),
        ("sport_complex_zhetygen", "sport_ground", 10000.0, None, 2034, 1200.0)):
    o0 = v0obj[rid]
    if m2 is None:
        m2 = max(5000.0, float(PL_PP["ha_per_100_visits"]) * 2.5 * 1e4)
    wd = math.sqrt(m2 * 1.25)
    hd = m2 / wd
    P, at = fit(lambda a, b: box(a - wd / 2, b - hd / 2, a + wd / 2, b + hd / 2), o0["to"][0], o0["to"][1], VILL_FREE, _AV,
                step=15.0, rmax=rad, extra=list(PLOTS.values()))
    if P is None:
        LOG.append({"what": "участок объекта в селе не найден: точка без участка", "id": rid})
        obj(rid if rid != "polyclinic_250" else "polyclinic_250_zhetygen", "add", None, o0["to"], o0["accuracy"], o0["why"],
            basis="по правилу", registry_row=rid if rid == "polyclinic_250" else None)
        continue
    PLOTS[rid] = P
    oid = rid if rid != "polyclinic_250" else "polyclinic_250_zhetygen"
    why = (MODEL + f": {o0['why']}; участок {m2 / 1e4:.1f} га на свободной земле села (без домов и красных линий) в "
           f"{math.dist(at, o0['to']):.0f} м от точки схемы")
    if rid == "polyclinic_250":
        why += ("; строка реестра polyclinic_250 — две точки (Жетыген и Коянкус), Gate ставит поликлинику Коянкуса под этим id, "
                "здесь — свой id polyclinic_250_zhetygen (spec_issues: «growing_e завести свой id»)")
    if math.dist(at, o0["to"]) > 1.0:
        MOVED.append((oid, list(o0["to"]), [round(at[0], 1), round(at[1], 1)],
                      "точка схемы стоит на домах или улицах села — участок на ближайшей свободной земле центра посёлка"))
    obj(oid, "add", None, [round(at[0], 1), round(at[1], 1)], o0["accuracy"], why, basis="по правилу", kind=kind, footprint=P,
        years=Y4(yr, "social"), capacity=cap, registry_row="polyclinic_250" if rid == "polyclinic_250" else None,
        name_ru=rname(rid) + (" — Жетыген" if rid == "polyclinic_250" else ""))
# the house of culture is the twin's typical model (culture_typical, 4 floors, 20 m: run 3, rule 16 at (7943, 8240)); the
# village zone it stands in keeps 9 m for its houses (no new houses there) and takes 20 m for the public building
for rid, P in PLOTS.items():
    if rid != "house_of_culture_zhetygen":
        continue
    for z in ZONES:
        if z["use"] == "village_existing" and Polygon(z["polygon"]).buffer(0).intersection(P).area > 0.5 * P.area:
            z["rules"]["height_cap_m"] = max(z["rules"].get("height_cap_m") or 0, 20)
            z["why"] = z["why"] + "; потолок 20 м — для Дома культуры (типовая модель двойника, 4 этажа); новых домов в селе нет"
            SCHEME_CHANGES.append((z["id"], "потолок высоты 9 → 20 м: Дом культуры Жетыгена (типовая модель 20 м) в центре посёлка; "
                                            "дома села остаются как есть, новых жилых домов в зоне нет"))
# --- the rest of the level-0 objects as they were (markers: existing objects, rows that are zones or lines), less the rows
# another district owns (spec_issues w42)
DROP = {"pepsico": "строку снять (spec_issues): завод ставит Gate на корпусе OSM",
        "tlc_zhetygen": "строку снять (spec_issues): ТЛЦ лежит на 74 % в Green, ставит Green (keep)",
        "airfield_zhetygen": "одна точка — КТА zhetygen_mil в city.json, владелец Green; здесь — только радиусы правила 16"}
have = {o["registry_id"] for o in OBJ} | set(PLOTS)
for o in V0["objects"]:
    rid = o["registry_id"]
    if rid in have:
        continue
    if rid in DROP:
        SCHEME_CHANGES.append((rid, DROP[rid]))
        continue
    d = {"registry_id": rid, "name_ru": o["name_ru"], "action": o["action"], "from": o.get("from"), "to": o.get("to"),
         "yaw": o.get("yaw"), "accuracy": o.get("accuracy"), "why": o.get("why"),
         "basis": "по правилу" if o["action"] == "by_rule" else "по источнику"}
    if rid == "road_growing_10km":
        d["why"] = ("по правилу = первая очередь Центральной магистрали (улица s_central): от развязки А-3 км 46 через центр и "
                    "путепровод над Турксибом в промпояс, 10,5 км")
    if rid in ("settlement_zhetygen", "settlement_zarechnoe"):
        d["why"] = (o.get("why") or "") + "; точка — у growing_e, Green берёт её же (spec_issues)"
    OBJ.append(d)
for rid, r in REG.items():
    mine = "growing_e" in (r.get("district_area"), r.get("scheme_spec"), r.get("scheme_area")) or \
           (r.get("scheme_conflict") or {}).get("owner") == "growing_e"
    if mine and rid not in {x["registry_id"] for x in OBJ} | {x.get("registry_row") for x in OBJ}:
        LOG.append({"what": "строка реестра без объекта", "id": rid})

# ===================================================================================================== 8. corridors (overhead lines)
KV_OSM = {"235a7bfa": (220, "OSM voltage=220000 (w835540724, Overture source_tags), реестр hv_lines_220 «ЛЭП 220 кВ»"),
          "83f0e91a": (220, "OSM voltage=220000 (w486242428, Overture source_tags), реестр hv_lines_220 «ЛЭП 220 кВ»")}
KV_MINOR = (10, MODEL + ": OSM power=minor_line (распределительная сеть на опорах) без voltage — класс 1–20 кВ, охранная зона 10 м")
KV_LINE = (110, MODEL + ": OSM power=line без voltage — принят 110 кВ, охранная зона 20 м")

# ===================================================================================================== 9. axes, joints, phases
axes = copy.deepcopy(V0["axes"])
REF_FIX = {"J082": "J055", "J083": "J056", "J084": "J057", "J093": "J067", "J097": "J068", "J098": "J100", "J099": "J100",
           "J106": "J069", "J109": "J073", "J110": "J073", "J117": "J076", "J118": "J076", "J120": "J119", "J121": "J119",
           "J122": "J078", "J126": "J037"}
REF_DROP = {"J080", "J081", "J094", "J095", "J101", "J102", "J103", "J113", "J114", "J115", "J116", "J124", "J125"}


def fix_refs(v):
    if isinstance(v, str):
        return REF_FIX.get(v, v)
    if isinstance(v, list):
        return [fix_refs(x) for x in v if not (isinstance(x, str) and x in REF_DROP)]
    if isinstance(v, dict):
        return {k: fix_refs(x) for k, x in v.items()}
    return v


axes = fix_refs(axes)
for a_ in axes:
    if a_["id"] == "ax_lrt":
        a_["line"] = [P1(p) for p in LRT_PTS[::max(1, len(LRT_PTS) // 40)]] + [P1(LRT_PTS[-1])]
    if a_["id"] == "ax_lrt_west":
        a_["line"] = [P1(p) for p in BR_PTS[::max(1, len(BR_PTS) // 20)]] + [P1(BR_PTS[-1])]
GJ = [j for j in CITY["joints"]["items"] if "growing_e" in (j.get("between") or [])]
JOINTS = [{"joint_id": j.get("id"), "x": j["x"], "z": j["z"], "kind": j.get("kind"), "between": j.get("between"), "line": j.get("line")}
          for j in GJ]
PHASES = fix_refs(copy.deepcopy(V0["phases"]))
_zids = {z["_base"] for z in ZONES}
for ph in PHASES:
    ph["zones"] = [z for z in ph.get("zones", []) if z in _zids]

# ===================================================================================================== 10. spec
STREETS_OUT = []
for s in N.STREETS:
    d = {k: v for k, v in s.items() if not k.startswith("_")}
    q = [list(map(float, d["line"][0]))]
    for pt in d["line"][1:]:
        if math.dist(pt, q[-1]) > 0.05:
            q.append(list(map(float, pt)))
    d["line"] = q
    if len(q) < 2:
        LOG.append({"what": "улица из одной точки после разрезки: не пишется", "id": d["id"]})
        continue
    STREETS_OUT.append(d)
SIDS = {s["id"] for s in STREETS_OUT}
NODES_OUT = []
for n in N.NODES.values():
    d = copy.deepcopy(n)
    d["streets"] = [x for x in d["streets"] if x in SIDS]
    if not d["streets"] and not d["params"].get("keep_existing"):
        continue
    NODES_OUT.append(d)
ZONES_OUT = [{k: v for k, v in z.items() if not k.startswith("_")} for z in ZONES]
replaced = sorted(set(N.RETIRED))

spec = {
    "district": "growing_e", "version": 1, "level": 2,
    "made_by": "w53 tools/map/district/growing_e_build.py (весь район Growing-восток)",
    "boundary": "city.json#districts/growing_e",
    "attribution": C.ATTRIBUTION,
    "area": [P1(p) for p in list(DIST.exterior.coords)[:-1]],
    "area_ha": round(DIST.area / 1e4, 1),
    "targets": TARGETS,
    "centres": V0["centres"],
    "axes": axes,
    "zones": ZONES_OUT,
    "lrt": LRT,
    "objects": OBJ,
    "phases": PHASES,
    "joints": JOINTS,
    "edge_joints": [],
    "streets": STREETS_OUT,
    "nodes": NODES_OUT,
    "keep": [],
    "views": [],
    "utilities": [],
    "corridors": None,
    "replaced_osm": replaced,
    "replaced_why": {k: N.RETIRED_WHY.get(k, "") for k in replaced},
    "scheme_changes": [{"id": k, "why": v} for k, v in SCHEME_CHANGES + Z.SCHEME_CHANGES],
    "moved": [{"id": k, "from": a, "to": b, "why": w} for k, a, b, w in MOVED],
    "checks": {},
}
_tmp = {k: v for k, v in spec.items() if k != "corridors"}
CORR = []
for c in LU.corridors(copy.deepcopy(_tmp)):
    if not str(c.get("source", "")).startswith("osm:"):
        continue
    short = c["source"][4:12]
    kv, basis = KV_OSM.get(short) or (KV_MINOR if c.get("osm_class") == "minor_line" else KV_LINE)
    CORR.append({**c, "kv": kv, "kv_basis": basis})
spec["corridors"] = CORR
LOG.append({"what": "ВЛ в коридорах spec с напряжением", "n": len(CORR), "kv": sorted({(c["id"], c["kv"]) for c in CORR})})

if __name__ == "__main__":
    import growing_e_check as CHK
    res = CHK.run(spec, verbose=False)
    spec["checks"] = res
    spec["checks"]["build_log"] = LOG[:600]
    txt = json.dumps(spec, ensure_ascii=False, indent=1)
    with open(SPEC_OUT + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")
    os.replace(SPEC_OUT + ".tmp", SPEC_OUT)
    from collections import Counter
    print(f"wrote {SPEC_OUT}: {len(txt) // 1024} KB; streets {len(STREETS_OUT)}, nodes {len(NODES_OUT)}, zones {len(ZONES_OUT)}, "
          f"objects {len(OBJ)}; {time.time() - T0:.1f} s")
    print("targets", {k: TARGETS[k] for k in ("homes_2050", "population_2050", "jobs_2050")}, "FH %.3f FJ %.3f FR %.3f FH2 %.3f held %d" % (FH, FJ, FR, FH2, len(HELD)))
    print("log", Counter(x["what"] for x in LOG))
    if "--no-check" not in sys.argv:
        ok = CHK.main([SPEC_OUT])
        sys.exit(0 if ok else 1)
