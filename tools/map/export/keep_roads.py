"""Streets of the keep quarters (CONTRACT §4 `keep`) as roads.json edges (w45).

The Gate District quarter round Iconic Complex is drawn in Unity from its own model (gate_district.bytes) and its cars run on its own
centre lines (Resources/Film/Traffic/gate_roads.json, the landmark's local frame; FilmTraffic.AddGateWays). Neither is in the twin's
road graph, so before this the 16 district streets that reach the quarter ended at its edge and no route reached the landmark.

This module turns those centre lines into a road graph at the quarter's place:
  - the place is Iconic's entry of LandmarkData.cs (IconicX, IconicZ, IconicYaw: the one source of truth, as for IconicFrame);
    world = (X + x·cos a + z·sin a, Z − x·sin a + z·cos a), a = yaw, the rotation FilmTraffic uses;
  - the traced centre lines stop short of the asphalt they meet, so a free end within KEEP_GAP_M of another line joins it there
    (a T-junction: that line is split and a short link closes the gap); a loose piece (the inner carriageway of the ring) joins the
    rest at its nodes within KEEP_LINK_M;
  - the ring (both carriageways) is one-way counterclockwise, the two small roundabouts one-way in point order, the rest two-way
    (as FilmTraffic drives them); the ring is t district_transport (c main), every other piece t local (c street); no profile;
  - heights: the quarter's ground as Unity grades it (IconicFrame.Grade: the best-fitting plane through the 50 m grid nodes inside
    the area, never steeper than 3 %, full weight up to 60 m from the edge, fading to the edge) plus the centre line's own lift;
  - district joints next to the quarter (its `attach` points) join a quarter street: the end node when within SNAP_M, else a split
    within KEEP_STITCH_M.
merge_districts.py lists every keep edge (and every link into it) in film_roads `drop`: the film never draws them (the quarter's
model does), and FilmRoads.Dropped keeps street trees off them."""
import gzip
import json
import math
import os
import re
import struct

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point

import util as U

KEEP_GAP_M = 16.0     # a free end of a quarter street this close to another quarter street is its junction
KEEP_LINK_M = 25.0    # a loose piece of the quarter joins the rest at its nodes within this
KEEP_STITCH_M = 30.0  # a district joint this close to a quarter street joins it (split there when not at an end)
END_M = 0.5           # ends of quarter streets this close are one node
SPLIT_END_M = 1.0     # a split this close to an end of its line takes the end node
GATE_ROADS = "Resources/Film/Traffic/gate_roads.json"
GATE_MODEL = "Resources/Landmarks/gate_district.bytes"
LANDMARK_DATA = os.path.join(U.REPO, "UnityProject", "Assets", "Scripts", "DigitalTwin", "Landmarks", "LandmarkData.cs")


def iconic_place():
    """(X, Z, yaw°) of Iconic from LandmarkData.cs, or None."""
    try:
        src = open(LANDMARK_DATA, encoding="utf-8").read()
    except OSError:
        return None
    v = {}
    for k in ("IconicX", "IconicZ", "IconicYaw"):
        m = re.search(k + r"\s*=\s*(-?[0-9.]+)f", src)
        if not m:
            return None
        v[k] = float(m.group(1))
    return v["IconicX"], v["IconicZ"], v["IconicYaw"]


def area_radius(base):
    """Radius of the quarter's mask (gate_district.bytes, as IconicFrame.AreaR reads it), or None."""
    try:
        b = gzip.open(os.path.join(base, GATE_MODEL)).read()
    except OSError:
        return None
    n = len(b)
    for W in range(16, 4097):                   # the file ends with i32 W, f32 half, W × W mask bytes
        o = n - W * W - 8
        if o < 4:
            break
        if struct.unpack_from("<i", b, o)[0] != W:
            continue
        half = struct.unpack_from("<f", b, o + 4)[0]; m = np.frombuffer(b, np.uint8, W * W, o + 8).reshape(W, W)
        iz, ix = np.nonzero(m > 127); cell = 2 * half / W
        if not len(ix):
            return None
        lx = -half + (ix + 0.5) * cell; lz = -half + (iz + 0.5) * cell
        r = float(np.sqrt((lx * lx + lz * lz).max()))
        return r if r > 50 else None
    return None


