"""Road rules 5–11 (w43). Texts in spec/rules.json, numbers from spec/norms.json by key.

Years: a rule looks at what stands in each check year (base scenario, segment years[0]); an issue is reported once,
for the first year it appears in. Rule 5 also looks at every year between the check years in which the network
changes, so a dead end that stands for one year only is caught.
"""
import math
import os
import sys

import numpy as np

_MAP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MAP not in sys.path:
    sys.path.insert(0, _MAP)
from lib import geom as G  # noqa: E402
from lib import model, rail  # noqa: E402
from lib import years as Y  # noqa: E402

URBAN = {"arterial_road_regulated", "arterial_regulated", "district_transport", "district_pedestrian", "local",
         "local_secondary", "industrial"}
NO_SIDEWALK = {"expressway", "arterial_continuous", "ramp"}
FAST = {"expressway", "arterial_continuous"}
NOT_JUNCTION = {"diverge", "merge", "ic", "joint", "end", "edge"}
AXIS_CLASS = {"expressway": "expressway", "arterial": "arterial_regulated", "district": "district_transport",
              "local": "local", "pedestrian": "pedestrian_street", "boulevard": "boulevard"}


# ------------------------------------------------------------------ shared network view
class Net:
    def __init__(self, ctx):
        n = ctx.network
        self.nodes = {d["id"]: d for d in n["nodes"]}
        self.segs = n["segments"]
        self.prof = n.get("profiles", {})
        self.ics = {i["id"]: i for i in n.get("interchanges", [])}
        self.P = [np.array([p[:2] for p in s["pts"]], float) for s in self.segs]
        self.Y = [np.array([p[2] for p in s["pts"]], float) for s in self.segs]
        self.S = [G.chainage(P) for P in self.P]
        self.at = {}
        for k, s in enumerate(self.segs):
            self.at.setdefault(s["a"], []).append((k, 0))
            self.at.setdefault(s["b"], []).append((k, 1))

    def standing(self, k, year):
        return int(self.segs[k]["years"][0]) <= year

    def first_year(self, k):
        return int(self.segs[k]["years"][0])

    def tangent_out(self, k, end, L=6.0):
        """Unit direction leaving the node along segment k (end 0 = a, 1 = b), measured over L m."""
        P, S = self.P[k], self.S[k]
        if end == 0:
            q = G.point_at(P, min(L, S[-1]), S)
            v = q - P[0]
        else:
            q = G.point_at(P, max(0.0, S[-1] - L), S)
            v = q - P[-1]
        n = math.hypot(*v)
        return v / n if n > 1e-9 else v

    def struct_at(self, k, s):
        for r in self.segs[k]["struct"]:
            if r["from_m"] - 0.5 <= s <= r["to_m"] + 0.5 and r["kind"] != "ground":
                return r["kind"]
        return "ground"


def _net(ctx):
    if getattr(ctx, "_roads_net", None) is None:
        ctx._roads_net = Net(ctx)
    return ctx._roads_net


DECK = ("overpass", "bridge")
AS_OSM = " (существующая дорога 2025: как в OSM)"


def _existing(net, *ks):
    """All the segments are existing roads (base year ≤ 2025): their defect is the source's, kept as in OSM."""
    return all(int(net.segs[k]["years"][0]) <= Y.EXISTING[0] for k in ks)


def _rail_x(ctx):
    """Crossings of the segments with the railway tracks (lib.rail: no tunnels, metro or abandoned lines):
    [(k, s, point, angle, track)]; a track on a bridge passes over the road and is left out."""
    if getattr(ctx, "_rail_x", None) is not None:
        return ctx._rail_x
    import shapely
    net = _net(ctx)
    tr = [t for t in rail.tracks(ctx.area, 50.0) if not t["up"]]
    out = []
    if tr:
        tree = shapely.STRtree([shapely.LineString(t["P"]) for t in tr])
        for k, P in enumerate(net.P):
            for j in tree.query(shapely.LineString(P)):
                t = tr[int(j)]
                for s1, _, pt, ang in G.crossings(P, t["P"]):
                    out.append((k, float(s1), pt, ang, t))
    ctx._rail_x = out
    return out


def _lrt_forbidden_x(ctx):
    """Crossings of a ground section of the LRT (lrt.json, sections as built) with a segment of a class the LRT may not
    cross at grade (norms.lrt_crossing_allowed) where the segment is in one level (no deck, no tunnel there):
    [(k, s, point, line)]."""
    import shapely
    net = _net(ctx)
    out, tree = [], None
    for ln in (ctx.lrt or {}).get("lines", []):
        P = np.array([q[:2] for q in ln.get("pts") or []], float)
        if len(P) < 2:
            continue
        ground = [(r["from_m"], r["to_m"]) for r in ln.get("sections", []) if r["kind"] == "ground"]
        if tree is None:
            tree = shapely.STRtree([shapely.LineString(Q) for Q in net.P])
        for k in tree.query(shapely.LineString(P)):
            k = int(k)
            if ctx.N.lrt_crossing_allowed(net.segs[k]["class"]):
                continue
            for sa, s1, pt, ang in G.crossings(P, net.P[k]):
                if not any(a - 1e-6 <= sa <= b + 1e-6 for a, b in ground):
                    continue
                kind = net.struct_at(k, s1)
                if kind in DECK or kind == "tunnel":
                    continue
                out.append((k, float(s1), pt, ln))
    return out


def _change_years(ctx, net):
    """The stage years and every year between the first and the last of them in which a segment is built (base): a
    carriageway end that stands blind for one year between two stage years is a dead end too."""
    lo, hi = min(ctx.years), max(ctx.years)
    return sorted(set(ctx.years) | {int(s["years"][0]) for s in net.segs if lo <= int(s["years"][0]) <= hi})


