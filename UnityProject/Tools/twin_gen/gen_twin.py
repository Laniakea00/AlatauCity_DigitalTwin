"""Alatau City digital twin — synthetic data generator (stage 3).
Deterministic (seed 2050). Inputs: buildings.csv (Unity CityData), blend_geo.json (centre-lines + named sites), roads.pkl.
Outputs: Assets/StreamingAssets/twin/*.json. Run: python3 gen_twin.py <buildings.csv> <blend_geo.json> <roads.pkl> <out dir>"""
import sys, json, math, pickle, collections, hashlib
import numpy as np
import networkx as nx
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.cluster.vq import kmeans2
from twin_common import *
import norms as N

rng = np.random.default_rng(SEED)
CATS = ["housing", "business", "social", "industry", "leisure"]   # same order as CityStats.CatKeys
CELL = 1000.0


def h01(*parts):
    """Stable pseudo-random 0..1 from a key (independent of call order)."""
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


# ----------------------------------------------------------------------------------------------- demand
def per_building_loads(b):
    """Loads of one building when completed (all at the design condition)."""
    u, g = b["use"], b["gfa"]
    if b["source"] == "existing_osm" or u not in N.ELEC_W_M2: return None
    res = g / N.M2_PER_RESIDENT if u == "housing" else 0.0
    jobs = g / N.M2_PER_JOB[u] if u in N.M2_PER_JOB else 0.0
    water = res * (N.WATER_L_RES + N.WATER_L_IRR) + jobs * N.WATER_L_JOB
    if u == "leisure": water += g / N.M2_PER_BED * N.WATER_L_BED
    if u == "industry": water += g * N.WATER_L_M2_IND
    water /= 1000.0                                                   # m³/day average
    irr = res * N.WATER_L_IRR / 1000.0
    heat = g / 1000.0 * N.HEAT_GCAL_1000M2[u]
    return {"res": res, "jobs": jobs, "power": g * N.ELEC_W_M2[u] / 1e6, "water": water * N.K_MAX_DAY,
            "sewer": (water - irr) * N.SEWER_SHARE * N.K_MAX_DAY, "heat": heat, "gas": heat * N.GAS_M3H_PER_GCALH, "gfa": g}


LOAD_KEYS = ["res", "jobs", "power", "water", "sewer", "heat", "gas", "gfa"]


