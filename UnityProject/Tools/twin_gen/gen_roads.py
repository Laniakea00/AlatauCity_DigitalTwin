"""Road graph of Alatau City from the master-plan street axes + OSM highways/main roads (centre-lines from blend_geo.json).
Result: nodes + edges (class, length, polyline) — the base graph for traffic and for laying utility networks along streets."""
import json, math, collections
import numpy as np
import networkx as nx
import shapely
from shapely.geometry import LineString, MultiLineString, Point
from shapely.strtree import STRtree
from scipy.spatial import cKDTree

XMIN, XMAX, ZMIN, ZMAX = -21800, 21800, -30300, 31400
CLASSES = {  # class: (lanes per direction, capacity veh/h per lane, free speed km/h)
    "highway": (4, 2000, 100),   # Almaty–Konaev: being widened; flows are AM-peak one-way
    "ring": (3, 1900, 100),
    "main": (2, 900, 60),
    "street": (2, 700, 50),
}
SOURCES = [("Highways", "highway"), ("BAKAD ring road axis", "ring"), ("Main roads", "main"),
           ("Planned street axes", "street"), ("Planned bridges", "street")]
RANK = {"highway": 0, "ring": 1, "main": 2, "street": 3}


def inside(s):
    return all(XMIN <= v <= XMAX for v in (s[0], s[2])) and all(ZMIN <= v <= ZMAX for v in (s[1], s[3]))


def build(geo):
    lines, cls = [], []
    for layer, c in SOURCES:
        segs = [s for s in geo["layers"].get(layer, []) if inside(s) and (abs(s[0] - s[2]) + abs(s[1] - s[3])) > 0.5]
        ml = MultiLineString([[(round(s[0]), round(s[1])), (round(s[2]), round(s[3]))] for s in segs])
        merged = shapely.line_merge(shapely.set_precision(ml, 1.0))
        geoms = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for g in geoms:
            if g.length > 1: lines.append(g); cls.append(c)
        print(f"  {layer}: {len(segs)} segments -> {len(geoms)} lines")
    # node all lines against each other (crossings become junctions)
    noded = shapely.unary_union(shapely.set_precision(MultiLineString(lines), 1.0))
    pieces = list(noded.geoms) if hasattr(noded, "geoms") else [noded]
    tree = STRtree(lines)
    G = nx.Graph()
    key = lambda p: (int(round(p[0])), int(round(p[1])))
    for pc in pieces:
        if pc.length < 1: continue
        mid = pc.interpolate(0.5, normalized=True)
        cand = tree.query(mid.buffer(2.0))
        c = "street"
        if len(cand):
            best = min(cand, key=lambda i: (lines[i].distance(mid), RANK[cls[i]]))
            c = cls[best]
        coords = list(pc.coords)
        a, b = key(coords[0]), key(coords[-1])
        if a == b: continue
        old = G.get_edge_data(a, b)
        if old is None or RANK[c] < RANK[old["cls"]]:
            G.add_edge(a, b, cls=c, geom=[key(p) for p in coords], length=pc.length)
    print(f"  noded graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    # close small gaps: dangling ends within 30 m of another node
    nodes = list(G.nodes); kd = cKDTree(np.array(nodes, float))
    added = 0
    for n in nodes:
        if G.degree(n) != 1: continue
        for j in kd.query_ball_point(n, 30.0):
            m = nodes[j]
            if m == n or G.has_edge(n, m) or nx.has_path(G, n, m) and nx.shortest_path_length(G, n, m) < 4: continue
            c = next(iter(G.edges(n, data=True)))[2]["cls"]
            G.add_edge(n, m, cls=c, geom=[n, m], length=math.dist(n, m)); added += 1; break
    print(f"  gap links added: {added}")
    comp = max(nx.connected_components(G), key=len)
    G = G.subgraph(comp).copy()
    print(f"  largest component: {G.number_of_nodes()} nodes")
    return contract(G)


def contract(G):
    """Merge chains of degree-2 nodes with the same class into one edge with a polyline."""
    H = nx.Graph(); seen = set()
    keep = {n for n in G.nodes if G.degree(n) != 2 or len({G.edges[e]["cls"] for e in G.edges(n)}) > 1}
    if not keep: keep = {next(iter(G.nodes))}
    for s in keep:
        for nb in G.neighbors(s):
            e0 = frozenset((s, nb))
            if e0 in seen: continue
            path = [s, nb]; seen.add(e0); c = G.edges[s, nb]["cls"]
            while path[-1] not in keep:
                cur, prev = path[-1], path[-2]
                nxt = [m for m in G.neighbors(cur) if m != prev][0]
                seen.add(frozenset((cur, nxt))); path.append(nxt)
            geom = []
            for u, v in zip(path, path[1:]):
                g = G.edges[u, v]["geom"]
                if g[0] != u: g = g[::-1]
                geom.extend(g if not geom else g[1:])
            ls = LineString(geom).simplify(3.0)
            a, b = path[0], path[-1]
            if a == b: continue
            if H.has_edge(a, b) and H.edges[a, b]["length"] <= ls.length: continue
            H.add_edge(a, b, cls=c, geom=[(int(x), int(z)) for x, z in ls.coords], length=ls.length)
    print(f"  contracted: {H.number_of_nodes()} nodes, {H.number_of_edges()} edges, "
          f"{sum(d['length'] for *_, d in H.edges(data=True)) / 1000:.0f} km")
    return H


if __name__ == "__main__":
    import sys, pickle
    geo = json.load(open(sys.argv[1], encoding="utf-8"))
    H = build(geo)
    pickle.dump(H, open(sys.argv[2], "wb"))
    print(collections.Counter(d["cls"] for *_, d in H.edges(data=True)))
