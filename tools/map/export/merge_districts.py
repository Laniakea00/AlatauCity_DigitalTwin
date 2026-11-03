#!/usr/bin/env python3
"""Merge of district outputs into the Unity files of the twin (CONTRACT §6), mode «district + current data».

    python3 tools/map/export/merge_districts.py [--districts gate_trial,…] [--base TWIN] --run <name> [--out OUT] [--no-twin] [--keep-solar]

Reads OUT/<d>/{network,lrt,blocks,lots,buildings,features,driveways}.json (+ spec/<d>.json or OUT/<d>/spec.json for `area` and `edge_joints`)
and the current twin (--base, default TWIN). Outside the districts' `area` everything stays as in the base. Writes every Unity file
of §6 to OUT/_merged/<run>/Assets/… and OUT/_merged/<run>/manifest.json (file → md5, size, what changed; bid mapping; log).
With no districts the Unity files are re-encoded from the parsed base (the round-trip proof: they must come out byte-equal) and the
twin computations are re-run on the unchanged data (twin_rerun.py).

Every merge moves the solar panels (kind solar) out of the buildings layer city-wide into Resources/Landmarks/solar.json (fields:
the panel rows of one opening year closed into plant outlines; SolarLayer draws them); their buildings.csv rows stay as they are
(kind solar, no mesh), so bids, per-bid arrays and the twin model do not change. --keep-solar leaves them in the layer (the pure
round trip). The buildings layer is written in parts of ≤ 24 MB (layer_buildings.bytes, layer_buildings_1.bytes, …; AQL1 each, a
building never in two parts; the Unity builder reads them in order) and no file over 24 MB is written at all (the laptop file
channel refuses files over 25 MB).

Driveways (OUT/<d>/driveways.json, w44): every drive segment becomes a roads.json edge (t = its class, c street, heights from the
terrain) after all district streets; each attach node splits its street edge there (the pieces keep the street's fields, `st` re-based)
and the drive starts on the split node. film_roads keeps a split street as one stroke (e = first piece, es = all pieces in order) and
draws each drive as its own stroke with a = −1 / b = −1 at the attach end (no junction patch on the street); turnaround pads are
film_roads `pads` [{n, p, y}]. The traffic re-run never routes through a drive (twin_rerun.py).

Buildings (gen_buildings, w44): buildings.csv gets three columns after the twin's sixteen (CityDatabase reads the first sixteen,
AlatauRoofs reads these by name): `model` (the building's model), `plinth_m` (a building on a slope carries `plinth` {from_y, h_m,
slope_pct}: its walls reach the lowest ground under it and `plinth_m` = base_y − that ground, which AlatauRoofs dresses as a stone
plinth) and `dock` ("x0 z0 x1 z1 n": a class-A shed's dock side and its n doors, which AlatauRoofs draws). A shed's `truck_yard`
becomes film_roads `yards` [{p, y, b, d}] (asphalt, FilmRoads; d = the shed's dock side and doors as in `dock`, for the bay lines)
and a noplant polygon. A canopy (model in CANOPY_MODELS) is extruded as
a roof slab on posts, not as a solid box.

Stitching (merge_roads): a base piece left outside the areas with both ends on the area edge (no base road beyond it) is no end for a
one-way carriageway or ramp joint (a two-way street may go on over it, out and back along the edge); a cut two-way twin road takes one joint traffic leaves the district by and one it enters by (two carriageways, or a ramp and its
carriageway, on one twin line); an expressway or ramp joint takes a cut twin motorway line (highway, ring) before a twin street
beside it; only spec edge joints with a district street hint which twin edge a joint goes on as.

Railway (spec `rail`, Gate v1.2): its lines and platforms become Resources/Landmarks/rail.json (RailLayer draws track, deck, piers,
buffer stops and the platform with its canopy from the line's year), and its corridor and platform polygons noplant polygons."""
import argparse
import bisect
import collections
import itertools
import glob
import math
import os
import sys
import time

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import polylabel, substring, unary_union
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import util as U  # noqa: E402
import keep_roads as KR  # noqa: E402

SNAP_M = 2.0          # a district joint this close to a cut twin road takes the twin node
STITCH_M = 80.0       # farther than SNAP_M but within this: a short link edge; beyond: a logged gap
HINT_M = 10.0         # a spec edge joint's `twin_edge` (the twin edge an OSM road's joint lies on) hints the stitch within this gap
KINDS = ("network", "lrt", "blocks", "lots", "buildings", "features", "driveways")
ZONE_Q = 80.0         # an interchange zone holds this share of its ramps' length …
ZONE_PAD_M = 25.0     # … plus this margin
NOPLANT_PIECE_M = 60.0   # road no-planting strips (decks, ramps, embankments) are cut into pieces this long or shorter: simple rings
NOPLANT_EDGE_M = 1.0     # … reaching this far beyond the outer edge of the deck or ramp, or beyond the foot of the embankment
NOPLANT_SLOPE = 1.5      # an embankment's side slope, horizontal metres per metre of height (CONTRACT §8, off-grade streets)
NOPLANT_RAISED_M = 1.0   # a street piece of `st` code 0 this far above the terrain is on fill too
PAD_PAD_M = 0.5          # a turnaround pad's no-planting ring reaches this far beyond the pad
PAD_SHARE = 0.5          # a pad with at least this share of its area on a plaza (or an apartment or public court) takes that surface
ATTACH_SNAP_M = 1.0  # a drive attach this close to an end (or another attach) of its street edge takes that node instead of a split
DRIVE_SIMPLIFY_M = 0.2   # drive points closer than this to the line through their neighbours are dropped
DNAME = (("gate", "Gate"), ("golden", "Golden"), ("growing", "Growing"), ("green", "Green"))
SRC_CSV = {"model": "generated", "registry": "master_plan", "existing_osm": "existing_osm", "existing_twin": "generated"}
COL = {"res_mid": 0, "res_high": 1, "podium": 2, "public": 3, "tower": 4, "education": 5, "health": 6, "industry": 7, "utility": 8,
       "resort": 9, "solar": 10, "residential": 11, "business": 12, "mixed": 13, "retail": 14, "culture": 17, "hotel": 18, "other": 19,
       "house": 21, "existing": 23}
PLINTH_M = 1.5        # a new building without a `plinth` whose ground falls more than this under its footprint is logged
PLINTH_FROM_TOL_M = 0.2    # the lowest ground merge finds on the outline this far below plinth.from_y is logged (gen_buildings samples inside)
NEW_COLS = ["model", "plinth_m", "dock"]   # buildings.csv columns after the twin's sixteen (module docstring)
WHOLE_CITY = {"gate", "golden", "green", "growing_w", "growing_e"}   # all merged: nothing of the base LRT trunk is kept outside them
CANOPY_MODELS = {"bus_canopy"}             # models drawn as a roof on posts
CANOPY_SLAB_M = 0.5        # … the roof slab's thickness
CANOPY_POST_M = 0.4        # … square posts this wide
CANOPY_POST_STEP_M = 8.0   # … at most this far apart along a row
CANOPY_ROW_M = 10.0        # … one row along the middle of a canopy up to this deep, else a row along each long edge
CANOPY_INSET_M = 0.8       # … the rows and the end posts this far in from the slab's edge
LRT_ON_ROUTE_M = 60.0      # a base LRT station this close to a route the areas clipped belongs to that route
# the twin's synthetic facilities inside the areas (gen_twin puts them at load centres snapped to a road, + 60 m): on a spec utility lot
# meant for them, else on free ground (no lot, outside red lines and interchange zones, clear of buildings) nearest their model place
FAC_KIND_WORDS = {"substation_hv": ("220/110", "ПС 220", "питающ"), "substation": ("ПС 110", "110/10", "подстанц"),
                  "boiler": ("котельн", "boiler"), "agrs": ("АГРС", "газорегулятор")}
# … else a utility zone of the same trade: an engineering hub hosts any of them, an energy corridor the substations
FAC_HUB_WORDS = {"substation_hv": ("инженерн", "engineering", "энергетическ", "energy"), "substation": ("инженерн", "engineering", "энергетическ", "energy"),
                 "boiler": ("инженерн", "engineering", "теплов", "heat"), "agrs": ("инженерн", "engineering", "газов")}
FAC_RADIUS_M = {"substation_hv": 40.0, "substation": 20.0, "boiler": 25.0, "agrs": 15.0}   # free ground round the site
FAC_FIT = 0.5              # a lot of its kind or trade (not one named for it) holds a circle of this × FAC_RADIUS_M (a corridor strip does not)
FAC_SEARCH_M = 1500.0      # … searched this far from the model place (also outside the areas), every FAC_STEP_M
FAC_STEP_M = 20.0
RED_LINE_DEFAULT_M = {"highway": 50.0, "ring": 50.0, "main": 40.0, "street": 20.0}         # base edges without a profile, by class
LOT_KIND = "landmark_lot"   # mesh-less csv rows of a landmark lot's own capacity (CityDatabase keeps them out of Buildings)
LOT_M2_PER_HOME = 75.0      # housing floor area per home of such a row (Unity and the twin count residents as GFA / 30)
LOT_M2_PER_JOB = 90.0       # business floor area per job (CityStats.M2PerJob business, norms.M2_PER_JOB)
SOLAR_CLOSE_M = 3.0   # panel rows closer than 2 × this join into one solar field
UNITY_FILES = [U.F_ROADS, U.F_FILM, U.F_CSV, U.F_AQL, U.F_BOUNDS, U.F_HIDE, U.F_ORDER, U.F_LRT, U.F_NOPLANT, U.F_PARKING,
               U.F_DISTRICTS, U.F_SOLAR, U.F_NORMS, U.F_RAIL]
RAIL_DECK_M = 1.8         # rail head → underside of the viaduct deck (Gate v1.2: underside = rail head − 1.8 m)
RAIL_NOPLANT_M = 0.5      # the platforms' no-planting polygons reach this far beyond their edge


class Run:
    def __init__(self):
        self.lines = []; self.what = collections.defaultdict(list); self.t0 = time.time()

    def log(self, s):
        s = f"[{time.time() - self.t0:6.1f} s] {s}"; print(s, flush=True); self.lines.append(s)

    def note(self, f, s):
        self.what[f].append(s)


def num(v, nd=1):
    v = float(v)
    return int(v) if v.is_integer() else round(v, nd)


def district_name(d):
    return next((n for k, n in DNAME if d.startswith(k)), "")


# ================================================================== districts
def load_district(d, out_root, R):
    folder = os.path.join(out_root, d); D = {"id": d, "dir": folder}
    for k in KINDS:
        p = os.path.join(folder, k + ".json"); D[k] = U.load_json(p) if os.path.exists(p) else None
        if D[k] is None:
            R.log(f"{d}: no {k}.json — that part of the base stays as it is")
    D["spec"] = None
    for p in (os.path.join(U.SPEC, d + ".json"), os.path.join(folder, "spec.json")):
        if os.path.exists(p):
            D["spec"] = U.load_json(p); break
    area = (D["network"] or {}).get("area") or (D["spec"] or {}).get("area")
    if not area:
        raise SystemExit(f"{d}: no work area (network.json `area` or spec `area`)")
    D["area"] = Polygon(area).buffer(0)
    R.log(f"{d}: area {D['area'].area / 1e4:.0f} ha, files: " + ", ".join(k for k in KINDS if D[k] is not None))
    return D


# ================================================================== roads
def clip_pieces(coords, area):
    """Parts of a polyline outside `area`, each in the line's own direction; None when the line does not enter the area."""
    if len(coords) < 2:
        return None
    L = LineString(coords)
    if L.length < 1e-6 or not L.intersects(area) or L.intersection(area).length < 0.05:
        return None
    diff = L.difference(area); out = []
    for g in getattr(diff, "geoms", [diff]):
        if g.is_empty or g.geom_type != "LineString" or g.length < 0.5:
            continue
        c = [tuple(p) for p in g.coords]
        if L.project(Point(c[0])) > L.project(Point(c[-1])):
            c.reverse()
        out.append(c)
    out.sort(key=lambda c: L.project(Point(c[0])))
    return out


def struct_flat(struct):
    out = []
    for s in struct or []:
        out += [round(float(s["from_m"]), 1), round(float(s["to_m"]), 1), U.ST_CODE.get(s.get("kind"), 0)]
    return out


def profile_entry(key, p):
    return {"id": key, "t": p.get("class"), "lanes": list(p.get("lanes") or [1, 1]), "lane_w": float(p.get("lane_w") or 3.0),
            "median_w": float(p.get("median_w") or 0), "sidewalk_w": list(p.get("sidewalk_w") or [0, 0]), "verge_w": list(p.get("verge_w") or [0, 0]),
            "bike_w": list(p.get("bike_w") or [0, 0]), "parking_w": list(p.get("parking_w") or [0, 0]), "red_line_w": float(p.get("red_line_w") or 0)}


def rdp(P, tol):
    """Douglas–Peucker on the xz of the points P ([x, z, …]); both ends stay."""
    if len(P) < 3:
        return list(P)
    ax, az = P[0][0], P[0][1]; bx, bz = P[-1][0], P[-1][1]; L = math.hypot(bx - ax, bz - az); best, bi = -1.0, 1
    for i in range(1, len(P) - 1):
        qx, qz = P[i][0] - ax, P[i][1] - az
        d = abs((bx - ax) * qz - (bz - az) * qx) / L if L > 1e-9 else math.hypot(qx, qz)
        if d > best:
            best, bi = d, i
    if best <= tol:
        return [P[0], P[-1]]
    return rdp(P[:bi + 1], tol)[:-1] + rdp(P[bi:], tol)


def st_piece(st, c0, c1):
    """`st` triples [from, to, code] of an edge re-based to its piece c0..c1 (metres); [] when the piece is all on the ground."""
    out = []
    for k in range(0, len(st or []), 3):
        f, t = max(st[k], c0), min(st[k + 1], c1)
        if t - f > 0.05:
            out += [round(f - c0, 1), round(t - c0, 1), st[k + 2]]
    return out if any(out[i] != 0 for i in range(2, len(out), 3)) else []


