"""Existing roads from Overture / OSM (W34 level-0 extract) for gen_network (w43).

roads.geojson gives the geometry in the Unity frame, class, sub(class), name and the connector indices; the raw
segment.parquet gives the spans of road_flags (is_bridge / is_tunnel) and level_rules (`between` = fractions of the
segment length). Every mapping decision and every drop goes to the network log.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import geom as G  # noqa: E402


def _nv(v):
    v = np.asarray(v, float)
    n = float(np.hypot(v[0], v[1]))
    return v / n if n > 1e-12 else v


from lib import jio, paths  # noqa: E402
from lib import years as Y  # noqa: E402
from net_core import Way  # noqa: E402
from net_roads import carriageway_profile, pid_of  # noqa: E402

# Overture class / subclass → norms class. (class, sub) wins over (class, None). "village" variants apply when most of
# the road lies in a village_existing zone. An existing service lane (any sub) is a street, never a driveway_* class:
# driveway_* is a drive of driveways.json only (merge takes every driveway_* edge for an access-only drive, so nothing
# could attach to it); in a village it is a village lane, elsewhere a secondary local street (as gate_net keeps them).
CLASS_MAP = {
    ("motorway", None): "expressway",
    ("motorway", "link"): "ramp",
    ("trunk", None): "arterial_continuous",
    ("trunk", "link"): "ramp",
    ("primary", None): "arterial_regulated",
    ("primary", "link"): "ramp",
    ("secondary", None): "district_transport",
    ("secondary", "link"): "district_transport",
    ("tertiary", None): "district_transport",
    ("tertiary", "link"): "district_transport",
    ("residential", None): "local",
    ("unclassified", None): "local",
    ("living_street", None): "local_secondary",
    ("service", None): "local_secondary",
    ("service", "driveway"): "local_secondary",
    ("service", "parking_aisle"): "local_secondary",
    ("service", "alley"): "local_secondary",
    ("pedestrian", None): "pedestrian_street",
    ("cycleway", None): "bike_path",
    ("track", None): "village_lane",          # only where it serves houses (else dropped)
    ("unknown", None): "local",
}
VILLAGE = {"district_transport": "village_main", "local": "village_secondary", "local_secondary": "village_secondary"}
VILLAGE_LANE = {"service"}      # Overture classes that are a village lane in a village (the narrowest village street)
ONEWAY = {"expressway", "ramp"}
HOUSE_MIN_M2 = 25.0      # orchestrator 31.10: every Overture building ≥ 25 m² is an existing house, smaller = shed
SKIP = {"footway", "path", "steps", "sidewalk", "crosswalk", "bridleway", "cycleway_link"}


def _flags(ids):
    """{id: {"struct": [(f0, f1, kind)], "level": [(f0, f1, lv)]}} from the raw parquet (fractions of the length)."""
    if not ids:
        return {}
    try:
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
    except ImportError:
        return {}
    f = paths.w34("overture_raw", "segment.parquet")
    if not os.path.exists(f):
        return {}
    t = pq.read_table(f, columns=["id", "road_flags", "level_rules"])
    t = t.filter(pc.is_in(t["id"], value_set=pa.array(list(ids))))
    out = {}
    for r in t.to_pylist():
        st, lv = [], []
        for fl in r["road_flags"] or []:
            b = fl["between"] or [0.0, 1.0]
            for v in fl["values"] or []:
                if v == "is_bridge":
                    st.append((b[0], b[1], "bridge"))
                elif v == "is_tunnel":
                    st.append((b[0], b[1], "tunnel"))
        for lr in r["level_rules"] or []:
            b = lr["between"] or [0.0, 1.0]
            if lr["value"]:
                lv.append((b[0], b[1], int(lr["value"])))
        out[r["id"]] = {"struct": st, "level": lv}
    return out


_CACHE = {}


def _polygons(features):
    """Shapely polygons of GeoJSON features, built in bulk for plain 2D polygons without holes (the same geometries
    as shapely.geometry.shape, which is used for every other feature)."""
    import shapely
    import shapely.geometry
    out = np.empty(len(features), dtype=object)
    simple, rings = [], []
    for k, f in enumerate(features):
        g = f["geometry"]
        c = g.get("coordinates") if g else None
        if g and g.get("type") == "Polygon" and c and len(c) == 1 and all(len(q) == 2 for q in c[0]):
            simple.append(k)
            rings.append(c[0])
        else:
            out[k] = shapely.geometry.shape(g)
    if simple:
        n = np.array([len(r) for r in rings])
        xy = np.array([q for r in rings for q in r], float)
        lr = shapely.linearrings(xy, indices=np.repeat(np.arange(len(rings)), n))
        out[np.array(simple)] = shapely.polygons(lr)
    return out


def _city_buildings():
    """W34 OSM building footprints, their areas and STRtree; parsed once per process (the file is the whole city)."""
    import shapely
    path = paths.w34("osm", "buildings.geojson")
    key = (path, os.path.getmtime(path), os.path.getsize(path))
    c = _CACHE.get("buildings")
    if c is None or c[0] != key:
        geoms = _polygons(jio.load_geojson(path))
        c = (key, geoms, shapely.area(geoms), shapely.STRtree(geoms))
        _CACHE["buildings"] = c
    return c[1], c[2], c[3]


def _twin_existing_points():
    """(x, z) of the twin's existing_osm rows of buildings.csv in file order; read once per process."""
    csv = paths.twin("CityData", "buildings.csv")
    if not os.path.exists(csv):
        return np.zeros((0, 2))
    key = (csv, os.path.getmtime(csv), os.path.getsize(csv))
    c = _CACHE.get("twin_existing")
    if c is None or c[0] != key:
        import csv as _csv
        with open(csv, encoding="utf-8") as fh:
            pts = [(float(r["x"]), float(r["z"])) for r in _csv.DictReader(fh) if r.get("source") == "existing_osm"]
        c = (key, np.array(pts, float).reshape(-1, 2))
        _CACHE["twin_existing"] = c
    return c[1]


