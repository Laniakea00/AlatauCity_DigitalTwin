"""Growing-East (growing_e), level 0 scheme: build the spec, run the checks, draw the picture.

    python3 -I tools/map/scheme/growing_e_scheme.py build   # design (growing_e_design.py) → tools/map/spec/growing_e.json (+ checks)
    python3 -I tools/map/scheme/growing_e_scheme.py check   # re-run the checks on the spec as it stands (after hand edits)
    python3 -I tools/map/scheme/growing_e_scheme.py draw    # spec → OUT/scheme.png
    python3 -I tools/map/scheme/growing_e_scheme.py all     # build + draw

Zones are cut in priority order: villages and pockets of existing houses → rivers and water strips → A-3 strip → power-line
strips → special parcels → industry / logistics → solar → rail strip (100 m, for housing) → centres → housing → rest = reserve.
Unity X/Z metres. Big data is read from the level-0 layers (city.json layers_root); nothing big goes into the repo."""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "geo"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import shapely  # noqa: E402
import shapely.affinity  # noqa: E402
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, shape  # noqa: E402

import frames  # noqa: E402
import growing_e_design as D  # noqa: E402
import layers  # noqa: E402

SPEC = os.path.join(frames.SPEC_DIR, "growing_e.json")
OUTDIR = os.environ.get("ALATAU_SCHEME_OUT", "/mnt/project-files/alatau_stage7/level0/schemes/growing_e")
DEV_USES = {"mixed_centre", "business", "residential_high", "residential_mid", "residential_low", "campus", "medical",
            "industry", "logistics", "utility", "sport"}
HOUSING_USES = {"mixed_centre", "residential_high", "residential_mid", "residential_low"}
SIMPLIFY_M = 15   # coverage_simplify tolerance for zone edges, m
AX_HALF = {"expressway": 30, "trunk": 25, "arterial": 18, "boulevard": 20, "district": 10, "pedestrian": 4, "lrt_corridor": 6}


# ============================================================ inputs
def city():
    return json.load(open(os.path.join(frames.SPEC_DIR, "city.json"), encoding="utf-8"))


def registry():
    return json.load(open(os.path.join(frames.SPEC_DIR, "registry.json"), encoding="utf-8"))


def district_poly(C):
    return Polygon(C["districts"]["growing_e"]["polygon"])


def a3_line(C, P):
    """A-3 (growing_split line) clipped to the half's z-range."""
    L = LineString(C["growing_split"]["line"])
    z0, z1 = P.bounds[1], P.bounds[3]
    return L.intersection(shapely.box(-5000, z0 - 50, 5000, z1 + 50))


def water(P):
    wg, wp = layers.load("water")
    G = P.buffer(400)
    polys, lines = [], {}
    for g, p in zip(wg, wp):
        if not g.intersects(G):
            continue
        if g.geom_type in ("Polygon", "MultiPolygon"):
            polys.append(g)
        elif "Line" in g.geom_type:
            lines.setdefault(p.get("name") or "", []).append(g)
    return shapely.union_all(polys) if polys else Polygon(), {k: shapely.union_all(v) for k, v in lines.items()}


def rail_lines(P):
    rl, _ = layers.load("rail")
    return shapely.union_all([g for g in rl if g.intersects(P.buffer(300))])


def power_lines(P):
    ig, ip = layers.load("infrastructure")
    return shapely.union_all([g for g, p in zip(ig, ip) if p.get("class") == "power_line" and g.intersects(P.buffer(300))])


def settlements(P):
    sg, sp = layers.load("derived/settlements")
    return [(p["name"], g.intersection(P), p) for g, p in zip(sg, sp) if g.intersects(P) and g.intersection(P).area > 1e4]


_BLD = None


def existing_buildings(P):
    """Overture building footprints + twin existing_osm points (8 m squares) touching the half: [(geom, src)]."""
    global _BLD
    if _BLD is None:
        import twin
        bg, bp = layers.load("buildings")
        G = P.buffer(60)
        sel = np.flatnonzero(shapely.intersects(G, bg))
        res = [(bg[i], "overture") for i in sel]
        B = twin.buildings()
        E = B[B.source == "existing_osm"]
        pts = shapely.points(E.x.values, E.z.values)
        m = shapely.intersects(G, pts)
        res += [(Point(x, z).buffer(8, cap_style="square"), "twin_existing") for x, z in zip(E.x.values[m], E.z.values[m])]
        _BLD = res
    return _BLD


def solar_points(P):
    import twin
    B = twin.buildings()
    S = B[(B.kind == "solar") & (B.x > 8800)]
    pts = shapely.points(S.x.values, S.z.values)
    return pts[shapely.contains(P, pts)]


def approach_polygon(a=D.APPROACH):
    tx, tz = a["threshold"]
    h = math.radians(a["heading_deg"])
    ux, uz = -math.sin(h), -math.cos(h)          # outward (south) along the extended centreline
    px, pz = uz, -ux                              # perpendicular
    pts = []
    for d, side in ((a["d0"], 1), (a["d1"], 1), (a["d1"], -1), (a["d0"], -1)):
        w = a["inner_half"] + a["divergence"] * (d - a["inner_offset"])
        pts.append((tx + ux * d + side * px * w, tz + uz * d + side * pz * w))
    return Polygon(pts)


# ============================================================ zones
def parts(g, min_area=0.0):
    if g.is_empty:
        return []
    gs = getattr(g, "geoms", [g])
    return [q for q in gs if q.geom_type == "Polygon" and q.area > min_area]