def split_edge(e, marks, nodes):
    """Edge e cut at the chainages of `marks` [(metres, node)] (sorted, strictly inside): its pieces in order, each with the edge's own
    fields; g, h, len and st per piece (the heights interpolated by chainage, the cut points at the split nodes)."""
    g = e["g"]; P = [(g[k], g[k + 1]) for k in range(0, len(g), 2)]; H = e.get("h") if len(e.get("h") or []) == len(P) else None
    cum = [0.0]
    for i in range(1, len(P)):
        cum.append(cum[-1] + math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]))

    def h_at(c):
        i = max(1, min(len(P) - 1, bisect.bisect_left(cum, c))); seg = cum[i] - cum[i - 1]; t = 0.0 if seg < 1e-9 else (c - cum[i - 1]) / seg
        return H[i - 1] + (H[i] - H[i - 1]) * t
    bounds = [(0.0, e["a"], P[0])] + [(c, n, tuple(nodes[n])) for c, n in marks] + [(cum[-1], e["b"], P[-1])]
    pieces = []
    for (c0, n0, p0), (c1, n1, p1) in zip(bounds, bounds[1:]):
        mid = [i for i in range(len(P)) if c0 + 0.05 < cum[i] < c1 - 0.05]
        xz = [p0] + [P[i] for i in mid] + [p1]
        q = dict(e, a=n0, b=n1, g=U.flat(xz, 1), len=round(c1 - c0))
        if H is not None:
            q["h"] = [round(h_at(c0), 2)] + [H[i] for i in mid] + [round(h_at(c1), 2)]
        st = st_piece(e.get("st"), c0, c1)
        if st:
            q["st"] = st
        else:
            q.pop("st", None)
        pieces.append(q)
    return pieces


def pad_surfaces(Ds):
    """Paved ground under turnaround pads, per district: (plazas, courts). Plazas are the features' plazas and greens of kind square
    (ground.py draws them over drives and pads); courts are the lots ground.py paves in part (types 10 and 16: public lots and apartment
    blocks) where no other green lies."""
    try:
        import ground as GRD
        lot_type = dict(GRD.LOT_TYPE)
    except Exception:                      # ground.py unreadable: the types that are not 10 or 16 in its table (w48 round 2)
        lot_type = {"residential_low": 5, "village_existing": 5, "school": 2, "kindergarten": 2, "square": 3, "playground": 13,
                    "sport_ground": 12, "sport": 12, "park": 6, "waterfront": 6, "industry": 7, "logistics": 7, "utility": 11,
                    "substation": 11, "reserve": 8}
    out = {}
    for D in Ds:
        F = D.get("features") or {}; lots = (D.get("lots") or {}).get("lots") or []

        def poly(q):
            return Polygon(q["polygon"], q.get("holes") or []).buffer(0)
        plaza = [poly(q) for q in F.get("plazas") or []] + [poly(g) for g in F.get("greens") or [] if g.get("kind") == "square"]
        court = [poly(L) for L in lots if lot_type.get(L.get("use"), 10) in (10, 16) and L.get("source") != "keep"]
        green = [poly(g) for g in F.get("greens") or [] if g.get("kind") != "square"]
        P = unary_union(plaza) if plaza else None
        C = unary_union(court) if court else None
        if C is not None and green:
            C = C.difference(unary_union(green))
        out[D["id"]] = (P, C)
    return out


def pad_surface(ring, paved):
    """`pl` of a pad: 1 on a plaza (FilmRoads leaves it to the ground's paving), 2 in a paved court (FilmRoads draws it as pavers), 0
    elsewhere (asphalt)."""
    if not paved:
        return 0
    P = Polygon(ring).buffer(0)
    if P.is_empty or P.area < 1.0:
        return 0
    for k, g in ((1, paved[0]), (2, paved[1])):
        if g is not None and P.intersection(g).area >= PAD_SHARE * P.area:
            return k
    return 0


def add_driveways(Ds, nodes, edges, new_node, seg_edge, profiles, prof_ix, terrain, R):
    """Drive segments of every district as edges after all district streets; attach nodes split their street edge (CONTRACT §8).
    Returns (split: street edge → its pieces in order, orig: street edge → its edge before the split, drives [(edge, attach at a,
    attach at b)], pads [{n, p, y}] with node ids before compaction, stats)."""
    split, orig, drives, pads, serves = {}, {}, [], [], []
    paved = pad_surfaces(Ds)
    st = {"segments": 0, "edges": 0, "km": 0.0, "points_in": 0, "points_out": 0, "attach": 0, "split": 0, "on_end": 0, "shared": 0,
          "fallback": 0, "unattached": 0, "pads": 0, "pads_pl1": 0, "pads_pl2": 0}
    attach_nodes = set(); work = []
    for D in Ds:                             # pass 1: attach points split the streets (all pieces before the first drive edge)
        dw = D.get("driveways"); did = D["id"]
        if not dw:
            continue
        dn = {n["id"]: n for n in dw.get("nodes") or []}
        dsegs = [x for x in dw.get("segments") or [] if len(x.get("pts") or []) >= 2]
        st["segments"] += len(dsegs)
        # profiles: the network's own entry when equal, otherwise a key of the drives' own
        pkey = {}
        for pid, p in (dw.get("profiles") or {}).items():
            key = f"{did}:{pid}"; ent = profile_entry(key, p)
            if key in prof_ix and {k: v for k, v in profiles[prof_ix[key]].items() if k != "id"} != {k: v for k, v in ent.items() if k != "id"}:
                key = f"{did}:dw.{pid}"; ent["id"] = key
            if key not in prof_ix:
                prof_ix[key] = len(profiles); profiles.append(ent)
            pkey[pid] = prof_ix[key]
        # ---- attach points → marks on their street edges
        marks = collections.defaultdict(list)            # street edge → [(chainage, drive node)]
        for n in dn.values():
            at = n.get("attach")
            if not at:
                continue
            st["attach"] += 1; p = Point(at["x"], at["z"]); ei = seg_edge.get((did, at.get("segment")))
            if ei is not None:
                gg = edges[ei]["g"]; L = LineString([(gg[k], gg[k + 1]) for k in range(0, len(gg), 2)])
                if L.distance(p) > 3.0:
                    ei = None
            if ei is None:                                   # the segment is not an edge of this merge: the nearest district street
                best = min(((LineString([(edges[j]["g"][k], edges[j]["g"][k + 1]) for k in range(0, len(edges[j]["g"]), 2)]).distance(p), j)
                            for (d2, _), j in seg_edge.items() if d2 == did), default=(1e9, None))
                if best[0] > 3.0:
                    R.log(f"  drives {did}: attach of {n['id']} on {at.get('segment')} has no street within 3 m: the drive stays unattached")
                    st["unattached"] += 1; continue
                ei = best[1]; st["fallback"] += 1
                R.log(f"  drives {did}: attach of {n['id']} names {at.get('segment')}, taken onto edge {ei} {best[0]:.1f} m away")
            gg = edges[ei]["g"]; L = LineString([(gg[k], gg[k + 1]) for k in range(0, len(gg), 2)])
            marks[ei].append((L.project(p), n["id"]))
        dmap = {}                                            # drive node → node id
        for ei, ms in sorted(marks.items()):
            e = edges[ei]; gg = e["g"]; L = LineString([(gg[k], gg[k + 1]) for k in range(0, len(gg), 2)]); ms.sort()
            groups = []
            for c, nid_ in ms:
                if groups and c - groups[-1][0][-1] <= ATTACH_SNAP_M:
                    groups[-1][0].append(c); groups[-1][1].append(nid_)
                else:
                    groups.append(([c], [nid_]))
            cut = []
            for cs, ids in groups:
                c = sum(cs) / len(cs); st["shared"] += len(ids) - 1
                if c <= ATTACH_SNAP_M:
                    node = e["a"]; st["on_end"] += 1
                elif c >= L.length - ATTACH_SNAP_M:
                    node = e["b"]; st["on_end"] += 1
                else:
                    q = L.interpolate(c); node = new_node(q.x, q.y); cut.append((c, node)); st["split"] += 1
                for i_ in ids:
                    dmap[i_] = node
                attach_nodes.add(node)
            if cut:
                orig[ei] = e; pieces = split_edge(e, cut, nodes)
                edges[ei] = pieces[0]; split[ei] = [ei]
                for q in pieces[1:]:
                    edges.append(q); split[ei].append(len(edges) - 1)
        for n in dn.values():
            if n["id"] not in dmap:
                dmap[n["id"]] = new_node(n["x"], n["z"])
        work.append((did, dw, dn, dsegs, dmap, pkey))
    for did, dw, dn, dsegs, dmap, pkey in work:   # pass 2: the drive edges
        # ---- chains through plain degree-2 drive nodes (no attach, no pad) with the same class, profile and years join into one edge
        padn = set(p.get("node") for p in dw.get("pads") or [])
        adj = collections.defaultdict(list)
        for i, x in enumerate(dsegs):
            adj[x["a"]].append(i); adj[x["b"]].append(i)

        def sig(x):
            return (x.get("class"), x.get("pid"), tuple(x.get("years") or []), bool(x.get("oneway")))

        def plain(n, sg):
            return (len(adj[n]) == 2 and n not in padn and not (dn.get(n) or {}).get("attach") and not (dn.get(n) or {}).get("turnaround")
                    and all(sig(dsegs[k]) == sg for k in adj[n]))
        used = set()
        for i, x in enumerate(dsegs):
            if i in used:
                continue
            used.add(i); sg = sig(x); pts = [list(p) for p in x["pts"]]; a, b = x["a"], x["b"]; sv = set(x.get("serves") or [])
            for fwd in (True, False):
                end = b if fwd else a
                while plain(end, sg) and not sg[3]:
                    nxt = [k for k in adj[end] if k not in used]
                    if not nxt:
                        break
                    j = nxt[0]; used.add(j); t = dsegs[j]; sv |= set(t.get("serves") or [])
                    q = [list(p) for p in (t["pts"] if t["a"] == end else t["pts"][::-1])]
                    end = t["b"] if t["a"] == end else t["a"]
                    pts = pts + q[1:] if fwd else q[::-1][:-1] + pts
                if fwd:
                    b = end
                else:
                    a = end
            na, nb = dmap[a], dmap[b]
            pts[0][0], pts[0][1] = nodes[na][0], nodes[na][1]; pts[-1][0], pts[-1][1] = nodes[nb][0], nodes[nb][1]
            st["points_in"] += len(pts); pts = rdp(pts, DRIVE_SIMPLIFY_M); st["points_out"] += len(pts)
            xz = [(p[0], p[1]) for p in pts]
            if na == nb and len(xz) < 3:
                continue
            ln = U.polyline_len(xz)
            e = {"a": na, "b": nb, "c": "street", "len": round(ln), "g": U.flat(xz, 1), "y": [int(v) for v in x["years"]],
                 "t": x.get("class") or "driveway_main", "k": 1 if x.get("oneway") else 0,
                 "h": [round(float(terrain.height(p[0], p[1])), 2) for p in xz]}
            if x.get("pid") in pkey:
                e["p"] = pkey[x["pid"]]
            edges.append(e); st["edges"] += 1; st["km"] += ln / 1000; serves.append((len(edges) - 1, did, sorted(sv)))
            drives.append((len(edges) - 1, bool((dn.get(a) or {}).get("attach")) and na in attach_nodes,
                           bool((dn.get(b) or {}).get("attach")) and nb in attach_nodes))
        for p in dw.get("pads") or []:
            if p.get("node") in dmap and len(p.get("polygon") or []) >= 3:
                pd = {"n": dmap[p["node"]], "p": [num(v) for q in p["polygon"] for v in q[:2]], "y": [int(v) for v in p.get("years") or [2025] * 4]}
                pl = pad_surface([q[:2] for q in p["polygon"]], paved.get(did))
                if pl:
                    pd["pl"] = pl; st["pads_pl%d" % pl] += 1
                pads.append(pd); st["pads"] += 1
    if st["segments"]:
        st["km"] = round(st["km"], 2)
        R.log(f"drives: {st['segments']} drive segments → {st['edges']} edges ({st['km']:.1f} km, points {st['points_in']} → {st['points_out']} "
              f"after joining plain chains and dropping points within {DRIVE_SIMPLIFY_M} m of a straight line); {st['attach']} attach points: "
              f"{st['split']} split a street edge ({len(split)} streets), {st['on_end']} on a street end node, {st['shared']} share a split, "
              f"{st['fallback']} taken onto the nearest street, {st['unattached']} unattached; {st['pads']} turnaround pads "
              f"({st['pads_pl1']} on a plaza: the ground's paving, pl 1; {st['pads_pl2']} in a paved court of an apartment or public lot: pavers, pl 2)")
    st["serves"] = serves
    return split, orig, drives, pads, st, attach_nodes


def keep_years(kp):
    """Opening years of a keep quarter's streets: the spec's `years`, not before the registry object's completion (Unity shows the
    Gate District quarter only once Iconic stands: IconicDistrict.On)."""
    y = [int(v) for v in (kp.get("years") or [2025] * 4)]
    rid = kp.get("registry_id")
    if rid:
        try:
            reg = U.load_json(os.path.join(U.SPEC, "registry.json"))
            row = next((r for r in reg.get("rows") or [] if r.get("id") == rid), None)
            done = ((row or {}).get("years") or {}).get("completion")
            if done:
                y = [max(v, int(done)) for v in y]
        except (OSError, ValueError):
            pass
    return y


