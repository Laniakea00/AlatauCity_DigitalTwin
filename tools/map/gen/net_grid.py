"""Local street grid and village lanes of gen_network (w43).

local_grid: inside each superblock (a zone cut by the corridors of the skeleton roads, keep land, water and the
interchange areas) a staggered ("brick") grid of local streets with the zone's block side (zones[i].rules.block_side_m,
else norms quarters.block_side_m; industrial zones × MODEL industrial_block_factor). Rows run along the superblock's
long side; cross streets are offset by half a block between rows, so every junction is a T. Each street end either
sits on another grid street or is extended to the nearest skeleton street that may take a junction (not an
expressway, ramp or continuous arterial); otherwise the street is cut back to its last junction (logged).
No grid in park, waterfront, reserve, sport, utility and village zones.

village_lanes: in village_existing zones every existing house gets a street within MODEL house_access_m: a lattice
of MODEL village_lane_grid_m between the houses (never through a house: lattice points within the lane half-width +
1 m of a footprint are blocked; never across a railway track or a road it does not join), shortest paths from the streets to each unserved house
ending at the lattice point nearest to it, as `village_lane` streets labelled «модель qTwin».
"""
import heapq
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import geom as G  # noqa: E402


def _nv(v):
    v = np.asarray(v, float)
    n = float(np.hypot(v[0], v[1]))
    return v / n if n > 1e-12 else v


from lib import model  # noqa: E402
from lib import years as Y  # noqa: E402
from net_roads import make_road  # noqa: E402

GRID_USES = {"mixed_centre": "local", "business": "local", "residential_high": "local", "residential_mid": "local",
             "residential_low": "local", "campus": "local", "medical": "local", "industry": "industrial",
             "logistics": "industrial"}
NO_JOIN = {"expressway", "ramp", "arterial_continuous"}


def _block_side(net, zone):
    r = (zone.get("rules") or {}).get("block_side_m")
    if r:
        b = 0.5 * (float(r[0]) + float(r[1]))
    else:
        bs = net.N.norm("quarters.block_side_m")
        b = 0.5 * (float(bs["min"]) + float(bs["max"]))
    if GRID_USES.get(zone.get("use")) == "industrial":
        b *= model("industrial_block_factor")
    return b


def _zone_years(zone):
    y = zone.get("years")
    if not y:
        return list(Y.EXISTING)
    return Y.years4(int(y[0])) if len(y) == 2 else Y.norm4(y)


def _corridors(net):
    import shapely
    geoms = []
    for w in net.ways:
        if w.role != "primary" and w.cls != "ramp":
            continue
        rl = (w.prof or {}).get("red_line_w") or 10.0
        half = rl / 2.0 if not w.oneway else (w.prof["cw_w"] / 2.0 + 8.0)
        geoms.append(shapely.LineString(w.P).buffer(half, cap_style="flat"))
    return shapely.union_all(geoms) if geoms else None


def _ic_zones(net):
    import shapely
    clear = model("interchange_grid_clear_m")
    geoms = [shapely.LineString(w.P).buffer(clear) for w in net.ways if w.role == "ramp" or (w.ic and w.cls == "ramp")]
    return shapely.union_all(geoms) if geoms else None


def _ray_hit(p, h, max_d, lines, skip=None):
    """First crossing of the ray p + h·t (0 < t ≤ max_d) with `lines` [(Way|tag, polyline)]: (t, point, tag)."""
    seg = np.vstack([p, p + h * max_d])
    best = None
    for tag, L in lines:
        if tag is skip:
            continue
        for sa, sb, pt, ang in G.crossings(seg, L):
            if sa < 0.5:
                continue
            if best is None or sa < best[0]:
                best = (sa, pt, tag)
    return best


