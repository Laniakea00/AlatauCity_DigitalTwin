"""The ends of the Gate District's streets at the edge of its area (Resources/Landmarks/gate_district.bytes, made by
build_gate_district.py): the page's ground was kept by the centre of each piece, so where a street meets the round of the area
its asphalt ends in a sawtooth of needles (long thin triangles on the edge of the asphalt) over the paving, and the city's street
outside starts behind a band of paving. This drops the needles of the asphalt near the edge and lays each street that runs out to
the edge (a centre line of Resources/Film/Traffic/gate_roads.json ending within EDGE_M of the round) on to the round at its own
width, so it meets the city's street there (IconicDistrict.ClipGround cuts the ground at the round). The rest of the file (trees,
mask) is kept byte for byte. Run it once on a file fresh from build_gate_district.py (applied 03.11.2026): a second run finds
new needles in its own fill and adds more asphalt.
usage: python fix_gate_road_ends.py [gate_district.bytes] [gate_roads.json] [--plot out.png]"""
import collections
import gzip
import json
import struct
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

ROOT = __file__.replace("\\", "/").rsplit("/tools/", 1)[0] + "/UnityProject/Assets/Resources"
PLOT = sys.argv[sys.argv.index("--plot") + 1] if "--plot" in sys.argv else None
args = [a for a in sys.argv[1:] if not a.startswith("--") and a != PLOT]
GD = args[0] if len(args) > 0 else ROOT + "/Landmarks/gate_district.bytes"
GR = args[1] if len(args) > 1 else ROOT + "/Film/Traffic/gate_roads.json"

ASPHALT = 31              # the district's surface tags (AlatauQTwin.cginc): 31 asphalt
R_AREA = 336.0            # the round of the area (IconicFrame.AreaR from the mask: 336 m)
EDGE_M = 40.0             # a street end this near the round runs out to it
NEEDLE_DEG = 12.0         # a needle: its smallest angle under this, its long edge on the edge of the asphalt
NEEDLE_R = 220.0          # only near the edge of the area
Y_ASPH = 0.45             # the height of the page's asphalt
U_MID = 1.8               # facade u of the new asphalt: between two lane lines (QLine(u, 3.6, …))

raw = gzip.decompress(open(GD, "rb").read())
assert raw[:4] == b"QGD1", "unknown format"
o = 4
nv, ni = struct.unpack_from("<ii", raw, o); o += 8
P = np.frombuffer(raw, "<f4", nv * 3, o).reshape(-1, 3).copy(); o += nv * 12
N = np.frombuffer(raw, "i1", nv * 3, o).reshape(-1, 3).copy(); o += nv * 3
U = np.frombuffer(raw, "<f4", nv, o).copy(); o += nv * 4
T = np.frombuffer(raw, "u1", nv, o).copy(); o += nv
I = np.frombuffer(raw, "<u4", ni, o).reshape(-1, 3).copy(); o += ni * 4
rest = raw[o:]

tri = P[I][:, :, [0, 2]]
tag = T[I[:, 0]]
ground = P[I][:, :, 1].max(1) < 1.0
asp = np.where(ground & (tag == ASPHALT))[0]


def key(p):
    return round(float(p[0]), 2), round(float(p[1]), 2)


edges = collections.Counter(tuple(sorted((key(tri[t, k]), key(tri[t, (k + 1) % 3])))) for t in asp for k in range(3))
needles = set()
for t in asp:
    p = tri[t]
    L = [float(np.linalg.norm(p[(k + 1) % 3] - p[k])) for k in range(3)]
    k = int(np.argmax(L))
    a, b, c = sorted(L)
    if b * c <= 1e-9:
        needles.add(int(t))
        continue
    ang = np.degrees(np.arccos(np.clip((b * b + c * c - a * a) / (2 * b * c), -1.0, 1.0)))
    if ang < NEEDLE_DEG and edges[tuple(sorted((key(p[k]), key(p[(k + 1) % 3]))))] == 1 and np.hypot(*p.mean(0)) > NEEDLE_R:
        needles.add(int(t))
A = unary_union([Polygon(tri[t]) for t in asp if t not in needles]).buffer(0)

