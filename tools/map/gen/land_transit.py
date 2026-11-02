"""Transit hubs (w44, модель qTwin): the registry lot of a rail station or a bus station (objects[].kind transit) laid out as
sub-lots, and the park-and-ride deck of a registry parking object. The spec gives the plot only; the parts are a model.

Rail station (its id or name says rail / ж/д / вокзал):
  tracks     the line's band along the lot side that faces the nearest expressway (the route is not published; the line is taken
             to follow the motorway corridor): TRACKS track beds and a side platform as long as the train (lrt.platform_length_m:
             «не короче состава», TRAIN_LEN_M) — lot use transit, nothing built, no trees, the platform is a plaza
  hall       the station hall along the platform at the end nearer the bus station (else the P+R, else the nearest street):
             HALL_LEN_M × HALL_DEPTH_M, HALL_FLOORS floors — lot use transit, one building (kind public)
  forecourt  round the hall's street side up to the lot edge: lot use square, at most FORECOURT_SHARE_MAX of the station lot
  taxi       taxi and kiss-and-ride bays next to the forecourt on the street edge: TAXI_KR_SPACES spaces at 90° (parking.aisles_m)
  bus        a bus terminal laid out as below, only when no bus station lies within the transfer walk
             (stops.transfer_walk_max_min × WALK_M_PER_MIN)
  park_ride  a P+R deck of PR_CARS_IN_LOT cars, only when no registry parking lies within parking.temporary_walk_max_m
             (stations_large_shops)
  park       the rest: park with trees
Bus station: the terminal (TERM_LEN_M × TERM_DEPTH_M, TERM_FLOORS floors) on the side facing the rail station (else the nearest
  street), the red-line setback in front; behind it the boarding island under a canopy and the bays (BAY_PITCH_M each along the
  island, BUS_BAY_DEPTH_M deep) with the apron (street_xs.bus_carriageway_m, the wider value); the rest green.
P+R deck: floors PR_FLOORS; cars = lot area / the plot m² per car of parking.garage_area_by_floors_m2 at that many floors; the deck's
  footprint = cars × its footprint m² per car.

Every part is a lot of source registry with `hub: {of, kind, part}`; the registry id stays on the main part only (the hall, the
terminal). Parts that carry buildings list them in `hub.build` (footprint, floors, height_m, kind, family, gfa); a stop point goes
in `hub.stop` (rail: the platform's middle; bus: the boarding island's middle); the platform polygon in `hub.platform`."""
import math
import re

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

import land_util as U

# ---- model constants (модель qTwin: no norm gives these sizes)
TRACKS = 2                    # tracks through the station
TRACK_BED_M = 5.0             # one track bed with its side (m)
PLATFORM_W_M = 8.0            # side platform width (m)
PLATFORM_END_M = 10.0         # platform end from the lot edge (m)
TRAIN_LEN_M = 130.0           # agglomeration train: 6 cars × ≈ 21.5 m
HALL_LEN_M = 90.0             # station hall along the platform (m)
HALL_DEPTH_M = 24.0           # station hall across (m)
HALL_FLOORS = 2
HALL_FLOOR_H_M = 5.0          # storey height of a station hall (m)
HALL_MARGIN_M = 6.0           # walk round the hall inside its part (m)
FORECOURT_SHARE_MAX = 0.30    # the forecourt takes at most this share of the station lot
FORECOURT_DEPTH_M = 45.0      # forecourt depth in front of the hall before the share cap (m)
FORECOURT_SIDE_M = 30.0       # forecourt beside the hall towards the street end (m)
STALL_DEPTH_M = 5.0           # 90° car stall depth (m)
TAXI_KR_SPACES = 24           # taxi and kiss-and-ride spaces at a rail station
TERM_LEN_M = 60.0             # bus terminal along the boarding island (m)
TERM_DEPTH_M = 18.0           # bus terminal across (m)
TERM_FLOORS = 2
TERM_FLOOR_H_M = 4.5          # storey height of a bus terminal (m)
TERM_MARGIN_M = 6.0           # walk at the terminal's ends inside its part (m)
ISLAND_GAP_M = 4.0            # walk between the terminal and the boarding island (m)
CANOPY_W_M = 6.0              # boarding island under the canopy (m)
CANOPY_H_M = 5.0              # canopy height (m)
BAY_PITCH_M = 7.5             # one saw-tooth bus bay along the island (m)
BUS_BAY_DEPTH_M = 15.0        # bay depth for a 12 m bus at an angle (m)
PR_FLOORS = 4                 # floors of a P+R deck (a row of parking.garage_area_by_floors_m2)
PR_FLOORS_MAX = 8             # a deck that does not fit rises up to the top row of the table (6–8 floors)
PR_CARS_IN_LOT = 300          # P+R inside a station lot when no deck stands within walk
WALK_M_PER_MIN = 70.0         # walking speed for the transfer walk (≈ 4.2 km/h)
STOP_OFF_M = 2.0              # the bus stop point: this far out from the boarding island's kerb, at the bays (m)
MIN_PART_M2 = 150.0           # smaller leftovers join the part they share most boundary with (m²)

