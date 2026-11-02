"""Rule 25 (w43): LRT lines from lrt.json against the roads in network.json and the buildings.

Each end is a depot or a terminus station (an end on the trial-area edge waits for the neighbour); a station is on the
axis (≤ lrt.station_axis_max_offset_m) and its platform lies between the cross streets (no street crosses the line at
the rail level inside the platform); station spacing lrt.station_spacing_km; the viaduct clears every road under it by
lrt.viaduct_clearance_over_road_m; the deck does not pass through a building; no grade above lrt.ramp_slope_max_pct
(over a chord of MODEL lrt_slope_base_m and between neighbouring vertices, less the 1 cm rounding of heights);
curve radius ≥ lrt.min_curve_radius_m and platform ≥ lrt.platform_length_m (analogue: warning).
Under decks (rule25_drives): a drive or turnaround pad under a street span, an LRT viaduct or a railway viaduct (spec
`rail`) keeps fire_access.arches.height_min_m clear; a street under a railway viaduct keeps bridges.road_clearance_m.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "gen"))
from lib import geom as G  # noqa: E402
from lib import model  # noqa: E402
from lib import rail as LR  # noqa: E402


def _lines(ctx):
    out = []
    for ln in (ctx.lrt or {}).get("lines", []):
        P = np.array(ln["pts"], float)
        if len(P) < 2:
            continue
        S = G.chainage(P[:, :2])
        out.append((ln, P, S))
    return out


def _kind_at(ln, s):
    for r in ln.get("sections", []):
        if r["from_m"] - 1e-6 <= s <= r["to_m"] + 1e-6:
            return r["kind"]
    return "ground"


def _crossings(ctx, P, S):
    """Road segments crossing the line: (chain on the line, y road, y rail, segment)."""
    out = []
    net = ctx.network
    if not net:
        return out
    import shapely
    ln = shapely.LineString(P[:, :2])
    for s in net["segments"]:
        Q = np.array(s["pts"], float)
        if len(Q) < 2 or not ln.intersects(shapely.LineString(Q[:, :2])):
            continue
        SQ = G.chainage(Q[:, :2])
        for sa, sb, pt, ang in G.crossings(P[:, :2], Q[:, :2]):
            out.append((sa, float(np.interp(sb, SQ, Q[:, 2])), float(np.interp(sa, S, P[:, 2])), s, pt))
    return out


def grade_excess(P, S, smax, base, tol):
    """Grades of a rail polyline [x, z, y] with chainage S: over every chord from a vertex to the first vertex at least
    `base` m further (a line shorter than that: end to end), and between neighbouring vertices (a short step); each
    height difference is taken less `tol` (two heights rounded to 1 cm), so rounding alone never exceeds smax.
    Returns None, or (vertex index of the worst, its grade as exported, its chord m, runs over smax, their length m)."""
    y = P[:, 2]
    n = len(S)
    i0 = np.arange(n - 1)
    j0 = i0 + 1
    j1 = np.searchsorted(S, S + base - 1e-9)
    ok = j1 < n
    i1, j1 = np.arange(n)[ok], j1[ok]
    if not len(i1):
        i1, j1 = np.array([0]), np.array([n - 1])
    I = np.concatenate([i0, i1])
    J = np.concatenate([j0, j1])
    L = np.maximum(S[J] - S[I], 1e-6)
    gr = np.maximum(np.abs(y[J] - y[I]) - tol, 0.0) / L
    bad = np.where(gr > smax + 1e-9)[0]
    if not len(bad):
        return None
    k = int(bad[np.argmax(gr[bad])])
    cover = np.zeros(n - 1, bool)
    for b in bad:
        cover[I[b]:J[b]] = True
    runs = int(np.sum(cover[1:] & ~cover[:-1]) + cover[0])
    length = float(np.sum(np.diff(S)[cover]))
    return int(I[k]), float(abs(y[J[k]] - y[I[k]]) / L[k]), float(L[k]), runs, length


def rule25(ctx):
    out = []
    N = ctx.N
    wait = (ctx.norm("validator.neighbour_wait") or {}).get("alone", "warning")
    wait_sev = "wait_neighbour" if wait == "warning" else wait
    clear = float(ctx.norm("lrt.viaduct_clearance_over_road_m"))
    deck = model("lrt_rail_over_deck_m")
    tol = model("height_round_tol_m")
    same = model("same_level_tol_m")
    smax = float(ctx.norm("lrt.ramp_slope_max_pct")) / 100.0
    off_max = float(ctx.norm("lrt.station_axis_max_offset_m"))
    sp = ctx.norm("lrt.station_spacing_km")
    plat_min = float(ctx.norm("lrt.platform_length_m")["min"])
    rmin = float(ctx.norm("lrt.min_curve_radius_m"))
    depots = {d["id"]: d for d in (ctx.lrt or {}).get("depots", [])}
    for ln, P, S in _lines(ctx):
        lid = ln["id"]
        L = float(S[-1])
        st_ids = {st["id"]: st for st in ln.get("stations", [])}
        # 1. ends
        ends = list(ln.get("ends") or [])
        ends += [None] * (2 - len(ends))
        for e, end in enumerate(ends[:2]):
            p = P[0] if e == 0 else P[-1]
            kind = (end or {}).get("kind")
            if kind == "joint":
                out.append(ctx.issue(25, wait_sev, p[0], p[1], f"ЛРТ {lid}: конец на границе участка — линия продолжается "
                                     f"у соседа ({(end or {}).get('to') or 'стык'}), «ждёт соседа»", [lid, end.get("id")]))
                continue
            if kind == "depot":
                if end.get("id") not in depots:
                    out.append(ctx.issue(25, ctx.sev("lrt.line_ends"), p[0], p[1],
                                         f"ЛРТ {lid}: конец — депо {end.get('id')}, но такого депо нет в lrt.json", [lid]))
                continue
            if kind == "terminus":
                st = st_ids.get(end.get("id"))
                if st is None:
                    # a terminus outside the line (the station is in the neighbour or the spec named it only)
                    out.append(ctx.issue(25, ctx.sev("lrt.line_ends"), p[0], p[1],
                                         f"ЛРТ {lid}: конечная {end.get('id')} не стоит на линии", [lid]))
                elif min(abs(st["chain_m"]), abs(L - st["chain_m"])) > st.get("platform_m", plat_min):
                    out.append(ctx.issue(25, ctx.sev("lrt.line_ends"), p[0], p[1],
                                         f"ЛРТ {lid}: конечная {st['id']} в {min(st['chain_m'], L - st['chain_m']):.0f} м "
                                         f"от конца линии", [lid, st["id"]]))
                continue
            out.append(ctx.issue(25, ctx.sev("lrt.line_ends"), p[0], p[1],
                                 f"ЛРТ {lid}: линия обрывается — конец не депо и не конечная станция", [lid]))
        xs = _crossings(ctx, P, S)
        # 2. stations: on the axis, platform between cross streets, platform length
        for st in ln.get("stations", []):
            s, d, q = G.project(P[:, :2], [st["x"], st["z"]])
            if d > off_max + 1e-6:
                out.append(ctx.issue(25, ctx.sev("lrt.station_axis_max_offset_m"), st["x"], st["z"],
                                     f"ЛРТ {lid}: станция {st['id']} в {d:.1f} м от оси (≤ {off_max:.0f} м)", [lid, st["id"]]))
            pl = float(st.get("platform_m") or 0)
            if pl < plat_min - 1e-6:
                out.append(ctx.issue(25, ctx.sev("lrt.platform_length_m"), st["x"], st["z"],
                                     f"ЛРТ {lid}: платформа {st['id']} {pl:.0f} м короче {plat_min:.0f} м", [lid, st["id"]]))
            a, b = s - pl / 2.0, s + pl / 2.0
            for sa, yr, yl, seg, pt in xs:
                if a <= sa <= b and abs(yl - yr) < same + 1.0:
                    out.append(ctx.issue(25, ctx.sev("lrt.platform_between_cross_streets"), pt[0], pt[1],
                                         f"ЛРТ {lid}: улица {seg.get('street') or seg['id']} пересекает платформу "
                                         f"станции {st['id']} в одном уровне", [lid, st["id"], seg["id"]]))
        # 3. station spacing (between stations of this line inside the area)
        ch = sorted(st["chain_m"] for st in ln.get("stations", []))
        for s0, s1 in zip(ch[:-1], ch[1:]):
            dk = (s1 - s0) / 1000.0
            if dk < float(sp["min"]) - 1e-6 or dk > float(sp["max"]) + 1e-6:
                p = G.point_at(P[:, :2], 0.5 * (s0 + s1), S)
                out.append(ctx.issue(25, ctx.sev("lrt.station_spacing_km"), p[0], p[1],
                                     f"ЛРТ {lid}: шаг станций {dk:.2f} км вне {sp['min']}–{sp['max']} км", [lid]))
        # 4. viaduct clearance over the roads it crosses
        for sa, yr, yl, seg, pt in xs:
            if _kind_at(ln, sa) != "elevated":
                continue
            under = yl - deck - yr
            if under < clear - tol:
                out.append(ctx.issue(25, ctx.sev("lrt.viaduct_clearance_over_road_m"), pt[0], pt[1],
                                     f"ЛРТ {lid}: низ эстакады над {seg['class']} {under:.2f} м (нужно ≥ {clear:.1f} м)",
                                     [lid, seg["id"]], lv=1))
        # 5. grade
        if len(S) > 1:
            g = grade_excess(P, S, smax, model("lrt_slope_base_m"), tol)
            if g:
                i, gr, ch, runs, length = g
                out.append(ctx.issue(25, ctx.sev("lrt.ramp_slope_max_pct"), P[i, 0], P[i, 1],
                                     f"ЛРТ {lid}: уклон {100 * gr:.1f} % на {ch:.0f} м (≤ {100 * smax:.0f} %), "
                                     f"участков {runs}, всего {length:.0f} м", [lid]))
        # 6. curve radius (analogue)
        r = G.min_radius(P[:, :2], base=10.0)
        if r < rmin - 0.5:
            out.append(ctx.issue(25, ctx.sev("lrt.min_curve_radius_m"), P[0, 0], P[0, 1],
                                 f"ЛРТ {lid}: радиус кривой {r:.0f} м меньше {rmin:.0f} м", [lid]))
    return out


def rule25_buildings(ctx):
    """The viaduct deck must not pass through a building (a building under the deck is fine only when lower)."""
    import shapely
    out = []
    half = model("lrt_viaduct_w_m") / 2.0
    deck = model("lrt_rail_over_deck_m")
    recs = [b for b in ctx.buildings.get("buildings", []) if b.get("footprint") and len(b["footprint"]) >= 3]
    if not recs:
        return out
    fps = [np.asarray(b["footprint"], float)[:, :2] for b in recs]      # all footprints in one call
    rings = shapely.linearrings(np.concatenate(fps), indices=np.repeat(np.arange(len(fps)), [len(f) for f in fps]))
    polys = shapely.buffer(shapely.polygons(rings), 0.0)
    tree = shapely.STRtree(polys)
    for ln, P, S in _lines(ctx):
        for r in ln.get("sections", []):
            if r["kind"] != "elevated":
                continue
            m = (S >= r["from_m"]) & (S <= r["to_m"])
            if m.sum() < 2:
                continue
            band = shapely.LineString(P[m, :2]).buffer(half, cap_style="flat")
            for i in tree.query(band, predicate="intersects"):
                b = recs[i]
                c = polys[i].intersection(band).representative_point()
                s = G.project(P[:, :2], [c.x, c.y])[0]
                y_deck = float(np.interp(s, S, P[:, 2])) - deck
                top = float(b.get("base_y") or ctx.h(c.x, c.y)) + float(b.get("height_m") or 0)
                if top > y_deck:
                    out.append(ctx.issue(25, "error", c.x, c.y,
                                         f"ЛРТ {ln['id']}: эстакада проходит сквозь здание {b['id']} "
                                         f"(верх {top:.1f} м, низ пролёта {y_deck:.1f} м)", [ln["id"], b["id"]], lv=1))
    return out


def _decks(ctx):
    """Every deck a drive or a street may pass under: [(what_ru, id, axis Nx3 [x, z, underside y], top y per vertex,
    footprint)]. A street span (struct overpass / bridge: the road surface less model deck_depth_m, its built width
    land_util.deck_half), an LRT viaduct (elevated sections: rail less lrt_rail_over_deck_m, lrt_viaduct_w_m wide) and a
    railway viaduct of the spec `rail` block (lib.rail.decks: rail head less rail_deck_below_m, rail_deck_half_m each side
    of each track; the tracks of one line are one deck, joined where their halves meet)."""
    import shapely
    import land_rulekit as K
    import land_util as U
    out = []
    depth = model("deck_depth_m")
    net = ctx.network or {}
    for s in net.get("segments") or []:
        P = np.array(s["pts"], float)
        if len(P) < 2:
            continue
        S = G.chainage(P[:, :2])
        for r in s.get("struct") or []:
            if r["kind"] not in LR.DECK_KINDS or r["to_m"] - r["from_m"] < 0.5:
                continue
            Q = _cut3(P, S, r["from_m"], r["to_m"])
            half = U.deck_half(U.seg_profile(net, s, K.norms(ctx)))
            fp = shapely.LineString(Q[:, :2]).buffer(half, cap_style="flat")
            out.append((f"путепроводом {s['class']} {s['id']}", s["id"], np.c_[Q[:, :2], Q[:, 2] - depth], Q[:, 2], fp, "road"))
    lrt_deck = model("lrt_rail_over_deck_m")
    half = model("lrt_viaduct_w_m") / 2.0
    for ln, P, S in _lines(ctx):
        for r in ln.get("sections") or []:
            if r["kind"] != "elevated" or r["to_m"] - r["from_m"] < 0.5:
                continue
            Q = _cut3(P, S, r["from_m"], r["to_m"])
            fp = shapely.LineString(Q[:, :2]).buffer(half, cap_style="flat")
            out.append((f"эстакадой ЛРТ {ln['id']}", ln["id"], np.c_[Q[:, :2], Q[:, 2] - lrt_deck], Q[:, 2], fp, "lrt"))
    below, half = model("rail_deck_below_m"), model("rail_deck_half_m")
    by_line = {}
    for d in LR.decks((ctx.spec or {}).get("rail")):
        by_line.setdefault(d["line"], []).append(d)
    for lid, ds in by_line.items():
        fp = shapely.union_all([shapely.LineString(d["P"][:, :2]).buffer(half, cap_style="flat") for d in ds])
        for d in ds:
            out.append((f"эстакадой ж/д {lid}", lid, np.c_[d["P"][:, :2], d["P"][:, 2] - below], d["P"][:, 2], fp, "rail"))
    return out


def _cut3(P, S, a, b):
    """The piece of a polyline [x, z, y] between 2-D chainages a and b, heights interpolated."""
    a, b = max(float(a), 0.0), min(float(b), float(S[-1]))
    ch = np.r_[a, S[(S > a + 1e-9) & (S < b - 1e-9)], b]
    return np.c_[np.interp(ch, S, P[:, 0]), np.interp(ch, S, P[:, 1]), np.interp(ch, S, P[:, 2])]


def _under(poly, surface, decks, idx, tol_same):
    """Lowest clearance between a surface (poly, surface(x, z) → y) and the decks over it (indices idx into decks),
    sampled on the overlap's vertices and a 1 m grid inside it. {deck key: (clearance, x, z, deck)}; a point at the deck's
    own top (a drive on the span, within tol_same) or above it is not under the deck."""
    import shapely
    res = {}
    for j in idx:
        what, did, ax, top, fp, kind = decks[int(j)]
        ov = poly.intersection(fp)
        if ov.is_empty or ov.area < 0.01:
            continue
        pts = [shapely.get_coordinates(ov)]                 # the overlap's outline vertices (any part kind)
        x0, z0, x1, z1 = ov.bounds
        gx, gz = np.meshgrid(np.arange(x0 + 0.5, x1, 1.0), np.arange(z0 + 0.5, z1, 1.0))
        gx, gz = gx.ravel(), gz.ravel()
        if len(gx):
            m = shapely.contains_xy(ov, gx, gz)
            pts.append(np.c_[gx[m], gz[m]])
        Q = np.vstack(pts)
        if not len(Q):
            continue
        AS = G.chainage(ax[:, :2])
        line = shapely.LineString(ax[:, :2])
        s_ax = shapely.line_locate_point(line, shapely.points(Q))
        under_y = np.interp(s_ax, AS, ax[:, 2])
        top_y = np.interp(s_ax, AS, top)
        y = surface(Q)
        c = under_y - y
        c = np.where(y >= top_y - tol_same, np.inf, c)        # on the span or over it: not under the deck
        k = int(np.argmin(c))
        if np.isfinite(c[k]) and (did not in res or c[k] < res[did][0]):
            res[did] = (float(c[k]), float(Q[k, 0]), float(Q[k, 1]), decks[int(j)])
    return res


def rule25_drives(ctx):
    """Clearance under decks (CONTRACT §5, rule 25): every drive segment and turnaround pad of driveways.json under a
    street span, an LRT viaduct or a railway viaduct (spec `rail`) keeps fire_access.arches.height_min_m between its
    surface and the deck's underside (the norm of a fire engine's passage, lower than bridges.road_clearance_m and the
    one gen_buildings' drives already keep under street spans: land_util.offgrade); every street carriageway under a
    railway viaduct keeps bridges.road_clearance_m (street and LRT decks over streets: rules 9 and 25)."""
    import shapely
    import land_rulekit as K
    out = []
    decks = _decks(ctx)
    if not decks:
        return out
    tree = shapely.STRtree([d[4] for d in decks])
    tol, same = model("height_round_tol_m"), model("same_level_tol_m")
    road_c = float(ctx.norm("bridges.road_clearance_m"))
    arch = (ctx.norm("fire_access.arches") or {}).get("height_min_m")
    drive_c, drive_key = (float(arch), "fire_access.arches") if arch is not None and float(arch) < road_c else (road_c, "bridges.road_clearance_m")

    def along(P):
        P = np.asarray(P, float)
        S = G.chainage(P[:, :2])
        line = shapely.LineString(P[:, :2])
        return lambda Q: np.interp(shapely.line_locate_point(line, shapely.points(Q)), S, P[:, 2])

    dv = ctx.driveways or {}
    if dv:
        nodes = {n["id"]: n for n in dv.get("nodes") or []}
        segs = {s["id"]: s for s in dv.get("segments") or []}
        for s, poly in K.drive_polys(ctx, "carriage"):
            if s.get("pad"):
                nid = s["id"][4:]
                n = nodes.get(nid) or {}
                y = n.get("y")
                surf = (lambda Q, y=float(y): np.full(len(Q), y)) if y is not None else \
                    (lambda Q: np.asarray(ctx.h(Q[:, 0], Q[:, 1]), float))
                what = f"разворотная площадка проезда у {nid}"
            else:
                sg = segs.get(s["id"]) or s
                if len(sg.get("pts") or []) < 2:
                    continue
                surf = along(sg["pts"])
                what = f"проезд {s['id']}"
            for did, (c, x, z, d) in _under(poly, surf, decks, tree.query(poly, predicate="intersects"), same).items():
                if c < drive_c - tol:
                    out.append(ctx.issue(25, ctx.sev(drive_key), x, z, f"{what} под {d[0]}: просвет {c:.2f} м (нужно ≥ {drive_c:.1f} м, "
                                         f"{drive_key}{'.height_min_m' if drive_key == 'fire_access.arches' else ''})", [s["id"], did], lv=0))
    for s, poly, lv in K.road_polys(ctx, "carriage"):
        idx = [j for j in tree.query(poly, predicate="intersects") if decks[int(j)][5] == "rail"]
        if not idx or len(s.get("pts") or []) < 2:
            continue
        for did, (c, x, z, d) in _under(poly, along(s["pts"]), decks, idx, same).items():
            if c < road_c - tol:
                out.append(ctx.issue(25, ctx.sev("bridges.road_clearance_m"), x, z, f"{s['class']} {s['id']} под {d[0]}: просвет "
                                     f"{c:.2f} м (нужно ≥ {road_c:.1f} м, bridges.road_clearance_m)", [s["id"], did], lv=0))
    return out


RULES = [{"no": 25, "key": "lrt", "fn": rule25, "needs": ["lrt"]},
         {"no": 25, "key": "lrt_buildings", "fn": rule25_buildings, "needs": ["lrt", "buildings"]},
         {"no": 25, "key": "under_decks", "fn": rule25_drives, "needs": ["network"]}]