class Graded:
    """The terrain with the quarter's ground graded as Unity does it (IconicFrame.Grade, w46 e40f883): the plate (every grid cell the
    plot w × d touches) level at the median of its nodes, the other nodes inside r moved as little as they can by relaxation while no step
    between neighbours is steeper than 3 % (1.5 m per 50 m); then the plot itself levelled 5 cm under the plate (LandmarkSystem)."""
    STEP_SLOPE = 0.03

    def __init__(self, terrain, cx, cz, R, yaw=0.0, w=0.0, d=0.0):
        self.nx, self.ny, self.step, self.x0, self.z0 = terrain.nx, terrain.ny, terrain.step, terrain.x0, terrain.z0
        h = terrain.h.copy(); S = self.step; NX, NY = self.nx, self.ny
        self.cut = self.fill = 0.0; self.nodes = 0; self.plate = float("nan"); self.plate_nodes = 0; self.h = h
        c0 = max(1, math.floor((cx - R - self.x0) / S) - 1); c1 = min(NX - 2, math.ceil((cx + R - self.x0) / S) + 1)
        r0 = max(1, math.floor((cz - R - self.z0) / S) - 1); r1 = min(NY - 2, math.ceil((cz + R - self.z0) / S) + 1)
        W, Hn = c1 - c0 + 1, r1 - r0 + 1
        if W < 3 or Hn < 3:
            return
        T = [[float(h[r0 + r, c0 + c]) for c in range(W)] for r in range(Hn)]
        kind = [[0] * W for _ in range(Hn)]
        for r in range(1, Hn - 1):
            for c in range(1, W - 1):
                dx = self.x0 + (c0 + c) * S - cx; dz = self.z0 + (r0 + r) * S - cz
                if dx * dx + dz * dz < R * R:
                    kind[r][c] = 1
        a = math.radians(yaw); ca, sa = math.cos(a), math.sin(a); hw, hd = w * 0.5, d * 0.5
        ux, uz, vx, vz = ca, -sa, sa, ca

        def hits(x0, z0, x1, z1):                       # LandmarkSystem.ObbHitsAabb
            ex = abs(ux) * hw + abs(vx) * hd; ez = abs(uz) * hw + abs(vz) * hd
            if cx + ex < x0 or cx - ex > x1 or cz + ez < z0 or cz - ez > z1:
                return False
            bx, bz, bhx, bhz = (x0 + x1) * 0.5 - cx, (z0 + z1) * 0.5 - cz, (x1 - x0) * 0.5, (z1 - z0) * 0.5
            if abs(bx * ux + bz * uz) > hw + bhx * abs(ux) + bhz * abs(uz):
                return False
            return abs(bx * vx + bz * vz) <= hd + bhx * abs(vx) + bhz * abs(vz)
        plate = []
        if w > 0 and d > 0:
            for r in range(Hn - 1):
                for c in range(W - 1):
                    x0, z0 = self.x0 + (c0 + c) * S, self.z0 + (r0 + r) * S
                    if not hits(x0, z0, x0 + S, z0 + S):
                        continue
                    for q in range(4):
                        rr, cc = r + (q >> 1), c + (q & 1)
                        if kind[rr][cc] == 1:
                            kind[rr][cc] = 2; plate.append(T[rr][cc])
        if plate:
            plate.sort(); lvl = plate[len(plate) // 2]; self.plate = lvl; self.plate_nodes = len(plate)
            for r in range(Hn):
                for c in range(W):
                    if kind[r][c] == 2:
                        T[r][c] = lvl
        st = self.STEP_SLOPE * S; sd = st * 1.41421356
        nb = [(dr, dc, sd if dr and dc else st) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]
        for _ in range(400):
            ch = 0.0
            for r in range(1, Hn - 1):
                for c in range(1, W - 1):
                    if kind[r][c] != 1:
                        continue
                    lo, hi = -1e30, 1e30
                    for dr, dc, m in nb:
                        t = T[r + dr][c + dc]; lo = max(lo, t - m); hi = min(hi, t + m)
                    v = T[r][c]; nv = (lo + hi) * 0.5 if lo > hi else min(max(v, lo), hi)
                    ch = max(ch, abs(nv - v)); T[r][c] = nv
            if ch < 0.001:
                break
        for r in range(1, Hn - 1):
            for c in range(1, W - 1):
                if kind[r][c] == 0:
                    continue
                dh = T[r][c] - h[r0 + r, c0 + c]
                if abs(dh) < 0.01:
                    continue
                h[r0 + r, c0 + c] = T[r][c]; self.nodes += 1; self.cut = max(self.cut, -dh); self.fill = max(self.fill, dh)
        if plate:                                       # the plot levelled 5 cm under the plate (CityGround.Flatten, 1 m edge)
            for r in range(max(0, r0 - 2), min(NY, r1 + 3)):
                for c in range(max(0, c0 - 2), min(NX, c1 + 3)):
                    dx = self.x0 + c * S - cx; dz = self.z0 + r * S - cz
                    if abs(dx * ux + dz * uz) <= hw and abs(dx * vx + dz * vz) <= hd:
                        h[r, c] = self.plate - 0.05

    height = U.Terrain.height


def iconic_pad():
    """(PadW, PadD) of Iconic from LandmarkData.cs, or (0, 0)."""
    try:
        src = open(LANDMARK_DATA, encoding="utf-8").read()
    except OSError:
        return 0.0, 0.0
    m = re.search(r'Id\s*=\s*"iconic".*?PadW\s*=\s*([0-9.]+)f,\s*PadD\s*=\s*([0-9.]+)f', src, re.S)
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)