def build_zones(C, P):
    zones = []          # (id, use, name, geom, years, density, why, extra)
    taken = Polygon()

    def add(zid, use, name, geom, years, why, density=None, extra=None):
        nonlocal taken
        g = geom.intersection(P).difference(taken)
        g = shapely.make_valid(g)
        g = shapely.union_all([q for q in parts(g, 50)]) if parts(g, 50) else Polygon()
        if g.is_empty:
            return Polygon()
        zones.append(dict(id=zid, use=use, name_ru=name, geom=g, years=years, density=density or {}, why=why, extra=extra or {}))
        taken = taken.union(g)
        return g

    # 1 villages + pockets of existing houses
    B = existing_buildings(P)
    bl = [g for g, _ in B]
    cl = shapely.union_all([g.buffer(60) for g in bl]).buffer(-35)
    cl = shapely.union_all([q for q in parts(cl)])
    S = settlements(P)
    vill_union = shapely.union_all([g for _, g, _ in S])
    for name, g, p in sorted(S, key=lambda t: -t[1].area):
        touching = [q for q in parts(cl) if q.intersects(g)]
        gg = shapely.union_all([g] + touching).buffer(5).buffer(-5)
        pop = p.get("population_osm") or 0
        share = min(1.0, g.area / 1e4 / max(p.get("area_ha") or 1, 1))
        pop_h = int(round(pop * share))
        add(f"v_{translit(name)}", "village_existing", f"{name} (существующее село)", gg, [2025, 2025],
            f"существующее село остаётся со своими улицами; дома OSM {p.get('overture_buildings')}, жителей по OSM {pop or 'нет данных'}"
            + (f" (в половине {100 * share:.0f} % площади)" if share < 0.99 else ""),
            density=dict(floors_typical=1), extra=dict(population_existing=pop_h, settlement=name))
    # pockets outside villages: close gaps of ≤ 250 m into groups
    rest = [q for q in parts(cl) if not q.intersects(vill_union)]
    groups = parts(shapely.union_all([q.buffer(125) for q in rest]).buffer(-100))
    k = 0
    for gq in sorted(groups, key=lambda q: (-q.centroid.y, q.centroid.x)):
        mem = [q for q in rest if q.intersects(gq.buffer(30))]
        if not mem:
            continue
        geom = shapely.union_all([gq] + mem).buffer(3).buffer(-3)
        n = sum(1 for b in bl if b.intersects(geom))
        k += 1
        add(f"v_pocket_{k:02d}", "village_existing", "существующие постройки вне сёл", geom, [2025, 2025],
            f"{n} существующих построек (хутора, дачи, склады): остаются, своя улица или проезд на уровне 1",
            extra=dict(population_existing=0, buildings=n))
    # 2 rivers and water strips
    wpoly, wlines = water(P)
    W = [wpoly.buffer(35)] if not wpoly.is_empty else []
    for name, g in wlines.items():
        r = D.RIVER_BUFFERS.get(name, 35)
        W.append((name, g.buffer(r)))
    big = {"Қаскелең": [], "Кіші Алматы": [], "Карасу-Байсерке": []}
    other = []
    if W and not isinstance(W[0], tuple):
        other.append(W.pop(0))
    for name, g in W:
        (big[name] if name in big else other).append(g)
    # water polygons go with the river they touch
    for name in ("Қаскелең", "Кіші Алматы", "Карасу-Байсерке"):
        g = shapely.union_all(big[name]) if big[name] else Polygon()
        if not wpoly.is_empty and not g.is_empty:
            g = g.union(shapely.union_all([q.buffer(35) for q in parts(wpoly) if q.intersects(g)]))
        add(f"p_{translit(name)}", "park", D.RIVER_PARK_NAMES[name], g, [2030, 2046],
            f"русло, пойма и водоохранная полоса ({D.RIVER_BUFFERS[name]} м от оси, ≥ 35 м по Водному кодексу): парк, набережные, без капитальных зданий")
    add("p_streams", "park", "Малые реки, каналы и пруды", shapely.union_all(other), [2030, 2046],
        "водоохранные полосы малых рек и каналов (≥ 35 м); газон и деревья")
    # 3 A-3 strip
    a3 = a3_line(C, P)
    add("p_a3", "park", "Шумозащитная полоса А-3", a3.buffer(D.A3_STRIP_M), [2028, 2040],
        "полоса отвода А-3 и 50 м от проезжей части до любого жилья: лесополоса")
    # 4 power-line strips
    pl = power_lines(P)
    add("u_power", "utility", "Охранные полосы ЛЭП 220 кВ", pl.buffer(D.POWER_STRIP_M), [2025, 2025],
        "охранная зона ЛЭП: без зданий и деревьев, газон и велодорожки; дороги только поперёк")
    # 5.. design zones
    rail = rail_lines(P)
    rail_strip = rail.buffer(D.RAIL_STRIP_M)
    villages_g = shapely.union_all([z["geom"] for z in zones if z["use"] == "village_existing" and not z["id"].startswith("v_pocket")])
    ind_rough = shapely.union_all([Polygon(z["poly"]) for z in D.ZONES if z["use"] in ("industry", "logistics") and isinstance(z["poly"], list)])
    add("p_szz_v", "park", "Санитарный разрыв у сёл (100 м)", villages_g.buffer(100).intersection(ind_rough), [2026, 2034],
        "между сёлами и промышленными/логистическими зонами 100 м зелени; в 300 м от сёл — только классы IV–V")
    housing_done = False
    for z in D.ZONES:
        if not housing_done and z["use"] in ("mixed_centre", "residential_high", "residential_mid", "residential_low"):
            housing_done = True
            ind = shapely.union_all([q["geom"] for q in zones if q["use"] == "industry"])
            log = shapely.union_all([q["geom"] for q in zones if q["use"] == "logistics"])
            band = shapely.make_valid(ind).buffer(300).union(shapely.make_valid(log).buffer(100))
            # wind: housing not in the 200–295° sector within 2 × 300 m of industry
            fan = []
            for part in parts(shapely.make_valid(ind).simplify(20)):
                for a in np.radians(np.arange(200, 296, 8)):
                    for dd in (200, 400, 600):
                        fan.append(shapely.affinity.translate(part, dd * math.sin(a), dd * math.cos(a)))
            if fan:
                band = band.union(shapely.union_all([shapely.make_valid(f).buffer(0) for f in fan], grid_size=1).buffer(5))
            hous_rough = shapely.union_all([Polygon(q["poly"]) for q in D.ZONES if q["use"] in HOUSING_USES and isinstance(q["poly"], list)]
                                           + [LineString(D.LRT_LINE).buffer(450)])
            add("p_szz", "park", "Санитарно-защитная зелень", band.intersection(hous_rough), [2028, 2046],
                "300 м от промышленных зон (класс III), 100 м от логистики (IV–V) и 600 м в подветренном секторе 200–295°: "
                "жилья нет, деревья, велодорожки, гаражи и сервис допускаются")
        poly = z["poly"]
        if poly == "APPROACH":
            geom = approach_polygon()
        elif poly == "SOLAR":
            sp = solar_points(P)
            geom = shapely.concave_hull(shapely.multipoints(sp), ratio=0.08).buffer(60).buffer(-30)
        elif poly == "VILLAGE_RING":
            vs = [g for n, g, _ in S if n in ("Жанаарна", "Енбек", "Мойнақ")]
            geom = shapely.union_all([g.buffer(320) for g in vs])
        elif poly == "LRT_BELT":
            L = LineString(D.LRT_LINE)
            geom = L.buffer(450).intersection(shapely.box(-2000, -300, 6000, 11200))
        else:
            geom = Polygon(poly)
        if z.get("after_rail"):
            geom = geom.difference(rail_strip)
        add(z["id"], z["use"], z["name_ru"], geom, z["years"], z["why"], z.get("density"))
        if z["id"] == "z_north_ind":           # the rail strip is a zone of its own from here on (housing gives way to it)
            add("u_rail", "utility", "Полоса ж/д (100 м от путей, без жилья)", rail_strip, [2025, 2025],
                "полоса отвода и защитная полоса железной дороги: жильё ≥ 100 м от крайнего пути; склады, гаражи, зелень")
    # rest = reserve, split in parts
    restg = P.difference(taken)
    for i, q in enumerate(sorted(parts(restg, 50), key=lambda q: -q.area), 1):
        add(f"r_{i:02d}", "reserve", "Резерв (сельхоз до освоения)", q, [2025, 2050],
            "свободная земля без назначения в 2050: остаётся сельхозугодьями; резерв на после 2050")
    return zones


