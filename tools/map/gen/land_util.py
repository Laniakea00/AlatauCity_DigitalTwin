"""Shared helpers of the land tools (w44): paths, JSON io, spec and norms access, red lines, terrain, years, geometry.

Used by gen_blocks_lots.py, gen_buildings.py, gen_masks.py, land_fixture.py, land_check.py and the rule files
validate/rules/{land,buildings,green,years}.py. Units: Unity metres, X = east, Z = north, Y = height a.s.l.

Numbers of the norms are read from spec/norms.json by key (Norms.v); nothing here types a norm value.
When w43's shared library tools/map/lib exists, red-line widths come from it (red_line_w tries it first)."""
import argparse
import json
import math
import re
import os
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))          # tools/map/gen
MAP = os.path.dirname(HERE)                                 # tools/map
REPO = os.path.dirname(os.path.dirname(MAP))
SPEC_DIR = os.path.join(MAP, "spec")
GEO_DIR = os.path.join(MAP, "geo")
TWIN_GEN = os.path.join(REPO, "UnityProject", "Tools", "twin_gen")
for _p in (GEO_DIR, TWIN_GEN):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = os.environ.get("ALATAU_OUT", "/mnt/project-files/alatau_stage7/out")
EXISTING_YEARS = [2025, 2025, 2025, 2025]
# an existing (OSM) building of at most EXISTING_HOME_M2 floor area is a home, its residents its floor area over the twin's m² per
# resident; a larger one holds workplaces at EXISTING_M2_PER_JOB. The traffic model's rule (export/twin_rerun.py, the same
# names), so buildings.json, the validator (has_homes) and traffic give one number (tester item 75; test_land.py checks they agree)
EXISTING_HOME_M2 = 600.0
EXISTING_M2_PER_JOB = 100.0


def existing_load(gfa, home_m2):
    """(homes, jobs) of an existing building of this floor area: homes of home_m2 (at least one) up to EXISTING_HOME_M2, else
    workplaces."""
    if gfa <= EXISTING_HOME_M2:
        return max(1, int(round(gfa / home_m2))), 0
    return 0, int(round(gfa / EXISTING_M2_PER_JOB))
SCENARIOS = ["base", "fast", "slow", "infra"]
DRIVABLE = {"expressway", "arterial_road_regulated", "arterial_continuous", "arterial_regulated", "district_transport",
            "district_pedestrian", "local", "local_secondary", "industrial", "park_road", "driveway_main", "driveway_secondary",
            "village_main", "village_secondary", "village_lane", "ramp"}
NO_ACCESS = {"expressway", "ramp", "arterial_continuous"}         # no lot entries straight from these (C08: access from service roads)
ARTERIAL_ROADS = {"expressway", "arterial_road_regulated"}       # «магистральные дороги»: housing ≥ 50 m from the carriageway
ARTERIAL_STREETS = {"arterial_continuous", "arterial_regulated", "district_transport", "district_pedestrian"}
TRANSIT_CLASSES = {"arterial_road_regulated", "arterial_regulated", "district_transport", "district_pedestrian", "local"}
BUILDABLE_USES = {"mixed_centre", "business", "residential_high", "residential_mid", "residential_low", "village_existing",
                  "campus", "medical", "industry", "logistics", "waterfront", "school", "kindergarten", "polyclinic", "hospital",
                  "clinic", "pharmacy_shop", "college", "university", "fire_station", "police", "utility", "substation", "worship",
                  "culture", "sport"}
RESIDENTIAL_USES = {"mixed_centre", "residential_high", "residential_mid", "residential_low", "village_existing", "waterfront"}
GREEN_USES = {"park", "square", "playground", "sport_ground", "reserve"}
FIRE_CLASS = {"school": "Ф4.1", "kindergarten": "Ф1.1", "hospital": "Ф1.1"}  # functional fire hazard class of lot uses (СП РК 2.02-101)


def ring_required(norms, lot_use, b_use, height_m):
    """fire_access.ring_required: the class list, residential over N m, other over M m."""
    rr = norms.v("fire_access.ring_required")
    if FIRE_CLASS.get(lot_use) in rr["classes"]:
        return True
    return height_m > (rr["residential_over_m"] if b_use == "housing" else rr["other_over_m"])


SOCIAL_USES = {"school", "kindergarten", "polyclinic", "hospital", "clinic", "pharmacy_shop", "college", "university",
               "fire_station", "police"}
LEVEL0_HOME_M2 = 75.0   # gate.json targets.source: «квартир — … (в схеме справочно: жилая GFA / 75 м²)» — level-0 convention


# ----------------------------------------------------------------------------------------------------------------- io
def cli(desc):
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("district", help="district id: gate, golden, green, growing_w, growing_e, gate_trial")
    ap.add_argument("--out", default=OUT, help="OUT root; files go to OUT/<district>/ (default %(default)s)")
    ap.add_argument("--spec", default=None, help="spec file (default tools/map/spec/<district>.json)")
    return ap


def out_dir(out, d):
    p = os.path.join(out, d)
    os.makedirs(p, exist_ok=True)
    return p


def read_json(p, default=None):
    if not os.path.isfile(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_json(p, obj):
    """UTF-8, LF, compact (CONTRACT: compact for files over 1 MB; we write every output compact)."""
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))      # one shot: the C encoder, same bytes
        f.write("\n")
    os.replace(tmp, p)
    return os.path.getsize(p)


def load_spec(d, path=None):
    p = path or os.path.join(SPEC_DIR, d + ".json")
    s = read_json(p)
    if s is None:
        raise FileNotFoundError(f"spec {p} not found (pass --spec)")
    s["_path"] = p
    return s


_city = None


def city():
    global _city
    if _city is None:
        _city = read_json(os.path.join(SPEC_DIR, "city.json"))
    return _city


def boundary_poly(spec):
    b = spec.get("boundary")
    if isinstance(b, list):
        return clean(Polygon(b))
    if isinstance(b, str) and b.startswith("city.json#districts/"):
        key = b.split("/")[-1]
        return clean(Polygon(city()["districts"][key]["polygon"]))
    key = spec.get("district")
    if key in city()["districts"]:
        return clean(Polygon(city()["districts"][key]["polygon"]))
    raise ValueError("no boundary in spec")


def work_polygon(spec):
    """area ∩ boundary (CONTRACT §3): generators build only inside it."""
    b = boundary_poly(spec)
    if spec.get("area"):
        b = b.intersection(clean(Polygon(spec["area"])))
    return clean(b)


# -------------------------------------------------------------------------------------------------------------- norms
class Norms:
    """Access to spec/norms.json: v('kindergartens.plot_m2_per_place') → value; sub-keys walk into dict values."""

    def __init__(self, path=None):
        self.doc = read_json(path or os.path.join(SPEC_DIR, "norms.json"))
        self.n = self.doc["norms"]
        self.used = {}

    def rec(self, key):
        if key not in self.n:
            raise KeyError("norms.json has no key " + key)
        return self.n[key]

    def v(self, key, *sub):
        r = self.rec(key)
        self.used[key] = r.get("status")
        val = r.get("value")
        for s in sub:
            if val is None:
                return None
            val = val[s] if isinstance(val, dict) else val
        return val

    def status(self, key):
        return self.rec(key).get("status")

    def sev(self, key):
        r = self.rec(key)
        if r.get("severity"):
            return r["severity"]
        return "error" if r.get("status") == "norm" else "warning"

    def num(self, key, *sub, prefer=("default", "design", "min", "value")):
        return num(self.v(key, *sub), prefer)

    def band(self, key, n):
        """Value of a table keyed by bands like "25-300", "<=100", ">1000" for number n (first band that holds n)."""
        tab = self.v(key)
        best = None
        for k, val in tab.items():
            lo, hi = _band(k)
            if lo is None:
                continue
            if lo <= n <= hi:
                return num(val, ("min", "default", "value"))
            best = val if best is None and n > hi else best
        return None

    def profile(self, cls):
        return self.doc["street_profiles"].get(cls, {})


def _band(k):
    k = k.replace(" ", "")
    try:
        if k.startswith("<="):
            return -1e18, float(k[2:])
        if k.startswith(">"):
            return float(k[1:].split("_")[0]) + 1e-9, 1e18
        if "-" in k:
            a, b = k.split("-")[:2]
            return float(a), float(b.split("_")[0])
    except ValueError:
        return None, None
    return None, None


