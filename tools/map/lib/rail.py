"""Railway tracks of W34 osm/rail.geojson (w43): the lines a road crosses in another level (a deck over them takes the
rail clearance, gen_network; an at-grade crossing is rule 6) and housing keeps its distance from (szz.rail_m, rule 15).
decks(): the viaducts of a district's own railway (spec `rail`, Gate v1.2, or a merge's rail.json), which roads and drives
pass under (rule 25).

rail.geojson carries bridge / tunnel / level as one flag per feature (true when any span of a 30 km line is a bridge);
the spans themselves (rail_flags and level_rules, `between` = fractions of the length) come from the raw Overture
segment.parquet, as net_osm takes them for roads. Each track is cut there into pieces on the ground and pieces on a
structure; tunnels and underground spans are left out.
"""
import os

import numpy as np

from . import geom as G
from . import jio, paths

_CACHE = {}


def _spans(ids):
    """{id: [(f0, f1, what)]} what ∈ up (bridge, level ≥ 1) / under (tunnel, level < 0) / gone (abandoned, disused)."""
    try:
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
    except ImportError:
        return None
    f = paths.w34("overture_raw", "segment.parquet")
    if not os.path.exists(f):
        return None
    t = pq.read_table(f, columns=["id", "rail_flags", "level_rules"])
    t = t.filter(pc.is_in(t["id"], value_set=pa.array(list(ids))))
    out = {}
    for r in t.to_pylist():
        sp = []
        for fl in r["rail_flags"] or []:
            b = fl["between"] or [0.0, 1.0]
            for v in fl["values"] or []:
                k = {"is_bridge": "up", "is_tunnel": "under", "is_abandoned": "gone", "is_disused": "gone"}.get(v)
                if k:
                    sp.append((b[0], b[1], k))
        for lr in r["level_rules"] or []:
            b = lr["between"] or [0.0, 1.0]
            if lr["value"]:
                sp.append((b[0], b[1], "up" if int(lr["value"]) > 0 else "under"))
        out[r["id"]] = sp
    return out


def _pieces(P, sp):
    """[(sub-polyline, up)] of P cut at its spans; under and gone spans are dropped (gone and under win over up)."""
    S = G.chainage(P)
    L = float(S[-1])
    cuts = sorted({0.0, L} | {min(max(f * L, 0.0), L) for f0, f1, _ in sp for f in (f0, f1)})
    rank = {"gone": 3, "under": 2, "up": 1}
    out = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 1e-6:
            continue
        m = (a + b) / 2.0 / L
        what = max((k for f0, f1, k in sp if f0 <= m <= f1), key=rank.get, default="ground")
        if what in ("gone", "under"):
            continue
        up = what == "up"
        if out and out[-1][2] == up and abs(out[-1][1] - a) < 1e-6:
            out[-1] = (out[-1][0], b, up)
        else:
            out.append((a, b, up))
    return [(G.cut(P, a, b), up) for a, b, up in out if b - a > 0.5]


def _all():
    path = paths.w34("osm", "rail.geojson")
    try:
        key = (path, os.path.getmtime(path), os.path.getsize(path))
    except OSError:
        return []
    c = _CACHE.get("tracks")
    if c is not None and c[0] == key:
        return c[1]
    import shapely
    feats = jio.load_geojson(path)
    spans = _spans([f["properties"]["id"] for f in feats])
    out = []
    for f in feats:
        p = f.get("properties") or {}
        flags = p.get("flags") or []
        if "is_abandoned" in flags or "is_disused" in flags:
            continue
        if spans is not None and p.get("id") in spans:
            sp = spans[p["id"]]
        else:
            # no span data: the feature's own flags over its whole length (a bridge flag then means nothing: ground)
            lv = int(p.get("level") or 0)
            sp = [(0.0, 1.0, "under")] if p.get("tunnel") or lv < 0 else []
        g = shapely.geometry.shape(f["geometry"])
        parts = list(getattr(g, "geoms", [g]))
        if len(parts) > 1:
            sp = [q for q in sp if q[0] <= 0.0 and q[1] >= 1.0]      # fractions of a multi-line: only the whole-line flags
        for k, part in enumerate(parts):
            if part.geom_type != "LineString" or len(part.coords) < 2:
                continue
            P = G.dedup(np.asarray(part.coords, float)[:, :2])
            for n, (Q, up) in enumerate(_pieces(P, sp)):
                if len(Q) >= 2:
                    out.append({"id": p.get("id"), "piece": f"{k}.{n}", "P": Q, "up": up, "name": p.get("name") or ""})
    _CACHE["tracks"] = (key, out)
    return out


def tracks(area=None, pad=0.0):
    """[{id, piece, P (n×2 array), up, name}] of the operating tracks near `area` (shapely, grown by `pad`; None → all).

    Left out: tunnels and underground spans (the metro), abandoned and disused lines. `up` marks a piece on a bridge or
    on level ≥ 1 (a road crossing it passes under it); the rest lies on the ground."""
    import shapely
    allt = _all()
    if area is None:
        return list(allt)
    zone = area.buffer(pad) if pad else area
    return [t for t in allt if shapely.LineString(t["P"]).intersects(zone)]


DECK_KINDS = ("overpass", "bridge")


def decks(block):
    """Viaduct pieces of a district railway: the spec `rail` block ({lines: [{id, years, tracks: [{id, pts: [[x, z, rail
    head y], …], struct: [{from_m, to_m, kind}]}]}]}) or a merge's rail.json ({v, lines: [{id, y, tracks: [{id, p: flat
    x, z, y}]}]}). A spec track is a viaduct on its struct runs of kind overpass / bridge (no struct: all of it); a
    rail.json track is one along its whole length, as RailLayer draws it. Returns [{line, track, P (n×3: x, z, rail
    head y), years}]; the deck's underside is model rail_deck_below_m under the rail head and it spans model
    rail_deck_half_m each side of the track axis."""
    out = []
    for L in (block or {}).get("lines") or []:
        years = list(L.get("years") or L.get("y") or [])
        for t in L.get("tracks") or []:
            if t.get("pts") is not None:
                P = np.array([q[:3] for q in t["pts"] if len(q) >= 3], float).reshape(-1, 3)
                runs = [(r["from_m"], r["to_m"]) for r in t.get("struct") or [] if r.get("kind") in DECK_KINDS]
                if not t.get("struct"):
                    runs = [(0.0, float("inf"))]
            else:
                P = np.array(t.get("p") or [], float).reshape(-1, 3)
                runs = [(0.0, float("inf"))]
            if len(P) < 2:
                continue
            S = G.chainage(P[:, :2])
            for a, b in runs:
                a, b = max(float(a), 0.0), min(float(b), float(S[-1]))
                if b - a < 0.5:
                    continue
                inner = (S > a + 1e-9) & (S < b - 1e-9)
                ch = np.r_[a, S[inner], b]
                Q = np.c_[np.interp(ch, S, P[:, 0]), np.interp(ch, S, P[:, 1]), np.interp(ch, S, P[:, 2])]
                out.append({"line": L.get("id") or "", "track": t.get("id") or "", "P": Q, "years": years})
    return out