def local_grid(net, spec, area, keep_polys):
    import shapely
    N = net.N
    cor = _corridors(net)
    icz = _ic_zones(net)
    block = []
    for kp in keep_polys.values():
        block.append(kp)
    if net.water is not None:
        block.append(net.water)
    for z in spec.get("zones", []):
        if z.get("use") not in GRID_USES:
            block.append(shapely.Polygon(z["polygon"]).buffer(0))
    blocked = shapely.union_all([b for b in block if b is not None]) if block else None
    skeleton = [(w, w.P) for w in net.ways if w.role == "primary"]
    # the roads a grid street end may run to, found by their bounding boxes (every road of the district per end is
    # quadratic in the district's size)
    sk_tree = shapely.STRtree([shapely.LineString(P) for _, P in skeleton]) if skeleton else None
    total = 0
    for z in spec.get("zones", []):
        use = z.get("use")
        if use not in GRID_USES:
            continue
        zp = shapely.Polygon(z["polygon"]).buffer(0).intersection(area)
        if zp.is_empty:
            continue
        cells = zp
        for cut in (cor, icz, blocked):
            if cut is not None:
                cells = cells.difference(cut)
        cls = GRID_USES[use]
        b = _block_side(net, z)
        yrs = _zone_years(z)
        for cell in getattr(cells, "geoms", [cells]):
            if cell.geom_type != "Polygon" or cell.area < 1.5 * b * b:
                continue
            n = _grid_cell(net, cell, b, cls, yrs, z["id"], skeleton, sk_tree)
            total += n
    net.L("местная сеть: улицы в суперкварталах по block_side_m зоны (T-перекрёстки, ряды со сдвигом)", [],
          streets=total)