def merge_roads(base, film, Ds, terrain, R, base_dir=U.TWIN):
    """Returns roads.json and film_roads.json dicts of the merged network (without `external`, which the traffic re-run sets)."""
    nodes = [list(p) for p in base["nodes"]]; nb0 = len(nodes)
    keep_edges = []                         # streets of keep quarters and the links into them: in roads.json, never in the film
    sig_nodes = []                          # junctions the districts signal (network nodes of kind crossing_signal)
    area = unary_union([D["area"] for D in Ds]) if Ds else None
    edges, cuts = [], []                    # cuts: (node, x, z, base edge)
    old2new = {}                            # base edge → its pieces in `edges`
    removed_edges = 0; orphans = []         # orphans: base pieces outside the areas with both ends on the area edge
    orph_cut = set()                        # indexes in `cuts` of their ends

    def new_node(x, z):
        nodes.append([num(x), num(z)]); return len(nodes) - 1

    for i, e in enumerate(base["edges"]):
        g = e["g"]; pts = [(g[k], g[k + 1]) for k in range(0, len(g), 2)]
        pieces = clip_pieces(pts, area) if area is not None else None
        if pieces is None:
            old2new[i] = [len(edges)]; edges.append(e); continue
        old2new[i] = []
        if not pieces:
            removed_edges += 1
        for c in pieces:
            old = [next((q for q in (e["a"], e["b"]) if math.hypot(nodes[q][0] - p[0], nodes[q][1] - p[1]) < 0.5), None) for p in (c[0], c[-1])]
            # both ends on the area edge (a loop of a base interchange the district rebuilt, a road along the edge): no base road
            # beyond either end, so it only joins district joints to each other; a two-way street may go on over it (a road out and
            # back along the edge), a one-way carriageway or ramp would take no traffic from the base network there (stitching)
            orphan = old[0] is None and old[1] is None
            if orphan:
                orphans.append((i, round(U.polyline_len(c))))
            ends = []
            for p, n in zip((c[0], c[-1]), old):
                if n is None:
                    n = new_node(*p); cuts.append((n, p[0], p[1], i))
                    if orphan:
                        orph_cut.add(len(cuts) - 1)
                ends.append(n)
            if ends[0] == ends[1]:
                continue
            old2new[i].append(len(edges))
            edges.append({"a": ends[0], "b": ends[1], "c": e["c"], "len": round(U.polyline_len(c)), "g": [num(v) for p in c for v in p], "y": e["y"]})
    if Ds:
        n_cut = len(set(c[3] for c in cuts))
        R.log(f"roads: base {len(base['edges'])} edges; {removed_edges} inside the areas removed, {n_cut} cut at the area edge "
              f"({len(cuts)} boundary nodes)" + (f"; {len(orphans)} pieces outside the areas with both ends on the area edge (no base road "
              f"beyond them; no one-way or ramp joint takes their ends): " + ", ".join(f"e{i} {m} m" for i, m in orphans[:8]) if orphans else ""))
    profiles, prof_ix, interchanges = [], {}, []
    film_new = []                           # (edge index, district segment) for the new strokes
    seg_edge = {}                           # (district, segment id) → edge index
    new_zones = []
    for D in Ds:
        net = D["network"]; did = D["id"]
        if net is None:
            continue
        nid = {}
        ninfo = {n["id"]: n for n in net["nodes"]}
        for n in net["nodes"]:
            nid[n["id"]] = new_node(n["x"], n["z"])
        for pid, p in (net.get("profiles") or {}).items():
            key = f"{did}:{pid}"; prof_ix[key] = len(profiles); profiles.append(profile_entry(key, p))
        ic_ix = {}
        for ic in net.get("interchanges") or []:
            ic_ix[ic["id"]] = len(interchanges)
            interchanges.append({"id": f"{did}:{ic['id']}", "template": ic.get("template"), "x": num(ic["x"]), "z": num(ic["z"])})
        segs = net["segments"]
        touching = collections.defaultdict(list)
        for s in segs:
            touching[s["a"]].append((s, 0)); touching[s["b"]].append((s, 1))
        # ---- stitching: joint nodes of the district ↔ boundary nodes of the cut twin roads
        jn = [j["node"] for j in net.get("joints") or []] + [n["id"] for n in net["nodes"] if n.get("kind") in ("joint", "edge")]
        jn = list(dict.fromkeys(j for j in jn if j in nid))
        # ---- keep quarters (CONTRACT §4 `keep`): their own streets as the twin data has them; the district joints at the quarter join them
        kjoined = set()
        for kp in (D["spec"] or {}).get("keep") or []:
            kzone = Polygon(kp["polygon"]).buffer(KR.KEEP_STITCH_M) if len(kp.get("polygon") or []) >= 3 else None
            js = [(j, ninfo[j]["x"], ninfo[j]["z"]) for j in jn if kzone is None or kzone.contains(Point(ninfo[j]["x"], ninfo[j]["z"]))]
            kg = KR.keep_graph(kp, js, base_dir, terrain, R.log)
            if kg is None:
                continue
            knodes, kedges, jm = kg; ky = keep_years(kp)
            kid = [new_node(x, z) for x, z in knodes]
            for e in kedges:
                edges.append({"a": kid[e["a"]], "b": kid[e["b"]], "c": U.old_class(e["t"]), "len": round(U.polyline_len(e["pts"])),
                              "g": U.flat(e["pts"], 1), "y": list(ky), "t": e["t"], "k": e["k"], "h": e["h"]})
                keep_edges.append(len(edges) - 1)
            khn = {}
            for e in kedges:
                khn[e["a"]] = e["h"][0]; khn[e["b"]] = e["h"][-1]
            snapped_k, linked_k = 0, 0
            for j, (kn, gap) in jm.items():
                kjoined.add(j)
                if gap <= SNAP_M:
                    nid[j] = kid[kn]; snapped_k += 1
                    continue
                s, end = touching[j][0] if touching[j] else (None, 0)
                t = s["class"] if s else "local"; k = 1 if s and s.get("oneway") and t != "ramp" else 0
                a, b = (kid[kn], nid[j]) if (k == 0 or end == 0) else (nid[j], kid[kn])
                jy = float(ninfo[j].get("y") or terrain.height(ninfo[j]["x"], ninfo[j]["z"]))
                ha = [round(khn.get(kn, float(terrain.height(*knodes[kn]))), 2), round(jy, 2)]
                if a != kid[kn]:
                    ha.reverse()
                yl = [max(int(u), v) for u, v in zip(s["years"], ky)] if s else list(ky)
                e = {"a": a, "b": b, "c": U.old_class(t, (s or {}).get("name_ru") or "", (s or {}).get("street") or ""), "len": round(gap),
                     "g": [num(nodes[a][0]), num(nodes[a][1]), num(nodes[b][0]), num(nodes[b][1])], "y": yl, "t": t, "k": k, "h": ha}
                pk = f"{did}:{s.get('pid')}" if s else None
                if pk in prof_ix:
                    e["p"] = prof_ix[pk]
                edges.append(e); keep_edges.append(len(edges) - 1); linked_k += 1
                R.log(f"  keep {kp.get('id')}: joint {j} ↔ quarter street, gap {gap:.1f} m → link edge ({t}, not drawn by the film)")
            far = [j for j, _, _ in js if j not in jm]
            R.log(f"  keep {kp.get('id')}: {len(jm)} of {len(js)} district joints at the quarter joined ({snapped_k} on a street end, "
                  f"{linked_k} by a link)" + (f"; not joined: {far}" if far else ""))
        jn_twin = [j for j in jn if j not in kjoined]
        # a two-way twin road at the cut takes one joint traffic leaves the district by and one it enters by (the two one-way
        # carriageways of a motorway, or a ramp and its carriageway, on one two-way twin line); a one-way twin road or a two-way
        # district street takes the cut alone
        def jdir(j):
            ds = set()
            for sg, end in touching[j]:
                if sg.get("class") == "ramp" or sg.get("oneway"):
                    ds.add("in" if end == 0 else "out")
                else:
                    ds |= {"in", "out"}
            return ds or {"in", "out"}
        pairs, hint = [], {}
        if cuts and jn_twin:
            ck = cKDTree(np.array([[c[1], c[2]] for c in cuts]))
            # spec edge joints: one with a district street names the twin edge it goes on as (connects "twin_edge:<i>", or the
            # `twin_edge` an OSM road's joint lies on, within HINT_M), a hint for the joint at it; one without a street only marks a
            # twin road the area edge cuts (it was the nearest joint's hint, so motorway joints went on as street stubs): no hint
            hdist = {}
            for ej in (D["spec"] or {}).get("edge_joints") or []:
                con = str(ej.get("connects") or ""); te = None
                if con.startswith("twin_edge:"):
                    te = int(con.split(":")[1])
                elif ej.get("twin_edge") is not None and float(ej.get("twin_gap_m") or 0.0) <= HINT_M:
                    te = int(ej["twin_edge"])
                if te is None or not ej.get("street"):
                    continue
                near = min(jn, key=lambda j: math.hypot(ninfo[j]["x"] - ej["x"], ninfo[j]["z"] - ej["z"]))
                dn = math.hypot(ninfo[near]["x"] - ej["x"], ninfo[near]["z"] - ej["z"])
                if dn < 30 and dn < hdist.get(near, 1e9):
                    hint[near] = te; hdist[near] = dn
            # a motorway carriageway or ramp joint takes a cut motorway line of the twin (highway, ring) before a twin street crossing
            # the edge beside it, so the carriageway goes on as the twin motorway (its capacity, its traffic) and not over a street stub
            fast_c = {"highway", "ring"}
            for j in jn_twin:
                x, z = ninfo[j]["x"], ninfo[j]["z"]
                fj = any(sg.get("class") in U.FAST or sg.get("class") == "ramp" for sg, _ in touching[j]); one = len(jdir(j)) == 1
                for d, ci in zip(*ck.query([x, z], k=min(8, len(cuts)), distance_upper_bound=STITCH_M)):
                    if np.isfinite(d):
                        if one and int(ci) in orph_cut:
                            continue
                        be = cuts[ci][3]
                        bonus = -1000.0 if hint.get(j) == be else 0.0
                        if fj and base["edges"][be]["c"] not in fast_c:
                            bonus += STITCH_M
                        pairs.append((d + bonus, d, j, int(ci)))
        used_j, cdir = set(), collections.defaultdict(set)
        snapped, links, shared = 0, 0, 0
        for _, d, j, ci in sorted(pairs):
            if j in used_j:
                continue
            dj, two = jdir(j), (base["edges"][cuts[ci][3]].get("k") or 0) == 0
            if cdir[ci] and (not two or dj & cdir[ci]):
                continue
            shared += bool(cdir[ci]); used_j.add(j); cdir[ci] |= dj if two else {"in", "out"}; cn, cx, cz, be = cuts[ci]
            if d <= SNAP_M:
                nid[j] = cn; snapped += 1
                continue
            s, end = touching[j][0] if touching[j] else (None, 0)
            t = s["class"] if s else "local"
            k = 2 if t == "ramp" else (1 if s and s.get("oneway") else 0)
            a, b = (cn, nid[j]) if (k == 0 or end == 0) else (nid[j], cn)
            pa, pb = (nodes[a], nodes[b])
            jy = float(ninfo[j].get("y") or terrain.height(ninfo[j]["x"], ninfo[j]["z"]))
            ha = [round(float(terrain.height(cx, cz)), 2), round(jy, 2)]
            if a != cn:
                ha.reverse()
            e = {"a": a, "b": b, "c": U.old_class(t, (s or {}).get("name_ru") or "", (s or {}).get("street") or ""), "len": round(d),
                 "g": [num(pa[0]), num(pa[1]), num(pb[0]), num(pb[1])], "y": list(s["years"]) if s else [2025] * 4, "t": t, "k": k, "h": ha}
            pk = f"{did}:{s.get('pid')}" if s else None
            if pk in prof_ix:
                e["p"] = prof_ix[pk]
            edges.append(e); film_new.append((len(edges) - 1, None)); links += 1
            R.log(f"  stitch {did}: joint {j} ↔ twin edge {be} boundary node, gap {d:.1f} m → link edge")
        for j in jn_twin:
            if j not in used_j:
                R.log(f"  stitch {did}: joint {j} at ({ninfo[j]['x']:.0f}, {ninfo[j]['z']:.0f}) has no twin road within {STITCH_M:.0f} m (gap)")
        R.log(f"roads {did}: {len(jn)} joints ({len(kjoined)} at keep quarters), {snapped} snapped (≤ {SNAP_M:.0f} m), {links} link edges, "
              f"{shared} on a two-way twin road another joint of the other direction takes too, {len(hint)} hinted by the spec's twin edge; "
              f"{sum(1 for i in range(len(cuts)) if not cdir[i])} cut twin roads end at the area edge without a district street")
        sig_nodes.extend(nid[n["id"]] for n in net["nodes"] if n.get("kind") == "crossing_signal")
        # ---- the district's segments (a spec street of a driveway_* class is a spec error: drives are driveways.json's only; it is
        # merged as a street, check_merge fails on it)
        sdw = [s["id"] for s in segs if str(s.get("class") or "").startswith("driveway")]
        if sdw:
            R.log(f"  {did}: SPEC ERROR: {len(sdw)} spec streets of a driveway_* class ({', '.join(sdw[:8])}{' …' if len(sdw) > 8 else ''}): "
                  "a spec street is never a drive")
        for s in segs:
            pts = [list(p) for p in s["pts"]]
            a, b = nid[s["a"]], nid[s["b"]]
            for idx, n in ((0, a), (-1, b)):
                if math.hypot(nodes[n][0] - pts[idx][0], nodes[n][1] - pts[idx][1]) <= SNAP_M + 0.01:
                    pts[idx][0], pts[idx][1] = nodes[n][0], nodes[n][1]
            if a == b and len(pts) < 3:
                continue
            xz = [(p[0], p[1]) for p in pts]
            t = s["class"]; k = 2 if t == "ramp" else (1 if s.get("oneway") else 0)
            e = {"a": a, "b": b, "c": U.old_class(t, s.get("name_ru") or "", s.get("street") or ""), "len": round(U.polyline_len(xz)),
                 "g": U.flat(xz, 1), "y": [int(v) for v in s["years"]], "t": t, "k": k, "h": [round(float(p[2]), 2) for p in pts]}
            st = struct_flat(s.get("struct"))
            if any(st[i] != 0 for i in range(2, len(st), 3)):
                e["st"] = st
            pk = f"{did}:{s.get('pid')}"
            if pk in prof_ix:
                e["p"] = prof_ix[pk]
            ps = [{"y": [int(v) for v in st["years"]], "p": prof_ix[f"{did}:{st['pid']}"]} for st in s.get("stages") or []
                  if f"{did}:{st['pid']}" in prof_ix]
            if ps:
                e["ps"] = ps            # the profile from these years on (a reconstruction: lanes of a ramp, network `stages`)
            if s.get("ic") is not None and s["ic"] in ic_ix:
                e["ic"] = ic_ix[s["ic"]]
            edges.append(e); film_new.append((len(edges) - 1, s)); seg_edge[(did, s["id"])] = len(edges) - 1
            out = LineString(xz).difference(D["area"].buffer(5)).length if len(xz) > 1 else 0
            if out > 1:
                R.log(f"  {did}: segment {s['id']} runs {out:.0f} m outside the area")
        for ic in net.get("interchanges") or []:
            ramps = set(ic.get("ramps") or []) | set(ic.get("structures") or [])
            P = [LineString([p[:2] for p in s["pts"]]) for s in segs if s["id"] in ramps and len(s["pts"]) > 1]
            if not P:
                continue
            # the land between the ramps: the circle round the centre that holds ZONE_Q % of the ramps' length (the loops; a long slip
            # road running out along its avenue stays outside), plus ZONE_PAD_M. Unity keeps it a mown verge, no yards, no walkers.
            d = np.concatenate([np.hypot(*(np.array([L.interpolate(t).coords[0] for t in np.arange(0, L.length + 1e-6, 2.0)]) - [ic["x"], ic["z"]]).T)
                                for L in P])
            r = float(np.percentile(d, ZONE_Q)) + ZONE_PAD_M
            y0 = min(s["years"][0] for s in segs if s["id"] in ramps)
            new_zones.append([num(ic["x"]), num(ic["z"]), num(r), int(y0)])
            R.log(f"  {did}: interchange {ic['id']}: zone r {r:.0f} m ({ZONE_Q:.0f} % of {sum(L.length for L in P):.0f} m of ramps, the farthest at {d.max():.0f} m)")
    split, orig, drives, pads, dstat, attach_set = add_driveways(Ds, nodes, edges, new_node, seg_edge, profiles, prof_ix, terrain, R)
    # ---- compact nodes: drop those only removed edges used
    base_used = set(e["a"] for e in base["edges"]) | set(e["b"] for e in base["edges"])
    used = set(e["a"] for e in edges) | set(e["b"] for e in edges)
    keep = [i for i in range(len(nodes)) if i in used or (i < nb0 and i not in base_used)]
    nmap = {o: n for n, o in enumerate(keep)}
    out_edges = []
    for e in edges:
        if nmap[e["a"]] != e["a"] or nmap[e["b"]] != e["b"]:
            e = dict(e, a=nmap[e["a"]], b=nmap[e["b"]])
        out_edges.append(e)
    roads = {k: v for k, v in base.items() if k not in ("nodes", "edges", "external")}
    roads["nodes"] = [nodes[i] for i in keep]; roads["edges"] = out_edges; roads["external"] = base.get("external")
    if profiles:
        roads["profiles"] = profiles
    if interchanges:
        roads["interchanges"] = interchanges
    # ---- film_roads
    if not Ds:
        return roads, film, {"edges_removed": 0}
    dstat["attach_nodes"] = sorted(nmap[n] for n in attach_set)
    strokes = []
    for s in film["s"]:
        g = s["g"]; pts = [(g[k], g[k + 1]) for k in range(0, len(g), 2)]
        pieces = clip_pieces(pts, area)
        base_s = {"c": s["c"], "k": s["k"], "a": nmap.get(s["a"], -1) if s["a"] >= 0 else -1, "b": nmap.get(s["b"], -1) if s["b"] >= 0 else -1,
                  "y": s["y"], "g": s["g"], "e": -1, "p": -1, "ic": -1}
        if pieces is None:
            strokes.append(base_s); continue
        for c in pieces:
            q = dict(base_s, g=[round(float(v), 1) for p in c for v in p])
            if math.hypot(c[0][0] - pts[0][0], c[0][1] - pts[0][1]) > 0.5:
                q["a"] = -1
            if math.hypot(c[-1][0] - pts[-1][0], c[-1][1] - pts[-1][1]) > 0.5:
                q["b"] = -1
            if U.polyline_len(c) >= 3:
                strokes.append(q)
    n_old = len(strokes)
    for ei, s in film_new:
        e = out_edges[ei]
        if ei in orig:                      # a street split by drive attaches stays one stroke over its pieces
            e = dict(orig[ei], a=nmap[orig[ei]["a"]], b=nmap[orig[ei]["b"]])
        q = {"c": e["c"], "k": e.get("k", 0), "a": e["a"], "b": e["b"], "y": e["y"], "g": e["g"], "e": ei, "p": e.get("p", -1), "ic": e.get("ic", -1),
             "t": e.get("t", ""), "h": e.get("h", []), "st": e.get("st", [])}
        if ei in split:
            q["es"] = split[ei]
        strokes.append(q)
    n_streets = len(strokes)
    for ei, at_a, at_b in drives:           # drives: no junction patch where they meet their street
        e = out_edges[ei]
        strokes.append({"c": e["c"], "k": e.get("k", 0), "a": -1 if at_a else e["a"], "b": -1 if at_b else e["b"], "y": e["y"], "g": e["g"], "e": ei,
                        "p": e.get("p", -1), "ic": -1, "t": e.get("t", ""), "h": e.get("h", []), "st": []})
    drop = sorted(set(n for o in film.get("drop") or [] for n in old2new.get(o, [])) | set(keep_edges))
    zones = [z for z in film.get("zones") or [] if not area.contains(Point(z[0], z[1]))] + new_zones
    if len(zones) > 32:
        R.log(f"film roads: {len(zones)} interchange zones, Unity reads the first 32")
    film_out = {"v": 2, "s": strokes, "zones": zones, "drop": drop, "profiles": profiles,
                "sigOn": 1, "sig": sorted(set(nmap[n] for n in sig_nodes if n in nmap))}
    if pads:
        film_out["pads"] = [dict(p, n=nmap[p["n"]]) for p in pads]
    R.log(f"film roads: {len(film['s'])} base strokes → {n_old} kept or clipped + {n_streets - n_old} new streets (stroke.e = roads edge; "
          f"{len(split)} split by drives carry es) + {len(strokes) - n_streets} drives, {len(pads)} pads, "
          f"{len(zones)} zones, drop {len(film.get('drop') or [])} → {len(drop)} ({len(keep_edges)} streets of keep quarters, drawn by their own model)")
    dstat["strokes"] = len(strokes) - n_streets
    return roads, film_out, {"edges_removed": removed_edges, "drives": dstat, "keep_edges": keep_edges}