def houses_in(polys):
    """Footprints (shapely) of existing houses inside the given polygons: W34 OSM buildings + twin existing_osm points
    (as 8 × 8 m squares where no OSM footprint is within 5 m)."""
    import shapely
    if not polys:
        return []
    zone = shapely.union_all(polys)
    out = []
    geoms, areas, tree = _city_buildings()
    small = 0
    for i in tree.query(zone, predicate="intersects"):
        if areas[i] < HOUSE_MIN_M2:
            small += 1                 # a shed: not a house (may be removed by the generators, with a log line)
            continue
        out.append(geoms[i])
    houses_in.sheds = small
    pts = _twin_existing_points()
    if len(pts):
        pts = pts[shapely.contains_xy(zone, pts[:, 0], pts[:, 1])]
        if len(pts) and out:
            have = shapely.STRtree(out)
            near = np.zeros(len(pts), bool)
            near[have.query(shapely.buffer(shapely.points(pts), 5.0, quad_segs=16), predicate="intersects")[0]] = True
            pts = pts[~near]
        out += [shapely.box(x - 4, z - 4, x + 4, z + 4) for x, z in pts]
    return out


def load(net, area, zones, retire=None, keep=None):
    """Add the existing roads inside `area` (shapely polygon) to the network. zones: spec zones (for villages);
    retire: {overture id: why} existing roads the spec replaces (not built, logged); keep: {overture id: spec street}
    (keep_existing streets: their class, name, years and struct win over the class map)."""
    retire = retire or {}
    keep = keep or {}
    import shapely
    N = net.N
    gj = jio.load_geojson(paths.w34("osm", "roads.geojson"))
    cj = jio.load_geojson(paths.w34("osm", "connectors.geojson"))
    conn_pt = {f["properties"]["i"]: np.array(f["geometry"]["coordinates"], float) for f in cj}
    feats = []
    for f in gj:
        g = shapely.geometry.shape(f["geometry"])
        if g.intersects(area):
            feats.append((f, g))
    flags = _flags([f["properties"]["id"] for f, _ in feats])
    vill = [shapely.Polygon(z["polygon"]) for z in zones if z.get("use") == "village_existing"]
    vill_u = shapely.union_all(vill) if vill else None
    houses = None
    stats = {}
    ways = []
    for f, g in feats:
        p = f["properties"]
        oid = p["id"]
        ocls, sub = p.get("class"), p.get("sub")
        if oid in retire:
            net.L("OSM: существующая дорога снята по spec (её заменяет новая)", [f"osm:{oid}"], why=retire[oid])
            continue
        if ocls in SKIP:
            net.L("OSM: не дорога для машин, не берётся", [f"osm:{oid}"], osm_class=ocls)
            continue
        cls = CLASS_MAP.get((ocls, sub)) or CLASS_MAP.get((ocls, None))
        if cls is None:
            cls = "local"
            net.L("OSM: неизвестный класс дороги, принят local", [f"osm:{oid}"], osm_class=ocls, osm_sub=sub)
        in_village = vill_u is not None and g.intersection(vill_u).length > 0.5 * g.length
        if in_village and ocls in VILLAGE_LANE:
            cls = "village_lane"
        elif in_village and cls in VILLAGE:
            cls = VILLAGE[cls]
        st = keep.get(oid)
        if st is not None:
            if st["class"] != cls:
                net.L("OSM: класс дороги взят из spec", [st["id"], f"osm:{oid}"], osm=cls, spec=st["class"])
            cls = st["class"]
        elif keep:
            net.L("OSM: дороги нет в улицах spec (не снята): построена по таблице классов", [f"osm:{oid}"], cls=cls)
        if ocls == "track" and st is None:
            if houses is None:
                houses = houses_in(vill) if vill else []
                htree = shapely.STRtree(houses) if houses else None
            serves = htree is not None and len(htree.query(g.buffer(25.0), predicate="intersects")) > 0
            if not serves:
                net.L("OSM: полевая дорога (track) не обслуживает дома — не берётся", [f"osm:{oid}"])
                continue
            net.L("OSM: полевая дорога (track) обслуживает дома — village_lane", [f"osm:{oid}"])
        full = np.array(g.coords, float)
        Lfull = G.length(full)
        fl = flags.get(oid, {"struct": [], "level": []})
        if p.get("bridge") and not fl["struct"]:
            fl["struct"] = [(0.0, 1.0, "bridge")]
        if p.get("tunnel") and not fl["struct"]:
            fl["struct"] = [(0.0, 1.0, "tunnel")]
        if p.get("level") and not fl["level"]:
            fl["level"] = [(0.0, 1.0, int(p["level"]))]
        clip = g.intersection(area)
        parts = [clip] if clip.geom_type == "LineString" else [x for x in getattr(clip, "geoms", []) if x.geom_type == "LineString"]
        if clip.length < g.length - 0.5:
            net.L("OSM: дорога обрезана по границе участка", [f"osm:{oid}"], kept_m=round(clip.length, 1),
                  of_m=round(g.length, 1))
        for k, part in enumerate(parts):
            P = np.array(part.coords, float)
            if G.length(P) < 2.0:
                continue
            # keep the direction of the original (oneway roads)
            s_a = G.project(full, P[0])[0]
            s_b = G.project(full, P[-1])[0]
            if s_b < s_a:
                P = P[::-1].copy()
                s_a, s_b = s_b, s_a
            oneway = cls in ONEWAY if st is None else bool(st.get("oneway")) or cls in ONEWAY
            prof = N.profile(cls)
            if cls == "expressway":
                prof = carriageway_profile(prof)
                pid = pid_of(cls, prof, "cw")
            else:
                pid = pid_of(cls, prof, "road")
            w = Way(cls, P, oneway=oneway, prof=prof, pid=pid,
                    years=Y.norm4(st["years"]) if st and st.get("years") else list(Y.EXISTING),
                    name_ru=(st.get("name_ru") if st else None) or p.get("name") or "",
                    street=st["id"] if st else None, source=f"osm:{oid}", role="primary", id=f"o{len(ways) + 1}")
            w.osm_class = (ocls, sub)
            spec_struct = (st.get("struct") or []) if st else []
            if spec_struct and fl["struct"]:
                # OSM/Overture spans are exact (bridges over creeks and roads); a spec span over most of the line is
                # a summary of them, so the OSM flags win
                if k == 0:
                    net.L("keep_existing: сооружения берутся из флагов OSM (точные пролёты), spec struct не применяется",
                          [st["id"], f"osm:{oid}"], osm_spans=len(fl["struct"]), spec_spans=len(spec_struct))
                spec_struct = []
            for sx in spec_struct:
                a_ = G.project(w.P, sx["from"])[0]
                b_ = G.project(w.P, sx["to"])[0]
                a_, b_ = min(a_, b_), max(a_, b_)
                if b_ - a_ > 0.5 and sx["kind"] in ("bridge", "overpass", "tunnel"):
                    w.osm_struct.append((a_, b_, sx["kind"]))
                    w.osm_level.append((a_, b_, -1 if sx["kind"] == "tunnel" else 1))
            for f0, f1, kind in fl["struct"]:
                a, b = f0 * Lfull - s_a, f1 * Lfull - s_a
                if b > 0 and a < w.L:
                    w.osm_struct.append((max(a, 0.0), min(b, w.L), kind))
            for f0, f1, lv in fl["level"]:
                a, b = f0 * Lfull - s_a, f1 * Lfull - s_a
                if b > 0 and a < w.L:
                    w.osm_level.append((max(a, 0.0), min(b, w.L), lv))
            for ci in p.get("conn") or []:
                cp = conn_pt.get(ci)
                if cp is None:
                    continue
                s, dist, _ = G.project(w.P, cp)
                if dist < 0.5:
                    w.osm_conn.append((s, ci))
            # ends on the area boundary are trial-area joints
            for e, pt in ((0, P[0]), (1, P[-1])):
                if area.exterior.distance(shapely.Point(pt)) < 0.5:
                    w.end_kind[e] = "joint"
                    w.end_ref[e] = f"osm:{oid}"
            ways.append(w)
            net.add(w)
            stats[cls] = stats.get(cls, 0.0) + w.L
    ways = _chain(net, ways)
    net.L("OSM: существующие дороги взяты по классам", [], km_by_class={k: round(v / 1000, 2) for k, v in stats.items()},
          mapping={f"{a}/{b or '-'}": c for (a, b), c in CLASS_MAP.items()})
    return ways