RAIL_RE = re.compile(r"rail|ж/д|железнодорож|вокзал(?!.*авто)", re.I)
BUS_RE = re.compile(r"bus|автовокзал|автостанц|автобус", re.I)


def hub_kind(o):
    """rail | bus for a registry object of kind transit (by its id and name; a plain station is a bus station)."""
    s = f"{o.get('registry_id', '')} {o.get('name_ru', '')}"
    if BUS_RE.search(s):
        return "bus"
    if RAIL_RE.search(s):
        return "rail"
    return "bus"


def garage_row(norms, floors):
    """(footprint m² per car, plot m² per car) of parking.garage_area_by_floors_m2 for that many floors."""
    tab = norms.v("parking.garage_area_by_floors_m2")
    for k, v in tab.items():
        lo, hi = (U._band(k) if "-" in str(k) else (float(k), float(k)))
        if lo <= floors <= hi:
            return float(v[0]), float(v[1])
    k = max(tab, key=lambda k: U._band(k)[1] if "-" in str(k) else float(k))
    return float(tab[k][0]), float(tab[k][1])


def pr_cars(area_m2, norms, floors=PR_FLOORS):
    """Cars of a P+R deck on a plot of area_m2 (the plot norm per car at that many floors)."""
    return int(area_m2 // garage_row(norms, floors)[1])


class Frame:
    """Local axes of a lot: a along T from the lot's u-min edge, b along V from its v-min edge (V points into the lot from the
    side it was built for). rect(a0, a1, b0, b1) is a world polygon."""

    def __init__(self, poly, T, V):
        self.T, self.V = np.asarray(T, float), np.asarray(V, float)
        P = np.asarray(poly.exterior.coords)
        u, v = P @ self.T, P @ self.V
        self.u0, self.v0 = float(u.min()), float(v.min())
        self.Lu, self.Dv = float(u.max() - u.min()), float(v.max() - v.min())

    def a_of(self, x, z):
        return float(np.array([x, z]) @ self.T) - self.u0

    def pt(self, a, b):
        p = (self.u0 + a) * self.T + (self.v0 + b) * self.V
        return [round(float(p[0]), 1), round(float(p[1]), 1)]

    def rect(self, a0, a1, b0, b1):
        pts = []
        for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1)):
            p = (self.u0 + a) * self.T + (self.v0 + b) * self.V
            pts.append((float(p[0]), float(p[1])))
        return Polygon(pts)


def _sides(poly, ang):
    """The four outward normals of the lot's frame box."""
    d = np.array([math.cos(ang), math.sin(ang)])
    n = np.array([-d[1], d[0]])
    return [d, -d, n, -n]


