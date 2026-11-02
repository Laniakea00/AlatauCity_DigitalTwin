"""Re-run of the twin computations (UnityProject/Tools/twin_gen/gen_twin.py) on merged roads and buildings, without blend_geo.json.

What gen_twin took from blend_geo.json and where it comes from here:
  * the road graph (roads.pkl): the merged roads.json itself (nodes, edges, years per scenario as written: the district networks
    carry their own years, the kept edges keep theirs; gen_twin's road_years() is not re-run);
  * named sites (water intakes «ВЗУ», treatment plants «Канализационное…», renewables «СЭС»/«ВИЭ»): rebuilt from the non-synthetic
    facilities of the current networks.json (same names, places and notes, same order);
  * the LRT model (stations, km per phase): the current construction.json `lrt` block, with the stations inside merged areas replaced
    by the districts' lrt.json stations;
  * rivers for the flood model (gen_risk.py): the «Rivers» ribbon of CityData/layer_infrastructure.bytes (centre, width, water level).
Everything else is gen_twin's own code (imported), except traffic(): gen_twin's demand (gravity between 1 km cells, LRT share,
external trips, BPR), but every trip starts and ends at a building on the street it fronts (or through its drive), trees grow from
the connectors of each origin cell, a few seeded passes spread through traffic, and the trees are loaded in one vectorised pass (gen_twin
needs numba for that, which is not installed here). New edges with a street profile get their lanes from the profile and their speed
from norms.json; drives, pedestrian streets, bike paths and boulevards without lanes are never routed through (see traffic())."""
import collections
import math
import os
import sys

import numpy as np
import shapely
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

import util as U

sys.path.insert(0, U.TWIN_GEN)
import twin_common as TC  # noqa: E402
import norms as N  # noqa: E402
import gen_twin as GT  # noqa: E402
import gen_roads as GR  # noqa: E402

SCEN = TC.SCENARIOS


class NodeTree:
    """cKDTree over the nodes that have edges, answering with indices of the full node list (gen_twin uses kd.query()[1] as a node id
    and kd.data[i] as its position)."""
    def __init__(self, nodes, used):
        self.idx = np.array(sorted(used), int); self.data = np.asarray(nodes, float)
        self.kd = cKDTree(self.data[self.idx])

    def query(self, p, k=1):
        d, i = self.kd.query(p, k)
        return d, (self.idx[i] if np.ndim(i) else int(self.idx[i]))


def geo_substitute(networks):
    """Named sites of the master plan as blend_geo `points` (the inverse of gen_twin.build_facilities' naming)."""
    pts = []
    for f in networks["facilities"]:
        if f.get("synthetic"):
            continue
        k, name, note = f["kind"], f["name"], f.get("note") or ""
        if k == "water_intake":
            pts.append({"text": name.replace(" (водозабор)", "") + "\n" + note, "x": f["x"], "z": f["z"]})
        elif k == "wastewater":
            pts.append({"text": "Канализационное очистное сооружение №" + name.split("№")[-1] + "\n" + note, "x": f["x"], "z": f["z"]})
        elif k == "renewable":
            n = name.split(" · ")[0].replace("«", '"').replace("»", '"')
            pts.append({"text": n + "\n" + note.split(" по генплану")[0], "x": f["x"], "z": f["z"]})
    return {"points": pts, "layers": {}}


# ------------------------------------------------------------------ traffic (gen_twin.traffic, loaded on the local network)
EXISTING_HOME_M2 = 600.0   # an existing (OSM) building up to this GFA is a home (residents by M2_PER_RESIDENT); a larger one is workplaces
EXISTING_M2_PER_JOB = 100.0
ACCESS_NEAR_M = 120.0      # streets this close to a building are its access candidates (beyond: the nearest open street)
FRONT_EXTRA_M, FRONT_MAX_M = 15.0, 60.0   # a second street piece this much farther than the nearest (and this close) is fronted too: trips split
DRIVE_NEAR_M = 30.0        # a building no drive names (sv) but with a drive this close reaches its street through that drive
NOISE = (0.85, 1.18)       # link costs × U(…) per assignment pass (seeded): through traffic spreads over parallel routes
PASSES = 3
WRONG_WAY = (10.0, 10.0)   # against a one-way edge or a ramp: cost × 10 + 10 min (only where nothing else connects)
# Almaty (80 % of the external trips) lies beyond the map's south edge: a trip leaves by any highway, ring or main road ending within
# ALMATY_GATE_M of that edge and then runs straight to the centre at ALMATY_KMH. gen_twin sent them all to its min-z highway node, the
# end of BAKAD's east branch (11158, −30267), 13 km east of A-3: every Almaty trip from the city turned A-3 S → BAKAD E there (the loop
# of ic_a3_bakad at v/c 8–10), none drove on along A-3 into the city.
ALMATY_CENTRE = (-5021.0, -40906.0)   # Republic Square, 43.2381 N 76.9457 E (geo/frames.lonlat_to_unity)
ALMATY_GATE_M = 400.0
ALMATY_KMH = 50.0


def _tree_flows(pred, dist, demand, arc_keys, S, n, flow):
    """For each row r: demand[r] sits at destination nodes; every node passes the sum of its subtree to its predecessor, and the arc
    (pred, node) hands it to its edges (S: arc → edges, shares by capacity where edges run in parallel). A node's predecessor is
    strictly nearer to the root, so pushing the nodes rank by rank from the farthest, all rows at once, passes every subtree sum up
    exactly once."""
    R = pred.shape[0]
    fin = np.isfinite(dist)
    s = np.where(fin, demand, 0.0)
    order = np.argsort(np.where(fin, -dist, 1.0).astype(np.float32), axis=1)     # farthest first, unreachable last
    nreach = fin.sum(axis=1); pr = np.take_along_axis(pred, order, axis=1)
    flat = s.reshape(-1); rows = np.arange(R); base = rows * n
    for k in range(int(nreach.max()) if R else 0):
        v = order[:, k]; p = pr[:, k]; m = (p >= 0) & (k < nreach)
        if m.all():
            flat[base + p] += flat[base + v]
        elif m.any():
            b = base[m]; flat[b + p[m]] += flat[b + v[m]]
    pf = pred.reshape(-1); idx = np.flatnonzero((pf >= 0) & fin.reshape(-1))
    key = pf[idx].astype(np.int64) * n + idx % n
    pos = np.minimum(np.searchsorted(arc_keys, key), len(arc_keys) - 1); good = arc_keys[pos] == key
    flow += S.T @ np.bincount(pos[good], flat[idx][good], len(arc_keys))