# ------------------------------------------------------------------ rule 5: dead ends
def rule5(ctx):
    net = _net(ctx)
    allowed = set(ctx.norm("validator.dead_end_allowed_classes")["classes"])
    dmax = float(ctx.norm("fire_access.dead_end_max_m"))
    out = []
    seen = set()
    for year in _change_years(ctx, net):
        deg = {}
        for k, s in enumerate(net.segs):
            if not net.standing(k, year):
                continue
            for nid in (s["a"], s["b"]):
                deg[nid] = deg.get(nid, 0) + 1
        for nid, dg in deg.items():
            if dg != 1 or nid in seen:
                continue
            nd = net.nodes[nid]
            if nd["kind"] in ("joint", "edge"):
                continue
            k, e = next((k, e) for k, e in net.at[nid] if net.standing(k, year))
            cls = net.segs[k]["class"]
            # length of the dead-end branch: walk to the first node with ≥ 3 standing segments
            L, cur, kk, ee = 0.0, nid, k, e
            for _ in range(200):
                L += net.S[kk][-1]
                other = net.segs[kk]["b"] if ee == 0 else net.segs[kk]["a"]
                nxt = [(k2, e2) for k2, e2 in net.at[other] if k2 != kk and net.standing(k2, year)]
                if len(nxt) != 1:
                    break
                kk, ee = nxt[0]
                cur = other
            seen.add(nid)
            p = net.P[k][0] if e == 0 else net.P[k][-1]
            when = f" в {year}" if year < max(ctx.years) and dg == 1 and deg_final(net, nid) > 1 else ""
            if cls in allowed and L <= dmax:
                continue
            why = (f"класс {cls} не может кончаться тупиком" if cls not in allowed
                   else f"тупик {L:.0f} м длиннее {dmax:.0f} м (fire_access.dead_end_max_m)")
            existing = int(net.segs[k]["years"][0]) <= 2025
            if existing:
                why += " (существующая дорога 2025: как в OSM)"
            out.append(ctx.issue(5, "warning" if existing else "error", p[0], p[1], f"дорога обрывается{when}: {why}",
                                 [net.segs[k]["id"], nid]))
    return out + _dead_ends_to_nowhere(ctx, net)


CARLESS = {"pedestrian_street", "boulevard", "path", "footway", "cycleway"}


def _dead_ends_to_nowhere(ctx, net):
    """Final year: a dead-end branch of a street (from its free end to the first junction) that nothing uses — no building
    within setbacks.building_line_max_m of its carriageway, no lot with a use entered from it, no drive tied to it — is a road
    to nowhere (a warning: a turnaround or a link to cut, or houses still to come). A lot counts with or without buildings
    when it holds a facility or registry object or has any planned use (a substation lot, a park, a school plot not yet
    built); only reserve land with no use does not."""
    import shapely
    from shapely.geometry import LineString
    if not ctx.buildings:
        return []
    year = max(ctx.years)
    lim = float(ctx.norm("setbacks.building_line_max_m")["max_from_carriageway"])
    fps = [b["footprint"] for b in ctx.buildings.get("buildings", []) if b.get("footprint") and len(b["footprint"]) >= 3
           and int(b["years"][0]) <= year]
    tree = shapely.STRtree([shapely.Polygon([q[:2] for q in f]) for f in fps]) if fps else None
    built = {b.get("lot") for b in ctx.buildings.get("buildings", []) if int(b["years"][0]) <= year}
    used = {l.get("access") for l in (ctx.lots or {}).get("lots", []) if l["id"] in built or _lot_in_use(l, year)}
    used |= {(n.get("attach") or {}).get("segment") for n in (ctx.driveways or {}).get("nodes", [])}
    deg = {}
    for k, s in enumerate(net.segs):
        if net.standing(k, year):
            for nid in (s["a"], s["b"]):
                deg[nid] = deg.get(nid, 0) + 1
    out = []
    for nid, dg in sorted(deg.items()):
        if dg != 1 or net.nodes[nid]["kind"] in ("joint", "edge"):
            continue
        k, e = next((k, e) for k, e in net.at[nid] if net.standing(k, year))
        if net.segs[k]["class"] in CARLESS:
            continue
        branch, kk, ee = [], k, e
        for _ in range(200):
            branch.append(kk)
            other = net.segs[kk]["b"] if ee == 0 else net.segs[kk]["a"]
            nxt = [(k2, e2) for k2, e2 in net.at[other] if k2 != kk and net.standing(k2, year)]
            if len(nxt) != 1 or nxt[0][0] in branch:
                break
            kk, ee = nxt[0]
        ids = [net.segs[j]["id"] for j in branch]
        if used & set(ids):
            continue
        reach = 0.0
        geoms = []
        for j in branch:
            pr = net.prof.get(net.segs[j]["pid"]) or {}
            half = (sum(pr.get("lanes", [1, 1])) * pr.get("lane_w", 3.5) + pr.get("median_w", 0.0)) / 2.0
            geoms.append(LineString(net.P[j]).buffer(half + lim, cap_style="flat"))
            reach += net.S[j][-1]
        if tree is not None and len(tree.query(shapely.union_all(geoms), predicate="intersects")):
            continue
        p = net.P[k][0] if e == 0 else net.P[k][-1]
        out.append(ctx.issue(5, "warning", p[0], p[1], f"тупик {ids[0]} ({reach:.0f} м до развилки) без зданий: ни одного дома в {lim:.0f} м "
                             f"от проезжей части, ни участка с назначением, ни проезда с него — дорога никуда", ids[:6] + [nid]))
    return out


def _lot_in_use(lot, year):
    """A lot that a street serves with or without buildings: one standing by `year` that holds a facility or registry object
    or has any planned use; reserve land with no use does not count."""
    ys = lot.get("years") or [0]
    if int(ys[0]) > year:
        return False
    return bool(lot.get("registry_id") or lot.get("facility") or lot.get("facilities")
                or (lot.get("use") or "reserve") != "reserve")


def deg_final(net, nid):
    return len(net.at.get(nid, []))


