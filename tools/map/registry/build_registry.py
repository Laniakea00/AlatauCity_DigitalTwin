#!/usr/bin/env python3
"""Build tools/map/spec/registry.json and tools/map/spec/registry_report.md (level 0, w35).

Inputs (all read-only; override with flags):
  --research  research folder with alatau_objects.md (source table S01-S149)
  --overture  folder with Overture 2026-10-21.0 extracts (places, infrastructure, land_use,
              division, division_area, segment_major .parquet), bbox lon 76.55-77.50, lat 43.25-44.05
  --genplan   alatau_plan_utm43n_rel.geojson (district polygons; relative UTM 43N + origin_utm43n)
  --out       output folder (default: tools/map/spec next to this script)

Frame: Unity X = E - 663000, Z = N - 4830000 in UTM 43N (EPSG:32643); lat/lon -> UTM by pyproj.
Curated rows live in seed_objects.py and seed_infra.py; sources outside S01-S149 in sources_ext.py.
Run: python3 tools/map/registry/build_registry.py
"""
import argparse
import collections
import json
import math
import os
import re
import sys

import networkx as nx
import pyarrow.parquet as pq
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, MultiPoint, Point, mapping
from shapely.ops import linemerge as _linemerge, substring, transform, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import seed_infra  # noqa: E402
import seed_objects  # noqa: E402
from sources_ext import DOCS, EXT  # noqa: E402

OVERTURE_RELEASE = "2026-10-21.0"
ATTRIBUTION = "© OpenStreetMap contributors, Overture Maps Foundation"
MODEL_CHIP = "модель qTwin"
TYPES = {
    "business_mixed": "деловой / многофункциональный комплекс", "hotel": "гостиница", "residential": "жильё",
    "school": "школа", "kindergarten": "детский сад", "university": "вуз / кампус", "college": "колледж, профтех",
    "research": "наука, НИИ, центр связи", "hospital": "больница", "clinic": "поликлиника, ФАП, амбулатория",
    "ambulance": "скорая помощь", "park": "парк, сквер, озеленение", "sport": "спорт", "culture": "культура, выставки",
    "tourism_leisure": "туризм, отдых, развлечения", "religious": "культовое здание", "industry": "завод",
    "logistics": "логистика, склады", "industrial_zone": "промзона, индустриальный парк", "admin": "администрация, суд",
    "military": "военный объект", "airport": "аэропорт", "airfield": "аэродром", "vertiport": "вертипорт",
    "road": "дорога", "interchange": "развязка", "bridge": "мост, путепровод", "rail_line": "ж/д линия",
    "rail_station": "ж/д станция", "metro": "метро", "lrt": "ЛРТ", "port_marina": "марина, причал, речной транспорт",
    "power_plant": "электростанция, ТЭЦ, СЭС", "substation": "подстанция", "power_line": "ЛЭП",
    "water_intake": "водозабор", "sewage": "очистные, ливневые бассейны", "pumping_station": "насосная станция, КНС",
    "heat_plant": "котельная, тепловые насосы", "gas_station": "ГРС / АГРС", "waste": "отходы, полигон",
    "settlement": "населённый пункт", "dacha": "дачные массивы", "datacenter": "ЦОД", "water": "вода",
    "district": "район города", "district_program": "программа / набор объектов без адресов",
    "label_only": "нематериальный объект или справка (только подпись)",
}
STATUSES = {
    "built": "существует", "under_construction": "строится", "planned": "в утверждённом плане (генплан, ПСД, эскиз)",
    "announced": "объявлен / меморандум / обсуждение", "reserve": "резерв, решение не принято",
    "cancelled": "отменён (не строим)", "removed": "был и убран",
}
ACCURACY = {
    "point_50m": "точка или контур с допуском 50 м (координаты источника или OSM)",
    "road_km_500m": "километр трассы: ±500 м вдоль оси и правильная сторона",
    "settlement_1km": "внутри полигона посёлка или в пределах 1 км",
    "district_only": "только район (внутри района по правилу зон)",
    "none": "места нет; ставится по правилу",
}
ACTIONS = {
    "keep": "оставить, как в двойнике (или существующее на месте)", "move": "перенести на место из источника",
    "add": "добавить (в двойнике нет)", "by_rule": "ставит генератор по правилам norms.json / rules.json",
    "remove": "убрать / не ставить",
    "reroute": "линия остаётся, но часть трассы меняется по схеме района (в кабель или в обход); участки — в action.segments",
}
ROUTE_ROWS = {"KAZ08": "road_a3", "KZ02-01": "road_bakad", "KAZ06": "road_a19", "KZ05-10": "road_kz05_10"}   # Overture route ref -> registry row
CORE_USES = ("mixed_centre", "business")   # zones of a district spec that make its centre (ядро) for the 220 kV owner decision
TWIN_INTERCHANGE_ZONES = [  # research/inventory.md: film_roads.json interchange zones (x, z, r)
    (113.5, 3965.3, 234), (-11151.3, -20521.2, 324), (-1780.2, -12157.4, 270), (-2293.5, -20325.8, 378),
    (415.8, 19019.4, 234), (1412.8, -15115.4, 270), (7214.0, -25349.9, 288), (-855.9, -3291.8, 297), (994.0, 26490.3, 270),
]
PLAN_NAMED = set("""
iconic_complex iconic_tower_main iconic_tower_second iconic_podium iconic_offices_6 gate_district_ring datacenter_alatau_data_hub l7_lotte
zhk_gate_city school_gate_city_20_keleshek kindergarten_gate_city_280 akimat_koyankus griffin_logopark pepsico avz_fan_plant
park_gate_city_yntymak water_intake_gate_city boiler_gate_city agrs_gate_city ps_kokpa_1 agglo_rail_station_1 metro_line3_reserve
academic_cluster qaist medcluster_golden k_park korean_clinics space_comm_centre agro_processing_golden sport_centre_hippodrome stadium_50k
mars_petcare tlc_zhetygen oiz_tulip airport_alatau airport_rail_station rail_sorting_station dry_port car_assembly_zhanaarna uam_center_eurasia
vocational_institute airfield_zhetygen military_unit station_building_zhetygen mosque_zhetygen house_of_culture_zhetygen hospital_zhetygen
overpass_zhetygen_950 ps_arna_twin ses_fields_twin sunny_paper danaflex g_trans gtes_doosan
resort_ircc f1_track golf_diving marina_kapchagay green_tower_30 iconic_building_2 expo_complexes sand_spit_leisure heat_pumps_green
theme_parks oceanarium_aquapark casino_zone urban_beaches green_terraces
road_a3 road_ia arterial_continuous_east road_bakad road_a19 half_rings_3_4 rail_turksib rail_bypass_zhetygen_kazybek rail_agglomeration
lrt_city lrt_depots river_tram micromobility_network a3_dubler moyynkum_forest_park
k_smart_town substations_programme kogtu_chp_10 water_intakes_4 pumping_stations_12 wwtp_4 schools_genplan kindergartens_genplan
polyclinics_genplan fire_depots_genplan hospitals_stage1
dolce_pharm jti_factory henkel_plant mareven_food knauf landfill_ali dachas_36
settlement_zhetygen settlement_enbek settlement_zhanaarna settlement_kuygan settlement_zhanadaur settlement_zhanatalap settlement_yntymak
settlement_koyankus settlement_daulet settlement_kairat settlement_zarechnoe settlement_arna
""".split())

T = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
SPEC_IDS = ["gate", "golden", "growing_w", "growing_e", "green"]



def linemerge(g):
    """linemerge that tolerates a single LineString or an empty result"""
    if g is None or g.is_empty:
        return g
    if g.geom_type == "LineString":
        return g
    if g.geom_type == "GeometryCollection":
        g = shapely.MultiLineString([p for p in g.geoms if p.geom_type == "LineString"])
    return _linemerge(g)

def ll2u(lon, lat):
    e, n = T.transform(lon, lat)
    return e - 663000.0, n - 4830000.0


def g2u(g):
    return transform(lambda x, y, z=None: (lambda en: (en[0] - 663000.0, en[1] - 4830000.0))(T.transform(x, y)), g)


def tagdict(st):
    out = {}
    for t in st or []:
        if isinstance(t, dict):
            out[t.get("key")] = t.get("value")
        else:
            out[t[0]] = t[1]
    return out


def rnd(g, nd=1):
    return shapely.set_precision(g, 10 ** -nd) if g is not None and not g.is_empty else g