def _frame_from_side(poly, ang, toward, front=None):
    """Frame whose V points into the lot from the side facing `toward` (a point), and whose a = 0 end lies towards `front`."""
    c = np.array(poly.centroid.coords[0])
    w = np.asarray(toward, float) - c
    nrm = max(_sides(poly, ang), key=lambda s: float(s @ w) / (np.linalg.norm(w) or 1.0))
    V = -nrm
    T = np.array([-V[1], V[0]])
    if front is not None and float((np.asarray(front, float) - c) @ T) > 0:
        T = -T
    return Frame(poly, T, V)


def _nearest_point(lines, poly):
    if not lines:
        return None
    best = min(lines, key=lambda ln: ln.distance(poly))
    q = best.interpolate(best.project(poly.centroid))
    return (q.x, q.y)


def _merge_small(parts):
    """Leftovers under MIN_PART_M2 join the part they share most boundary with."""
    big = [p for p in parts if p["poly"].area >= MIN_PART_M2]
    for p in parts:
        if p["poly"].area >= MIN_PART_M2 or not big:
            continue
        q = max(big, key=lambda r: r["poly"].buffer(0.05).intersection(p["poly"].boundary).length)
        q["poly"] = U.merge([q["poly"], p["poly"]])
    return big


def _bld(fp, floors, height, kind, family, gfa=None):
    return {"footprint": U.coords(fp), "floors": int(floors), "height_m": round(float(height), 1), "kind": kind, "family": family,
            **({"gfa_m2": float(gfa)} if gfa is not None else {})}