# ================================================================== buildings
def extrude(fp, bottom, top, col_wall, col_roof, min_area=1.0):
    """Flat-roofed prism of a footprint: (V[n,3], T[m,3], col[m]); every face's np.cross(b − a, c − a) points outward (as the base meshes).
    None for a footprint under min_area m²."""
    P = Polygon(fp).buffer(0)
    if P.geom_type == "MultiPolygon":
        P = max(P.geoms, key=lambda g: g.area)
    if P.is_empty or P.area < min_area:
        return None
    P = orient(P, 1.0)
    V, T, C = [], [], []

    def tri(a, b, c, want, col):
        a, b, c = np.asarray(a, float), np.asarray(b, float), np.asarray(c, float)
        if np.dot(np.cross(b - a, c - a), want) < 0:
            b, c = c, b
        n0 = len(V); V.extend([a, b, c]); T.append([n0, n0 + 1, n0 + 2]); C.append(col)
    for t in shapely.constrained_delaunay_triangles(P).geoms:
        q = list(t.exterior.coords)[:3]
        tri(*[(x, top, z) for x, z in q], want=(0, 1, 0), col=col_roof)
    for ring in [P.exterior] + list(P.interiors):
        c = list(ring.coords)
        for (px, pz), (qx, qz) in zip(c[:-1], c[1:]):
            if math.hypot(qx - px, qz - pz) < 0.05:
                continue
            out = (qz - pz, 0, -(qx - px))
            n0 = len(V); quad = [(px, bottom, pz), (qx, bottom, qz), (qx, top, qz), (px, top, pz)]
            a, b, cc = np.array(quad[0]), np.array(quad[1]), np.array(quad[2])
            V.extend(np.array(quad, float))
            if np.dot(np.cross(b - a, cc - a), out) >= 0:
                T.extend([[n0, n0 + 1, n0 + 2], [n0, n0 + 2, n0 + 3]])
            else:
                T.extend([[n0, n0 + 2, n0 + 1], [n0, n0 + 3, n0 + 2]])
            C.extend([col_wall, col_wall])
    return np.array(V, np.float32), np.array(T, np.uint32), np.array(C, np.uint8)