def translit(s):
    t = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
         "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh",
         "щ": "sch", "ы": "y", "э": "e", "ю": "yu", "я": "ya", "ә": "a", "қ": "k", "ң": "n", "ғ": "g", "ү": "u", "ұ": "u", "і": "i",
         "ө": "o", "һ": "h", "ь": "", "ъ": "", "ё": "e"}
    out = "".join(t.get(ch, ch if ch.isalnum() and ch.isascii() else "_") for ch in s.lower())
    return "_".join(w for w in out.split("_") if w)


def finish_polys(zones, P, min_ha=1.5, tol=SIMPLIFY_M):
    """Split zones into single polygons (holes kept), merge small non-village parts into the neighbour with the longest shared
    edge (water strips only into park / reserve / utility / village), simplify as a coverage, round to 1 m."""
    flat = []
    for k, z in enumerate(zones):          # list order = priority (villages first, reserve last)
        for q in parts(z["geom"], 50):
            flat.append(dict(z, geom=q, prio=k))
    soft = {"park", "reserve", "utility", "village_existing"}
    changed = True
    while changed:
        changed = False
        flat.sort(key=lambda z: z["geom"].area)
        tree = shapely.STRtree([z["geom"] for z in flat])
        for i, z in enumerate(flat):
            if z["geom"].area >= min_ha * 1e4 or z["use"] == "village_existing" or z.get("dead"):
                continue
            best, bl = None, 0.0
            for j in tree.query(z["geom"].buffer(1), predicate="intersects"):
                if j == i or flat[j].get("dead"):
                    continue
                if z["use"] == "park" and flat[j]["use"] not in soft:
                    continue
                L = z["geom"].boundary.intersection(flat[j]["geom"].buffer(0.5)).length
                if L > bl:
                    best, bl = j, L
            if best is not None and bl > 1:
                flat[best]["geom"] = flat[best]["geom"].union(z["geom"]).buffer(0.01).buffer(-0.01)
                if flat[best]["geom"].geom_type != "Polygon":
                    flat[best]["geom"] = max(parts(flat[best]["geom"]), key=lambda q: q.area)
                z["dead"] = True
                changed = True
    flat = [z for z in flat if not z.get("dead")]
    simp = shapely.coverage_simplify([z["geom"] for z in flat], tolerance=tol)

    def rnd(pr):
        ext = [(round(x), round(y)) for x, y in pr.exterior.coords]
        holes = [[(round(x), round(y)) for x, y in r.coords] for r in pr.interiors if Polygon(r).area > 300]
        return Polygon(ext, holes)
    pieces = []   # (zone, polygon) — a part that turns invalid after rounding is split, never dropped
    for i in sorted(range(len(flat)), key=lambda i: (flat[i]["id"], -flat[i]["geom"].area)):
        z, sg = flat[i], simp[i]
        for q in parts(sg):
            pr = rnd(q)
            cand = [pr] if pr.is_valid else [rnd(m) for m in parts(shapely.make_valid(pr).buffer(0))]
            pieces.extend((z, c) for c in cand if c.area >= 300)
    # exact coverage on a 1 m grid: earlier (higher-priority) zones win overlaps, rounding slivers go to the longest neighbour
    Pq = shapely.set_precision(P, 1.0)
    taken, clean = Polygon(), []
    for z, pr in sorted(pieces, key=lambda t: t[0]["prio"]):
        areal = lambda h: shapely.MultiPolygon(parts(h)) if parts(h) else Polygon()   # noqa: E731 — drop lines/points of an overlay
        g = areal(shapely.intersection(shapely.set_precision(pr, 1.0), Pq, grid_size=1))
        if not taken.is_empty and not g.is_empty:
            g = areal(shapely.difference(g, taken, grid_size=1))
        clean.extend([z, q] for q in parts(g) if q.area >= 300)
        taken = areal(shapely.union(taken, g, grid_size=1)) if not g.is_empty else taken
    gap = shapely.difference(Pq, shapely.union_all([q for _, q in clean], grid_size=1), grid_size=1)
    tree = shapely.STRtree([q for _, q in clean])
    extra = {}
    for gp in parts(gap):
        best, bl = None, 0.0
        for j in tree.query(gp.buffer(0.5), predicate="intersects"):
            L = gp.boundary.intersection(clean[j][1].buffer(0.5)).length
            if L > bl:
                best, bl = j, L
        if best is not None:
            extra.setdefault(best, []).append(gp)
    for j, gl in extra.items():
        clean[j][1] = shapely.union_all([clean[j][1]] + gl, grid_size=1)
        clean[j][1] = shapely.MultiPolygon(parts(clean[j][1])) if clean[j][1].geom_type == "GeometryCollection" else clean[j][1]
    pieces = []
    for z, g in sorted(clean, key=lambda t: (t[0]["id"], -t[1].area)):
        pieces.extend((z, q) for q in parts(g) if q.area >= 1)
    count, seen, out = {}, {}, []
    for z, _ in pieces:
        count[z["id"]] = count.get(z["id"], 0) + 1
    for z, pr in pieces:
        seen[z["id"]] = seen.get(z["id"], 0) + 1
        zz = dict(z)
        zz["id"] = z["id"] if count[z["id"]] == 1 else f"{z['id']}_{seen[z['id']]}"
        zz["polygon"] = [[int(round(x)), int(round(y))] for x, y in pr.exterior.coords]
        if pr.interiors:
            zz["holes"] = [[[int(round(x)), int(round(y))] for x, y in r.coords] for r in pr.interiors]
        out.append(zz)
    return out


