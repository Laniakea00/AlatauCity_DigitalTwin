#!/usr/bin/env python3
"""Checks of a merge run (OUT/_merged/<run>) beyond validate_twin.py: file set and sizes, roads.json fields, film_roads.json v2,
bid tables, meshes, per-bid arrays, ramp traffic, structure clearance, drives (attach nodes on their street, pads), and the car edges
of the merged districts left without traffic (printed by class; not a failure). Exit code 1 on failure.

    python3 tools/map/export/check_merge.py <run> [--out OUT] [--base TWIN]"""
import argparse
import collections
import os
import subprocess
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import util as U  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("  ok   " if cond else "  FAIL ") + msg); ok &= bool(cond)


def zero_report(E, prof, tr, scen="base", year="2050", drives=None):
    """Car edges of the merged districts (new edges, `t` set) with vc = 0 in one year, by class; edges opening later are left out.
    Dead ends: the edge lies on a chain from a dead-end node (only through nodes of two car edges), or it is a one-way edge out of a
    node no edge leads into — no route can reach it unless a building fronts it (stubs and carriageway ends at the area edge waiting
    for a neighbour). Carless by design and drives (`drives`: merge's drive edges; by class when None) are listed apart."""
    si = ["base", "fast", "slow", "infra"].index(scen); vc = tr["by_scenario"][scen][year]["vc"]; Y = int(year)
    carless = [U.carless(e.get("t"), prof[e["p"]] if "p" in e else None) for e in E]
    isdrv = [(i in drives) if drives is not None else e.get("t") in U.DRIVES for i, e in enumerate(E)]
    car = [not carless[i] and not isdrv[i] for i, e in enumerate(E)]
    deg = collections.Counter(); inc = collections.defaultdict(list)
    for i, e in enumerate(E):
        if car[i] and e["y"][si] <= Y:
            deg[e["a"]] += 1; deg[e["b"]] += 1; inc[e["a"]].append(i); inc[e["b"]].append(i)
    dead = set()
    for nd in [v for v, d in deg.items() if d == 1]:
        prev, cur = None, nd
        while True:
            nxt = [i for i in inc[cur] if i != prev and i not in dead]
            if len(nxt) != 1:
                break
            i = nxt[0]; dead.add(i); prev = i; cur = E[i]["b"] if E[i]["a"] == cur else E[i]["a"]
            if deg[cur] != 2:
                break
    for v, es in inc.items():                    # one-way edges out of a node nothing leads into (a carriageway starting at a gap)
        if all(E[i].get("k", 0) != 0 and E[i]["a"] == v for i in es):
            dead |= set(es)
    z, tot, zd, cl, dz, dt = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter(), 0, 0
    for i, e in enumerate(E):
        if "t" not in e or e["y"][si] > Y:
            continue
        if carless[i]:
            cl[e["t"]] += 1; continue
        if isdrv[i]:
            dt += 1; dz += vc[i] == 0; continue
        tot[e["t"]] += 1
        if vc[i] == 0:
            z[e["t"]] += 1; zd[e["t"]] += i in dead
    print(f"Car edges of the merged districts with vc = 0 ({scen} {year}; target 0, edges opening later left out)")
    print("  " + ", ".join(f"{t} {z[t]}/{tot[t]}" + (f" ({zd[t]} dead ends)" if zd[t] else "") for t in sorted(tot)))
    print(f"  total {sum(z.values())} of {sum(tot.values())} car edges, {sum(zd.values())} of them dead ends without buildings (left: {sum(z.values()) - sum(zd.values())}); "
          f"drives (access only, no through route) {dz} of {dt} without cars")
    if cl:
        print("  по проекту без машин (not counted): " + ", ".join(f"{t} {n}" for t, n in sorted(cl.items())))
    return z, tot, zd


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--out", default=U.OUT); ap.add_argument("--base", default=U.TWIN)
    a = ap.parse_args()
    run = os.path.join(a.out, "_merged", a.run); A = os.path.join(run, "Assets")
    man = U.load_json(os.path.join(run, "manifest.json"))
    print("Files")
    parts = man.get("layer_parts") or [U.F_AQL]
    need = [U.F_ROADS, U.F_FILM, U.F_CSV] + parts + [U.F_BOUNDS, U.F_HIDE, U.F_ORDER, U.F_LRT, U.F_NOPLANT, U.F_PARKING, U.F_DISTRICTS, U.F_SOLAR,
            U.F_NORMS, U.F_RAIL] + [f"StreamingAssets/twin/{k}.json" for k in U.TWIN_JSON]
    for rel in need:
        p = os.path.join(A, rel); ex = os.path.exists(p)
        check(ex and man["files"].get(rel, {}).get("md5") == U.md5(p), f"{rel} present, md5 as in manifest")
    for rel in need:
        p = os.path.join(A, rel); s = os.path.getsize(p); bs = os.path.getsize(os.path.join(a.base, rel)) if os.path.exists(os.path.join(a.base, rel)) else 0
        check(s <= U.PART_LIMIT, f"{rel}: {s / 1e6:.2f} MB" + (f" (base {bs / 1e6:.2f} MB)" if bs else "") + f" ≤ {U.PART_LIMIT / 1e6:.0f} MB")
    big = [os.path.relpath(os.path.join(d, f), run) for d, _, fs in os.walk(run) for f in fs if os.path.getsize(os.path.join(d, f)) > U.PART_LIMIT]
    check(not big, f"no file of the run over {U.PART_LIMIT / 1e6:.0f} MB" + (f": {big}" if big else ""))
    on_disk = U.aql_part_paths(os.path.join(A, U.F_AQL))
    check([os.path.relpath(p, A) for p in on_disk] == parts, f"buildings layer in {len(parts)} part(s) as the manifest lists, no stray part: "
          + ", ".join(f"{os.path.basename(p)} {os.path.getsize(p) / 1e6:.2f} MB" for p in on_disk))
    print("roads.json")
    R = U.load_json(os.path.join(A, U.F_ROADS)); nn = len(R["nodes"]); E = R["edges"]; prof = R.get("profiles") or []
    check(all(0 <= e["a"] < nn and 0 <= e["b"] < nn for e in E), f"{len(E)} edges reference valid nodes ({nn})")
    check(all(len(e["g"]) >= 4 and len(e["g"]) % 2 == 0 and len(e["y"]) == 4 for e in E), "geometry and 4 years on every edge")
    check(all(e["c"] in ("highway", "ring", "main", "street") for e in E), "old class c on every edge")
    new = [e for e in E if "t" in e]
    check(all(len(e["h"]) * 2 == len(e["g"]) for e in new), f"{len(new)} new edges: one height per vertex")
    check(all(e.get("k", 0) in (0, 1, 2) for e in E), "k in {0,1,2}")
    check(all(0 <= e["p"] < len(prof) for e in E if "p" in e), f"p indexes the {len(prof)} profiles")
    check(all(e["st"][i] in range(6) for e in E if "st" in e for i in range(2, len(e["st"]), 3)), "st codes 0..5")
    gap = max([np.hypot(R["nodes"][e["a"]][0] - e["g"][0], R["nodes"][e["a"]][1] - e["g"][1]) for e in new] +
              [np.hypot(R["nodes"][e["b"]][0] - e["g"][-2], R["nodes"][e["b"]][1] - e["g"][-1]) for e in new] or [0])
    check(gap < 0.6, f"new edges start and end on their nodes (max gap {gap:.2f} m)")
    km = sum(e["len"] for e in E) / 1000; bkm = sum(e["len"] for e in U.load_json(os.path.join(a.base, U.F_ROADS))["edges"]) / 1000
    print(f"  road km {km:,.1f} (base {bkm:,.1f}); by t: " + ", ".join(f"{k} {v / 1000:.1f}" for k, v in sorted(collections.Counter({}).items())))
    tkm = collections.Counter()
    for e in new:
        tkm[e["t"]] += e["len"]
    print("  new edges by type, km: " + ", ".join(f"{k} {v / 1000:.2f}" for k, v in sorted(tkm.items())))
    # connectivity of the ramps to the city
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    G = sp.coo_matrix((np.ones(len(E)), ([e["a"] for e in E], [e["b"] for e in E])), shape=(nn, nn))
    nc, lab = connected_components(G, directed=False)
    big = np.bincount(lab).argmax()
    ramps = [i for i, e in enumerate(E) if e.get("k") == 2 and "t" in e]
    check(all(lab[E[i]["a"]] == big for i in ramps), f"{len(ramps)} new ramp edges are in the main road graph")
    # reconstructions (w43 `ps`): FilmRoads draws each stage's profile from its year, FilmTraffic and the traffic model take its lanes
    npr = len(R.get("profiles") or []); stg = [(i, q) for i, e in enumerate(E) for q in (e.get("ps") or [])]
    sbad = [i for i, q in stg if len(q.get("y") or []) != 4 or not isinstance(q.get("p"), int) or not 0 <= q["p"] < npr]
    check(not sbad, f"ps: {len(stg)} later cross-sections on {len({i for i, _ in stg})} edges, each with 4 years and a profile"
          + (f"; malformed on {sorted(set(sbad))[:8]}" if sbad else ""))
    # structures: clearance where an overpass crosses another road
    over = [e for e in new if "st" in e and 4 in e["st"][2::3]]
    for e in over:
        g = e["g"]; P = [(g[i], g[i + 1]) for i in range(0, len(g), 2)]; L = LineString(P); ch = U.chain(P)
        for f in E:
            if f is e or f.get("k") == 2 and "t" in f:
                continue
            gf = f["g"]; Lf = LineString([(gf[i], gf[i + 1]) for i in range(0, len(gf), 2)])
            X = L.intersection(Lf)
            if X.is_empty or X.geom_type != "Point":
                continue
            t = L.project(X); ye = float(np.interp(t, ch, e["h"]))
            code = next((int(e["st"][k + 2]) for k in range(0, len(e["st"]), 3) if e["st"][k] - 0.5 <= t <= e["st"][k + 1] + 0.5 and e["st"][k + 2] in (3, 4)), 0)
            if "h" in f:
                Pf = [(gf[i], gf[i + 1]) for i in range(0, len(gf), 2)]; yf = float(np.interp(Lf.project(X), U.chain(Pf), f["h"]))
            else:
                yf = float(U.Terrain(a.base).height(X.x, X.y))
            if ye - yf > 2 and not code:
                print(f"  note: {f.get('t', f['c'])} meets the {e.get('t', e['c'])} at ({X.x:.0f}, {X.y:.0f}) {t:.0f} m along it, where it is on an "
                      f"embankment or a landing, not a span: {ye - yf:.1f} m above (a land conflict, no clearance to check)")
            elif ye - yf > 2:
                check(ye - yf >= 5.5 + 1.0, f"overpass over edge ({f.get('t', f['c'])}) at ({X.x:.0f}, {X.y:.0f}): deck {ye:.2f} m, below {yf:.2f} m, "
                      f"clear {ye - yf - 1.5:.2f} m (deck 1.5 m)")
    print("film_roads.json")
    F = U.load_json(os.path.join(A, U.F_FILM))
    if F.get("v") == 2:
        ne = [s for s in F["s"] if s.get("e", -1) >= 0]
        keep = set(man.get("keep_edges") or [])
        cover = [i for s in ne for i in (s.get("es") or [s["e"]])]; newi = [i for i, e in enumerate(E) if "t" in e and i not in keep]
        check(sorted(cover) == newi, f"v2: {len(ne)} strokes cover the {len(newi)} new roads edges once each ({sum(1 for s in ne if s.get('es'))} "
              "streets split by drives carry es; streets of keep quarters left to their own model)")
        if keep:
            kj = set(E[i]["a"] for i in keep) | set(E[i]["b"] for i in keep)
            nkj = sum(1 for i, e in enumerate(E) if i not in keep and "t" in e and (e["a"] in kj or e["b"] in kj))
            check(keep <= set(F["drop"]) and all(lab[E[i]["a"]] == big and lab[E[i]["b"]] == big for i in keep),
                  f"{len(keep)} streets of keep quarters ({sum(E[i]['len'] for i in keep) / 1000:.2f} km): in drop (not drawn by the film), "
                  f"in the main road graph, {nkj} district edges end on them")
        check(all(0 <= s["e"] < len(E) and E[s["e"]]["g"] == s["g"] for s in ne if not s.get("es")), "stroke.e points at the roads edge with the same geometry")

        def pieces_ok(s):
            es = s["es"]; Ls = LineString([(s["g"][i], s["g"][i + 1]) for i in range(0, len(s["g"]), 2)])
            chain = all(E[es[k]]["b"] == E[es[k + 1]]["a"] for k in range(len(es) - 1)) and E[es[0]]["a"] == s["a"] and E[es[-1]]["b"] == s["b"]
            near = all(Ls.distance(LineString([(E[i]["g"][k], E[i]["g"][k + 1]) for k in range(0, len(E[i]["g"]), 2)]).interpolate(f, normalized=True)) < 0.2
                       for i in es for f in (0, 0.5, 1))
            return chain and near and s["e"] == es[0] and abs(sum(U.polyline_len([(E[i]["g"][k], E[i]["g"][k + 1]) for k in range(0, len(E[i]["g"]), 2)])
                                                                  for i in es) - Ls.length) < 1.0
        sp_ = [s for s in ne if s.get("es")]
        check(all(pieces_ok(s) for s in sp_), f"{len(sp_)} split streets: es = the pieces in order from a to b along the stroke, e = es[0]")
        check(all(s["a"] < nn and s["b"] < nn for s in F["s"]), "stroke junction ids are roads nodes or −1")
        check(all(0 <= d < len(E) for d in F["drop"]), "drop indexes roads edges")
        check(len(F["zones"]) <= 32, f"{len(F['zones'])} interchange zones (Unity reads 32)")
        ends = set(v for q in F["s"] for v in (q["a"], q["b"]) if v >= 0)
        check(F.get("sigOn") == 1 and all(0 <= n < nn and n in ends for n in F.get("sig") or []),
              f"sig: {len(F.get('sig') or [])} signalled junctions of the districts, each a stroke end (sigOn 1: fresh junctions without one stay unsignalled)")
        NP = U.load_json(os.path.join(A, U.F_NOPLANT))["polys"]
        rings = [Polygon([(q["p"][k], q["p"][k + 1]) for k in range(0, len(q["p"]), 2)]) for q in NP]
        check(all(r.is_valid and not r.interiors for r in rings), f"noplant.json: {len(rings)} polygons, each one simple ring")
        tree = shapely.STRtree(rings)

        def covered(x, z):
            return len(tree.query(Point(x, z), predicate="within")) > 0
        probe, miss = 0, []
        for q in ne:
            st = q.get("st") or []
            Lq = LineString([(q["g"][i], q["g"][i + 1]) for i in range(0, len(q["g"]), 2)])
            spans = [(st[k], st[k + 1]) for k in range(0, len(st), 3) if st[k + 2] in (1, 3, 4)] + ([(0.0, Lq.length)] if q.get("k") == 2 else [])
            for f0, f1 in spans:
                for t in np.arange(f0 + 1.0, f1 - 1.0, 10.0):
                    if any(st[k] <= t <= st[k + 1] and st[k + 2] == 5 for k in range(0, len(st), 3)):
                        continue                      # a ramp's tunnel: trees may stand above it
                    X = Lq.interpolate(t); probe += 1
                    if not covered(X.x, X.y):
                        miss.append((round(X.x), round(X.y)))
        pads = F.get("pads") or []
        for pd in pads:
            c = Polygon([(pd["p"][k], pd["p"][k + 1]) for k in range(0, len(pd["p"]), 2)]).representative_point(); probe += 1
            if not covered(c.x, c.y):
                miss.append((round(c.x), round(c.y)))
        yards = F.get("yards") or []
        for yd in yards:
            c = Polygon([(yd["p"][k], yd["p"][k + 1]) for k in range(0, len(yd["p"]), 2)]).representative_point(); probe += 1
            if not covered(c.x, c.y):
                miss.append((round(c.x), round(c.y)))
        check(not miss, f"noplant covers the new decks, embankments and ramps (every 10 m), the {len(pads)} pads and the {len(yards)} truck yards: "
              f"{probe} probes" + (f"; not at {miss[:8]}" if miss else ""))
        # the railway of the districts' spec `rail` (rail.json, RailLayer): well formed, and no planting on its tracks or platforms
        RJ = U.load_json(os.path.join(A, U.F_RAIL)); rl = RJ.get("lines") or []; rpl = RJ.get("platforms") or []; lids = {L.get("id") for L in rl}
        rbad = [L.get("id") for L in rl if len(L.get("y") or []) != 4 or not L.get("tracks")
                or any(len(t.get("p") or []) < 6 or len(t["p"]) % 3 for t in L["tracks"])]
        rbad += [P.get("id") for P in rpl if len(P.get("yr") or []) != 4 or len(P.get("p") or []) < 6 or P.get("line") not in lids]
        check(not rbad, f"rail.json: {len(rl)} lines, {sum(len(L.get('tracks') or []) for L in rl)} tracks, {len(rpl)} platforms; 4 years each, "
              f"every platform on a line" + (f"; malformed {rbad}" if rbad else ""))
        rprobe, rmiss = 0, []
        for L in rl:
            for t in L.get("tracks") or []:
                q = t["p"]; Lt = LineString([(q[k], q[k + 1]) for k in range(0, len(q), 3)])
                for d in np.arange(1.0, Lt.length - 1.0, 10.0):
                    X = Lt.interpolate(d); rprobe += 1
                    if not covered(X.x, X.y):
                        rmiss.append((round(X.x), round(X.y)))
        for P in rpl:
            c = Polygon([(P["p"][k], P["p"][k + 1]) for k in range(0, len(P["p"]), 2)]).representative_point(); rprobe += 1
            if not covered(c.x, c.y):
                rmiss.append((round(c.x), round(c.y)))
        check(not rmiss, f"noplant covers the railway tracks (every 10 m) and its platforms: {rprobe} probes" + (f"; not at {rmiss[:8]}" if rmiss else ""))
        check(all(pd.get("pl", 0) in (0, 1, 2) for pd in pads), f"pads: {sum(1 for pd in pads if pd.get('pl') == 1)} on plazas (pl 1), "
              f"{sum(1 for pd in pads if pd.get('pl') == 2)} in paved courts (pl 2), the rest asphalt")
    else:
        print("  film_roads v1 (no districts)")
    dman = man.get("drives") or {}
    # merge's drive edges (driveways.json): the edges of the last `strokes` film strokes (drives follow every street stroke); a run
    # whose manifest predates that count takes them by class
    nds = int(dman.get("strokes") or 0) if "strokes" in dman or not dman else None
    Fs = F.get("s") or []
    drv_set = set(s["e"] for s in Fs[len(Fs) - nds:] if s.get("e", -1) >= 0) if nds else (set() if nds == 0 else
                                                                                           set(i for i, e in enumerate(E) if e.get("t") in U.DRIVES))
    drv = sorted(drv_set)
    if man["districts"]:
        # a spec street (network.json) of a driveway_* class is a spec error, not a drive: drives are driveways.json's only (w44). Its
        # roads edges stay streets in these checks (drives may attach to them); twin_rerun still never routes through them (by class)
        spec_dw = []
        for d in man["districts"]:
            p = os.path.join(a.out, d, "network.json")
            for s in (U.load_json(p).get("segments") or []) if os.path.exists(p) else []:
                if str(s.get("class") or "").startswith("driveway"):
                    spec_dw.append(f"{d}:{s.get('id')} {s.get('class')} {U.polyline_len([(q[0], q[1]) for q in s.get('pts') or []]):.0f} m")
        spec_e = [i for i, e in enumerate(E) if str(e.get("t") or "").startswith("driveway") and i not in drv_set]
        check(not spec_dw and not spec_e, "no spec street of a driveway_* class (network.json); drives are driveways.json's only" if not (spec_dw or spec_e)
              else f"spec error: {len(spec_dw)} spec street(s) of a driveway_* class in network.json ({', '.join(spec_dw[:10])}; roads edges "
                   f"{spec_e[:10]}): a spec street is never a drive (w47 removes these classes); checked as streets here")
    if dman.get("edges") or drv:
        print("Drives")
        carless = [U.carless(e.get("t"), prof[e["p"]] if "p" in e else None) for e in E]
        street = [i not in drv_set and not carless[i] for i, e in enumerate(E)]
        at_street = collections.defaultdict(list)
        for i, e in enumerate(E):
            if street[i]:
                at_street[e["a"]].append(i); at_street[e["b"]].append(i)
        att = dman.get("attach_nodes") or []

        def on_edge(nd, i):
            g = E[i]["g"]; return LineString([(g[k], g[k + 1]) for k in range(0, len(g), 2)]).distance(LineString([R["nodes"][nd], R["nodes"][nd]])) < 0.1
        bad = [nd for nd in att if not any(on_edge(nd, i) for i in at_street.get(nd, []))]
        check((len(att) > 0 or not dman.get("attach")) and not bad, f"{len(att)} attach nodes: each is a node of a street edge with cars, on its line (split there)"
              + (f"; not: {bad[:10]}" if bad else ""))
        dn = set(E[i]["a"] for i in drv) | set(E[i]["b"] for i in drv)
        check(set(att) <= dn, "every attach node is the end of a drive edge")
        ds = [s for s in (Fs[len(Fs) - nds:] if nds else []) if s.get("e", -1) >= 0] if nds is not None else \
            [s for s in Fs if s.get("e", -1) >= 0 and s.get("t") in U.DRIVES]
        atts = set(att)
        check(all(s.get("t") in U.DRIVES for s in ds), f"drive strokes are of a drive class ({', '.join(sorted(U.DRIVES))})")
        check(len(ds) == len(drv) and all((s["a"] == -1) == (E[s["e"]]["a"] in atts) and (s["b"] == -1) == (E[s["e"]]["b"] in atts) for s in ds),
              f"{len(ds)} drive strokes: a / b = −1 exactly at their attach end (no junction patch on the street)")
        pads = F.get("pads") or []
        check(all(p["n"] in dn and len(p["p"]) >= 6 and len(p["p"]) % 2 == 0 and len(p["y"]) == 4 for p in pads), f"{len(pads)} pads at drive ends, each a ring and y[4]")
        check(all(e.get("sv") for e in (E[i] for i in drv) if e.get("sv") is not None), f"{sum(1 for i in drv if E[i].get('sv'))} of {len(drv)} drive edges name the bids they serve (sv)")
        km = sum(E[i]["len"] for i in drv) / 1000
        print(f"  {len(drv)} drive edges, {km:.1f} km, {len(ds)} strokes, {len(pads)} pads; roads.json {os.path.getsize(os.path.join(A, U.F_ROADS)) / 1e6:.2f} MB, "
              f"film_roads.json {os.path.getsize(os.path.join(A, U.F_FILM)) / 1e6:.2f} MB, {len(E)} edges (traffic texture: 131072), {len(F['s'])} strokes")
    print("Buildings")
    rows, cols = U.read_csv_rows(os.path.join(A, U.F_CSV)); n = len(rows)
    xc = ["model", "plinth_m", "dock"]
    check(cols[:len(U.CSV_COLS)] == U.CSV_COLS and (all(c in cols for c in xc) or not man["districts"])
          and not any("," in (r.get(c) or "") for r in rows for c in xc),
          f"buildings.csv: the twin's {len(U.CSV_COLS)} columns first (CityDatabase reads them by index)"
          + (f", then {', '.join(xc)} (AlatauRoofs reads them by name), no comma in a value" if man["districts"] else ""))
    check(all(int(r["bid"]) == i for i, r in enumerate(rows)), f"{n} csv rows, bids 0..n−1 contiguous")
    check(n <= U.BID_LIMIT, f"bids < {U.BID_LIMIT} (the 256 × 512 per-building tables of Unity, BidTable.cs)")
    # every number merge gave lies in a range it may take (city.json#bids): an Overture-only existing house in its district's
    # existing_overture block, a new building in the district's first or second range, a twin building re-extruded its own number
    city = U.load_json(os.path.join(U.SPEC, "city.json")); num = man.get("bid_numbering") or {}
    ov, own = set(num.get("overture") or []), set(num.get("own") or [])
    nbase = len(U.read_csv_rows(os.path.join(a.base, U.F_CSV))[0])
    bad, wrong_src = [], []
    for d, bid_id, bid in man["bids"]:
        if bid in own:
            allowed = [(bid, bid)] if bid < nbase else []
        elif bid in ov:
            allowed = [r for r in [U.overture_range(city, d)] if r]
        else:
            allowed = U.district_ranges(city, d)
        if not any(lo <= bid <= hi for lo, hi in allowed):
            bad.append((d, bid_id, bid))
        if (bid in ov) != (rows[bid]["source"] == "existing_osm") and bid not in own:
            wrong_src.append((d, bid_id, bid, rows[bid]["source"]))
    n_ov = sum(1 for x in man["bids"] if x[2] in ov); n_r2 = sum(1 for d, _, b in man["bids"] if b not in ov and b not in own and len(U.district_ranges(city, d)) > 1
                                                             and U.district_ranges(city, d)[1][0] <= b <= U.district_ranges(city, d)[1][1])
    check(not bad, f"{len(man['bids'])} numbered buildings each in its allowed ranges ({n_ov} Overture-only houses in existing_overture, "
          f"{n_r2} new in a second range, {len(own)} own numbers)" + (f"; not: {bad[:10]}" if bad else ""))
    check(not wrong_src, "Overture-range numbers are exactly the existing_osm rows merge numbered" + (f"; not: {wrong_src[:10]}" if wrong_src else ""))
    live_new = [i for i in range(nbase, n) if rows[i]["kind"] != "removed"]
    check(set(live_new) <= set(x[2] for x in man["bids"]), f"every live row past the base ({len(live_new)}) is a numbered building of the merge")
    pbids = [set(int(b) for o in U.read_aql(p) for b in np.unique(o[6])) for p in on_disk]
    check(all(not (pbids[i] & pbids[j]) for i in range(len(pbids)) for j in range(i)), "no building in two parts")
    objs = U.read_aql_parts(os.path.join(A, U.F_AQL))
    mb = set(int(b) for o in objs for b in np.unique(o[6]))
    rem = set(i for i, r in enumerate(rows) if r["kind"] == "removed")
    check(not (mb & rem), f"no mesh for the {len(rem)} removed placeholders")
    sm = man.get("solar_moved"); sol = set(i for i, r in enumerate(rows) if r["kind"] == "solar")
    if sm:
        check(not (mb & sol), f"solar moved: none of the {len(sol)} solar rows has a mesh ({sm['triangles']} triangles moved into {sm['fields']} fields)")
        S = U.load_json(os.path.join(A, U.F_SOLAR))
        check(len(S["f"]) >= sm["fields"] and all(len(f["y"]) == 4 and len(f["p"]) >= 6 and len(f["p"]) % 2 == 0 for f in S["f"]),
              f"solar.json: {len(S['f'])} fields, each y[4] and a ring")
    base_rows, _ = U.read_csv_rows(os.path.join(a.base, U.F_CSV)); base_objs = U.read_aql_parts(os.path.join(a.base, U.F_AQL))
    base_mb = set(int(b) for o in base_objs for b in np.unique(o[6]))
    lot = [i for i, r in enumerate(rows) if r["kind"] == "landmark_lot"]
    missing = [i for i in range(n) if i not in rem and i not in mb and (i >= len(base_rows) or i in base_mb) and not (sm and i in sol)
               and rows[i]["kind"] != "landmark_lot"]
    check(not missing, f"every building row that had a mesh still has one ({len(missing)} missing" + (", solar rows excepted)" if sm else ")"))
    if not man["districts"]:
        # the round trip: the layer (all parts together) has every triangle of the base, less the solar panels when they moved
        def tri_rows(ob, skip):
            out = []
            for o in ob:
                k = ~np.isin(o[6], list(skip)) if skip else np.ones(len(o[6]), bool)
                P = o[2][o[3][k]].reshape(-1, 9); out.append(np.concatenate([P, o[4][k, None], o[5][k, None], o[6][k, None]], 1))
            M = np.concatenate(out); return M[np.lexsort(M.T[::-1])]
        check(np.array_equal(tri_rows(objs, None), tri_rows(base_objs, sol if sm else None)),
              "round trip: the parts together hold exactly the base triangles" + (" less the solar panels" if sm else ""))
    B = U.read_bounds(os.path.join(A, U.F_BOUNDS))
    check(len(B) == n, f"bid_bounds has {len(B)} entries")
    if lot or man["districts"]:
        caps = {}
        for d in man["districts"]:
            p = os.path.join(a.out, d, "lots.json")
            for L in (U.load_json(p).get("lots") or []) if os.path.exists(p) else []:
                if L.get("use") == "landmark":
                    caps[L["id"]] = L.get("capacity") or {}
        per = {"housing": ("homes", 75.0), "business": ("jobs", 90.0)}
        ok_lot = all(not (set([i]) & mb) and not any(B[i]) and rows[i]["use"] in per and rows[i]["parcel"] in caps
                     and abs(float(rows[i]["gfa_m2"]) - int(caps[rows[i]["parcel"]].get(per[rows[i]["use"]][0]) or 0) * per[rows[i]["use"]][1]) < 1.0
                     for i in lot)
        check(ok_lot, f"{len(lot)} mesh-less landmark_lot rows (a landmark lot's own homes × 75 m² housing, jobs × 90 m² business): no mesh, "
              f"an empty box, parcel = the lot (" + ", ".join(f"{rows[i]['parcel']} {rows[i]['use']} {float(rows[i]['gfa_m2']):.0f} m²" for i in lot[:4]) + ")")
    if man["districts"]:
        # gen_buildings' fields (w44): a plinth's walls reach down to plinth_m under the floor, a shed's dock side and doors in `dock`,
        # its truck yard in film_roads yards, a canopy drawn as a roof slab on posts
        bm = {(d, i): b for d, i, b in man["bids"]}; pl, dk, cn, nty = [], [], [], 0
        for d in man["districts"]:
            p = os.path.join(a.out, d, "buildings.json")
            for b in (U.load_json(p).get("buildings") or []) if os.path.exists(p) else []:
                bid = bm.get((d, b.get("id")))
                if bid is None or bid >= n:
                    continue
                if b.get("plinth"):
                    pl.append((b, bid))
                if b.get("dock_side") and b.get("docks"):
                    dk.append((b, bid))
                if (b.get("model") or "") == "bus_canopy":
                    cn.append((b, bid))
                nty += bool(b.get("truck_yard"))
        want = np.array(sorted(set(bid for _, bid in pl + cn)), np.int64); mv = collections.defaultdict(list)
        for o in objs if len(want) else []:
            k = np.isin(o[6], want)
            for b in np.unique(o[6][k]):
                mv[int(b)].append(o[2][o[3][o[6] == b].ravel()])
        mv = {b: np.concatenate(v) for b, v in mv.items()}

        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return float("nan")
        bad = [b["id"] for b, bid in pl if not (num(rows[bid]["plinth_m"]) >= float(b["plinth"].get("h_m") or 0) - 0.02) or bid not in mv
               or mv[bid][:, 1].min() > float(rows[bid]["ground_m"]) - num(rows[bid]["plinth_m"]) - 0.2]
        npm = sum(1 for r in rows if r.get("plinth_m"))
        check(not bad and npm == len(pl), f"{len(pl)} plinths (gen_buildings `plinth`): plinth_m ≥ plinth.h_m and the walls reach plinth_m under ground_m"
              + (f" (" + ", ".join(f"{b['id']} {rows[bid]['plinth_m']} m" for b, bid in sorted(pl, key=lambda x: -num(rows[x[1]]["plinth_m"]))[:4]) + ")" if pl else "")
              + f"; {npm} rows carry plinth_m" + (f"; not: {bad[:8]}" if bad else ""))
        bad = []
        for b, bid in dk:
            t = (rows[bid].get("dock") or "").split(); (x0, z0), (x1, z1) = b["dock_side"][0], b["dock_side"][-1]
            ring = Polygon(b["footprint"]).exterior
            if not (len(t) == 5 and int(t[4]) == int(b["docks"]) and max(abs(num(t[0]) - x0), abs(num(t[1]) - z0), abs(num(t[2]) - x1), abs(num(t[3]) - z1)) < 0.01
                    and all(ring.distance(Point(x, z)) < 0.5 for x, z in ((x0, z0), (x1, z1), ((x0 + x1) / 2, (z0 + z1) / 2)))):
                bad.append(b["id"])
        ndk = sum(1 for r in rows if r.get("dock"))
        check(not bad and ndk == len(dk), f"{len(dk)} sheds with docks: dock = \"x0 z0 x1 z1 n\" (dock_side on the footprint's outline, n = docks"
              + (", " + ", ".join(f"{b['id']} {b['docks']} doors" for b, _ in dk[:4]) if dk else "") + f"); {ndk} rows carry dock" + (f"; not: {bad[:8]}" if bad else ""))
        yards = F.get("yards") or []
        check(len(yards) >= nty and all(len(yd["p"]) >= 6 and len(yd["p"]) % 2 == 0 and len(yd["y"]) == 4 and 0 <= yd["b"] < n for yd in yards),
              f"film_roads yards: {len(yards)} rings for the {nty} truck yards, each a ring, y[4] and its shed's bid")
        bad, posts = [], []
        for b, bid in cn:
            v = mv.get(bid); top = float(rows[bid]["ground_m"]) + float(rows[bid]["height_m"])
            low = v[v[:, 1] < top - 0.6] if v is not None else np.zeros((0, 3))
            cs = []
            for x, _, z in low:
                for c in cs:
                    if abs(c[0] - x) < 0.5 and abs(c[1] - z) < 0.5:
                        break
                else:
                    cs.append((x, z))
            if v is None or not cs or not all(min(max(abs(c[0] - x), abs(c[1] - z)) for c in cs) < 0.5 for x, _, z in low):
                bad.append(b["id"])
            posts.append((b["id"], len(cs)))
        check(not bad, f"{len(cn)} canopies drawn as a roof slab on posts (" + ", ".join(f"{i} {k} posts" for i, k in posts[:6]) + ")"
              + (f"; not: {bad}" if bad else ""))
    bad = 0; cnb = set(i for i, r in enumerate(rows) if r.get("model") == "bus_canopy")
    for o in objs:
        V, T, bid = o[2], o[3], o[6]
        for b in np.unique(bid):
            if b < len(base_rows) and int(b) not in man.get("removed_bids", []) and b not in [x[2] for x in man["bids"]]:
                continue
            vs = V[T[bid == b].ravel()]
            x0, z0, x1, z1 = B[b]
            if not (abs(vs[:, 0].min() - x0) < 0.5 and abs(vs[:, 2].max() - z1) < 0.5):
                bad += 1
            # winding: roofs up (a canopy's soffit faces down)
            tri = T[bid == b]; nrm = np.cross(V[tri[:, 1]] - V[tri[:, 0]], V[tri[:, 2]] - V[tri[:, 0]])
            if (nrm[:, 1] < -1e-3).any() and int(b) not in cnb:
                bad += 1
    check(bad == 0, "new meshes: bounds match, no face points down" + (f" (but the {len(cnb)} canopies' soffits)" if cnb else ""))
    hid = U.read_hide(os.path.join(A, U.F_HIDE)); mo = U.load_json(os.path.join(A, U.F_ORDER))
    check(all(0 <= b < n and b not in rem for b, _ in hid) and all(0 <= b < n and b not in rem for b in mo["b"]), "hide lists reference live bids")
    print("Per-bid arrays")
    T = os.path.join(A, "StreamingAssets/twin")
    con = U.load_json(os.path.join(T, "construction.json")); risk = U.load_json(os.path.join(T, "risk.json"))
    check(all(len(v) == n for v in con["per_building"].values()), "construction per_building covers every bid")
    check(all(len(v["depth_cm"]) == n for v in risk["scenarios"].values()), "risk depth_cm covers every bid")
    print("Traffic on the new ramps (base scenario, v/c ×100)")
    tr = U.load_json(os.path.join(T, "traffic.json"))
    check(all(len(tr["by_scenario"][s][y]["vc"]) == len(E) for s in tr["by_scenario"] for y in tr["by_scenario"][s]), "vc arrays match roads edges")
    if ramps:
        for y in ("2035", "2050"):
            vc = tr["by_scenario"]["base"][y]["vc"]
            print(f"  {y}: " + ", ".join(f"e{i}={vc[i]}" for i in ramps))
        check(any(tr["by_scenario"]["base"]["2050"]["vc"][i] > 0 for i in ramps), "the traffic model sends cars over the new ramps")
    if new:
        zero_report(E, prof, tr, drives=drv_set)
    print("validate_twin.py")
    r = subprocess.run([sys.executable, os.path.join(U.TWIN_GEN, "validate_twin.py"), os.path.join(A, U.F_CSV), T], capture_output=True, text=True, cwd=U.TWIN_GEN)
    print("  " + "\n  ".join(l for l in r.stdout.splitlines() if "FAIL" in l or "RESULT" in l))
    check(r.returncode == 0, "validate_twin.py green")
    print("RESULT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
