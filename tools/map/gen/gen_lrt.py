"""gen_lrt (w43): spec lrt → OUT/<d>/lrt.json (CONTRACT §4, schema qtwin.lrt/1).

    python3 tools/map/gen/gen_lrt.py <district | path/to/spec.json> [--out OUT]

Lines come from the spec v1 `lrt.lines` (sections, stations, ends, joints) or from the level-0 `lrt.line` + stations
(one line on the ground; an end is a terminus when a station lies on it). For each line:
 1. clipped to the area; an end on the area edge is a joint `{kind:"joint", id, x, z, to}` (the line goes on in the
    neighbour; rule 25 waits for it), other ends are the spec `ends` (depot / terminus) in line order;
 2. corners tighter than lrt.min_curve_radius_m are rounded with arcs of that radius where the legs allow it;
 3. y_rail: on ground sections the street surface the line runs in (network.json, the median of its street) or the
    smoothed ground; on elevated sections at least ground + lrt.viaduct_clearance_over_road_m + the deck everywhere and
    over every road it crosses, tunnels the same below; transitions to the ground no steeper than
    lrt.ramp_slope_max_pct (the ramp is part of the spec section; where the rail is still within one deck of the
    ground it is reported as ground);
 4. stations snapped onto the axis with chain_m, platform_m = lrt.platform_length_m.min and the section kind;
 5. depots pass through.
Every change is a line in `log`.
"""
import argparse
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from lib import geom as G  # noqa: E402
from lib import jio, model, norms, paths, terrain  # noqa: E402
from lib import years as Y  # noqa: E402
from net_core import _grade_limit, _smooth  # noqa: E402

STEP = 5.0          # vertex spacing of the output line (m), finer than the road profile step: rails are smooth


def area_polygon(spec):
    from gen_network import area_polygon as ap
    return ap(spec, jio.load_city())


def spec_lines(spec, d):
    lrt = spec.get("lrt") or {}
    if lrt.get("lines"):
        return [dict(ln) for ln in lrt["lines"]], list(lrt.get("depots") or [])
    if lrt.get("line"):
        return [{"id": f"lrt_{d}", "name_ru": lrt.get("name_ru", ""), "line": lrt["line"],
                 "stations": lrt.get("stations") or [], "sections": [], "ends": None, "years": lrt.get("years"),
                 "level0": True}], list(lrt.get("depots") or [])
    return [], list(lrt.get("depots") or [])


def line_years(y):
    if y is None:
        return list(Y.EXISTING)
    if isinstance(y, list) and len(y) == 2:
        return Y.years4(int(y[1]))          # a level-0 [start, end]: the line opens when it is finished
    return Y.norm4(y)


# ------------------------------------------------------------------ plan
def fillet(P, R, log, lid):
    """Round every vertex whose corner is tighter than R with an arc of radius R (tangent length R·tan(θ/2) must fit in
    half of each leg; otherwise the largest arc that fits, logged)."""
    P = G.dedup(np.asarray(P, float))
    if len(P) < 3 or G.min_radius(P, base=5.0) >= R - 1e-6:
        return P
    out = [P[0]]
    short = []
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        u = (b - a) / max(np.hypot(*(b - a)), 1e-9)
        v = (c - b) / max(np.hypot(*(c - b)), 1e-9)
        th = math.acos(max(-1.0, min(1.0, float(np.dot(u, v)))))
        if th < math.radians(1.0):
            out.append(b)
            continue
        T = R * math.tan(th / 2)
        Tmax = 0.5 * min(np.hypot(*(b - a)), np.hypot(*(c - b)))
        r = R
        if T > Tmax:
            T, r = Tmax, Tmax / math.tan(th / 2)
            if r < R - 0.5:
                short.append((round(float(b[0]), 1), round(float(b[1]), 1), round(r, 1)))
        p0, p1 = b - u * T, b + v * T
        # arc centre on the inner side
        n = np.array([-u[1], u[0]]) if (u[0] * v[1] - u[1] * v[0]) > 0 else np.array([u[1], -u[0]])
        C = p0 + n * r
        a0 = math.atan2(p0[1] - C[1], p0[0] - C[0])
        a1 = math.atan2(p1[1] - C[1], p1[0] - C[0])
        sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        out.extend(G.arc_pts(C, r, a0, sweep, step=2.0))
    out.append(P[-1])
    Q = G.dedup(np.array(out))
    log.append({"what": f"ЛРТ: углы скруглены радиусом {R:.0f} м (lrt.min_curve_radius_m)", "ids": [lid],
                "short": short})
    return Q