def _bus_parts(lot, F, norms, partner_a=None):
    """Terminal, bays (with the canopy over the boarding island) and the green rest, in frame F (b = 0 on the street side)."""
    sb = float(norms.v("setbacks.red_line_m", "arterial_streets"))
    apron = float(U.num(norms.v("street_xs.bus_carriageway_m", "width"), ("max", "min")))
    TL = min(TERM_LEN_M, F.Lu - 2 * TERM_MARGIN_M)
    if TL < 2 * BAY_PITCH_M:
        return None
    ac = F.Lu / 2.0 if partner_a is None else min(max(partner_a, TERM_MARGIN_M + TL / 2), F.Lu - TERM_MARGIN_M - TL / 2)
    a0, a1 = ac - TL / 2, ac + TL / 2
    b_t1 = sb + TERM_DEPTH_M
    b_i0 = b_t1 + ISLAND_GAP_M
    b_i1 = b_i0 + CANOPY_W_M
    b_end = min(b_i1 + BUS_BAY_DEPTH_M + apron, F.Dv)
    term = F.rect(a0, a1, sb, b_t1)
    canopy = F.rect(a0, a1, b_i0, b_i1)
    if not lot.buffer(0.01).contains(term) or not lot.buffer(0.01).contains(canopy):
        return None
    term_lot = U.clean(F.rect(a0 - TERM_MARGIN_M, a1 + TERM_MARGIN_M, 0, b_t1 + ISLAND_GAP_M / 2).intersection(lot))
    bays_lot = U.clean(F.rect(a0 - TERM_MARGIN_M, a1 + TERM_MARGIN_M, b_t1 + ISLAND_GAP_M / 2, b_end).intersection(lot).difference(term_lot))
    n_bays = int(TL // BAY_PITCH_M)
    parts = [
        {"part": "terminal", "use": "transit", "poly": term_lot, "main": True,
         "build": [_bld(term, TERM_FLOORS, TERM_FLOORS * TERM_FLOOR_H_M, "public", "bus_terminal")], "stop": F.pt(ac, b_i1 + STOP_OFF_M)},
        {"part": "bays", "use": "transit", "poly": bays_lot, "bays": n_bays,
         "build": [_bld(canopy, 1, CANOPY_H_M, "other", "bus_canopy", gfa=0.0)]},
    ]
    return parts


def plan(lot, o, objs, net, norms, frame_ang):
    """Sub-lots of a registry transit lot: [{part, use, poly, main?, build?, stop?, platform?, cars?}] covering the lot, or None
    when the lot is too small for the layout (it then stays one lot)."""
    kind = hub_kind(o)
    walk = norms.v("stops.transfer_walk_max_min") * WALK_M_PER_MIN
    pr_walk = float(norms.v("parking.temporary_walk_max_m", "stations_large_shops"))
    others = [q for q in objs if q is not o and q.get("to")]
    bus_near = [q for q in others if q.get("kind") == "transit" and hub_kind(q) == "bus" and lot.distance(Point(q["to"])) <= walk]
    rail_near = [q for q in others if q.get("kind") == "transit" and hub_kind(q) == "rail" and lot.distance(Point(q["to"])) <= walk]
    pr_near = [q for q in others if q.get("kind") == "parking" and lot.distance(Point(q["to"])) <= pr_walk]
    streets = [U.seg_line(s) for s in net["segments"] if s["class"] in U.DRIVABLE and s["class"] not in ("expressway", "ramp")]
    xway = [U.seg_line(s) for s in net["segments"] if s["class"] == "expressway"]
    street_pt = _nearest_point(streets, lot)
    if kind == "bus":
        toward = (rail_near[0]["to"] if rail_near else street_pt)
        if toward is None:
            return None
        F = _frame_from_side(lot, frame_ang, toward)
        pa = F.a_of(*toward)
        parts = _bus_parts(lot, F, norms, pa)
        if parts is None:
            return None
        used = unary_union([p["poly"] for p in parts])
        parts += [{"part": "green", "use": "park", "poly": q} for q in U.polys(U.clean(lot.difference(used)), 1.0)]
        return _merge_small(parts)

    # rail station
    front = (bus_near[0]["to"] if bus_near else pr_near[0]["to"] if pr_near else street_pt)
    tq = _nearest_point(xway, lot)
    if tq is None:          # no expressway: the tracks on the side away from the front
        c = np.array(lot.centroid.coords[0])
        tq = tuple(2 * c - np.asarray(front if front is not None else c + 1.0, float))
    F = _frame_from_side(lot, frame_ang, tq, front)
    TB = TRACKS * TRACK_BED_M + PLATFORM_W_M
    HM = HALL_MARGIN_M
    HL = min(HALL_LEN_M, F.Lu - 2 * HM - FORECOURT_SIDE_M)
    HD = min(HALL_DEPTH_M, (F.Dv - TB) / 3.0)
    if HL < 30 or HD < 12:
        return None
    ha0 = FORECOURT_SIDE_M + HM
    hall = F.rect(ha0, ha0 + HL, TB, TB + HD)
    if not lot.buffer(0.01).contains(hall):
        return None
    hall_lot = U.clean(F.rect(ha0 - HM, ha0 + HL + HM, TB, TB + HD + HM).intersection(lot))
    tracks = U.clean(F.rect(0, F.Lu, 0, TB).intersection(lot))
    pl_len = min(max(TRAIN_LEN_M, float(U.num(norms.v("lrt.platform_length_m"), ("min",)))), F.Lu - 2 * PLATFORM_END_M)
    pc = ha0 + HL / 2.0
    pa0 = min(max(pc - pl_len / 2.0, PLATFORM_END_M), F.Lu - PLATFORM_END_M - pl_len)
    platform = U.clean(F.rect(pa0, pa0 + pl_len, TB - PLATFORM_W_M, TB).intersection(lot))
    # forecourt: round the hall towards the front edge and in front of it, at most FORECOURT_SHARE_MAX of the lot
    W = min(ha0 + HL + HM + FORECOURT_SIDE_M, F.Lu)
    cap = FORECOURT_SHARE_MAX * lot.area
    fd = min(FORECOURT_DEPTH_M, max(0.0, (cap + hall_lot.area) / W - (HD + HM)))
    fb1 = TB + HD + HM + fd
    fore = U.clean(F.rect(0, W, TB, fb1).intersection(lot).difference(hall_lot))
    while fore.area > cap * 1.02 and fd > 1.0:
        fd -= 1.0
        fb1 = TB + HD + HM + fd
        fore = U.clean(F.rect(0, W, TB, fb1).intersection(lot).difference(hall_lot))
    aisle = float(norms.v("parking.aisles_m", "90deg_two_sided"))
    sw = float(norms.v("parking.aisles_m", "space_width_90deg"))
    tw = 2 * STALL_DEPTH_M + aisle
    tl = math.ceil(TAXI_KR_SPACES / 2) * sw
    taken = unary_union([tracks, hall_lot, fore])
    taxi = U.clean(F.rect(0, tw, fb1, fb1 + tl).intersection(lot).difference(taken))
    mid = platform.centroid if not platform.is_empty else hall.centroid
    parts = [
        {"part": "tracks", "use": "transit", "poly": tracks, "platform": U.coords(platform) if not platform.is_empty else None,
         "nobuild": True},
        {"part": "hall", "use": "transit", "poly": hall_lot, "main": True, "stop": [round(mid.x, 1), round(mid.y, 1)],
         "build": [_bld(hall, HALL_FLOORS, HALL_FLOORS * HALL_FLOOR_H_M, "public", "rail_station_hall")]},
        {"part": "forecourt", "use": "square", "poly": fore},
        {"part": "taxi", "use": "parking", "poly": taxi, "cars": min(TAXI_KR_SPACES, int(taxi.area // (STALL_DEPTH_M * sw + aisle * sw / 2)))},
    ]
    b_next = fb1 + tl
    taken = unary_union([taken, taxi])
    if not bus_near:
        sbk = float(norms.v("setbacks.red_line_m", "arterial_streets"))
        apron = float(U.num(norms.v("street_xs.bus_carriageway_m", "width"), ("max", "min")))
        dep = sbk + TERM_DEPTH_M + ISLAND_GAP_M + CANOPY_W_M + BUS_BAY_DEPTH_M + apron
        ln = TERM_LEN_M + 2 * TERM_MARGIN_M
        sub = U.clean(F.rect(0, dep, b_next, b_next + ln).intersection(lot).difference(taken))
        bp = None
        if sub.area > 0.9 * dep * ln:
            Fb = Frame(sub, F.V, F.T)          # the bus part's street is the front edge (a = 0 of the station frame)
            bp = _bus_parts(sub, Fb, norms)
        if bp:
            for p in bp:
                p.pop("main", None)
            parts += [dict(p, part="bus_" + p["part"]) for p in bp]
            rest = U.clean(sub.difference(unary_union([p["poly"] for p in bp])))
            parts += [{"part": "green", "use": "park", "poly": q} for q in U.polys(rest, 1.0)]
            taken = unary_union([taken, sub])
            b_next += ln
        else:
            parts.append({"part": "note", "use": None, "poly": Polygon(), "why": "автостанция не помещается на участке станции"})
    if not pr_near:
        fp_car, plot_car = garage_row(norms, PR_FLOORS)
        area = PR_CARS_IN_LOT * plot_car
        side = math.sqrt(area)
        sub = U.clean(F.rect(0, side, b_next, b_next + side).intersection(lot).difference(taken))
        if sub.area > 0.9 * area:
            parts.append({"part": "park_ride", "use": "parking", "poly": sub, "cars": pr_cars(sub.area, norms)})
            taken = unary_union([taken, sub])
        else:
            parts.append({"part": "note", "use": None, "poly": Polygon(), "why": "перехватывающая стоянка не помещается на участке станции"})
    parts += [{"part": "park", "use": "park", "poly": q} for q in U.polys(U.clean(lot.difference(taken)), 1.0)]
    notes = [p for p in parts if p["use"] is None]
    parts = [p for p in parts if p["use"] is not None and not p["poly"].is_empty]
    keep = [p for p in parts if p["part"] in ("hall", "tracks")]
    parts = keep + _merge_small([p for p in parts if p not in keep])
    return parts + notes