# ============================================================ axes, LRT, objects
def resolve_line(ax, C, P):
    if ax["line"] == "A3":
        g = a3_line(C, P)
        return [[int(round(x)), int(round(y))] for x, y in g.simplify(10).coords]
    if ax["line"] == "LRT_BLVD":
        L = LineString(D.LRT_LINE)
        a = L.project(Point(430, -640)); b = L.project(Point(3130, 10950))
        from shapely.ops import substring
        g = substring(L, a, b)
        return [[int(round(x)), int(round(y))] for x, y in g.coords]
    return [[int(x), int(y)] for x, y in ax["line"]]


def lrt_block():
    L = LineString(D.LRT_LINE)
    st = []
    for sid, name, pt in D.LRT_STATIONS:
        s = L.interpolate(L.project(Point(pt)))
        st.append(dict(id=sid, name_ru=name, x=int(round(s.x)), z=int(round(s.y))))
    return dict(line=[[int(x), int(z)] for x, z in D.LRT_LINE],
                west_branch=[[int(x), int(z)] for x, z in D.LRT_WEST_BRANCH],
                stations=st, years=[2031, 2036],
                why="ствол ЛРТ двойника перепроложен внутри половины: не выходит за границу у Жаңалыка (стыки J080/J081 отпадают), "
                    "заходит к станции Жанаарна (пересадка на ж/д ≈ 400 м), проходит OIZ TULIP, главный центр и северные кварталы до Каскелена; "
                    "стыки J027 (Golden) и J046 (Green) сохранены; ветка на запад (к аэропорту, стык J062) отходит от станции «Центр Growing»; "
                    "станции через 0,9–1,4 км, годы — очередь «Growing» двойника (2031–2036, базовый сценарий); названия — модель qTwin")


def objects_block(R, zones_by_id):
    rows = {r["id"]: r for r in R["rows"]}
    out = []
    for rid, (act, to, why) in D.OBJECTS.items():
        r = rows.get(rid)
        if r is None:
            out.append(dict(registry_id=rid, name_ru="(нет в реестре)", action=act, **{"from": None}, to=None, yaw=None, accuracy=None, why=why))
            continue
        g = shape(r["geom"]) if r.get("geom") else None
        frm = None
        tn = r.get("twin_now") or ""
        m = re.search(r"\((−?-?\d+(?:\.\d+)?),\s*(−?-?\d+(?:\.\d+)?)\)", tn)
        if m and ("landmark" in tn or "networks" in tn):
            frm = [float(m.group(1).replace("−", "-")), float(m.group(2).replace("−", "-"))]
        if to == "reg":
            if g is None:
                t = None
            elif g.geom_type == "Point":
                t = [g.x, g.y]
            elif g.geom_type == "Polygon":
                c = g.centroid; t = [c.x, c.y]
            else:
                c = g.representative_point(); t = [c.x, c.y]
        elif isinstance(to, str) and to.startswith("zone:"):
            zg = zones_by_id.get(to[5:])
            t = [zg.centroid.x, zg.centroid.y] if zg is not None else None
        elif to is None:
            t = None
        else:
            t = list(to)
        if act in ("keep",) and frm is None and t is not None and g is not None and g.geom_type == "Point":
            frm = [g.x, g.y]
        if act == "keep" and frm is not None and t is not None and math.hypot(frm[0] - t[0], frm[1] - t[1]) < 1:
            frm = None                                    # unchanged
        rnd = lambda v: None if v is None else [int(round(v[0])), int(round(v[1]))]
        out.append(dict(registry_id=rid, name_ru=r["name_ru"], action=act, **{"from": rnd(frm)}, to=rnd(t), yaw=0 if t else None,
                        accuracy=r.get("accuracy"), why=why))
    return out


# ============================================================ phases, joints
PHASES = [
    dict(queue=1, years=[2026, 2030], what_ru="Работа и сёла: Южная и Центральная магистрали (10,3 км с путепроводом), улицы промпояса, "
         "OIZ TULIP 1-я очередь, Mars, ПС «Арна», ГТЭС; свои улицы для Жетыгена, Жанаарны, Енбека, Заречного, Даулета",
         zones=["z_mars", "z_oiz", "z_belt", "z_gtes", "z_ps_arna", "z_tlc", "z_kairat", "z_ind_centre"],
         axes=["ax_south", "ax_central", "ax_ind1", "ax_ind2", "ax_oiz"]),
    dict(queue=2, years=[2031, 2036], what_ru="ЛРТ Growing и бульвар; главный центр (1-я очередь), деловой квартал у А-3 км 46, "
         "кварталы Жанаарна-север и вокруг центра; спортпарк",
         zones=["z_centre_main", "z_business_a3", "z_centre_zh", "z_centre_south", "z_sport", "z_res_high", "z_res_mid"],
         axes=["ax_lrt_blvd", "ax_km44", "ax_centre_walk", "ax_ind3"]),
    dict(queue=3, years=[2036, 2042], what_ru="Восточная магистраль с обходом Жетыгена, развязка А-3 км ≈ 48; кварталы до Енбека; "
         "больничный городок; логистический пояс у Турксиба; река-парк Малая Алматинка",
         zones=["z_medical", "z_centre_mid", "z_log_turksib", "z_a3_front", "z_log_south", "z_res_low_e", "p_kishi_almaty"],
         axes=["ax_east_s", "ax_east_n", "ax_n48", "ax_river_walk"]),
    dict(queue=4, years=[2042, 2050], what_ru="Север: развязка А-3 км ≈ 50,5, центры Енбек и Каскелен, мост к Заречному, "
         "кварталы до Каскелена, парк Каскелен; дозаполнение СЭС",
         zones=["z_centre_enbek", "z_centre_kaskelen", "z_res_low_v", "z_res_low_n", "p_kaskelen", "z_solar", "z_north_ind"],
         axes=["ax_n50", "ax_moynak"]),
]