def _grid_cell(net, cell, b, cls, yrs, zid, skeleton, sk_tree=None):
    import shapely
    N = net.N
    rect = cell.minimum_rotated_rectangle
    rc = np.array(rect.exterior.coords)[:4]
    e1, e2 = rc[1] - rc[0], rc[2] - rc[1]
    ax = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
    u = ax / np.hypot(*ax)
    v = G.left(u)
    c = np.array(cell.centroid.coords[0])
    pts = np.array(cell.exterior.coords)
    pu = (pts - c) @ u
    pv = (pts - c) @ v
    umin, umax, vmin, vmax = pu.min(), pu.max(), pv.min(), pv.max()
    W = lambda a, bb: c + u * a + v * bb
    # rows (along u) every b, at least b/2 from the long edges
    nrow = int((vmax - vmin) // b)
    if nrow < 1:
        rows_v = []
    else:
        off = ((vmax - vmin) - nrow * b) / 2.0
        rows_v = [vmin + off + k * b for k in range(1, nrow + 1) if vmin + off + k * b < vmax - b / 3]
    lines = []
    for vv in rows_v:
        L = shapely.LineString([W(umin - 10, vv), W(umax + 10, vv)]).intersection(cell)
        for g in getattr(L, "geoms", [L]):
            if g.geom_type == "LineString" and g.length > b / 2:
                lines.append(("row", np.array(g.coords), vv))
    # cross streets between consecutive rows (and the cell edges), staggered by b/2
    bands = [vmin - 1.0] + rows_v + [vmax + 1.0]
    for i in range(len(bands) - 1):
        va, vb = bands[i], bands[i + 1]
        if vb - va < b / 3:
            continue
        shift = (i % 2) * b / 2.0
        nu = int((umax - umin) // b)
        for k in range(1, nu + 1):
            uu = umin + ((umax - umin) - nu * b) / 2.0 + k * b - b / 2.0 + shift
            if uu <= umin + b / 3 or uu >= umax - b / 3:
                continue
            L = shapely.LineString([W(uu, va), W(uu, vb)]).intersection(cell)
            for g in getattr(L, "geoms", [L]):
                if g.geom_type == "LineString" and g.length > b / 3:
                    lines.append(("cross", np.array(g.coords), uu))
    if not lines:
        return 0
    # extend ends that lie on the cell edge to the skeleton (T on a street that may take a junction)
    if sk_tree is None:
        sk_tree = shapely.STRtree([shapely.LineString(P) for _, P in skeleton])
    lt = shapely.STRtree([shapely.LineString(l[1]) for l in lines])
    made = 0
    out = []
    for kind, P, key in lines:
        P = P.copy()
        ok = [True, True]
        for e in (0, 1):
            p = P[0] if e == 0 else P[-1]
            h = _nv(P[0] - P[1]) if e == 0 else _nv(P[-1] - P[-2])
            # the grid lines near the end (bounding boxes within 1 m), then the exact test as before
            near = lt.query(shapely.Point(p).buffer(1.0, quad_segs=1).envelope)
            on_grid = any(G.project(Q, p)[1] < 0.5 for k2, Q, _ in (lines[i] for i in near) if Q is not P and k2 != kind)
            if on_grid:
                continue
            # the skeleton roads whose bounding box meets the ray's (the crossings test drops the others anyway), in
            # skeleton order so that equal hits resolve as before
            cand = np.sort(sk_tree.query(shapely.LineString([p, p + h * 60.0])))
            hit = _ray_hit(p, h, 60.0, [skeleton[i] for i in cand])
            if hit is None or hit[2].cls in NO_JOIN:
                ok[e] = False
                continue
            if e == 0:
                P = np.vstack([hit[1], P])
            else:
                P = np.vstack([P, hit[1]])
        out.append((kind, P, ok))
    # an end that could not join: cut back to the last junction with another grid street, else drop
    for kind, P, ok in out:
        if not all(ok):
            js = []
            for k2, Q, _ in out:
                if Q is P or k2 == kind:
                    continue
                for e in (Q[0], Q[-1]):
                    s, dd, _ = G.project(P, e)
                    if dd < 0.5:
                        js.append(s)
            L = G.length(P)
            s0 = 0.0 if ok[0] else (min(js) if js else None)
            s1 = L if ok[1] else (max(js) if js else None)
            if s0 is None or s1 is None or s1 - s0 < b / 3:
                net.L("местная улица без примыкания на обоих концах не строится", [zid], x=round(float(P[0][0]), 1),
                      z=round(float(P[0][1]), 1))
                continue
            P = G.cut(P, s0, s1)
        road, ways = make_road(N, cls, P, years=yrs, name_ru="", street=None, source="grid",
                               id_prefix=f"g{zid}_{made + 1}")
        for w in ways:
            w.keep_exact = False
            net.add(w)
        made += 1
    return made


# ------------------------------------------------------------------ village lanes
class _Buckets:
    """Lines added one by one, found by a square-cell hash of their bounding boxes (an STRtree cannot grow)."""

    def __init__(self, cell=100.0):
        self.cell = cell
        self.cells = {}
        self.geoms = []

    def _range(self, b, d):
        c = self.cell
        return (range(int(math.floor((b[0] - d) / c)), int(math.floor((b[2] + d) / c)) + 1),
                range(int(math.floor((b[1] - d) / c)), int(math.floor((b[3] + d) / c)) + 1))

    def add(self, g):
        k = len(self.geoms)
        self.geoms.append(g)
        rx, rz = self._range(g.bounds, 0.0)
        for cx in rx:
            for cz in rz:
                self.cells.setdefault((cx, cz), []).append(k)

    def near(self, g, d):
        """Lines whose bounding box comes within d of g's bounding box (a superset of those within d of g)."""
        if not self.geoms:
            return []
        if math.isinf(d):
            return list(self.geoms)
        rx, rz = self._range(g.bounds, d)
        ks = set()
        for cx in rx:
            for cz in rz:
                ks.update(self.cells.get((cx, cz), ()))
        return [self.geoms[k] for k in sorted(ks)]


def _near_lines(lines, tree, poly, x0, z0, step, gi0, gj0, ni, nj, r):
    """Flat bool mask over a cluster's lattice (global origin x0, z0; cluster offset gi0, gj0; ni × nj points): True
    for every point that may lie within r of a line (a superset: lines cut to ≤ step/2 pieces, all lattice points
    within r + step/4 of a piece end)."""
    import shapely
    mask = np.zeros((ni, nj), bool)
    b = poly.bounds
    ks = tree.query(shapely.box(b[0] - r, b[1] - r, b[2] + r, b[3] + r))
    if not len(ks):
        return mask.ravel()
    pts = shapely.get_coordinates(shapely.segmentize(np.array([lines[k] for k in ks], dtype=object), step / 2.0))
    R = r + step / 4.0
    k = int(math.ceil(R / step)) + 1
    bi = np.floor((pts[:, 0] - x0) / step).astype(np.int64) - gi0
    bj = np.floor((pts[:, 1] - z0) / step).astype(np.int64) - gj0
    for di in range(-k, k + 1):
        a = bi + di
        for dj in range(-k, k + 1):
            c = bj + dj
            m = (a >= 0) & (a < ni) & (c >= 0) & (c < nj)
            mask[a[m], c[m]] = True
    return mask.ravel()


def village_lanes(net, spec, area):
    """Distances to "the streets" and "the lanes" are taken to the nearest single line (STRtree of the streets, a cell
    hash of the lanes as they are added): the same as to their union, without building a union per house."""
    import shapely
    import shapely.ops
    from net_osm import houses_in
    N = net.N
    zones = [shapely.Polygon(z["polygon"]).buffer(0).intersection(area) for z in spec.get("zones", [])
             if z.get("use") == "village_existing"]
    zones = [z for z in zones if not z.is_empty]
    if not zones:
        return
    houses = houses_in(zones)
    if not houses:
        net.L("сёла: домов в зонах village_existing нет", [])
        return
    reach = model("house_access_m")
    step = model("village_lane_grid_m")
    prof = N.profile("village_lane")
    half = N.cross_width(prof) / 2.0
    streets = [w for w in net.ways if w.role == "primary" and w.cls not in NO_JOIN]
    lines = [shapely.LineString(w.P) for w in streets]
    st_tree = shapely.STRtree(lines) if lines else None
    harr = np.array(houses, dtype=object)
    served = np.zeros(len(houses), bool)
    if st_tree is not None:
        served[st_tree.query(harr, predicate="dwithin", distance=reach)[0]] = True
    todo = [h for k, h in enumerate(houses) if not served[k]]
    net.L("сёла: дома и доступ к улице (дом — здание Overture ≥ 25 м² или existing_osm двойника; меньше — сарай, "
          "проулок к нему не нужен)", [], houses=len(houses), sheds=getattr(houses_in, "sheds", 0),
          unserved_before=len(todo), reach_m=reach)
    if not todo:
        return
    region = shapely.union_all(zones).buffer(reach + 60.0).intersection(area)
    x0, z0, x1, z1 = region.bounds
    nx, nz = int((x1 - x0) / step) + 1, int((z1 - z0) / step) + 1
    # lattice points within the lane half-width + 1 m of a house are blocked (STRtree of the buffers: the same points
    # as inside their union, without building it)
    hb = shapely.STRtree(shapely.buffer(harr, half + 1.0, quad_segs=16))             # quad_segs as h.buffer()
    rails = getattr(net, "rail", None) or []
    rail_tree = shapely.STRtree([shapely.LineString(t["P"]) for t in rails]) if rails else None
    rail_half = model("rail_track_half_m")
    # roads a lane never joins (expressways, ramps, continuous arterials) are not sources either: a lane must not cross
    # them, so the lattice is blocked over their carriageway + the lane half-width + 1 m
    barrier = [shapely.LineString(w.P).buffer((N.cross_width(w.prof) if w.prof else 0.0) / 2.0 + half + 1.0)
               for w in net.ways if w.cls in NO_JOIN]
    barrier = shapely.union_all(barrier) if barrier else None
    INF = 1e18
    # One lattice of step m over the district (origin x0, z0), stored per cluster of the region: parts of the region
    # closer than 2 steps share a cluster, so no lattice move joins two clusters and the shortest paths, their ties
    # and the lane order are the same as on one lattice over the whole bounding box, while memory and time follow
    # the village area, not its bounding box.
    parts = [g for g in shapely.get_parts(region) if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty]
    root = list(range(len(parts)))

    def find(k):
        while root[k] != k:
            root[k] = root[root[k]]
            k = root[k]
        return k
    if len(parts) > 1:
        pa, pb = shapely.STRtree(parts).query(parts, predicate="dwithin", distance=2.0 * step)
        for u, v in zip(pa, pb):
            ru, rv = find(int(u)), find(int(v))
            if ru != rv:
                root[max(ru, rv)] = min(ru, rv)
    groups = {}
    for k in range(len(parts)):
        groups.setdefault(find(k), []).append(parts[k])
    s1, s2 = step * 1.0, step * 1.4142
    nb = [(1, 0, s1), (-1, 0, s1), (0, 1, s1), (0, -1, s1), (1, 1, s2), (1, -1, s2), (-1, 1, s2), (-1, -1, s2)]
    clusters = []
    for ps in groups.values():
        poly = ps[0] if len(ps) == 1 else shapely.union_all(ps)
        bx0, bz0, bx1, bz1 = poly.bounds
        gi0, gi1 = max(0, int(math.floor((bx0 - x0) / step))), min(nx - 1, int(math.ceil((bx1 - x0) / step)))
        gj0, gj1 = max(0, int(math.floor((bz0 - z0) / step))), min(nz - 1, int(math.ceil((bz1 - z0) / step)))
        ni, nj = gi1 - gi0 + 1, gj1 - gj0 + 1
        if ni * nj > 4_000_000:
            net.L("сёла: участок слишком велик для сетки проулков", [], error=True, x=round(bx0, 1), z=round(bz0, 1))
            continue
        cx = x0 + np.arange(gi0, gi1 + 1) * step
        cz = z0 + np.arange(gj0, gj1 + 1) * step
        XX, ZZ = np.meshgrid(cx, cz, indexing="ij")
        flat = np.column_stack([XX.ravel(), ZZ.ravel()])
        ok = shapely.contains_xy(poly, flat[:, 0], flat[:, 1])
        idx = np.nonzero(ok)[0]
        ok[idx[hb.query(shapely.points(flat[idx]), predicate="within")[0]]] = False
        if net.water is not None:
            ok &= ~shapely.contains_xy(net.water, flat[:, 0], flat[:, 1])
        if barrier is not None:
            ok &= ~shapely.contains_xy(barrier, flat[:, 0], flat[:, 1])
        if rail_tree is not None:
            # a lane never crosses a railway track: lattice points within the lane half-width + the track's gauge
            # half-width + 1 m of a track axis are blocked (a band wider than a diagonal lattice step)
            idx = np.nonzero(ok)[0]
            ok[idx[rail_tree.query(shapely.points(flat[idx]), predicate="dwithin", distance=half + rail_half + 1.0)[0]]] = False
        # flat lists over the cluster's lattice with a border of blocked points (no bounds checks in the search):
        # point (i, j) of the district is at ((i − i0 + 1) · w + j − j0 + 1), w = nj + 2; that index grows with
        # (i, j) in lexicographic order, so (distance, index) heap entries break ties as (distance, i, j) did
        w = nj + 2
        okp = np.zeros((ni + 2, w), bool)
        okp[1:-1, 1:-1] = ok.reshape(ni, nj)
        c = {"i0": gi0, "i1": gi1, "j0": gj0, "j1": gj1, "w": w, "ok": okp.ravel().tolist(),
             "dist": [INF] * ((ni + 2) * w), "prev": [-1] * ((ni + 2) * w), "pq": [],
             "offs": [(di * w + dj, d) for di, dj, d in nb]}
        # sources: lattice points next to a street (exact test on the lattice points near the streets' vertices)
        if st_tree is not None:
            idx = np.nonzero(ok & _near_lines(lines, st_tree, poly, x0, z0, step, gi0, gj0, ni, nj, step * 0.75))[0]
            hit = np.unique(st_tree.query(shapely.points(flat[idx]), predicate="dwithin", distance=step * 0.75)[0])
            for q in idx[hit]:                                  # row-major, as np.nonzero over the lattice
                k = (int(q) // nj + 1) * w + int(q) % nj + 1
                c["dist"][k] = 0.0
                heapq.heappush(c["pq"], (0.0, k))
        clusters.append(c)
    xs = x0 + np.arange(nx) * step
    zs = z0 + np.arange(nz) * step

    def run(c):
        """Dijkstra from the cluster's queued sources; neighbours in the order of nb."""
        pq, dist, prev, ok, offs = c["pq"], c["dist"], c["prev"], c["ok"], c["offs"]
        pop, push = heapq.heappop, heapq.heappush
        while pq:
            dcur, k = pop(pq)
            if dcur > dist[k]:
                continue
            for o, d in offs:
                q = k + o
                if ok[q]:
                    nd = dcur + d
                    if nd < dist[q] - 1e-9:
                        dist[q] = nd
                        prev[q] = k
                        push(pq, (nd, q))
    for c in clusters:
        run(c)

    def cluster_of(a, b):
        """The cluster holding the free lattice point (a, b) (global indices) and its flat index there."""
        for c in clusters:
            if c["i0"] <= a <= c["i1"] and c["j0"] <= b <= c["j1"]:
                q = (a - c["i0"] + 1) * c["w"] + (b - c["j0"] + 1)
                if c["ok"][q]:
                    return c, q
        return None, -1
    made = 0
    left = []
    if st_tree is not None:
        tarr = np.array(todo, dtype=object)
        (qi, _), qd = st_tree.query_nearest(tarr, return_distance=True, all_matches=False)
        dkey = np.zeros(len(todo))
        dkey[qi] = qd
        order = sorted(range(len(todo)), key=lambda k: dkey[k])       # stable, as the sort by distance before
        todo = [todo[k] for k in order]
    lanes = _Buckets()
    for h in todo:
        near = lanes.near(h, reach)
        if near and bool(shapely.dwithin(h, near, reach).any()):
            continue
        # target: the reachable lattice point within reach − step of the house that lies nearest to the house (the lane
        # ends at the house, not in its garden; on a tie the nearest by path, then the first in i, j order)
        hx0, hz0, hx1, hz1 = h.buffer(reach - step).bounds
        i0, i1 = max(0, int((hx0 - x0) / step)), min(nx - 1, int((hx1 - x0) / step) + 1)
        j0, j1 = max(0, int((hz0 - z0) / step)), min(nz - 1, int((hz1 - z0) / step) + 1)
        CI, CJ, CD, CC = [], [], [], []
        for c in clusters:
            a0, a1, b0, b1 = max(i0, c["i0"]), min(i1, c["i1"]), max(j0, c["j0"]), min(j1, c["j1"])
            if a0 > a1 or b0 > b1:
                continue
            w, dist = c["w"], c["dist"]
            for a in range(a0, a1 + 1):
                r = (a - c["i0"] + 1) * w - c["j0"] + 1
                for b in range(b0, b1 + 1):
                    d = dist[r + b]
                    if d < INF:
                        CI.append(a)
                        CJ.append(b)
                        CD.append(d)
                        CC.append(c)
        best = None
        if CI:
            ci, cj, cd = np.array(CI), np.array(CJ), np.array(CD)
            dd = shapely.distance(h, shapely.points(np.column_stack([xs[ci], zs[cj]])))
            dv = np.where(dd > reach - step, np.inf, dd)
            o = np.lexsort((cj, ci, cd, np.round(dv, 6)))   # nearest to the house, then by path, then i, j
            k = int(o[0])
            if np.isfinite(dv[k]):
                best = (CC[k], int(ci[k]), int(cj[k]))
        if best is None:
            left.append(h)
            continue
        c, i, j = best
        w, dist, prev = c["w"], c["dist"], c["prev"]
        q = (i - c["i0"] + 1) * w + (j - c["j0"] + 1)
        path = []
        while q >= 0:
            path.append((xs[c["i0"] + q // w - 1], zs[c["j0"] + q % w - 1]))
            if dist[q] == 0.0:
                break
            q = prev[q]
        path = np.array(path[::-1])
        if len(path) < 2:
            continue
        # start exactly on the street (or lane) nearest to the path's first point
        p0 = shapely.Point(path[0])
        base, dmin = [], math.inf
        if st_tree is not None:
            k = int(st_tree.query_nearest(p0)[0])
            base.append(lines[k])
            dmin = float(p0.distance(lines[k]))
        base += lanes.near(p0, dmin)
        bd = shapely.distance(p0, base)
        foot = shapely.ops.nearest_points(base[int(np.argmin(bd))], p0)[0]
        path = np.vstack([[foot.x, foot.y], path])
        line = shapely.LineString(path).simplify(step * 0.3)
        P = np.array(line.coords)
        if G.length(P) < 3.0:
            continue
        road, ways = make_road(N, "village_lane", P, years=list(Y.EXISTING), name_ru="проулок (модель qTwin)",
                               street=None, source="village", id_prefix=f"vl{made + 1}")
        for w in ways:
            w.model = "модель qTwin"
            net.add(w)
        lanes.add(shapely.LineString(P))
        made += 1
        # the new lane is a street too: its lattice points become sources
        dirty = []
        for p in G.densify(P, step / 2):
            a, b = int(round((p[0] - x0) / step)), int(round((p[1] - z0) / step))
            if 0 <= a < nx and 0 <= b < nz:
                c, q = cluster_of(a, b)
                if c is not None and c["dist"][q] > 0:
                    c["dist"][q] = 0.0
                    c["prev"][q] = -1
                    heapq.heappush(c["pq"], (0.0, q))
                    if not any(c is e for e in dirty):
                        dirty.append(c)
        for c in dirty:
            run(c)
    net.L("сёла: проулки village_lane к домам дальше 25 м от улицы (модель qTwin)", [f"vl{k + 1}" for k in range(made)],
          lanes=made, unserved_after=len(left))
    if left:
        c = [h.centroid for h in left[:20]]
        net.L("сёла: к этим домам проулок не найден (окружены другими домами)", [],
              points=[[round(p.x, 1), round(p.y, 1)] for p in c], error=True)