def clip(P, area, log, lid):
    import shapely
    line = shapely.LineString(P)
    g = line.intersection(area)
    parts = [g] if g.geom_type == "LineString" else [x for x in getattr(g, "geoms", []) if x.geom_type == "LineString"]
    parts = [x for x in parts if x.length > 20.0]
    if not parts:
        return []
    if g.length < line.length - 1.0:
        log.append({"what": "ЛРТ: линия обрезана по участку", "ids": [lid], "kept_m": round(g.length, 1),
                    "of_m": round(line.length, 1)})
    out = []
    for part in parts:
        Q = np.array(part.coords, float)
        # keep the spec direction
        s0 = G.project(P, Q[0])[0]
        s1 = G.project(P, Q[-1])[0]
        out.append(Q if s1 >= s0 else Q[::-1].copy())
    return out


# ------------------------------------------------------------------ sections and heights
def sections_of(P, spec_secs):
    """[(from_m, to_m, kind)] covering the line: spec sections by projection, gaps are ground."""
    S = G.chainage(P)
    L = float(S[-1])
    iv = []
    for sc in spec_secs or []:
        a = G.project(P, sc["from"])[0]
        b = G.project(P, sc["to"])[0]
        a, b = min(a, b), max(a, b)
        if b - a > 1.0:
            iv.append((a, b, sc.get("kind", "ground")))
    iv.sort()
    out, cur = [], 0.0
    for a, b, k in iv:
        if a > cur + 0.5:
            out.append((cur, a, "ground"))
        a = max(a, cur)
        if b > a:
            out.append((a, b, k))
            cur = b
    if cur < L - 0.5:
        out.append((cur, L, "ground"))
    # merge neighbours of one kind
    m = []
    for a, b, k in out:
        if m and m[-1][2] == k and abs(m[-1][1] - a) < 0.6:
            m[-1] = (m[-1][0], b, k)
        else:
            m.append((a, b, k))
    if m:
        m[0] = (0.0, m[0][1], m[0][2])
        m[-1] = (m[-1][0], L, m[-1][2])
    return m


def road_points(net):
    """KD tree over every road vertex (x, z) with its surface y and the segment index."""
    if not net:
        return None
    from scipy.spatial import cKDTree
    xs, ys, ks = [], [], []
    for k, s in enumerate(net["segments"]):
        P = np.array(s["pts"], float)
        if len(P) < 2:
            continue
        Q = G.densify(P[:, :2], 2.0)
        S = G.chainage(P[:, :2])
        y = np.interp(G.chainage(Q), S, P[:, 2]) if len(P) > 1 else np.full(len(Q), P[0, 2])
        xs.append(Q)
        ys.append(y)
        ks.append(np.full(len(Q), k))
    if not xs:
        return None
    X = np.vstack(xs)
    return cKDTree(X), np.concatenate(ys), np.concatenate(ks)