def canopy_mesh(fp, base_y, top, col, terrain):
    """A roof on posts: the footprint's slab CANOPY_SLAB_M thick under `top`, and square posts CANOPY_POST_M wide down into the ground,
    in rows along the long axis of its minimum rectangle (one row in the middle of a shallow canopy, one along each long edge of a deep
    one), CANOPY_INSET_M in from the ends and at most CANOPY_POST_STEP_M apart. The slab has an underside (faces down, the soffit seen
    from the platforms). (V, T, col, posts) like extrude, None for an empty one."""
    slab = extrude(fp, top - CANOPY_SLAB_M, top, col, col)
    if slab is None:
        return None
    P = Polygon(fp).buffer(0)
    if P.geom_type == "MultiPolygon":
        P = max(P.geoms, key=lambda g: g.area)
    yb, sv = top - CANOPY_SLAB_M, []
    for t in shapely.constrained_delaunay_triangles(orient(P, 1.0)).geoms:
        a, b, c = [np.array([x, yb, z]) for x, z in list(t.exterior.coords)[:3]]
        sv += [a, c, b] if np.cross(b - a, c - a)[1] > 0 else [a, b, c]
    under = (np.array(sv, np.float32), np.arange(len(sv), dtype=np.uint32).reshape(-1, 3), np.full(len(sv) // 3, col, np.uint8))
    r = list(P.minimum_rotated_rectangle.exterior.coords)
    e0, e1 = np.subtract(r[1], r[0]), np.subtract(r[2], r[1])
    u, v = (e0, e1) if np.hypot(*e0) >= np.hypot(*e1) else (e1, e0)
    Lu, Lv = float(np.hypot(*u)), float(np.hypot(*v)); u, v = u / max(Lu, 1e-9), v / max(Lv, 1e-9)
    c = np.mean(np.array(r[:4]), axis=0)
    rows = [0.0] if Lv <= CANOPY_ROW_M else [-(Lv / 2 - CANOPY_INSET_M), Lv / 2 - CANOPY_INSET_M]
    run = max(Lu - 2 * CANOPY_INSET_M, 0.0); n = max(1, int(math.ceil(run / CANOPY_POST_STEP_M))) + 1 if run > 0 else 1
    parts, posts, h = [slab, under], 0, CANOPY_POST_M / 2
    for ov in rows:
        for i in range(n):
            ou = -run / 2 + run * i / (n - 1) if n > 1 else 0.0
            q = c + u * ou + v * ov
            if not P.contains(Point(q[0], q[1])):
                continue
            sq = [tuple(q + u * a * h + v * b * h) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            m = extrude(sq, min(base_y, float(terrain.height(q[0], q[1]))) - 0.3, top - CANOPY_SLAB_M, col, col, min_area=0.01)
            if m is not None:
                parts.append(m); posts += 1
    V, T, C, nv = [], [], [], 0
    for mv, mt, mc in parts:
        V.append(mv); T.append(mt + nv); C.append(mc); nv += len(mv)
    return np.concatenate(V), np.concatenate(T).astype(np.uint32), np.concatenate(C), posts


def footprint_relief(P, terrain, step=4.0):
    """(lowest, highest) terrain under a footprint polygon: its vertices, its edges every `step` m and a `step` m grid inside."""
    pts = []
    for ring in [P.exterior] + list(P.interiors):
        L = LineString(ring.coords)
        pts += [L.interpolate(t).coords[0] for t in np.arange(0.0, L.length, step)]
    x0, z0, x1, z1 = P.bounds
    gx, gz = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(z0 + step / 2, z1, step))
    gx, gz = gx.ravel(), gz.ravel()
    if len(gx):
        m = shapely.contains_xy(P, gx, gz); pts += list(zip(gx[m], gz[m]))
    a = np.array(pts, float); h = terrain.height(a[:, 0], a[:, 1])
    return float(np.min(h)), float(np.max(h))


def chunk_name(year, kind, source):
    if source == "existing_osm":
        return "Existing buildings"
    if kind == "house":
        return f"{year} generated houses"
    if source == "master_plan":
        return f"{year} master plan buildings"
    return f"{year} generated blocks"


def chunk_key(name):
    p = name.split(" ", 1)
    return (0, int(p[0]), p[1]) if p[0].isdigit() else (1, 0, name)


def landmark_lot_rows(D, bj, R):
    """Pseudo buildings for the own capacity of each landmark lot (use landmark) that carries no building of its own: a housing row of
    homes × LOT_M2_PER_HOME and a business row of jobs × LOT_M2_PER_JOB, kind LOT_KIND, no footprint (no mesh, empty bounds)."""
    lots = (D.get("lots") or {}).get("lots") or []; out = []
    with_b = {b.get("lot") for b in bj.get("buildings") or [] if b.get("lot")}
    for L in lots:
        cap = L.get("capacity") or {}; homes, jobs = int(cap.get("homes") or 0), int(cap.get("jobs") or 0)
        if L.get("use") != "landmark" or not (homes or jobs):
            continue
        if L["id"] in with_b:
            R.log(f"  {D['id']}: landmark lot {L['id']} ({L.get('registry_id')}) carries buildings of its own: their rows hold its capacity, "
                  f"no lot rows (a registry landmark lot should carry none)")
            continue
        P = Polygon(L["polygon"], L.get("holes") or []).buffer(0); c = P.representative_point()
        for use, n, m2 in (("housing", homes, LOT_M2_PER_HOME), ("business", jobs, LOT_M2_PER_JOB)):
            if n > 0:
                out.append({"id": f"{L['id']}:{use}", "lot": L["id"], "kind": LOT_KIND, "use": use, "gfa_m2": n * m2, "floors": 0, "height_m": 0.0,
                            "years": list(L.get("years") or [2025] * 4), "source": "registry", "registry_id": L.get("registry_id"),
                            "lot_point": (c.x, c.y), "lot_n": n})
        R.log(f"  {D['id']}: landmark lot {L['id']} ({L.get('registry_id')}): {homes} homes and {jobs} jobs of its own as mesh-less {LOT_KIND} "
              f"rows ({homes * LOT_M2_PER_HOME:.0f} m² housing, {jobs * LOT_M2_PER_JOB:.0f} m² business)")
    return out


def merge_buildings(base_dir, Ds, terrain, city, R):
    rows, cols = U.read_csv_rows(os.path.join(base_dir, U.F_CSV))
    nb0 = len(rows)
    assert all(int(r["bid"]) == i for i, r in enumerate(rows)), "buildings.csv bids must be 0..n-1"
    aql = U.read_aql_parts(os.path.join(base_dir, U.F_AQL))
    bounds = U.read_bounds(os.path.join(base_dir, U.F_BOUNDS))
    hide = U.read_hide(os.path.join(base_dir, U.F_HIDE))
    order = U.load_json(os.path.join(base_dir, U.F_ORDER))
    if Ds:                                       # (a run without districts keeps the base's csv byte-equal)
        cols = list(cols) + [c for c in NEW_COLS if c not in cols]
    res = {"rows": rows, "cols": cols, "aql": aql, "bounds": bounds, "hide": hide, "order": order, "solar": [], "bidmap": [], "changed": set(),
           "removed": set(), "touched": set(), "yards": []}
    if not Ds:
        return res
    xy = np.array([[float(r["x"]), float(r["z"])] for r in rows])
    removed, touched, new_b = set(), set(), []
    for D in Ds:
        A = D["area"]; inside = set(np.flatnonzero(shapely.contains_xy(A, xy[:, 0], xy[:, 1])).tolist())
        touched |= inside
        bj = D["buildings"]
        if bj is None:
            R.log(f"{D['id']}: no buildings.json — {len(inside)} buildings inside the area stay as they are"); continue
        kept = set()
        for b in bj["buildings"]:
            if b.get("bid") is not None and b.get("keep_mesh", True):
                bid = int(b["bid"])
                if not 0 <= bid < nb0:
                    R.log(f"  {D['id']}: kept building {b['id']} has bid {bid} that the base does not have — treated as new"); new_b.append((D, b, None)); continue
                kept.add(bid)
                if bid not in inside:
                    R.log(f"  {D['id']}: kept bid {bid} lies outside the area")
            else:
                new_b.append((D, b, int(b["bid"]) if b.get("bid") is not None else None))
        new_b += [(D, x, None) for x in landmark_lot_rows(D, bj, R)]
        rem = set(int(v) for v in bj.get("removed") or [])
        # solar: a district that lists its own fields ("solar", even empty) replaces the twin's panels inside its area; without the key
        # the twin's panels there stay (their rows kept; their meshes go to solar.json with the rest of the city's)
        has_solar = bj.get("solar") is not None
        solar_in = {b for b in inside - kept if rows[b]["kind"] == "solar"}
        if not has_solar:
            kept |= solar_in; solar_in = set()
        unlisted = inside - kept - rem - solar_in
        if unlisted:
            R.log(f"  {D['id']}: {len(unlisted)} twin buildings inside the area neither kept nor listed as removed → removed")
        removed |= rem | unlisted | solar_in
        if has_solar:
            res["solar"] += [{"y": [int(v) for v in s["years"]], "p": U.flat(s["polygon"], 1)} for s in bj["solar"]]
        R.log(f"buildings {D['id']}: {len(inside)} twin buildings in the area: {len(kept)} kept, {len(rem | unlisted)} removed; "
              + (f"{len(solar_in)} twin solar panels replaced by {len(bj['solar'])} district solar fields" if has_solar else "twin solar panels kept")
              + f"; {sum(1 for x in new_b if x[0] is D)} new")
    # ---- bids (CONTRACT §8, w49): the table holds U.BID_LIMIT = 131 072 numbers (256 × 512).
    # Existing houses only Overture has (source existing_osm, bid null) are numbered first, from their district's own range
    # (city.json#bids.existing_overture.by_district), in a stable order: district in the order merged, then the rounded centroid
    # (z, then x), then the building id. New buildings then take, in order: removed numbers in the district's first range, its
    # unused numbers, the same in its second range (city.json#bids.ranges2); only past both: other removed numbers, then append.
    taken = set(); assign = []
    rem_sorted = sorted(removed)
    nxt = [nb0]

    cand = {}

    def free_in(rg):
        """A free number of a range: a removed number first, then one the base does not have (≥ nb0). The caller always takes the
        number returned, so each range keeps one cursor over its candidates."""
        if rg not in cand:
            lo, hi = bisect.bisect_left(rem_sorted, rg[0]), bisect.bisect_right(rem_sorted, rg[1])
            cand[rg] = itertools.chain(rem_sorted[lo:hi], range(max(rg[0], nb0), rg[1] + 1))
        return next((v for v in cand[rg] if v not in taken), None)

    def is_ov(b, pref):
        return pref is None and b.get("source") == "existing_osm"

    def ov_key(x):
        D, b, _ = x
        try:
            c = Polygon(b["footprint"]).buffer(0).centroid; cz, cx = int(round(c.y)), int(round(c.x))
        except Exception:                          # an empty or broken footprint sorts first; merge logs it below
            cz = cx = -10 ** 9
        return (dist_order[D["id"]], cz, cx, str(b.get("id")))
    dist_order = {D["id"]: i for i, D in enumerate(Ds)}
    ov_b = sorted((x for x in new_b if is_ov(x[1], x[2])), key=ov_key)
    rest_b = [x for x in new_b if not is_ov(x[1], x[2])]
    n_ov = collections.Counter(); n_ov_out = 0; n_second = collections.Counter(); n_past = 0
    numbering = {"limit": U.BID_LIMIT, "overture": [], "own": [], "past_ranges": []}
    for D, b, pref in ov_b + rest_b:
        bid = None
        if is_ov(b, pref):
            org = U.overture_range(city, D["id"])
            bid = free_in(org) if org else None
            if bid is not None:
                n_ov[D["id"]] += 1; numbering["overture"].append(bid)
            else:
                n_ov_out += 1
                R.log(f"  {D['id']}: Overture house {b.get('id')}: " + ("its range is full" if org else "city.json has no existing_overture range")
                      + " — numbered like a new building")
        if bid is None and pref is not None and pref in removed and pref not in taken:
            bid = pref; numbering["own"].append(bid)
        if bid is None:
            for k, rg in enumerate(U.district_ranges(city, D["id"])):
                bid = free_in(rg)
                if bid is not None:
                    n_second[D["id"]] += k == 1; break
        if bid is None:
            n_past += 1
            bid = next((v for v in rem_sorted if v not in taken), None)
            past = True
        else:
            past = False
        if bid is None:
            while nxt[0] in taken:
                nxt[0] += 1
            bid = nxt[0]
        if bid >= U.BID_LIMIT:
            raise SystemExit(f"bid limit {U.BID_LIMIT} reached")
        if past:
            numbering["past_ranges"].append(bid)
        taken.add(bid); assign.append((D, b, bid))
    numbering["counts"] = {"overture": dict(n_ov), "overture_past_range": n_ov_out, "second_range": dict(n_second), "past_ranges": n_past}
    res["numbering"] = numbering
    R.log(f"bids: {sum(n_ov.values())} Overture-only existing houses numbered in their own range ("
          + ", ".join(f"{k} {v}" for k, v in n_ov.items()) + f"), {n_ov_out} past it; "
          f"{sum(n_second.values())} new buildings in a district's second range; {n_past} past every range of their district")
    nb = max([nb0] + [bid + 1 for _, _, bid in assign])
    R.log(f"bids: {len(removed)} removed, {len(assign)} new ({sum(1 for _, _, v in assign if v in removed)} reuse removed numbers, "
          f"{sum(1 for _, _, v in assign if v >= nb0)} appended), table {nb0} → {nb}")
    # ---- csv rows
    rows = [dict(r) for r in rows] + [None] * (nb - nb0)
    for bid in removed | set(range(nb0, nb)):
        old = rows[bid] or {}
        rows[bid] = {"bid": str(bid), "id": f"REMOVED_{bid:05d}", "district": "", "kind": "removed", "use": "none", "source": "removed", "year": "2099",
                     "floors": "0", "height_m": "0.0", "gfa_m2": "0.0", "parcel": "", "x": old.get("x", "0.0"), "z": old.get("z", "0.0"),
                     "ground_m": old.get("ground_m", "0.0"), "easting": old.get("easting", "663000.0"), "northing": old.get("northing", "4830000.0")}
    meshes = collections.defaultdict(list)
    B = np.zeros((nb, 4), np.float32); B[:nb0] = bounds
    for bid in removed | set(range(nb0, nb)):
        B[bid] = 0
    plinths, low_outline, drops, canopies, docks = [], [], [], [], 0; nlot = 0
    for D, b, bid in assign:
        if b.get("kind") == LOT_KIND:                   # a landmark lot's own capacity: a row, no mesh, an empty box
            x, z = b["lot_point"]; g = float(terrain.height(x, z)); year = int(b["years"][0])
            rows[bid] = {"bid": str(bid), "id": f"{district_name(D['id']).upper() or 'CITY'}_{LOT_KIND}_{year}_{bid:05d}", "district": district_name(D["id"]),
                         "kind": LOT_KIND, "use": b["use"], "source": SRC_CSV["registry"], "year": str(year), "floors": "0", "height_m": "0.0",
                         "gfa_m2": f"{float(b['gfa_m2']):.1f}", "parcel": b["lot"], "x": f"{x:.1f}", "z": f"{z:.1f}", "ground_m": f"{g:.1f}",
                         "easting": f"{663000 + x:.1f}", "northing": f"{4830000 + z:.1f}"}
            B[bid] = 0; res["bidmap"].append([D["id"], b.get("id"), bid]); nlot += 1
            continue
        fp = b["footprint"]; P = Polygon(fp).buffer(0); c = P.centroid
        ground = float(terrain.height(c.x, c.y)); base_y = float(b.get("base_y") if b.get("base_y") is not None else ground)
        # the walls reach the lowest ground under the footprint (merge samples its outline every 4 m and a 4 m grid inside); on a slope
        # (gen_buildings' `plinth`, rule 3) the part below base_y is the building's plinth from the lower of plinth.from_y and that ground,
        # written as plinth_m for AlatauRoofs; ground_m = base_y, the floor level, so the facade's storeys start at the floor
        lo, hi = footprint_relief(P, terrain) if not P.is_empty and P.geom_type == "Polygon" else (ground, ground)
        pl = b.get("plinth") or None
        if pl:
            from_y = float(pl.get("from_y", lo)); low = min(from_y, lo); plinth_m = max(base_y - low, 0.0)
            plinths.append((plinth_m, float(pl.get("slope_pct") or 0), b.get("id")))
            if lo < from_y - PLINTH_FROM_TOL_M:
                low_outline.append((from_y - lo, b.get("id")))
        else:
            low = lo; plinth_m = 0.0
            if hi - lo > PLINTH_M:
                drops.append((hi - lo, base_y - lo, b.get("id")))
        ground = base_y
        year = int((b.get("years") or [2025])[0]); src = SRC_CSV.get(b.get("source"), "generated"); kind = b.get("kind") or "other"
        if src == "existing_osm":
            kind = "existing"
        h = float(b.get("height_m") or 3.0 * float(b.get("floors") or 1))
        model = str(b.get("model") or "")
        dock = ""
        if b.get("dock_side") and b.get("docks"):
            (dx0, dz0), (dx1, dz1) = b["dock_side"][0], b["dock_side"][-1]
            dock = f"{float(dx0):.2f} {float(dz0):.2f} {float(dx1):.2f} {float(dz1):.2f} {int(b['docks'])}"; docks += 1
        rows[bid] = {"bid": str(bid), "id": f"{district_name(D['id']).upper() or 'CITY'}_{kind}_{year}_{bid:05d}", "district": district_name(D["id"]),
                     "kind": kind, "use": b.get("use") or "", "source": src, "year": str(year), "floors": str(int(b.get("floors") or 1)),
                     "height_m": f"{h:.1f}", "gfa_m2": f"{float(b.get('gfa_m2') or 0):.1f}", "parcel": "", "x": f"{c.x:.1f}", "z": f"{c.y:.1f}",
                     "ground_m": f"{ground:.1f}", "easting": f"{663000 + c.x:.1f}", "northing": f"{4830000 + c.y:.1f}",
                     "model": model, "plinth_m": f"{plinth_m:.2f}" if pl else "", "dock": dock}
        if b.get("truck_yard"):
            for ring in flat_rings(b["truck_yard"], 1):
                yd = {"p": ring, "y": eff_years(year, b.get("source"), b.get("use")), "b": bid}
                if dock:                                                   # the shed's dock side: FilmRoads draws the bays
                    yd["d"] = [round(float(v), 2) for v in dock.split()]
                res["yards"].append(yd)
        col = COL.get(kind, 19)
        if src == "master_plan" and kind in ("education", "health"):
            col = 15 if kind == "education" else 16
        if model in CANOPY_MODELS:
            m = canopy_mesh(fp, base_y, base_y + h, col, terrain)
            if m is not None:
                canopies.append((b.get("id"), m[3])); m = m[:3]
        else:
            m = extrude(fp, min(base_y, low) - 0.3, base_y + h, col, 22 if kind == "house" else col)
        if m is None:
            R.log(f"  {D['id']}: building {b.get('id')} has an empty footprint — row written, no mesh"); continue
        meshes[chunk_name(year, kind, src)].append((m, year, bid))
        x0, z0, x1, z1 = P.bounds; B[bid] = (x0, z0, x1, z1)
        res["bidmap"].append([D["id"], b.get("id"), bid])
    if plinths:
        plinths.sort(reverse=True)
        R.log(f"buildings: {len(plinths)} new buildings on a slope stand on a plinth (`plinth` of gen_buildings, rule 3; buildings.csv plinth_m, "
              f"drawn by AlatauRoofs): " + ", ".join(f"{i} {p:.1f} m at {sl:.1f} %" for p, sl, i in plinths[:6]) + (" …" if len(plinths) > 6 else "")
              + (f"; on {len(low_outline)} of them the outline reaches lower ground than plinth.from_y (the most: "
                 + ", ".join(f"{i} {d:.1f} m" for d, i in sorted(low_outline, reverse=True)[:4]) + "): the plinth goes down to it" if low_outline else ""))
    if drops:
        drops.sort(reverse=True)
        R.log(f"buildings: {len(drops)} new buildings without a `plinth` stand on ground that falls more than {PLINTH_M} m under their footprint "
              f"(terraced lots, slopes up to the plinth threshold; walls down to the lowest ground, no plinth drawn): "
              + ", ".join(f"{i} {d:.1f} m" for d, _, i in drops[:4]))
    if canopies or docks or res["yards"]:
        R.log(f"buildings: {len(canopies)} canopies as a roof on posts (" + ", ".join(f"{i} {n} posts" for i, n in canopies[:6])
              + f"); {docks} sheds with dock doors (buildings.csv dock), {len(res['yards'])} truck yards (film_roads yards, noplant)")
    res["plinths"] = len(plinths); res["lot_rows"] = nlot
    # ---- AQL: drop removed meshes, append new ones to their chunks
    gone = np.array(sorted(removed), np.int64)
    out = []
    names = {o[0]: i for i, o in enumerate(aql)}
    for name, kind, V, T, col, yr, bid in aql:
        keep = ~np.isin(bid, gone) if len(gone) else np.ones(len(bid), bool)
        if keep.all() and name not in meshes:
            out.append([name, kind, V, T, col, yr, bid]); continue
        T2 = T[keep]; used = np.unique(T2); remap = np.full(len(V), -1, np.int64); remap[used] = np.arange(len(used))
        Vn, Tn, Cn, Yn, Bn = [V[used]], [remap[T2].astype(np.uint32)], [col[keep]], [yr[keep]], [bid[keep]]
        nv = len(used)
        for (mv, mt, mc), year, b in meshes.pop(name, []):
            Vn.append(mv); Tn.append(mt + nv); Cn.append(mc); Yn.append(np.full(len(mt), year, np.uint16)); Bn.append(np.full(len(mt), b, np.int32)); nv += len(mv)
        out.append([name, kind, np.concatenate(Vn), np.concatenate(Tn), np.concatenate(Cn), np.concatenate(Yn), np.concatenate(Bn)])
    for name, ms in meshes.items():
        Vn, Tn, Cn, Yn, Bn, nv = [], [], [], [], [], 0
        for (mv, mt, mc), year, b in ms:
            Vn.append(mv); Tn.append(mt + nv); Cn.append(mc); Yn.append(np.full(len(mt), year, np.uint16)); Bn.append(np.full(len(mt), b, np.int32)); nv += len(mv)
        obj = [name, 0, np.concatenate(Vn), np.concatenate(Tn), np.concatenate(Cn), np.concatenate(Yn), np.concatenate(Bn)]
        pos = next((i for i, o in enumerate(out) if chunk_key(o[0]) > chunk_key(name)), len(out))
        out.insert(pos, obj)
    del names
    res["aql"] = out
    # ---- hide lists shrink: nothing inside a merged area and no reassigned number stays hidden
    drop = touched | removed | set(v for _, _, v in assign)
    res["hide"] = [(b, c) for b, c in hide if b not in drop]
    keep_i = [i for i, b in enumerate(order["b"]) if b not in drop]
    res["order"] = {k: [v[i] for i in keep_i] for k, v in order.items()}
    R.log(f"hide lists: hide_extra {len(hide)} → {len(res['hide'])}, map_order {len(order['b'])} → {len(keep_i)}")
    res.update(rows=rows, bounds=B, removed=removed, touched=touched, changed=removed | set(v for _, _, v in assign))
    return res


def eff_years(year, source, use):
    """Opening year per scenario (base, fast, slow, infra-first) as TwinScenario.EffectiveYear computes it (float32, round half even)."""
    y = int(year)
    if y <= 2026 or source == "existing_osm":
        return [y] * 4
    dy = np.float32(y - 2026)
    fast = 2026 + max(1, int(round(float(dy * np.float32(0.75)))))
    slow = 2026 + int(round(float(dy * np.float32(1.3))))
    return [y, fast, 2099 if slow > 2050 else slow, y + 2 if use == "housing" and y <= 2036 else y]


def move_solar(res, R):
    """Solar panels out of the buildings layer, city-wide: their triangles leave the chunks, their outlines become solar.json fields
    (the convex hull of each panel row's mesh; the rows of one opening year closed by SOLAR_CLOSE_M into plant outlines). The csv rows,
    bid_bounds and every per-bid array stay as they are."""
    rows = res["rows"]
    sol = np.array(sorted(i for i, r in enumerate(rows) if r and r["kind"] == "solar"), np.int64)
    res["solar_moved"] = {"rows": int(len(sol)), "triangles": 0, "fields": 0}
    if not len(sol):
        return
    pts = collections.defaultdict(list); out = []; ntri = 0
    for name, kind, V, T, col, yr, bid in res["aql"]:
        m = np.isin(bid, sol)
        if not m.any():
            out.append([name, kind, V, T, col, yr, bid]); continue
        tb, tv = bid[m], T[m]; ntri += int(m.sum())
        o = np.argsort(tb, kind="stable"); tb, tv = tb[o], tv[o]
        ub, st = np.unique(tb, return_index=True); st = list(st) + [len(tb)]
        for i, b in enumerate(ub):
            pts[int(b)].append(V[np.unique(tv[st[i]:st[i + 1]].ravel())][:, [0, 2]])
        keep = ~m
        if keep.any():
            T2 = T[keep]; used = np.unique(T2); remap = np.full(len(V), -1, np.int64); remap[used] = np.arange(len(used))
            out.append([name, kind, V[used], remap[T2].astype(np.uint32), col[keep], yr[keep], bid[keep]])
        else:
            R.log(f"  solar: chunk '{name}' held only solar panels — left out of the layer")
    res["aql"] = out
    groups = collections.defaultdict(list)
    for b, v in pts.items():
        r = rows[b]; groups[tuple(eff_years(r["year"], r["source"], r["use"]))].append(shapely.MultiPoint(np.concatenate(v)).convex_hull)
    fields, holes = [], 0
    for ys, hs in sorted(groups.items()):
        g = shapely.union_all([h.buffer(SOLAR_CLOSE_M, join_style=2) for h in hs]).buffer(-SOLAR_CLOSE_M, join_style=2).simplify(0.5)
        for p in getattr(g, "geoms", [g]):
            if p.is_empty or p.geom_type != "Polygon" or p.area < 1.0:
                continue
            holes += len(p.interiors)
            fields.append({"y": list(ys), "p": U.flat(list(orient(p).exterior.coords)[:-1], 1)})
    res["solar"] += fields
    res["solar_moved"] = {"rows": int(len(sol)), "triangles": ntri, "fields": len(fields)}
    R.log(f"solar: {len(sol)} panel rows ({ntri} triangles, {len(pts)} with a mesh) moved out of the buildings layer into {len(fields)} "
          f"solar.json fields ({sum(shapely.Polygon(np.reshape(f['p'], (-1, 2))).area for f in fields) / 1e4:.0f} ha); csv rows kept"
          + (f"; {holes} holes inside fields filled" if holes else ""))


# ================================================================== LRT
def merge_lrt(base_routes, base_lrt, Ds, R, norms=None):
    """lrt_routes.json (routes clipped by the areas + the districts' lines with sec/h/ends) and the construction.json `lrt` block.
    A base station outside the areas is replaced too when it lies on a route the areas clipped and closer than the minimum station
    spacing (norms lrt.station_spacing_km min) to a district station: the district station serves that stop."""
    import gen_twin as GT
    routes = base_routes; lrt = base_lrt
    lines = [(D, ln) for D in Ds if D["lrt"] for ln in D["lrt"].get("lines") or []]
    if not lines:
        return routes, lrt
    area = unary_union([D["area"] for D in Ds if D["lrt"]])
    out = []; km_delta = [0.0] * len(lrt["phase_km"])

    def phase(z):
        return next((i for i, (lo, hi, _) in enumerate(GT.LRT_PHASES) if lo <= z < hi), 0)
    clipped = []
    for r in routes["routes"]:
        g = r["pts"]; pts = [(g[k], g[k + 1]) for k in range(0, len(g), 2)]
        pieces = clip_pieces(pts, area)
        if pieces is None:
            out.append(r); continue
        clipped.append(LineString(pts))
        L0 = LineString(pts)
        inside = L0.intersection(area)
        km_delta[phase(inside.centroid.y)] -= inside.length / 1000
        if WHOLE_CITY <= {D["id"] for D in Ds}:
            # the whole city merged: the districts' lines replace the base trunk, and what the areas leave of it are stubs in the
            # strips between districts (a 180 m viaduct at (1300, −1679) between Golden and Growing-E stood alone over the steppe)
            for c in pieces:
                km_delta[phase(float(np.mean([p[1] for p in c])))] -= U.polyline_len(c) / 1000
            R.log(f"lrt: route {r['name']}: {len(pieces)} pieces outside the areas dropped (the whole city is merged)")
            continue
        for k, c in enumerate(pieces):
            q = dict(r, pts=[round(float(v), 1) for p in c for v in p])
            if len(pieces) > 1:
                q["name"] = f"{r['name']}_{k + 1}"
            out.append(q)
        R.log(f"lrt: route {r['name']} clipped by the area into {len(pieces)} pieces ({inside.length:.0f} m inside)")
    sec_code = {"ground": 0, "elevated": 1, "tunnel": 2}
    for D, ln in lines:
        P = ln["pts"]; xz = [(p[0], p[1]) for p in P]
        sec = []
        for s in ln.get("sections") or []:
            sec += [round(float(s["from_m"]), 1), round(float(s["to_m"]), 1), sec_code.get(s.get("kind"), 0)]
        ends = [{"depot": 1, "joint": 2}.get(e.get("kind"), 0) for e in (ln.get("ends") or [])][:2] or [0, 0]
        out.append({"name": f"{D['id']}:{ln['id']}", "pts": U.flat(xz, 1), "sec": sec, "h": [round(float(p[2]), 2) for p in P], "ends": ends})
        L = U.polyline_len(xz); km_delta[phase(float(np.mean([p[1] for p in xz])))] += L / 1000
    stations_named = [s for s in routes.get("stations") or [] if not area.contains(Point(s["x"], s["z"]))]
    routes = dict(routes, routes=out, stations=stations_named)
    st = [s for s in lrt["stations"] if not area.contains(Point(s[0], s[1]))]
    n_rm = len(lrt["stations"]) - len(st)
    # a base stop next to a district station on the same (clipped) route: the district station replaces it
    smin = float((((norms or {}).get("norms") or {}).get("lrt.station_spacing_km") or {}).get("value", {}).get("min") or 0.8) * 1000
    dst = [(float(s["x"]), float(s["z"]), s.get("id")) for _, ln in lines for s in ln.get("stations") or []]
    near = []
    for s in st:
        on = any(L.distance(Point(s[0], s[1])) < LRT_ON_ROUTE_M for L in clipped)
        d = min(((math.hypot(s[0] - x, s[1] - z), i) for x, z, i in dst), default=(1e9, None))
        if on and d[0] < smin:
            near.append((s, d))
    if near:
        st = [s for s in st if all(s is not n for n, _ in near)]
        R.log(f"lrt: {len(near)} base stations outside the areas on a clipped route within {smin:.0f} m of a district station replaced by it ("
              + ", ".join(f"({n[0]}, {n[1]}) → {i} {d:.0f} m" for n, (d, i) in near) + ")")
    for D, ln in lines:
        for s in ln.get("stations") or []:
            st.append([int(round(s["x"])), int(round(s["z"])), phase(s["z"])])
    lrt = dict(lrt, stations=st, phase_km=[round(a + b, 1) for a, b in zip(lrt["phase_km"], km_delta)])
    R.log(f"lrt: {n_rm + len(near)} stations inside the areas or next to their stations replaced by {sum(len(ln.get('stations') or []) for _, ln in lines)} district stations; "
          f"phase km {base_lrt['phase_km']} → {lrt['phase_km']}")
    return routes, lrt


# ================================================================== features, districts, norms
def flat_rings(P, nd=1):
    """Flat open rings of polygon P rounded to nd decimals. Rounding can pinch a ring into a bow (two vertices 0.1 m apart
    swap sides); such a ring is repaired and split into its simple parts (holes dropped, slivers under 0.5 m² left out)."""
    q = [(round(float(v[0]), nd), round(float(v[1]), nd)) for v in P]
    if len(q) >= 3 and Polygon(q).is_valid:
        return [[c for v in q for c in v]]
    out = []
    for g in shapely.get_parts(shapely.make_valid(Polygon([tuple(v[:2]) for v in P]))):
        for h in shapely.get_parts(g):
            if h.geom_type != "Polygon" or h.area < 0.5:
                continue
            for e in (h, h.simplify(0.05), h.buffer(0.1, join_style=2)):
                r = [(round(x, nd), round(y, nd)) for x, y in list(e.exterior.coords)[:-1]]
                if len(r) >= 3 and Polygon(r).is_valid:
                    out.append([c for v in r for c in v])
                    break
    return out


def merge_rail(Ds, terrain, R):
    """rail.json for Unity (RailLayer) from the districts' spec `rail` blocks (Gate v1.2, CONTRACT): per line its tracks as flat
    [x, z, rail head y] points, years per scenario, gauge, buffer stops [x, z, …] and edge joints [x, z, y, …]; per platform its
    ring, surface height, years and track. Returns (rail json, noplant polygons: each line's corridor and each platform + 0.5 m).
    The base railways (lib.rail: the Turksib tracks of W34 rail.geojson) are only looked up for the log: the nearest one to each
    edge joint, where the line goes on beyond the city."""
    lines, plats, nop = [], [], []
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from lib import rail as LR
    except ImportError:
        LR = None
    for D in Ds:
        rb = (D.get("spec") or {}).get("rail") or {}
        for L in rb.get("lines") or []:
            yrs = [int(v) for v in (L.get("years") or [])[:4]]
            if len(yrs) != 4:
                R.log(f"  {D['id']}: rail line {L.get('id')} without years[4]: left out"); continue
            tracks, low = [], []
            for t in L.get("tracks") or []:
                P = [(float(q[0]), float(q[1]), float(q[2])) for q in t.get("pts") or [] if len(q) >= 3]
                if len(P) < 2:
                    continue
                tracks.append({"id": t.get("id") or "", "side": t.get("side") or "", "p": [round(v, 2) for q in P for v in q]})
                g = terrain.height(np.array([q[0] for q in P]), np.array([q[1] for q in P]))
                low.append(float(np.min(np.array([q[2] for q in P]) - RAIL_DECK_M - g)))
            if not tracks:
                R.log(f"  {D['id']}: rail line {L.get('id')} has no track with two points [x, z, y]: left out"); continue
            ends = [round(float(v), 2) for e in L.get("ends") or [] if e.get("kind") == "buffer_stop" for v in (e["x"], e["z"])]
            joints = [round(float(v), 2) for j in L.get("edge_joints") or [] for v in (j["x"], j["z"], j.get("y") or 0.0)]
            lines.append({"id": L.get("id") or "", "name": L.get("name_ru") or L.get("id") or "", "gauge": int(L.get("gauge_mm") or 1520),
                          "y": yrs, "tracks": tracks, "ends": ends, "joints": joints})
            corr = L.get("corridor") or []
            if len(corr) >= 3:
                nop += [{"y": yrs, "p": r} for r in flat_rings(corr, 1)]
            near = ""
            if LR is not None and L.get("edge_joints"):
                try:
                    ej = L["edge_joints"][0]; pt = Point(ej["x"], ej["z"]); tr = LR.tracks(pt.buffer(5000.0))
                    if tr:
                        d, t0 = min((LineString(t["P"]).distance(pt), t) for t in tr)
                        near = f"; the nearest base railway track (lib.rail, W34) is {d:.0f} m from its edge joint ({t0['name'] or t0['id'][:8]})"
                except Exception as ex:                                   # the W34 data is not needed for the merge
                    near = f"; base railways not read ({type(ex).__name__})"
            R.log(f"  {D['id']}: rail line {L.get('id')} ({L.get('gauge_mm') or 1520} mm, from {yrs[0]}): {len(tracks)} tracks, "
                  f"{sum(len(t['p']) // 3 for t in tracks)} points, deck underside {min(low):.1f} m over the terrain at the lowest, "
                  f"{len(ends) // 2} buffer stops, {len(joints) // 3} edge joints{near}")
        for P in rb.get("platforms") or []:
            ring = P.get("polygon") or []
            yrs = [int(v) for v in (P.get("years") or [])[:4]]
            if len(ring) < 3 or len(yrs) != 4 or P.get("y") is None:
                R.log(f"  {D['id']}: platform {P.get('id')} without polygon, years[4] or y: left out"); continue
            plats.append({"id": P.get("id") or "", "line": P.get("line") or "", "track": (P.get("tracks") or [""])[0], "y": round(float(P["y"]), 2),
                          "yr": yrs, "p": [round(float(v), 2) for q in ring for v in q[:2]]})
            nop += [{"y": yrs, "p": r} for r in flat_rings(list(Polygon(ring).buffer(RAIL_NOPLANT_M, join_style=2).exterior.coords)[:-1], 1)]
    if lines or plats:
        R.log(f"rail: {len(lines)} lines, {len(plats)} platforms → rail.json (RailLayer); {len(nop)} noplant polygons (corridors, platforms + {RAIL_NOPLANT_M} m)")
    return {"v": 1, "lines": lines, "platforms": plats}, nop


def features(Ds, city, norms, solar):
    noplant, parking = [], []
    for D in Ds:
        f = D["features"]
        if not f:
            continue
        for n in f.get("noplant") or []:
            y = [int(v) for v in n.get("years") or [2025] * 4]
            noplant += [{"y": y, "p": r} for r in flat_rings(n["polygon"], 1)]
        for p in f.get("parking") or []:
            parking.append({"t": {"surface": 0, "multi": 1, "underground": 2}.get(p.get("type"), 0), "cap": int(p.get("cap") or 0),
                            "lv": int(p.get("levels") or 1), "y": [int(v) for v in p.get("years") or [2025] * 4], "p": U.flat(p["polygon"], 1)})
    dd = city["districts"]
    polys = []
    for i, (key, name) in enumerate((("gate", "Gate"), ("golden", "Golden"), ("growing", "Growing"), ("green", "Green"))):
        src = dd.get(key) or {}
        poly = src.get("polygon")
        if key == "growing" and not poly:
            u = unary_union([Polygon(dd[k]["polygon"]) for k in ("growing_w", "growing_e")]).buffer(0)
            poly = list(max(getattr(u, "geoms", [u]), key=lambda g: g.area).exterior.coords)
        polys.append({"id": i, "name": name, "p": U.flat(poly, 1)})

    def nv(key, sub=None):
        v = norms["norms"][key]["value"]
        return v[sub] if sub else v
    keys = ["schools.places_per_1000_genplan", "kindergartens.places_per_1000_genplan", "schools.radius_m", "kindergartens.radius_m", "clinics.polyclinic_radius_m"]
    src = sorted(set(norms["norms"][k]["source"]["label"] for k in keys))
    ns = {"school_places_per_1000": nv(keys[0]), "kindergarten_places_per_1000": nv(keys[1]), "school_radius_m": nv(keys[2]),
          "kindergarten_radius_m": nv(keys[3], "multi_storey"), "polyclinic_radius_m": nv(keys[4]),
          "source_ru": "spec/norms.json: " + ", ".join(f"{k} ({norms['norms'][k]['source']['label']})" for k in keys) + "; источники: " + ", ".join(src)}
    return ({"v": 1, "polys": noplant}, {"v": 1, "lots": parking}, {"v": 1, "d": polys}, {"v": 1, "f": solar}, ns)


def stroke_outer(s, profiles):
    """Half width to the outer edge of what FilmRoads draws for a new stroke (FilmRoads.Halves of its profile, else StrokeDims)."""
    pi = s.get("p", -1)
    if isinstance(pi, int) and 0 <= pi < len(profiles):
        pr = profiles[pi]; ln = pr.get("lanes") or [1, 1]; lw = float(pr.get("lane_w") or 3.0) or 3.0
        sw, vg, bk, pk = ((pr.get(k) or [0, 0]) for k in ("sidewalk_w", "verge_w", "bike_w", "parking_w"))
        # one carriageway of a divided road (lanes [n, 0] with the road's median): its lanes only, as FilmRoads.OneCarriageway
        one_cw = ln[0] > 0 and ln[1] <= 0 and float(pr.get("median_w") or 0) > 0.5
        car = (max(0, ln[0]) + max(0, ln[1])) * lw * 0.5 + (0.0 if one_cw else float(pr.get("median_w") or 0) * 0.5) + (pk[0] + pk[1]) * 0.5
        side = max(sw[0] + vg[0] + bk[0], sw[1] + vg[1] + bk[1])
        if s.get("t") == "bike_path":
            car = max(0.75, (bk[0] + bk[1]) * 0.5); side = max(vg[0], vg[1])
        return car + side
    if s.get("k") == 2:
        return 4.0
    half, walk = {"highway": (11.0, 0.0), "ring": (9.0, 0.0), "main": (7.5, 3.5)}.get(s.get("c"), (4.0, 2.4))
    if s.get("k") == 1:
        half = {"highway": 6.0, "ring": 5.5, "main": 3.8}.get(s.get("c"), 3.2)
    return half + walk


def facility_sites(Ds, roads, film, bounds, R):
    """place(F) for twin_rerun.rerun: every synthetic facility (substations, boiler houses, AGRS) whose model place lies in a merged
    area moves to the lot of a spec utility zone (1) that names it (zone id or a `facility`/`facilities` field with its id), (2) whose
    text says its kind (FAC_KIND_WORDS), (3) of its trade (FAC_HUB_WORDS: an engineering hub, an energy corridor): the zone's largest
    lot not yet taken that holds it (FAC_FIT; any for (1)), nearest zone first, at the lot's deepest point (polylabel), the larger
    facilities first; (4) with none, to the nearest free ground, inside or outside the areas: on no lot, outside every red line (a
    street's red_line_w, base roads by class) and interchange zone, FAC_RADIUS_M clear of them, of every standing building (district
    footprints, the twin's footprint boxes `bounds`) and of the facilities placed before it. Logged."""
    areas = [D["area"] for D in Ds]
    if not areas:
        return None
    lots, zone_lots, zone_txt = [], collections.defaultdict(list), {}
    for D in Ds:
        bz = {b["id"]: b.get("zone") for b in ((D.get("blocks") or {}).get("blocks") or [])}
        for z in ((D.get("spec") or {}).get("zones") or []):
            if z.get("use") == "utility":
                zone_txt[z["id"]] = (z, " ".join(str(z.get(k) or "") for k in ("id", "name_ru", "name_en", "why", "kind")).lower())
        for L in ((D.get("lots") or {}).get("lots") or []):
            P = Polygon(L["polygon"]).buffer(0)
            if P.is_empty:
                continue
            lots.append(P); zid = bz.get(L.get("block"))
            if L.get("use") in ("utility", "substation") and zid in zone_txt:
                zone_lots[zid].append((P, L["id"]))
    reach = unary_union(areas).buffer(FAC_SEARCH_M + 200); shapely.prepare(reach)
    obst = list(lots)
    for D in Ds:
        for b in ((D.get("buildings") or {}).get("buildings") or []):
            if b.get("footprint") and len(b["footprint"]) >= 3:
                obst.append(Polygon(b["footprint"]).buffer(0))
    bb = np.asarray(bounds, float) if bounds is not None and len(bounds) else np.zeros((0, 4))
    live = (bb[:, 2] > bb[:, 0]) & (bb[:, 3] > bb[:, 1]) if len(bb) else np.zeros(0, bool)
    boxes = shapely.box(bb[live, 0], bb[live, 1], bb[live, 2], bb[live, 3]) if live.any() else np.zeros(0, dtype=object)
    obst += [g for g in boxes[shapely.intersects(boxes, reach)]] if len(boxes) else []
    prof = roads.get("profiles") or []; red = []
    for e in roads["edges"]:
        g = e["g"]; xz = [(g[k], g[k + 1]) for k in range(0, len(g), 2)]
        if len(xz) < 2 or not reach.intersects(LineString(xz)):
            continue
        w = float(prof[e["p"]].get("red_line_w") or 0) if e.get("p") is not None and 0 <= e["p"] < len(prof) else 0.0
        w = w or RED_LINE_DEFAULT_M.get(e.get("c"), 20.0)
        red.append(LineString(xz).buffer(w / 2, cap_style=2))
    zones = [Point(z[0], z[1]).buffer(float(z[2])) for z in film.get("zones") or []]
    tree_o = shapely.STRtree(obst + red + zones) if (obst or red or zones) else None
    taken, deep, sites = set(), {}, []           # sites: (x, z, r) of the facilities already placed on free ground

    def deepest(P, lid):
        if lid not in deep:
            q = polylabel(P if P.geom_type == "Polygon" else max(P.geoms, key=lambda g: g.area), tolerance=1.0)
            deep[lid] = (q, float(P.boundary.distance(q)))
        return deep[lid]

    def free(x, z, r):
        if any(math.hypot(x - sx, z - sz) < r + sr + 10.0 for sx, sz, sr in sites):
            return False
        return tree_o is None or len(tree_o.query(Point(x, z).buffer(r, 8), predicate="intersects")) == 0

    def place(F):
        moved = []
        for f in sorted(F, key=lambda f: -FAC_RADIUS_M.get(f.get("kind"), 20.0)):
            if not f.get("synthetic") or not any(A.contains(Point(f["x"], f["z"])) for A in areas):
                continue
            x0, z0, kind = float(f["x"]), float(f["z"]), f.get("kind"); here = Point(x0, z0); r = FAC_RADIUS_M.get(kind, 20.0)
            open_z = {zid: [t for t in zone_lots.get(zid, []) if t[1] not in taken] for zid in zone_txt}
            tiers = (([zid for zid, (z, txt) in zone_txt.items() if f["id"].lower() in zid.lower() or f["id"] == z.get("facility")
                       or f["id"] in (z.get("facilities") or [])], "its spec utility lot"),
                     ([zid for zid, (z, txt) in zone_txt.items() if any(w.lower() in txt for w in FAC_KIND_WORDS.get(kind, ()))],
                      "a spec utility lot of its kind"),
                     ([zid for zid, (z, txt) in zone_txt.items() if any(w.lower() in txt for w in FAC_HUB_WORDS.get(kind, ()))],
                      "a spec utility lot of its trade"))
            how, seen = None, set()
            for ti, (zl, label) in enumerate(tiers):
                fits = {q: [t for t in open_z[q] if ti == 0 or deepest(*t)[1] >= FAC_FIT * r] for q in zl if q not in seen}
                seen |= set(zl); zl = [q for q in fits if fits[q]]
                if not zl:
                    continue
                zid = min(zl, key=lambda q: min(t[0].distance(here) for t in fits[q]))
                P, lid = max(fits[zid], key=lambda t: t[0].area); q, dq = deepest(P, lid)
                taken.add(lid); how = (q.x, q.y, f"{label} {lid} (zone {zid}, {P.area:.0f} m², {dq:.0f} m from its edge)"); break
            if how is None:
                best = None
                for rad in np.arange(0.0, FAC_SEARCH_M + 1e-6, FAC_STEP_M):
                    n = max(1, int(2 * math.pi * rad / FAC_STEP_M))
                    for k in range(n):
                        a = 2 * math.pi * k / n; x, z = x0 + rad * math.cos(a), z0 + rad * math.sin(a)
                        if free(x, z, r):
                            best = (x, z); break
                    if best:
                        break
                if best is None:
                    R.log(f"  facilities: {f['id']} «{f['name']}» finds no free ground within {FAC_SEARCH_M:.0f} m: stays at ({x0:.0f}, {z0:.0f})"); continue
                inside = any(A.contains(Point(best)) for A in areas); sites.append((best[0], best[1], r))
                how = (best[0], best[1], f"free ground {math.hypot(best[0] - x0, best[1] - z0):.0f} m from its model place, "
                       f"{'inside' if inside else 'outside'} the area (no lot, outside red lines and interchanges, {r:.0f} m clear of them and of buildings)")
            f["x"], f["z"] = int(round(how[0])), int(round(how[1]))
            moved.append(f"{f['id']} ({x0:.0f}, {z0:.0f}) → ({f['x']}, {f['z']}) on {how[2]}")
        R.log(f"facilities: {len(moved)} synthetic facilities of the twin inside the areas placed" + (": " + "; ".join(moved) if moved else ""))
    return place


def road_noplant(film, terrain, R, drives=None):
    """noplant.json polygons of the new roads that FilmTrees must keep clear: bridge and overpass spans (st 3, 4) and every ramp (k 2, but
    its tunnels) to the outer edge of what is drawn + NOPLANT_EDGE_M; embankments (st 1, and street pieces NOPLANT_RAISED_M or more above
    the terrain) also over their side slopes (NOPLANT_SLOPE × height); turnaround pads + PAD_PAD_M. Pieces of at most NOPLANT_PIECE_M,
    each one simple ring without holes, with the years of its stroke. Drives (the last `drives` strokes; by class when None) are left out;
    a spec street of a driveway_* class (a spec error) is a street here."""
    profiles = film.get("profiles") or []; out = []; metres = collections.Counter()
    first_drive = len(film["s"]) - drives if drives is not None else None
    for i_s, s in enumerate(film["s"]):
        if s.get("e", -1) < 0 or (i_s >= first_drive if first_drive is not None else str(s.get("t") or "").startswith("driveway")):
            continue
        g = s["g"]; P = [(g[k], g[k + 1]) for k in range(0, len(g), 2)]
        st = s.get("st") or []; ramp = s.get("k") == 2; H = s.get("h") if len(s.get("h") or []) == len(P) else None
        if len(P) < 2 or not (ramp or H or any(st[k + 2] in (1, 3, 4) for k in range(0, len(st), 3))):
            continue
        L = LineString(P)
        if L.length < 1.0:
            continue
        cum = [0.0]
        for i in range(1, len(P)):
            cum.append(cum[-1] + math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]))
        outer = stroke_outer(s, profiles) + NOPLANT_EDGE_M
        n = max(2, int(math.ceil(L.length / 2.0)) + 1); step = L.length / (n - 1); runs, cur = [], None
        for i in range(n):
            c = min(L.length, i * step); q = L.interpolate(c)
            code = next((int(st[k + 2]) for k in range(0, len(st), 3) if st[k] - 0.05 <= c <= st[k + 1] + 0.05), 0)
            dh = 0.0
            if H is not None:
                j = max(1, min(len(P) - 1, bisect.bisect_left(cum, c))); seg = cum[j] - cum[j - 1]
                t = 0.0 if seg < 1e-9 else (c - cum[j - 1]) / seg
                dh = H[j - 1] + (H[j] - H[j - 1]) * t - float(terrain.height(q.x, q.y))
            if code in (3, 4):
                r, kind = outer, "deck"
            elif code == 1 or (code == 0 and dh >= NOPLANT_RAISED_M):
                r, kind = outer + NOPLANT_SLOPE * max(dh, 0.0 if H is not None else 2.0), "fill"
            elif ramp and code != 5:
                r, kind = outer, "ramp"
            else:
                r, kind = None, None
            if r is None:
                cur = None; continue
            if cur is None or c - cur["c0"] > NOPLANT_PIECE_M + 1e-6:
                if cur is not None:                 # the next piece starts where this one ends: no gap between them
                    cur["c1"] = c
                cur = {"c0": c, "c1": c, "r": r, "kinds": collections.Counter()}; runs.append(cur)
            cur["c1"] = c; cur["r"] = max(cur["r"], r); cur["kinds"][kind] += 1
        for rn in runs:
            seg = substring(L, rn["c0"], rn["c1"]) if rn["c1"] - rn["c0"] > 0.05 else L.interpolate(rn["c0"])
            poly = seg.buffer(rn["r"], quad_segs=4)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda x: x.area)
            ring = Polygon(poly.exterior).simplify(0.3)
            if ring.is_empty or ring.geom_type != "Polygon" or ring.area < 1.0:
                continue
            out.append({"y": [int(v) for v in s["y"]], "p": U.flat(list(ring.exterior.coords)[:-1], 1)})
            for k, v in rn["kinds"].items():
                metres[k] += v * step
    npads = 0
    for pd in film.get("pads") or []:
        ring = Polygon([(pd["p"][k], pd["p"][k + 1]) for k in range(0, len(pd["p"]), 2)]).buffer(0)
        if ring.is_empty or ring.geom_type != "Polygon":
            continue
        ring = Polygon(ring.buffer(PAD_PAD_M, quad_segs=2, join_style="mitre").exterior).simplify(0.1)
        out.append({"y": [int(v) for v in pd.get("y") or [2025] * 4], "p": U.flat(list(ring.exterior.coords)[:-1], 1)}); npads += 1
    R.log(f"noplant: {len(out) - npads} road pieces of ≤ {NOPLANT_PIECE_M:.0f} m (decks {metres['deck']:.0f} m, embankments {metres['fill']:.0f} m, "
          f"ramps at grade or in cuts {metres['ramp']:.0f} m; edge + {NOPLANT_EDGE_M:.0f} m, slopes 1:{NOPLANT_SLOPE}) and {npads} turnaround pads (+ {PAD_PAD_M} m)")
    return out