def demand_cells(B):
    """Grid cells (1 km) with yearly cumulative loads per scenario: cells[key] -> {x, z, d, loads[s][k][yi]}."""
    cells = {}
    for b in B:
        L = per_building_loads(b)
        if L is None or b["d"] < 0: continue
        key = (int(b["x"] // CELL), int(b["z"] // CELL))
        c = cells.get(key)
        if c is None:
            c = cells[key] = {"x": 0.0, "z": 0.0, "w": 0.0, "dw": np.zeros(4), "add": {s: np.zeros((len(LOAD_KEYS), NY + 1)) for s in SCENARIOS}}
        w = max(b["gfa"], 1.0); c["x"] += b["x"] * w; c["z"] += b["z"] * w; c["w"] += w; c["dw"][b["d"]] += w
        for s in SCENARIOS:
            e = b["eff"][s]; i = NY if e > Y1 else yi(e)
            c["add"][s][:, i] += [L[k] for k in LOAD_KEYS]
    out = []
    for key, c in cells.items():
        cum = {s: np.cumsum(c["add"][s][:, :NY], axis=1) for s in SCENARIOS}
        kg = LOAD_KEYS.index("gfa")
        first = {s: next((YEARS[i] for i in range(NY) if cum[s][kg, i] > 0.1 * max(cum[s][kg, -1], 1e-9)), None) for s in SCENARIOS}
        out.append({"key": key, "x": c["x"] / c["w"], "z": c["z"] / c["w"], "d": int(np.argmax(c["dw"])), "cum": cum, "first": first})
    return out


def district_series(B):
    """[scenario][district][cat][year] cumulative GFA + loads per district (the same numbers CityStats shows in Unity)."""
    res = {}
    for s in SCENARIOS:
        gfa = np.zeros((4, len(CATS), NY)); L = np.zeros((4, len(LOAD_KEYS), NY))
        for b in B:
            if b["d"] < 0 or b["use"] not in CATS: continue
            e = b["eff"][s]
            if e > Y1: continue
            i = yi(e); gfa[b["d"], CATS.index(b["use"]), i:] += b["gfa"]
            l = per_building_loads(b)
            if l: L[b["d"], :, i:] += np.array([l[k] for k in LOAD_KEYS])[:, None]
        res[s] = {"gfa": gfa, "loads": L}
    return res


# ----------------------------------------------------------------------------------------------- facilities
def named(geo, prefix):
    return [p for p in geo["points"] if p["text"].split("\n")[0].startswith(prefix)]


def nearest_district(x, z, Bxy, Bd):
    _, i = Bxy.query([x, z]); return int(Bd[i])


HEADROOM = {"power_hv": 0.0, "power": 0.3, "heat": 0.3, "sewer": 0.3, "water": 0.3, "gas": 0.3}   # share of one stage available before the first new stage: existing networks + temporary connections


def need_years(series, unit, head, reserve=N.RESERVE):
    """Base commissioning year of each stage: one year before reserve-adjusted demand exceeds the capacity without it."""
    peak = float(np.max(series)); K = max(0, math.ceil((peak * reserve - head) / unit))
    return [next((YEARS[i] for i in range(NY) if series[i] * reserve > head + k * unit), Y1) - 1 for k in range(K)]


def scenario_years(base_years, delays):
    out = {}
    for s in SCENARIOS:
        ys = []
        for k, y in enumerate(base_years):
            dl = delays.get(k, 0)
            y2 = y - 2 if s == "infra" else y - 1 + dl // 2 if s == "fast" else y + 1 + dl if s == "slow" else y + dl
            ys.append(int(min(max(y2, 2026), 2060)))
        out[s] = ys
    return out


def capacity_series(stage_years, unit, head=0.0):
    return [r1(head + sum(unit for y in stage_years if y <= Y)) for Y in YEARS]


def build_facilities(geo, B, cells, roads_xy):
    Bxy = cKDTree(np.array([[b["x"], b["z"]] for b in B if b["d"] >= 0]))
    Bd = np.array([b["d"] for b in B if b["d"] >= 0])
    F = []

    def add(fid, name, kind, res, x, z, unit, synthetic, note=""):
        F.append({"id": fid, "name": name, "kind": kind, "res": res, "x": round(x), "z": round(z), "unit": unit,
                  "district": nearest_district(x, z, Bxy, Bd), "synthetic": synthetic, "note": note})

    # --- from the master plan (named sites)
    for p in named(geo, "ВЗУ"):
        n = p["text"].split("\n")[0]; add("wi_" + n[-1], n + " (водозабор)", "water_intake", "water", p["x"], p["z"], N.UNIT["water"], False, p["text"].split("\n")[-1])
    for p in named(geo, "Канализационное"):
        n = p["text"].split("\n")[0]; num = n.split("№")[-1]
        add("ww_" + num, "КОС №" + num, "wastewater", "sewer", p["x"], p["z"], N.UNIT["sewer"], False, p["text"].split("\n")[-1])
    # --- synthetic: substations, boiler houses, AGRS — placed at load centres of their district
    pts = np.array([[c["x"], c["z"]] for c in cells]); dist_of = np.array([c["d"] for c in cells])
    w2050 = {r: np.array([c["cum"]["base"][LOAD_KEYS.index(r), -1] for c in cells]) for r in ("power", "heat")}
    names_ps = {0: "Gate", 1: "Golden", 2: "Growing", 3: "Green"}
    for res, unit, per, kind, label in (("power", N.UNIT["power"], 2, "substation", "ПС 110/10 кВ"), ("heat", N.UNIT["heat"], 2, "boiler", "Котельная")):
        for d in range(4):
            m = dist_of == d; tot = w2050[res][m].sum()
            k = max(1, math.ceil(tot * N.RESERVE / (unit * per)))
            P = pts[m]; W = w2050[res][m]
            rep = np.repeat(P, np.maximum(1, (W / max(W.max(), 1e-9) * 20).astype(int)), axis=0)
            np.random.seed(SEED + d)
            cent, lab = kmeans2(rep, k, seed=SEED + d, minit="++")
            dcells = [cc for cc, mm in zip(cells, m) if mm]
            near_c = np.argmin(np.linalg.norm(P[:, None, :] - cent[None, :, :], axis=2), axis=1)
            firsts = [min([(dcells[i]["first"]["base"] or 2099) for i in range(len(dcells)) if near_c[i] == ci] or [2099]) for ci in range(k)]
            order = np.argsort(firsts, kind="stable")
            for j, ci in enumerate(order):
                x, z = cent[ci]
                _, ri = roads_xy.query([x, z]); x, z = roads_xy.data[ri]
                add(f"{'ps' if res == 'power' else 'hb'}_{names_ps[d].lower()}_{j + 1}", f"{label} «{names_ps[d]}-{j + 1}»", kind, res, x + 60, z + 60, unit, True)
    # 220/110 kV feeding substations: one per district, at the GFA-weighted centre (snapped to a road)
    for d in range(4):
        m = dist_of == d; P = pts[m]; W = w2050["power"][m]
        x, z = (P * W[:, None]).sum(0) / max(W.sum(), 1e-9)
        _, ri = roads_xy.query([x + 900, z]); x, z = roads_xy.data[ri]
        add(f"hv_{names_ps[d].lower()}", f"ПС 220/110 кВ «{names_ps[d]}»", "substation_hv", "power_hv", x + 80, z - 80, N.UNIT["power_hv"], True,
            "питающий центр района; связь с сетью 220 кВ KEGOC — модель")
    # AGRS: south edge of the city next to the Almaty–Konaev highway (gas comes from the Almaty side)
    gate = [b for b in B if b["d"] == 0]
    zmin = min(b["z"] for b in gate); xs = np.median([b["x"] for b in gate if b["z"] < zmin + 3000])
    _, ri = roads_xy.query([xs + 1500, zmin + 800]); x, z = roads_xy.data[ri]
    add("agrs_1", "АГРС «Алатау»", "agrs", "gas", x + 80, z, N.UNIT["gas"], True, "газопровод с АГРС — 2-й этап 2028–2030 (kapital.kz)")
    # renewables (energy, not firm capacity) from the master plan
    ren = {"СЭС \"Каскелен\"": (55, 2028), "СЭС": (320, 2033), "ВИЭ": (200, 2038)}
    for p in geo["points"]:
        n = p["text"].split("\n")[0]
        if n in ren:
            mw, y = ren[n]
            F.append({"id": "re_" + str(len(F)), "name": n.replace('"', "«", 1).replace('"', "»") + f" · {mw} МВт", "kind": "renewable", "res": "renewable",
                      "x": round(p["x"]), "z": round(p["z"]), "unit": mw, "district": nearest_district(p["x"], p["z"], Bxy, Bd), "synthetic": False,
                      "note": p["text"].split("\n")[-1] + " по генплану; мощность — модель (~0,5 МВт/га)", "year": y})
    return F


def assign_service(F, cells):
    """Each cell is served by the nearest facility of each network (power/heat: only within its district)."""
    serve = {}
    for res in ("water", "sewer", "power", "heat", "gas", "power_hv"):
        fac = [f for f in F if f["res"] == res]
        for ci, c in enumerate(cells):
            cand = [f for f in fac if res in ("water", "sewer", "gas") or f["district"] == c["d"]] or fac
            best = min(cand, key=lambda f: (f["x"] - c["x"]) ** 2 + (f["z"] - c["z"]) ** 2)
            serve[(res, ci)] = best["id"]
    return serve


# designed delays of the base plan: (resource, district or None, window of base years, delay) — the twin must reveal them
DESIGNED_DELAYS = [("power_hv", 1, (2030, 2036), 3), ("heat", 2, (2034, 2040), 3), ("sewer", None, (2035, 2042), 3)]
POOLED = ("water", "gas")


def plan_all(F, cells, serve):
    """Stage plan of every facility. water/gas are pooled city systems (stages shared round-robin between intakes / AGRS);
    power, heat, sewer are local (substation / boiler-house / treatment-plant service areas)."""
    systems = {}
    for f in F:
        if f["res"] == "renewable":
            y = f.pop("year"); f["stages"] = {s: [y - 2 if s == "infra" else y + 2 if s == "slow" else y] for s in SCENARIOS}
            f["head"] = 0.0; f["demand"] = None; f["base_years"] = None
    for res in ("water", "sewer", "power", "heat", "gas", "power_hv"):
        fac = sorted([f for f in F if f["res"] == res], key=lambda f: f["id"]); k = LOAD_KEYS.index("power" if res == "power_hv" else res)
        if res in POOLED:
            dem = {s: np.sum([c["cum"][s][k] for c in cells], axis=0) for s in SCENARIOS}
            head = HEADROOM[res] * fac[0]["unit"]
            yrs = need_years(dem["base"], fac[0]["unit"], head, 1.05)
            for f in fac: f["base_years"] = []; f["head"] = head / len(fac)
            for i, y in enumerate(yrs): fac[i % len(fac)]["base_years"].append(y)
            share = {f["id"]: max(1, len(f["base_years"])) for f in fac}; tot = sum(share.values())
            for f in fac: f["demand_arr"] = {s: dem[s] * share[f["id"]] / tot for s in SCENARIOS}
            systems[res] = {"demand": dem, "fac": [f["id"] for f in fac]}
        else:
            for f in fac:
                ci = [i for i in range(len(cells)) if serve[(res, i)] == f["id"]]
                f["demand_arr"] = {s: np.sum([cells[i]["cum"][s][k] for i in ci], axis=0) if ci else np.zeros(NY) for s in SCENARIOS}
                f["head"] = HEADROOM[res] * f["unit"]
                f["base_years"] = need_years(f["demand_arr"]["base"], f["unit"], f["head"], 1.05 if res in ("power_hv", "sewer") else N.RESERVE)
    # designed delays: pick the stage whose delay creates the most visible deficit
    def deficit(res, fac_list, years_of):
        if res in POOLED:
            d = systems[res]["demand"]["base"]; head = sum(f["head"] for f in fac_list)
            cap = np.array([head + sum(f["unit"] for f in fac_list for y in years_of(f) if y <= Y) for Y in YEARS]); return float(np.max(d - cap))
        return max(float(np.max(f["demand_arr"]["base"] - np.array(capacity_series(years_of(f), f["unit"], f["head"])))) for f in fac_list)
    for f in F: f["delays"] = {}
    for res, dist, (w0, w1), dl in DESIGNED_DELAYS:
        fac = [f for f in F if f["res"] == res and (dist is None or f["district"] == dist)]
        best = None
        for f in fac:
            for kk, y in enumerate(f["base_years"]):
                if not (w0 <= y <= w1): continue
                yo = lambda g, f=f, kk=kk: [yy + (dl if (g is f and j == kk) else 0) for j, yy in enumerate(g["base_years"])]
                v = deficit(res, [g for g in F if g["res"] == res] if res in POOLED else [f], yo)
                if best is None or v > best[0]: best = (v, f, kk)
        if best: best[1]["delays"][best[2]] = dl; print(f"  designed delay: {res} {best[1]['name']} stage {best[2] + 1} +{dl} y -> deficit {best[0]:.0f}")
    for f in F:
        if f["res"] in ("water", "sewer", "power", "heat", "gas", "power_hv"):
            f["stages"] = scenario_years(f["base_years"], f["delays"])
            f["demand"] = {s: [r1(v) for v in f["demand_arr"][s]] for s in SCENARIOS}
    return systems


# ----------------------------------------------------------------------------------------------- roads and networks
def road_tables(H):
    nodes = list(H.nodes); idx = {n: i for i, n in enumerate(nodes)}
    edges = []
    for a, b, d in H.edges(data=True):
        edges.append({"a": idx[a], "b": idx[b], "cls": d["cls"], "len": d["length"], "geom": d["geom"]})
    return nodes, idx, edges


def road_years(edges, B):
    """Year a road edge opens, per scenario: existing OSM roads 2025; planned streets one year before the first building within 350 m."""
    pts = np.array([[b["x"], b["z"]] for b in B if b["source"] != "existing_osm"])
    eff = {s: np.array([b["eff"][s] for b in B if b["source"] != "existing_osm"]) for s in SCENARIOS}
    kd = cKDTree(pts)
    for e in edges:
        if e["cls"] != "street": e["year"] = {s: 2025 for s in SCENARIOS}; continue
        g = np.array(e["geom"], float); probe = g[[0, len(g) // 2, -1]]
        near = set()
        for p in probe: near.update(kd.query_ball_point(p, 350.0))
        e["year"] = {}
        for s in SCENARIOS:
            if not near: e["year"][s] = 2099; continue
            ys = eff[s][list(near)]; ys = ys[ys <= Y1]
            if len(ys) == 0: e["year"][s] = 2099; continue
            y = int(np.percentile(ys, 20, method="lower"))      # the street opens when its block really starts, not for one early house
            e["year"][s] = 2025 if y <= 2026 else y - 1         # ≤ 2026: serves today's settlements


def graph_csr(nodes, edges, weight):
    n = len(nodes); rows, cols, w = [], [], []
    for i, e in enumerate(edges):
        rows += [e["a"], e["b"]]; cols += [e["b"], e["a"]]; w += [weight(i, e)] * 2
    return csr_matrix((w, (rows, cols)), shape=(n, n))


def networks(F, cells, serve, nodes, edges, kd_nodes):
    """Trunk networks laid along streets: shortest-path tree from each facility to the cells it serves."""
    edge_of = {}
    for i, e in enumerate(edges): edge_of[(e["a"], e["b"])] = i; edge_of[(e["b"], e["a"])] = i
    G = graph_csr(nodes, edges, lambda i, e: e["len"] * (0.8 if e["cls"] == "street" else 1.0))
    cell_node = [int(kd_nodes.query([c["x"], c["z"]])[1]) for c in cells]
    nets = {}
    res_list = ["water", "sewer", "power", "heat", "gas", "telecom"]
    # telecom: fibre ring from a data centre in Gate (synthetic) to every cell
    gate_cells = [c for c in cells if c["d"] == 0]
    dc = min(gate_cells, key=lambda c: c["first"]["base"] or 2099)
    _, dcn = kd_nodes.query([dc["x"], dc["z"]])
    F.append({"id": "dc_1", "name": "ЦОД «Alatau Data Hub»", "kind": "datacenter", "res": "telecom", "x": round(nodes[dcn][0] + 70), "z": round(nodes[dcn][1] + 70),
              "unit": 0, "district": 0, "synthetic": True, "note": "модель", "stages": {s: [2027] for s in SCENARIOS}, "demand": None, "head": 0.0, "delays": {}})
    for res in res_list:
        fac = [f for f in F if f["res"] == res]
        seg = {}   # edge index -> {"year": {s: y}, "load": base 2050 downstream load, "fac": id}
        k = LOAD_KEYS.index(res) if res in LOAD_KEYS else LOAD_KEYS.index("gfa")
        for f in fac:
            _, src = kd_nodes.query([f["x"], f["z"]])
            served = [i for i in range(len(cells)) if (res == "telecom" or serve[(res, i)] == f["id"])]
            if not served: continue
            dist, pred = dijkstra(G, directed=False, indices=int(src), return_predecessors=True)
            for ci in served:
                c = cells[ci]; t = cell_node[ci]
                if not np.isfinite(dist[t]): continue
                load = float(c["cum"]["base"][k, -1])
                v = t
                while v != src and v >= 0:
                    u = pred[v]
                    if u < 0: break
                    ei = edge_of[(u, v)]
                    sg = seg.setdefault(ei, {"year": {s: 2099 for s in SCENARIOS}, "load": 0.0, "fac": f["id"]})
                    sg["load"] += load
                    for s in SCENARIOS:
                        fy = c["first"][s]
                        if fy is not None and fy <= Y1: sg["year"][s] = min(sg["year"][s], 2025 if fy <= 2026 else fy - 1)
                    v = u
        nets[res] = seg
    return nets


DN = [100, 150, 200, 250, 300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1400]


def pipe_size(res, load):
    if res in ("water", "sewer"):
        q = load / 86400.0; v = 1.0 if res == "water" else 0.8
        d = math.sqrt(4 * q / (math.pi * v)) * 1000; return next((x for x in DN if x >= d), DN[-1])
    if res == "heat":
        q = load * 1e6 / (1000 * 4.19 * 40) / 3600; d = math.sqrt(4 * q / (math.pi * 1.5)) * 1000   # ΔT 40 K, 1.5 m/s
        return next((x for x in DN if x >= d), DN[-1])
    if res == "gas":
        q = load / 3600 / 6.0; d = math.sqrt(4 * q / (math.pi * 15)) * 1000   # medium pressure ~0.6 MPa, 15 m/s
        return next((x for x in DN if x >= d), DN[-1])
    return 0


# ----------------------------------------------------------------------------------------------- traffic
try:
    from numba import njit
except ImportError:                       # pure-python fallback (slow, same result)
    def njit(*a, **k): return (lambda f: f) if not a or not callable(a[0]) else a[0]


@njit(cache=True)
def _push_tree(pred, dist, demand, adj_ptr, adj_nbr, adj_eid, flow):
    """Load one shortest-path tree: demand sits at destination nodes; push it back to the source along predecessors."""
    order = np.argsort(-dist)
    f = demand.copy()
    for v in order:
        if f[v] <= 0 or not np.isfinite(dist[v]): continue
        u = pred[v]
        if u < 0: continue
        for k in range(adj_ptr[v], adj_ptr[v + 1]):
            if adj_nbr[k] == u:
                flow[adj_eid[k]] += f[v]; break
        f[u] += f[v]


def traffic(nodes, edges, cells, kd_nodes, lrt, scen_years=(2030, 2035, 2040, 2045, 2050)):
    """AM peak hour. Origins/destinations = 1 km demand cells (each loads onto its nearest street node), gravity distribution
    over jobs, 15-45 % to Almaty / Konaev, incremental assignment in 3 slices with BPR. Delay is reported with v/c capped at 1.6
    (beyond that the peak spreads over a longer period rather than the queue growing without bound)."""
    cap = []; t0 = []
    from gen_roads import CLASSES
    for e in edges:
        lanes, c, v = CLASSES[e["cls"]]; cap.append(lanes * c); t0.append(e["len"] / 1000 / v * 60)   # minutes
    cap = np.array(cap, float); t0 = np.maximum(np.array(t0), 0.01)
    hw = [i for i, e in enumerate(edges) if e["cls"] == "highway"]
    hw_nodes = set([edges[i]["a"] for i in hw] + [edges[i]["b"] for i in hw])
    almaty = min(hw_nodes, key=lambda n: nodes[n][1]); konaev = max(hw_nodes, key=lambda n: nodes[n][1])
    n = len(nodes)
    # adjacency (node -> neighbour, edge id) for the tree push
    deg = np.zeros(n + 1, np.int64)
    for e in edges: deg[e["a"] + 1] += 1; deg[e["b"] + 1] += 1
    adj_ptr = np.cumsum(deg); fill = adj_ptr[:-1].copy()
    adj_nbr = np.zeros(2 * len(edges), np.int64); adj_eid = np.zeros(2 * len(edges), np.int64)
    for i, e in enumerate(edges):
        for p, q in ((e["a"], e["b"]), (e["b"], e["a"])):
            adj_nbr[fill[p]] = q; adj_eid[fill[p]] = i; fill[p] += 1
    cxy = np.array([[c["x"], c["z"]] for c in cells])
    cnode = np.array([kd_nodes.query(p)[1] for p in cxy])
    D = np.linalg.norm(cxy[:, None, :] - cxy[None, :, :], axis=2)
    G = np.exp(-0.00012 * D); np.fill_diagonal(G, 0.35)           # same-cell trips are mostly on foot
    out = {}
    kres, kjob = LOAD_KEYS.index("res"), LOAD_KEYS.index("jobs")
    for s in SCENARIOS:
        out[s] = {}
        for Y in scen_years:
            res = np.array([c["cum"][s][kres, yi(Y)] for c in cells]); jobs = np.array([c["cum"][s][kjob, yi(Y)] for c in cells])
            st = np.array([[x, z] for x, z, ph in lrt["stations"] if lrt["phase_year"][s][ph] <= Y]).reshape(-1, 2)
            near = np.array([(np.min(np.linalg.norm(st - p, axis=1)) < 1500) if len(st) else False for p in cxy])
            lrt_share = np.where(near, 0.30, 0.10) if len(st) else np.zeros(len(cells))
            persons = res * 0.12                                          # AM-peak person trips
            veh = persons * (1 - lrt_share) / 1.3                          # cars, 1.3 persons per car
            ext_share = float(np.interp(Y, [2025, 2050], [0.45, 0.15]))  # share heading to Almaty / Konaev
            flow = np.zeros(len(edges)); tt = t0.copy()
            open_mask = np.array([e["year"][s] <= Y for e in edges])
            att = G * jobs[None, :]; att[:, jobs <= 0] = 0
            local = np.diag(att) / np.maximum(att.sum(axis=1), 1e-9)       # share staying inside the cell (not routed)
            srcs = [i for i in range(len(cells)) if veh[i] > 0.5]
            for it in range(3):     # incremental assignment, 3 slices with BPR update
                w = np.where(open_mask, tt, tt * 20 + 30)
                Gc = graph_csr(nodes, edges, lambda i, e: w[i])
                uniq = sorted(set(int(cnode[i]) for i in srcs))
                if not uniq: break
                dist, pred = dijkstra(Gc, directed=False, indices=uniq, return_predecessors=True)
                row = {v: r for r, v in enumerate(uniq)}
                demand_by_src = collections.defaultdict(lambda: np.zeros(n))
                for i in srcs:
                    T = veh[i] / 3.0; a = att[i].copy(); a[i] = 0
                    dem = demand_by_src[int(cnode[i])]
                    if a.sum() > 0: np.add.at(dem, cnode, T * (1 - ext_share) * a / a.sum() * (1 - local[i]))
                    dem[almaty] += T * ext_share * 0.8; dem[konaev] += T * ext_share * 0.2
                for v, dem in demand_by_src.items():
                    r = row[v]; dem[v] = 0
                    _push_tree(pred[r].astype(np.int64), dist[r], dem, adj_ptr, adj_nbr, adj_eid, flow)
                tt = t0 * (1 + 0.15 * np.minimum(flow / cap, 1.6) ** 4)
            vc = flow / cap
            used = open_mask & (flow > 0)
            delay = 100 * float(((tt - t0) * flow)[used].sum() / max((t0 * flow)[used].sum(), 1))
            out[s][Y] = {"vc": [int(min(255, round(v * 100))) if open_mask[i] else 0 for i, v in enumerate(vc)],
                         "kpi": {"car_trips": round(float(veh.sum())), "lrt_trips": round(float((persons * lrt_share).sum())),
                                 "congested_km": r1(sum(edges[i]["len"] for i in range(len(edges)) if open_mask[i] and vc[i] > 0.85) / 1000),
                                 "avg_delay_pct": r1(delay)}}
            print(f"    traffic {s} {Y}: cars {veh.sum():.0f}, congested km {out[s][Y]['kpi']['congested_km']}, delay {delay:.0f} %, "
                  f"vc>1: {sum(edges[i]['len'] for i in range(len(edges)) if open_mask[i] and vc[i] > 1) / 1000:.0f} km")
    return out, {"almaty": int(almaty), "konaev": int(konaev)}


# ----------------------------------------------------------------------------------------------- LRT
LRT_PHASES = [(-1e9, -1255, "Gate–Golden"), (-1255, 15556, "Growing"), (15556, 1e9, "Green")]
LRT_YEARS = {"base": [2031, 2036, 2041], "fast": [2030, 2034, 2039], "slow": [2034, 2040, 2046], "infra": [2029, 2033, 2038]}


def lrt_model(geo):
    import shapely
    from shapely.geometry import MultiLineString
    segs = geo["layers"]["LRT line"]
    ml = shapely.line_merge(MultiLineString([[(s[0], s[1]), (s[2], s[3])] for s in segs]))
    lines = sorted(list(ml.geoms) if hasattr(ml, "geoms") else [ml], key=lambda g: -g.length)
    lines = [g for g in lines if g.length > 2000]
    stations = []
    named_st = [(p["x"], p["z"]) for p in geo["points"] if "Станция ЛРТ" in p["text"]]
    for g in lines:
        n = max(2, int(g.length // 1600))
        for i in range(n + 1):
            p = g.interpolate(i / n, normalized=True)
            if all(math.dist((p.x, p.y), q) > 900 for q in [(s[0], s[1]) for s in stations] + named_st):
                stations.append([round(p.x), round(p.y)])
    stations += [[round(x), round(z)] for x, z in named_st]
    out = []
    for x, z in stations:
        ph = next(i for i, (a, b, _) in enumerate(LRT_PHASES) if a <= z < b)
        out.append([x, z, ph])
    km = [0.0, 0.0, 0.0]
    for g in lines:
        for a, b in zip(list(g.coords), list(g.coords)[1:]):
            zm = (a[1] + b[1]) / 2; ph = next(i for i, (lo, hi, _) in enumerate(LRT_PHASES) if lo <= zm < hi)
            km[ph] += math.dist(a, b) / 1000
    return {"stations": out, "phase_km": [r1(k) for k in km], "phase_names": [p[2] for p in LRT_PHASES], "phase_year": LRT_YEARS}


# ----------------------------------------------------------------------------------------------- construction + finance
CONTRACTORS = [("Генподрядчик 1", 0.04), ("Генподрядчик 2", 0.06), ("Генподрядчик 3", 0.05), ("Генподрядчик 4", 0.18),
               ("Генподрядчик 5", 0.07), ("Генподрядчик 6", 0.25), ("Генподрядчик 7", 0.05), ("Генподрядчик 8", 0.09),
               ("Генподрядчик 9", 0.12), ("Генподрядчик 10", 0.06), ("Генподрядчик 11", 0.30), ("Генподрядчик 12", 0.08)]


def construction(B):
    nb = max(b["bid"] for b in B) + 1
    dur = [0] * nb; con = [255] * nb; delay = [0] * nb
    for b in B:
        if b["source"] == "existing_osm": continue
        dur[b["bid"]] = N.BUILD_YEARS.get(b["kind"], 2)
        # one contractor per parcel/block (generated blocks share a parcel id)
        key = b["id"].rsplit("_", 1)[0] if not b.get("parcel") else b["parcel"]
        ci = int(h01("contractor", b["district"], key) * len(CONTRACTORS)); con[b["bid"]] = ci
        if h01("delay", b["bid"]) < CONTRACTORS[ci][1] and b["kind"] not in ("solar", "house"):
            delay[b["bid"]] = 6 * (1 + int(h01("delay-m", b["bid"]) * 4))     # 6, 12, 18 or 24 months
    return dur, con, delay


def s_curves(B, dur, delay):
    """Cumulative GFA completed: plan vs fact per scenario/district/year (fact = plan + delay)."""
    out = {}
    for s in SCENARIOS:
        plan = np.zeros((4, NY)); fact = np.zeros((4, NY)); wip = np.zeros((4, NY))
        for b in B:
            if b["d"] < 0 or b["source"] == "existing_osm" or b["gfa"] <= 0: continue
            e = b["eff"][s]
            if e > Y1: continue
            plan[b["d"], yi(e):] += b["gfa"]
            ef = e + math.ceil(delay[b["bid"]] / 12)
            if ef <= Y1: fact[b["d"], yi(ef):] += b["gfa"]
            for y in range(max(Y0, e - dur[b["bid"]]), min(Y1, ef - 1) + 1): wip[b["d"], yi(y)] += b["gfa"]
        out[s] = {"plan": [[r1(v / 1e6) for v in row] for row in plan], "fact": [[r1(v / 1e6) for v in row] for row in fact],
                  "wip": [[r1(v / 1e6) for v in row] for row in wip]}
    return out


def finance(B, dur, delay, F, nets, edges, lrt):
    out = {}
    for s in SCENARIOS:
        bld = np.zeros((4, len(CATS), NY)); src = np.zeros((4, len(N.FUNDING_KEYS), NY)); fact = np.zeros((4, NY))
        for b in B:
            if b["d"] < 0 or b["use"] not in CATS or b["source"] == "existing_osm": continue
            e = b["eff"][s]
            if e > Y1 + 3: continue
            cost = b["gfa"] * N.COST_TG_M2[b["use"]] / 1e9
            n = max(1, dur[b["bid"]]); ys = [y for y in range(e - n + 1, e + 1)]
            dl = math.ceil(delay[b["bid"]] / 12)
            for y in ys:
                if Y0 <= y <= Y1:
                    bld[b["d"], CATS.index(b["use"]), yi(y)] += cost / n
                    src[b["d"], :, yi(y)] += cost / n * np.array(N.FUNDING[b["use"]])
                yf = y + dl
                if Y0 <= yf <= Y1: fact[b["d"], yi(yf)] += cost / n * (1.07 if dl else 1.0)
        infra = {k: np.zeros(NY) for k in ("power_hv", "power", "heat", "gas", "water", "sewer", "networks", "roads", "lrt")}
        for f in F:
            ck = {"power_hv": "power_hv_stage", "power": "power_stage", "heat": "heat_stage", "gas": "gas_stage", "water": "water_stage", "sewer": "sewer_stage"}.get(f["res"])
            if not ck: continue
            for y in f["stages"][s]:
                for yy in (y - 1, y):
                    if Y0 <= yy <= Y1: infra[f["res"]][yi(yy)] += N.COST_BLN[ck] / 2
        for res, seg in nets.items():
            for ei, sg in seg.items():
                y = sg["year"][s]
                if 2026 <= y <= Y1: infra["networks"][yi(y)] += edges[ei]["len"] / 1000 * N.COST_BLN["pipe_km"][res]
        for e in edges:
            y = e["year"][s]
            if e["cls"] == "street" and 2026 <= y <= Y1: infra["roads"][yi(y)] += e["len"] / 1000 * N.COST_BLN["road_km"]["street"]
        for ph, y in enumerate(lrt["phase_year"][s]):
            for yy in range(y - 3, y):
                if Y0 <= yy <= Y1: infra["lrt"][yi(yy)] += lrt["phase_km"][ph] * N.COST_BLN["lrt_km"] / 3
        out[s] = {"buildings": [[[r1(v) for v in bld[d, c]] for c in range(len(CATS))] for d in range(4)],
                  "sources": [[[r1(v) for v in src[d, k]] for k in range(len(N.FUNDING_KEYS))] for d in range(4)],
                  "fact": [[r1(v) for v in fact[d]] for d in range(4)],
                  "infra": {k: [r1(v) for v in a] for k, a in infra.items()}}
    return out


# ----------------------------------------------------------------------------------------------- social
def social(B):
    out = {}
    for s in SCENARIOS:
        need = np.zeros((4, 4, NY)); cap = np.zeros((4, 4, NY))   # [d][school, kindergarten, beds, clinic][y]
        for b in B:
            if b["d"] < 0 or b["source"] == "existing_osm": continue
            e = b["eff"][s]
            if e > Y1: continue
            i = yi(e); g = b["gfa"]
            if b["use"] == "housing":
                r = g / N.M2_PER_RESIDENT / 1000
                need[b["d"], :, i:] += np.array([N.SCHOOL_SEATS_PER_1000, N.KG_PLACES_PER_1000, N.BEDS_PER_1000, N.CLINIC_VISITS_PER_1000])[:, None] * r
            elif b["kind"] == "education":
                cap[b["d"], 0, i:] += g * N.EDU_SPLIT["school"] / N.M2_PER_SCHOOL_SEAT
                cap[b["d"], 1, i:] += g * N.EDU_SPLIT["kindergarten"] / N.M2_PER_KG_PLACE
            elif b["kind"] == "health":
                cap[b["d"], 2, i:] += g * N.HEALTH_SPLIT["hospital"] / N.M2_PER_BED_HOSP
                cap[b["d"], 3, i:] += g * N.HEALTH_SPLIT["clinic"] / N.M2_PER_CLINIC_VISIT
        out[s] = {"need": [[[round(v) for v in need[d, k]] for k in range(4)] for d in range(4)],
                  "cap": [[[round(v) for v in cap[d, k]] for k in range(4)] for d in range(4)]}
    return out


# ----------------------------------------------------------------------------------------------- main
def main(bcsv, geo_path, roads_pkl, out):
    import time; t = time.time()
    B = load_buildings(bcsv); geo = json.load(open(geo_path, encoding="utf-8")); H = pickle.load(open(roads_pkl, "rb"))
    print(f"buildings {len(B)}, roads {H.number_of_edges()} edges")
    nodes, idx, edges = road_tables(H)
    kd_nodes = cKDTree(np.array(nodes, float))
    road_years(edges, B)
    cells = demand_cells(B); print(f"demand cells {len(cells)}")
    DS = district_series(B)
    F = build_facilities(geo, B, cells, kd_nodes)
    serve = assign_service(F, cells)
    systems = plan_all(F, cells, serve)
    nets = networks(F, cells, serve, nodes, edges, kd_nodes)
    for r, sg in nets.items(): print(f"  network {r}: {len(sg)} segments, {sum(edges[i]['len'] for i in sg) / 1000:.0f} km")
    lrt = lrt_model(geo); print(f"LRT: {len(lrt['stations'])} stations, km {lrt['phase_km']}")
    dur, con, delay = construction(B)
    sc = s_curves(B, dur, delay)
    fin = finance(B, dur, delay, F, nets, edges, lrt)
    soc = social(B)
    tr, ext = traffic(nodes, edges, cells, kd_nodes, lrt)
    print(f"generated in {time.time() - t:.0f} s")

    sizes = {}
    about_common = {"sources": N.SOURCES, "note": "Демо-сценарий: все числа — модель, не официальные данные."}
    # roads
    sizes["roads"] = dump({"frame": "Unity: x = восток, z = север (м); UTM 43N: E = 663000 + x, N = 4830000 + z",
        "classes": {k: {"lanes": v[0], "cap_per_lane": v[1], "speed": v[2]} for k, v in __import__("gen_roads").CLASSES.items()},
        "nodes": [[int(x), int(z)] for x, z in nodes],
        "edges": [{"a": e["a"], "b": e["b"], "c": e["cls"], "len": round(e["len"]), "g": [v for p in e["geom"] for v in p],
                   "y": [e["year"][s] for s in SCENARIOS]} for e in edges],
        "external": ext}, f"{out}/roads.json", {**about_common, "what": "Граф дорог: оси улиц генплана + трассы OSM; y = год открытия по сценариям [base, fast, slow, infra], 2099 = после 2050"})
    # facilities + networks
    fac_out = []
    for f in F:
        st = f["stages"]
        o = {k: f[k] for k in ("id", "name", "kind", "res", "x", "z", "unit", "district", "synthetic", "note")}
        o["stages"] = [st[s] for s in SCENARIOS]
        o["head"] = r1(f.get("head", 0.0))
        o["cap"] = [capacity_series(st[s], f["unit"], f.get("head", 0.0)) for s in SCENARIOS] if f["res"] not in ("telecom",) else None
        o["delayed_stages"] = sorted(int(k) + 1 for k in f.get("delays", {}))
        o["demand"] = [f["demand"][s] for s in SCENARIOS] if f.get("demand") else None
        fac_out.append(o)
    fid = {f["id"]: i for i, f in enumerate(F)}
    net_out = {}
    for res, seg in nets.items():
        net_out[res] = [[ei, pipe_size(res, sg["load"]) if res not in ("power", "telecom") else (220 if sg["load"] > 150 else 110 if res == "power" else 0),
                         *[sg["year"][s] for s in SCENARIOS], fid[sg["fac"]], r1(sg["load"])] for ei, sg in sorted(seg.items())]
    sizes["networks"] = dump({"facilities": fac_out, "networks": net_out,
        "net_fields": ["road_edge", "size (DN мм / кВ)", "year_base", "year_fast", "year_slow", "year_infra", "facility", "load_2050"],
        "units": {"power_hv": "МВт", "power": "МВт", "heat": "Гкал/ч", "gas": "м³/ч", "water": "м³/сут (макс. сутки)", "sewer": "м³/сут", "renewable": "МВт"},
        "designed_delays": [{"facility": f["id"], "name": f["name"], "stage": int(k) + 1, "years": d} for f in F for k, d in f.get("delays", {}).items()],
        "headroom_note": "head = существующие сети и временные подключения (30 % одного этапа; для ПС 220 кВ — 0) до ввода первого нового этапа"},
        f"{out}/networks.json", {**about_common, "what": "Объекты инфраструктуры (этапы ввода и мощность по сценариям) и магистральные сети вдоль улиц"})
    # balance: demand vs capacity — per district and for the whole city
    balance = {}
    for s in SCENARIOS:
        si = SCENARIOS.index(s); balance[s] = {}
        for res in ("power_hv", "power", "heat", "sewer", "water", "gas"):
            fac = [o for o in fac_out if o["res"] == res]
            dem_city = np.sum([f["demand"][si] for f in fac], axis=0); cap_city = np.sum([f["cap"][si] for f in fac], axis=0)
            def unserved(fl):   # local networks: spare capacity of one substation cannot cover another one's area
                return np.sum([np.maximum(0, np.array(f["demand"][si]) - np.array(f["cap"][si])) for f in fl], axis=0) if fl else np.zeros(NY)
            per_d = []
            for d in range(4):
                fd = [o for o in fac if o["district"] == d]
                if res in POOLED or not fd: per_d.append(None); continue
                per_d.append({"demand": [r1(v) for v in np.sum([f["demand"][si] for f in fd], axis=0)], "cap": [r1(v) for v in np.sum([f["cap"][si] for f in fd], axis=0)],
                              "deficit": [r1(v) for v in unserved(fd)]})
            city_def = np.maximum(0, dem_city - cap_city) if res in POOLED else unserved(fac)
            balance[s][res] = {"city": {"demand": [r1(v) for v in dem_city], "cap": [r1(v) for v in cap_city], "deficit": [r1(v) for v in city_def]}, "districts": per_d}
    # loads per district
    loads = {}
    for s in SCENARIOS:
        L = DS[s]["loads"]
        loads[s] = {k: [[r1(v) for v in L[d, LOAD_KEYS.index(k)]] for d in range(4)] for k in LOAD_KEYS if k != "gfa"}
        loads[s]["gfa"] = [[[r1(v / 1e6) for v in DS[s]["gfa"][d, c]] for c in range(len(CATS))] for d in range(4)]
    sizes["loads"] = dump({"years": YEARS, "districts": DISTRICTS, "cats": CATS, "loads": loads, "balance": balance, "social": soc,
        "social_keys": ["школы, мест", "детсады, мест", "больницы, коек", "поликлиники, посещ./смену"],
        "norms": {k: getattr(N, k) for k in dir(N) if k.isupper() and k not in ("SOURCES",)}},
        f"{out}/loads.json", {**about_common, "what": "Население, рабочие места, нагрузки на сети и социальная инфраструктура по районам и годам"})
    sizes["construction"] = dump({"contractors": [{"name": n, "delay_rate": r} for n, r in CONTRACTORS],
        "per_building": {"duration_years": dur, "contractor": con, "delay_months": delay}, "s_curves": sc,
        "lrt": lrt}, f"{out}/construction.json", {**about_common, "what": "Стройка: длительность, генподрядчик и задержка по каждому зданию (bid); S-кривые план/факт, млн м²; ЛРТ по очередям"})
    sizes["finance"] = dump({"unit": "млрд ₸, цены 2026 г.", "cats": CATS, "funding": N.FUNDING_KEYS, "cost_tg_m2": N.COST_TG_M2,
        "infra_cost_bln": N.COST_BLN, "by_scenario": fin}, f"{out}/finance.json", {**about_common, "what": "CAPEX по годам, районам, назначению и источникам; инфраструктура по видам"})
    sizes["traffic"] = dump({"years": [2030, 2035, 2040, 2045, 2050], "by_scenario": {s: {str(y): v for y, v in tr[s].items()} for s in SCENARIOS},
        "vc_note": "загрузка ребра в утренний час пик ×100 (100 = на пределе пропускной способности)"},
        f"{out}/traffic.json", {**about_common, "what": "Утренний час пик: загрузка дорог по годам и сценариям (гравитационная модель, BPR)"})
    sizes["scenarios"] = dump({"scenarios": [
        {"id": "base", "name": "Базовый (генплан)", "pace": 1.0, "desc": "Годы ввода из сценария застройки QTwin; сети вводятся за год до нагрузки, но 4 объекта запаздывают."},
        {"id": "fast", "name": "Ускоренный", "pace": 1.33, "desc": "Темп +33 %: жильё и бизнес раньше, сети успевают лишь частично — растут дефициты."},
        {"id": "slow", "name": "Отставание", "pace": 0.77, "desc": "Темп −23 %: задержки финансирования, часть города не успевает к 2050, сети простаивают."},
        {"id": "infra", "name": "Приоритет инфраструктуры", "pace": 1.0, "desc": "Сети и ЛРТ на 2 года раньше, жильё первой очереди ждёт сети: дефицитов нет, но вложения раньше."}],
        "formula": "year_effective = f(year_plan): fast 2025 + round(0.75·Δ), slow 2025 + round(1.3·Δ), infra: жильё ≤ 2036 +2 года"},
        f"{out}/scenarios.json", {**about_common, "what": "Сценарии развития"})
    for k, v in sizes.items(): print(f"  {k}.json {v / 1e6:.2f} MB")


if __name__ == "__main__":
    main(*sys.argv[1:5])