def num(v, prefer=("default", "design", "min", "value")):
    if v is None or isinstance(v, (bool, str)):
        return None if isinstance(v, (str,)) or v is None else float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        for p in prefer:
            if p in v and isinstance(v[p], (int, float)):
                return float(v[p])
        for x in v.values():
            if isinstance(x, (int, float)):
                return float(x)
    if isinstance(v, list) and v and isinstance(v[0], (int, float)):
        return float(v[0])
    return None


# ---------------------------------------------------------------------------------------------------- street profiles
def profile_from_norms(norms, cls, lanes_total=None):
    """A contract profile {class, lanes, lane_w, median_w, sidewalk_w, verge_w, bike_w, parking_w, red_line_w} from
    norms.street_profiles[cls]; red_line_w = clamp(sum of the parts, red_lines_m.min, red_lines_m.max)."""
    P = norms.profile(cls)

    def g(name, prefer=("design", "default", "min", "value", "no_barrier_min", "main", "on_axis_min")):
        return num(P.get(name, {}).get("value"), prefer) if name in P else None

    lanes = lanes_total
    lv = P.get("lanes", {}).get("value") if "lanes" in P else None
    lo = num(lv, ("min", "value")) if lv is not None else None
    hi = num(lv, ("max", "value")) if lv is not None else None
    if lanes is None:
        lanes = lo if lo is not None else 2
    if lo is not None:
        lanes = max(lanes, lo)
    if hi is not None:
        lanes = min(lanes, hi)
    lanes = int(round(lanes))
    lane_w = g("lane_width_m")
    if lane_w is None:
        cw = g("carriageway_m")
        lane_w = cw / max(lanes, 1) if cw else (num(P.get("width_m", {}).get("value"), ("right_turn", "left_turn")) or 0.0)
    median = g("median_m") or 0.0
    side = g("sidewalk_m") or 0.0
    if cls == "pedestrian_street":
        side = 0.0
    verge = num(P.get("green_strip_m", {}).get("value")) if isinstance(P.get("green_strip_m", {}).get("value"), (int, float)) else 0.0
    bike = 0.0
    if cls == "bike_path":
        lanes, lane_w = int(lo or 1), g("lane_width_m") or 0.0
    total = lanes * lane_w + median + 2 * (side + (verge or 0.0))
    rl = P.get("red_lines_m", {}).get("value") if "red_lines_m" in P else None
    if isinstance(rl, dict):
        total = min(max(total, rl.get("min", total)), rl.get("max", total))
    if cls == "boulevard":
        total = max(total, num(P.get("green_width_m", {}).get("value"), ("on_axis_min",)) or total)
    if cls == "pedestrian_street":
        ex = P.get("width_examples_m", {}).get("value", {})
        total = max(total, num(ex.get("lanes"), ("min",)) or 0.0)
    fwd = lanes - lanes // 2 if lanes > 1 else lanes
    return {"class": cls, "lanes": [fwd, lanes - fwd], "lane_w": round(lane_w, 2), "median_w": round(median, 2),
            "sidewalk_w": [side, side], "verge_w": [verge or 0.0, verge or 0.0], "bike_w": [bike, bike], "parking_w": [0.0, 0.0],
            "red_line_w": round(total, 2)}


def rail_housing_band(area, norms):
    """Land within szz.rail_m housing_from_outer_track_axis of an operating railway track (lib.rail, as rule 15 measures:
    no tunnels, metro or abandoned lines) near area, plus RAIL_TOL_M; an empty polygon without the rail layer."""
    try:
        if MAP not in sys.path:
            sys.path.insert(0, MAP)
        from lib import rail as _rail
    except ImportError:
        return Polygon()
    lim = float(norms.v("szz.rail_m", "housing_from_outer_track_axis"))
    tr = _rail.tracks(area, lim)
    return clean(unary_union([LineString(t["P"]).buffer(lim + RAIL_TOL_M) for t in tr])) if tr else Polygon()


KEEP_MODEL_SRC = "gate_district.bytes"     # a spec keep quarter drawn by this model (the Gate District round Iconic)
_KEEP_MODEL_BLOCKS = {}


def keep_models_tall(spec, hi_h):
    """[(polygon, top_m)] of the blocks over hi_h of the model quarters the spec keeps (`keep` whose source names
    gate_district.bytes), as rule 12 pairs them with new buildings (validate rules/buildings.py _keep_models_tall): the
    model's triangles of 1 m and higher in the world frame (district/gate_common.local_to_world), joined, each block's top its
    highest triangle, blocks under gen_blocks_lots.SHED_MAX_M2 left out, a block standing in the keep polygon. [] when the
    model file is not there."""
    keeps = [k for k in spec.get("keep") or [] if KEEP_MODEL_SRC in str(k.get("source") or "") and len(k.get("polygon") or []) >= 3]
    if not keeps:
        return []
    if "gate" not in _KEEP_MODEL_BLOCKS:
        blocks = []
        try:
            sys.path.insert(0, os.path.join(MAP, "district"))
            import gate_common as GC
            from gen_blocks_lots import SHED_MAX_M2
            d = GC.gate_district_bytes()
        except (OSError, ValueError, ImportError):
            d = None
        if d is not None:
            tri = d["p"][d["idx"]]
            top = tri[:, :, 1].max(1)
            up = top >= 1.0
            x, z = GC.local_to_world(tri[up][:, :, 0], tri[up][:, :, 2])
            polys = shapely.buffer(shapely.polygons(np.stack([x, z], -1)), 0.05, join_style=2)
            u = shapely.union_all(polys)
            tree = shapely.STRtree(polys)
            for g in getattr(u, "geoms", [u]):
                if g.area < SHED_MAX_M2:
                    continue
                blocks.append((g.buffer(-0.05, join_style=2) if g.area > 1.0 else g,
                               float(top[up][tree.query(g, predicate="intersects")].max())))
        _KEEP_MODEL_BLOCKS["gate"] = blocks
    out = []
    for k in keeps:
        kz = shapely.Polygon(k["polygon"]).buffer(1.0)
        out += [(g, h) for g, h in _KEEP_MODEL_BLOCKS["gate"] if h > hi_h and kz.intersects(g.representative_point())]
    return out


def rail_decks(spec):
    """The spec railway's viaduct pieces as rule 25 reads them (lib.rail.decks: struct runs of kind overpass / bridge, the
    deck's underside lib.model rail_deck_below_m under the rail head, rail_deck_half_m each side of the track axis):
    [(axis LineString, rail head heights along it (n), half width, underside below the head)]. [] without a rail block."""
    blk = (spec or {}).get("rail")
    if not blk:
        return []
    try:
        if MAP not in sys.path:
            sys.path.insert(0, MAP)
        from lib import model as _model
        from lib import rail as _rail
        below, half = float(_model("rail_deck_below_m")), float(_model("rail_deck_half_m"))
        ds = _rail.decks(blk)
    except Exception:
        return []
    return [(LineString(d["P"][:, :2]), d["P"][:, 2], half, below) for d in ds if len(d["P"]) >= 2]


DECK_STEP_M = 1.0          # m between the points a deck's clearance is sampled at along its axis (модель qTwin)
DECK_CLEAR_MARGIN_M = 0.3  # m over fire_access.arches.height_min_m: a drive's surface stands a little over the terrain (модель qTwin)