# ------------------------------------------------------------------ rule 6: crossings without a node, 5+ arms
def _crossings(ctx):
    """All crossings of two segments that are not at a shared node: (k1, s1, k2, s2, point, dy)."""
    if getattr(ctx, "_roads_x", None) is not None:
        return ctx._roads_x
    import shapely
    net = _net(ctx)
    lines = [shapely.LineString(P) for P in net.P]
    tree = shapely.STRtree(lines)
    out = []
    a_idx, b_idx = tree.query(lines, predicate="intersects")
    for i, j in zip(a_idx, b_idx):
        if i >= j:
            continue
        si, sj = net.segs[i], net.segs[j]
        shared = {si["a"], si["b"]} & {sj["a"], sj["b"]}
        for s1, s2, pt, ang in G.crossings(net.P[i], net.P[j]):
            near_shared = any(np.hypot(pt[0] - net.nodes[n]["x"], pt[1] - net.nodes[n]["z"]) < 3.0 for n in shared)
            if near_shared:
                continue
            # ends touching (a segment end on the other one within 0.5 m of a node) are graph matters, not crossings
            if min(s1, net.S[i][-1] - s1) < 0.3 and min(s2, net.S[j][-1] - s2) < 0.3:
                continue
            y1 = float(np.interp(s1, net.S[i], net.Y[i]))
            y2 = float(np.interp(s2, net.S[j], net.Y[j]))
            out.append((i, s1, j, s2, pt, y1 - y2, ang))
    ctx._roads_x = out
    return out


def rule6(ctx):
    net = _net(ctx)
    clear = float(ctx.norm("bridges.road_clearance_m"))
    tol = model("same_level_tol_m")
    out = []
    for i, s1, j, s2, pt, dy, ang in _crossings(ctx):
        a, b = net.segs[i], net.segs[j]
        y0 = max(net.first_year(i), net.first_year(j))
        ids = [a["id"], b["id"]]
        if abs(dy) < max(tol, 1.0):
            out.append(ctx.issue(6, "error", pt[0], pt[1],
                                 f"{a['class']} и {b['class']} пересекаются в одном уровне без узла (с {y0})", ids))
        elif abs(dy) < clear:
            out.append(ctx.issue(6, ctx.sev("bridges.road_clearance_m"), pt[0], pt[1],
                                 f"пересечение без узла: разница отметок {abs(dy):.1f} м меньше габарита {clear:.1f} м", ids,
                                 lv=1))
        else:
            up = i if dy > 0 else j
            su = s1 if dy > 0 else s2
            if net.struct_at(up, su) not in ("overpass", "bridge"):
                lo = j if up == i else i
                if net.struct_at(lo, s2 if up == i else s1) != "tunnel":
                    out.append(ctx.issue(6, "error", pt[0], pt[1],
                                         f"{net.segs[up]['class']} проходит выше на {abs(dy):.1f} м без пролёта (struct не мост/путепровод)",
                                         ids, lv=1))
    # a road and a railway track cross only in different levels (crossing_matrix, rail): a new road in one level with
    # the track is an error, an existing level crossing (2025) stays as in OSM
    for k, s1, pt, ang, t in _rail_x(ctx):
        kind = net.struct_at(k, s1)
        if kind in DECK or kind == "tunnel":
            continue                    # rule 9 checks the clearance over the track
        sg = net.segs[k]
        old = _existing(net, k)
        what = (f"{sg['class']} пересекает ж/д {t['name'] or t['id'][:8]} в одном уровне: "
                + ("существующий переезд (как в OSM)" if old else "нужен путепровод или тоннель (struct в spec)"))
        out.append(ctx.issue(6, "warning" if old else "error", pt[0], pt[1], what, [sg["id"], t["id"]]))
    # the ground LRT and a road it may not cross at grade (a ramp, an expressway, a continuous arterial) in one level
    for k, s1, pt, ln in _lrt_forbidden_x(ctx):
        sg = net.segs[k]
        out.append(ctx.issue(6, "error", pt[0], pt[1], f"ЛРТ {ln['id']} на земле пересекает {sg['class']} в одном уровне: переезд "
                             f"здесь не допускается — нужна эстакада или тоннель (lrt.at_grade_crossing)", [sg["id"], ln["id"]]))
    # 5+ arms without a ring or square
    mx = int(ctx.norm("intersections.max_legs_without_ring"))
    for nid, uses in net.at.items():
        nd = net.nodes[nid]
        if len(uses) > mx and nd["kind"] not in ("roundabout", "square") and nd["kind"] not in ("ic", "diverge", "merge"):
            # every arm an existing 2025 road: the junction is OSM's, kept as it is (a warning); one new arm: an error
            old = _existing(net, *[k for k, _ in uses])
            out.append(ctx.issue(6, "warning" if old else "error", nd["x"], nd["z"],
                                 f"узел из {len(uses)} лучей без кольца или площади ({nd['kind']})" + (AS_OSM if old else ""),
                                 [nid]))
    return out


# ------------------------------------------------------------------ rule 7: ramps
def _ramp_chains(net):
    """Ramp ways rebuilt from ramp segments: chains through nodes where exactly two ramp segments meet."""
    rs = [k for k, s in enumerate(net.segs) if s["class"] == "ramp"]
    rset = set(rs)
    used = set()
    chains = []
    for k in rs:
        if k in used:
            continue
        chain = [(k, 0)]
        used.add(k)
        for end in (1, 0):
            cur, ce = k, end
            while True:
                nid = net.segs[cur]["b"] if ce == 1 else net.segs[cur]["a"]
                nxt = [(k2, e2) for k2, e2 in net.at[nid] if k2 != cur]
                ramps_here = [(k2, e2) for k2, e2 in nxt if k2 in rset]
                if len(nxt) != 1 or len(ramps_here) != 1 or ramps_here[0][0] in used:
                    break
                k2, e2 = ramps_here[0]
                used.add(k2)
                if end == 1:
                    chain.append((k2, e2))
                else:
                    chain.insert(0, (k2, 1 - e2))
                cur, ce = k2, 1 - e2
        chains.append(chain)
    return chains