def heights(P, secs, net, rp, N, log, lid):
    S = G.chainage(P)
    g = np.array([terrain.h(x, z) for x, z in P], float)
    gs = _smooth(S, g, 60.0)
    slope = 0.95 * float(N.norm("lrt.ramp_slope_max_pct")) / 100.0      # design a little under the norm (vertex spacing)
    clear = float(N.norm("lrt.viaduct_clearance_over_road_m"))
    deck = model("lrt_rail_over_deck_m")
    margin = model("clearance_margin_m")
    kind = np.array(["ground"] * len(S), dtype=object)
    for a, b, k in secs:
        kind[(S >= a - 1e-6) & (S <= b + 1e-6)] = k
    # ground: the street the line runs in (median between its carriageways), else the smoothed ground
    yg = gs.copy()
    if rp is not None:
        tree, ry, _ = rp
        for i, p in enumerate(P):
            if kind[i] != "ground":
                continue
            idx = tree.query_ball_point(p, 12.0)
            if idx:
                yg[i] = float(np.mean(ry[idx]))
    yg = _grade_limit(yg, S, slope)
    # roads crossed (for tents and the log)
    xs = []
    if net:
        for k, s in enumerate(net["segments"]):
            Q = np.array(s["pts"], float)
            for sa, sb, pt, ang in G.crossings(P, Q[:, :2]):
                yr = float(np.interp(sb, G.chainage(Q[:, :2]), Q[:, 2]))
                prof = (net.get("profiles") or {}).get(s["pid"]) or {}
                half = _half_width(prof) / max(math.sin(math.radians(max(ang, 20.0))), 0.34) + 3.0
                xs.append((sa, yr, half, s["id"]))
    T = yg.copy()
    up = kind == "elevated"
    dn = kind == "tunnel"
    T[up] = gs[up] + clear + deck + margin
    T[dn] = gs[dn] - clear - deck - margin
    for sa, yr, half, sid in xs:
        m = np.abs(S - sa) <= half
        T[m & up] = np.maximum(T[m & up], yr + clear + deck + margin)
        T[m & dn] = np.minimum(T[m & dn], yr - clear - deck - margin)
    y = T.copy()
    # smooth envelope inside structures: up tents fall at the ramp slope, never below the requirement
    for i in range(1, len(y)):
        ds = S[i] - S[i - 1]
        if up[i]:
            y[i] = max(y[i], y[i - 1] - slope * ds) if up[i - 1] else y[i]
        if dn[i]:
            y[i] = min(y[i], y[i - 1] + slope * ds) if dn[i - 1] else y[i]
    for i in range(len(y) - 2, -1, -1):
        ds = S[i + 1] - S[i]
        if up[i] and up[i + 1]:
            y[i] = max(y[i], y[i + 1] - slope * ds)
        if dn[i] and dn[i + 1]:
            y[i] = min(y[i], y[i + 1] + slope * ds)
    # transitions: from every ground point the structure rises / falls at most at the ramp slope
    gi = np.where(~(up | dn))[0]
    if len(gi):
        for i in np.where(up | dn)[0]:
            j = gi[np.argmin(np.abs(S[gi] - S[i]))]
            lim = abs(S[i] - S[j]) * slope
            y[i] = min(y[i], y[j] + lim) if up[i] else max(y[i], y[j] - lim)
    # sections as built: the ramp part of a structure still within one deck of the ground is on the ground
    built = kind.copy()
    built[up & (y - g < deck)] = "ground"
    built[dn & (g - y < deck)] = "ground"
    ramp_m = float(np.sum(np.diff(S)[(built[:-1] != kind[:-1])]))
    if ramp_m > 0.5:
        log.append({"what": "ЛРТ: подъём эстакады / спуск в тоннель (≤ lrt.ramp_slope_max_pct) — участок у земли считается "
                            "наземным", "ids": [lid], "m": round(ramp_m, 1)})
    short = []
    for sa, yr, half, sid in xs:
        i = int(np.argmin(np.abs(S - sa)))
        if built[i] == "elevated" and y[i] - deck - yr < clear - model("height_round_tol_m"):
            short.append(sid)
    if short:
        log.append({"what": "ЛРТ: эстакада не набирает габарит над дорогой у рампы (уклон ограничен нормой)",
                    "ids": [lid] + short, "error": True})
    return y, built, xs


def _half_width(prof):
    if not prof:
        return 6.0
    lanes = prof.get("lanes") or [1, 1]
    w = float(prof.get("lane_w", 3.5)) * sum(lanes) + float(prof.get("median_w", 0) or 0)
    return w / 2.0


def runs(S, kinds):
    out = []
    a = 0
    for i in range(1, len(S) + 1):
        if i == len(S) or kinds[i] != kinds[a]:
            s0 = 0.0 if a == 0 else 0.5 * (S[a - 1] + S[a])
            s1 = float(S[-1]) if i == len(S) else 0.5 * (S[i - 1] + S[i])
            out.append({"from_m": jio.r2(s0), "to_m": jio.r2(s1), "kind": str(kinds[a])})
            a = i
    return out