# ================================================================== main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--districts", default="")
    ap.add_argument("--base", default=U.TWIN)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=U.OUT)
    ap.add_argument("--no-twin", action="store_true", help="skip the gen_twin re-run (debug only: the twin json files are not written)")
    ap.add_argument("--keep-solar", action="store_true", help="leave the solar panels in the buildings layer (the pure round trip)")
    a = ap.parse_args(argv)
    R = Run()
    dists = [d for d in a.districts.split(",") if d]
    run_dir = os.path.join(a.out, "_merged", a.run); assets = os.path.join(run_dir, "Assets")
    city = U.load_json(os.path.join(U.SPEC, "city.json")); norms = U.load_json(os.path.join(U.SPEC, "norms.json"))
    terrain = U.Terrain(a.base)
    Ds = [load_district(d, a.out, R) for d in dists]
    base_roads = U.load_json(os.path.join(a.base, U.F_ROADS)); base_film = U.load_json(os.path.join(a.base, U.F_FILM))
    sys.path.insert(0, U.TWIN_GEN)
    import twin_rerun as TR
    base_con = TR.load_base(a.base, "construction")
    version = base_roads["version"] + (f" · merge {a.run}" if Ds else "")
    # ---- roads, buildings, lrt, features
    roads, film, rinfo = merge_roads(base_roads, base_film, Ds, terrain, R, a.base)
    bres = merge_buildings(a.base, Ds, terrain, city, R)
    if not a.keep_solar:
        move_solar(bres, R)
    # drives name the buildings they serve: `sv` = their bids (the traffic model sends those buildings' trips along them)
    dinfo = rinfo.get("drives") or {}; bm = {(d, i): b for d, i, b in bres["bidmap"]}; nsv = 0
    for ei, did, ids in dinfo.pop("serves", []):
        sv = sorted(set(int(bm[(did, i)]) for i in ids if (did, i) in bm))
        if sv:
            roads["edges"][ei]["sv"] = sv; nsv += 1
    if dinfo.get("edges"):
        R.log(f"drives: {nsv} of {dinfo['edges']} drive edges name the bids they serve (sv)")
    routes, lrt_block = merge_lrt(U.load_json(os.path.join(a.base, U.F_LRT)), base_con["lrt"], Ds, R, norms)
    noplant, parking, dist_json, solar, norms_social = features(Ds, city, norms, bres["solar"])
    rail_json, rail_np = merge_rail(Ds, terrain, R)
    if bres.get("yards"):
        film["yards"] = bres["yards"]
    if Ds:
        nf = len(noplant["polys"]); noplant["polys"] += road_noplant(film, terrain, R, int(dinfo.get("strokes") or 0))
        ny = len(bres.get("yards") or []); noplant["polys"] += [{"y": list(yd["y"]), "p": yd["p"]} for yd in bres.get("yards") or []]
        noplant["polys"] += rail_np
        R.log(f"noplant.json: {nf} polygons of the districts' features + {len(noplant['polys']) - nf - ny - len(rail_np)} of the roads + {ny} truck yards"
              f" + {len(rail_np)} of the railway (corridors, platforms)")
    written = {}

    def put(rel, data, what):
        if len(data) > U.PART_LIMIT:
            raise SystemExit(f"merge_districts: REFUSED to write {rel}: {len(data) / 1e6:.2f} MB is over the {U.PART_LIMIT / 1e6:.0f} MB limit "
                             f"(the laptop file channel refuses files over 25 MB). The run {a.run} is incomplete and has no manifest.")
        size = U.write_bytes(os.path.join(assets, rel), data); written[rel] = what
        R.log(f"  wrote {rel}: {size / 1e6:.2f} MB")
    put(U.F_CSV, U.csv_bytes(bres["rows"], bres["cols"]), "buildings: rows of removed buildings become placeholders (kind removed), new rows")
    parts = U.split_aql(bres["aql"])
    for k, part in enumerate(parts):
        put(U.part_path(U.F_AQL, k), U.aql_bytes(part), f"part {k + 1} of {len(parts)} of the buildings layer (AQL1; the Unity builder reads "
            "layer_buildings.bytes, _1, _2 … in order): meshes of removed buildings dropped, new buildings extruded (flat roofs)"
            + ("" if a.keep_solar else ", solar panels moved to solar.json"))
    stem = os.path.splitext(os.path.join(assets, U.F_AQL))[0]
    for f in sorted(glob.glob(stem + "_*.bytes")):                        # parts an earlier run into this directory left behind
        k = f[len(stem) + 1:-len(".bytes")]
        if k.isdigit() and int(k) >= len(parts):
            os.remove(f); R.log(f"  removed {os.path.relpath(f, assets)} (left by an earlier run of {a.run})")
    put(U.F_BOUNDS, U.bounds_bytes(bres["bounds"]), "footprint boxes of new bids; removed bids get an empty box")
    put(U.F_HIDE, U.hide_bytes(bres["hide"]), "entries inside merged areas and of reassigned bids dropped")
    put(U.F_ORDER, U.dumps(bres["order"]).encode("utf-8"), "entries inside merged areas and of reassigned bids dropped")
    put(U.F_LRT, U.dumps(routes).encode("utf-8"), "routes clipped by the areas; district lines with sec/h/ends")
    put(U.F_NOPLANT, U.dumps(noplant).encode("utf-8"), "features.noplant of the districts; decks, ramps, embankments and turnaround pads of the new roads")
    put(U.F_PARKING, U.dumps(parking).encode("utf-8"), "features.parking of the districts")
    put(U.F_DISTRICTS, U.dumps(dist_json).encode("utf-8"), "district outlines from city.json")
    put(U.F_SOLAR, U.dumps(solar).encode("utf-8"), "solar fields: the city's panels moved out of the buildings layer, and the merged districts' own"
        if not a.keep_solar else "solar fields of the merged districts")
    put(U.F_NORMS, U.dumps(norms_social).encode("utf-8"), "social norms from spec/norms.json")
    put(U.F_RAIL, U.dumps(rail_json).encode("utf-8"), "railway lines and platforms of the districts' spec `rail` (RailLayer draws them)")
    put(U.F_FILM, U.dumps(film).encode("utf-8"), "base strokes clipped by the areas; one stroke per new roads edge (e, t, h, st, p, ic)")
    # ---- twin re-run (needs the merged csv on disk); then roads.json with `external` from the traffic model
    if not a.no_twin:
        csv_path = os.path.join(assets, U.F_CSV)
        infra = U.read_aql(os.path.join(a.base, "CityData/layer_infrastructure.bytes"))
        ground = {int(r["bid"]): float(r["ground_m"] or 0) for r in bres["rows"]}
        # a landmark lot's own capacity rows start and end their trips on the streets of the lot (a whole quarter: Iconic)
        lot_poly = {(D["id"], L["id"]): Polygon(L["polygon"], L.get("holes") or []).buffer(0) for D in Ds for L in ((D.get("lots") or {}).get("lots") or [])}
        fronts = {bid: lot_poly[(did, bres["rows"][bid]["parcel"])] for did, _, bid in bres["bidmap"]
                  if bres["rows"][bid].get("kind") == LOT_KIND and (did, bres["rows"][bid].get("parcel")) in lot_poly}
        twin, ext, _ = TR.rerun(roads, csv_path, a.base, infra, ground, version, lrt_block, norms, R.log,
                                place=facility_sites(Ds, roads, film, bres["bounds"], R), fronts=fronts)
        # flood depths: the base value for every unchanged building (gen_risk ran on the real river layer), the port for the others
        base_risk = TR.load_base(a.base, "risk"); nkeep = 0
        for k, sc in twin["risk"]["scenarios"].items():
            bd = base_risk["scenarios"][k]["depth_cm"]; d = sc["depth_cm"]
            for bid in range(min(len(bd), len(d))):
                if bid not in bres["changed"]:
                    d[bid] = bd[bid]; nkeep += 1
        R.log(f"risk: base depths kept for {nkeep // 2} unchanged bids, model depths for the other {len(twin['risk']['scenarios']['flood_1pct']['depth_cm']) - nkeep // 2}")
        if Ds:
            roads["external"] = ext
        elif ext != base_roads.get("external"):
            R.log(f"round trip: traffic model puts the external nodes at {ext}, roads.json has {base_roads.get('external')} (kept)")
        if Ds:
            roads["version"] = version
        for k in U.TWIN_JSON:
            put(f"StreamingAssets/twin/{k}.json", U.dumps(twin[k]).encode("utf-8"), "recomputed by twin_rerun.py (gen_twin logic) on the merged data")
    put(U.F_ROADS, U.dumps(roads).encode("utf-8"), "edges inside the areas replaced by the district networks (new fields t, k, h, st, p, ic)" if Ds else "re-encoded")
    # ---- manifest
    man = {"run": a.run, "base": a.base, "districts": dists, "version": version, "files": {}, "bids": bres["bidmap"],
           "layer_parts": [U.part_path(U.F_AQL, k) for k in range(len(parts))], "solar_moved": bres.get("solar_moved"), "drives": dinfo or None,
           "keep_edges": rinfo.get("keep_edges") or [],
           "removed_bids": sorted(int(v) for v in bres["removed"]), "bid_numbering": bres.get("numbering"), "log": R.lines}
    for rel in sorted(written):
        p = os.path.join(assets, rel); bp = os.path.join(a.base, rel)
        same = os.path.exists(bp) and os.path.getsize(bp) == os.path.getsize(p) and U.md5(bp) == U.md5(p)
        man["files"][rel] = {"md5": U.md5(p), "size": os.path.getsize(p), "same_as_base": same,
                             "what": "unchanged (byte-equal to the base)" if same else written[rel]}
    U.write_json(os.path.join(run_dir, "manifest.json"), man)
    big = [rel for rel, f in man["files"].items() if f["size"] > 25e6]
    R.log(f"done: {len(written)} files in {run_dir}" + (f"; OVER 25 MB: {big}" if big else ""))
    return man


if __name__ == "__main__":
    main()