def _chain_pts(net, chain):
    parts = []
    for k, e in chain:
        P = net.P[k] if e == 0 else net.P[k][::-1]
        parts.append(P)
    return G.concat(*parts)


def _chain_ends(net, chain):
    k0, e0 = chain[0]
    k1, e1 = chain[-1]
    a = net.segs[k0]["a"] if e0 == 0 else net.segs[k0]["b"]
    b = net.segs[k1]["b"] if e1 == 0 else net.segs[k1]["a"]
    return a, b


def rule7(ctx):
    net = _net(ctx)
    N = ctx.N
    amax = float(ctx.norm("ramps.merge_angle_max_deg"))
    term = ctx.norm("ramps.secondary_terminal_angle_deg")
    lr = ctx.norm("ramps.loop_radius_m")
    tbl = ctx.norm("ramps.speed_change_lanes_kz_m")
    sev_loop = ctx.sev("ramps.loop_radius_m")
    keep_ics = {k: v for k, v in net.ics.items() if (v.get("params") or {}).get("keep_existing")}
    out = []
    for chain in _ramp_chains(net):
        P = _chain_pts(net, chain)
        a, b = _chain_ends(net, chain)
        segs = [net.segs[k] for k, _ in chain]
        ids = [s["id"] for s in segs]
        ic = segs[0].get("ic")
        if ic in keep_ics:
            continue        # an existing interchange the spec keeps (params.keep_existing): checked against OSM below
        existing = all(int(s["years"][0]) <= 2025 for s in segs)
        sev = "warning" if existing else "error"
        tag = " (существующая развязка OSM)" if existing else ""
        tmpl = net.ics.get(ic, {}).get("template") if ic else None
        turn = abs(math.degrees(G.turn_total(P))) if len(P) > 2 else 0.0
        if a == b or turn > 330:
            out.append(ctx.issue(7, "error", P[0][0], P[0][1], f"съезд замкнут в круг{tag} (поворот {turn:.0f}°)", ids))
            continue
        for end, nid in ((0, a), (1, b)):
            nd = net.nodes[nid]
            others = [(k2, e2) for k2, e2 in net.at[nid] if k2 not in {k for k, _ in chain}]
            if not others:
                if nd["kind"] not in ("joint", "edge"):
                    out.append(ctx.issue(7, sev, nd["x"], nd["z"], f"съезд кончается не узлом{tag}", ids + [nid]))
                continue
            kk, ee = chain[0] if end == 0 else chain[-1]
            ee_node = ee if end == 0 else 1 - ee
            t_r = net.tangent_out(kk, ee_node)
            fast = [(k2, e2) for k2, e2 in others if net.segs[k2]["class"] in FAST]
            if len(others) == 1 and fast:
                # the ramp continues one carriageway end to end (a trumpet / directional stem roadway): no merge here
                t2 = net.tangent_out(*others[0])
                if float(np.dot(t_r, t2)) < -math.cos(math.radians(amax)):
                    continue
            minor = [(k2, e2) for k2, e2 in others if net.segs[k2]["class"] not in FAST and net.segs[k2]["class"] != "ramp"]
            if fast:
                # tangent junction: smallest angle to the carriageway's direction through the node
                best = 180.0
                for k2, e2 in fast:
                    t2 = net.tangent_out(k2, e2)
                    a_ = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(t_r, t2))))))
                    best = min(best, a_, 180.0 - a_)
                if best > amax + 0.05:
                    out.append(ctx.issue(7, sev, nd["x"], nd["z"],
                                         f"съезд примыкает к {net.segs[fast[0][0]]['class']} под {best:.1f}° (> {amax:.0f}°){tag}", ids + [nid]))
                # speed-change lane: alongside the carriageway (edge to edge) for the norm length
                k2 = fast[0][0]
                fast_cls = net.segs[k2]["class"]
                row = tbl["I-b_II"]
                need = float(row[1] if end == 0 else row[0])
                cw = (net.prof.get(net.segs[k2]["pid"]) or {})
                cw_w = (cw.get("lane_w", 3.75) * max(cw.get("lanes", [2, 0]))) if cw else 7.5
                lim = cw_w / 2.0 + 5.0 / 2.0 + 1.0
                Q = P if end == 0 else P[::-1]
                car = np.vstack([net.P[k2]] + [net.P[k3] for k3, _ in fast[1:]])
                Sq = G.chainage(Q)
                along = 0.0
                for s_, q in zip(Sq, Q):
                    if s_ > need * 2.5:
                        break
                    if G.project(car, q)[1] <= lim:
                        along = s_
                    else:
                        break
                if along < 0.6 * need:
                    out.append(ctx.issue(7, sev, nd["x"], nd["z"],
                                         f"нет переходно-скоростной полосы: вдоль {fast_cls} {along:.0f} м из {need:.0f} м "
                                         f"(ramps.speed_change_lanes_kz_m){tag}", ids + [nid]))
            elif minor and tmpl in ("diamond", "partial_cloverleaf"):
                k2, e2 = minor[0]
                t2 = net.tangent_out(k2, e2)
                jang = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(np.dot(t_r, t2)))))))   # 0…90°
                if jang < 180.0 - float(term["max"]) - 1e-6 or jang < float(term["min"]) - 1e-6:
                    out.append(ctx.issue(7, sev, nd["x"], nd["z"],
                                         f"съезд выходит на второстепенную дорогу под {jang:.0f}° (нужно {term['min']}–{term['max']}°){tag}",
                                         ids + [nid]))
        # loop radius
        if turn > 180:
            R = G.min_radius(P, 8.0)
            fast_major = any(net.segs[k2]["class"] == "expressway" for nid in (a, b) for k2, _ in net.at[nid])
            band = lr["roads_over_80_kmh"] if fast_major else lr["otherwise"]
            if R < float(band["min"]) - 1.0:
                out.append(ctx.issue(7, "warning" if existing else sev_loop, P[len(P) // 2][0], P[len(P) // 2][1],
                                     f"радиус петли {R:.0f} м меньше {band['min']} м (ramps.loop_radius_m){tag}", ids))
    return _sum_existing(ctx, net, out, " (существующая развязка OSM)") + _keep_existing(ctx, net, keep_ics)


KEEP_DEV_M = 0.5        # a road of a kept interchange may move this far off its OSM line (end snapping): a model parameter


def _keep_existing(ctx, net, keep_ics):
    """Interchanges the spec keeps as they exist (a spec node with params.keep_existing: true, the owner's rule that real
    objects stay as their source draws them): rule 7's norms are not applied; every road of params.osm_ids must be in the
    network on its OSM / Overture line (each point within KEEP_DEV_M, the length inside the area kept)."""
    if not keep_ics:
        return []
    import shapely
    from lib import jio, paths
    if getattr(ctx, "_osm_roads", None) is None:
        ctx._osm_roads = {f["properties"]["id"]: shapely.geometry.shape(f["geometry"]) for f in jio.load_geojson(paths.w34("osm", "roads.geojson"))}
    osm = ctx._osm_roads
    street_of = {str(st.get("source", "")).split(":", 1)[1]: st["id"] for st in (ctx.spec.get("streets") or [])
                 if str(st.get("source", "")).startswith("keep_existing:")}
    by_street, by_osm, src_ids = {}, {}, {}
    for k, s in enumerate(net.segs):
        by_street.setdefault(s.get("street"), []).append(k)
        src = str(s.get("source") or "")
        if src.startswith("osm:"):
            # one OSM id, or several joined by "+" (OSM pieces chained into one way)
            src_ids[k] = [i for i in src.split(":", 1)[1].split("+") if i]
            for i in src_ids[k]:
                by_osm.setdefault(i, []).append(k)
    out = []
    for ic, rec in sorted(keep_ics.items()):
        ids = list((rec.get("params") or {}).get("osm_ids") or [])
        bad, worst, n_ok = [], 0.0, 0
        for oid in ids:
            g = osm.get(oid)
            sid = street_of.get(oid)
            # the segments of its keep_existing street, and those built from this OSM id (their source); a segment of
            # its street built from other OSM ids only is another road's (an older network chained two pieces)
            ks = [k for k in (by_street.get(sid, []) if sid else []) if k not in src_ids or oid in src_ids[k]]
            ks = sorted(set(ks) | set(by_osm.get(oid, [])))
            if g is None:
                bad.append((f"дороги osm:{oid[:8]} нет в слое OSM", None, [ic]))
                continue
            inside = g.intersection(ctx.area).length
            if inside < 1.0:
                continue
            if not ks:
                c = g.intersection(ctx.area).representative_point()
                bad.append((f"дорога osm:{oid[:8]} ({sid or 'нет улицы spec keep_existing'}) не построена", (c.x, c.y), [ic] + ([sid] if sid else [])))
                continue
            dev, got = 0.0, 0.0
            for k in ks:
                many = [osm[i] for i in src_ids.get(k, []) if i in osm]
                if len(many) > 1:
                    # a segment over several chained OSM pieces: on their lines, and only its part on this one counts
                    d = shapely.distance(shapely.union_all(many), shapely.points(net.P[k]))
                    got += shapely.LineString(net.P[k]).intersection(g.buffer(KEEP_DEV_M)).length
                else:
                    d = shapely.distance(g, shapely.points(net.P[k]))
                    got += float(net.S[k][-1])
                dev = max(dev, float(d.max()))
            worst = max(worst, dev)
            if dev > KEEP_DEV_M or got < inside - 2.0 * KEEP_DEV_M - 0.01 * inside:
                k = ks[0]
                q = net.P[k][len(net.P[k]) // 2]
                bad.append((f"{net.segs[k]['class']} {sid} (osm:{oid[:8]}) не по OSM: отклонение до {dev:.1f} м (допуск {KEEP_DEV_M} м), "
                            f"длина {got:.0f} из {inside:.0f} м", (q[0], q[1]), [ic, sid] + [net.segs[k2]["id"] for k2 in ks[:4]]))
            else:
                n_ok += 1
        for what, xz, ids_ in bad:
            x, z = xz or (rec.get("x", 0.0), rec.get("z", 0.0))
            out.append(ctx.issue(7, "error", x, z, f"существующая развязка {ic} (params.keep_existing): {what}", ids_))
        out.append(ctx.issue(7, "info", rec.get("x", 0.0), rec.get("z", 0.0),
                             f"существующая развязка {ic} сохраняется как в OSM (spec: params.keep_existing): нормы съездов не применяются; "
                             f"{n_ok} из {len(ids)} дорог OSM на своих линиях (отклонение до {worst:.2f} м)", [ic]))
    return out


def _sum_existing(ctx, net, issues, tag):
    """Existing (OSM) interchanges are kept as they are: their deviations become one warning per interchange."""
    import re
    keep, groups = [], {}
    seg_ic = {s["id"]: s.get("ic") for s in net.segs}
    for i in issues:
        if not i["what_ru"].endswith(tag):
            keep.append(i)
            continue
        ic = next((seg_ic.get(x) for x in i["ids"] if seg_ic.get(x)), None) or "?"
        groups.setdefault(ic, []).append(i)
    kinds = [("угол примыкания", "съезд примыкает", "°"), ("переходно-скоростная полоса", "нет переходно-скоростной", " м"),
             ("радиус петли", "радиус петли", " м"), ("прочее", "", "")]
    for ic, its in groups.items():
        parts = []
        for name, pre, unit in kinds:
            sel = [i for i in its if i["what_ru"].startswith(pre)] if pre else \
                [i for i in its if not any(i["what_ru"].startswith(k[1]) for k in kinds[:-1])]
            if not sel:
                continue
            vals = []
            for i in sel:
                m = re.search(r"(?:под|вдоль \S+|петли) (\d+(?:\.\d+)?)", i["what_ru"])
                if m:
                    vals.append(float(m.group(1)))
            rng = f" {min(vals):g}–{max(vals):g}{unit}" if vals else ""
            parts.append(f"{name}{rng} ×{len(sel)}")
        rec = net.ics.get(ic, {})
        x = rec.get("x", its[0]["x"])
        z = rec.get("z", its[0]["z"])
        ids = [ic] + sorted({x_ for i in its for x_ in i["ids"] if x_ in seg_ic})[:12]
        keep.append(ctx.issue(7, "warning", x, z, f"существующая развязка OSM {ic}: {len(its)} отклонений съездов от норм "
                              f"({'; '.join(parts)}); у её узла spec нет params.keep_existing — оставить как в OSM или перестроить, "
                              f"решает spec", ids))
    return keep


# ------------------------------------------------------------------ rule 8: node types and spacing
def _cell_check(ctx, ca, cb, kind):
    m = ctx.N.matrix_cell(ca, cb)
    if m is None:
        return None
    if kind in m["allowed"]:
        return None
    for key in ("forbidden_at_grade", "forbidden_grade_separated"):
        f = m.get(key) or {}
        if kind in f.get("types", []):
            return f.get("severity", "error"), f.get("why", "")
    return "error", f"тип не в списке допустимых {m['allowed']}"


def _ic_classes(net, N, ic, axes):
    """Classes of the roads an interchange or ring joins, highest rank first, one per road: its major / minor street refs
    (a None ref names nothing), and the arms at the nodes of its own segments (ramps, ring arcs, segments of the ic) when
    the refs give fewer than two roads (net_rings writes minor None; five_arm_rings writes no major either)."""
    roads = {}
    for ref in (ic.get("major"), ic.get("minor")):
        if ref is None:
            continue
        ks = [k for k, s in enumerate(net.segs) if s.get("street") == ref and s["class"] != "ramp"]
        if ks:
            roads[ref] = net.segs[ks[0]]["class"]
        elif ref in axes:
            roads[ref] = AXIS_CLASS.get(axes[ref].get("class"), axes[ref].get("class"))
    if len(roads) < 2:
        own = set(ic.get("ramps") or []) | {s["id"] for s in net.segs if s.get("ic") == ic["id"]}
        for nid in dict.fromkeys(e for s in net.segs if s["id"] in own for e in (s["a"], s["b"])):
            for k, _ in net.at.get(nid, []):
                sg = net.segs[k]
                if sg["id"] in own or sg["class"] == "ramp":
                    continue
                roads.setdefault(sg.get("street") or ("~", sg["class"], sg.get("name_ru") or sg["id"]), sg["class"])
    return sorted(roads.values(), key=N.class_rank)


def rule8(ctx):
    net = _net(ctx)
    N = ctx.N
    out = []
    in_ic = set()
    axes = {a["id"]: a for a in ctx.spec.get("axes", [])}
    for ic in net.ics.values():
        cls = _ic_classes(net, N, ic, axes)
        # the road of the highest class against every other road of the node (a ring of five arms joins more than two)
        for c in dict.fromkeys(cls[1:]):
            r = _cell_check(ctx, cls[0], c, ic["template"])
            if r:
                sev, why = r
                out.append(ctx.issue(8, sev, ic["x"], ic["z"], f"узел {ic['template']} на {cls[0]} × {c}: {why}", [ic["id"]]))
    # at-grade junctions
    for nid, uses in net.at.items():
        nd = net.nodes[nid]
        if nd["kind"] in NOT_JUNCTION or len(uses) < 3:
            continue
        if nd.get("ic") and nd["kind"] not in ("roundabout", "square", "crossing", "crossing_signal", "right_in_right_out"):
            continue
        # the roads that meet: one street passing through is one road (its two segments); ramps alone with one
        # road are a ramp terminal (rule 7 checks those)
        roads = {}
        for k, _ in uses:
            sg = net.segs[k]
            if sg["class"] != "ramp":
                roads.setdefault(sg.get("street") or ("~", sg["class"], sg.get("name_ru") or sg["id"]), sg["class"])
        if len(roads) < 2:
            continue
        cls = sorted(roads.values(), key=N.class_rank)
        r = _cell_check(ctx, cls[0], cls[1], nd["kind"])
        if r and nd.get("lrt") and nd["kind"] == "crossing_signal":
            # an LRT level crossing has signals whatever the streets (lrt.at_grade_crossing): the streets' own default holds
            r = _cell_check(ctx, cls[0], cls[1], N.default_node(cls[0], cls[1]))
        if r:
            sev, why = r
            existing = all(int(net.segs[k]["years"][0]) <= 2025 for k, _ in uses)
            if existing:
                sev = "warning"
                why += " (существующий узел OSM)"
            out.append(ctx.issue(8, sev, nd["x"], nd["z"], f"узел {nd['kind']} на {cls[0]} × {cls[1]}: {why}", [nid]))
    # spacing of interchanges on expressways
    sp = ctx.norm("interchanges.spacing_expressway_m")
    dmin = float(sp["city_min"])
    ics = [ic for ic in net.ics.values() if ic["template"] not in ("grade_separation", "roundabout", "square")]
    for i, a in enumerate(ics):
        for b in ics[i + 1:]:
            d = math.hypot(a["x"] - b["x"], a["z"] - b["z"])
            if d < dmin and (set(filter(None, [a.get("major"), a.get("minor")])) & set(filter(None, [b.get("major"), b.get("minor")]))):
                out.append(ctx.issue(8, ctx.sev("interchanges.spacing_expressway_m"), (a["x"] + b["x"]) / 2, (a["z"] + b["z"]) / 2,
                                     f"развязки {a['id']} и {b['id']} в {d:.0f} м (меньше {dmin:.0f} м; ближе — только с C-D или параллельными съездами)",
                                     [a["id"], b["id"]]))
    return out


# ------------------------------------------------------------------ rule 9: bridges and overpasses
def rule9(ctx):
    net = _net(ctx)
    clear = float(ctx.norm("bridges.road_clearance_m"))
    depth = model("deck_depth_m")
    out = []
    for i, s1, j, s2, pt, dy, ang in _crossings(ctx):
        if abs(dy) < 1.0:
            continue                    # rule 6
        up, lo = (i, j) if dy > 0 else (j, i)
        under = abs(dy) - depth
        if under < clear - model("height_round_tol_m"):
            old = _existing(net, up, lo)
            out.append(ctx.issue(9, "warning" if old else ctx.sev("bridges.road_clearance_m"), pt[0], pt[1],
                                 f"низ пролёта {net.segs[up]['class']} над {net.segs[lo]['class']} {under:.2f} м (нужно ≥ {clear:.1f} м)"
                                 + (AS_OSM if old else ""), [net.segs[up]["id"], net.segs[lo]["id"]], lv=1))
    # over a railway track: the rail clearance from the rail head (the ground at the track) to the underside of the deck
    rclear = float(ctx.norm("bridges.rail_clearance_m"))
    for k, s1, pt, ang, t in _rail_x(ctx):
        if net.struct_at(k, s1) not in DECK:
            continue                    # rule 6: in one level or a tunnel
        under = float(np.interp(s1, net.S[k], net.Y[k])) - depth - float(ctx.h(pt[0], pt[1]))
        if under < rclear - model("height_round_tol_m"):
            old = _existing(net, k)
            out.append(ctx.issue(9, "warning" if old else ctx.sev("bridges.rail_clearance_m"), pt[0], pt[1],
                                 f"низ пролёта {net.segs[k]['class']} над ж/д {t['name'] or t['id'][:8]} {under:.2f} м (нужно ≥ {rclear:.1f} м)"
                                 + (AS_OSM if old else ""), [net.segs[k]["id"], t["id"]], lv=1))
    # spans: not lying on the ground, not ending in the air
    for k, s in enumerate(net.segs):
        P, Y_, S = net.P[k], net.Y[k], net.S[k]
        for r in s["struct"]:
            if r["kind"] not in ("overpass", "bridge"):
                continue
            m = (S >= r["from_m"]) & (S <= r["to_m"])
            if not m.any():
                continue
            g = np.array([ctx.h(x, z) for x, z in P[m]])
            old = _existing(net, k)
            sev, tail = ("warning", AS_OSM) if old else ("error", "")
            if s["struct"] and r["kind"] == "overpass" and float(np.max(Y_[m] - g)) < 1.0:
                q = P[m][len(P[m]) // 2]
                out.append(ctx.issue(9, sev, q[0], q[1], f"путепровод лежит на земле ({s['class']}){tail}", [s["id"]], lv=1))
            for e, at_end in ((0, r["from_m"] < 0.6), (1, r["to_m"] > S[-1] - 0.6)):
                if not at_end:
                    continue
                nid = s["a"] if e == 0 else s["b"]
                if len(net.at[nid]) == 1 and net.nodes[nid]["kind"] not in ("joint", "edge"):
                    q = P[0] if e == 0 else P[-1]
                    out.append(ctx.issue(9, sev, q[0], q[1], "мост / путепровод обрывается в воздухе" + tail, [s["id"], nid], lv=1))
    return out


# ------------------------------------------------------------------ rule 10: sidewalks and crossings
def rule10(ctx):
    net = _net(ctx)
    N = ctx.N
    out = []
    smax = float(ctx.norm("crossings.at_grade_spacing_regulated_m")["max"])
    seen_p = set()
    for k, s in enumerate(net.segs):
        cls = s["class"]
        p = net.prof.get(s["pid"]) or {}
        sw = p.get("sidewalk_w", [0, 0])
        if (cls, s["pid"]) in seen_p:
            continue
        seen_p.add((cls, s["pid"]))
        q = net.P[k][len(net.P[k]) // 2]
        if cls in URBAN:
            need = N._sp(cls, "sidewalk_m", 0) or 0
            if isinstance(need, dict):
                need = need.get("min", 0)
            sides = [sw[1]] if s["oneway"] else sw
            if any(float(x) + 1e-6 < float(need) for x in sides):
                out.append(ctx.issue(10, "error", q[0], q[1], f"профиль {s['pid']}: тротуар {sides} м меньше {need} м", [s["id"]]))
        elif cls in NO_SIDEWALK and any(float(x) > 0 for x in sw):
            out.append(ctx.issue(10, "error", q[0], q[1], f"на {cls} не должно быть тротуаров ({s['pid']})", [s["id"]]))
    # long runs without an at-grade node on regulated streets (no crossing for pedestrians); a street with sidewalks
    # passing over the segment is a grade-separated crossing and splits the run
    over = {}
    for i, s1, j, s2, pt, dy, ang in _crossings(ctx):
        if abs(dy) < 1.0:
            continue
        up, lo, s_lo = (i, j, s2) if dy > 0 else (j, i, s1)
        if net.segs[up]["class"] not in NO_SIDEWALK:
            over.setdefault(lo, []).append(s_lo)
    for k, s in enumerate(net.segs):
        if s["class"] not in ("arterial_regulated", "arterial_road_regulated", "district_transport"):
            continue
        L = _at_grade_run(net.S[k][-1], s["struct"], over.get(k, []))
        if L > smax * 1.05 and int(s["years"][0]) > 2025:
            q = net.P[k][len(net.P[k]) // 2]
            out.append(ctx.issue(10, ctx.sev("crossings.at_grade_spacing_regulated_m"), q[0], q[1],
                                 f"{s['class']}: {L:.0f} м без узла и перехода (шаг переходов ≤ {smax:.0f} м)", [s["id"]]))
    # pedestrian streets and boulevards: both ends at a street with sidewalks, a square or a joint
    for k, s in enumerate(net.segs):
        if s["class"] not in ("pedestrian_street", "boulevard"):
            continue
        for nid in (s["a"], s["b"]):
            nd = net.nodes[nid]
            others = [k2 for k2, _ in net.at[nid] if k2 != k]
            ok = nd["kind"] in ("joint", "edge", "square") or any(_walkable(net, N, k2) for k2 in others)
            if not ok:
                out.append(ctx.issue(10, "error", nd["x"], nd["z"], f"{s['class']} не связан с тротуаром или площадью на конце",
                                     [s["id"], nid]))
    return out


def _walkable(net, N, k):
    """A pedestrian street may end at a street with sidewalks, another pedestrian street / boulevard, or a shared
    street (a class whose norm profile has no sidewalks and is not motor-only: pedestrians walk on it, e.g. a village
    lane)."""
    s = net.segs[k]
    cls = s["class"]
    if cls in ("pedestrian_street", "boulevard") or cls in URBAN:
        return True
    sw = (net.prof.get(s["pid"]) or {}).get("sidewalk_w") or [0, 0]
    if any(float(x) > 0 for x in sw):
        return True
    if cls in NO_SIDEWALK or cls == "bike_path":
        return False
    base = N.profile(cls).get("sidewalk_w") or [0, 0]
    return all(float(x) == 0 for x in base)


def _at_grade_run(L, struct, splits=()):
    """Longest run of a segment that is at grade (not on an overpass, a bridge or in a tunnel), split at `splits`."""
    iv = [(r["from_m"], r["to_m"]) for r in struct if r["kind"] in ("overpass", "bridge", "tunnel")]
    iv += [(s, s) for s in splits]
    best, cur = 0.0, 0.0
    for a, b in sorted(iv):
        best = max(best, a - cur)
        cur = max(cur, b)
    return max(best, L - cur)


# ------------------------------------------------------------------ rule 11: carriageways and lanes
def rule11(ctx):
    net = _net(ctx)
    N = ctx.N
    out = []
    seen = set()
    for k, s in enumerate(net.segs):
        cls = s["class"]
        if cls in ("ramp", "pedestrian_street", "boulevard", "bike_path"):
            continue
        base = N.profile(cls)
        p = net.prof.get(s["pid"]) or {}
        q = net.P[k][len(net.P[k]) // 2]
        existing = int(s["years"][0]) <= 2025
        sev = "warning" if existing else "error"
        if base.get("carriageways") == 2 and not s["oneway"] and not s.get("ic"):
            out.append(ctx.issue(11, sev, q[0], q[1], f"{cls}: встречные полосы на одной проезжей части (норма — две)"
                                 + (" (существующая дорога)" if existing else ""), [s["id"]]))
        key = (cls, s["pid"])
        if key in seen:
            continue
        seen.add(key)
        if p and abs(float(p.get("lane_w", 0)) - float(base["lane_w"])) > 0.05 and not s.get("ic"):
            out.append(ctx.issue(11, "warning", q[0], q[1], f"{s['pid']}: ширина полосы {p['lane_w']} м вместо {base['lane_w']} м",
                                 [s["id"]]))
        lanes = p.get("lanes") or [0, 0]
        if base.get("carriageways") == 2 and s["oneway"] and max(lanes) < max(base["lanes"]) and not s.get("ic"):
            out.append(ctx.issue(11, sev, q[0], q[1], f"{s['pid']}: {max(lanes)} полос вместо {max(base['lanes'])}", [s["id"]]))
    return out + _ramp_lanes(ctx, net)


def _seg_lanes(net, sg, year):
    """Lanes of a segment's carriageway in `year` (base scenario): its `stages` from their years, else its profile."""
    pid = sg["pid"]
    for st in sg.get("stages") or []:
        if int(st["years"][0]) <= year:
            pid = st["pid"]
    return max((net.prof.get(pid) or {}).get("lanes") or [0])


def _ramp_lanes(ctx, net):
    """Spec interchange `ramps` {<ramp id or movement>: {lanes, from_year}}: every key found ramps
    (interchanges[].ramp_lanes, gen_network), and each of those carries the lanes from that year (its profile, or a
    segment `stages` profile from the year) to the last validator year."""
    out = []
    nodes = {n["id"]: n for n in ctx.spec.get("nodes") or []}
    last = max(ctx.years)
    k_of = {sg["id"]: k for k, sg in enumerate(net.segs)}
    for ic_id, ic in net.ics.items():
        nd = nodes.get(ic_id) or {}
        req = nd.get("ramps") or (nd.get("params") or {}).get("ramps") or {}
        got = {r["key"]: r for r in ic.get("ramp_lanes") or []}
        for key, want in req.items():
            r = got.get(key)
            if not r or not r.get("segments"):
                out.append(ctx.issue(11, "error", ic["x"], ic["z"], f"развязка {ic_id}: ramps «{key}» не нашёл съезда в сети "
                                     "(id улицы съезда или движение «дорога N → дорога W»)", [ic_id]))
                continue
            need = int(want.get("lanes") or 0)
            fy = want.get("from_year")
            y0 = int(fy[0] if isinstance(fy, (list, tuple)) else fy) if fy is not None else None
            for sid in r["segments"]:
                k = k_of.get(sid)
                if k is None:
                    continue
                sg = net.segs[k]
                y = max(int(sg["years"][0]), y0 or 0)
                for yy in sorted({y, last}):
                    have = _seg_lanes(net, sg, yy)
                    if have < need:
                        q = net.P[k][len(net.P[k]) // 2]
                        out.append(ctx.issue(11, "error", q[0], q[1], f"съезд {sid} развязки {ic_id}: {have} полос в {yy} г. вместо {need} "
                                             f"(spec ramps «{key}»)", [sid, ic_id]))
                        break
    return out


RULES = [
    {"no": 5, "key": "dead_end", "fn": rule5, "needs": ["network"]},
    {"no": 6, "key": "crossing_without_node", "fn": rule6, "needs": ["network"]},
    {"no": 7, "key": "ramps", "fn": rule7, "needs": ["network"]},
    {"no": 8, "key": "node_type", "fn": rule8, "needs": ["network"]},
    {"no": 9, "key": "bridges", "fn": rule9, "needs": ["network"]},
    {"no": 10, "key": "sidewalks_crossings", "fn": rule10, "needs": ["network"]},
    {"no": 11, "key": "carriageways", "fn": rule11, "needs": ["network"]},
]