def joints_block(C, axes, lrt, P):
    rail = rail_lines(P)
    J = [j for j in C["joints"]["items"] if "growing_e" in j["between"]]
    lines = {a["id"]: LineString(a["line"]) for a in axes}
    lines["lrt"] = LineString(lrt["line"])
    lines["lrt_west_branch"] = LineString(lrt["west_branch"])
    out, missed = [], []
    for j in J:
        p = Point(j["x"], j["z"])
        if j["kind"] == "rail":
            d = p.distance(rail)
            ok = d <= 50
            out.append(dict(joint_id=j["id"], axis="ж/д (существующая, сохраняется)", dist_m=round(d, 1), met=ok))
            continue
        if j["kind"] == "lrt" and j["id"] in ("J080", "J081"):
            out.append(dict(joint_id=j["id"], axis=None, dist_m=None, met=None,
                            note="отпадает: стык черновика там, где ЛРТ двойника выходит за границу у Жаңалыка; новая трасса идёт внутри района"))
            continue
        cand = ["lrt", "lrt_west_branch"] if j["kind"] == "lrt" else [a for a in lines if not a.startswith("lrt")]
        best = min(cand, key=lambda a: lines[a].distance(p))
        d = lines[best].distance(p)
        tol = 400 if j.get("class") == "highway" else 60      # A-3 joints are ramps of its interchanges
        ok = d <= tol
        out.append(dict(joint_id=j["id"], axis=best, dist_m=round(d, 1), met=ok))
        if not ok:
            missed.append(j["id"])
    return out, missed