def gate_lines(base, X, Z, yaw):
    """The quarter's centre lines in world coordinates: [{pts, ly, one, ring}]; None without gate_roads.json."""
    p = os.path.join(base, GATE_ROADS)
    if not os.path.exists(p):
        p = os.path.join(U.REPO, "UnityProject", "Assets", GATE_ROADS)
    if not os.path.exists(p):
        return None
    a = math.radians(yaw); ca, sa = math.cos(a), math.sin(a)
    out = []
    for r in json.load(open(p, encoding="utf-8")).get("roads") or []:
        q = r.get("p") or []; m = len(q) // 3
        if m < 2:
            continue
        loc = [(q[3 * j], q[3 * j + 2]) for j in range(m)]
        e = [(x / 249.5) ** 2 + (z / 202.0) ** 2 for x, z in loc]           # FilmTraffic's test of the ring: the oval ≈ 250 × 200 m
        rl = sum(math.hypot(loc[j][0] - loc[j - 1][0], loc[j][1] - loc[j - 1][1]) for j in range(1, m))
        one = r.get("o") == 1; ring = not one and min(e) > 0.72 and max(e) < 1.15 and rl > 20
        pts = [(X + x * ca + z * sa, Z - x * sa + z * ca) for x, z in loc]
        ly = [q[3 * j + 1] for j in range(m)]
        if ring:                                                             # counterclockwise round the centre
            turn = sum((pts[j][0] - X) * (pts[j + 1][1] - pts[j][1]) - (pts[j][1] - Z) * (pts[j + 1][0] - pts[j][0]) for j in range(m - 1))
            if turn < 0:
                pts.reverse(); ly.reverse()
        out.append({"pts": pts, "ly": ly, "one": one, "ring": ring})
    return out