def virtual_carriageway(ways, w0, reach=2500.0, same_class=True):
    """A carriageway made of OSM pieces chained through their nodes (links branch off there): the piece w0 extended
    forward and backward by the most collinear continuation, up to `reach` m each way (same class for expressway
    carriageways; any class for a minor road that runs into another street). Returns a Way that is NOT in the network
    (templates attach ramps to its geometry; the ramp ends land on the real pieces), or w0 when nothing continues."""
    def nxt(P, fwd, used):
        p = P[-1] if fwd else P[0]
        h = _nv(P[-1] - P[-2]) if fwd else _nv(P[0] - P[1])
        best = None
        for o in ways:
            if any(o is u for u in used) or (same_class and o.cls != w0.cls) or o.role != "primary" \
                    or o.oneway != w0.oneway:
                continue
            for rev in ((False, True) if not o.oneway else (False,)):
                Q = o.P[::-1] if rev else o.P
                q = Q[0] if fwd else Q[-1]
                if np.hypot(*(q - p)) > 1.0:
                    continue
                ho = _nv(Q[1] - Q[0]) if fwd else _nv(Q[-2] - Q[-1])
                c = float(np.dot(h, ho))
                if c > (0.95 if same_class else 0.7) and (best is None or c > best[0]):
                    best = (c, o, Q)
        return best
    chain = [w0]
    P = w0.P.copy()
    L = 0.0
    while L < reach:
        b = nxt(P, True, chain)
        if b is None:
            break
        chain.append(b[1])
        P = G.concat(P, b[2])
        L += b[1].L
    Lb = 0.0
    while Lb < reach:
        b = nxt(P, False, chain)
        if b is None:
            break
        chain.insert(0, b[1])
        P = G.concat(b[2], P)
        Lb += b[1].L
    if len(chain) == 1:
        return w0
    v = Way(w0.cls, P, oneway=w0.oneway, prof=w0.prof, pid=w0.pid, years=w0.years,
            name_ru=w0.name_ru, source=w0.source, role="primary", id=f"{w0.id}~")
    v.pieces = chain
    return v