# ============================================================ checks
def run_checks(spec, C, P, R):
    T = __import__("terrain").terrain()
    res = {}
    zones = spec["zones"]
    zg = {z["id"]: shapely.make_valid(Polygon(z["polygon"], z.get("holes") or [])) for z in zones}
    # coverage
    U = shapely.union_all(list(zg.values()))
    tot = sum(g.area for g in zg.values())
    res["coverage"] = dict(district_ha=round(P.area / 1e4, 1), zones_ha=round(tot / 1e4, 1),
                           gap_ha=round(P.difference(U).area / 1e4, 2), overlap_ha=round((tot - U.area) / 1e4, 2),
                           outside_ha=round(U.difference(P).area / 1e4, 2), zones=len(zones),
                           note="зоны сведены на сетку 1 м; остаток щелей и перекрытий — шум округления вдоль границы района (< 0,1 %)")
    # houses hit
    B = existing_buildings(P)
    bg = np.array([g for g, _ in B], dtype=object)
    tree = shapely.STRtree(bg)
    hits = {}
    for z in zones:
        if z["use"] == "village_existing":
            continue
        g = zg[z["id"]]
        idx = tree.query(g, predicate="intersects")
        n = sum(1 for i in idx if bg[i].intersection(g).area > 2.0)
        if n:
            hits[z["id"]] = n
    ax_hits = {}
    for a in spec["axes"]:
        if a["status"] != "new":
            continue
        g = LineString(a["line"]).buffer(AX_HALF[a["class"]])
        idx = tree.query(g, predicate="intersects")
        n = sum(1 for i in idx if bg[i].intersection(g).area > 2.0)
        if n:
            ax_hits[a["id"]] = n
    lrt = LineString(spec["lrt"]["line"]).buffer(AX_HALF["lrt_corridor"]).union(LineString(spec["lrt"]["west_branch"]).buffer(AX_HALF["lrt_corridor"]))
    idx = tree.query(lrt, predicate="intersects")
    n_lrt = sum(1 for i in idx if bg[i].intersection(lrt).area > 2.0)
    if n_lrt:
        ax_hits["lrt"] = n_lrt
    res["houses_hit"] = dict(buildings_checked=len(B), by_zone=hits, by_new_axis=ax_hits,
                             zones_total=sum(hits.values()), new_axes_total=sum(ax_hits.values()),
                             rule="Overture + twin existing_osm, пересечение > 2 м²; зоны village_existing не считаются; оси — по полуширине класса")
    # water and flood
    wpoly, wlines = water(P)
    wl = shapely.union_all(list(wlines.values()))
    sm = 35 - SIMPLIFY_M   # 35 m minus the simplification step
    strip = wl.buffer(sm).union(wpoly.buffer(sm) if not wpoly.is_empty else Polygon())
    wat = {}
    for z in zones:
        if z["use"] in DEV_USES:
            a1 = zg[z["id"]].intersection(wpoly).area if not wpoly.is_empty else 0
            a2 = zg[z["id"]].intersection(strip).area
            if a1 > 1 or a2 > 1:
                wat[z["id"]] = dict(water_m2=round(a1), strip_m2=round(a2))
    bridges = {}
    for a in spec["axes"]:
        if a["status"] == "new":
            L = LineString(a["line"])
            n = len(parts(L.buffer(1).intersection(wl.buffer(1)))) if L.intersects(wl) else 0
            if n:
                bridges[a["id"]] = n
    Lr = LineString(spec["lrt"]["line"])
    bridges["lrt"] = len(parts(Lr.buffer(1).intersection(wl.buffer(1)))) if Lr.intersects(wl) else 0
    try:
        kg, kp = layers.load("derived/kapchagay_levels")
        k485 = shapely.union_all([g for g, p in zip(kg, kp) if abs(float(p.get("real_m", 0)) - 485) < 0.1])
        kap = {z["id"]: round(zg[z["id"]].intersection(k485).area) for z in zones if zg[z["id"]].intersects(k485)}
        kap_note = "слой kapchagay_levels, отметка 485 м"
    except Exception as e:  # noqa: BLE001
        kap, kap_note = None, f"слой не прочитан: {e}"
    res["water"] = dict(dev_zones_on_water_or_35m_strip=wat, new_axes_river_crossings_bridges=bridges,
                        kapchagay_485_overlap_m2=kap, kapchagay_note=kap_note,
                        rule=f"застраиваемые зоны (все, кроме park / reserve / village_existing) не заходят в воду и в 35 м от неё "
                             f"(проверка на {35 - SIMPLIFY_M} м: границы зон упрощены с шагом {SIMPLIFY_M} м); "
                             "оси пересекают реки только мостами (число пересечений — ниже; в него входят арыки и каналы — трубы, не мосты; "
                             "набережная идёт по извилистому берегу, её пересечения — мостики)")
    # joints
    res["joints"] = dict(met=sum(1 for j in spec["joints"] if j.get("met")), total=len(spec["joints"]),
                         not_met=[j["joint_id"] for j in spec["joints"] if j.get("met") is False],
                         obsolete=[j["joint_id"] for j in spec["joints"] if j.get("met") is None])
    # registry coverage
    rows = R["rows"]
    in_geom = [r["id"] for r in rows if r.get("geom") and shape(r["geom"]).intersects(P)]
    listed = {o["registry_id"] for o in spec["objects"]}
    assigned = ["uam_center_eurasia", "evtol_plant", "road_growing_10km", "growing_polycentres", "growing_industry_types", "district_growing"]
    res["registry"] = dict(rows_in_half_by_geometry=len(in_geom), missing=[i for i in in_geom + assigned if i not in listed],
                           objects_rows=len(spec["objects"]),
                           by_action={a: sum(1 for o in spec["objects"] if o["action"] == a) for a in ("keep", "move", "add", "by_rule", "remove")})
    # shares and capacity
    share, cap_res, cap_jobs = {}, 0.0, 0.0
    per = {}
    for z in zones:
        a = zg[z["id"]].area / 1e4
        share[z["use"]] = share.get(z["use"], 0) + a
        d = z.get("density") or {}
        r = d.get("residents_per_ha", 0) * a if z["use"] != "village_existing" else (z.get("population_existing") or 0)
        j = d.get("jobs_per_ha", 0) * a
        if z["use"] == "village_existing":
            j = 5 * a
        if z["use"] == "utility":
            j = 2 * a
        if z["use"] == "park":
            j = 0.3 * a
        cap_res += r; cap_jobs += j
        p = per.setdefault(z["use"], [0, 0, 0]); p[0] += a; p[1] += r; p[2] += j
    tgt = spec["targets"]
    res["zone_use_share"] = {k: dict(ha=round(v[0], 1), pct=round(100 * v[0] * 1e4 / P.area, 1), residents=int(round(v[1], -2)),
                                     jobs=int(round(v[2], -2))) for k, v in sorted(per.items(), key=lambda t: -t[1][0])}
    res["capacity"] = dict(residents=int(round(cap_res, -2)), residents_target=tgt["population_2050"],
                           residents_dev_pct=round(100 * (cap_res / tgt["population_2050"] - 1), 1),
                           jobs=int(round(cap_jobs, -2)), jobs_target=tgt["jobs_2050"],
                           jobs_dev_pct=round(100 * (cap_jobs / tgt["jobs_2050"] - 1), 1),
                           method="жители: га × «жителей на га» зоны (norms.json quarters.residential_zone_ha_per_1000: 9+ эт. 7–8 га/1000 → 135; "
                                  "4–8 эт. 8–9 → 118; до 3 эт. 10–11 → 95; центры — 60 при FAR 1,5–2,2) + жители сёл по OSM; "
                                  "рабочие места: га × «мест на га» зоны (модель qTwin: промышленность 35 = FAR 0,35 / 100 м² на место, логистика 30 = FAR 0,3 / 100 м², как в CityStats)")
    # social numbers (norms)
    pop = tgt["population_2050"]
    res["social_norms"] = dict(school_seats=int(round(pop * 165 / 1000, -2)), kindergarten_places=int(round(pop * 63.2 / 1000, -2)),
                               hospital_beds=int(round(pop * 5 / 1000, -1)), sport_ha=[round(pop * 0.7 / 1000), round(pop * 0.9 / 1000)],
                               public_green_ha_needed=round(pop * 16 / 1e4), river_and_district_parks_ha=round(share.get("park", 0)),
                               note="норма на 417,9 тыс.: школы 165, сады 63,2 мест на 1000, 5 коек на 1000 (norms.json); расстановка по радиусам — уровень 2")
    # slope
    def slope_stats(pts):
        s = T.slope(np.array([p[0] for p in pts]), np.array([p[1] for p in pts])) * 100
        return dict(mean_pct=round(float(np.mean(s)), 2), p95_pct=round(float(np.percentile(s, 95)), 2), max_pct=round(float(np.max(s)), 2))
    cm = next(c for c in spec["centres"] if c["kind"] == "main")
    g = zg.get("z_centre_main") or Point(cm["x"], cm["z"]).buffer(500)
    xs, zs = np.meshgrid(np.arange(g.bounds[0], g.bounds[2], 50), np.arange(g.bounds[1], g.bounds[3], 50))
    pts = [(x, z) for x, z in zip(xs.ravel(), zs.ravel()) if g.contains(Point(x, z))]
    hc = T.height(cm["x"], cm["z"])
    res["slope"] = dict(main_centre=dict(point=slope_stats([(cm["x"], cm["z"])]), zone=slope_stats(pts), ground_m=round(float(hc), 1)),
                        axes={})
    for a in spec["axes"] + [dict(id="lrt", line=spec["lrt"]["line"])]:
        L = LineString(a["line"])
        s, x, z, h = T.profile(list(L.coords), step=50)
        if len(x) < 2:
            continue
        st = slope_stats(list(zip(x, z)))
        grade = np.abs(np.diff(h)) / 50 * 100
        st["grade_p95_pct"] = round(float(np.percentile(grade, 95)), 2) if len(grade) else 0
        res["slope"]["axes"][a["id"]] = st
    # airfields and heights
    af = {a["id"]: a for a in C["height_limits"]["airfields"]}
    zh = af["zhetygen_mil"]
    newap = (-16000, 1800)
    tall = []
    for z in zones:
        fl = (z.get("density") or {}).get("floors_typical", 0)
        if z["id"] == "z_centre_main":
            tall.append(dict(zone=z["id"], what="2 акцента до 16 этажей (≈ 55 м)", flag="нужно согласование"))
        if z["id"] == "z_gtes":
            tall.append(dict(zone=z["id"], what="дымовые трубы ГТЭС (≥ 50 м)", flag="нужно согласование"))
        if fl >= 14:
            tall.append(dict(zone=z["id"], what=f"{fl} этажей типично", flag="нужно согласование"))
    distP = lambda x, z, p: round(math.hypot(x - p[0], z - p[1]) / 1000, 1)
    ap = approach_polygon()
    in_app = {z["id"]: round(zg[z["id"]].intersection(ap).area / 1e4, 1) for z in zones if zg[z["id"]].intersects(ap) and zg[z["id"]].intersection(ap).area > 1e3}
    res["airfields"] = dict(
        zhetygen_kta=[zh["x"], zh["z"]],
        half_within_30km_pct=round(100 * P.intersection(Point(zh["x"], zh["z"]).buffer(30000)).area / P.area, 1),
        half_within_10km_pct=round(100 * P.intersection(Point(zh["x"], zh["z"]).buffer(10000)).area / P.area, 1),
        main_centre_to_zhetygen_km=distP(cm["x"], cm["z"], (zh["x"], zh["z"])),
        main_centre_to_new_airport_km=distP(cm["x"], cm["z"], newap),
        new_airport_point="(−16000, 1800), runway ≈ 080° — по сообщению Growing-запад (w40); city.json держит модель (−5900, 8300)",
        planned_50m_plus=tall,
        rule="всё в 30 км от КТА Жетыген (и будущего аэропорта): ≥ 50 м — «нужно согласование»; остальная застройка ≤ 12 этажей (< 45 м)",
        approach_runway01=dict(polygon=[[int(round(x)), int(round(y))] for x, y in ap.exterior.coords],
                               zones_inside_ha=in_app,
                               surface_height_at_district_edge_m=round(0.02 * (2350 - 60)),
                               note="модель qTwin: порог ВПП 01 по контуру OSM, внутренний край 300 м, расхождение 15 %, уклон 2 %"))
    # SZZ and wind
    ind = [z for z in zones if z["use"] in ("industry",)]
    log = [z for z in zones if z["use"] in ("logistics",)]
    hous = [z for z in zones if z["use"] in HOUSING_USES]
    hu = shapely.union_all([zg[z["id"]] for z in hous])
    vu = shapely.union_all([zg[z["id"]] for z in zones if z["use"] == "village_existing" and z["id"].startswith("v_") and not z["id"].startswith("v_pocket")])
    def mind(zs_, other):
        return {z["id"]: round(zg[z["id"]].distance(other)) for z in zs_}
    res["szz"] = dict(industry_to_new_housing_m=mind(ind, hu), logistics_to_new_housing_m=mind(log, hu),
                      industry_to_villages_m=mind(ind, vu),
                      rule="новое жильё ≥ 300 м от промышленных зон (класс III по умолчанию) и ≥ 100 м от логистики (IV–V); "
                           "где ближе — в зоне только классы IV–V (см. why зоны); существующие сёла у старых заводов — как есть")
    # wind sector: housing area inside 2×300 m of industry in the 200–295° sector
    sect = []
    for z in ind:
        g = zg[z["id"]]
        c = g.centroid
        far = 600 + max(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1])
        a0, a1 = math.radians(200), math.radians(295)
        wedge = Polygon([(c.x, c.y)] + [(c.x + far * math.sin(a), c.y + far * math.cos(a)) for a in np.linspace(a0, a1, 12)])
        zone2 = g.buffer(600).difference(g)
        risk = zone2.intersection(wedge).intersection(hu)
        if risk.area > 100:
            sect.append(dict(zone=z["id"], housing_ha=round(risk.area / 1e4, 1)))
    res["szz"]["wind_sector_200_295_housing_within_2x300m"] = sect
    # twin defects named by the plan (plan.md, audit table and Growing row): plants without streets, duplicate houses, schools/kindergartens
    import twin
    TB = twin.buildings()
    TB = TB[(TB.district == "Growing") & (TB.year <= 2050)]
    tp = shapely.points(TB.x.values, TB.z.values)
    TE = TB[shapely.contains(P, tp)]
    ind = TE[TE.use == "industry"]
    ip = shapely.points(ind.x.values, ind.z.values)
    rg, rp = layers.load("roads")
    road_cls = ("motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "service", "track", "living_street", "road")
    Rl = [g for g, q in zip(rg, rp) if q.get("class") in road_cls and g.intersects(P.buffer(500))]
    tr_r = shapely.STRtree(Rl)
    axl = [LineString(a["line"]) for a in spec["axes"]]
    tr_a = shapely.STRtree(axl)
    d0 = np.array([Rl[tr_r.nearest(q)].distance(q) for q in ip])
    d1 = np.minimum(d0, np.array([axl[tr_a.nearest(q)].distance(q) for q in ip]))
    tz = shapely.STRtree(list(zg.values()))
    zuse = [z["use"] for z in zones]
    by_use = {}
    for q in ip:
        j = tz.query(q, predicate="intersects")
        u = zuse[j[0]] if len(j) else "вне зон"
        by_use[u] = by_use.get(u, 0) + 1
    cells = {}
    for x, z in zip(TE.x.values, TE.z.values):
        k = (round(x / 5), round(z / 5)); cells[k] = cells.get(k, 0) + 1
    res["twin_fixes"] = dict(
        plants_without_streets=dict(
            twin_industry_buildings_2050=int(len(ind)), farther_200m_from_osm_road=int((d0 > 200).sum()),
            farther_200m_from_osm_road_or_scheme_axis=int((d1 > 200).sum()), farther_400m_after_scheme=int((d1 > 400).sum()),
            by_scheme_zone_use=by_use,
            plan="plan.md: Growing — 1 811 домов дальше 200 м от дороги, из них 711 заводов без улиц (весь Growing)",
            fix="уровень 0: промзоны получают магистрали и промышленные улицы (ax_ind1–3, ax_oiz, Центральная, Южная), "
                "санитарные разрывы — зоны p_szz (300 м до нового жилья) и p_szz_v (100 м до сёл); уровень 1: сетка проездов ≤ 400 м, "
                "каждый завод ≤ 200 м от проезда; заводы двойника, попавшие в парки, сёла и жильё, переносятся в промзоны"),
        duplicate_houses=dict(
            twin_buildings_sharing_5m_cell=int(sum(v for v in cells.values() if v > 1)),
            plan="plan.md: «здание в здании» — Growing 909",
            fix="уровень 1 ставит дома заново по зонам этой схемы: одна точка — одно здание, дубли не переносятся"),
        schools_kindergartens=dict(
            plan="plan.md: школы Growing 60 % нормы, сады 40 % (по старой норме двойника 120 и 60 мест на 1000)",
            need_school_seats=res["social_norms"]["school_seats"], need_kindergarten_places=res["social_norms"]["kindergarten_places"],
            fix="по norms.json (165 и 63,2 места на 1000): участок школы и сада в каждом местном центре и у каждой станции ЛРТ, "
                "в сёлах — по одной школе и саду на село; расстановка по радиусам 500/300 м — уровень 2"))
    # LRT
    st = spec["lrt"]["stations"]
    L = LineString(spec["lrt"]["line"])
    ds = sorted(L.project(Point(s["x"], s["z"])) for s in st)
    gaps = [round(b - a) for a, b in zip(ds, ds[1:])]
    res["lrt"] = dict(length_km=round(L.length / 1000, 2), stations=len(st), spacing_m=gaps, min_m=min(gaps), max_m=max(gaps),
                      within_800_1500=all(800 <= g <= 1500 for g in gaps),
                      west_branch_km=round(LineString(spec["lrt"]["west_branch"]).length / 1000, 2))
    return res


# ============================================================ build / write
def build():
    C, R = city(), registry()
    P = district_poly(C)
    zones = build_zones(C, P)
    pre = {z['id']: z['geom'] for z in zones}
    zones = finish_polys(zones, P)
    axes = []
    for a in D.AXES:
        axes.append(dict(id=a["id"], **{"class": a["cls"]}, name_ru=a["name_ru"], line=resolve_line(a, C, P), status=a["status"],
                         years=a["years"], why=a["why"]))
    lrt = lrt_block()
    axes.append(dict(id="ax_lrt", **{"class": "lrt_corridor"}, name_ru="ЛРТ: ствол (новая трасса в половине)", line=lrt["line"],
                     status="new", years=lrt["years"], why="см. lrt.why"))
    axes.append(dict(id="ax_lrt_west", **{"class": "lrt_corridor"}, name_ru="ЛРТ: ветка на запад (к аэропорту)", line=lrt["west_branch"],
                     status="new", years=[2036, 2041], why="ветка двойника west_growing, стык J062 на А-3; дальше — Growing-запад"))
    joints, _ = joints_block(C, axes, lrt, P)
    tw = D.TWIN_RES_2050; tj = D.TWIN_JOBS_2050
    sh_r = tw["E"] / (tw["E"] + tw["W"]); sh_j = tj["E"] / (tj["E"] + tj["W"])
    pop = int(round(D.GROWING_POP_TARGET * sh_r, -2))
    n = lambda v: f"{v:,}".replace(",", " ")            # noqa: E731 — 470 307
    f2 = lambda v: f"{v:.2f}".replace(".", ",")         # noqa: E731 — 64,29
    f4 = lambda v: f"{v:.4f}".replace(".", ",")         # noqa: E731
    targets = dict(population_2050=pop, jobs_2050=267460, homes_2050=None,
                   source=(f"жители: цель кода двойника для Growing 650 тыс. (CityStats.DistrictTarget2050k) × доля восточной половины в жителях двойника 2050 "
                           f"(buildings.csv district=Growing, жильё / 30 м², базовый сценарий, точка здания в полигоне половины): "
                           f"{n(tw['E'])} / ({n(tw['E'])} + {n(tw['W'])}) = {f2(100 * sh_r)} % → 650 000 × {f4(sh_r)} = {n(pop)}; "
                           f"рабочие места: собственные места двойника 2050 в полигоне половины (формулы CityStats: 90 м² офис, 50 соц., 100 пром./энергетика, 120 досуг), "
                           f"без масштабирования (правило оркестратора для всех районов): {n(tj['E'])} = {f2(100 * sh_j)} % от {n(tj['E'] + tj['W'])} по Growing; "
                           "в 2026 CityStats даёт 0 жителей (дома existing_osm не считаются), поэтому база — 2050; квартир в коде нет (homes_2050 = null). "
                           "Тот же метод у Growing-запад (w40): 35,7 % жителей, 33,3 % мест"))
    zones_out = []
    for z in zones:
        d = {k: v for k, v in (z.get("density") or {}).items()}
        zo = dict(id=z["id"], use=z["use"], name_ru=z["name_ru"], polygon=z["polygon"], density=d, years=z["years"], why=z["why"])
        if z.get("holes"):
            zo["holes"] = z["holes"]
        if z["extra"].get("population_existing"):
            zo["population_existing"] = z["extra"]["population_existing"]
        zones_out.append(zo)
    spec = dict(
        district="growing_e", version=0, boundary="city.json#districts/growing_e",
        targets=targets,
        centres=[dict(id=c["id"], kind=c["kind"], name_ru=c["name_ru"], x=c["x"], z=c["z"], why=c["why"]) for c in D.CENTRES],
        axes=axes, zones=zones_out, lrt=lrt,
        objects=objects_block(R, pre),
        phases=[dict(ph, zones=[i for b in ph["zones"] for i in [z["id"] for z in zones_out] if i == b or re.fullmatch(re.escape(b) + r"_\d+", i)])
                for ph in PHASES],
        joints=joints, checks={})
    spec["checks"] = run_checks(spec, C, P, R)
    spec["checks"]["open_questions"] = OPEN_QUESTIONS
    write_spec(spec)
    return spec


OPEN_QUESTIONS = [
    "ТЛЦ «Жетыген» на 2/3 лежит за границей района (в Green): передвинуть границу Growing-восток/Green, чтобы весь ТЛЦ был в Growing? (да/нет)",
    "Ветку ЛРТ от центра Growing до Жетыгена (≈ 6 км) резервировать коридором уже сейчас? (да/нет)",
]


def _numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) or isinstance(v, list) and len(v) > 0 and all(_numeric(q) for q in v)


