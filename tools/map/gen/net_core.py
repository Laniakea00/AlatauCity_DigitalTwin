"""Core of gen_network (w43): ways → planar graph per level → heights → structures → network.json (CONTRACT §4).

A Way is a polyline with a road class and attributes. Divided roads are two oneway Ways (one per carriageway, drawn in
the direction of travel). Interchange templates add ramp Ways whose ends lie exactly on other Ways (diverge / merge /
terminal); `Network.planarize` turns every shared point and every at-grade crossing into a node, keeps crossings that
are separated in height without a node, and splits the ways into segments. Heights: the ground under each road smoothed
to the slope norm of its class, pinned at nodes, raised by tents where a road passes over another one (clearance +
deck depth), over a railway track it crosses as a deck (rail clearance + deck depth) and over the water under a spec
bridge (water clearance + deck depth), ramps interpolated between their end nodes. Structures (ground / embankment /
cut / overpass / bridge / tunnel) come from those heights and from the spec's bridge / overpass spans.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import geom as G  # noqa: E402
from lib import model, terrain  # noqa: E402
from lib import years as Y  # noqa: E402

STRUCT_CODE = {"ground": 0, "embankment": 1, "cut": 2, "bridge": 3, "overpass": 4, "tunnel": 5}


class Way:
    _n = 0

    def __init__(self, cls, pts, *, oneway=False, prof=None, pid=None, years=None, name_ru="", street=None, ic=None,
                 source="new", role="primary", id=None, grade=None, parent=None):
        Way._n += 1
        self.id = id or f"w{Way._n}"
        self.cls = cls
        self.P = G.dedup(pts)
        self.oneway = oneway
        self.prof = prof                  # profile dict (norms.profile + carriageway form)
        self.pid = pid
        self.years = list(years) if years else list(Y.EXISTING)
        self.name_ru = name_ru or ""
        self.street = street
        self.ic = ic
        self.source = source
        self.role = role                  # primary | ramp
        self.grade = grade                # max grade (fraction) for tents on this way (None → class norm)
        self.parent = parent              # the Way a ramp's speed-change lane runs along (for crossings near nodes)
        self.lifts = []                   # [(s0, s1, why)]: here the way passes OVER whatever it crosses
        self.unders = []                  # [(s0, s1, why)]: here the way passes UNDER whatever it crosses
        self.osm_struct = []              # [(s0, s1, kind)] from Overture flags (bridge / tunnel)
        self.osm_conn = []                # [(s, connector index)]
        self.osm_level = []               # [(s0, s1, level)]
        self.end_kind = [None, None]      # hints for the two ends: joint / end / edge
        self.end_ref = [None, None]
        self.node_hint = {}               # chainage → node kind for nodes the template defines on this way
        self.keep_exact = False
        self.pieces = None                # [(P, street, name_ru, source)]: the OSM pieces net_osm._chain joined into this way
        self.S = G.chainage(self.P)
        self.y = None

    @property
    def L(self):
        return float(self.S[-1])

    def bbox(self):
        """(xmin, zmin, xmax, zmax) of P, kept until P is replaced."""
        if getattr(self, "_bb_of", None) is not self.P:
            self._bb_of = self.P
            lo, hi = self.P.min(axis=0), self.P.max(axis=0)
            self._bb = (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))
        return self._bb

    def at(self, s):
        return G.point_at(self.P, s, self.S)

    def piece_at(self, p):
        """(P, street, name_ru, source) of the chained OSM piece nearest to point p; None for a way of one piece."""
        if not self.pieces or len(self.pieces) < 2:
            return None
        return min(self.pieces, key=lambda q: G.project(q[0], p)[1])

    def streets_near(self, p, tol=0.5):
        """The spec streets of this way at point p: every chained OSM piece passing within tol m (two where pieces
        meet), the way's own street for a way of one piece."""
        if not self.pieces or len(self.pieces) < 2:
            return {self.street}
        near = {q[1] for q in self.pieces if G.project(q[0], p)[1] <= tol}
        return near or {self.piece_at(p)[1]}

    def streets(self):
        """Every spec street this way carries (one per chained OSM piece)."""
        return {self.street} | {q[1] for q in self.pieces or []}

    def tan(self, s):
        return G.tangent_at(self.P, s, self.S)

    def refresh(self):
        self.P = G.dedup(self.P)
        self.S = G.chainage(self.P)

    def lifted_at(self, s):
        return any(a - 1e-6 <= s <= b + 1e-6 for a, b, _ in self.lifts)

    def under_at(self, s):
        return any(a - 1e-6 <= s <= b + 1e-6 for a, b, _ in self.unders)

    def osm_kind_at(self, s):
        for a, b, k in self.osm_struct:
            if a - 1e-6 <= s <= b + 1e-6:
                return k
        return None

    def osm_level_at(self, s):
        for a, b, lv in self.osm_level:
            if a - 1e-6 <= s <= b + 1e-6:
                return lv
        return 0

    def __repr__(self):
        return f"Way({self.id} {self.cls} L={self.L:.0f} {self.source})"


class Node:
    def __init__(self, id, p):
        self.id = id
        self.p = np.asarray(p, float)
        self.kind = None
        self.ic = None
        self.r = None
        self.y = None
        self.ref = None          # joint id, spec node id…
        self.lrt = None          # the LRT line of a level crossing at this node (planarize 3b)
        self.uses = []           # [(way, s)]
        self.why = None

    def __repr__(self):
        return f"Node({self.id} {self.kind} {self.p.round(1)})"