def carriageway_pairs(ways, C, radius=80.0):
    """Two oneway OSM carriageways of one expressway near C, travelling in opposite directions: [(w_plus, w_minus)],
    each chained through its OSM nodes (virtual_carriageway)."""
    near = [w for w in ways if w.cls == "expressway" and G.project(w.P, C)[1] < radius]
    best = None
    for i, a in enumerate(near):
        sa, da, _ = G.project(a.P, C)
        ta = a.tan(sa)
        for b in near[i + 1:]:
            sb, db, _ = G.project(b.P, C)
            tb = b.tan(sb)
            if np.dot(ta, tb) > -0.8:
                continue
            sep = G.min_distance(a.P, b.P)
            if sep > 60:
                continue
            score = da + db
            if best is None or score < best[0]:
                best = (score, a, b)
    if not best:
        return None
    return virtual_carriageway(ways, best[1]), virtual_carriageway(ways, best[2])


def _chain(net, ways):
    """Join OSM pieces of one road that meet end to start with nobody else at that point (same class, same
    oneway, same years): Overture splits a carriageway at every flag change; templates need it whole. Each piece
    keeps its own spec street, name and OSM id (Way.pieces): planarize puts a node where two pieces of different
    streets meet and each segment takes the street of the piece it lies on."""
    from collections import defaultdict
    def key(p):
        return (round(float(p[0]), 1), round(float(p[1]), 1))
    changed = True
    while changed:
        changed = False
        at = defaultdict(list)
        for w in ways:
            at[key(w.P[0])].append((w, 0))
            at[key(w.P[-1])].append((w, 1))
        for k, uses in at.items():
            if len(uses) != 2:
                continue
            (a, ea), (b, eb) = uses
            if a is b or a.cls != b.cls or a.oneway != b.oneway or ea == eb and a.oneway or list(a.years) != list(b.years):
                continue
            if a.cls not in ("expressway", "ramp", "arterial_continuous"):
                continue
            # orient: a ends here, b starts here
            if ea == 0 and eb == 1:
                a, b = b, a
            elif ea == 0 and eb == 0:
                a.P = a.P[::-1].copy(); _flip(a)
            elif ea == 1 and eb == 1:
                b.P = b.P[::-1].copy(); _flip(b)
            La = G.length(a.P)
            a.pieces = (a.pieces or [(a.P.copy(), a.street, a.name_ru, a.source)]) + \
                (b.pieces or [(b.P.copy(), b.street, b.name_ru, b.source)])
            a.P = G.concat(a.P, b.P)
            for attr in ("osm_struct", "osm_level"):
                getattr(a, attr).extend((x0 + La, x1 + La, z) for x0, x1, z in getattr(b, attr))
            a.osm_conn.extend((sc + La, c) for sc, c in b.osm_conn)
            a.end_kind[1], a.end_ref[1] = b.end_kind[1], b.end_ref[1]
            a.source = a.source + "+" + b.source.split(":", 1)[1]
            a.refresh()
            net.ways.remove(b)
            ways.remove(b)
            kw = {"streets": [q[1] for q in a.pieces]} if len({q[1] for q in a.pieces}) > 1 else {}
            net.L("OSM: части одной дороги соединены в одну", [a.id, b.id], **kw)
            changed = True
            break
    return ways


def _flip(w):
    L = G.length(w.P)
    for attr in ("osm_struct", "osm_level"):
        setattr(w, attr, [(L - x1, L - x0, z) for x0, x1, z in getattr(w, attr)])
    w.osm_conn = [(L - sc, c) for sc, c in w.osm_conn]
    if w.pieces:
        w.pieces = w.pieces[::-1]
    w.end_kind = w.end_kind[::-1]
    w.end_ref = w.end_ref[::-1]
    w.refresh()