# ------------------------------------------------------------------ one line
def build_line(ln, area, net, rp, N, log, part_no=None):
    lid = ln["id"] if part_no is None else f"{ln['id']}#{part_no}"
    Rmin = float(N.norm("lrt.min_curve_radius_m"))
    P0 = np.asarray(ln["line"], float)
    P0 = fillet(P0, Rmin, log, lid)
    out = []
    parts = clip(P0, area, log, lid)
    for k, P in enumerate(parts):
        pid = lid if len(parts) == 1 else f"{lid}#{k + 1}"
        P = G.densify(P, STEP)
        S = G.chainage(P)
        L = float(S[-1])
        secs = sections_of(P, ln.get("sections"))
        y, built, xs = heights(P, secs, net, rp, N, log, pid)
        # ends: area edge → joint, else the spec ends in line order (v1), or a terminus station on the end (level 0)
        ends = []
        spec_ends = list(ln.get("ends") or [])
        joints = list(ln.get("joints") or [])
        import shapely
        for e, p in ((0, P[0]), (1, P[-1])):
            if area.exterior.distance(shapely.Point(p)) < 1.0:
                j = min(joints, key=lambda j: math.hypot(j["x"] - p[0], j["z"] - p[1])) if joints else None
                if j is not None and math.hypot(j["x"] - p[0], j["z"] - p[1]) > 60.0:
                    j = None
                ends.append({"kind": "joint", "id": (j or {}).get("edge_joint") or f"{pid}:edge{e}",
                             "x": jio.r1(p[0]), "z": jio.r1(p[1]), "to": (j or {}).get("to")})
                continue
            got = None
            if len(spec_ends) == 2:
                got = spec_ends[e]
            elif len(spec_ends) == 1:
                got = spec_ends[0] if not ends or ends[-1].get("kind") == "joint" else None
            if got is None:
                st = [s for s in ln.get("stations") or [] if math.hypot(s["x"] - p[0], s["z"] - p[1]) < 60.0]
                if st:
                    got = {"kind": "terminus", "id": st[0]["id"]}
            if got is None:
                got = {"kind": "open", "id": None}
                log.append({"what": "ЛРТ: конец линии не депо, не конечная и не на границе участка", "ids": [pid],
                            "x": jio.r1(p[0]), "z": jio.r1(p[1]), "error": True})
            ends.append(dict(got))
        # stations
        plat = float(N.norm("lrt.platform_length_m")["min"])
        stations = []
        for st in ln.get("stations") or []:
            s, dist, q = G.project(P, [st["x"], st["z"]])
            if dist > 100.0 or s < 0.5 or s > L - 0.5:
                if not area.contains(shapely.Point(st["x"], st["z"])):
                    log.append({"what": "ЛРТ: станция вне участка — не берётся", "ids": [pid, st["id"]]})
                else:
                    log.append({"what": "ЛРТ: станция далеко от линии — не берётся", "ids": [pid, st["id"]],
                                "dist_m": round(dist, 1), "error": True})
                continue
            if dist > 0.05:
                log.append({"what": "ЛРТ: станция поставлена на ось линии", "ids": [pid, st["id"]],
                            "moved_m": round(dist, 2)})
            i = int(np.argmin(np.abs(S - s)))
            stations.append({"id": st["id"], "name_ru": st.get("name_ru", ""), "x": jio.r2(q[0]), "z": jio.r2(q[1]),
                             "chain_m": jio.r2(s), "platform_m": plat, "kind": str(built[i]),
                             "y_rail": jio.r2(y[i])})
            if st.get("kind") and st["kind"] != built[i]:
                log.append({"what": f"ЛРТ: станция задана как {st['kind']}, по профилю линии {built[i]}",
                            "ids": [pid, st["id"]]})
        stations.sort(key=lambda t: t["chain_m"])
        out.append({"id": pid, "name_ru": ln.get("name_ru", ""),
                    "pts": [[jio.r2(x), jio.r2(z), jio.r2(yy)] for (x, z), yy in zip(P, y)],
                    "sections": runs(S, built), "stations": stations, "ends": ends,
                    "years": line_years(ln.get("years")),
                    "crossings": [{"chain_m": jio.r2(sa), "segment": sid, "y_road": jio.r2(yr)} for sa, yr, _, sid in xs]})
        log.append({"what": f"ЛРТ: линия {pid} {L:.0f} м, станций {len(stations)}, пересечений с дорогами {len(xs)}",
                    "ids": [pid], "sections": [(r["kind"], round(r["to_m"] - r["from_m"])) for r in runs(S, built)]})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("district")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    d = paths.district_id(a.district)
    spec = jio.load_spec(a.district)
    N = norms.get()
    area = area_polygon(spec)
    net = jio.load_out(d, "network.json", a.out)
    log = []
    if net is None:
        log.append({"what": "ЛРТ: network.json нет — высоты по земле, пересечения с дорогами не учтены", "ids": []})
    rp = road_points(net)
    lines, depots = spec_lines(spec, d)
    out = []
    for ln in lines:
        out.extend(build_line(ln, area, net, rp, N, log))
    if not lines:
        log.append({"what": "ЛРТ: в spec нет линий", "ids": []})
    doc = {"schema": "qtwin.lrt/1", "district": d, "lines": out,
           "depots": [{"id": dp["id"], "polygon": dp["polygon"], "years": Y.norm4(dp.get("years")) if dp.get("years") else list(Y.EXISTING)}
                      for dp in depots],
           "log": log}
    path = paths.out_file(d, "lrt.json", a.out)
    jio.save_json(doc, path, indent=1)
    print(f"gen_lrt {d}: линий {len(out)}, станций {sum(len(l['stations']) for l in out)}, "
          f"депо {len(doc['depots'])}, {time.time() - t0:.1f} с → {path}")
    for ln in out:
        print(f"  {ln['id']}: " + ", ".join(f"{r['kind']} {r['to_m'] - r['from_m']:.0f} м" for r in ln["sections"])
              + "; концы " + ", ".join(e["kind"] for e in ln["ends"]))
    for e in log:
        if e.get("error"):
            print("  ! " + e["what"], e["ids"][:4])
    return 0


if __name__ == "__main__":
    sys.exit(main())