def _arcs(ri, A, Bn, K, cap, NT, E):
    """Directed arcs of the route edges (key u·NT + v) and the share of each edge in its arc: by capacity over the edges that run that
    way (parallel edges between the same two nodes share the flow), the wrong way only where no edge runs that way."""
    u = np.r_[A[ri], Bn[ri]]; v = np.r_[Bn[ri], A[ri]]; e = np.r_[ri, ri]; wrong = np.r_[np.zeros(len(ri), bool), K[ri] != 0]
    key = u.astype(np.int64) * NT + v; o = np.lexsort((wrong, key)); key, e, wrong = key[o], e[o], wrong[o]
    uk, gi = np.unique(key, return_inverse=True); gi = gi.reshape(-1)
    ok_any = np.bincount(gi, ~wrong, len(uk)) > 0; keep = ~wrong | ~ok_any[gi]
    c = np.where(keep, cap[e], 0.0); share = c / np.bincount(gi, c, len(uk))[gi]
    return uk, csr_matrix((share[keep], (gi[keep], e[keep])), shape=(len(uk), E))


def _min_csr(u, v, w, N):
    """Directed graph with the cheapest of parallel arcs (csr_matrix would add their costs)."""
    key = u.astype(np.int64) * N + v; o = np.lexsort((w, key)); key, w = key[o], w[o]
    first = np.r_[True, key[1:] != key[:-1]]
    return csr_matrix((w[first], (key[first] // N, key[first] % N)), shape=(N, N))


def traffic_loads(B):
    """Per building (d ≥ 0) residents and jobs for the traffic model: gen_twin's per_building_loads; existing OSM buildings (no loads in
    gen_twin, they are not new construction) count too: homes up to EXISTING_HOME_M2, workplaces above."""
    keep, res, jobs = [], [], []
    for i, b in enumerate(B):
        if b["d"] < 0:
            continue
        if b["source"] == "existing_osm":
            r, j = (b["gfa"] / N.M2_PER_RESIDENT, 0.0) if b["gfa"] <= EXISTING_HOME_M2 else (0.0, b["gfa"] / EXISTING_M2_PER_JOB)
        else:
            L = GT.per_building_loads(b)
            if L is None:
                continue
            r, j = L["res"], L["jobs"]
        if r > 0 or j > 0:
            keep.append(i); res.append(r); jobs.append(j)
    return keep, np.array(res), np.array(jobs)


def edge_kinds(edges, prof):
    """Masks per edge: carless (by design no cars), drive, route (cars may pass through), access (a building may front it), main (a
    zone connector: arterials, district streets, a village's main street, the old 'main')."""
    carless = np.array([U.carless(e["t"], prof[e["p"]] if e["p"] is not None and 0 <= e["p"] < len(prof) else None) for e in edges], bool)
    drive = np.array([e["t"] in U.DRIVES for e in edges], bool) & ~carless
    route = ~carless & ~drive
    fast = np.array([e["k"] == 2 or e["t"] in ("expressway", "ramp") or (e["t"] is None and e["cls"] in ("highway", "ring")) for e in edges], bool)
    main = route & ~fast & np.array([e["t"] in U.MAIN or e["t"] == "village_main" or (e["t"] is None and e["cls"] == "main") for e in edges], bool)
    return carless, drive, route, route & ~fast, main


def drive_forest(edges, drive, route, n):
    """Each drive node's way out to a street: the nearest attach node (a node a drive shares with a route edge) over the drive edges,
    and the drive edges on that way. Returns (dist, root per node or −1, path(node) → tuple of drive edges), or None."""
    di = np.flatnonzero(drive)
    if not len(di):
        return None
    A = np.array([edges[i]["a"] for i in di]); Bn = np.array([edges[i]["b"] for i in di]); L = np.array([max(edges[i]["len"], 0.1) for i in di])
    rn = set(e["a"] for e, r in zip(edges, route) if r) | set(e["b"] for e, r in zip(edges, route) if r)
    roots = sorted((set(A.tolist()) | set(Bn.tolist())) & rn)
    if not roots:
        return None
    dist, pred, src = dijkstra(_min_csr(np.r_[A, Bn], np.r_[Bn, A], np.r_[L, L], n), directed=True, indices=roots, min_only=True,
                               return_predecessors=True)
    pair = {}
    for k, i in enumerate(di):
        pair.setdefault((int(A[k]), int(Bn[k])), int(i)); pair.setdefault((int(Bn[k]), int(A[k])), int(i))
    memo = {}

    def path(v):
        out = []; x = v
        while x not in memo and pred[x] >= 0:
            out.append(x); x = int(pred[x])
        tail = memo.get(x, ())
        for y in reversed(out):
            tail = (pair[(int(pred[y]), y)],) + tail; memo[y] = tail
        return memo.get(v, ())
    return dist, np.where(np.isfinite(dist), src, -1), path


def traffic(nodes, edges, B, lrt, cap, t0, prof, scen_years=(2030, 2035, 2040, 2045, 2050), log=print, fronts=None, stages=()):
    """gen_twin's morning-peak model (gravity between 1 km cells, LRT share, external trips, BPR) with every trip starting and ending at
    a building on the street it fronts (or at the end of its drive), so each street carries its own access traffic:
      * one shortest-path tree per origin cell from a virtual source joined to the cell's connector nodes (arterials and district
        streets in the cell): a trip leaves by the connector best for its destination, never through one centroid node;
      * origin legs: each home's departures at its access point (the nearer end of its street piece by the tree); destination legs:
        each cell's arrivals spread over its workplaces by jobs (intra-cell trips too, which gen_twin left unloaded);
      * the street piece a building fronts carries that building's trips; a building's drives (roads edge `sv`, else a drive within
        DRIVE_NEAR_M) carry its trips to their attach nodes, split evenly;
      * a mesh-less row of a landmark lot's own capacity (`fronts`: bid → the lot's polygon; a whole quarter such as Iconic with its
        own streets) starts and ends its trips on every open street piece within FRONT_EXTRA_M of the lot, by the length there;
      * drives, pedestrian streets, bike paths and boulevards without lanes are not in the routing graph (no route uses them); one-way
        edges and ramps are driven in point order (against it only at WRONG_WAY cost); parallel edges between two nodes share by capacity;
      * PASSES incremental passes, each on link costs × a seeded U(NOISE) (BPR between passes): through traffic spreads.
      * stages [(edge, {scenario: year}, capacity)]: an edge rebuilt with other lanes (roads.json `ps`) has that capacity
        from its year on (a ramp widened in 2035 carries 2035 and later at the new capacity);
      * external trips (gen_twin's shares): 20 % to Konaev (the max-z highway node), 80 % to Almaty through a virtual sink joined to
        every road that reaches the map's south edge (ALMATY_GATE_M), each at the straight run from there to the centre.
    vc = flow / capacity ×100, at least 1 where any car passes (> 0.01 veh/h); 0 = no cars (not open, or carless by design)."""
    import time
    t_s = time.time()
    n = len(nodes); E = len(edges)
    carless, drive, route, access, main = edge_kinds(edges, prof)
    hw = [i for i, e in enumerate(edges) if e["cls"] == "highway"]
    hw_nodes = set([edges[i]["a"] for i in hw] + [edges[i]["b"] for i in hw])
    almaty = min(hw_nodes, key=lambda q: nodes[q][1]); konaev = max(hw_nodes, key=lambda q: nodes[q][1])
    A = np.array([e["a"] for e in edges]); Bn = np.array([e["b"] for e in edges]); Lm = np.array([e["len"] for e in edges], float)
    K = np.array([e["k"] or 0 for e in edges]); P = np.asarray(nodes, float)
    # the Almaty gates: ends of the highway, ring and main roads at the map's south edge, each with its run on to the centre (minutes)
    gm = route & np.array([e["cls"] in ("highway", "ring", "main") for e in edges], bool)
    gn = np.unique(np.r_[A[gm], Bn[gm]]) if gm.any() else np.array([almaty])
    z0 = float(P[np.unique(np.r_[A, Bn]), 1].min()); gates = gn[P[gn, 1] <= z0 + ALMATY_GATE_M]
    if not len(gates):
        gates = np.array([almaty])
    gcost = np.hypot(P[gates, 0] - ALMATY_CENTRE[0], P[gates, 1] - ALMATY_CENTRE[1]) / 1000.0 / ALMATY_KMH * 60.0
    # ---- buildings: loads, cells, access candidates
    keep, res_b, jobs_b = traffic_loads(B)
    nb = len(keep); local_of = {B[i]["bid"]: k for k, i in enumerate(keep)}
    bx = np.array([B[i]["x"] for i in keep]); bz = np.array([B[i]["z"] for i in keep]); gfa = np.array([max(B[i]["gfa"], 1.0) for i in keep])
    eff = {s: np.array([B[i]["eff"][s] for i in keep]) for s in SCEN}
    ckey = [(int(x // GT.CELL), int(z // GT.CELL)) for x, z in zip(bx, bz)]
    cid = {k: i for i, k in enumerate(sorted(set(ckey)))}; keys_sorted = sorted(cid, key=cid.get)
    bc = np.array([cid[k] for k in ckey]); NC = len(cid)
    cw = np.bincount(bc, gfa, NC); cxy = np.c_[np.bincount(bc, gfa * bx, NC) / cw, np.bincount(bc, gfa * bz, NC) / cw]
    geoms = np.array([shapely.LineString(e["geom"]) for e in edges], dtype=object)
    pts = shapely.points(bx, bz)
    ae = np.flatnonzero(access); tree_a = shapely.STRtree(geoms[ae])
    pb, pe = tree_a.query(pts, predicate="dwithin", distance=ACCESS_NEAR_M); pe = ae[pe]
    pd = shapely.distance(geoms[pe], pts[pb]); pt = shapely.line_locate_point(geoms[pe], pts[pb], normalized=True)
    o = np.lexsort((pd, pb)); sb_, se_, st2, sd_ = pb[o], pe[o], pt[o], pd[o]   # street candidates, nearest first per building
    # ---- landmark lots: the street pieces in the lot (+ FRONT_EXTRA_M) and their length there
    zb, ze, zw = [], [], []
    for k, i in enumerate(keep):
        lp = (fronts or {}).get(B[i]["bid"])
        if lp is None:
            continue
        Pb = lp.buffer(FRONT_EXTRA_M)
        for q in tree_a.query(Pb, predicate="intersects"):
            ln = float(geoms[ae[q]].intersection(Pb).length)
            if ln > 1.0:
                zb.append(k); ze.append(int(ae[q])); zw.append(ln)
    zb, ze, zw = np.array(zb, int), np.array(ze, int), np.array(zw, float)
    isz = np.zeros(nb, bool); isz[zb] = True
    # ---- drives: the buildings each drive serves (sv), else a drive within DRIVE_NEAR_M; the way out to the attach node
    fo = drive_forest(edges, drive, route, n)
    ap_b, ap_e, ap_root, mr, mc = [], [], [], [], []
    if fo is not None:
        ddist, droot, dpath = fo
        pairs = set()
        for i in np.flatnonzero(drive):
            for bid in edges[i].get("sv") or []:
                if bid in local_of:
                    pairs.add((local_of[bid], int(i)))
        named = set(b for b, _ in pairs)
        di = np.flatnonzero(drive)
        q1, q2 = shapely.STRtree(geoms[di]).query(pts, predicate="dwithin", distance=DRIVE_NEAR_M)
        if len(q1):
            dq = shapely.distance(geoms[di[q2]], pts[q1]); oo = np.lexsort((dq, q1)); q1, q2 = q1[oo], q2[oo]
            first = np.r_[True, q1[1:] != q1[:-1]]
            pairs |= set((int(b), int(di[e])) for b, e in zip(q1[first], q2[first]) if int(b) not in named)
        for b, e in sorted(pairs):
            if isz[b]:
                continue
            t = float(shapely.line_locate_point(geoms[e], pts[b], normalized=True))
            u, v = edges[e]["a"], edges[e]["b"]; du = ddist[u] + t * Lm[e]; dv = ddist[v] + (1 - t) * Lm[e]
            c = u if du <= dv else v
            if not np.isfinite(min(du, dv)) or droot[c] < 0:
                continue
            k = len(ap_b); ap_b.append(b); ap_e.append(e); ap_root.append(int(droot[c]))
            for x in set((e,) + dpath(c)):
                mr.append(x); mc.append(k)
    ap_b, ap_e, ap_root = np.array(ap_b, int), np.array(ap_e, int), np.array(ap_root, int)
    Md = csr_matrix((np.ones(len(mr)), (mr, mc)), shape=(E, len(ap_b)))
    ri = np.flatnonzero(route)
    out = {}; diag = ""
    for s in SCEN:
        out[s] = {}
        for Y in scen_years:
            here = eff[s] <= Y
            r_b = np.where(here, res_b, 0.0); j_b = np.where(here, jobs_b, 0.0)
            res = np.bincount(bc, r_b, NC); jobs = np.bincount(bc, j_b, NC)
            st = np.array([[x, z] for x, z, ph in lrt["stations"] if lrt["phase_year"][s][ph] <= Y]).reshape(-1, 2)
            near = np.array([(np.min(np.linalg.norm(st - p, axis=1)) < 1500) if len(st) else False for p in cxy])
            lrt_share = np.where(near, 0.30, 0.10) if len(st) else np.zeros(NC)
            persons = res * 0.12
            veh = persons * (1 - lrt_share) / 1.3
            ext_share = float(np.interp(Y, [2025, 2050], [0.45, 0.15]))
            open_mask = np.array([e["year"][s] <= Y for e in edges], bool)
            capY = cap.copy()
            for i_, ys_, c_ in stages:
                if ys_[s] <= Y:
                    capY[i_] = c_
            # gravity between cells (gen_twin): F[row, cell] = trips from the row's cell (intra-cell trips on its own cell), externals apart
            Dm = np.linalg.norm(cxy[:, None, :] - cxy[None, :, :], axis=2)
            G = np.exp(-0.00012 * Dm); np.fill_diagonal(G, 0.35)
            att = G * jobs[None, :]; att[:, jobs <= 0] = 0
            local = np.diag(att) / np.maximum(att.sum(axis=1), 1e-9)
            srcs = np.flatnonzero(veh > 0.5); R = len(srcs)
            if R == 0:
                out[s][Y] = {"vc": [0] * E, "kpi": {"car_trips": 0, "lrt_trips": 0, "congested_km": 0.0, "avg_delay_pct": 0.0}}
                continue
            a2 = att[srcs].copy(); a2[np.arange(R), srcs] = 0
            F = (veh[srcs] * (1 - ext_share) * (1 - local[srcs]))[:, None] * a2 / np.maximum(a2.sum(axis=1), 1e-9)[:, None]
            F[np.arange(R), srcs] += veh[srcs] * (1 - ext_share) * local[srcs]
            w_b = np.where(jobs[bc] > 0, j_b / np.maximum(jobs[bc], 1e-9), 0.0)
            dep_b = r_b * 0.12 * (1 - lrt_share[bc]) / 1.3
            arr_b = F.sum(axis=0)[bc] * w_b
            row_of_cell = np.full(NC, -1); row_of_cell[srcs] = np.arange(R)
            # access points this year: the building's open drives (evenly), else the nearest open street piece, else the nearest open one
            ap_ok = open_mask[ap_e] if len(ap_e) else np.zeros(0, bool)
            cnt = np.bincount(ap_b[ap_ok], minlength=nb); use_d = cnt > 0
            ap_f = np.where(ap_ok, 1.0 / np.maximum(cnt[ap_b], 1), 0.0) if len(ap_b) else np.zeros(0)
            m = open_mask[se_] & ~use_d[sb_]; fb, fe, ft, fd = sb_[m], se_[m], st2[m], sd_[m]
            sp_b, sp_e, sp_t, sp_f = (np.zeros(0, int), np.zeros(0, int), np.zeros(0), np.zeros(0))
            if len(fb):                                             # the nearest open piece, and a second one it also fronts (a corner)
                g0 = np.flatnonzero(np.r_[True, fb[1:] != fb[:-1]]); gi = np.cumsum(np.r_[True, fb[1:] != fb[:-1]]) - 1
                rank = np.arange(len(fb)) - g0[gi]; d0 = fd[g0][gi]
                two = (rank == 1) & (fd <= d0 + FRONT_EXTRA_M) & (fd <= FRONT_MAX_M); has2 = np.zeros(nb, bool); has2[fb[two]] = True
                tk = (rank == 0) | two; sp_b, sp_e, sp_t = fb[tk], fe[tk], ft[tk]; sp_f = np.where(has2[sp_b], 0.5, 1.0)
            if len(zb):                                             # landmark lots: every open piece in the lot, by its length there
                kz = ~isz[sp_b]; sp_b, sp_e, sp_t, sp_f = sp_b[kz], sp_e[kz], sp_t[kz], sp_f[kz]
                zo = open_mask[ze]; tot = np.bincount(zb[zo], zw[zo], nb)
                sp_b = np.r_[sp_b, zb[zo]]; sp_e = np.r_[sp_e, ze[zo]]; sp_t = np.r_[sp_t, np.full(int(zo.sum()), 0.5)]
                sp_f = np.r_[sp_f, zw[zo] / np.maximum(tot[zb[zo]], 1e-9)]
            got = np.zeros(nb, bool); got[sp_b] = True
            miss = np.flatnonzero(~got & ~use_d & ((dep_b > 0) | (w_b > 0)))
            oe = np.flatnonzero(access & open_mask)
            if len(miss) and len(oe):
                qi, qe = shapely.STRtree(geoms[oe]).query_nearest(pts[miss], all_matches=False)
                sp_b = np.r_[sp_b, miss[qi]]; sp_e = np.r_[sp_e, oe[qe]]; sp_f = np.r_[sp_f, np.ones(len(qi))]
                sp_t = np.r_[sp_t, shapely.line_locate_point(geoms[oe[qe]], pts[miss[qi]], normalized=True)]
            # points: (building, end a, end b, along t, street piece or −1, share)
            nd_ = int(ap_ok.sum())
            pt_b = np.r_[sp_b, ap_b[ap_ok]]; pt_a = np.r_[A[sp_e], ap_root[ap_ok]]; pt_n = np.r_[Bn[sp_e], ap_root[ap_ok]]
            pt_t = np.r_[sp_t, np.zeros(nd_)]; pt_e = np.r_[sp_e, np.full(nd_, -1)]; pt_f = np.r_[sp_f, ap_f[ap_ok]]
            ends = dep_b + arr_b
            acc_flow = np.bincount(pt_e[pt_e >= 0], (ends[pt_b] * pt_f)[pt_e >= 0], E)
            if len(ap_b):
                acc_flow += Md @ (ends[ap_b] * ap_f)

            def groups(wt, sel):
                key = np.c_[bc[pt_b][sel], pt_a[sel], pt_n[sel], pt_e[sel]]
                u, inv = np.unique(key, axis=0, return_inverse=True); inv = inv.reshape(-1); wv = (wt[pt_b] * pt_f)[sel]
                W = np.bincount(inv, wv, len(u)); Tm = np.bincount(inv, wv * pt_t[sel], len(u)) / np.maximum(W, 1e-12)
                return u[:, 0], u[:, 1], u[:, 2], u[:, 3], W, Tm
            pc, pa, pn, pee, pW, pT = groups(dep_b, (dep_b[pt_b] > 0) & (row_of_cell[bc[pt_b]] >= 0))
            qc, qa, qn, qee, qW, qT = groups(w_b, w_b[pt_b] > 0)
            prow = row_of_cell[pc]
            # routing graph: route edges in point order (against a one-way edge at WRONG_WAY cost) + a virtual source per origin row
            NT = n + R + 1; sink = n + R; arc_keys, S = _arcs(ri, A, Bn, K, capY, NT, E)   # n + r: the origin rows; sink: Almaty
            mo = np.flatnonzero(main & open_mask); cn = np.unique(np.r_[A[mo], Bn[mo]]) if len(mo) else np.zeros(0, int)
            ccell = collections.defaultdict(list)
            for v in cn:
                ccell[(int(P[v, 0] // GT.CELL), int(P[v, 1] // GT.CELL))].append(int(v))
            ao = np.flatnonzero(access & open_mask); an = np.unique(np.r_[A[ao], Bn[ao]]) if len(ao) else np.array([almaty])
            kd_m = cKDTree(P[cn]) if len(cn) else None; kd_a = cKDTree(P[an])
            sr, sc_ = [], []
            for r, ci in enumerate(srcs):
                cs = ccell.get(keys_sorted[ci])
                if not cs and kd_m is not None:
                    d, k = kd_m.query(cxy[ci]); cs = [int(cn[k])] if d < 1000 else None
                if not cs:
                    cs = [int(an[kd_a.query(cxy[ci])[1]])]
                sr += [n + r] * len(cs); sc_ += cs
            sr = np.array(sr, int); sc_ = np.array(sc_, int)
            rng = np.random.default_rng(int(Y) * 10 + SCEN.index(s))
            if s == "base" and Y == scen_years[-1]:
                diag = (f"base {Y}: intra-cell trips {100 * float((veh[srcs] * (1 - ext_share) * local[srcs]).sum()) / max(float(veh.sum()), 1):.1f} % "
                        f"of {veh.sum():.0f} car trips (gen_twin left them unloaded), existing homes "
                        f"{100 * float(dep_b[[B[keep[k]]['source'] == 'existing_osm' for k in range(nb)]].sum()) / max(float(dep_b.sum()), 1):.1f} %, "
                        f"{int((sp_f < 1).sum() // 2)} buildings front two streets")
            flow = np.zeros(E); tt = t0.copy(); T3 = 1.0 / PASSES; one = K[ri] != 0
            for it in range(PASSES):
                w = np.where(open_mask, tt, tt * 20 + 30) * rng.uniform(NOISE[0], NOISE[1], E)
                wb = np.where(one, w[ri] * WRONG_WAY[0] + WRONG_WAY[1], w[ri])
                Gc = _min_csr(np.r_[A[ri], Bn[ri], sr, gates], np.r_[Bn[ri], A[ri], sc_, np.full(len(gates), sink)],
                              np.r_[w[ri], wb, np.full(len(sr), 1e-4), gcost], NT)
                dist, pred = dijkstra(Gc, directed=True, indices=n + np.arange(R), return_predecessors=True)
                te_q = np.where(qee >= 0, w[np.maximum(qee, 0)], 0.0); te_p = np.where(pee >= 0, w[np.maximum(pee, 0)], 0.0)
                CH = 256
                for c0 in range(0, R, CH):
                    c1 = min(R, c0 + CH); rr = np.arange(c0, c1); nr = c1 - c0; dd = dist[c0:c1]
                    # arrivals at the workplaces of every cell from these rows, at the nearer end of their street piece
                    amt = F[c0:c1][:, qc] * (qW * T3)[None, :]
                    da = dd[:, qa] + (qT * te_q)[None, :]; db = dd[:, qn] + ((1 - qT) * te_q)[None, :]
                    idx = [((rr - c0)[:, None] * NT + np.where(da <= db, qa[None, :], qn[None, :])).ravel()]; val = [amt.ravel()]
                    sel = (prow >= c0) & (prow < c1)                   # departures of the homes in these rows' own cells
                    if sel.any():
                        r_ = prow[sel]; da2 = dist[r_, pa[sel]] + pT[sel] * te_p[sel]; db2 = dist[r_, pn[sel]] + (1 - pT[sel]) * te_p[sel]
                        idx.append((r_ - c0) * NT + np.where(da2 <= db2, pa[sel], pn[sel])); val.append(pW[sel] * T3)
                    vr = veh[srcs[c0:c1]] * ext_share * T3                # external trips (gen_twin's shares): to Almaty and Konaev
                    idx += [(rr - c0) * NT + sink, (rr - c0) * NT + konaev]; val += [vr * 0.8, vr * 0.2]
                    dem = np.bincount(np.concatenate(idx), np.concatenate(val), nr * NT).reshape(nr, NT)
                    dem[np.arange(nr), n + rr] = 0
                    _tree_flows(pred[c0:c1].astype(np.int64), dd, dem, arc_keys, S, NT, flow)
                flow += acc_flow * T3
                tt = t0 * (1 + 0.15 * np.minimum(flow / capY, 1.6) ** 4)
            flow = np.where(carless, 0.0, flow)
            vc = flow / capY
            used = open_mask & (flow > 0)
            delay = 100 * float(((tt - t0) * flow)[used].sum() / max((t0 * flow)[used].sum(), 1))
            enc = np.minimum(255, np.round(vc * 100)).astype(int); enc = np.where((flow > 0.01) & (enc < 1), 1, enc); enc = np.where(open_mask, enc, 0)
            out[s][Y] = {"vc": [int(v) for v in enc],
                         "kpi": {"car_trips": round(float(veh.sum())), "lrt_trips": round(float((persons * lrt_share).sum())),
                                 "congested_km": TC.r1(float(Lm[open_mask & (vc > 0.85)].sum()) / 1000), "avg_delay_pct": TC.r1(delay)}}
    log(f"  traffic: {nb} buildings with trips ({int((res_b > 0).sum())} homes, {int((jobs_b > 0).sum())} with jobs), {NC} cells, "
        f"{int(drive.sum())} drive edges ({len(set(ap_b.tolist()))} buildings reach their street by a drive), {int(carless.sum())} carless edges, "
        f"{int(isz.sum())} landmark lot rows on the {len(set(ze.tolist()))} street pieces of their lots, "
        f"Almaty by {len(gates)} road ends at the south edge, {PASSES} passes in {time.time() - t_s:.0f} s; {diag}")
    return out, {"almaty": int(almaty), "konaev": int(konaev)}


# ------------------------------------------------------------------ flood (gen_risk.py) with rivers from layer_infrastructure
def river_points(infra_objs):
    """Centre points every ≤ 25 m of the «Rivers» ribbon with its width and water level (the y of the ribbon)."""
    o = next(x for x in infra_objs if x[0] == "Rivers")
    V, T = np.asarray(o[2], float), np.asarray(o[3], np.int64)
    pairs = set()
    for t in T:
        a, b, c = sorted(int(v) for v in t)
        cand = [(a, b), (a, c), (b, c)]
        u, w = max(cand, key=lambda q: q[1] - q[0]); pairs.add((u, w))
    pairs = sorted(pairs)
    mids = {u: ((V[u] + V[w]) / 2, float(np.linalg.norm(V[u, [0, 2]] - V[w, [0, 2]]))) for u, w in pairs}
    pts, z, wd = [], [], []
    for u in sorted(mids):
        m, width = mids[u]; pts.append((m[0], m[2])); z.append(m[1]); wd.append(width)
        nx = mids.get(u + 1)
        if nx is not None:
            m2 = nx[0]; L = math.hypot(m2[0] - m[0], m2[2] - m[2]); k = int(L // 25)
            for i in range(1, k + 1):
                t = i / (k + 1); pts.append((m[0] + (m2[0] - m[0]) * t, m[2] + (m2[2] - m[2]) * t)); z.append(m[1] + (m2[1] - m[1]) * t); wd.append(width)
    return np.array(pts), np.array(z), np.array(wd)


def risk(B, ground, infra_objs):
    pts, z, wd = river_points(infra_objs)
    m = wd >= 20; kd = cKDTree(pts[m]); z = z[m]
    nb = max(b["bid"] for b in B) + 1
    xy = np.array([[b["x"], b["z"]] for b in B]); dist, idx = kd.query(xy)
    res = {}
    for key, name, stage in (("flood_1pct", "Паводок 1 % (раз в 100 лет)", 1.6), ("flood_ext", "Экстремальный паводок 0,1 % + сброс Капшагайской ГЭС", 3.0)):
        depth = np.zeros(nb, dtype=int)
        for k, b in enumerate(B):
            dpt = stage - max(0.0, ground[b["bid"]] - z[idx[k]]) - dist[k] / 400.0
            if dist[k] < 1200 and dpt > 0.05:
                depth[b["bid"]] = int(round(min(dpt, 6.0) * 100))
        res[key] = {"name": name, "stage_m": stage, "depth_cm": depth.tolist()}
    return {"scenarios": res, "river_dist_m": []}


# ------------------------------------------------------------------ the run
def norms_speed(norms, t):
    sp = (norms.get("street_profiles", {}).get(t) or {}).get("speed_kmh")
    v = sp.get("value") if isinstance(sp, dict) else sp
    if isinstance(v, dict):
        v = v.get("design") or v.get("from_I_II_min") or v.get("separated") or next((x for x in v.values() if isinstance(x, (int, float))), None)
    return float(v) if isinstance(v, (int, float)) else None


CAP_LANE = {"expressway": 2000, "ramp": 1600, "arterial_road_regulated": 900, "arterial_continuous": 1000, "arterial_regulated": 900,
            "district_transport": 800, "district_pedestrian": 700, "driveway_main": 400, "driveway_secondary": 300, "village_lane": 300}


def rerun(roads, bcsv, base_twin, infra_objs, ground, version, lrt_block, norms, log, place=None, fronts=None):
    """roads: merged roads.json dict (edges may carry t, k, p; top-level profiles). Returns {name: obj} of the twin json files.
    place(F): moves gen_twin's synthetic facilities (they stand at load centres snapped to a road) to real sites before the
    networks are routed (merge_districts.facility_sites). fronts: bid → lot polygon of the landmark lot rows (traffic())."""
    import time
    t_start = time.time(); T = [t_start]

    def tick(what):
        log(f"  twin re-run: {what} {time.time() - T[0]:.0f} s"); T[0] = time.time()
    B = TC.load_buildings(bcsv)
    nodes = [tuple(p) for p in roads["nodes"]]
    prof = roads.get("profiles") or []
    edges = []
    for e in roads["edges"]:
        g = e["g"]; geom = [(g[i], g[i + 1]) for i in range(0, len(g), 2)]
        edges.append({"a": e["a"], "b": e["b"], "cls": e["c"], "len": float(e["len"]), "geom": geom,
                      "year": {s: e["y"][i] for i, s in enumerate(SCEN)}, "t": e.get("t"), "k": e.get("k", 0), "p": e.get("p"),
                      "sv": e.get("sv"), "ps": e.get("ps")})
    used = set(e["a"] for e in edges) | set(e["b"] for e in edges)
    kd = NodeTree(nodes, used)
    cells = GT.demand_cells(B)
    DS = GT.district_series(B)
    geo = geo_substitute(load_base(base_twin, "networks"))
    F = GT.build_facilities(geo, B, cells, kd)
    if place is not None:
        place(F)
    serve = GT.assign_service(F, cells)
    GT.plan_all(F, cells, serve)
    tick("facilities")
    # utility networks avoid ramps, structures and paths without cars (pipes and cables follow streets)
    carless, drive = edge_kinds(edges, prof)[:2]
    net_edges = [dict(e, len=e["len"] * (4.0 if (e["k"] == 2 or carless[i] or drive[i]) else 1.0)) for i, e in enumerate(edges)]
    nets = GT.networks(F, cells, serve, nodes, net_edges, kd)
    tick("networks")
    lrt = lrt_block
    dur, con, delay = GT.construction(B)
    sc = GT.s_curves(B, dur, delay)
    fin = GT.finance(B, dur, delay, F, nets, edges, lrt)
    soc = GT.social(B)
    tick("construction, finance, social")
    # capacity and free time per edge: the class (as today) or, for edges with a street profile, the profile's lanes
    cap = []; t0 = []; stages = []

    def lanes_cap(e, p, i):
        lanes, c, v = GR.CLASSES[e["cls"]]
        t = e["t"]
        if t and p is not None and 0 <= p < len(prof):
            pl = prof[p].get("lanes") or [lanes, lanes]
            lanes = max(1, max(pl) if e["k"] == 0 else pl[0])
            c = CAP_LANE.get(t, c); v = norms_speed(norms, t) or v
        if carless[i]:
            lanes, c, v = 1, 1, 0.1
        return lanes * c, v
    for i, e in enumerate(edges):
        c, v = lanes_cap(e, e["p"], i)
        cap.append(c); t0.append(e["len"] / 1000 / v * 60)
        for st in e.get("ps") or []:        # a reconstruction (network `stages`, roads.json `ps`): its lanes from its years
            stages.append((i, {s: st["y"][k] for k, s in enumerate(SCEN)}, lanes_cap(e, st["p"], i)[0]))
    cap = np.array(cap, float); t0 = np.maximum(np.array(t0), 0.01)
    tr, ext = traffic(nodes, edges, B, lrt, cap, t0, prof, log=log, fronts=fronts, stages=stages)
    tick("traffic")
    rk = risk(B, ground, infra_objs)
    log(f"twin re-run: {len(B)} buildings, {len(edges)} edges, {len(cells)} cells, {len(F)} facilities in {time.time() - t_start:.0f} s")
    return dump_all(version, edges, nets, F, DS, soc, dur, con, delay, sc, lrt, fin, tr, rk), ext, {"nets": nets, "F": F}


def load_base(base_twin, name):
    return U.load_json(os.path.join(base_twin, "StreamingAssets/twin", name + ".json"))


def dump_all(version, edges, nets, F, DS, soc, dur, con, delay, sc, lrt, fin, tr, rk):
    """gen_twin.main's output section (same objects, same order of keys), with the data version passed in."""
    about_common = {"sources": N.SOURCES, "note": "Демо-сценарий: все числа — модель, не официальные данные."}
    out = {}

    def put(name, obj, about):
        out[name] = {"about": about, "version": version, **obj}
    fac_out = []
    for f in F:
        st = f["stages"]
        o = {k: f[k] for k in ("id", "name", "kind", "res", "x", "z", "unit", "district", "synthetic", "note")}
        o["stages"] = [st[s] for s in SCEN]
        o["head"] = TC.r1(f.get("head", 0.0))
        o["cap"] = [GT.capacity_series(st[s], f["unit"], f.get("head", 0.0)) for s in SCEN] if f["res"] not in ("telecom",) else None
        o["delayed_stages"] = sorted(int(k) + 1 for k in f.get("delays", {}))
        o["demand"] = [f["demand"][s] for s in SCEN] if f.get("demand") else None
        fac_out.append(o)
    fid = {f["id"]: i for i, f in enumerate(F)}
    net_out = {}
    for res, seg in nets.items():
        net_out[res] = [[ei, GT.pipe_size(res, sg["load"]) if res not in ("power", "telecom") else (220 if sg["load"] > 150 else 110 if res == "power" else 0),
                         *[sg["year"][s] for s in SCEN], fid[sg["fac"]], TC.r1(sg["load"])] for ei, sg in sorted(seg.items())]
    put("networks", {"facilities": fac_out, "networks": net_out,
        "net_fields": ["road_edge", "size (DN мм / кВ)", "year_base", "year_fast", "year_slow", "year_infra", "facility", "load_2050"],
        "units": {"power_hv": "МВт", "power": "МВт", "heat": "Гкал/ч", "gas": "м³/ч", "water": "м³/сут (макс. сутки)", "sewer": "м³/сут", "renewable": "МВт"},
        "designed_delays": [{"facility": f["id"], "name": f["name"], "stage": int(k) + 1, "years": d} for f in F for k, d in f.get("delays", {}).items()],
        "headroom_note": "head = существующие сети и временные подключения (30 % одного этапа; для ПС 220 кВ — 0) до ввода первого нового этапа"},
        {**about_common, "what": "Объекты инфраструктуры (этапы ввода и мощность по сценариям) и магистральные сети вдоль улиц"})
    balance = {}
    for s in SCEN:
        si = SCEN.index(s); balance[s] = {}
        for res in ("power_hv", "power", "heat", "sewer", "water", "gas"):
            fac = [o for o in fac_out if o["res"] == res]
            dem_city = np.sum([f["demand"][si] for f in fac], axis=0); cap_city = np.sum([f["cap"][si] for f in fac], axis=0)

            def unserved(fl):
                return np.sum([np.maximum(0, np.array(f["demand"][si]) - np.array(f["cap"][si])) for f in fl], axis=0) if fl else np.zeros(TC.NY)
            per_d = []
            for d in range(4):
                fd = [o for o in fac if o["district"] == d]
                if res in GT.POOLED or not fd:
                    per_d.append(None); continue
                per_d.append({"demand": [TC.r1(v) for v in np.sum([f["demand"][si] for f in fd], axis=0)], "cap": [TC.r1(v) for v in np.sum([f["cap"][si] for f in fd], axis=0)],
                              "deficit": [TC.r1(v) for v in unserved(fd)]})
            city_def = np.maximum(0, dem_city - cap_city) if res in GT.POOLED else unserved(fac)
            balance[s][res] = {"city": {"demand": [TC.r1(v) for v in dem_city], "cap": [TC.r1(v) for v in cap_city], "deficit": [TC.r1(v) for v in city_def]}, "districts": per_d}
    loads = {}
    for s in SCEN:
        L = DS[s]["loads"]
        loads[s] = {k: [[TC.r1(v) for v in L[d, GT.LOAD_KEYS.index(k)]] for d in range(4)] for k in GT.LOAD_KEYS if k != "gfa"}
        loads[s]["gfa"] = [[[TC.r1(v / 1e6) for v in DS[s]["gfa"][d, c]] for c in range(len(GT.CATS))] for d in range(4)]
    put("loads", {"years": TC.YEARS, "districts": TC.DISTRICTS, "cats": GT.CATS, "loads": loads, "balance": balance, "social": soc,
        "social_keys": ["школы, мест", "детсады, мест", "больницы, коек", "поликлиники, посещ./смену"],
        "norms": {k: getattr(N, k) for k in dir(N) if k.isupper() and k not in ("SOURCES",)}},
        {**about_common, "what": "Население, рабочие места, нагрузки на сети и социальная инфраструктура по районам и годам"})
    put("construction", {"contractors": [{"name": n, "delay_rate": r} for n, r in GT.CONTRACTORS],
        "per_building": {"duration_years": dur, "contractor": con, "delay_months": delay}, "s_curves": sc, "lrt": lrt},
        {**about_common, "what": "Стройка: длительность, генподрядчик и задержка по каждому зданию (bid); S-кривые план/факт, млн м²; ЛРТ по очередям"})
    put("finance", {"unit": "млрд ₸, цены 2026 г.", "cats": GT.CATS, "funding": N.FUNDING_KEYS, "cost_tg_m2": N.COST_TG_M2,
        "infra_cost_bln": N.COST_BLN, "by_scenario": fin}, {**about_common, "what": "CAPEX по годам, районам, назначению и источникам; инфраструктура по видам"})
    put("traffic", {"years": [2030, 2035, 2040, 2045, 2050], "by_scenario": {s: {str(y): v for y, v in tr[s].items()} for s in SCEN},
        "vc_note": "загрузка ребра в утренний час пик ×100 (100 = на пределе пропускной способности); 1 — машины есть, но загрузка < 1 %; "
                   "0 — машин нет: ребро ещё не открыто или по проекту без машин (пешеходная улица, велодорожка, бульвар без полос)"},
        {**about_common, "what": "Утренний час пик: загрузка дорог по годам и сценариям (гравитационная модель, BPR; поездки от зданий по "
                                 "улицам, на которые они выходят, и по их проездам; через проезды маршрутов нет)"})
    put("scenarios", {"scenarios": [
        {"id": "base", "name": "Базовый (генплан)", "pace": 1.0, "desc": "Годы ввода из сценария застройки QTwin; сети вводятся за год до нагрузки, но 4 объекта запаздывают."},
        {"id": "fast", "name": "Ускоренный", "pace": 1.33, "desc": "Темп +33 %: жильё и бизнес раньше, сети успевают лишь частично — растут дефициты."},
        {"id": "slow", "name": "Отставание", "pace": 0.77, "desc": "Темп −23 %: задержки финансирования, часть города не успевает к 2050, сети простаивают."},
        {"id": "infra", "name": "Приоритет инфраструктуры", "pace": 1.0, "desc": "Сети и ЛРТ на 2 года раньше, жильё первой очереди ждёт сети: дефицитов нет, но вложения раньше."}],
        "formula": "year_effective = f(year_plan): fast 2025 + round(0.75·Δ), slow 2025 + round(1.3·Δ), infra: жильё ≤ 2036 +2 года"},
        {**about_common, "what": "Сценарии развития"})
    out["risk"] = {"about": {"what": "Подтопление зданий при паводках (модель): глубина воды у здания, см; bid → см",
                             "note": "Демо-модель: уровень воды над урезом рек шириной ≥ 20 м, затухание 2,5 м на км. Не заменяет гидрологический расчёт."},
                   "version": version, **rk}
    return out
