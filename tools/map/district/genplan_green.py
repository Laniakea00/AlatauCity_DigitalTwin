"""Green by the master plan drawing (decree 727, 2025; owner 09.11.2026: «соответствовать к генплану обязаны»).

Polygons read off the drawing laid over the twin's frame (outline match 98 %, 38.5 m per pixel, about ±300 m):
  - the city on the north shore, between Konaev and the bay, down to the water (the drawing's shore is the 479 m level);
  - the round resort on the east shore (the Unity model «ring_resort» stands on z_ring, see green_build.py) with hotels round it;
  - the big oval of the racing circuit, the golf course in the smaller oval east of it, the theme park on the shore west of the resort;
  - the gardens west of the city in place of the office belt by the railway.
apply() takes the zone list of green_zones.plan() [(zone, polygon)] and returns it cut by these polygons.
"""
from shapely.affinity import scale
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

MODEL = "модель qTwin"
WHY = "чертёж генплана № 727, решение владельца 09.11.2026"

CITY_N = Polygon([(3000, 23400), (3400, 24300), (4300, 25600), (5000, 25900), (5400, 27200), (6100, 27200), (5900, 26300),
                  (6500, 25700), (6100, 25200), (7100, 24700), (7100, 24100), (7900, 23600), (8000, 23000), (8700, 22900),
                  (8900, 22300), (8300, 21900), (7400, 21800), (7400, 20900), (6800, 20500), (6000, 20700), (5100, 20800),
                  (4000, 20900), (3600, 21300), (3000, 22500)])
RING_C, RING_R = (14800.0, 20150.0), 900.0
RESORT = Polygon([(12400, 19150), (12600, 20900), (13300, 21100), (14500, 21400), (15900, 21500), (15900, 19050), (15200, 18950),
                  (13500, 19100)])
VILLAS = box(15900, 19050, 17300, 21300)
THEME = box(9750, 19100, 12200, 20750)
F1_C, F1_A, F1_B = (12700.0, 16850.0), 2450.0, 1950.0
F1 = scale(Point(F1_C).buffer(1.0, quad_segs=32), F1_A, F1_B)
GOLF = scale(Point(16300.0, 17300.0).buffer(1.0, quad_segs=24), 800.0, 1400.0)
GARDENS = box(600, 20200, 2300, 23600)

# never cut: what exists and the centre of the scheme
KEEP_USES = {"village_existing", "utility"}
KEEP_IDS = {"gc", "ircc", "expo_1", "expo_2", "expo_hotels", "heat", "golf_club", "track"}
FROM_NEW = {"f1": F1, "golf_1": GOLF, "theme": THEME, "resort_e": RESORT, "res_e": VILLAS}


def kept(z):
    return z["use"] in KEEP_USES or z["id"] in KEEP_IDS or z["id"].startswith("water_")


def apply(zones, use_rules_density=None):
    water = unary_union([p for z, p in zones if z["id"].startswith("water_")])
    hard = unary_union([p for z, p in zones if kept(z)])
    new = dict(FROM_NEW)
    city = CITY_N.difference(water.buffer(90.0))                 # the shore band stays a park with beaches and the promenade
    made = [("gp_city", city, "residential_mid", "Город на северном берегу (Green-Сити)", [2034, 2048],
             {"floors_typical": "6-12", "residents_per_ha": 420.0, "jobs_per_ha": 14.0}),
            ("gp_gardens", GARDENS, "park", "Сады к западу от города", [2036, 2046], {})]
    taken = unary_union(list(new.values()) + [m[1] for m in made])
    out = []
    for z, p in zones:
        if kept(z):
            out.append((z, p))
            continue
        rest = p.difference(taken).buffer(0)
        if z["id"] in new:
            q = new[z["id"]].intersection(zones_area(zones)).difference(hard).difference(water.buffer(60.0)).buffer(0)
            out.append((dict(z, why=WHY + ": " + z.get("why", "")), q))
            if not rest.is_empty and rest.area >= 200.0:
                # the zone's old land: the circuit's old site is a logistics park as on the drawing, the rest open parkland
                if z["id"] == "f1":
                    out.append((dict(id="gp_log", use="logistics", name_ru="Логистический парк", years=[2038, 2046],
                                     why=WHY + ": на чертеже здесь склады и логистика", density={}), rest))
                else:
                    out.append((dict(id=z["id"] + "_old", use="park", name_ru="Парк восточного берега", years=[2040, 2050],
                                     why=WHY + ": прежнее место зоны — парк", density={}), rest))
            continue
        if z["id"].startswith("golf_"):
            z = dict(z, use="park", name_ru="Парк у гольф-поля", why=WHY + ": гольф перенесён и уменьшен", density={})
        if not rest.is_empty and rest.area >= 200.0:
            out.append((z, rest))
    for zid, g, use, name, years, density in made:
        q = g.intersection(zones_area(zones)).difference(hard).buffer(0)
        out.append((dict(id=zid, use=use, name_ru=name, years=years, why=WHY, density=density), q))
    return out


def zones_area(zones):
    return unary_union([p for _, p in zones]).buffer(0)