def gj(g):
    if g is None or g.is_empty:
        return None
    m = mapping(rnd(g, 1))

    def fix(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            return [round(c[0], 1), round(c[1], 1)]
        return [fix(x) for x in c]
    if m["type"] == "GeometryCollection":
        return {"type": "GeometryCollection", "geometries": [gj(x) for x in g.geoms]}
    return {"type": m["type"], "coordinates": fix(m["coordinates"])}


class Ctx:
    def __init__(self, a):
        self.a = a
        self.tables = {}
        self.byid = {}
        self.load_sources()
        self.load_genplan()
        self.load_city()
        self.specs = {d: json.load(open(os.path.join(self.a.specs, d + ".json"), encoding="utf-8")) for d in SPEC_IDS}
        self.load_overture_index()
        self.build_roads()

    # ---------- sources ----------
    def load_sources(self):
        txt = open(os.path.join(self.a.research, "alatau_objects.md"), encoding="utf-8").read()
        sec = txt[txt.index("## 7. Список источников"):]
        self.S = {}
        for m in re.finditer(r"^\| (S\d{2,3}) \| (.+?) \| (\S+) \| (.+?) \|\s*$", sec, re.M):
            self.S[m.group(1)] = (m.group(2).strip(), m.group(3).strip(), m.group(4).strip())

    def src(self, code, claim):
        if code in self.S:
            pub, url, date = self.S[code]
            return {"code": code, "publisher": pub, "url": url, "date": date, "claim": claim}
        if code in EXT:
            pub, url, date = EXT[code]
            return {"code": code, "publisher": pub, "url": url, "date": date, "claim": claim}
        if code in DOCS:
            return {"code": code, "publisher": DOCS[code], "url": None, "date": "31.10.2026", "claim": claim}
        if code == "OVT":
            return self.ovt(claim)
        raise KeyError("unknown source code %s" % code)

    def ovt(self, claim):
        return {"code": "OVT", "publisher": "OpenStreetMap contributors via Overture Maps Foundation (" + ATTRIBUTION + ")",
                "url": "s3://overturemaps-us-west-2/release/%s/ (https://docs.overturemaps.org/)" % OVERTURE_RELEASE,
                "date": "21.10.2026", "claim": claim}

    # ---------- genplan ----------
    def load_genplan(self):
        d = json.load(open(self.a.genplan, encoding="utf-8"))
        ox, oy = d["origin_utm43n"]
        dx, dz = ox - 663000.0, oy - 4830000.0
        self.genplan_shift = (round(dx, 2), round(dz, 2))
        self.gp = {}
        for f in d["features"]:
            g = shapely.geometry.shape(f["geometry"])
            self.gp[f["properties"]["name"]] = transform(lambda x, y, z=None: (x + dx, y + dz), g)
        self.districts = {k: self.gp[k] for k in ("gate", "golden", "growing", "green")}
        self.city = self.gp["city"]
        self.city_buf = self.city.buffer(2000)

    def district_genplan(self, g):
        """level 0: district by the genplan geojson polygons (kept for comparison)"""
        if g is None or g.is_empty:
            return None
        p = g if g.geom_type == "Point" else g.representative_point()
        for k, poly in self.districts.items():
            if poly.contains(p):
                return k.capitalize()
        if self.city.contains(p):
            return "city"
        dmin = min((poly.distance(p), k) for k, poly in self.districts.items())
        return "outside (%.1f km from %s)" % (dmin[0] / 1000.0, dmin[1].capitalize())

    # ---------- city.json (level 1): district polygons of the twin, Growing halves
    def load_city(self):
        c = json.load(open(self.a.city, encoding="utf-8"))
        self.cityjson = c
        self.cdist = {k: shapely.geometry.Polygon(c["districts"][k]["polygon"]) for k in ("gate", "golden", "growing", "green")}
        self.careas = {k: shapely.geometry.Polygon(c["districts"][k]["polygon"]) for k in SPEC_IDS}
        for g in list(self.cdist.values()) + list(self.careas.values()):
            shapely.prepare(g)
        self.city_l1 = unary_union(list(self.cdist.values()))
        shapely.prepare(self.city_l1)
        ap = [a for a in c["height_limits"]["airfields"] if a["id"] == "alatau_new"][0]
        self.airport_cp = Point(ap["x"], ap["z"])

    def district_of(self, g):
        """district by the city.json polygons (twin outlines, level 1)"""
        if g is None or g.is_empty:
            return None
        p = g if g.geom_type == "Point" else g.representative_point()
        for k, poly in self.cdist.items():
            if poly.contains(p):
                return k.capitalize()
        dmin = min((poly.distance(p), k) for k, poly in self.cdist.items())
        return "outside (%.1f km from %s)" % (dmin[0] / 1000.0, dmin[1].capitalize())

    def area_of(self, g):
        """spec area (gate, golden, growing_w, growing_e, green) by the city.json polygons"""
        if g is None or g.is_empty:
            return None
        p = g if g.geom_type == "Point" else g.representative_point()
        for k, poly in self.careas.items():
            if poly.contains(p):
                return k
        return None

    # ---------- overture ----------
    def table(self, name):
        if name not in self.tables:
            self.tables[name] = pq.read_table(os.path.join(self.a.overture, name + ".parquet")).to_pylist()
            for r in self.tables[name]:
                self.byid[(name, r["id"])] = r
        return self.tables[name]

    def load_overture_index(self):
        for n in ("places", "infrastructure", "land_use", "division", "division_area", "segment_major"):
            self.table(n)
        self.div_area = {}
        for r in self.table("division_area"):
            self.div_area.setdefault(r["division_id"], r)

    def ov(self, theme, fid):
        r = self.byid.get((theme, fid))
        if r is None:
            raise KeyError("Overture %s/%s not found" % (theme, fid))
        return r, g2u(shapely.from_wkb(r["geometry"]))

    def ov_name(self, r):
        n = r.get("names") or {}
        return n.get("primary")

    # ---------- roads ----------
    def route_graph(self, ref):
        G = nx.MultiGraph()
        pos = {}
        for r in self.table("segment_major"):
            if not any((rr.get("ref") or "") == ref for rr in (r.get("routes") or [])):
                continue
            g = g2u(shapely.from_wkb(r["geometry"]))
            cons = sorted(r.get("connectors") or [], key=lambda c: c["at"])
            for c1, c2 in zip(cons, cons[1:]):
                sub = substring(g, c1["at"], c2["at"], normalized=True)
                if sub.length == 0:
                    continue
                G.add_edge(c1["connector_id"], c2["connector_id"], w=sub.length, g=sub)
                pos[c1["connector_id"]] = sub.coords[0]
                pos[c2["connector_id"]] = sub.coords[-1]
        return G, pos

    @staticmethod
    def path_line(G, pos, a, b):
        p = nx.shortest_path(G, a, b, weight="w")
        pts = []
        for u, v in zip(p, p[1:]):
            d = min(G.get_edge_data(u, v).values(), key=lambda d: d["w"])
            cs = list(d["g"].coords)
            if Point(cs[0]).distance(Point(pos[u])) > 1:
                cs = cs[::-1]
            pts += cs if not pts else cs[1:]
        return LineString(pts)

    def route_path(self, ref, axis):
        G, pos = self.route_graph(ref)
        big = max(nx.connected_components(G), key=len)
        lo = min(big, key=lambda n: pos[n][axis])
        hi = max(big, key=lambda n: pos[n][axis])
        return self.path_line(G, pos, lo, hi)

    def build_roads(self):
        self.a3 = self.route_path("KAZ08", 1)          # south -> north
        self.bakad = self.route_path("KZ02-01", 0)     # west -> east
        x = self.a3.intersection(self.bakad)
        self.a3xbakad = x if x.geom_type == "Point" else list(x.geoms)[0]
        self.ch_x = self.a3.project(self.a3xbakad) / 1000.0
        # km markers: OSM milestones (Overture infrastructure class milestone, tag distance) near the A-3 path
        pts = []
        for r in self.table("infrastructure"):
            if r.get("class") != "milestone":
                continue
            t = tagdict(r.get("source_tags"))
            try:
                km = float(str(t.get("distance", "")).replace(",", "."))
            except ValueError:
                continue
            p = g2u(shapely.from_wkb(r["geometry"]))
            if p.distance(self.a3) < 150:
                pts.append((self.a3.project(p) / 1000.0, km))
        self.km_fit = self.fit(pts)
        # link-road clusters along A-3 and BAKAD (existing interchanges)
        self.links = {}
        for name, line in (("A3", self.a3), ("BAKAD", self.bakad)):
            ls = []
            for r in self.table("segment_major"):
                if r["subtype"] == "road" and r.get("subclass") == "link":
                    g = g2u(shapely.from_wkb(r["geometry"]))
                    if g.distance(line) < 60:
                        ls.append(g)
            u = unary_union([g.buffer(150) for g in ls])
            parts = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
            self.links[name] = sorted(((line.project(p.centroid) / 1000.0, p.centroid, p) for p in parts), key=lambda t: t[0])

    @staticmethod
    def fit(pts):
        def ls(ps):
            n = len(ps)
            mx = sum(p[0] for p in ps) / n
            my = sum(p[1] for p in ps) / n
            sxx = sum((p[0] - mx) ** 2 for p in ps)
            a = sum((p[0] - mx) * (p[1] - my) for p in ps) / sxx
            return a, my - a * mx
        a, b = ls(pts)
        keep = [p for p in pts if abs(p[1] - (a * p[0] + b)) < 2.0]
        a, b = ls(keep)
        res = [p[1] - (a * p[0] + b) for p in keep]
        sd = math.sqrt(sum(r * r for r in res) / max(1, len(res) - 2))
        return {"a": a, "b": b, "n": len(keep), "n_all": len(pts), "sd_km": sd}

    def km2ch(self, km):
        return (km - self.km_fit["b"]) / self.km_fit["a"]

    def ch2km(self, ch):
        return self.km_fit["a"] * ch + self.km_fit["b"]

    def on_a3(self, ch, side=None, off=0.0):
        p = self.a3.interpolate(ch * 1000.0)
        if not side or not off:
            return p
        q = self.a3.interpolate(min(self.a3.length, ch * 1000.0 + 50))
        o = self.a3.interpolate(max(0.0, ch * 1000.0 - 50))
        dx, dz = q.x - o.x, q.y - o.y
        L = math.hypot(dx, dz)
        nx_, nz_ = dz / L, -dx / L          # right-hand normal
        if (side == "E" and nx_ < 0) or (side == "W" and nx_ > 0):
            nx_, nz_ = -nx_, -nz_
        return Point(p.x + nx_ * off, p.y + nz_ * off)

    def griffin_ch(self):
        a = self.ch_x + 1.0
        nxt = [c for c, _, _ in self.links["A3"] if c > a]
        b = (nxt[0] - 0.6) if nxt else a
        return (a + b) / 2.0, a, b, (nxt[0] if nxt else None)

    def clip(self, g):
        return g.intersection(self.city_buf)

    def railname(self, rx):
        gs = []
        for r in self.table("segment_major"):
            if r["subtype"] != "rail":
                continue
            n = self.ov_name(r) or ""
            if re.search(rx, n):
                gs.append(g2u(shapely.from_wkb(r["geometry"])))
        g = linemerge(unary_union(gs)) if gs else None
        return g

    def power(self, volt):
        gs = []
        for r in self.table("infrastructure"):
            if r.get("class") != "power_line":
                continue
            v = str(tagdict(r.get("source_tags")).get("voltage") or "")
            if volt in v.split(";"):
                g = g2u(shapely.from_wkb(r["geometry"]))
                if g.intersects(self.city_buf):
                    gs.append(g)
        return linemerge(unary_union(gs)) if gs else None

    # ---------- level 1 (w42b): a route on other roads' carriageways; 220 kV lines one by one
    def trial_area(self):
        p = os.path.join(self.a.specs, "gate_trial.json")
        if not os.path.isfile(p):
            return None
        a = json.load(open(p, encoding="utf-8")).get("area")
        return shapely.geometry.Polygon(a) if a else None

    def route_aliases(self, ref):
        """international numbers (E …, AH …) the route `ref` carries on ≥ 80 % of its length near the city: OSM keeps them on both
        carriageways where a national relation (KAZ06) may hold only one"""
        tot, by = 0.0, collections.Counter()
        for r in self.table("segment_major"):
            refs = {(rr.get("ref") or "") for rr in (r.get("routes") or [])}
            if ref not in refs:
                continue
            g = g2u(shapely.from_wkb(r["geometry"]))
            L = g.intersection(self.city_buf).length
            tot += L
            for x in refs:
                if x.startswith(("E ", "AH")):
                    by[x] += L
        return sorted(x for x, v in by.items() if tot and v >= 0.8 * tot)

    def route_concurrency(self, ref):
        """Sections of the Overture route `ref` in the city (city.json polygons). A segment belongs to the route when it carries
        `ref`, or all its international aliases (the other carriageway). It is «concurrent» with another registry road when it also
        carries that road's ref or all that road's aliases (one road with two numbers); «ramp» when it has no name and both ends lie
        on the other registry roads (links of an interchange); else «own». None when the route shares nothing."""
        al = {q: self.route_aliases(q) for q in ROUTE_ROWS}
        net = []
        segs = []
        for r in self.table("segment_major"):
            refs = {(rr.get("ref") or "") for rr in (r.get("routes") or [])}
            mine = ref in refs or (al[ref] and set(al[ref]) <= refs)
            others = sorted(ROUTE_ROWS[q] for q in ROUTE_ROWS if q != ref and (q in refs or (al[q] and set(al[q]) <= refs)))
            if not mine and not others:
                continue
            g = g2u(shapely.from_wkb(r["geometry"]))
            if not g.intersects(self.city_buf):
                continue
            if others and not (ref in refs):
                net.append(g)
            if mine:
                segs.append({"id": r["id"], "g": g, "name": self.ov_name(r), "with": others, "by_ref": ref in refs})
        if not any(s_["with"] for s_ in segs):
            return None
        net = unary_union(net + [s_["g"] for s_ in segs if s_["with"]])
        for s_ in segs:
            if s_["with"]:
                s_["kind"] = "concurrent"
            else:
                a, b = Point(s_["g"].coords[0]), Point(s_["g"].coords[-1])
                s_["kind"] = "ramp" if not s_["name"] and a.distance(net) < 30 and b.distance(net) < 30 else "own"
        trial = self.trial_area()
        out = []
        for key in sorted({(s_["kind"], tuple(s_["with"])) for s_ in segs}, key=lambda k: (("concurrent", "ramp", "own").index(k[0]), k[1])):
            grp = [s_ for s_ in segs if (s_["kind"], tuple(s_["with"])) == key]
            u = unary_union([s_["g"] for s_ in grp])
            ua = unary_union([s_["g"] for s_ in grp if not s_["by_ref"]])
            sec = {"kind": key[0], "with": list(key[1]) or None,
                   "len_km_city": round(u.intersection(self.city_l1).length / 1000, 2),
                   "len_km_trial_area": round(u.intersection(trial).length / 1000, 2) if trial is not None else None,
                   "of_it_other_carriageway_km_city": round(ua.intersection(self.city_l1).length / 1000, 2) if not ua.is_empty else 0.0,
                   "names": sorted({s_["name"] for s_ in grp if s_["name"]}),
                   "overture_segments": sorted(s_["id"][:8] for s_ in grp if s_["g"].intersects(self.city_l1))}
            if key[0] == "own":
                sec["geom"] = gj(linemerge(u.intersection(self.city_buf)).simplify(10.0))
            out.append(sec)
        return {"route_ref": ref, "aliases": al[ref], "sections": out,
                "rule_ru": "сегмент маршрута = несёт его номер или все его международные номера (вторая проезжая часть); «общий» — несёт ещё номер "
                           "(или все международные номера) другой дороги реестра; «съезды развязки» — без названия, оба конца на других дорогах реестра; "
                           "«своя проезжая часть» — остальное. Длины — сумма проезжих частей (у двухпутной дороги ≈ 2 × ось) в полигонах city.json и в area пробной зоны gate_trial.json"}

    def power_lines(self, volt):
        """{overture id: line} of the power lines with this voltage that reach the city (the same set as power())"""
        res = {}
        for r in self.table("infrastructure"):
            if r.get("class") != "power_line":
                continue
            v = str(tagdict(r.get("source_tags")).get("voltage") or "")
            if volt in v.split(";"):
                g = g2u(shapely.from_wkb(r["geometry"]))
                if g.intersects(self.city_buf):
                    res[r["id"]] = g
        return res


def settlement_point(ctx, key):
    did = seed_infra.SETTLEMENTS[key][0]
    _, g = ctx.ov("division", did)
    return g


def resolve(ctx, spec, rows_by_id, meta):
    """Return a shapely geometry (Unity frame) for a geometry spec; meta collects method notes and Overture ids."""
    if spec is None:
        return None
    k = spec[0]
    if k == "twin":
        meta["method"] = "twin_model"
        return Point(spec[1], spec[2])
    if k == "ll":
        meta["method"] = "latlon"
        meta.setdefault("from", []).append("lat %.4f, lon %.4f" % (spec[1], spec[2]))
        return Point(*ll2u(spec[2], spec[1]))
    if k in ("ov", "ovpt"):
        r, g = ctx.ov(spec[1], spec[2])
        meta["method"] = "overture"
        meta.setdefault("overture", []).append({"theme": spec[1], "id": spec[2], "name": ctx.ov_name(r), "class": r.get("class") or r.get("basic_category")})
        if k == "ovpt" and g.geom_type != "Point":
            g = g.representative_point()
        if g.geom_type in ("Polygon", "MultiPolygon"):
            g = g.simplify(2.0)
        return g
    if k == "set":
        did, ru = seed_infra.SETTLEMENTS[spec[1]][0], seed_infra.SETTLEMENTS[spec[1]][1]
        meta["method"] = "settlement"
        meta.setdefault("overture", []).append({"theme": "division", "id": did, "name": ru, "class": "settlement point"})
        return settlement_point(ctx, spec[1])
    if k == "km":
        ch = ctx.km2ch(spec[2])
        meta["method"] = "km_marker"
        meta["km"] = {"road": spec[1], "km": spec[2], "chainage_km": round(ch, 2), "side": spec[3], "offset_m": spec[4]}
        return ctx.on_a3(ch, spec[3], spec[4])
    if k == "ch":
        if spec[2] == "griffin":
            ch, a, b, nxt = ctx.griffin_ch()
            meta["km"] = {"road": "A3", "chainage_km": round(ch, 2), "km_osm": round(ctx.ch2km(ch), 1), "side": spec[3], "offset_m": spec[4],
                          "why": "середина между «1,0 км от узла с БАКАД» (пикет %.2f) и «0,6 км до развязки» (пикет развязки %.2f → %.2f)" % (a, nxt or 0, b)}
        else:
            ch = spec[2]
            meta["km"] = {"road": "A3", "chainage_km": ch, "km_osm": round(ctx.ch2km(ch), 1), "side": spec[3], "offset_m": spec[4]}
        meta["method"] = "km_marker"
        return ctx.on_a3(ch, spec[3], spec[4])
    if k == "mid":
        p1, p2 = resolve(ctx, spec[1], rows_by_id, meta), resolve(ctx, spec[2], rows_by_id, meta)
        meta["method"] = "between"
        return Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    if k == "seg_a3":
        p = resolve(ctx, spec[1], rows_by_id, meta)
        q = ctx.a3.interpolate(ctx.a3.project(p))
        meta["method"] = "between"
        return LineString([p, q])
    if k == "multi":
        ps = [resolve(ctx, s, rows_by_id, meta) for s in spec[1]]
        return MultiPoint(ps)
    if k == "ref":
        meta["method"] = "same_as"
        meta["same_as"] = spec[1]
        return rows_by_id[spec[1]]["_g"]
    if k == "route":
        meta["method"] = "overture_route"
        meta.setdefault("overture", []).append({"theme": "segment", "route_ref": spec[1]})
        if spec[1] == "KAZ08":
            g = ctx.a3
        elif spec[1] == "KZ02-01":
            g = ctx.bakad
        else:
            gs = [g2u(shapely.from_wkb(r["geometry"])) for r in ctx.table("segment_major")
                  if any((rr.get("ref") or "") == spec[1] for rr in (r.get("routes") or []))]
            g = linemerge(unary_union(gs))
        if spec[1] in ROUTE_ROWS:
            sec = ctx.route_concurrency(spec[1])
            if sec:
                meta["concurrency"] = sec
        return ctx.clip(g).simplify(10.0)
    if k == "railname":
        meta["method"] = "overture_rail"
        meta.setdefault("overture", []).append({"theme": "segment", "rail_name_regex": spec[1]})
        g = ctx.railname(spec[1])
        return ctx.clip(g).simplify(10.0) if g is not None else None
    if k == "power":
        meta["method"] = "overture_power"
        meta.setdefault("overture", []).append({"theme": "infrastructure", "class": "power_line", "voltage": spec[1]})
        g = ctx.power(spec[1])
        return ctx.clip(g).simplify(10.0) if g is not None else None
    if k == "a3xbakad":
        meta["method"] = "overture_route"
        meta.setdefault("overture", []).append({"theme": "segment", "route_ref": "KAZ08 x KZ02-01"})
        return ctx.a3xbakad
    if k == "scheme":
        # a place an approved district scheme gives the object: spec[1].json objects[registry_id = spec[2]] «to» (else its footprint centre);
        # spec[3] is the level-0 geometry spec, kept as «было»
        o = next((o for o in ctx.specs[spec[1]].get("objects", []) if o.get("registry_id") == spec[2]), None)
        if o is None or not (o.get("to") or o.get("footprint")):
            raise ValueError("scheme %s has no place for %s" % (spec[1], spec[2]))
        fp = shapely.geometry.Polygon(o["footprint"]) if o.get("footprint") and len(o["footprint"]) > 2 else None
        p = Point(*o["to"][:2]) if o.get("to") else fp.centroid
        meta["method"] = "district_scheme"
        meta["scheme"] = "%s.json objects «%s» (%s)" % (spec[1], spec[2], "to" if o.get("to") else "центр footprint")
        if fp is not None:
            meta["footprint_centre"] = [round(fp.centroid.x, 1), round(fp.centroid.y, 1)]
            meta["footprint_m2"] = round(fp.area)
        if o.get("why"):
            meta["scheme_why"] = o["why"]
        b = spec[3]
        meta["before"] = "было: same_as %s" % b[1] if b[0] == "ref" else "было: %r" % (b,)
        return Point(round(p.x, 1), round(p.y, 1))
    if k == "owner_airport":
        # the new airport by the owner decision of 31.10.2026: the centre of the single runway of city.json airport_new;
        # the level-0 rule point (spec[1]) is kept in geom_details as «было»
        ap = ctx.cityjson["airport_new"]
        rw = LineString(ap["line"])
        c = rw.interpolate(0.5, normalized=True)
        m0 = {}
        p0 = resolve(ctx, spec[1], rows_by_id, m0)
        b = float(ap["bearing_deg"]) % 360.0
        meta["method"] = "owner_decision"
        meta["decision"] = ("решение владельца 31.10.2026 (утверждение схем уровня 0; COMMON_RULES, Stage 7, levels 1–2): новый аэропорт 15 млн пасс./год, "
                            "одна ВПП 4 000 × 45 м, курс 095°/275°, центр (−16000, 1500), после 2040")
        meta["runway"] = {"source": "city.json airport_new", "line": ap["line"], "length_m": round(rw.length, 1), "width_m": ap["width_m"],
                          "bearing_deg": [round(b), round((b + 180.0) % 360.0)], "count": 1, "build_years": ap.get("build_years"), "years": ap.get("years"),
                          "ends_elev_m": ap.get("elev_m_ends")}
        meta["control_point"] = "центр ВПП = geom (по нему считает правило 16, как КТА)"
        meta["before"] = "было: (%s, %s) %s" % (("%.1f" % p0.x).replace("-", "−"), ("%.1f" % p0.y).replace("-", "−"), m0.get("method"))
        meta["before_rule"] = m0.get("rule")
        if m0.get("overture"):                         # the sources stay as they were (the old rule point used Overture Жанаарна)
            meta.setdefault("overture", []).extend(m0["overture"])
        return Point(round(c.x, 1), round(c.y, 1))
    if k == "west_border":
        p = resolve(ctx, spec[1], rows_by_id, meta)
        ray = LineString([(-80000, p.y), (p.x, p.y)])
        x = ray.intersection(ctx.city.boundary)
        pts = [x] if x.geom_type == "Point" else list(getattr(x, "geoms", []))
        w = min(pts, key=lambda q: q.x)
        meta["method"] = "rule_west_border"
        meta["rule"] = "западная граница города (полигон city генплана) на Z точки %s (%.0f), внутрь на %d м" % (spec[1][1], p.y, spec[2])
        meta["west_border_x"] = round(w.x, 1)
        return Point(w.x + spec[2], p.y)
    raise ValueError("unknown geometry spec %r" % (spec,))


def build_rows(ctx):
    seeds = list(seed_objects.ROWS) + list(seed_infra.ROWS)
    # settlements
    for key, (did, ru, en, member, note) in seed_infra.SETTLEMENTS.items():
        srcs = list(seed_infra.SETTLEMENT_SOURCES.get(key, []))
        if member and key != "gate_city":
            srcs = seed_infra.SETTLEMENT_SOURCES["_all12"] + srcs
        seeds.append(dict(id="settlement_" + key, no=None, ru=ru, en=en, type="settlement", district=None,
                          district_inf=seed_infra.SETTLEMENT_DISTRICT_INF.get(key), status="built", years={"start": None, "first_stage": None, "completion": None},
                          cap=None, place=("микрорайон г. Алатау" if member else "соседний населённый пункт (вне 12 микрорайонов)"),
                          geom=("settle_area", key), acc="point_50m", src=srcs, twin="existing_osm дома" if member else "нет",
                          action=("keep", "план: существующие сёла остаются на месте, получают свои улицы; новые дороги их обходят") if member
                          else ("keep", "ориентир вне города; не застраивать"), notes=note, member=member))
    for key, (ru, en, member, note) in seed_infra.SETTLEMENTS_MISSING.items():
        seeds.append(dict(id="settlement_" + key, ru=ru, en=en, type="settlement", district=None, status="built",
                          years={"start": None, "first_stage": None, "completion": None}, cap=None, place="ориентир в описаниях районов",
                          geom=None, acc="none", src=seed_infra.SETTLEMENT_SOURCES.get(key, []), twin="нет",
                          action=("keep", "ориентир; геометрия не найдена"), notes=note, member=member))
    # districts (polygons stay in the genplan geojson / city.json)
    pop = {"gate": "223 тыс.", "golden": "675 тыс.", "growing": "≈ 650 тыс.", "green": "≈ 320 тыс."}
    fn = {"gate": "финансово-деловой центр", "golden": "образование, наука, медицина, спорт", "growing": "промышленность, логистика, транспорт", "green": "туризм, курорт, казино"}
    for k in ("gate", "golden", "growing", "green"):
        seeds.append(dict(id="district_" + k, ru="Район " + k.capitalize(), en=k.capitalize() + " District", type="district", district=k.capitalize(),
                          status="planned", years={"start": 2023, "first_stage": 2030, "completion": 2050},
                          cap="%d га (geojson генплана); жители 2050: %s" % (round(ctx.districts[k].area / 1e4), pop[k]), place=fn[k],
                          geom=None, geom_ref="geojson генплана alatau_plan_utm43n_rel.geojson, слой %s; spec/city.json (w34)" % k, acc="district_only",
                          src=[("S03", "население 2050 по районам"), ("S08", "функция и положение района")], twin="map_districts", action=("keep", "границы районов берём из geojson генплана")))
    # interchanges from OSM link clusters inside the city
    for road, items in ctx.links.items():
        for ch, c, poly in items:
            if not ctx.city.buffer(300).contains(c):
                continue
            if road == "BAKAD" and c.distance(ctx.a3xbakad) < 600:
                continue
            km = ctx.ch2km(ch) if road == "A3" else None
            rid = ("interchange_a3_km%04.1f" % km).replace(".", "_") if road == "A3" else "interchange_bakad_ch%04.1f" % ch
            name = "Развязка А-3 (съезды OSM), км ≈ %.1f" % km if road == "A3" else "Развязка БАКАД (съезды OSM), пикет %.1f км" % ch
            srcs = [("S03", "развязки: А-3 23 (7 существующих), БАКАД 12 (7 существующих)")]
            act = None
            if road == "A3" and c.distance(ctx.a3xbakad) < 500:
                rid, name = "interchange_a3_bakad", "Развязка А-3 × БАКАД"
                srcs += [("S83", "Griffin Logopark на развязке А3 × БАКАД"), ("PLAN", "узел А-3 × БАКАД — полная развязка")]
            elif road == "A3" and abs(ch - ctx.griffin_ch()[3]) < 0.05 if ctx.griffin_ch()[3] else False:
                rid, name = "interchange_a3_yntymak_zhanadaur", "Развязка А-3 × дорога Ынтымак – Жанадаур"
                srcs += [("S82", "0,6 км от Griffin до развязки А3 × дорога Ынтымак – Жанадаур")]
            tw = [z for z in TWIN_INTERCHANGE_ZONES if math.hypot(z[0] - c.x, z[1] - c.y) < 400]
            twin = ("зона развязки film_roads (%.1f, %.1f, r %d)" % tw[0]) if tw else "нет зоны развязки в film_roads"
            act = ("keep", "существующая развязка (OSM)") if tw else ("add", "существующая развязка есть в OSM, в двойнике зоны нет")
            seeds.append(dict(id=rid, ru=name, en=name.replace("Развязка", "Interchange"), type="interchange", district=None, status="built",
                              years={"start": None, "first_stage": None, "completion": None}, cap=None, place="съезды OSM у пикета %.2f км" % ch,
                              geom=("_shape", c), acc="point_50m", src=srcs, twin=twin, action=act,
                              notes="кластер съездов OSM (subclass link в 60 м от оси); какие из них генплан считает существующими (7 на А-3), не сказано"))
    return seeds


def finalize(ctx, seeds):
    rows_by_id = {}
    out = []
    pending = [s for s in seeds if not (s.get("geom") and s["geom"][0] == "ref")] + [s for s in seeds if s.get("geom") and s["geom"][0] == "ref"]
    for s in pending:
        if s["id"] in rows_by_id:
            raise ValueError("duplicate id " + s["id"])
        meta = {}
        g = None
        spec = s.get("geom")
        if spec and spec[0] == "_shape":
            g = spec[1]
            meta["method"] = "overture_links"
        elif spec and spec[0] == "settle_area":
            did = seed_infra.SETTLEMENTS[spec[1]][0]
            r, pt = ctx.ov("division", did)
            ar = ctx.div_area.get(did)
            meta["method"] = "overture"
            meta.setdefault("overture", []).append({"theme": "division", "id": did, "name": ctx.ov_name(r), "class": r.get("subtype")})
            if ar is not None:
                g = g2u(shapely.from_wkb(ar["geometry"])).simplify(5.0)
                meta["overture"].append({"theme": "division_area", "id": ar["id"], "name": ctx.ov_name(ar), "class": ar.get("subtype")})
                meta["label_point"] = [round(pt.x, 1), round(pt.y, 1)]
            else:
                g = pt
        else:
            g = resolve(ctx, spec, rows_by_id, meta)
        s["_g"] = g
        s["_meta"] = meta
        rows_by_id[s["id"]] = s
        out.append(s)
    # restore seed order
    order = {s["id"]: i for i, s in enumerate(seeds)}
    out.sort(key=lambda s: order[s["id"]])
    return out, rows_by_id


def aviation(ctx, s, rows_by_id):
    h = s.get("height_m")
    fl = s.get("floors")
    if not h and not fl:
        return None
    g = s["_g"]
    tall = (h and h >= 50) or (fl and fl >= 15)
    res = {"height_m": h, "floors": fl, "tall_50m": bool(tall), "basis": "высота из источника" if h else "этажность ≥ 15 ⇒ вероятно ≥ 50 м (вывод)"}
    if g is None:
        res["needs_approval"] = "проверить после размещения"
        return res
    p = g if g.geom_type == "Point" else g.representative_point()
    cp = Point(*ll2u(77.1206, 43.7317))
    ap = ctx.airport_cp
    d1, d2 = p.distance(cp) / 1000.0, p.distance(ap) / 1000.0
    res.update({"km_to_zhetygen_airfield_cp": round(d1, 1), "km_to_alatau_airport_model": round(d2, 1),
                "airport_point": "центр ВПП нового аэропорта (city.json height_limits alatau_new, −16000, 1500)",
                "needs_approval": bool(tall and (d1 <= 30 or d2 <= 30))})
    return res


def to_json(ctx, rows, rows_by_id):
    res = []
    for s in rows:
        srcs = []
        for code, claim in s.get("src") or []:
            srcs.append(ctx.src(code, claim))
        meta = s["_meta"]
        if meta.get("overture"):
            names = ["%s %s%s" % (o.get("theme"), o.get("id") or o.get("route_ref") or o.get("rail_name_regex") or o.get("voltage"),
                                  (" «%s»" % o["name"]) if o.get("name") else "") for o in meta["overture"]]
            srcs.append(ctx.ovt("геометрия: " + "; ".join(names)))
        if meta.get("method") == "overture_links":
            srcs.append(ctx.ovt("геометрия: центр кластера съездов (segment subclass=link) у оси"))
        chips = []
        act0 = (s.get("action") or (None,))[0]
        if s.get("model") or act0 == "by_rule":                      # placed by rule = a qTwin model place, whatever its sources
            chips.append(MODEL_CHIP)
        if s.get("id") == "metro_line3_reserve":
            chips.append("модель, решение не принято")
        if not srcs and MODEL_CHIP not in chips:
            raise ValueError("row %s has neither a source nor the model chip" % s["id"])
        if not srcs:
            srcs = []
        g = s["_g"]
        conflicts = []
        for c in s.get("conflicts") or []:
            cc = dict(c)
            cc["claims"] = [dict(x, **({"url": ctx.src(x["source"], "")["url"]} if x["source"] in ctx.S or x["source"] in EXT else {})) for x in c["claims"]]
            conflicts.append(cc)
        act = s.get("action")
        row = {
            "id": s["id"],
            "research_no": s.get("no"),
            "parent": s.get("parent"),
            "name_ru": s["ru"],
            "name_en": s["en"],
            "type": s["type"],
            "district": s.get("district"),
            "district_inferred": s.get("district_inf"),
            "district_geom": ctx.district_of(g),
            "district_area": ctx.area_of(g),
            "district_genplan": ctx.district_genplan(g),
            "status": s["status"],
            "years": s.get("years") or {"start": None, "first_stage": None, "completion": None},
            "capacity": s.get("cap"),
            "place": s.get("place"),
            "geom": gj(g),
            "geom_frame": "unity_xz_m" if g is not None else None,
            "geom_method": meta.get("method"),
            "geom_details": {k: v for k, v in meta.items() if k not in ("method", "overture")} or None,
            "geom_ref": s.get("geom_ref"),
            "anchor": s.get("anchor"),
            "accuracy": s["acc"],
            "sources": srcs,
            "chips": chips,
            "twin_now": s.get("twin"),
            "action": {"do": act[0], "reason": act[1]} if act else None,
            "conflicts": conflicts,
            "on_map": s.get("on_map", True),
            "plan_named": s["id"] in PLAN_NAMED,
            "notes": s.get("notes"),
        }
        av = aviation(ctx, s, rows_by_id)
        if av:
            row["aviation"] = av
        if s.get("points"):
            row["points"] = {k: gj(resolve(ctx, v, rows_by_id, {})) for k, v in s["points"].items()}
        for k in ("type", "status", "accuracy"):
            pass
        assert row["type"] in TYPES, row["id"]
        assert row["status"] in STATUSES, row["id"]
        assert row["accuracy"] in ACCURACY, row["id"]
        assert row["action"]["do"] in ACTIONS, row["id"]
        res.append(row)
    return res


def scheme_link(ctx, rows):
    """Level 1 (w42): every row gets the place the approved district schemes give it (objects of the five specs).
    scheme: all spec entries; scheme_to / scheme_action / scheme_area: the owner entry = the spec whose own area holds its `to`
    (else an entry that moves or adds, else the spec of the row's district). Entries that disagree by > 50 m are listed."""
    ent = collections.defaultdict(list)
    for d in SPEC_IDS:
        for o in ctx.specs[d].get("objects", []):
            ent[o["registry_id"]].append((d, o))
    conflicts = []
    for r in rows:
        es = ent.get(r["id"], [])
        r["scheme"] = [{"spec": d, "action": o.get("action"), "to": o.get("to"), "yaw": o.get("yaw"),
                        **({"years": o["years"]} if o.get("years") else {})} for d, o in es]
        owner = None
        own = [(d, o) for d, o in es if o.get("to") and ctx.careas[d].contains(Point(*o["to"]))]
        if len(own) == 1:
            owner = own[0]
        elif len(own) > 1:
            mv = [(d, o) for d, o in own if o.get("action") in ("move", "add")]
            owner = (mv or own)[0]
        elif es:
            mv = [(d, o) for d, o in es if o.get("action") in ("move", "add") and o.get("to")]
            same = [(d, o) for d, o in es if d == r.get("district_area")]
            owner = (mv or same or es)[0]
        r["scheme_to"] = owner[1].get("to") if owner else None
        r["scheme_action"] = owner[1].get("action") if owner else None
        r["scheme_spec"] = owner[0] if owner else None
        r["scheme_area"] = ctx.area_of(Point(*r["scheme_to"])) if r["scheme_to"] else None
        tos = [(d, o.get("to"), o.get("action")) for d, o in es if o.get("to")]
        far = [(a, b) for i, a in enumerate(tos) for b in tos[i + 1:] if math.dist(a[1], b[1]) > 50.0]
        acts = sorted(set(o.get("action") for _, o in es))
        if far or len(acts) > 1:
            c = {"id": r["id"], "entries": [{"spec": d, "action": a, "to": t} for d, t, a in tos] +
                 [{"spec": d, "action": o.get("action"), "to": None} for d, o in es if not o.get("to")],
                 "owner": r["scheme_spec"], "max_apart_m": round(max((math.dist(a[1], b[1]) for a, b in far), default=0.0))}
            r["scheme_conflict"] = c
            conflicts.append(c)
    return conflicts


def hv_segments(ctx, rows, by, conflicts):
    """Level 1 (w42b): hv_lines_220 line by line and district by district, as the approved schemes draw them under the owner
    decision of 31.10.2026 (220 kV through the Gate and Golden centres into cable or round the core). A line part is «cable» where
    a spec's utilities[] lays a 220 kV cable that replaces that OSM line, else it stays overhead in its protection corridor.
    The centre (ядро) of a spec = its zones with use mixed_centre / business; an overhead part inside it is listed as open."""
    r = by.get("hv_lines_220")
    if r is None:
        return
    lines = ctx.power_lines("220000")
    cable = {}
    for d in SPEC_IDS:
        for u in ctx.specs[d].get("utilities", []):
            if u.get("kind") == "power_cable_220kv" and str(u.get("replaces", "")).startswith("osm:"):
                cable[(u["replaces"][4:], d)] = u
    segs, open_ = [], []
    for oid, g in sorted(lines.items()):
        for d in SPEC_IDS:
            part = g.intersection(ctx.careas[d])
            if part.length < 1.0:
                continue
            core = unary_union([shapely.geometry.Polygon(z["polygon"]).buffer(0) if isinstance(z["polygon"][0][0], (int, float))
                                else shapely.geometry.Polygon(z["polygon"][0], z["polygon"][1:]).buffer(0)
                                for z in ctx.specs[d].get("zones", []) if z.get("use") in CORE_USES and z.get("polygon")])
            in_core = part.intersection(core).length if not core.is_empty else 0.0
            u = cable.get((oid, d))
            if u:
                sg = {"osm": oid[:8], "district": d, "state": "cable", "len_km": round(part.length / 1000, 2),
                      "in_core_km": round(in_core / 1000, 2), "cable": "%s.json#utilities/%s" % (d, u["id"]),
                      "cable_len_km": round(LineString(u["line"]).length / 1000, 2), "years": u.get("years"), "why_ru": u.get("why")}
            else:
                sg = {"osm": oid[:8], "district": d, "state": "overhead", "len_km": round(part.length / 1000, 2),
                      "in_core_km": round(in_core / 1000, 2), "years": [2025] * 4,
                      "why_ru": "остаётся воздушной в охранном коридоре (схема %s: hv_lines_220 «%s»)"
                                % (d, next((o.get("action") for o in ctx.specs[d].get("objects", []) if o.get("registry_id") == "hv_lines_220"), "нет строки"))}
                if in_core >= 1.0:
                    open_.append(sg)
            segs.append(sg)
    # a power=line without voltage through a Gate/Golden centre (the twin or a scheme may read it as 220 kV)
    unk = []
    for d in ("gate", "golden"):
        core = unary_union([shapely.geometry.Polygon(z["polygon"]).buffer(0) if isinstance(z["polygon"][0][0], (int, float))
                            else shapely.geometry.Polygon(z["polygon"][0], z["polygon"][1:]).buffer(0)
                            for z in ctx.specs[d].get("zones", []) if z.get("use") in CORE_USES and z.get("polygon")])
        for t in ctx.table("infrastructure"):
            if t.get("class") != "power_line" or tagdict(t.get("source_tags")).get("voltage"):
                continue
            g = g2u(shapely.from_wkb(t["geometry"]))
            L = g.intersection(core).length if g.intersects(core) else 0.0
            if L >= 100.0:
                unk.append({"osm": t["id"][:8], "district": d, "len_km": round(g.intersection(ctx.careas[d]).length / 1000, 2), "in_core_km": round(L / 1000, 2),
                            "what_ru": "линия OSM power=line без напряжения через ядро %s; если это 220 кВ (так читает её схема), по решению владельца — "
                                       "в кабель или в обход ядра; трассу задаёт схема района" % d})
    by_d = collections.defaultdict(lambda: collections.Counter())
    for sg in segs:
        by_d[sg["district"]][sg["state"]] += sg["len_km"]
    r["action"]["segments"] = segs
    r["action"]["summary_km"] = {d: {k: round(v, 2) for k, v in c.items()} for d, c in by_d.items()}
    r["action"]["core_rule"] = "ядро района = зоны спецификации с use %s; кабель = utilities[] kind power_cable_220kv с replaces этой линии OSM" % " / ".join(CORE_USES)
    r["action"]["overhead_in_core"] = open_
    r["action"]["unknown_voltage_in_core"] = unk
    chk = []
    for d in ("gate", "golden"):
        cab = sum(sg["in_core_km"] for sg in segs if sg["district"] == d and sg["state"] == "cable")
        ovh = sum(sg["in_core_km"] for sg in segs if sg["district"] == d and sg["state"] == "overhead")
        uk = [u for u in unk if u["district"] == d]
        t = "%s: ВЛ 220 кВ (OSM voltage=220000) в ядре %.2f км, из них в кабеле %.2f км, воздушных %.2f км" % (d, cab + ovh, cab, ovh) if cab + ovh else \
            "%s: ВЛ 220 кВ (OSM voltage=220000) ядро не пересекают" % d
        if uk:
            t += "; линия без напряжения %s проходит ядро %.2f км — открыто, трассу задаёт схема %s" % (", ".join(u["osm"] for u in uk), sum(u["in_core_km"] for u in uk), d)
        chk.append(t)
    r["action"]["decision_check_ru"] = chk
    # the schemes agree when a spec says reroute exactly where it lays a cable and keep elsewhere
    cab_d = {sg["district"] for sg in segs if sg["state"] == "cable"}
    bad = [e for e in r["scheme"] if (e["action"] == "reroute") != (e["spec"] in cab_d)]
    r["scheme_action"] = "reroute" if cab_d else r["scheme_action"]
    r["scheme_spec"] = ",".join(sorted(cab_d)) if cab_d else r["scheme_spec"]
    if not bad:
        r.pop("scheme_conflict", None)
        conflicts[:] = [c for c in conflicts if c["id"] != "hv_lines_220"]
    r["scheme_check"] = {"agree": not bad, "rule": "reroute в схеме ⇔ схема кладёт кабель 220 кВ в своём районе; keep ⇔ все участки района воздушные",
                         "disagree": [e["spec"] for e in bad]}


def flag_rows(ctx, rows, by):
    """Level 1 (w42): rows the approved schemes found odd. Flagged with a measured fact, not moved."""
    import pandas as pd
    flags = []
    def add(rid, code, what, by_, measured):
        r = by.get(rid)
        if r is None:
            return
        f = {"code": code, "what_ru": what, "by": by_, "measured": measured}
        r.setdefault("flags", []).append(f)
        if code in ("inside_interchange",) and MODEL_CHIP not in r["chips"]:   # the scheme sets the exact place inside the source accuracy
            r["chips"].append(MODEL_CHIP)
        flags.append({"id": rid, **f})
    # PepsiCo: the source point (centre of Yntymak) stands on village houses
    r = by.get("pepsico")
    if r and r["geom"] and r["geom"]["type"] == "Point":
        x, z = r["geom"]["coordinates"]
        p = Point(x, z)
        B = pd.read_csv(ctx.a.buildings, usecols=["bid", "x", "z", "source"])
        ex = B[B.source == "existing_osm"]
        d = ((ex.x - x) ** 2 + (ex.z - z) ** 2) ** 0.5
        ov = []
        if os.path.exists(ctx.a.osm_buildings):
            for ft in json.load(open(ctx.a.osm_buildings, encoding="utf-8"))["features"]:
                c0 = ft["geometry"]["coordinates"][0]
                c0 = c0[0] if isinstance(c0[0][0], list) else c0
                if abs(c0[0][0] - x) > 400 or abs(c0[0][1] - z) > 400:
                    continue
                ov.append(shapely.geometry.shape(ft["geometry"]).distance(p))
        ov = sorted(ov)
        add("pepsico", "point_on_houses", "точка источника (центр мкр Ынтымак) стоит среди домов села; завод ставится по схеме Gate на корпус OSM 28 043 м²",
            "схема gate (objects pepsico)", {"overture_buildings_within_50m": sum(1 for v in ov if v <= 50), "within_100m": sum(1 for v in ov if v <= 100),
                                              "nearest_overture_building_m": round(ov[0], 1) if ov else None,
                                              "twin_existing_osm_within_100m": int((d <= 100).sum()),
                                              "source": "OUT/osm/buildings.geojson уровня 0 (Overture 2026-10-21.0: OSM + Microsoft ML Buildings)"})
    # agglomeration rail station 1: the point is the A-3 × BAKAD crossing itself, inside the cloverleaf
    r = by.get("agglo_rail_station_1"); ic = by.get("interchange_a3_bakad")
    if r and ic and r["geom"] and ic["geom"]:
        p = Point(*r["geom"]["coordinates"]); q = Point(*ic["geom"]["coordinates"])
        add("agglo_rail_station_1", "inside_interchange", "точка = пересечение осей А-3 и БАКАД, внутри клеверной развязки; станция по схеме Gate — ТПУ у развязки",
            "схема gate (objects agglo_rail_station_1)", {"to_interchange_centre_m": round(p.distance(q), 1), "interchange": "interchange_a3_bakad",
                                                          "twin_interchange_zone_r_m": 378})
    # TLC Zhetygen: the OSM outline lies mostly in Green
    r = by.get("tlc_zhetygen")
    if r and r["geom"] and r["geom"]["type"] in ("Polygon", "MultiPolygon"):
        g = shapely.geometry.shape(r["geom"])
        sh = {k: round(g.intersection(ctx.careas[k]).area / g.area * 100, 1) for k in SPEC_IDS if g.intersects(ctx.careas[k])}
        add("tlc_zhetygen", "outline_across_border", "контур OSM «ТЛЦ Логистика» лежит больше чем наполовину в Green, а объект ставит Growing-восток",
            "схемы growing_e и green (objects tlc_zhetygen)", {"share_pct_by_area": sh, "area_ha": round(g.area / 1e4, 1)})
    return flags


def twin_unmatched(ctx, rows):
    """film_roads interchange zones with no OSM interchange row within 400 m"""
    ic = [Point(*r["geom"]["coordinates"]) for r in rows if r["type"] == "interchange" and r["geom"] and r["geom"]["type"] == "Point"]
    allc = [c for items in ctx.links.values() for _, c, _ in items]
    out = []
    for x, z, rad in TWIN_INTERCHANGE_ZONES:
        p = Point(x, z)
        if any(p.distance(q) < 400 for q in ic):
            continue
        near = min(p.distance(c) for c in allc) if allc else None
        out.append({"x": x, "z": z, "r": rad, "to_a3_m": round(p.distance(ctx.a3)), "to_bakad_m": round(p.distance(ctx.bakad)),
                    "nearest_osm_links_m": round(near) if near is not None else None, "in_city": bool(ctx.city.contains(p)),
                    "verdict": ("реальная развязка OSM вне города: контекст" if near is not None and near < 400 and not ctx.city.contains(p)
                                else "реальная развязка OSM" if near is not None and near < 400
                                else "только в двойнике: по матрице узлов или убрать")})
    return out


def report(ctx, rows, path, doc=None):
    L = []
    w = L.append
    w("# Реестр реальных объектов Alatau City — отчёт (уровень 0 w35, уровень 1 w42)\n")
    w("Собран `tools/map/registry/build_registry.py` из `research/alatau_objects.md`, `research/transport_site.md`, "
      "кода двойника и Overture %s. Координаты — Unity X/Z (X = E − 663000, Z = N − 4830000, UTM 43N). %s.\n" % (OVERTURE_RELEASE, ATTRIBUTION))
    w("Всего строк: **%d**; на карте (on_map): %d; названы в плане: %d.\n" % (len(rows), sum(r["on_map"] for r in rows), sum(r["plan_named"] for r in rows)))
    f = ctx.km_fit
    w("Километраж А-3: по %d столбам OSM (из %d в 150 м от оси) км = %.4f × пикет + %.3f, СКО %.2f км; "
      "пикет — расстояние по пути KAZ08 от его южного конца. Узел А-3 × БАКАД: пикет %.2f км, км ≈ %.1f; точка (%.1f, %.1f).\n"
      % (f["n"], f["n_all"], f["a"], f["b"], f["sd_km"], ctx.ch_x, ctx.ch2km(ctx.ch_x), ctx.a3xbakad.x, ctx.a3xbakad.y))

    def table(title, key, fn=None):
        c = collections.Counter((fn or (lambda r: r[key]))(r) for r in rows)
        w("\n## %s\n\n| %s | строк |\n|---|---|" % (title, key))
        for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0]))):
            w("| %s | %d |" % (k, v))
    table("По району из источника (district; пусто = источник не называет)", "district", lambda r: r["district"] or "—")
    table("По району, выведенному исследованием (district_inferred)", "district_inferred", lambda r: r["district_inferred"] or "—")
    table("По району по геометрии (district_geom, полигоны city.json — контуры двойника, уровень 1)", "district_geom", lambda r: (r["district_geom"] or "нет геометрии").split(" (")[0])
    table("По району спецификации (district_area: половины Growing)", "district_area", lambda r: r["district_area"] or ("нет геометрии" if r["geom"] is None else "вне районов"))
    table("По месту схемы (scheme_area)", "scheme_area", lambda r: r["scheme_area"] or ("нет в схемах" if not r["scheme"] else "нет точки в схеме"))
    table("По действию схемы (scheme_action)", "scheme_action", lambda r: r["scheme_action"] or "нет в схемах")
    if doc:
        lv = doc["level1"]
        w("\n## Уровень 1: район до и после (district_geom)\n")
        w("До — уровень 0, полигоны geojson генплана; после — полигоны city.json (контуры двойника).\n")
        b0 = lv["before"]["by_district_geom_level0"] or doc["counts"]["by_district_genplan_level0"]
        b1 = doc["counts"]["by_district_geom"]
        w("| район | до | после |\n|---|---|---|")
        for k in sorted(set(b0) | set(b1), key=lambda k: -(b1.get(k, 0))):
            w("| %s | %d | %d |" % (k, b0.get(k, 0), b1.get(k, 0)))
        moved = [r for r in rows if (r["district_genplan"] or "").split(" (")[0] != (r["district_geom"] or "").split(" (")[0]]
        w("\nСтрок, у которых район сменился: %d.\n" % len(moved))
        w("| id | было (генплан) | стало (city.json) | половина |\n|---|---|---|---|")
        for r in moved:
            w("| %s | %s | %s | %s |" % (r["id"], r["district_genplan"], r["district_geom"], r["district_area"] or "—"))
        w("\n## Уровень 1: флаги (строки не перенесены)\n")
        for f in lv["flags"]:
            w("- **%s** — %s (%s); замер: %s" % (f["id"], f["what_ru"], f["by"], json.dumps(f["measured"], ensure_ascii=False)))
        conc = [r for r in rows if (r.get("geom_details") or {}).get("concurrency")]
        if conc:
            w("\n## Уровень 1: дороги на общих проезжих частях (одна дорога с двумя номерами — не ошибка)\n")
            w("| id | участок | вместе с | км в городе | км в пробной зоне Gate | названия OSM |\n|---|---|---|---|---|---|")
            for r in conc:
                for c in r["geom_details"]["concurrency"]["sections"]:
                    w("| %s | %s | %s | %.2f | %s | %s |" % (r["id"], {"concurrent": "общий", "ramp": "съезды развязки", "own": "своя проезжая часть"}[c["kind"]],
                                                         ", ".join(c["with"] or []) or "—", c["len_km_city"],
                                                         "—" if c["len_km_trial_area"] is None else "%.2f" % c["len_km_trial_area"], "; ".join(c["names"]) or "—"))
        hv = next((r for r in rows if r["id"] == "hv_lines_220" and r["action"].get("segments")), None)
        if hv:
            a_ = hv["action"]
            w("\n## Уровень 1: ВЛ 220 кВ по участкам (решение владельца 31.10.2026: через центры Gate и Golden — в кабель или в обход ядра)\n")
            w("| линия OSM | район | состояние | км | в ядре, км | кабель | годы |\n|---|---|---|---|---|---|---|")
            for sg in a_["segments"]:
                w("| %s | %s | %s | %.2f | %.2f | %s | %s |" % (sg["osm"], sg["district"], {"cable": "кабель", "overhead": "воздушная"}[sg["state"]], sg["len_km"],
                                                          sg["in_core_km"], sg.get("cable") or "—", sg["years"]))
            w("\nСводка, км: %s. Схемы согласны: %s. Правило: %s." % (json.dumps(a_["summary_km"], ensure_ascii=False), "да" if hv["scheme_check"]["agree"] else
                                                         "нет (%s)" % ", ".join(hv["scheme_check"]["disagree"]), a_["core_rule"]))
            for t in a_["decision_check_ru"]:
                w("- %s" % t)
            for sg in a_["overhead_in_core"]:
                w("- открыто: воздушная %s в ядре %s, %.2f км" % (sg["osm"], sg["district"], sg["in_core_km"]))
            for u in a_["unknown_voltage_in_core"]:
                w("- открыто: %s (%s, в ядре %.2f км)" % (u["what_ru"], u["osm"], u["in_core_km"]))
        w("\n## Уровень 1: схемы расходятся в месте или действии\n")
        w("| id | владелец | записи схем | разнос, м |\n|---|---|---|---|")
        for c in lv["scheme_conflicts"]:
            w("| %s | %s | %s | %d |" % (c["id"], c["owner"] or "—", "; ".join("%s: %s %s" % (e["spec"], e["action"], e["to"] or "") for e in c["entries"]), c["max_apart_m"]))
        far = [r for r in rows if r["scheme_to"] and r["geom"] and r["geom"]["type"] == "Point" and math.dist(r["scheme_to"], r["geom"]["coordinates"]) > 50]
        w("\n## Уровень 1: место схемы отличается от места реестра (> 50 м)\n")
        w("| id | реестр (geom) | схема (scheme_to) | действие | схема-владелец | район схемы |\n|---|---|---|---|---|---|")
        for r in far:
            w("| %s | %.0f, %.0f | %.0f, %.0f | %s | %s | %s |" % (r["id"], r["geom"]["coordinates"][0], r["geom"]["coordinates"][1], r["scheme_to"][0], r["scheme_to"][1],
                                                            r["scheme_action"], r["scheme_spec"], r["scheme_area"]))
        nos = [r for r in rows if not r["scheme"] and r["on_map"]]
        w("\n## Уровень 1: строки на карте, которых нет ни в одной схеме (%d)\n" % len(nos))
        w("| id | тип | район (city.json) | действие реестра |\n|---|---|---|---|")
        for r in nos:
            w("| %s | %s | %s | %s |" % (r["id"], r["type"], r["district_area"] or r["district_geom"] or "—", r["action"]["do"]))
    table("По типу", "type")
    table("По статусу", "status")
    table("По действию", "action", lambda r: r["action"]["do"])
    table("По точности", "accuracy")

    w("\n## Расхождение района: источник/вывод против полигона city.json\n")
    w("| id | район источника | вывод | по геометрии |\n|---|---|---|---|")
    for r in rows:
        dg = (r["district_geom"] or "")
        if not dg or r["accuracy"] == "none" or r["geom_method"] == "twin_model":
            continue
        for d in (r["district"], r["district_inferred"]):
            if d and dg and d.split(" ")[0] not in dg and "/" not in d and " и " not in d:
                w("| %s | %s | %s | %s |" % (r["id"], r["district"] or "—", r["district_inferred"] or "—", dg))
                break

    w("\n## Все расхождения источников (кто побеждает и почему)\n")
    for r in rows:
        for c in r["conflicts"]:
            claims = "; ".join("%s: %s" % (x["source"], x["says"]) for x in c["claims"])
            w("- **%s** — %s. %s → побеждает **%s**: %s" % (r["id"], c["topic"], claims, c["wins"], c["why"]))

    w("\n## Объекты, которые называет план, а исследование не ставит в точку\n")
    w("Точность `none` или `district_only` (место — по правилу) или нет геометрии. Генератор ставит их по norms.json / rules.json с чипом «модель qTwin».\n")
    w("Колонка «геометрия сейчас»: `twin_model` — точка/контур двойника с чипом «модель qTwin» (не источник); `нет` — генератор ставит по правилу.\n")
    w("| id | имя | точность | геометрия сейчас | действие | что известно о месте |\n|---|---|---|---|---|---|")
    for r in rows:
        if r["plan_named"] and (r["accuracy"] in ("none", "district_only") or r["geom"] is None) and not r["geom_ref"]:
            w("| %s | %s | %s | %s | %s | %s |" % (r["id"], r["name_ru"], r["accuracy"], r["geom_method"] if r["geom"] else "нет", r["action"]["do"], (r["place"] or "—").replace("|", "/")))

    w("\n## Прочие объекты на карте без места (geom null, не по ссылке на city.json)\n")
    w("| id | имя | статус | действие |\n|---|---|---|---|")
    for r in rows:
        if r["on_map"] and r["geom"] is None and not r["geom_ref"] and not r["plan_named"]:
            w("| %s | %s | %s | %s |" % (r["id"], r["name_ru"], r["status"], r["action"]["do"]))

    w("\n## Высотки в 30 км от аэродрома / будущего аэропорта (правило №16)\n")
    for r in rows:
        if r.get("aviation"):
            a = r["aviation"]
            w("- %s: %s; до КТА Жетыген %s км, до модели аэропорта %s км → нужно согласование: %s"
              % (r["id"], a["basis"], a.get("km_to_zhetygen_airfield_cp"), a.get("km_to_alatau_airport_model"), a["needs_approval"]))

    w("\n## Зоны развязок двойника (film_roads) без съездов OSM в городе\n")
    w("Строки реестра для них нет: развязка у съездов OSM вне полигона города — реальная, но за пределами города (контекст карты); "
      "зона без съездов OSM — только модель двойника, генератор решает её по матрице узлов norms.json или убирает.\n")
    w("| x | z | r | до оси А-3, м | до оси БАКАД, м | ближайший кластер съездов OSM, м | в полигоне города | вывод |\n|---|---|---|---|---|---|---|---|")
    for z in twin_unmatched(ctx, rows):
        w("| %.1f | %.1f | %d | %d | %d | %s | %s | %s |" % (z["x"], z["z"], z["r"], z["to_a3_m"], z["to_bakad_m"], z["nearest_osm_links_m"],
                                                         "да" if z["in_city"] else "нет", z["verdict"]))

    w("\n## Объекты двойника, которые переезжают (action = move)\n")
    for r in rows:
        if r["action"]["do"] == "move" and r["geom"] and r["geom"]["type"] == "Point":
            w("- %s: было «%s» → стало (%.0f, %.0f), %s; %s" % (r["id"], r["twin_now"], r["geom"]["coordinates"][0], r["geom"]["coordinates"][1], r["district_geom"], r["action"]["reason"]))
        elif r["action"]["do"] == "move":
            w("- %s: было «%s» → контур OSM, %s; %s" % (r["id"], r["twin_now"], r["district_geom"], r["action"]["reason"]))
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--research", default="/mnt/project-files/alatau_stage7/research")
    ap.add_argument("--overture", default="/mnt/project-files/alatau_stage7/level0/w35/overture")
    ap.add_argument("--genplan", default="/mnt/user-data/uploads/Downloads/alatau_maket/alatau_plan_utm43n_rel.geojson")
    ap.add_argument("--out", default=os.path.normpath(os.path.join(HERE, "..", "spec")))
    ap.add_argument("--city", default=os.path.normpath(os.path.join(HERE, "..", "spec", "city.json")), help="city.json (district polygons, airport)")
    ap.add_argument("--specs", default=os.path.normpath(os.path.join(HERE, "..", "spec")), help="folder with the five district specs")
    ap.add_argument("--buildings", default="/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/Assets/CityData/buildings.csv")
    ap.add_argument("--osm-buildings", dest="osm_buildings", default="/mnt/project-files/alatau_stage7/level0/w34/osm/buildings.geojson")
    a = ap.parse_args()
    ctx = Ctx(a)
    seeds = build_rows(ctx)
    rows, rows_by_id = finalize(ctx, seeds)
    out = to_json(ctx, rows, rows_by_id)
    by = {r["id"]: r for r in out}
    sconf = scheme_link(ctx, out)
    hv_segments(ctx, out, by, sconf)
    flags = flag_rows(ctx, out, by)
    f = ctx.km_fit
    doc = {
        "schema": "qtwin.registry/1",
        "level": 1,
        "made_by": "w35 (уровень 0), w42 (уровень 1: районы по city.json, места схем, флаги), tools/map/registry/build_registry.py",
        "date": "2026-10-31",
        "frame": {"name": "unity_xz_m", "x": "E − 663000 (UTM 43N, EPSG:32643)", "z": "N − 4830000", "from_latlon": "pyproj EPSG:4326 → EPSG:32643, always_xy",
                  "genplan_shift": {"dx": ctx.genplan_shift[0], "dz": ctx.genplan_shift[1], "note": "x = x_rel + dx, z = y_rel + dz (origin_utm43n)"}},
        "overture_release": OVERTURE_RELEASE,
        "attribution": ATTRIBUTION,
        "a3_km_fit": {"km = a × chainage_km + b": True, "a": round(f["a"], 5), "b": round(f["b"], 3), "milestones_used": f["n"], "sd_km": round(f["sd_km"], 2),
                      "chainage_origin": "южный конец пути KAZ08 в выгрузке (%.0f, %.0f)" % ctx.a3.coords[0],
                      "a3_x_bakad": {"x": round(ctx.a3xbakad.x, 1), "z": round(ctx.a3xbakad.y, 1), "chainage_km": round(ctx.ch_x, 2)}},
        "vocab": {"type": TYPES, "status": STATUSES, "accuracy": ACCURACY, "action": ACTIONS,
                  "chips": {MODEL_CHIP: "место или объект задан правилом/моделью двойника, а не источником",
                            "модель, решение не принято": "резерв без решения (метро)"},
                  "district": "как называет источник; null — источник не называет (тогда см. district_inferred — вывод исследования — и district_geom — по полигонам генплана)",
                  "tolerances": {"point_50m": 50, "road_km_500m": 500, "settlement_1km": 1000},
                  "moved_reference": "для объектов с action=move эталон — новое место (geom)"},
        "counts": {"rows": len(out), "on_map": sum(r["on_map"] for r in out), "plan_named": sum(r["plan_named"] for r in out),
                   "by_district_source": dict(collections.Counter(r["district"] or "—" for r in out).most_common()),
                   "by_district_geom": dict(collections.Counter((r["district_geom"] or "нет геометрии").split(" (")[0] for r in out).most_common()),
                   "by_district_area": dict(collections.Counter(r["district_area"] or ("нет геометрии" if r["geom"] is None else "вне районов") for r in out).most_common()),
                   "by_district_genplan_level0": dict(collections.Counter((r["district_genplan"] or "нет геометрии").split(" (")[0] for r in out).most_common()),
                   "by_scheme_area": dict(collections.Counter(r["scheme_area"] or ("нет в схемах" if not r["scheme"] else "нет точки в схеме") for r in out).most_common()),
                   "by_scheme_action": dict(collections.Counter(r["scheme_action"] or "нет в схемах" for r in out).most_common()),
                   "by_type": dict(collections.Counter(r["type"] for r in out).most_common()),
                   "by_status": dict(collections.Counter(r["status"] for r in out).most_common()),
                   "by_action": dict(collections.Counter(r["action"]["do"] for r in out).most_common()),
                   "by_accuracy": dict(collections.Counter(r["accuracy"] for r in out).most_common())},
        "twin_interchange_zones_without_osm": twin_unmatched(ctx, out),
        "level1": {"district_geom": "район по полигонам city.json (контуры двойника, уровень 1); district_area — район спецификации (половины Growing); "
                                    "district_genplan — прежний район по полигонам geojson генплана (уровень 0)",
                   "scheme": "scheme — все строки objects пяти утверждённых схем с этим registry_id; scheme_to / scheme_action / scheme_spec — место "
                             "владельца (схема, в своём районе которой стоит её to; иначе схема, которая переносит или добавляет); "
                             "scheme_area — район места схемы; geom остаётся местом источника",
                   "flags": flags, "scheme_conflicts": sconf,
                   "before": {"by_district_geom_level0": dict(collections.Counter((r["district_genplan"] or "нет геометрии").split(" (")[0] for r in out).most_common()),
                              "note": "уровень 0 считал district_geom по полигонам geojson генплана; это те же числа, пересчитанные тем же правилом"}},
        "rows": out,
    }
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "registry.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    report(ctx, out, os.path.join(a.out, "registry_report.md"), doc)
    print("rows", len(out), "km fit", {k: round(v, 4) if isinstance(v, float) else v for k, v in f.items()})


if __name__ == "__main__":
    main()