class Network:
    def __init__(self, norms, district, area=None, log=None):
        self.N = norms
        self.d = district
        self.area = area
        self.ways = []
        self.nodes = []
        self.ics = []                    # interchange records (dicts) — templates fill them
        self.log = log if log is not None else []
        self.separated = []              # [(upper way, s_u, lower way, s_l, point, angle)]
        self.node_types_spec = {}        # (x, z) of spec nodes → (type, id)
        self.water = None                # shapely geometry of water (bridges)
        self.rail = []                   # railway tracks (lib.rail.tracks): a deck over one takes the rail clearance
        self.rail_at_grade = []          # [(way, s, point, track id)]: crossings of a track in one level (for the log)
        self.joints = []                 # [{id, node}]
        self.ground = None               # ground(x_array, z_array) → heights; default: the twin's terrain

    def add(self, w):
        self.ways.append(w)
        return w

    def carve(self, w, s0, s1):
        """Remove the part (s0, s1) of way w (before planarize): w keeps the first piece, a clone the second one.
        Returns the pieces left (w removed from the network when nothing is left)."""
        import copy
        L = w.L
        s0, s1 = max(0.0, s0), min(L, s1)
        P = w.P.copy()
        orig = {k: list(getattr(w, k)) for k in ("lifts", "unders", "osm_struct", "osm_level", "osm_conn")}
        ends = list(w.end_kind)
        spans = []
        if s0 > 0.5:
            spans.append((0.0, s0))
        if s1 < L - 0.5:
            spans.append((s1, L))
        pieces = []
        for k, (a, b) in enumerate(spans):
            nw = w if k == 0 else copy.copy(w)
            if k:
                nw.id = f"{w.id}b"
                self.ways.append(nw)
            nw.P = G.cut(P, a, b)
            for key in ("lifts", "unders", "osm_struct", "osm_level"):
                setattr(nw, key, [(max(x0, a) - a, min(x1, b) - a, z) for x0, x1, z in orig[key] if x1 > a and x0 < b])
            nw.osm_conn = [(c - a, i) for c, i in orig["osm_conn"] if a - 0.01 <= c <= b + 0.01]
            nw.end_kind = [ends[0] if a == 0.0 else None, ends[1] if b == L else None]
            nw.node_hint = {}
            nw.refresh()
            pieces.append(nw)
        if not pieces and w in self.ways:
            self.ways.remove(w)
        return pieces

    def L(self, what, ids=None, **kw):
        e = {"what": what, "ids": list(ids or [])}
        e.update(kw)
        self.log.append(e)

    # ------------------------------------------------------------------ planarisation
    def planarize(self, snap_tol=0.3, end_tol=1.5):
        """Nodes at every shared point and at every crossing in one level; ways split into segments later."""
        from scipy.spatial import cKDTree
        for w in self.ways:
            w.refresh()
            w.cuts = []                  # [(s, node)]
        self.nodes = []
        nid = [0]

        def new_node(p):
            nid[0] += 1
            n = Node(f"n{nid[0]}", p)
            self.nodes.append(n)
            return n

        # 1. way ends: merge ends closer than end_tol, then ends lying on another way (T, diverge, merge)
        ends = []
        for w in self.ways:
            ends.append((w, 0))
            ends.append((w, 1))
        E = np.array([w.P[0] if k == 0 else w.P[-1] for w, k in ends])
        tree = cKDTree(E)
        groups = {}
        parent = list(range(len(ends)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i, j in tree.query_pairs(end_tol):
            wi, wj = ends[i][0], ends[j][0]
            # ends of generated ways are exact: only merge them when really coincident
            tol = end_tol if (wi.source.startswith(("osm", "keep")) or wj.source.startswith(("osm", "keep"))) else snap_tol
            if np.hypot(*(E[i] - E[j])) <= tol:
                parent[find(i)] = find(j)
        for i in range(len(ends)):
            groups.setdefault(find(i), []).append(i)
        end_node = {}
        for g, idx in groups.items():
            p = E[idx].mean(axis=0)
            # an exact (template) end wins the position
            for i in idx:
                if ends[i][0].keep_exact:
                    p = E[i]
                    break
            n = new_node(p)
            for i in idx:
                w, k = ends[i]
                end_node[(id(w), k)] = n
                s = 0.0 if k == 0 else w.L
                w.cuts.append((s, n))
        # end on the interior of another way
        import shapely
        lines = [shapely.LineString(w.P) for w in self.ways]
        st = shapely.STRtree(lines)
        way_of = {id(x): x for x in self.ways}
        for (wid, k), n in list(end_node.items()):
            w = way_of[wid]
            p = w.P[0] if k == 0 else w.P[-1]
            for j in st.query(shapely.Point(p).buffer(end_tol)):
                o = self.ways[j]
                if o is w:
                    continue
                s, dist, foot = G.project(o.P, p)
                tol = end_tol if (w.source.startswith(("osm", "keep")) and o.source.startswith(("osm", "keep"))) else snap_tol
                if dist > tol or s < 0.05 or s > o.L - 0.05:
                    continue
                if any(abs(s - cs) < 0.05 for cs, _ in o.cuts):
                    # already a node there: reuse it
                    for cs, cn in o.cuts:
                        if abs(s - cs) < 0.05 and cn is not n:
                            self._merge_nodes(cn, n)
                    continue
                o.cuts.append((s, n))
        # 2. OSM connectors shared by two OSM ways: nodes (Overture topology)
        conn_at = {}
        for w in self.ways:
            for s, c in w.osm_conn:
                conn_at.setdefault(c, []).append((w, s))
        for c, uses in conn_at.items():
            if len(uses) < 2:
                continue
            pts = [w.at(s) for w, s in uses]
            # an end node may already be there
            n = None
            for w, s in uses:
                for cs, cn in w.cuts:
                    if abs(cs - s) < 0.5:
                        n = cn
            if n is None:
                n = new_node(np.mean(pts, axis=0))
            for w, s in uses:
                if not any(abs(cs - s) < 0.5 for cs, _ in w.cuts):
                    w.cuts.append((s, n))
                else:
                    for cs, cn in w.cuts:
                        if abs(cs - s) < 0.5 and cn is not n:
                            self._merge_nodes(cn, n)
        # 2b. a chained way whose OSM pieces carry different spec streets: a node where one piece meets the next, so
        # every segment lies on one piece and carries its street (net_osm._chain)
        for w in self.ways:
            for q0, q1 in zip(w.pieces or [], (w.pieces or [])[1:]):
                if q0[1] == q1[1]:
                    continue
                p = min(((a, b) for a in (q0[0][0], q0[0][-1]) for b in (q1[0][0], q1[0][-1])),
                        key=lambda ab: float(np.hypot(*(ab[0] - ab[1]))))[0]
                s, dist, _ = G.project(w.P, p)
                if dist > 0.5 or s < 0.05 or s > w.L - 0.05 or any(abs(cs - s) < 0.5 for cs, _ in w.cuts):
                    continue
                w.cuts.append((s, new_node(w.at(s))))
        # 3. crossings
        pairs = st.query(lines, predicate="intersects")
        seen = set()
        for i, j in zip(*pairs):
            if i >= j:
                continue
            a, b = self.ways[i], self.ways[j]
            key = (i, j)
            if key in seen:
                continue
            seen.add(key)
            for sa, sb, pt, ang in G.crossings(a.P, b.P):
                self._crossing(a, sa, b, sb, pt, ang, new_node)
        # 3b. the ground LRT crossing a road in one level: a level-crossing node on the road (lrt.at_grade_crossing)
        lrt_x = self._lrt_cuts(lines, st, new_node)
        # node uses
        for n in self.nodes:
            n.uses = []
        for w in self.ways:
            w.cuts = self._dedup_cuts(w)
            for s, n in w.cuts:
                n.uses.append((w, s))
        self.nodes = [n for n in self.nodes if n.uses]
        for w, s, line in lrt_x:
            n = min(w.cuts, key=lambda c: abs(c[0] - s))[1]
            n.lrt = line
        return self

    def _lrt_cuts(self, lines, st, new_node):
        """Cuts where a ground run of the LRT (self.lrt_ground [(line id, Nx2)]) crosses a way in one level (not where
        the way passes over or under: spec lifts / unders, OSM bridge / tunnel / level). On a road the LRT may cross at
        grade (norms.lrt_crossing_allowed) the crossing is a node: the way's own node within lrt_crossing_join_m (its
        junction with the street the LRT runs in, or its end there) or a new one. On another (a ramp, an expressway, a continuous arterial)
        it is listed in self.lrt_forbidden for the log and rule 6. Returns [(way, s, line id)] for the node marks."""
        out = []
        self.lrt_forbidden = []
        runs = getattr(self, "lrt_ground", None) or []
        if not runs:
            return out
        import shapely
        join = model("lrt_crossing_join_m")
        for line, R in runs:
            for j in st.query(shapely.LineString(R)):
                w = self.ways[int(j)]
                for _, s, pt, ang in G.crossings(R, w.P):
                    s = float(s)
                    if w.lifted_at(s) or w.under_at(s) or w.osm_kind_at(s) in ("bridge", "tunnel") or w.osm_level_at(s) != 0:
                        continue
                    if not self.N.lrt_crossing_allowed(w.cls):
                        self.lrt_forbidden.append((w, s, np.asarray(pt, float), line))
                        continue
                    near = [(abs(cs - s), cs) for cs, _ in w.cuts if abs(cs - s) <= join]
                    if near:
                        out.append((w, min(near)[1], line))
                        continue
                    w.cuts.append((s, new_node(w.at(s))))
                    out.append((w, s, line))
        return out

    def _merge_nodes(self, keep, gone):
        if keep is gone:
            return
        for w in self.ways:
            w.cuts = [(s, keep if n is gone else n) for s, n in getattr(w, "cuts", [])]
        if gone in self.nodes:
            self.nodes.remove(gone)

    def _dedup_cuts(self, w):
        cuts = sorted(w.cuts, key=lambda c: c[0])
        out = []
        for s, n in cuts:
            if out and abs(s - out[-1][0]) < 0.05:
                if out[-1][1] is not n:
                    self._merge_nodes(out[-1][1], n)
                continue
            if out and out[-1][1] is n and abs(s - out[-1][0]) < 1.5:
                # one node twice on a way (a crossing merged with the way's end): keep the end
                if s > w.L - 0.05:
                    out[-1] = (s, n)
                continue
            out.append((s, n))
        return out

    def _near_cut(self, w, s, tol):
        for cs, cn in w.cuts:
            if abs(cs - s) < tol:
                return cn
        return None

    def _crossing(self, a, sa, b, sb, pt, ang, new_node):
        # already a node at that place on both ways?
        na, nb = self._near_cut(a, sa, 1.0), self._near_cut(b, sb, 1.0)
        if na is not None and na is nb:
            return
        # crossings of a ramp with the way its speed-change lane runs along (numerical touches near the node)
        if (a.parent is b or b.parent is a) and (na is not None or nb is not None or ang < 6):
            return
        if (a.parent is b or b.parent is a):
            shared = [n for _, n in a.cuts if any(n is m for _, m in b.cuts)]
            if any(np.hypot(*(n.p - pt)) < 40 for n in shared):
                return
        up = self._who_is_over(a, sa, b, sb, pt)
        if up is not None:
            u, su, l, sl = (a, sa, b, sb) if up == "a" else (b, sb, a, sa)
            self.separated.append((u, su, l, sl, pt, ang))
            return
        # at grade: one node (reuse a node within 1 m)
        n = na or nb or new_node(pt)
        if na is None:
            a.cuts.append((sa, n))
        elif na is not n:
            self._merge_nodes(n, na)
        if nb is None:
            b.cuts.append((sb, n))
        elif nb is not n:
            self._merge_nodes(n, nb)

    def mid_block_crossings(self, classes, smax, pad=20.0):
        """After planarize: a pedestrian crossing node (2-arm `crossing`) in every at-grade run of a new road of
        `classes` longer than smax between its nodes, evenly spaced so no run is longer than smax. Spans over or under
        other roads (lifts, tunnels, OSM bridges, separated crossings ± pad) are not at grade and get none."""
        added = []
        sep_up, sep_low = {}, {}            # separated crossings by their upper / lower way, in their order
        for e in self.separated:
            sep_up.setdefault(id(e[0]), []).append(e)
            sep_low.setdefault(id(e[2]), []).append(e)
        for w in self.ways:
            if w.cls not in classes or w.role != "primary" or w.source != "new":
                continue
            up, low = sep_up.get(id(w), []), sep_low.get(id(w), [])
            blocked = [(a, b) for a, b, _ in w.lifts + w.unders + w.osm_struct]
            blocked += [(su - pad, su + pad) for u, su, l, sl, pt, ang in up]
            # a street with sidewalks passing over this road is a crossing (grade-separated) for pedestrians
            over = [(G.project(w.P, pt)[0], None) for u, su, l, sl, pt, ang in low
                    if u.cls not in ("expressway", "ramp", "arterial_continuous")]
            blocked += [(sl_ - pad, sl_ + pad) for u, su, l, sl_, pt, ang in low
                        if u.cls in ("expressway", "ramp", "arterial_continuous")]
            cuts = sorted(w.cuts + over, key=lambda c: c[0])
            for (s0, _), (s1, _) in zip(cuts[:-1], cuts[1:]):
                # at-grade runs inside [s0, s1]
                runs, cur = [], s0
                for a, b in sorted(blocked):
                    if b <= cur or a >= s1:
                        continue
                    if a > cur:
                        runs.append((cur, a))
                    cur = max(cur, b)
                if cur < s1:
                    runs.append((cur, s1))
                for a, b in runs:
                    L = b - a
                    if L <= smax:
                        continue
                    k = int(math.ceil(L / smax))
                    for i in range(1, k):
                        s = a + L * i / k
                        n = Node(f"nx{len(added) + 1}", w.at(s))
                        n.kind = "crossing"
                        n.why = "mid_block"
                        n.uses.append((w, s))
                        w.cuts.append((s, n))
                        self.nodes.append(n)
                        added.append(n)
        if added:
            self.L(f"пешеходные переходы между перекрёстками: {len(added)} узлов (шаг ≤ {smax:.0f} м)",
                   [n.id for n in added], norm="crossings.at_grade_spacing_regulated_m")
        return added

    def _who_is_over(self, a, sa, b, sb, pt):
        """'a' or 'b' when the crossing is separated in height (that way is the upper one), None when at grade."""
        if id(b) in getattr(a, "over_ways", ()):
            return "a"
        if id(a) in getattr(b, "over_ways", ()):
            return "b"
        la, lb = a.lifted_at(sa), b.lifted_at(sb)
        if la and not lb:
            return "a"
        if lb and not la:
            return "b"
        if la and lb:
            # both lifted (a ramp over a lifted road…): the one whose lift is about this crossing — the ramp
            return "a" if a.role == "ramp" and b.role != "ramp" else "b"
        if a.under_at(sa):
            return "b"
        if b.under_at(sb):
            return "a"
        osm_a, osm_b = a.source.startswith("osm"), b.source.startswith("osm")
        ka, kb = a.osm_kind_at(sa), b.osm_kind_at(sb)
        lva, lvb = a.osm_level_at(sa), b.osm_level_at(sb)
        if osm_a and osm_b:
            # Overture: ways crossing without a shared connector are on different levels
            if lva != lvb:
                return "a" if lva > lvb else "b"
            if ka in ("bridge", "overpass") and kb not in ("bridge", "overpass"):
                return "a"
            if kb in ("bridge", "overpass") and ka not in ("bridge", "overpass"):
                return "b"
            if ka == "tunnel":
                return "b"
            if kb == "tunnel":
                return "a"
            self.L("существующие дороги OSM пересекаются без общего узла и без отметки уровня: принято, что выше дорога высшего класса",
                   [a.id, b.id], x=round(float(pt[0]), 1), z=round(float(pt[1]), 1))
            return "a" if self.N.class_rank(a.cls) <= self.N.class_rank(b.cls) else "b"
        if ka in ("bridge", "overpass") or lva > 0:
            return "a"
        if kb in ("bridge", "overpass") or lvb > 0:
            return "b"
        if ka == "tunnel" or lva < 0:
            return "b"
        if kb == "tunnel" or lvb < 0:
            return "a"
        return None

    # ------------------------------------------------------------------ heights
    def heights(self, iters=3):
        """y per vertex of every way (after planarize). Returns the list of checks failed (for the log)."""
        step = model("profile_step_m")
        clear = self.N.norm("bridges.road_clearance_m") + model("clearance_margin_m")
        depth = model("deck_depth_m")
        rail_x = self._rail_crossings()
        self.rail_at_grade = []
        for w in self.ways:
            # densify so the profile has vertices (keep cut chainages: they are on the polyline)
            P = G.densify(w.P, step)
            # vertices at the ends of a spec bridge (and 0.2 m outside them): the bridge run starts and ends there
            P = _with_vertices_at(P, [x for a, b, why in w.lifts if why == "spec:bridge" for x in (a - 0.2, a, b, b + 0.2)])
            # vertices at a railway track crossed and at the edges of its gauge: the deck is level over the track
            P = _with_vertices_at(P, [x for o in rail_x.get(id(w), ()) for x in (o["s"] - o["half"], o["s"], o["s"] + o["half"])])
            w.P = P
            w.S = G.chainage(P)
            w.g = np.asarray(self._ground(P[:, 0], P[:, 1]), float)
            w.spans = self._water_spans(w, depth)
            w.rails = self._rail_spans(w, rail_x.get(id(w), ()), depth)
            w.gmax = w.grade if w.grade else self.N.slope_max(w.cls)
            w.gs = _grade_limit(_smooth(w.S, w.g, 60.0), w.S, w.gmax * 0.9) if w.role == "primary" else None
            w.y = w.gs.copy() if w.gs is not None else None
            # the cut chainages move a hair when densified: re-project, each near where it was (on a closed way the
            # node at s = L is also at s = 0: projecting it on the whole line would drop the closing piece)
            w.cuts = [(_reproject(w.P, s, n.p), n) for s, n in w.cuts]
        # separated crossings by upper way
        for w in self.ways:
            w.over = []
        for u, su, l, sl, pt, ang in self.separated:
            su = G.project(u.P, pt)[0]
            sl = G.project(l.P, pt)[0]
            half = self._footprint_half(l, ang)
            # the upper deck's own half width at the skew: the span reaches past the lower road's edge by it, so the
            # abutments and walls stand off the lower lanes (≤ 30 m)
            pu = u.prof or self.N.profile(u.cls)
            wu = (pu["cw_w"] + sum(pu["shoulder_w"])) if u.oneway else self.N.cross_width(pu)
            skew = min(30.0, wu / 2.0 / max(math.tan(math.radians(max(ang, 20.0))), 1e-3))
            u.over.append({"s": su, "lower": l, "sl": sl, "half": half, "pt": pt, "ang": ang, "skew": skew})
        for w in self.ways:
            if w.y is None:
                w.y = np.interp(w.S, [0, w.L], [w.g[0], w.g[-1]])
        for it in range(iters):
            # 1. free profiles of the primary roads: smoothed ground raised by tents over the roads they pass over
            for w in self.ways:
                if w.role == "primary":
                    w.free = self._tents(w, w.gs, clear, depth)
            # 2. node heights from the free profiles (a lifted road wins, else the road of the highest class)
            for n in self.nodes:
                n.y = self._node_y(n)
            self._ramp_only_nodes(clear, depth)
            # 3. profiles pinned at the nodes; ramps between their nodes (following their carriageway alongside it)
            for w in self.ways:
                if w.role == "primary":
                    w.y = self._pin(w, w.free)
                else:
                    w.y = self._tents(w, self._ramp_base(w), clear, depth)
        self._clearance_fix(clear, depth)

    def _water_spans(self, w, depth):
        """[(s0, s1, y)] spec bridges of a way: the deck is at least y over [s0, s1] — the water under the bridge
        (the lowest ground along the span, sampled every metre: a stream or canal drawn as a line is a dip in the
        terrain) + the clearance of a span over water + the deck depth."""
        out = []
        for a, b, why in w.lifts:
            if why != "spec:bridge":
                continue
            lo, hi = max(0.0, float(a)), min(w.L, float(b))
            if hi - lo < 0.5:
                continue
            ss = np.linspace(lo, hi, max(2, int(math.ceil(hi - lo)) + 1))
            g = np.asarray(self._ground(np.interp(ss, w.S, w.P[:, 0]), np.interp(ss, w.S, w.P[:, 1])), float)
            out.append((lo, hi, float(np.min(g)) + self._water_clear() + depth))
        return out

    def _rail_crossings(self):
        """{id(way): [{s, half, pt, track}]}: crossings of the ways with the railway tracks that run on the ground (a
        track on a bridge passes over the road). `half`: the track's structure gauge each side of its axis along the
        way (/ sin of the crossing angle) + the same 2 m pad as over a road."""
        out = {}
        if not self.rail:
            return out
        import shapely
        tr = [t for t in self.rail if not t["up"]]
        if not tr:
            return out
        tree = shapely.STRtree([shapely.LineString(t["P"]) for t in tr])
        gh = model("rail_track_half_m")
        for w in self.ways:
            for j in tree.query(shapely.LineString(w.P)):
                t = tr[int(j)]
                for s, _, pt, ang in G.crossings(w.P, t["P"]):
                    half = gh / math.sin(math.radians(max(ang, 20.0))) + 2.0
                    out.setdefault(id(w), []).append({"s": float(s), "half": half, "pt": np.asarray(pt, float), "track": t["id"]})
        return out

    def _rail_spans(self, w, xs, depth):
        """[{s, half, need, track}] of the tracks a way crosses as a deck (a lift: spec bridge / overpass or a separated
        crossing; an OSM bridge or level ≥ 1): the deck is at least need = rail head (the ground at the crossing) + rail
        clearance + deck depth over s ± half. A crossing in one level (no deck, no tunnel) goes to rail_at_grade."""
        out = []
        clear = None
        for o in xs:
            s, _, _ = G.project(w.P, o["pt"])
            deck = w.lifted_at(s) or w.osm_kind_at(s) == "bridge" or w.osm_level_at(s) > 0
            if not deck:
                if not (w.under_at(s) or w.osm_kind_at(s) == "tunnel" or w.osm_level_at(s) < 0):
                    self.rail_at_grade.append((w, s, o["pt"], o["track"]))
                continue
            if clear is None:
                clear = float(self.N.norm("bridges.rail_clearance_m")) + model("clearance_margin_m")
            g = float(self._ground(*o["pt"]))
            out.append({"s": float(s), "half": o["half"], "need": g + clear + depth, "track": o["track"], "pt": o["pt"]})
        return out

    def _water_clear(self):
        # a small non-navigable stream or canal (no backwater over 1 m): the least clearance of the norm's table
        return float(self.N.norm("bridges.river_clearance_m", "backwater_up_to_1m")) + model("clearance_margin_m")

    def _ground(self, x, z):
        if self.ground is not None:
            return self.ground(np.asarray(x, float), np.asarray(z, float))
        return terrain.h(x, z)

    def _footprint_half(self, l, ang):
        p = l.prof or self.N.profile(l.cls)
        width = self.N.cross_width(p) if not (l.oneway and l.role == "ramp") else p["cw_w"] + sum(p["shoulder_w"])
        if l.oneway and l.role != "ramp" and p.get("carriageways") == 2:
            width = p["cw_w"] + sum(p["shoulder_w"]) / 1.0
        s = math.sin(math.radians(max(ang, 20.0)))
        return width / 2.0 / s + 2.0

    def _node_y(self, n):
        vals = []
        lifted = []
        for w, s in n.uses:
            if w.role != "primary":
                continue
            prof = w.free if getattr(w, "free", None) is not None else w.y
            v = float(np.interp(s, w.S, prof))
            vals.append((self.N.class_rank(w.cls), v, w))
            if w.gs is not None and v > float(np.interp(s, w.S, w.gs)) + 0.1:
                lifted.append(v)
        if lifted:
            return max(lifted)
        if vals:
            vals.sort(key=lambda t: t[0])
            return vals[0][1]
        return None

    def _ramp_only_nodes(self, clear=None, depth=None):
        """Nodes touched only by ramps: harmonic interpolation along the ramp graph between the known nodes, then
        raised where a ramp through the node is on its tent (a ramp node on a bridge approach)."""
        unknown = [n for n in self.nodes if n.y is None]
        if not unknown:
            return
        self._harmonic(unknown)
        if clear is None:
            return
        for n in unknown:
            for w, s in n.uses:
                t = self._tent_at(w, s, clear, depth)
                if t is not None and t > n.y:
                    n.y = t

    def _tent_at(self, w, s, clear, depth):
        best = None
        for o in getattr(w, "over", []):
            l = o["lower"]
            if l.y is None:
                continue
            yl = float(np.interp(o["sl"], l.S, l.y))
            t = yl + clear + depth - w.gmax * max(0.0, abs(s - o["s"]) - o["half"])
            best = t if best is None else max(best, t)
        for a, b, need in getattr(w, "spans", ()):
            t = need - w.gmax * max(0.0, a - s, s - b)
            best = t if best is None else max(best, t)
        for o in getattr(w, "rails", ()):
            t = o["need"] - w.gmax * max(0.0, abs(s - o["s"]) - o["half"])
            best = t if best is None else max(best, t)
        return best

    def _harmonic(self, unknown):
        idx = {id(n): i for i, n in enumerate(unknown)}
        m = len(unknown)
        Amat = np.zeros((m, m))
        b = np.zeros(m)
        for w in self.ways:
            cuts = sorted(w.cuts, key=lambda c: c[0])
            for (s0, n0), (s1, n1) in zip(cuts[:-1], cuts[1:]):
                L = max(s1 - s0, 1.0)
                k = 1.0 / L
                for na, nb in ((n0, n1), (n1, n0)):
                    if id(na) in idx:
                        i = idx[id(na)]
                        Amat[i, i] += k
                        if id(nb) in idx:
                            Amat[i, idx[id(nb)]] -= k
                        else:
                            b[i] += k * (nb.y if nb.y is not None else float(np.interp(s0, w.S, w.g)))
        for i, n in enumerate(unknown):
            if Amat[i, i] == 0:
                Amat[i, i] = 1.0
                b[i] = float(self._ground(n.p[0], n.p[1]))
        yv = np.linalg.solve(Amat + np.eye(m) * 1e-9, b)
        for n, v in zip(unknown, yv):
            n.y = float(v)

    def _ramp_base(self, w):
        """Ramp profile before tents: a straight grade line between its nodes; where the ramp runs alongside its
        carriageway (speed-change lane, auxiliary lane) it takes the carriageway's height, blended over 15 m."""
        S = w.S
        cuts = sorted(w.cuts, key=lambda c: c[0])
        ss = [c[0] for c in cuts if c[1].y is not None]
        yy = [c[1].y for c in cuts if c[1].y is not None]
        if not ss:
            ss, yy = [0, w.L], [w.g[0], w.g[-1]]
        y = np.interp(S, ss, yy)
        parents = [p for p in (getattr(w, "parents", None) or ([w.parent] if w.parent else [])) if p is not None]
        if not parents:
            return y
        import shapely
        best_d = np.full(len(S), np.inf)
        best_y = np.zeros(len(S))
        for p in parents:
            if p.y is None:
                continue
            line = shapely.LineString(p.P)
            pts = shapely.points(w.P)
            dd = shapely.distance(pts, line)
            sp = shapely.line_locate_point(line, pts)
            yp = np.interp(sp, p.S, p.y)
            m = dd < best_d
            best_d[m] = dd[m]
            best_y[m] = yp[m]
        half = (w.prof["cw_w"] if w.prof else 5.0) / 2.0
        pw = 0.0
        for p in parents:
            if p.prof:
                pw = max(pw, p.prof["cw_w"] / 2.0)
        lim = half + pw + 1.0
        wgt = np.clip(1.0 - (best_d - lim) / 15.0, 0.0, 1.0)
        # the free part runs as a straight grade line from where the ramp leaves its carriageway to its other node
        full = wgt >= 0.999
        cs = list(zip(ss, yy)) + [(float(S[i]), float(best_y[i])) for i in np.nonzero(full)[0]]
        cs.sort()
        ylin = np.interp(S, [c[0] for c in cs], [c[1] for c in cs])
        return wgt * best_y + (1 - wgt) * ylin

    def _tents(self, w, base, clear, depth):
        S = w.S
        y = base.copy()
        g = w.gmax
        for o in w.over:
            l = o["lower"]
            yl = float(np.interp(o["sl"], l.S, l.y)) if l.y is not None else float(self._ground(*o["pt"]))
            need = yl + clear + depth
            t = need - g * np.maximum(0.0, np.abs(S - o["s"]) - o["half"])
            y = np.maximum(y, t)
        for a, b, need in getattr(w, "spans", ()):
            y = np.maximum(y, need - g * np.maximum(0.0, np.maximum(a - S, S - b)))
        for o in getattr(w, "rails", ()):
            y = np.maximum(y, o["need"] - g * np.maximum(0.0, np.abs(S - o["s"]) - o["half"]))
        return y

    def _pin(self, w, y):
        """Pin a primary road's profile to its node heights: piecewise-linear correction that fades out over the
        length the grade needs."""
        S = w.S
        g = w.gmax
        cuts = sorted(w.cuts, key=lambda c: c[0])
        ctrl = []
        for s, n in cuts:
            if n.y is None:
                continue
            d = n.y - float(np.interp(s, S, y))
            ctrl.append((s, d, abs(d) / max(g * 0.8, 1e-3) + 15.0))
        if not ctrl:
            return y
        cs = []
        for k, (s, d, Lk) in enumerate(ctrl):
            if k == 0 and s - Lk > 0:
                cs.append((s - Lk, 0.0))
            cs.append((s, d))
            if k + 1 < len(ctrl):
                s2, d2, L2 = ctrl[k + 1]
                if s2 - s > Lk + L2:
                    cs.append((s + Lk, 0.0))
                    cs.append((s2 - L2, 0.0))
            elif s + Lk < w.L:
                cs.append((s + Lk, 0.0))
        cs.sort()
        xs = np.array([c[0] for c in cs])
        ds = np.array([c[1] for c in cs])
        return y + np.interp(S, xs, ds)

    def _clearance_fix(self, clear, depth):
        """Raise an upper road locally when a later pin pulled it below the clearance (keeps nodes as they are)."""
        for w in self.ways:
            for o in w.over:
                l = o["lower"]
                yl = float(np.interp(o["sl"], l.S, l.y))
                yu = float(np.interp(o["s"], w.S, w.y))
                if yu - depth - yl < clear - 1e-3:
                    t = yl + clear + depth - w.gmax * np.maximum(0.0, np.abs(w.S - o["s"]) - o["half"])
                    w.y = np.maximum(w.y, t)
            for a, b, need in getattr(w, "spans", ()):
                m = (w.S >= a) & (w.S <= b)
                if m.any() and float(np.min(w.y[m])) < need - 1e-3:
                    w.y = np.maximum(w.y, need - w.gmax * np.maximum(0.0, np.maximum(a - w.S, w.S - b)))
            for o in getattr(w, "rails", ()):
                m = np.abs(w.S - o["s"]) <= o["half"]
                if m.any() and float(np.min(w.y[m])) < o["need"] - 1e-3:
                    w.y = np.maximum(w.y, o["need"] - w.gmax * np.maximum(0.0, np.abs(w.S - o["s"]) - o["half"]))

    # ------------------------------------------------------------------ structures
    def structures(self):
        fill = self.N.norm("validator.grading", "cut_fill_max_m")
        for w in self.ways:
            kinds = np.array(["ground"] * len(w.S), dtype=object)
            dy = w.y - w.g
            kinds[dy > fill] = "embankment"
            kinds[dy < -fill] = "cut"
            for o in w.over + getattr(w, "rails", []):
                m = np.abs(w.S - o["s"]) <= o["half"] + o.get("skew", 0.0)
                kinds[m] = "overpass"
            # the spec's own spans: a bridge over a canal or stream drawn as a line (not in the water polygons) and
            # an overpass are structures over their whole length
            for a, b, why in w.lifts:
                if why in ("spec:bridge", "spec:overpass"):
                    kinds[(w.S >= a - 1e-6) & (w.S <= b + 1e-6)] = why[5:]
            for a, b, k in w.osm_struct:
                m = (w.S >= a) & (w.S <= b)
                kinds[m] = k
            if self.water is not None and w.source == "new":
                import shapely
                inside = shapely.contains_xy(self.water, w.P[:, 0], w.P[:, 1])
                kinds[inside & (kinds != "overpass")] = "bridge"
            w.kinds = kinds

    # ------------------------------------------------------------------ export
    def segments(self):
        """Split ways at their nodes → list of segment dicts (CONTRACT §4) and the node list."""
        segs = []
        k = 0
        for w in self.ways:
            cuts = sorted(w.cuts, key=lambda c: c[0])
            if len(cuts) < 2:
                continue
            for (s0, n0), (s1, n1) in zip(cuts[:-1], cuts[1:]):
                if s1 - s0 < 0.05:
                    continue
                m = (w.S > s0 + 1e-6) & (w.S < s1 - 1e-6)
                Pm = w.P[m]
                ym = w.y[m]
                p0, p1 = n0.p, n1.p
                y0, y1 = n0.y, n1.y
                pts = np.vstack([p0, Pm, p1])
                yy = np.concatenate([[y0], ym, [y1]])
                Sloc = G.chainage(pts)
                kk = np.concatenate([[_kind_at(w, s0)], w.kinds[m], [_kind_at(w, s1)]])
                struct = _runs(Sloc, kk)
                k += 1
                # a chained way: street, name and OSM id of the piece the segment lies on
                q = w.piece_at(G.point_at(pts, 0.5 * float(Sloc[-1]), Sloc))
                street, name_ru, src = (w.street, w.name_ru, w.source) if q is None else q[1:]
                seg = {"id": f"s{k}", "a": n0.id, "b": n1.id, "class": w.cls, "pid": w.pid,
                       "oneway": bool(w.oneway),
                       "pts": [[round(float(x), 2), round(float(z), 2), round(float(yv), 2)] for (x, z), yv in zip(pts, yy)],
                       "struct": struct, "years": list(w.years), "name_ru": name_ru, "street": street,
                       "ic": w.ic, "_way": w.id, "_source": w.source, "_role": w.role}
                if str(src).startswith("osm:"):
                    seg["source"] = src
                if getattr(w, "stages", None):
                    seg["stages"] = [dict(st, years=list(st["years"])) for st in w.stages]
                segs.append(seg)
        return segs


def _reproject(P, s_old, p, win=5.0):
    """Chainage of point p on polyline P, looked for within `win` m of s_old (a closed or self-touching line passes the
    same point at two chainages)."""
    L = float(G.chainage(P)[-1])
    a, b = max(0.0, s_old - win), min(L, s_old + win)
    if b - a < 1e-6:
        return min(max(s_old, 0.0), L)
    return a + float(G.project(G.cut(P, a, b), p)[0])


def _with_vertices_at(P, ss):
    """P with extra vertices at chainages ss (inside the line, where it has none yet); the shape does not change."""
    if not len(ss):
        return P
    S = G.chainage(P)
    add = [float(x) for x in ss if 1e-3 < x < S[-1] - 1e-3 and float(np.min(np.abs(S - x))) > 1e-3]
    if not add:
        return P
    S2 = np.unique(np.concatenate([S, add]))
    return np.column_stack([np.interp(S2, S, P[:, 0]), np.interp(S2, S, P[:, 1])])


def _kind_at(w, s):
    i = int(np.argmin(np.abs(w.S - s)))
    return w.kinds[i]


def _runs(S, kinds):
    """[{from_m, to_m, kind}] runs of equal kind along chainage (a run starts / ends halfway between samples)."""
    out = []
    n = len(S)
    if n == 0:
        return out
    start = 0.0
    cur = kinds[0]
    for i in range(1, n):
        if kinds[i] != cur:
            mid = 0.5 * (S[i - 1] + S[i])
            out.append({"from_m": round(float(start), 1), "to_m": round(float(mid), 1), "kind": str(cur)})
            start, cur = mid, kinds[i]
    out.append({"from_m": round(float(start), 1), "to_m": round(float(S[-1]), 1), "kind": str(cur)})
    # merge tiny ground runs between two equal structures (< 2 m)
    merged = []
    for r in out:
        if merged and r["kind"] == merged[-1]["kind"]:
            merged[-1]["to_m"] = r["to_m"]
        else:
            merged.append(r)
    return merged


def _smooth(S, g, win):
    """Moving average of ground heights over a window (m) along chainage."""
    if len(S) < 3:
        return g.copy()
    out = np.empty_like(g)
    j0 = j1 = 0
    cs = np.concatenate([[0], np.cumsum(g)])
    n = len(S)
    for i in range(n):
        while S[j0] < S[i] - win / 2:
            j0 += 1
        while j1 < n and S[j1] <= S[i] + win / 2:
            j1 += 1
        out[i] = (cs[j1] - cs[j0]) / max(j1 - j0, 1)
    return out


def _grade_limit(y, S, g):
    """Clamp the grade to ≤ g, the same whichever way the line runs: the mean of the clamp along it and of the clamp against
    it (each a forward then a backward pass; the mean of two lines of grade ≤ g keeps it). One pass direction alone put the two
    carriageways of a divided road, drawn in opposite directions, one on a 10–20 m fill and its twin in a cut over the same
    ground (owner 03.11.2026)."""
    def once(y_, S_):
        y_ = y_.copy()
        for i in range(1, len(y_)):
            ds = S_[i] - S_[i - 1]
            y_[i] = min(max(y_[i], y_[i - 1] - g * ds), y_[i - 1] + g * ds)
        for i in range(len(y_) - 2, -1, -1):
            ds = S_[i + 1] - S_[i]
            y_[i] = min(max(y_[i], y_[i + 1] - g * ds), y_[i + 1] + g * ds)
        return y_
    S = np.asarray(S, float)
    return 0.5 * (once(np.asarray(y, float), S) + once(np.asarray(y, float)[::-1], (S[-1] - S)[::-1])[::-1])