def write_spec(spec):
    """Indented JSON, but every all-number list (coordinates, polygons, holes, lines, years) on one compact line."""
    store = []

    def pack(o):
        if isinstance(o, dict):
            return {k: pack(v) for k, v in o.items()}
        if isinstance(o, list):
            if _numeric(o):
                store.append(o)
                return f"@@G{len(store) - 1}@@"
            return [pack(v) for v in o]
        return o
    s = json.dumps(pack(spec), ensure_ascii=False, indent=1)
    s = re.sub(r'"@@G(\d+)@@"', lambda m: json.dumps(store[int(m.group(1))], separators=(",", ":")), s)
    tmp = SPEC + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(s + "\n")
    os.replace(tmp, SPEC)
    print(f"[spec] {SPEC}: {os.path.getsize(SPEC) / 1e3:.0f} kB, {len(spec['zones'])} zones, {len(spec['axes'])} axes, {len(spec['objects'])} objects")


def check_only():
    spec = json.load(open(SPEC, encoding="utf-8"))
    C, R = city(), registry()
    P = district_poly(C)
    oq = spec["checks"].get("open_questions", OPEN_QUESTIONS)
    spec["checks"] = run_checks(spec, C, P, R)
    spec["checks"]["open_questions"] = oq
    write_spec(spec)
    return spec


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("build", "all"):
        sp = build()
        print(json.dumps({k: sp["checks"][k] for k in ("coverage", "capacity", "houses_hit", "joints", "registry", "lrt")}, ensure_ascii=False, indent=1))
    if cmd == "check":
        sp = check_only()
        print(json.dumps({k: sp["checks"][k] for k in ("coverage", "capacity", "houses_hit", "joints", "registry", "lrt")}, ensure_ascii=False, indent=1))
    if cmd in ("draw", "all"):
        import growing_e_draw
        growing_e_draw.main(SPEC, OUTDIR)