# the street ends at the round: the last 30 m of the centre line, its width read off the asphalt 25 m before the end
roads = json.load(open(GR, encoding="utf-8"))["roads"]
deg = collections.Counter()
lines = []
for r in roads:
    q = np.array(r["p"], float).reshape(-1, 3)[:, [0, 2]]
    if len(q) >= 2:
        lines.append(q)
        deg[key(q[0])] += 1
        deg[key(q[-1])] += 1
strips = []
for q in lines:
    for end, prev in ((q[-1], q[-2]), (q[0], q[1])):
        if deg[key(end)] != 1 or np.hypot(*end) < R_AREA - EDGE_M:
            continue
        d = end - prev
        d /= max(np.linalg.norm(d), 1e-9)
        n = np.array([-d[1], d[0]])
        probe = end - d * 25.0
        cut = LineString([probe - n * 30.0, probe + n * 30.0]).intersection(A)
        piece = min(getattr(cut, "geoms", [cut]), key=lambda g: g.distance(Point(probe)), default=None) if not cut.is_empty else None
        if piece is None or piece.is_empty or piece.distance(Point(probe)) > 1.0:
            continue
        w = piece.length
        if not 4.0 <= w <= 40.0:
            continue
        a0, a1 = probe, end + d * 12.0
        strips.append(Polygon([a0 - n * w / 2, a1 - n * w / 2, a1 + n * w / 2, a0 + n * w / 2]))
fill = unary_union(strips).difference(A).buffer(-0.02).buffer(0.02) if strips else Polygon()
fill = [g for g in getattr(fill, "geoms", [fill]) if g.geom_type == "Polygon" and g.area > 1.0]

# the new triangles (constrained Delaunay of each piece, kept where their centre is in the piece)
newP, newI = [], []
for g in fill:
    for t in getattr(shapely.constrained_delaunay_triangles(g), "geoms", []):
        c = list(t.exterior.coords)[:3]
        if not g.buffer(0.01).contains(t.centroid):
            continue
        # counter-clockwise in (x, z) seen from above in Unity (left-handed: clockwise in x-z)
        (x0, z0), (x1, z1), (x2, z2) = c
        if (x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0) > 0:
            c = [c[0], c[2], c[1]]
        b0 = nv + len(newP)
        newP += [(x, Y_ASPH, z) for x, z in c]
        newI.append((b0, b0 + 1, b0 + 2))

keep = np.array([t for t in range(len(I)) if t not in needles], int)
I2 = np.vstack([I[keep], np.array(newI, np.int64).reshape(-1, 3)]).astype("<u4")
k = len(newP)
P2 = np.vstack([P, np.array(newP, np.float32).reshape(-1, 3)]).astype("<f4")
N2 = np.vstack([N, np.tile(np.array([0, 127, 0], np.int8), (k, 1))]).astype("i1")
U2 = np.concatenate([U, np.full(k, U_MID, np.float32)]).astype("<f4")
T2 = np.concatenate([T, np.full(k, ASPHALT, np.uint8)]).astype("u1")
print(f"needles dropped {len(needles)}, street ends laid to the round {len(strips)}, new asphalt {sum(g.area for g in fill):.0f} m² "
      f"in {len(newI)} triangles")

if PLOT:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    t2 = P2[I2][:, :, [0, 2]]
    g2 = P2[I2][:, :, 1].max(1) < 1.0
    tg2 = T2[I2[:, 0]]
    fig, ax = plt.subplots(figsize=(14, 14))
    ax.add_collection(PolyCollection(t2[g2 & (tg2 != ASPHALT)], facecolor="#ccc", edgecolor="none"))
    ax.add_collection(PolyCollection(t2[g2 & (tg2 == ASPHALT)], facecolor="#333", edgecolor="none"))
    for g in fill:
        x, y = g.exterior.xy
        ax.fill(x, y, color="#e33", alpha=0.8)
    th = np.linspace(0, 2 * np.pi, 720)
    ax.plot(R_AREA * np.cos(th), R_AREA * np.sin(th), "b-", lw=1)
    ax.set_xlim(-360, 360); ax.set_ylim(-360, 360); ax.set_aspect("equal")
    plt.savefig(PLOT, dpi=80, bbox_inches="tight")
    sys.exit(0)

body = b"QGD1" + struct.pack("<ii", len(P2), I2.size) + P2.tobytes() + N2.tobytes() + U2.tobytes() + T2.tobytes() + I2.tobytes() + rest
open(GD, "wb").write(gzip.compress(body, 9))
print("written", GD)