def build(lines, joints, hfun):
    """Road graph of the quarter. joints: [(id, x, z)] of the district joints near it.
    Returns (nodes [(x, z)], edges [{a, b, pts, h, k, t, link}], joint_map {id: (node, gap)}, stats)."""
    nodes = []
    ends = [(i, j) for i in range(len(lines)) for j in (0, -1)]
    P = np.array([lines[i]["pts"][j] for i, j in ends])
    end_node = {}; tree = cKDTree(P)
    for k, (i, j) in enumerate(ends):                                      # ends within END_M are one node
        if (i, j) in end_node:
            continue
        nodes.append((float(P[k][0]), float(P[k][1]))); n = len(nodes) - 1
        for k2 in tree.query_ball_point(P[k], END_M):
            end_node.setdefault(ends[k2], n)
    for (i, j), n in end_node.items():
        lines[i]["pts"][j] = nodes[n]
    deg = np.bincount([end_node[e] for e in ends], minlength=len(nodes))
    Ls = [LineString(L["pts"]) for L in lines]
    jpos = {jid: (x, z) for jid, x, z in joints}
    marks = [[] for _ in lines]                                             # per line: (metres along, node or None, key)
    links = []                                                              # (node key a, node key b, kind)
    stats = {"t_junctions": 0, "loose_links": 0, "dead_ends": 0}

    def nearest_line(pt, skip=None):
        best = None
        for i, L in enumerate(Ls):
            if i == skip:
                continue
            d = L.distance(Point(pt))
            if best is None or d < best[0]:
                best = (d, i)
        return best

    def mark(i, pt):
        L = Ls[i]; c = L.project(Point(pt))
        if c <= SPLIT_END_M:
            return ("n", end_node[(i, 0)])
        if c >= L.length - SPLIT_END_M:
            return ("n", end_node[(i, -1)])
        for m in marks[i]:
            if abs(m[0] - c) <= SPLIT_END_M:
                return ("m", i, m[0])
        marks[i].append((c,)); return ("m", i, c)

    near_joint = set()
    for (i, j), n in end_node.items():
        if deg[n] != 1:
            continue
        p = nodes[n]
        if any(math.hypot(p[0] - x, p[1] - z) <= U_SNAP for x, z in jpos.values()):
            near_joint.add(n); continue                                     # an attach end: a district street goes on from here
        b = nearest_line(p, skip=i)
        if b and b[0] <= KEEP_GAP_M:
            links.append((("n", n), mark(b[1], p), "gap")); stats["t_junctions"] += 1
        else:
            stats["dead_ends"] += 1
    jmark = {}
    for jid, (x, z) in jpos.items():
        dn = min(((math.hypot(nodes[n][0] - x, nodes[n][1] - z), n) for n in range(len(nodes))), default=(1e9, -1))
        if dn[0] <= U_SNAP:
            jmark[jid] = (("n", dn[1]), dn[0]); continue
        b = nearest_line((x, z))
        if b and b[0] <= KEEP_STITCH_M:
            jmark[jid] = (mark(b[1], (x, z)), b[0])
    # split the lines at their marks
    edges = []

    def key_node(key):
        return key[1] if key[0] == "n" else mnode[(key[1], key[2])]
    mnode = {}
    for i, L in enumerate(lines):
        cs = sorted(m[0] for m in marks[i])
        for c in cs:
            q = Ls[i].interpolate(c); nodes.append((q.x, q.y)); mnode[(i, c)] = len(nodes) - 1
        ch = U.chain(L["pts"]); cuts = [0.0] + cs + [float(ch[-1])]
        ids = [end_node[(i, 0)]] + [mnode[(i, c)] for c in cs] + [end_node[(i, -1)]]
        for k in range(len(cuts) - 1):
            c0, c1 = cuts[k], cuts[k + 1]
            mid = [t for t in range(len(ch)) if c0 + 0.05 < ch[t] < c1 - 0.05]
            pts = [nodes[ids[k]]] + [L["pts"][t] for t in mid] + [nodes[ids[k + 1]]]
            ly = [float(np.interp(c0, ch, L["ly"]))] + [L["ly"][t] for t in mid] + [float(np.interp(c1, ch, L["ly"]))]
            edges.append({"a": ids[k], "b": ids[k + 1], "pts": pts, "ly": ly, "k": 1 if (L["ring"] or L["one"]) else 0,
                          "t": "district_transport" if L["ring"] else "local", "link": False})
    for ka, kb, _ in links:
        a, b = key_node(ka), key_node(kb)
        if a != b:
            edges.append({"a": a, "b": b, "pts": [nodes[a], nodes[b]], "ly": [0.45, 0.45], "k": 0, "t": "local", "link": True})
    # loose pieces (the inner carriageway of the ring): join the largest piece at their nodes within KEEP_LINK_M
    par = list(range(len(nodes)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for e in edges:
        par[find(e["a"])] = find(e["b"])
    used = sorted(set(n for e in edges for n in (e["a"], e["b"])))
    comp = {}
    for n in used:
        comp.setdefault(find(n), []).append(n)
    if len(comp) > 1:
        main = max(comp.values(), key=lambda c: sum(1 for e in edges if find(e["a"]) == find(c[0])))
        mt = cKDTree(np.array([nodes[n] for n in main]))
        for root, ns in comp.items():
            if root == find(main[0]):
                continue
            for n in ns:
                d, k = mt.query(nodes[n])
                if d <= KEEP_LINK_M:
                    m = main[int(k)]
                    edges.append({"a": n, "b": m, "pts": [nodes[n], nodes[m]], "ly": [0.45, 0.45], "k": 0, "t": "local", "link": True})
                    stats["loose_links"] += 1
    for e in edges:
        e["h"] = [round(float(hfun(x, z)) + float(y), 2) for (x, z), y in zip(e["pts"], e["ly"])]
    joint_map = {jid: (key_node(k), gap) for jid, (k, gap) in jmark.items()}
    stats["joints"] = len(joint_map); stats["lines"] = len(lines); stats["edges"] = len(edges)
    return nodes, edges, joint_map, stats


U_SNAP = 2.0          # = merge_districts.SNAP_M


def keep_graph(keep, joints, base, terrain, log):
    """The road graph of one keep entry of a district spec, or None when its streets have no source here."""
    src = str(keep.get("source") or "") + " " + str(keep.get("id") or "")
    if "gate_roads" not in src and keep.get("registry_id") != "iconic_complex":
        return None
    place = iconic_place()
    if place is None:
        log(f"  keep {keep.get('id')}: Iconic's place not found in LandmarkData.cs; its streets are left out")
        return None
    X, Z, yaw = place
    lines = gate_lines(base, X, Z, yaw)
    if not lines:
        log(f"  keep {keep.get('id')}: no {GATE_ROADS}; its streets are left out")
        return None
    R = area_radius(base) or max(math.hypot(x - X, z - Z) for x, z in keep.get("polygon") or [(X + 335, Z)])
    pw, pd = iconic_pad()
    G = Graded(terrain, X, Z, R, yaw, pw + 16.0 if pw else 0.0, pd + 16.0 if pd else 0.0)
    nodes, edges, jm, st = build(lines, joints, G.height)
    log(f"  keep {keep.get('id')}: {st['lines']} centre lines of {GATE_ROADS} at ({X:.0f}, {Z:.0f}) yaw {yaw:.0f} → {st['edges']} edges "
        f"({st['t_junctions']} T-junctions closed, {st['loose_links']} links of the inner ring, {st['dead_ends']} dead ends); ground graded "
        f"as Unity does inside r {R:.0f} m: {G.nodes} nodes moved, plate {G.plate:.2f} m on {G.plate_nodes} nodes (plot {pw:.0f} × {pd:.0f} + 16 m), "
        f"terraced at ≤ {Graded.STEP_SLOPE * 100:.0f} %, cut {G.cut:.1f} m, fill {G.fill:.1f} m")
    return nodes, edges, jm