def _low_pieces(ax, under, half, T, clear):
    """Plan pieces of a deck (axis LineString, underside heights at its vertices, half width) with less than clear between
    the underside and the ground (the highest of the terrain at the axis and at both deck edges, sampled every
    DECK_STEP_M). [Polygon]."""
    out = []
    L = ax.length
    if L < 0.5:
        return out
    n = max(2, int(math.ceil(L / DECK_STEP_M)) + 1)
    t = np.linspace(0.0, L, n)
    P = np.array([[ax.interpolate(v).x, ax.interpolate(v).y] for v in t])
    S = np.r_[0.0, np.cumsum(np.hypot(*np.diff(np.array(ax.coords)[:, :2], axis=0).T))]
    u = np.interp(t, S, under)
    d = np.gradient(P, axis=0)
    nrm = np.c_[-d[:, 1], d[:, 0]] / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)[:, None]
    g = np.max([np.asarray(T.height(P[:, 0] + k * half * nrm[:, 0], P[:, 1] + k * half * nrm[:, 1]), float) for k in (-1.0, 0.0, 1.0)], axis=0)
    low = u - g < clear
    i = 0
    while i < n:
        if not low[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and low[j + 1]:
            j += 1
        a, b = max(0.0, t[i] - DECK_STEP_M), min(L, t[j] + DECK_STEP_M)
        out.append(shapely.ops.substring(ax, a, b).buffer(half, cap_style="flat"))
        i = j + 1
    return out


def rail_low_decks(spec, norms, T=None):
    """Plan pieces of the spec railway's viaduct with less than fire_access.arches.height_min_m (+ DECK_CLEAR_MARGIN_M)
    between its underside and the ground (the highest of the terrain at the axis and at both deck edges): no drive or
    turnaround passes under them (rule 25 since integ eaa6287; gate_trial ds329 and the pad of dn431 under rail_agglo_1 at
    3.7 m). [Polygon]."""
    T = T or terrain()
    clear = norms.v("fire_access.arches", "height_min_m") + DECK_CLEAR_MARGIN_M
    out = []
    for ax, top, half, below in rail_decks(spec):
        out += _low_pieces(ax, np.asarray(top, float) - below, half, T, clear)
    return out


def lrt_low_decks(lrt, norms, T=None):
    """Plan pieces of the LRT viaduct (sections of kind elevated, as rule 25 takes them: the rail heights of lrt.json less
    lib.model lrt_rail_over_deck_m, lib.model lrt_viaduct_w_m wide) with less than fire_access.arches.height_min_m
    (+ DECK_CLEAR_MARGIN_M) over the ground, where the viaduct comes down to its ramps: no drive or turnaround passes under
    them (rule 25 under_decks). [Polygon]."""
    try:
        if MAP not in sys.path:
            sys.path.insert(0, MAP)
        from lib import model as _model
        deck, half = float(_model("lrt_rail_over_deck_m")), float(_model("lrt_viaduct_w_m")) / 2.0
    except Exception:
        return []
    T = T or terrain()
    clear = norms.v("fire_access.arches", "height_min_m") + DECK_CLEAR_MARGIN_M
    out = []
    for Ln in (lrt or {}).get("lines", []):
        P = np.asarray(Ln.get("pts") or [], float)
        if len(P) < 2 or P.shape[1] < 3:
            continue
        S = np.r_[0.0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
        for r in Ln.get("sections", []):
            a, b = max(0.0, float(r["from_m"])), min(float(S[-1]), float(r["to_m"]))
            if r["kind"] != "elevated" or b - a < 0.5:
                continue
            ch = np.r_[a, S[(S > a + 1e-9) & (S < b - 1e-9)], b]
            ax = LineString(np.c_[np.interp(ch, S, P[:, 0]), np.interp(ch, S, P[:, 1])])
            out += _low_pieces(ax, np.interp(ch, S, P[:, 2]) - deck, half, T, clear)
    return out


def span_bands(net, lrt, norms, spec=None):
    """Plan footprints of the elevated spans: the LRT viaduct (sections of kind elevated, lib.model lrt_viaduct_w_m wide, as
    rule 25 takes it), the street decks on bridges and overpasses (struct pieces, the deck half-width either side) and the
    spec railway's viaduct (rail_decks). Land under them takes no building, and a thin zone under one joins no block
    (golden B2127: three offices in the strip of u_lrt_viaduct_1 under the LRT span, rule 25). [Polygon]."""
    try:
        if MAP not in sys.path:
            sys.path.insert(0, MAP)
        from lib import model as _model
        w_v = float(_model("lrt_viaduct_w_m"))
    except Exception:
        w_v = norms.num("lrt.corridor_width_m", "double_track")
    out = [ax.buffer(half, cap_style="flat") for ax, _, half, _ in rail_decks(spec)]
    for L in (lrt or {}).get("lines", []):
        ls = LineString([(p[0], p[1]) for p in L["pts"]])
        for r in L.get("sections", []):
            a, b = max(0.0, r["from_m"]), min(ls.length, r["to_m"])
            if r["kind"] == "elevated" and b - a > 0.5:
                out.append(shapely.ops.substring(ls, a, b).buffer(w_v / 2.0, cap_style="flat"))
    for sg in (net or {}).get("segments", []):
        pcs = [p for p in sg.get("struct") or [] if p.get("kind") in SPAN_KINDS and p["to_m"] - p["from_m"] > 0.5]
        if not pcs or len(sg.get("pts") or []) < 2:
            continue
        ls = seg_line(sg)
        hw = deck_half(seg_profile(net, sg, norms))
        for p in pcs:
            q = shapely.ops.substring(ls, max(0.0, p["from_m"]), min(ls.length, p["to_m"]))
            if q.length > 0.5:
                out.append(q.buffer(hw, cap_style="flat"))
    return out


SPAN_KINDS = ("bridge", "overpass", "viaduct", "elevated")    # struct pieces of a street carried on a span


RAIL_TOL_M = 0.5      # m over the rail housing distance: the buffer's chords and the 0.01 m rounding of footprints (model qTwin)


def _lib_red_line(cls):
    try:
        lib = os.path.join(MAP, "lib")
        if os.path.isdir(lib) and MAP not in sys.path:
            sys.path.insert(0, MAP)
        from lib import profiles as _lp  # noqa: F401  (w43, when merged)
        f = getattr(_lp, "red_line_w", None)
        return f(cls) if f else None
    except Exception:
        return None


def seg_profile(net, seg, norms):
    """Profile of a network segment: network.json profiles[pid] (w43's single definition), else lib, else norms."""
    pr = (net.get("profiles") or {}).get(str(seg.get("pid"))) if seg.get("pid") is not None else None
    if pr:
        return pr
    p = profile_from_norms(norms, seg["class"])
    w = _lib_red_line(seg["class"])
    if w:
        p["red_line_w"] = w
    return p


def is_cw(pr):
    """One carriageway of a divided road: network.json gives it a '/cw' profile (lanes [n, 0] with the road's whole median and
    red line; the median on the left of its direction of travel, the sidewalk side on the right)."""
    ln = pr.get("lanes") or [0, 0]
    return ln[1] == 0 and ln[0] > 0 and pr.get("median_w", 0.0) > 0


def cw_offset(pr):
    """Distance from the road axis to the line of one carriageway of a divided road (0 for any other profile)."""
    return pr.get("median_w", 0.0) / 2.0 + pr["lanes"][0] * pr["lane_w"] / 2.0 if is_cw(pr) else 0.0


def carriage_half(pr):
    """Half width of the carriageway around a segment's line (one carriageway of a divided road: its own lanes only)."""
    if is_cw(pr):
        return pr["lanes"][0] * pr["lane_w"] / 2.0
    return (sum(pr["lanes"]) * pr["lane_w"] + pr.get("median_w", 0.0)) / 2.0


def red_half(pr):
    """Half width of the red-line band around a segment's line: red/2. One carriageway of a divided road lies cw_offset off the
    road axis, so its band is red/2 − offset: the outer side then reaches red/2 from the road axis, and the inner side passes
    the axis (at least by the offset), so the two carriageways' bands cover the median between them."""
    r = pr["red_line_w"] / 2.0
    e = cw_offset(pr)
    return max(r - e, e) if e > 0 else r


def walk_half(pr, side=0):
    return carriage_half(pr) + pr["verge_w"][side] + pr["sidewalk_w"][side]


def seg_line(seg):
    return LineString([(p[0], p[1]) for p in seg["pts"]])


def seg_level_parts(seg):
    """[(LineString part, level)] by struct ranges: bridge/overpass +1, tunnel −1, others 0 (CONTRACT §2)."""
    ls = seg_line(seg)
    st = seg.get("struct") or []
    if not st:
        return [(ls, 0)]
    out = []
    L = ls.length
    cuts = sorted({0.0, L} | {min(max(s["from_m"], 0), L) for s in st} | {min(max(s["to_m"], 0), L) for s in st})
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 0.5:
            continue
        mid = (a + b) / 2
        lv = 0
        for s in st:
            if s["from_m"] <= mid <= s["to_m"]:
                lv = {"bridge": 1, "overpass": 1, "tunnel": -1}.get(s["kind"], 0)
        out.append((shapely.ops.substring(ls, a, b), lv))
    return out or [(ls, 0)]


def network_polys(net, norms, part="red"):
    """Per segment polygons: part = 'red' (red line), 'carriage', 'walk' (carriageway + verge + sidewalks). The walk band
    takes each side's own verge and sidewalk (profiles [left, right] of the segment's direction): one carriageway of a
    divided road has none on its median side (left), so its band no longer reaches into the median by the outer sidewalk's
    width (w52, growing_w: an LRT in the median of s_trunk_2 «on the same land» as both carriageways)."""
    res = []
    for s in net.get("segments", []):
        pr = seg_profile(net, s, norms)
        wl = wr = 0.0
        if part == "red":
            w = red_half(pr)
        elif part == "carriage":
            w = carriage_half(pr)
        else:
            wl, wr = walk_half(pr, 0), walk_half(pr, 1)
            w = min(wl, wr)
        if max(w, wl, wr) <= 0:
            continue
        for ls, lv in seg_level_parts(s):
            if wl == wr:
                g = ls.buffer(w, cap_style="flat" if part != "red" else "round", quad_segs=4)
            else:
                # the narrower side's band round the line, the wider side's own single-sided band (left > 0, right < 0)
                g = clean(unary_union([ls.buffer(w, cap_style="flat", quad_segs=4) if w > 0 else Polygon(),
                                       ls.buffer(wl if wl > wr else -wr, single_sided=True, quad_segs=4)]))
            res.append((s, g, lv))
    return res


# ------------------------------------------------------------------------------------------- street pieces off grade
OFFGRADE_MIN = 0.5    # a street piece more than this above (or below) the terrain is off grade (m), from the network heights:
#                       a landing, ramp, embankment or cut; a model parameter (the coordinator's ~0.5 m)
OFFGRADE_STEP = 2.0   # sampling step along a street for its height over the terrain (m): a model parameter
SPAN_DECK = 1.5       # structure depth of a span, deck surface to its underside (m): a model parameter (check_merge assumes 1.5 m)
SIDE_SLOPE = 1.5      # horizontal run of an embankment or cut side slope per metre of height (1:1.5 earthwork): a model parameter


def deck_half(pr):
    """Half width of the street's built surface (carriageway + verge + sidewalk + bike + parking, the wider side); the red
    line when the profile has no parts."""
    w = max(carriage_half(pr) + pr["verge_w"][i] + pr["sidewalk_w"][i] + pr.get("bike_w", [0.0, 0.0])[i]
            + pr.get("parking_w", [0.0, 0.0])[i] for i in (0, 1))
    return w if w > 0 else red_half(pr)


def seg_heights(seg, step=OFFGRADE_STEP, T=None):
    """(chainage t, x, z, height over terrain dh, struct kind) sampled along a segment: every `step` m plus its vertices and
    struct ends; the street height is linear between the network points [x, z, y]."""
    T = T or terrain()
    P = np.asarray(seg["pts"], dtype=float)
    ch = np.r_[0.0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
    L = float(ch[-1])
    st = seg.get("struct") or []
    t = np.unique(np.r_[np.arange(0.0, L, step), ch, [min(max(s["from_m"], 0.0), L) for s in st],
                        [min(max(s["to_m"], 0.0), L) for s in st], L])
    x, z, y = (np.interp(t, ch, P[:, k]) for k in range(3))
    dh = y - np.asarray(T.height(x, z), dtype=float)
    kind = np.array(["ground"] * len(t), dtype=object)
    for i in range(len(t) - 1):          # an interval's kind by its middle (as seg_level_parts)
        mid = (t[i] + t[i + 1]) / 2
        for s in st:
            if s["from_m"] <= mid <= s["to_m"]:
                kind[i] = s["kind"]
    kind[-1] = kind[-2] if len(t) > 1 else kind[-1]
    return t, x, z, dh, kind


def offgrade(net, norms, T=None, classes=None):
    """Street pieces a drive or a building must keep off: every run of a segment more than OFFGRADE_MIN above or below
    the terrain (network heights), except tunnels and the spans (bridge, overpass) with fire_access.arches.height_min_m clear
    beneath the deck (SPAN_DECK) — a drive may pass under those. Returns [{seg, line, poly, kind, h, from_m, to_m}]: poly is
    the built surface (deck_half) plus the side slopes (SIDE_SLOPE · |height|) where the piece is earthwork (no span),
    flat-capped at the run's ends, so the street stays reachable where it is at grade. classes limits the segment classes."""
    T = T or terrain()
    clear = norms.v("fire_access.arches", "height_min_m")
    out = []
    for s in net.get("segments", []):
        if classes is not None and s["class"] not in classes or len(s.get("pts") or []) < 2:
            continue
        t, x, z, dh, kind = seg_heights(s, T=T)
        if len(t) < 2:
            continue
        span = np.isin(kind, ["bridge", "overpass"])
        iv_kind = kind[:-1]
        iv_dh = np.maximum(np.abs(dh[:-1]), np.abs(dh[1:]))
        iv_lo = np.minimum(dh[:-1], dh[1:])
        bad = (iv_kind != "tunnel") & (iv_dh > OFFGRADE_MIN) & ~(span[:-1] & (iv_lo - SPAN_DECK >= clear))
        if not bad.any():
            continue
        half = deck_half(seg_profile(net, s, norms))
        ls = LineString(np.c_[x, z])
        i = 0
        while i < len(bad):
            if not bad[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(bad) and bad[j + 1]:
                j += 1
            # run of intervals i..j; its ends move to where |dh| crosses OFFGRADE_MIN inside the end intervals
            t0, t1 = t[i], t[j + 1]
            if abs(dh[i]) < OFFGRADE_MIN < abs(dh[i + 1]) and not span[i]:
                t0 = t[i] + (t[i + 1] - t[i]) * (OFFGRADE_MIN - abs(dh[i])) / (abs(dh[i + 1]) - abs(dh[i]))
            if abs(dh[j + 1]) < OFFGRADE_MIN < abs(dh[j]) and not span[j]:
                t1 = t[j] + (t[j + 1] - t[j]) * (abs(dh[j]) - OFFGRADE_MIN) / (abs(dh[j]) - abs(dh[j + 1]))
            parts = []
            for k in range(i, j + 1):
                a, b = max(t[k], t0), min(t[k + 1], t1)
                if b - a < 1e-3:
                    continue
                w = half + (0.0 if span[k] else SIDE_SLOPE * iv_dh[k])
                parts.append(shapely.ops.substring(ls, a, b).buffer(w, cap_style="flat", quad_segs=2))
                if k < j:                     # fill the outer corner at a bend
                    q = ls.interpolate(b)
                    parts.append(q.buffer(w, quad_segs=4))
            if parts:
                kinds = sorted(set(iv_kind[i:j + 1]))
                out.append({"seg": s, "line": shapely.ops.substring(ls, t0, t1), "poly": clean(unary_union(parts)),
                            "kind": "/".join(kinds), "h": float(dh[i:j + 2][np.argmax(np.abs(dh[i:j + 2]))]),
                            "from_m": float(t0), "to_m": float(t1)})
            i = j + 1
    return out


def at_grade_parts(seg, pieces, min_len=0.5):
    """The parts of a segment's centreline at grade: level 0 (no bridge, overpass or tunnel range) and off every off-grade
    piece of it (pieces: offgrade() records of this segment)."""
    ls = seg_line(seg)
    L = ls.length
    cuts = sorted([(p["from_m"], p["to_m"]) for p in pieces]
                  + [(s["from_m"], s["to_m"]) for s in seg.get("struct") or [] if s["kind"] in ("bridge", "overpass", "tunnel")])
    if not cuts:
        return [ls]
    out, a = [], 0.0
    for f, t_ in cuts:
        f = min(max(f, 0.0), L)
        if f - a >= min_len:
            out.append(shapely.ops.substring(ls, a, f))
        a = max(a, min(t_, L))
    if L - a >= min_len:
        out.append(shapely.ops.substring(ls, a, L))
    return out


# ------------------------------------------------------------------------------------------------------------- terrain
_T = None


def terrain():
    global _T
    if _T is None:
        import terrain as tmod
        _T = tmod.terrain()
    return _T


def h(x, z):
    return terrain().height(x, z)


GREEN_ENTRY_STEP = 40.0   # spacing of the entrances taken on a green's edge for walking distances (m): a model parameter


def entrances(poly, step=GREEN_ENTRY_STEP):
    """[(x, z)] where people walk into a green: points every `step` m along its edge, plus a point inside (a park is reached
    at its edge across the street, not at its middle)."""
    out = []
    for q in polys(poly):
        ring = q.exterior
        n = max(1, int(ring.length // step))
        out += [(p.x, p.y) for p in shapely.line_interpolate_point(ring, np.arange(n) * ring.length / n)]
    c = poly.representative_point()
    return out + [(c.x, c.y)]


def poly_samples(poly, step=20.0, max_n=4000):
    """Points inside a polygon on a grid (plus its vertices), as (N, 2)."""
    x0, z0, x1, z1 = poly.bounds
    st = max(step, math.sqrt(max(poly.area, 1.0) / max_n))
    xs = np.arange(x0 + st / 2, x1, st)
    zs = np.arange(z0 + st / 2, z1, st)
    pts = [np.asarray(poly.exterior.coords)[:-1]] if poly.geom_type == "Polygon" else [np.asarray(g.exterior.coords)[:-1] for g in poly.geoms]
    if len(xs) and len(zs):
        X, Z = np.meshgrid(xs, zs)
        P = np.c_[X.ravel(), Z.ravel()]
        m = shapely.contains_xy(poly, P[:, 0], P[:, 1])
        pts.append(P[m])
    return np.vstack(pts)


def grade(poly):
    """Planning mark of a lot: mid-range of the terrain inside, and the largest cut or fill it needs."""
    P = poly_samples(poly, 15.0)
    H = terrain().height(P[:, 0], P[:, 1])
    g = (float(H.max()) + float(H.min())) / 2.0
    return round(g, 2), round(float(H.max() - H.min()) / 2.0, 2)


# --------------------------------------------------------------------------------------------------------------- years
def effective_years(base_year, use="housing", source="new"):
    """[base, fast, slow, infra] exactly as TwinScenario.EffectiveYear / twin_common.effective_year."""
    import twin_common
    return [int(twin_common.effective_year(int(base_year), use, source, s)) for s in SCENARIOS]


def years_max(*ys):
    ys = [y for y in ys if y]
    if not ys:
        return list(EXISTING_YEARS)
    return [max(y[i] for y in ys) for i in range(4)]


def shift_like(street_years, base_year, use="housing"):
    """Years of an object built in base_year that must not open before its street, in every scenario."""
    e = effective_years(base_year, use)
    return [max(a, b) for a, b in zip(e, street_years)]


# ------------------------------------------------------------------------------------------------------------ geometry
def clean(g):
    if g is None:
        return Polygon()
    if not g.is_valid:
        g = shapely.make_valid(g)
    if g.geom_type == "GeometryCollection":
        g = unary_union([q for q in g.geoms if q.geom_type in ("Polygon", "MultiPolygon")])
    return g


def merge(geoms):
    """Union of touching polygons with hairline slits closed (out and back by 1 cm, mitre). GEOS can return nothing for the
    negative buffer of a dense ring (seen on a 5,500 m² block, shapely 2.2 / GEOS 3.14): then, or when the area moves, the plain
    union."""
    u = clean(unary_union(list(geoms)))
    try:
        v = clean(u.buffer(0.01, join_style="mitre").buffer(-0.01, join_style="mitre"))
    except Exception:
        return u
    return u if v.is_empty or abs(v.area - u.area) > 1e-3 * max(u.area, 1.0) + 1.0 else v


def polys(g, min_area=0.0):
    """Polygon parts of any geometry."""
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g] if g.area > min_area else []
    if hasattr(g, "geoms"):
        out = []
        for q in g.geoms:
            out += polys(q, min_area)
        return out
    return []


def no_holes(poly, min_area=1.0):
    """Hole-free parts of a polygon (CONTRACT polygons are exterior rings): cut through each hole until none is left."""
    from shapely.geometry import box as _box
    out, stack, guard = [], polys(poly, min_area), 0
    while stack and guard < 5000:
        guard += 1
        p = stack.pop()
        if not p.interiors:
            out.append(p)
            continue
        hx = Polygon(p.interiors[0]).centroid.x
        x0, z0, x1, z1 = p.bounds
        stack += polys(clean(p.intersection(_box(x0 - 1, z0 - 1, hx, z1 + 1))), min_area)
        stack += polys(clean(p.intersection(_box(hx, z0 - 1, x1 + 1, z1 + 1))), min_area)
    return out


def coords(p, nd=2):
    """[[x, z], …] of a polygon exterior (no closing point); a MultiPolygon gives its largest part."""
    if p.geom_type != "Polygon":
        p = max(polys(p), key=lambda q: q.area)
    c = np.asarray(p.exterior.coords)[:-1]
    return [[round(float(x), nd), round(float(z), nd)] for x, z in c]


def from_coords(c, holes=None):
    return clean(Polygon(c, holes or None))


def holes(p, nd=2):
    """Interior rings of a polygon (of its largest part) as [[[x, z], …], …] — written as the optional `holes` field next to
    `polygon` (lots, blocks, greens): a reader that ignores it sees the outer ring only."""
    if p.geom_type != "Polygon":
        p = max(polys(p), key=lambda q: q.area)
    return [[[round(float(x), nd), round(float(z), nd)] for x, z in np.asarray(r.coords)[:-1]] for r in p.interiors]


def geom(rec, key="polygon", hkey="holes"):
    """Shapely polygon of a record with `polygon` and optional `holes`."""
    return from_coords(rec[key], rec.get(hkey))


def poly_fields(p, nd=2):
    """{'polygon': …, 'holes': …?} for writing a polygon that may have holes (nd decimals)."""
    h = holes(p, nd)
    return {"polygon": coords(p, nd), **({"holes": h} if h else {})}


def axis(poly):
    """(angle_rad, length, width) of the minimum rotated rectangle; angle of the long side."""
    r = poly.minimum_rotated_rectangle
    if r.geom_type != "Polygon":
        return 0.0, 0.0, 0.0
    c = np.asarray(r.exterior.coords)
    e1, e2 = c[1] - c[0], c[2] - c[1]
    l1, l2 = np.hypot(*e1), np.hypot(*e2)
    if l1 >= l2:
        return math.atan2(e1[1], e1[0]), l1, l2
    return math.atan2(e2[1], e2[0]), l2, l1


FRAME_TOL_DEG = 4.0   # edges within this many degrees (mod 90°) count for one frame direction: a model parameter


def frame_angle(poly):
    """The block's frame (rad, in [0, π/2)): the direction, modulo 90°, that most of its edge length runs along or across.
    Lots are cut square to it (side lines parallel, cuts across the frontage); a block of no clear frame falls back to the
    long side of its minimum rotated rectangle."""
    segs = []
    for q in polys(poly, 0.0):
        c = np.asarray(q.exterior.simplify(0.5).coords)
        d = np.diff(c, axis=0)
        L = np.hypot(d[:, 0], d[:, 1])
        a = np.mod(np.arctan2(d[:, 1], d[:, 0]), math.pi / 2)
        segs.append((a, L))
    if not segs:
        return 0.0
    a = np.concatenate([s_[0] for s_ in segs])
    L = np.concatenate([s_[1] for s_ in segs])
    if L.sum() <= 0:
        return 0.0
    tol = math.radians(FRAME_TOL_DEG)
    best, best_w = None, -1.0
    for a0 in a[np.argsort(-L)][:24]:
        dd = np.abs((a - a0 + math.pi / 4) % (math.pi / 2) - math.pi / 4)
        w = L[dd <= tol].sum()
        if w > best_w + 1e-9:
            # the length-weighted mean of the edges within tol (circular, period 90°)
            m = dd <= tol
            off = ((a[m] - a0 + math.pi / 4) % (math.pi / 2) - math.pi / 4)
            best, best_w = (a0 + float((off * L[m]).sum() / L[m].sum())) % (math.pi / 2), w
    if best_w < 0.25 * L.sum():
        return axis(poly)[0] % (math.pi / 2)
    return best


def frame_axis(poly, frame):
    """(angle, length, width) like axis(), with the two directions of the frame: angle of the longer extent."""
    out = []
    for a in (frame, frame + math.pi / 2):
        lo, hi = _proj_range(poly, a)
        out.append((hi - lo, a))
    (l1, a1), (l2, a2) = out
    return (a1, l1, l2) if l1 >= l2 else (a2, l2, l1)


def _halfplane(poly, ang, t, keep_low=True, c=None):
    """Part of poly whose projection on direction ang is < t (keep_low) or > t (c: poly's centroid, when known)."""
    c = poly.centroid if c is None else c
    d = np.array([math.cos(ang), math.sin(ang)])
    n = np.array([-d[1], d[0]])
    R = 1e5
    base = np.array([c.x, c.y]) + d * t
    if keep_low:
        q = [base + n * R, base + n * R - d * R, base - n * R - d * R, base - n * R]
    else:
        q = [base + n * R, base + n * R + d * R, base - n * R + d * R, base - n * R]
    return clean(poly.intersection(shapely.polygons(np.array(q))))


def _proj_range(poly, ang, c=None):
    c = poly.centroid if c is None else c
    d = np.array([math.cos(ang), math.sin(ang)])
    P = np.asarray(poly.exterior.coords) - [c.x, c.y] if poly.geom_type == "Polygon" else \
        np.vstack([np.asarray(g.exterior.coords) for g in poly.geoms]) - [c.x, c.y]
    pr = P @ d
    return float(pr.min()), float(pr.max())


CUT_SURE_M2 = 1e-6     # m²: a bisection step whose estimated piece area is farther than this (+ CUT_SURE_REL of the polygon's
CUT_SURE_REL = 1e-8    # area) from the wanted area is decided by the estimate, nearer ones by the polygon cut itself (the same
                       # decisions): the ring clip and GEOS's cut differ by ≤ 2.6e-9 m² and ≤ 2e-10 of the area on 26 thousand
                       # cuts of gate_trial's blocks and lots (measured, round 4), so the margin holds them 50 times over


def _roll1(a):
    """np.roll(a, -1) along the first axis (the same values, without np.roll's overhead)."""
    return np.concatenate((a[1:], a[:1]))


def _rings_rel(poly, c=None):
    """[(ring coordinates relative to the centroid, the same rolled by one, ±1 sign of the ring's area in the part, the ring's
    signed half shoelace)] of a valid (multi)polygon."""
    c = poly.centroid if c is None else c
    out = []
    for q in (poly.geoms if poly.geom_type == "MultiPolygon" else [poly]):
        for k, ring in enumerate([q.exterior] + list(q.interiors)):
            P = np.asarray(ring.coords)[:-1, :2] - [c.x, c.y]
            if len(P) < 3:
                continue
            x, y = P[:, 0], P[:, 1]
            s = float(np.dot(x, _roll1(y)) - np.dot(_roll1(x), y))
            if s != 0.0:
                ks = (1.0 if k == 0 else -1.0) * (1.0 if s > 0 else -1.0)
                out.append((P, _roll1(P), ks, 0.5 * s))
    return out


def _clip_area(rings, d, t, keep_low, proj=None):
    """Area of the part with projection on d below t (keep_low) or above t, by clipping each ring at the line (a half-plane
    clip keeps the winding inside the half-plane, so the signed areas add up to the area of the part). proj: each ring's
    projections on d (P @ d), when the caller cuts the same rings along d many times."""
    tot = 0.0
    for k, (P, Pn, ks, full) in enumerate(rings):
        s = (P @ d if proj is None else proj[k]) - t
        inside = s <= 0 if keep_low else s >= 0
        if inside.all():
            tot += ks * full
            continue
        if not inside.any():
            continue
        sn = _roll1(s)
        cross = inside != _roll1(inside)
        den = s - sn
        f = np.divide(s, den, out=np.zeros_like(s), where=cross)
        X = P + f[:, None] * (Pn - P)
        n = len(P)
        pts = np.empty((2 * n, 2))
        pts[0::2] = P
        pts[1::2] = X
        keep = np.empty(2 * n, dtype=bool)
        keep[0::2] = inside
        keep[1::2] = cross
        Q = pts[keep]
        if len(Q) < 3:
            continue
        x, y = Q[:, 0], Q[:, 1]
        tot += ks * 0.5 * float(np.dot(x, _roll1(y)) - np.dot(_roll1(x), y))
    return tot


def cut_at_area(poly, ang, area, from_low=True):
    """Cut poly by a line ⟂ ang so that the piece on the low (or high) side has ≈ area. Returns (piece, rest).
    Bisection on the cut line; a step far from the wanted area is decided from an estimate of the piece's area (a ring clip
    in numpy), the near ones by the polygon cut as always — the steps, and so the cut, are those of cutting every time."""
    c = poly.centroid
    lo, hi = _proj_range(poly, ang, c)
    a, b = lo, hi
    rings = _rings_rel(poly, c) if poly.geom_type in ("Polygon", "MultiPolygon") and poly.is_valid else None
    d = np.array([math.cos(ang), math.sin(ang)])
    proj = [P @ d for P, _, _, _ in rings] if rings is not None else None
    sure = CUT_SURE_M2 + CUT_SURE_REL * poly.area
    for _ in range(30):
        m = (a + b) / 2
        est = _clip_area(rings, d, m, from_low, proj) if rings is not None else None
        if est is not None and abs(est - area) > sure:
            low_side = est < area
        else:
            low_side = _halfplane(poly, ang, m, keep_low=from_low, c=c).area < area
        if low_side == from_low:
            a = m
        else:
            b = m
    m = (a + b) / 2
    return _halfplane(poly, ang, m, keep_low=from_low, c=c), _halfplane(poly, ang, m, keep_low=not from_low, c=c)


def strips(poly, ang, n):
    """n pieces of equal area by cuts ⟂ ang."""
    out = []
    rest = poly
    for i in range(n - 1):
        piece, rest = cut_at_area(rest, ang, rest.area / (n - i))
        out.append(piece)
    out.append(rest)
    return out


def split_lots(poly, target, max_depth, min_area, frame=None):
    """Lots of ≈ target m² that keep frontage: halve along the long axis while the block is deeper than 2 × max_depth,
    then cut strips ⟂ the long axis. Pieces below min_area merge back into a neighbour. With the block's frame
    (frame_angle) every cut is square to it, so side lines stay parallel."""
    out = []
    stack = [poly]
    while stack:
        p = stack.pop()
        if p.area <= target * 1.35 or p.area < 2 * min_area:
            out.append(p)
            continue
        ang, L, W = axis(p) if frame is None else frame_axis(p, frame)
        if W > 2 * max_depth and W > 0:
            a, b = cut_at_area(p, ang + math.pi / 2, p.area / 2)
            parts = polys(a, 1.0) + polys(b, 1.0)
            if len(parts) < 2:
                out.append(p)
                continue
            stack += parts
            continue
        n = max(2, int(round(p.area / target)))
        parts = []
        for q in strips(p, ang, n):
            parts += polys(q, 1.0)
        if len(parts) < 2:
            out.append(p)
            continue
        out += parts
    # merge slivers
    big = [p for p in out if p.area >= min_area]
    small = [p for p in out if p.area < min_area]
    for s in small:
        if not big:
            big.append(s)
            continue
        j = max(range(len(big)), key=lambda i: big[i].intersection(s.buffer(0.5)).area)
        if big[j].intersection(s.buffer(0.5)).area > 0:
            big[j] = clean(unary_union([big[j], s]))
        else:
            big.append(s)
    return big


def oriented_rect(cx, cz, ang, L, W):
    d = np.array([math.cos(ang), math.sin(ang)])
    n = np.array([-d[1], d[0]])
    c = np.array([cx, cz])
    return Polygon([c + d * L / 2 + n * W / 2, c - d * L / 2 + n * W / 2, c - d * L / 2 - n * W / 2, c + d * L / 2 - n * W / 2])


def edge_angle_to(poly, other):
    """Angle of the polygon edge closest to `other` (the street): buildings run along it."""
    c = np.asarray(poly.exterior.coords if poly.geom_type == "Polygon" else max(polys(poly), key=lambda q: q.area).exterior.coords)
    best, ang = 1e18, axis(poly)[0]
    for a, b in zip(c[:-1], c[1:]):
        L = np.hypot(*(b - a))
        if L < 5:
            continue
        d = LineString([a, b]).distance(other)
        score = d - 0.001 * L
        if score < best:
            best, ang = score, math.atan2(b[1] - a[1], b[0] - a[0])
    return ang


def strtree(geoms):
    return shapely.STRtree(np.asarray(geoms, dtype=object))


def stable_hash(s):
    h_ = 2166136261
    for ch in s.encode("utf-8"):
        h_ = ((h_ ^ ch) * 16777619) & 0xFFFFFFFF
    return h_


# ---------------------------------------------------------------------------------------------------- spec helpers
def zone_rules(z):
    r = dict(z.get("rules") or {})
    d = z.get("density") or {}
    r.setdefault("far", d.get("far"))
    r.setdefault("homes_per_ha", d.get("homes_per_ha"))
    r.setdefault("jobs_per_ha", d.get("jobs_per_ha"))
    if "floors" not in r and d.get("floors_typical"):
        r["floors"] = [max(1, d["floors_typical"] - 2), d["floors_typical"] + 2]
    return r


def zone_years(z):
    y = z.get("years") or [2030, 2040]
    if len(y) == 4:
        return y[0], y[0]
    return int(y[0]), int(y[-1])


def low_rise_max(norms):
    """Top floor count of «малоэтажная» in quarters.floor_zone_types (key "1_3" → 3)."""
    for k, v in norms.v("quarters.floor_zone_types").items():
        if "мало" in str(v):
            return int(k.split("_")[-1])
    raise KeyError("quarters.floor_zone_types: no low-rise type")


def low_rise(z_rules, norms):
    """Low-rise zone by C08 floor types (quarters.floor_zone_types)."""
    fl = z_rules.get("floors") or [1, 1]
    return fl[1] <= low_rise_max(norms)


def corridors(spec):
    """Utility corridors [{id, kind, line, state: overhead|cable, width_m, years, source}] of the district: spec corridors[]
    when the spec lists them (fixture); otherwise the overhead power lines of the level-0 Overture infrastructure layer that
    cross the area, minus those a spec utility replaces (utilities[].replaces names the OSM line); plus spec utilities[]
    (a 220 kV cable replacing an overhead line: state cable, its strip is utilities.to_foundations_m.cables)."""
    if "_corridors" in spec:
        return spec["_corridors"]
    out = list(spec.get("corridors") or [])
    replaced = set()
    for u in spec.get("utilities") or []:
        m = re.search(r"([0-9a-f]{8})", str(u.get("replaces") or ""))
        if m:
            replaced.add(m.group(1))
        out.append({"id": u["id"], "kind": u.get("kind", "cable"), "line": u["line"], "state": "cable", "width_m": None,
                    "years": u.get("years"), "source": "spec utilities", "replaces": u.get("replaces")})
    if spec.get("corridors") is None:
        try:
            sys.path.insert(0, GEO_DIR)
            import layers
            g, p = layers.load("infrastructure")
            area = work_polygon(spec).buffer(50.0)
            for gg, pp in zip(g, p):
                if pp.get("subtype") != "power" or pp.get("class") not in ("power_line", "minor_line") or not gg.intersects(area):
                    continue
                short = str(pp.get("id", ""))[:8]
                if short in replaced:
                    continue
                for part in getattr(gg.intersection(area.buffer(100.0)), "geoms", [gg.intersection(area.buffer(100.0))]):
                    if part.geom_type == "LineString" and part.length > 1.0:
                        out.append({"id": f"pl_{short}", "kind": "power_line", "line": [[round(x, 1), round(z, 1)] for x, z in part.coords],
                                    "state": "overhead", "width_m": None, "source": "osm:" + str(pp.get("id")), "years": list(EXISTING_YEARS),
                                    "osm_class": pp.get("class")})
        except (OSError, ImportError, ValueError):
            pass
    spec["_corridors"] = out
    return out


# voltage assumed for an overhead line of unknown voltage, by its OSM class: minor_line is a distribution line, power_line the
# smallest transmission class (a model assumption about the OSM tags, not a norm; a spec corridor's kv overrides it)
UNKNOWN_KV = {"minor_line": 10, "power_line": 35}


def power_zone_m(norms, c):
    """(half width from the axis, m; kV taken; True if the voltage is assumed) of the protected zone of an overhead line:
    utilities.power_line_protection_zone_m (by voltage class) for c["kv"]; a corridor's own width_m wins; None for a gas pipe
    or a cable."""
    if c.get("width_m"):
        return float(c["width_m"]), c.get("kv"), False
    if c.get("kind") != "power_line" or c.get("state") == "cable":
        return None, None, False
    tab = norms.v("utilities.power_line_protection_zone_m")
    if not isinstance(tab, dict):
        return None, None, False
    kv, assumed = c.get("kv"), False
    if kv is None:
        kv, assumed = UNKNOWN_KV.get(c.get("osm_class") or "power_line", UNKNOWN_KV["power_line"]), True
    # classes by their upper voltage («1-20kV» → 20, «up_to_1kV_bare» → 1); the insulated low-voltage row only when asked
    ins = bool(c.get("insulated"))
    cls = sorted((float(re.findall(r"(\d+(?:\.\d+)?)kV", k)[-1]), k) for k in tab
                 if "kV" in k and (ins if "insulated" in k else (not ins if "bare" in k else True)))
    for top, k in cls:
        if float(kv) <= top + 1e-9:
            return float(tab[k]), kv, assumed
    return float(tab[cls[-1][1]]), kv, assumed


def keep_polys(spec):
    return [(k, from_coords(k["polygon"])) for k in spec.get("keep", [])]


def water_geoms(work, buffer_m=0.0):
    """Water polygons and watercourse lines (Overture water layer of level 0) near the work polygon."""
    import layers
    g, p = layers.load("water")
    sel = np.flatnonzero(shapely.intersects(g, work.buffer(buffer_m + 200)))
    pol, lin = [], []
    for i in sel:
        q = g[i]
        if q.geom_type in ("Polygon", "MultiPolygon"):
            pol += polys(clean(q))
        elif q.geom_type in ("LineString", "MultiLineString"):
            lin.append((q, p[i]))
    return pol, lin


def flood_poly(work, norms):
    """Land below the Kapchagay design level + freeboard (flood.kapchagay_levels_m npu_design_max + flood.freeboard_m)."""
    lvl = norms.num("flood.kapchagay_levels_m", "npu_design_max") + norms.num("flood.freeboard_m")
    T = terrain()
    x0, z0, x1, z1 = work.bounds
    xs = np.arange(x0, x1 + T.step, T.step)
    zs = np.arange(z0, z1 + T.step, T.step)
    X, Z = np.meshgrid(xs, zs)
    H = T.height(X, Z)
    cells = [box(x - T.step / 2, z - T.step / 2, x + T.step / 2, z + T.step / 2) for x, z, hh in zip(X.ravel(), Z.ravel(), H.ravel()) if hh < lvl]
    return clean(unary_union(cells).intersection(work)) if cells else Polygon(), lvl


_TWIN_NORMS = []


def twin_norms():
    """The twin's own norms module (Tools/twin_gen/norms.py): M2_PER_* constants of CityStats. Loaded once per process (the
    validator asks for it per house: loading the file each time cost rule 14 seconds on a district)."""
    if not _TWIN_NORMS:
        import importlib.util
        sp = importlib.util.spec_from_file_location("twin_gen_norms", os.path.join(TWIN_GEN, "norms.py"))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        _TWIN_NORMS.append(m)
    return _TWIN_NORMS[0]


def twin_m2():
    """The twin's own panel formulas (CityStats.cs / Tools/twin_gen/norms.py): m² of GFA per resident and per job."""
    tn = twin_norms()
    return tn.M2_PER_RESIDENT, dict(tn.M2_PER_JOB), tn.M2_PER_SCHOOL_SEAT, tn.M2_PER_KG_PLACE


def social_m2(norms):
    """(m² of building floor area per school seat, per kindergarten place): schools.building_m2_per_seat and
    kindergartens.building_m2_per_place of norms.json («модель qTwin», the twin's own figures), as rule 13 measures a social
    building against its lot's capacity."""
    return float(norms.num("schools.building_m2_per_seat")), float(norms.num("kindergartens.building_m2_per_place"))


def floor_heights():
    """Median storey height by buildings.csv kind (the twin's own meshes; model qTwin)."""
    import twin
    df = twin.buildings()
    df = df[df.floors > 0]
    return (df.height_m / df.floors).groupby(df.kind).median().round(2).to_dict()


class Log:
    def __init__(self):
        self.rows = []

    def __call__(self, what, ids=None, **kw):
        r = {"what": what, "ids": list(ids or [])}
        r.update(kw)
        self.rows.append(r)


# ------------------------------------------------------------------------------------------------------- walking network
class SegIndex:
    """Points of a WalkNet.points() set by the walkable segment they snap to: get(segment id) → their indices (ascending)."""
    __slots__ = ("seg", "sidx", "_order", "_sorted")

    def __init__(self, seg, sidx):
        self.seg, self.sidx = seg, sidx
        self._order = np.argsort(seg, kind="stable")
        self._sorted = seg[self._order]

    def get(self, sid, default=None):
        c = self.sidx.get(sid)
        if c is None:
            return default
        lo, hi = np.searchsorted(self._sorted, c, "left"), np.searchsorted(self._sorted, c, "right")
        return self._order[lo:hi] if hi > lo else default

    def subset(self, idx):
        return SegIndex(self.seg[idx], self.sidx)

    @staticmethod
    def concat(parts):
        return SegIndex(np.concatenate([q.seg for q in parts]), parts[0].sidx)


class WalkNet:
    """Pedestrian graph of the network (every class with sidewalks or paths; expressways and ramps excluded).
    dist_from(points) → per-node distance; dist_to(p, D) → walking distance from point p using node distances D."""

    def __init__(self, net, exclude=("expressway", "ramp")):
        import networkx as nx
        self.G = nx.Graph()
        self.segs = []
        for s in net.get("segments", []):
            if s["class"] in exclude:
                continue
            ls = seg_line(s)
            if ls.length <= 0:
                continue
            self.segs.append((s, ls))
            w = ls.length
            if self.G.has_edge(s["a"], s["b"]):
                w = min(w, self.G[s["a"]][s["b"]]["w"])
            self.G.add_edge(s["a"], s["b"], w=w)
        self.tree = shapely.STRtree([ls for _, ls in self.segs]) if self.segs else None

    def snap(self, x, z):
        """(segment, along, perpendicular, length) of the nearest walkable segment (cached)."""
        if self.tree is None:
            return None
        key = (round(x, 1), round(z, 1))
        c = self._cache.get(key) if hasattr(self, "_cache") else None
        if c is not None:
            return c
        if not hasattr(self, "_cache"):
            self._cache = {}
        p = Point(x, z)
        i = self.tree.nearest(p)
        s, ls = self.segs[int(i)]
        r = (s, ls.project(p), ls.distance(p), ls.length)
        self._cache[key] = r
        return r

    def dist_from(self, pts, cutoff=None):
        """Multi-source Dijkstra from points [(x, z)]: {node: metres}. With cutoff, nodes farther than cutoff are left out
        (dist_to then gives inf there — enough for every «within the radius» question with cutoff ≥ the radius)."""
        import heapq
        if not hasattr(self, "_adj"):
            self._adj = {n: [(m, d["w"]) for m, d in self.G[n].items()] for n in self.G.nodes}
        adj = self._adj
        same = {}
        D = {}
        heap = []
        for x, z in pts:
            sn = self.snap(x, z)
            if sn is None:
                continue
            s, along, perp, L = sn
            same.setdefault(s["id"], []).append((along, perp))
            for n, d in ((s["a"], perp + along), (s["b"], perp + (L - along))):
                if d < D.get(n, float("inf")):
                    D[n] = d
                    heapq.heappush(heap, (d, n))
        if not D:
            return {}
        done = {}
        while heap:
            d, n = heapq.heappop(heap)
            if n in done or d > D[n]:
                continue
            if cutoff is not None and d > cutoff:
                break
            done[n] = d
            for m, w in adj[n]:
                nd = d + w
                if m not in done and nd < D.get(m, float("inf")):
                    D[m] = nd
                    heapq.heappush(heap, (nd, m))
        done["__same__"] = same       # sources per segment: a point on the same segment walks along it directly
        return done

    def points(self, xz):
        """Snapped points [(x, z)] for dist_many: node indices, along, length − along, perpendicular, segment per point."""
        if not hasattr(self, "_nidx"):
            self._nidx = {nd: i for i, nd in enumerate(self.G.nodes)}
        nul = len(self._nidx)                   # index of «no node»: infinite distance
        n = len(xz)
        if not hasattr(self, "_sidx"):
            self._sidx = {s["id"]: i for i, (s, _) in enumerate(self.segs)}
        A, B = np.full(n, nul, dtype=np.int64), np.full(n, nul, dtype=np.int64)
        al, rest, pe = np.zeros(n), np.zeros(n), np.full(n, np.inf)
        seg = np.full(n, -1, dtype=np.int64)
        for k, (x, z) in enumerate(xz):
            sn = self.snap(x, z)
            if sn is None:
                continue
            s, along, perp, L = sn
            A[k], B[k], al[k], rest[k], pe[k] = self._nidx[s["a"]], self._nidx[s["b"]], along, L - along, perp
            seg[k] = self._sidx[s["id"]]
        return A, B, al, rest, pe, SegIndex(seg, self._sidx)

    def dist_many(self, P, D):
        """dist_to for every point of P (points()) at once: the same sums in the same order, as a numpy array."""
        Dn = np.full(len(self._nidx) + 1, np.inf)
        idx = self._nidx
        for nd, d in D.items():
            if nd != "__same__":
                Dn[idx[nd]] = d
        return self.dist_dense(P, Dn, D.get("__same__") or {})

    def dist_arr(self, pts, cutoff=None):
        """dist_from as arrays (node indices, metres, sources per segment): kept, merged by np.minimum (a multi-source run
        is exactly the minimum of its sources' runs) and spread into a dense vector for dist_dense."""
        if not hasattr(self, "_nidx"):
            self._nidx = {nd: i for i, nd in enumerate(self.G.nodes)}
        D = self.dist_from(pts, cutoff)
        same = D.pop("__same__", None) or {}
        idx = self._nidx
        ix = np.fromiter((idx[n] for n in D), dtype=np.int64, count=len(D))
        return ix, np.fromiter(D.values(), dtype=float, count=len(D)), same

    def dense(self, arr, out=None):
        """Dense node vector (inf where no distance) of a dist_arr result."""
        Dn = np.full(len(self._nidx) + 1, np.inf) if out is None else out
        if out is not None:
            Dn.fill(np.inf)
        Dn[arr[0]] = arr[1]
        return Dn

    def dist_dense(self, P, Dn, same):
        """dist_many from a dense node vector Dn and the sources per segment."""
        A, B, al, rest, pe, by_seg = P
        best = np.minimum(Dn[A] + al, Dn[B] + rest) + pe
        for sid, srcs in same.items():
            ks = by_seg.get(sid)
            if ks is None or not len(ks):
                continue
            al_k, pe_k = al[ks], pe[ks]
            b_k = best[ks]
            for a2, p2 in srcs:            # the same sums per point as one at a time (elementwise float64)
                b_k = np.minimum(b_k, np.abs(a2 - al_k) + p2 + pe_k)
            best[ks] = b_k
        return best

    def dist_to(self, x, z, D, direct=None):
        sn = self.snap(x, z)
        best = float("inf")
        if sn is not None:
            s, along, perp, L = sn
            best = min(D.get(s["a"], float("inf")) + along, D.get(s["b"], float("inf")) + (L - along)) + perp
            for a2, p2 in D.get("__same__", {}).get(s["id"], ()):
                best = min(best, abs(a2 - along) + p2 + perp)
        if direct is not None:
            best = min(best, direct)
        return best
