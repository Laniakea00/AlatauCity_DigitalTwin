"""Norms lookup (spec/norms.json): numbers by key, statuses, severities, road profiles, the red line, the node matrix.

    from lib import norms
    N = norms.get()
    N.norm("bridges.road_clearance_m")        # 5.0
    N.sev("ramps.loop_radius_m")              # "warning" (analogue)
    N.profile("local")                        # CONTRACT §4 profile dict
    N.red_line_w("arterial_regulated")        # one definition of the red line per class
    N.matrix_cell("expressway", "district_transport")
"""
import copy
import json
import os

from . import paths

_N = None

# The bike treatment by class (the norms give it as text): a separated path on both sides where the text says
# «обособленная велодорожка» for a street of city type with car speed > 30 km/h; zone 30 / shared lane otherwise.
_BIKE_SEPARATED = {"arterial_continuous", "arterial_regulated", "district_transport", "district_pedestrian",
                   "arterial_road_regulated", "industrial"}
_BIKE_LANE = {"district_pedestrian"}


class Norms:
    def __init__(self, path=None):
        self.path = path or os.path.join(paths.SPEC, "norms.json")
        with open(self.path, encoding="utf-8") as f:
            self.raw = json.load(f)
        self.N = self.raw["norms"]
        self.road_classes = self.raw["road_classes"]
        self.street_profiles = self.raw["street_profiles"]
        self.node_types = self.raw["node_types"]
        self.node_matrix = self.raw["node_matrix"]
        self.crossing_matrix = self.raw["crossing_matrix"]
        self._profiles = {}

    # ------------------------------------------------------------------ numbers
    def rec(self, key):
        """The full record of a norm key (also street.<class>.<field> keys of street_profiles)."""
        if key in self.N:
            return self.N[key]
        if key.startswith("street."):
            _, cls, field = key.split(".", 2)
            r = self.street_profiles.get(cls, {}).get(field)
            if r is not None:
                return r
        raise KeyError(f"norm {key} not in norms.json")

    def norm(self, key, sub=None, default=KeyError):
        """Value of a norm key; `sub` walks into a dict value ("a.b" or a list of keys)."""
        try:
            v = self.rec(key)["value"]
        except KeyError:
            if default is KeyError:
                raise
            return default
        if sub is not None:
            for k in (sub.split(".") if isinstance(sub, str) else sub):
                v = v[k]
        return v

    def has(self, key):
        try:
            self.rec(key)
            return True
        except KeyError:
            return False

    def status(self, key):
        return self.rec(key).get("status", "norm")

    def sev(self, key):
        """error for a norm, warning for an analogue / not_verified number (severity_policy), unless the record says."""
        r = self.rec(key)
        s = r.get("severity")
        if s in ("error", "warning", "info"):
            return s
        return "error" if r.get("status", "norm") == "norm" else "warning"

    def sev_any(self, *keys):
        """The mildest severity among the norms a check depends on (an analogue number makes the check a warning)."""
        out = "error"
        for k in keys:
            if self.sev(k) != "error":
                out = "warning"
        return out

    # ------------------------------------------------------------------ classes and nodes
    def node_group(self, cls):
        g = self.road_classes.get(cls, {}).get("node_group")
        if cls == "boulevard":
            return "pedestrian"
        return g

    def matrix_cell(self, ca, cb):
        """The node_matrix cell of two road classes (unordered), or None (no cell: pedestrian, bike, ramp…)."""
        ga, gb = self.node_group(ca), self.node_group(cb)
        for m in self.node_matrix:
            if (m["a"], m["b"]) in ((ga, gb), (gb, ga)):
                return m
        return None

    def at_grade_allowed(self, ca, cb):
        """True when the pair may meet in one level (some at-grade type is allowed)."""
        m = self.matrix_cell(ca, cb)
        if m is None:
            return None
        return any(self.node_types[t]["level"] == "at_grade" for t in m["allowed"])

    def lrt_crossing_allowed(self, cls):
        """May the ground LRT cross a road of class `cls` in one level (lrt.at_grade_crossing: only at a level-crossing
        node with signals)? By norms.json crossing_matrix `lrt_at_grade` (its row of the class's node group allows
        level_crossing_signal: not on expressways and continuous arterials); a group no row lists may, except a ramp."""
        g = self.node_group(cls)
        for row in self.raw.get("crossing_matrix") or []:
            if row.get("a") == "lrt_at_grade" and g in (row.get("b") or []):
                return "level_crossing_signal" in (row.get("allowed") or [])
        return g != "ramp"

    def default_node(self, ca, cb):
        """Default junction type of an at-grade crossing that the spec did not list (first preferred at-grade type)."""
        m = self.matrix_cell(ca, cb)
        if m is None:
            return "crossing"
        for t in (m.get("preferred") or []) + m["allowed"]:
            if self.node_types.get(t, {}).get("level") == "at_grade":
                return t
        return "grade_separation"

    def class_rank(self, cls):
        """Rank for major/minor decisions: lower = more important."""
        order = ["expressway", "arterial_continuous", "arterial_road_regulated", "arterial_regulated",
                 "district_transport", "district_pedestrian", "industrial", "local", "village_main", "park_road",
                 "local_secondary", "village_secondary", "driveway_main", "driveway_secondary", "village_lane",
                 "ramp", "boulevard", "pedestrian_street", "bike_path"]
        return order.index(cls) if cls in order else len(order)

    # ------------------------------------------------------------------ profiles (CONTRACT §4)
    def _sp(self, cls, field, default=None):
        r = self.street_profiles.get(cls, {}).get(field)
        return default if r is None else r["value"]

    def slope_max(self, cls):
        """Max grade as a fraction for a class (street_profiles slope_max_permille; dict → the strictest value)."""
        v = self._sp(cls, "slope_max_permille")
        if v is None:
            if cls in ("village_main", "village_secondary"):
                v = self._sp("local", "slope_max_permille")
            elif cls == "village_lane":
                v = self._sp("driveway_main", "slope_max_permille")
            elif cls == "boulevard":
                v = self._sp("pedestrian_street", "slope_max_permille")
            else:
                v = self._sp("local", "slope_max_permille")
        if isinstance(v, dict):
            v = min(v.values())
        return float(v) / 1000.0

    def r_min(self, cls):
        v = self._sp(cls, "r_min_m")
        if isinstance(v, dict):
            v = min(v.values())
        return float(v) if v is not None else None

    def speed(self, cls):
        v = self._sp(cls, "speed_kmh")
        if isinstance(v, dict):
            v = v.get("design") or min(x for x in v.values() if isinstance(x, (int, float)))
        return v

    def profile(self, cls, overrides=None):
        """Cross-section of a class (CONTRACT §4 profile dict) with optional overrides (any of its fields).

        Extra fields: carriageways (1 or 2), cw_w (one carriageway), shoulder_w [l, r], cw_offset (axis → carriageway
        centreline of a divided road), src (where each number came from)."""
        if cls not in self._profiles:
            self._profiles[cls] = self._base_profile(cls)
        p = copy.deepcopy(self._profiles[cls])
        if overrides:
            for k, v in overrides.items():
                p[k] = v
            if "lanes" in overrides and "carriageways" not in overrides and cls in ("arterial_road_regulated",):
                tot = sum(p["lanes"])
                cw = self._sp(cls, "carriageways")
                if isinstance(cw, dict):
                    p["carriageways"] = cw["lanes_ge_4"] if tot >= 4 else cw["lanes_lt_4"]
            self._finish(p)
        return p

    def _base_profile(self, cls):
        if cls not in self.street_profiles:
            raise KeyError(f"road class {cls} not in norms.street_profiles")
        src = {}
        lanes_v = self._sp(cls, "lanes")
        lane_w = self._sp(cls, "lane_width_m")
        if isinstance(lane_w, dict):
            lane_w = lane_w.get("design", lane_w.get("min"))
        cw = self._sp(cls, "carriageways", 1)
        median = self._sp(cls, "median_m", 0) or 0
        sidewalk = self._sp(cls, "sidewalk_m", 0) or 0
        verge = self._sp(cls, "green_strip_m", 0) or 0
        shoulder = self._sp(cls, "shoulder_m", 0) or 0
        if isinstance(lanes_v, dict):
            if "min" in lanes_v:
                lanes = int(lanes_v["min"])
            else:          # bike_path {separated:{min,max}, isolated:{…}}
                lanes = int(min(v["min"] for v in lanes_v.values() if isinstance(v, dict)))
        else:
            lanes = int(lanes_v) if lanes_v is not None else 0
        if isinstance(cw, dict):
            cw = cw["lanes_ge_4"] if lanes >= 4 else cw["lanes_lt_4"]
        if isinstance(median, dict):
            median = median.get("no_barrier_min", median.get("min", 0))
        if int(cw) == 1 and cls not in ("boulevard",):
            median = 0                             # a median exists only between two carriageways
        if isinstance(verge, dict):
            verge = min(v for v in verge.values() if isinstance(v, (int, float)))
        oneway = False
        if cls == "ramp":
            w = self._sp("ramp", "width_m")
            sh = self._sp("ramp", "shoulder_m")
            lanes, lane_w, cw, median, sidewalk, verge = 1, float(w["right_turn"]), 1, 0, 0, 0
            shoulder = [float(sh["inner"]), float(sh["outer"])]
            oneway = True
            src["lane_w"] = "street.ramp.width_m.right_turn"
        elif cls == "pedestrian_street":
            ex = self._sp(cls, "width_examples_m")
            width = float(min(ex["pedestrian_streets"]))
            lanes, lane_w, cw, median, verge = 0, 0.0, 1, 0, 0
            sidewalk = width / 2.0
            src["sidewalk_w"] = "street.pedestrian_street.width_examples_m (меньший пример, по половине на сторону)"
        elif cls == "boulevard":
            gw = self._sp(cls, "green_width_m")
            pw = self._sp(cls, "path_width_multiple_m")
            lanes, lane_w, cw = 0, 0.0, 1
            median = float(gw["on_axis_min"])
            sidewalk = 4 * float(pw)             # a path of 4 walking lanes on each side of the green
            verge = 0
            src["median_w"] = "street.boulevard.green_width_m.on_axis_min (зелень по оси)"
            src["sidewalk_w"] = "4 × street.boulevard.path_width_multiple_m (аллея с каждой стороны)"
        elif cls == "bike_path":
            lanes = 2                              # a two-way path: the upper value of street.bike_path.lanes.separated
            sidewalk, verge, median = 0, 0, 0
            src["lanes"] = "street.bike_path.lanes.separated.max (двусторонняя дорожка)"
        elif cls in ("village_main", "village_secondary", "village_lane"):
            cwm = self._sp(cls, "carriageway_m")
            if cwm and lanes:
                lane_w = float(cwm) / lanes
        if lane_w is None:
            lane_w = 0.0
        lane_w = float(lane_w)
        # lanes per direction
        if oneway:
            lanes_fb = [lanes, 0]
        elif lanes <= 1 and cls not in ("pedestrian_street", "boulevard"):
            # one lane for both directions (village lane, secondary driveway): two half lanes so the width is right
            lanes_fb = [1, 1]
            lane_w = lane_w / 2.0
            src["lanes"] = "одна полоса на оба направления: две полуполосы (ширина проезжей части как в норме)"
        else:
            lanes_fb = [lanes - lanes // 2, lanes // 2]
        bike = 0.0
        if cls in _BIKE_SEPARATED:
            bike = float(self._sp("bike_path", "lane_width_m"))
            src["bike_w"] = "street.bike_path.lane_width_m (обособленная велодорожка по тексту street.<класс>.bike)"
        if cls in _BIKE_LANE:
            bike = float(self.norm("street_xs.bike_lane_on_carriageway_m", "one_way"))
        p = {"class": cls, "lanes": lanes_fb, "lane_w": lane_w, "median_w": float(median),
             "sidewalk_w": [float(sidewalk)] * 2, "verge_w": [float(verge)] * 2, "bike_w": [bike, bike],
             "parking_w": [0.0, 0.0], "carriageways": int(cw), "oneway": oneway,
             "shoulder_w": shoulder if isinstance(shoulder, list) else [float(shoulder)] * 2, "src": src}
        self._finish(p)
        return p

    def _finish(self, p):
        cls = p["class"]
        lanes = p["lanes"]
        if p.get("oneway"):
            p["cw_w"] = lanes[0] * p["lane_w"]
            p["cw_offset"] = 0.0
            p["carriageways"] = 1
        elif p["carriageways"] == 2:
            p["cw_w"] = max(lanes) * p["lane_w"]           # one carriageway of a divided road
            p["cw_offset"] = p["median_w"] / 2.0 + p["cw_w"] / 2.0
        else:
            p["cw_w"] = sum(lanes) * p["lane_w"]
            p["cw_offset"] = 0.0
        p["width"] = self.cross_width(p)
        rl = self._sp(cls, "red_lines_m")
        rmin = float(rl["min"]) if isinstance(rl, dict) else 0.0
        p["red_line_w"] = round(max(p["width"], rmin), 2)

    @staticmethod
    def cross_width(p):
        """Full width of the cross-section between its outer edges (carriageways, median, shoulders, sidewalks…)."""
        if p.get("oneway"):
            core = p["cw_w"]
        elif p["carriageways"] == 2:
            core = 2 * p["cw_w"] + p["median_w"]
        else:
            core = p["cw_w"] + p["median_w"]
        side = sum(p["shoulder_w"]) + sum(p["sidewalk_w"]) + sum(p["verge_w"]) + sum(p["bike_w"]) + sum(p["parking_w"])
        return round(core + side, 2)

    def red_line_w(self, cls, overrides=None):
        """One definition of the red-line width (m) for a class: the cross-section width, at least the class minimum."""
        return self.profile(cls, overrides)["red_line_w"]

    def carriage_half(self, p):
        """Half width of the paved carriageway band of a segment drawn with profile p (a oneway segment = itself)."""
        return p["cw_w"] / 2.0 if (p.get("oneway") or p["carriageways"] == 2) else (p["cw_w"] + p["median_w"]) / 2.0


def get(path=None):
    global _N
    if path is not None:
        return Norms(path)
    if _N is None:
        _N = Norms()
    return _N
