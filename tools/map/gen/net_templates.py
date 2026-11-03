"""Interchange and junction templates of gen_network (w43), built on the real carriageway geometry.

Every ramp is made of exact pieces, so the rules hold by construction:
* diverge / merge on a carriageway: the ramp starts (ends) at a point OF the carriageway polyline (gap 0, one node),
  leaves it with a cos-shaped taper whose largest divergence angle is ≤ ramps.merge_angle_max_deg, its tip a straight
  wedge of ramps.tapers_scdot entrance_taper_desired (70:1) so the ramp keeps to its own side up to the node, and
  runs a parallel speed-change lane whose inner edge is the carriageway's outer edge for the length of
  ramps.speed_change_lanes_kz_m (decel / accel);
* curves: Dubins paths (arcs of the ramp radius and straights, tangent at both ends), then clothoid-like transitions
  (curvature averaged over a transition length; end points and end tangents kept exactly);
* terminals on the minor road: a straight of MODEL terminal_straight_m perpendicular to the minor road (junction 90°);
* loops: 180° (parclo terminal loops) or 270° (cloverleaf) right-hand arcs of the loop radius tangent to both lanes;
* levels: the upper road is marked lifted around the crossing; the height solver raises it by clearance + deck depth
  over every way it crosses there and records the overpass span.
Each template checks its own result (no crossing of ramps, clear gap between ramps, angles) and returns a log line.

Coordinates: X east, Z north, right-hand traffic.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import geom as G  # noqa: E402
from lib import model  # noqa: E402
from lib import years as Y  # noqa: E402
from net_core import Way  # noqa: E402

TEMPLATES = ["diamond", "partial_cloverleaf", "cloverleaf", "trumpet", "directional", "grade_separation",
             "roundabout", "square"]


class TemplateError(Exception):
    pass


# ------------------------------------------------------------------ norms used by the templates
class RampNorms:
    def __init__(self, N, major_cls):
        self.N = N
        fast = major_cls in ("expressway", "arterial_continuous")
        tbl = N.norm("ramps.speed_change_lanes_kz_m")
        row = tbl["I-b_II"] if fast else tbl["III"]
        self.accel, self.decel, self.taper_norm = float(row[0]), float(row[1]), float(row[2])
        self.max_angle = float(N.norm("ramps.merge_angle_max_deg"))
        sp = N.norm("ramps.design_speed_kmh")
        self.speed = float(sp["from_I_II"] if fast else sp["from_III"])
        rr = N.norm("ramps.min_radius_by_speed_m")
        ks = sorted((float(k), float(v)) for k, v in rr.items())
        self.R = float(np.interp(self.speed, [k for k, _ in ks], [v for _, v in ks]))
        lr = N.norm("ramps.loop_radius_m")
        band = lr["roads_over_80_kmh"] if (N.speed(major_cls) or 0) > 80 else lr["otherwise"]
        self.loop_min, self.loop_max = float(band["min"]), float(band["max"])
        self.loop_R = 0.5 * (self.loop_min + self.loop_max)
        w = N.norm("ramps.width_m")
        self.w_right, self.w_left = float(w["right_turn"]), float(w["left_turn"])
        self.slope = float(N.norm("ramps.slope_max_permille")) / 1000.0
        self.term_angle = N.norm("ramps.secondary_terminal_angle_deg")
        self.straight = model("terminal_straight_m")
        self.gap = model("ramp_clear_gap_m")
        self.cd_w = float(N.norm("ramps.cd_road_width_m", "one_lane"))
        ta = N.norm("ramps.tapers_scdot")
        self.design_angle = min(self.max_angle - 0.5, float(ta["exit_divergence_range_deg"]["max"]))
        a, b = (float(x) for x in str(ta["entrance_taper_desired"]).split(":"))
        self.tip = b / a                  # slope of the straight tip of every taper ("70:1" → 1/70)

    def taper(self, d):
        """Taper length: the norm (отгон), lengthened so the cos taper never diverges more than the design angle."""
        return max(self.taper_norm, G.taper_len_for_angle(d, self.design_angle, "cos"))


# ------------------------------------------------------------------ roads at a crossing
class Road:
    """A road at the crossing point C: its axis and its carriageway Ways.

    divided → cws = {+1: Way travelling along the axis direction, −1: Way travelling against it};
    undivided → cws = {0: the two-way Way}."""

    def __init__(self, cls, prof, axis, cws, name_ru="", years=None, street=None):
        self.cls, self.prof, self.axis, self.cws = cls, prof, G.A(axis), cws
        self.divided = 0 not in cws
        self.name_ru = name_ru
        self.years = years or list(Y.EXISTING)
        self.street = street

    def e(self):
        """Axis → carriageway centreline offset (0 for an undivided road)."""
        if not self.divided:
            return 0.0
        return float(self.prof.get("cw_offset", 0.0))

    def cw_half(self):
        return self.prof["cw_w"] / 2.0 if self.divided else (self.prof["cw_w"] + self.prof["median_w"]) / 2.0

    def half_width(self):
        """Half the paved width incl. shoulders, from the axis."""
        sh = max(self.prof.get("shoulder_w", [0, 0]))
        if self.divided:
            return self.e() + self.prof["cw_w"] / 2.0 + sh
        return self.cw_half() + sh


def road_at(C, road, sign):
    """(carriageway Way, chainage of C on it, unit travel direction there) for the carriageway travelling with
    `sign` (+1 along the axis direction, −1 against). Undivided: the centreline Way in the asked direction."""
    if road.divided:
        w = road.cws[sign]
    else:
        w = road.cws[0]
    s, _, _ = G.project(w.P, C)
    t = w.tan(s)
    if not road.divided and sign < 0:
        t = -t
    return w, s, t


class Frame:
    """One travel direction of the major road at C, and the minor road seen from it (v points to its right side)."""

    def __init__(self, C, major, minor, sign):
        self.C = np.asarray(C, float)
        self.major, self.minor, self.sign = major, minor, sign
        self.cw, self.sC, self.u = road_at(C, major, sign)
        sa, _, _ = G.project(minor.axis, C)
        self.mS = G.chainage(minor.axis)
        self.mC = sa
        tv = G.tangent_at(minor.axis, sa, self.mS)
        self.vsign = 1.0 if np.dot(tv, G.right(self.u)) > 0 else -1.0

    def mpoint(self, t):
        """Minor-axis point at signed distance t from C (t > 0 on this frame's right side)."""
        return G.point_at(self.minor.axis, self.mC + self.vsign * t, self.mS)

    def mtan(self, t):
        """Minor-axis unit tangent at t, pointing to the right side of this frame."""
        return self.vsign * G.tangent_at(self.minor.axis, self.mC + self.vsign * t, self.mS)

    def minor_span(self):
        """Usable t range on each side (stay 30 m off the ends of the minor axis)."""
        L = self.mS[-1]
        if self.vsign > 0:
            return -(self.mC - 30.0), (L - self.mC) - 30.0
        return -((L - self.mC) - 30.0), self.mC - 30.0

    def minor_cw_points(self, t, h):
        """Points where the line through mpoint(t) with direction h meets the minor carriageways:
        (back, front) along h — for an undivided road both are the axis point."""
        A = self.mpoint(t)
        if not self.minor.divided:
            return A, A
        lo, hi = self.minor_span()
        if t > hi + 29.0 or t < lo - 29.0:
            return A, A                 # the terminal is the junction at the minor road's end
        e = self.minor.e()
        pts = []
        for wsg in (1, -1):
            w = self.minor.cws[wsg]
            far = np.vstack([A - h * (e + 40), A + h * (e + 40)])
            cr = G.crossings(far, w.P)
            if not cr:
                raise TemplateError("линия примыкания не пересекает проезжую часть второстепенной дороги")
            pts.append(cr[0][2])
        pts.sort(key=lambda p: float(np.dot(p - A, h)))
        return pts[0], pts[1]


# ------------------------------------------------------------------ pieces
def lane_off(cw, s0, s1, dfun, step=2.0):
    """Polyline along carriageway `cw` from chainage s0 to s1 (s0 < s1) offset by dfun(s) to the right."""
    if s0 < 1.0 or s1 > cw.L - 1.0:
        raise TemplateError(f"проезжая часть {cw.id} коротка для полосы {s0:.0f}…{s1:.0f} м (длина {cw.L:.0f} м)")
    sub = G.cut(cw.P, s0, s1)
    sub = G.densify(sub, step)
    S = G.chainage(sub) + s0
    nr, sc = G.vertex_normals(sub)
    dv = np.array([dfun(s) for s in S])
    out = sub + nr * (dv * sc)[:, None]
    out[0] = sub[0] if abs(dfun(S[0])) < 1e-9 else out[0]
    out[-1] = sub[-1] if abs(dfun(S[-1])) < 1e-9 else out[-1]
    return out


def taper_fn(Lt, d, tip):
    """Offset at distance x from the tip of a taper of length Lt to offset d: the cos taper (0° at the tip, its largest
    angle in the middle), its first metres replaced by a straight wedge of slope `tip` (ramps.tapers_scdot
    entrance_taper_desired) from the tip to where the wedge meets the cos curve. The cos curve alone leaves the
    carriageway with zero slope, so its first metres lie within a centimetre of the carriageway's line and, rounded to
    1 cm, touch or cross it before the node (w50 golden ic_kokterek); the wedge keeps the ramp on its own side up to the
    node."""
    a = abs(d)
    c = lambda x: a * G.smooth01(x / Lt) if x < Lt else a
    xs = 0.0
    if tip > 0.0 and Lt > 0.0:
        lo, hi = 1e-6, Lt
        if c(hi) > tip * hi:
            for _ in range(60):                 # first point where the cos curve rises above the wedge
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if c(mid) <= tip * mid else (lo, mid)
            xs = hi
        else:
            xs = Lt
    sg = 1.0 if d >= 0 else -1.0
    return lambda x: sg * (min(max(c(x), tip * x), a) if x < xs else c(x))


def diverge_lane(cw, s_d, Lt, Lp, d, tip=0.0):
    """From cw(s_d) (offset 0) to offset d over Lt (cos taper with a straight tip, taper_fn), then parallel for Lp.
    Returns (pts, end chainage)."""
    t = taper_fn(Lt, d, tip)
    f = lambda s: t(s - s_d) if s < s_d + Lt else d
    pts = lane_off(cw, s_d, s_d + Lt + Lp, f)
    pts[0] = cw.at(s_d)
    return pts, s_d + Lt + Lp


def merge_lane(cw, s_m, Lt, Lp, d, tip=0.0):
    """Parallel at offset d for Lp, then taper to 0 over Lt (cos with a straight tip, taper_fn), ending at cw(s_m).
    Returns (pts, start chainage)."""
    s0 = s_m - Lt - Lp
    t = taper_fn(Lt, d, tip)
    f = lambda s: d if s < s_m - Lt else t(s_m - s)
    pts = lane_off(cw, s0, s_m, f)
    pts[-1] = cw.at(s_m)
    return pts, s0


def straight(p, h, L, step=2.0):
    n = max(1, int(math.ceil(L / step)))
    return np.array([p + h * L * k / n for k in range(n + 1)])


def connect(pA, hA, pB, hB, R, words=None, accept=None):
    th0 = G.heading(hA)
    th1 = G.heading(hB)
    pts, info = G.dubins(pA, th0, pB, th1, R, words=words, step=1.0, accept=accept)
    if pts is None:
        raise TemplateError("нет пути съезда радиуса %.0f м" % R)
    return pts, info


def finish(pts, Lt, keep_a=0.0, keep_b=0.0):
    """Clothoid-like transitions and output resampling (≈ 3 m). The first keep_a m and the last keep_b m (speed-change
    lanes) stay exactly where they are: only the part between them is smoothed, starting Lt/2 + 5 m inside them so the
    transition begins on the lane's straight."""
    P = G.dedup(G.A(pts))
    L = G.length(P)
    m = Lt / 2.0 + 5.0
    a = max(0.0, keep_a - m) if keep_a > 0 else 0.0
    b = min(L, L - keep_b + m) if keep_b > 0 else L
    if b - a < 2 * Lt or (a <= 0.0 and b >= L):
        Q = G.smooth_transitions(P, Lt, step=1.0)
        return G.resample(Q, 3.0, keep_vertices=False)
    mid = G.smooth_transitions(G.cut(P, a, b), Lt, step=1.0)
    parts = []
    if a > 0.0:
        parts.append(G.resample(G.cut(P, 0.0, a), 3.0, keep_vertices=False))
    parts.append(G.resample(mid, 3.0, keep_vertices=False))
    if b < L:
        parts.append(G.resample(G.cut(P, b, L), 3.0, keep_vertices=False))
    return G.concat(*parts)


def max_dev_deg(pts, h):
    d = np.diff(pts, axis=0)
    th = np.arctan2(d[:, 1], d[:, 0])
    t0 = G.heading(h)
    return float(np.max(np.abs([math.degrees(G.wrap(a - t0)) for a in th])))


# ------------------------------------------------------------------ result
class Result:
    def __init__(self, ic_id, template, C, major, minor, params):
        self.id = ic_id
        self.template = template
        self.C = np.asarray(C, float)
        self.major, self.minor = major, minor
        self.params = params or {}
        self.ramps = []          # new Ways
        self.lifted = []         # (way, s0, s1, why)
        self.hints = []          # (point, kind)
        self.notes = []
        self.years = Y.latest(major.years, minor.years) if minor is not None else list(major.years)

    def ramp(self, pts, kind, parents=(), lane_w=None, grade=None, name=""):
        w = Way("ramp", pts, oneway=True, years=self.years, name_ru=name or "", ic=self.id, source="template",
                role="ramp", grade=grade)
        w.kind = kind
        w.parents = list(parents)
        w.parent = parents[0] if parents else None
        w.lane_w = lane_w
        w.keep_exact = True
        self.ramps.append(w)
        return w

    def hint(self, p, kind):
        self.hints.append((np.asarray(p, float), kind))

    def lift(self, way, s0, s1, why):
        self.lifted.append((way, s0, s1, why))

    def record(self):
        return {"id": self.id, "template": self.template, "x": round(float(self.C[0]), 1), "z": round(float(self.C[1]), 1),
                "major": self.major.street, "minor": self.minor.street if self.minor else None,
                "params": self.params, "notes": self.notes}


# ------------------------------------------------------------------ checks shared by all templates
def _ok_pair(a, b):
    def has(x, y):
        c = getattr(x, "cross_ok", None)
        return c is y or (isinstance(c, (list, tuple)) and any(e is y for e in c))
    return has(a, b) or has(b, a)


def self_check(res, rn, others=()):
    """Ramps must not cross each other (except where they share an end), nor any road they do not attach to
    (unless they are lifted there), and unconnected ramps keep a clear gap. Raises TemplateError."""
    rs = res.ramps
    lifts = {}
    for way, s0, s1, why in res.lifted:
        lifts.setdefault(id(way), []).append((s0, s1))

    def lifted(w, s):
        return any(a <= s <= b for a, b in lifts.get(id(w), []))
    for i, a in enumerate(rs):
        for b in rs[i + 1:]:
            shared = _shared_end(a, b)
            for sa, sb, pt, ang in G.crossings(a.P, b.P):
                if shared is not None and np.hypot(*(pt - shared)) < 1.0:
                    continue
                if lifted(a, sa) != lifted(b, sb):
                    continue
                if _ok_pair(a, b):
                    continue
                raise TemplateError(f"съезды {a.kind} и {b.kind} пересекаются в ({pt[0]:.0f}, {pt[1]:.0f})")
            if shared is None:
                need = (rn.w_right + rn.w_right) / 2.0 + rn.gap
                if G.crossings(a.P, b.P):
                    continue          # crossing on two levels (checked above)
                dmin = G.min_distance(a.P, b.P)
                touching = any(np.hypot(*(p - q)) < 1.0 for p in (a.P[0], a.P[-1]) for q in (b.P[0], b.P[-1]))
                if not touching and dmin < need and not _ok_pair(a, b):
                    raise TemplateError(f"съезды {a.kind} и {b.kind} ближе {dmin:.1f} м (нужно ≥ {need:.1f})")


def _shared_end(a, b):
    for p in (a.P[0], a.P[-1]):
        for q in (b.P[0], b.P[-1]):
            if np.hypot(*(p - q)) < 0.5:
                return p
    # an end of one on the other (branch)
    for p in (a.P[0], a.P[-1]):
        if G.project(b.P, p)[1] < 0.3:
            return p
    for p in (b.P[0], b.P[-1]):
        if G.project(a.P, p)[1] < 0.3:
            return p
    return None


def crosses_road(pts, road, skip_end=None, tol_end=1.0):
    for w in road.cws.values():
        for sa, sb, pt, ang in G.crossings(pts, w.P):
            if skip_end is not None and np.hypot(*(pt - skip_end)) < tol_end:
                continue
            return pt
    return None


# ------------------------------------------------------------------ diagonal ramps (diamond, parclo)
def _terminal(F, t, h, mode):
    """End / start point of a ramp at the minor road line through mpoint(t) with heading h.
    mode 'arrive_far' / 'arrive_near' / 'depart_far' / 'depart_near'."""
    back, front = F.minor_cw_points(t, h)
    if mode == "arrive_far":
        return front
    if mode == "arrive_near":
        return back
    if mode == "depart_far":
        return back
    return front


def exit_diag(res, rn, F, t, mode, X_range=(150, 1400), max_dev=35.0):
    """+u traffic leaves before C and arrives at the minor road (this frame's right side, distance t) heading ⊥."""
    d = F.major.prof["cw_w"] / 2.0 + rn.w_right / 2.0
    Lt, Lp = rn.taper(d), rn.decel
    vt = F.mtan(t)
    h = G.left(vt)
    if np.dot(h, F.u) < 0:
        h = -h
    E = _terminal(F, t, h, mode)
    back, front = F.minor_cw_points(t, h)
    Ls = rn.straight + float(np.hypot(*(E - back)))
    Ep = E - h * Ls
    dev_lim = max(max_dev, math.degrees(G.angle_between(h, F.u)) + 12.0)
    last = None
    for X in np.arange(X_range[0], X_range[1], 20.0):
        s_d = F.sC - X
        try:
            lane, s_end = diverge_lane(F.cw, s_d, Lt, Lp, d, rn.tip)
        except TemplateError as e:
            last = e
            break
        if s_end > F.sC - F.minor.half_width() - 10:
            continue
        q, hq = lane[-1], F.cw.tan(s_end)
        try:
            mid, info = connect(q, hq, Ep, h, rn.R, words=["RSL", "RSR", "LSL", "LSR"])
        except TemplateError as e:
            last = e
            continue
        if max_dev_deg(mid, F.u) > dev_lim:
            continue
        pts = G.concat(lane, mid, straight(Ep, h, Ls))
        keep = {"keep_a": G.length(lane)}
        if crosses_road(pts[5:], F.major) is not None:
            continue
        cm = crosses_road(pts, F.minor)
        if cm is not None and np.hypot(*(cm - E)) > Ls + 1.0:
            continue
        pts = finish(pts, min(40.0, 0.4 * rn.R), **keep)
        w = res.ramp(pts, "exit", parents=[F.cw])
        w.term = {"t": t, "end": "b", "minor": True}
        w.scl = [{"end": "a", "kind": "decel", "len_m": round(Lp, 1), "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
        res.hint(pts[0], "diverge")
        return w
    raise TemplateError(f"съезд-выезд не вписан ({last})")


def entry_diag(res, rn, F, t, mode, X_range=(150, 1400), max_dev=35.0, after=None):
    """Traffic from the minor road (right side, distance t) joins +u after C."""
    d = F.major.prof["cw_w"] / 2.0 + rn.w_right / 2.0
    Lt, Lp = rn.taper(d), rn.accel
    vt = F.mtan(t)
    h = G.left(vt)
    if np.dot(h, F.u) < 0:
        h = -h
    S0 = _terminal(F, t, h, mode)
    back, front = F.minor_cw_points(t, h)
    Ls = rn.straight + float(np.hypot(*(front - S0)))
    Sp = S0 + h * Ls
    dev_lim = max(max_dev, math.degrees(G.angle_between(h, F.u)) + 12.0)
    last = None
    for X in np.arange(X_range[0], X_range[1], 20.0):
        s_m = F.sC + X
        try:
            lane, s_start = merge_lane(F.cw, s_m, Lt, Lp, d, rn.tip)
        except TemplateError as e:
            last = e
            break
        if s_start < F.sC + F.minor.half_width() + 10:
            continue
        if after is not None and s_start < after:
            continue
        q, hq = lane[0], F.cw.tan(s_start)
        try:
            mid, info = connect(Sp, h, q, hq, rn.R, words=["LSR", "RSR", "LSL", "RSL"])
        except TemplateError as e:
            last = e
            continue
        if max_dev_deg(mid, F.u) > dev_lim:
            continue
        pts = G.concat(straight(S0, h, Ls), mid, lane)
        keep = {"keep_b": G.length(lane)}
        if crosses_road(pts[:-5], F.major) is not None:
            continue
        cm = crosses_road(pts, F.minor)
        if cm is not None and np.hypot(*(cm - S0)) > Ls + 1.0:
            continue
        pts = finish(pts, min(40.0, 0.4 * rn.R), **keep)
        w = res.ramp(pts, "entry", parents=[F.cw])
        w.term = {"t": t, "end": "a", "minor": True}
        w.scl = [{"end": "b", "kind": "accel", "len_m": round(Lp, 1), "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
        w.merge_s = s_m
        res.hint(pts[-1], "merge")
        return w
    raise TemplateError(f"съезд-въезд не вписан ({last})")


def entry_loop_A(res, rn, F, R, mode="depart_far"):
    """Parclo A loop: leaves the minor road (right side) heading −u, turns 180° to the right, accelerates along +u
    from just before the minor road, merges downstream. Returns the Way."""
    d = F.major.prof["cw_w"] / 2.0 + rn.w_left / 2.0
    Lt, Lp = rn.taper(d), rn.accel
    lat0 = F.major.e() + d
    sk = max(0.5, math.sin(math.radians(G.line_angle_deg(F.u, F.mtan(0.0)))))
    found = False
    for t in (lat0 + 2 * R) / sk + np.arange(0.0, 200.0, 5.0):
        vt = F.mtan(t)
        h = -G.left(vt) if np.dot(G.left(vt), F.u) > 0 else G.left(vt)        # ≈ −u
        S0 = _terminal(F, t, h, mode)
        back, front = F.minor_cw_points(t, h)
        Ls = rn.straight + float(np.hypot(*(front - S0)))
        Sp = S0 + h * Ls
        s_start = G.project(F.cw.P, Sp)[0]
        for extra in np.arange(0.0, 300.0, 10.0):
            s_m = s_start - extra + Lp + Lt
            try:
                lane, s_st = merge_lane(F.cw, s_m, Lt, Lp, d, rn.tip)
            except TemplateError as e:
                raise TemplateError(f"петля A: {e}")
            q, hq = lane[0], F.cw.tan(s_st)
            try:
                mid, info = connect(Sp, h, q, hq, R, words=["RSR"])
            except TemplateError:
                continue
            turn = abs(math.degrees(G.turn_total(mid)))
            if 140 <= turn <= 225:
                found = True
                break
        if found:
            break
    if not found:
        raise TemplateError("петля A не вписана")
    pts = G.concat(straight(S0, h, Ls), mid, lane)
    pts = finish(pts, min(30.0, 0.5 * R), keep_b=G.length(lane))
    w = res.ramp(pts, "loop_entry", parents=[F.cw], lane_w=rn.w_left)
    w.term = {"t": t, "end": "a", "minor": True}
    w.loop_R = R
    w.scl = [{"end": "b", "kind": "accel", "len_m": round(Lp, 1), "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
    w.merge_s = s_m
    res.hint(pts[-1], "merge")
    return w


def exit_loop_B(res, rn, F, R, mode="arrive_far"):
    """Parclo B loop: +u traffic leaves after C (decel lane from before the minor road), turns 180° to the right and
    arrives at the minor road (right side) heading −u."""
    d = F.major.prof["cw_w"] / 2.0 + rn.w_left / 2.0
    Lt, Lp = rn.taper(d), rn.decel
    lat0 = F.major.e() + d
    sk = max(0.5, math.sin(math.radians(G.line_angle_deg(F.u, F.mtan(0.0)))))
    found = False
    for t in (lat0 + 2 * R) / sk + np.arange(0.0, 200.0, 5.0):
        vt = F.mtan(t)
        h = -G.left(vt) if np.dot(G.left(vt), F.u) > 0 else G.left(vt)        # ≈ −u
        E = _terminal(F, t, h, mode)
        back, front = F.minor_cw_points(t, h)
        Ls = rn.straight + float(np.hypot(*(E - back)))
        Ep = E - h * Ls
        s_abeam = G.project(F.cw.P, Ep)[0]
        for extra in np.arange(0.0, 300.0, 10.0):
            s_end = s_abeam + extra
            s_d = s_end - Lp - Lt
            lane, _ = diverge_lane(F.cw, s_d, Lt, Lp, d, rn.tip)
            q, hq = lane[-1], F.cw.tan(s_end)
            try:
                mid, info = connect(q, hq, Ep, h, R, words=["RSR"])
            except TemplateError:
                continue
            turn = abs(math.degrees(G.turn_total(mid)))
            if 140 <= turn <= 225:
                found = True
                break
        if found:
            break
    if not found:
        raise TemplateError("петля B не вписана")
    pts = G.concat(lane, mid, straight(Ep, h, Ls))
    pts = finish(pts, min(30.0, 0.5 * R), keep_a=G.length(lane))
    w = res.ramp(pts, "loop_exit", parents=[F.cw], lane_w=rn.w_left)
    w.term = {"t": t, "end": "b", "minor": True}
    w.loop_R = R
    w.scl = [{"end": "a", "kind": "decel", "len_m": round(Lp, 1), "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
    res.hint(pts[0], "diverge")
    return w


def terminal_connector(res, F, t, h):
    """Divided minor road: the straight across its median that links an exit ramp ending at the near carriageway with
    the entry ramp starting at the far one (one signalised terminal)."""
    back, front = F.minor_cw_points(t, h)
    if np.hypot(*(front - back)) < 1.0:
        return None                     # both ramps end at the junction at the minor road's end
    w = res.ramp(straight(back, h, float(np.hypot(*(front - back)))), "terminal_link", parents=[])
    return w


def lift_minor(res, F, why):
    """The minor road passes over the major road around C (its ways lifted over the major's footprint). The major's half width
    is taken at most MAX_LIFT_HALF: an estimate from a pair of carriageways that are not a pair (the A-3 at km 48, its other
    carriageway on the district border) lifted the street 650 m long instead of ≈ 60 m (owner 03.11.2026)."""
    half = min(F.major.half_width(), MAX_LIFT_HALF) + 12.0
    for w in F.minor.cws.values():
        s, _, _ = G.project(w.P, F.C)
        ang = math.radians(max(20.0, 90.0 - G.line_angle_deg(F.u, w.tan(s)) if False else G.line_angle_deg(F.u, w.tan(s))))
        h = half / max(math.sin(ang), 0.3)
        res.lift(w, s - h, s + h, why)


MAX_LIFT_HALF = 40.0              # m: the widest road crossed (an 8-lane expressway with its median and verges)


def lift_major(res, F, why):
    half = min(F.minor.half_width(), MAX_LIFT_HALF) + 12.0
    for w in F.major.cws.values():
        s, _, _ = G.project(w.P, F.C)
        ang = math.radians(G.line_angle_deg(F.u, F.mtan(0.0)))
        h = half / max(math.sin(ang), 0.3)
        res.lift(w, s - h, s + h, why)


def _upper(params):
    return params.get("upper", "minor")


# ------------------------------------------------------------------ templates
def t_grade_separation(res, N, major, minor, params):
    F = Frame(res.C, major, minor, +1)
    if _upper(params) == "major":
        lift_major(res, F, "grade_separation")
    else:
        lift_minor(res, F, "grade_separation")
    res.notes.append("путепровод без съездов")


def _term_t(F, rn, extra=0.0):
    """Distance from C to the ramp terminals on the minor road: beyond the lifted span and the bridge approach."""
    base = F.major.half_width() + 12.0
    return base + max(60.0, rn.R * 0.5) + extra


def t_diamond(res, N, major, minor, params):
    rn = RampNorms(N, major.cls)
    if not major.divided:
        raise TemplateError("ромб: главная дорога должна быть разделённой (две проезжие части)")
    t0 = float(params.get("terminal_m", 0)) or _term_t(Frame(res.C, major, minor, +1), rn)
    omit = set(params.get("omit_quadrants") or [])
    for sign in (+1, -1):
        F = Frame(res.C, major, minor, sign)
        lo, hi = F.minor_span()
        if t0 > hi + 30.0 + 0.5:
            raise TemplateError(f"ромб: второстепенная дорога коротка для примыкания на {t0:.0f} м")
        h = G.left(F.mtan(t0))
        h = h if np.dot(h, F.u) > 0 else -h
        vr = F.mtan(t0)
        q_ex, q_en = _quadrant_name(res.C, -F.u, vr), _quadrant_name(res.C, F.u, vr)
        made = []
        for q, fn, mode in ((q_ex, exit_diag, "arrive"), (q_en, entry_diag, "depart")):
            if q in omit:
                res.notes.append(f"ромб: квадрант {q} без съезда шаблона (omit_quadrants)")
                continue
            w = fn(res, rn, F, t0, f"{mode}_near" if minor.divided else f"{mode}_far")
            w.quadrant = q
            res.hint(w.P[-1] if mode == "arrive" else w.P[0], "crossing_signal")
            made.append(w)
        if minor.divided and made:
            terminal_connector(res, F, t0, h)
    F = Frame(res.C, major, minor, +1)
    if _upper(params) == "major":
        lift_major(res, F, "diamond")
    else:
        lift_minor(res, F, "diamond")
    res.notes.append(f"ромб: примыкания съездов на второстепенной дороге в {t0:.0f} м от оси, радиус съездов {rn.R:.0f} м")
    self_check(res, rn)


def _quadrant_name(C, a, b):
    """Compass name of the quadrant between two directions a, b (unit vectors from C)."""
    m = a + b
    return ("n" if m[1] >= 0 else "s") + ("e" if m[0] >= 0 else "w")


def _diag_pair(res, rn, F, t, ex=True, en=True, ex_after=None, en_after=None):
    """Diamond-like terminal at distance t on the minor road for direction F: an exit diagonal (approach quadrant)
    and / or an entry diagonal (beyond quadrant). A divided minor road gets the ramps on their own near carriageways
    and one connector across its median (as t_diamond), so the two never overlap in the median."""
    div = F.minor.divided
    made = []
    h = G.left(F.mtan(t))
    h = h if np.dot(h, F.u) > 0 else -h
    if ex:
        w = exit_diag(res, rn, F, t, "arrive_near" if div else "arrive_far")
        res.hint(w.P[-1], "crossing_signal")
        made.append(w)
    if en:
        w = entry_diag(res, rn, F, t, "depart_near" if div else "depart_far", after=en_after)
        res.hint(w.P[0], "crossing_signal")
        made.append(w)
    if div and made:
        terminal_connector(res, F, t, h)
    return made


def t_parclo(res, N, major, minor, params):
    """Partial cloverleaf. params: variant "A" (entrance loops before the structure, default) or "B" (exit loops beyond
    it); quadrants (compass names, e.g. ["ne", "sw"]): which quadrants get ramps. A loop stands in the approach quadrant
    of its direction (A) or in the beyond quadrant (B); the other quadrant of that direction may get the outer ramp
    (A4 / B4). A direction without a loop gets diamond ramps. Default: one loop per direction, A2 / B2."""
    rn = RampNorms(N, major.cls)
    if not major.divided:
        raise TemplateError("неполный клевер: главная дорога должна быть разделённой")
    var = str(params.get("variant", "A")).upper()
    if var not in ("A", "B"):
        raise TemplateError(f"неполный клевер: вариант {var!r} неизвестен (A или B)")
    R = float(params.get("loop_r", rn.loop_R))
    quads = [q.lower() for q in params.get("quadrants", [])]
    built = []
    plan = []
    for sign in (+1, -1):
        F = Frame(res.C, major, minor, sign)
        rgt = F.mtan(10.0)
        qa = _quadrant_name(res.C, -F.u, rgt)        # approach quadrant of this direction (right side, before C)
        qb = _quadrant_name(res.C, F.u, rgt)         # beyond quadrant (right side, after C)
        plan.append((F, qa, qb))
    if not quads:
        quads = [p[1] if var == "A" else p[2] for p in plan]
    allq = {q for p in plan for q in p[1:]}
    unknown = [q for q in quads if q not in allq]
    if unknown:
        raise TemplateError(f"неполный клевер: квадранты {', '.join(unknown)} не из {', '.join(sorted(allq))}")
    loop_q = [p[1] if var == "A" else p[2] for p in plan]
    other_q = [p[2] if var == "A" else p[1] for p in plan]
    stray = [o for o, l in zip(other_q, loop_q) if o in quads and l not in quads]
    if stray:
        raise TemplateError(f"неполный клевер {var}: в квадранте {', '.join(stray)} петли варианта {var} нет; "
                            f"петли {var} стоят в {', '.join(loop_q)} (внешний съезд даётся вместе со своей петлёй)")
    if not any(q in quads for q in loop_q):
        raise TemplateError(f"неполный клевер {var}: ни одной петли (петли {var} стоят в {', '.join(loop_q)}); "
                            "без петель это ромб")
    t_term = _term_t(plan[0][0], rn)
    div = minor.divided

    def room(F, t, what, q):
        """A terminal is either ≥ 30 m before the end of the minor axis (minor_span) or the junction at that end
        (minor_cw_points from 29 m beyond the span): in between it would be a second junction a few metres off the
        end one, or merge with it."""
        hi = F.minor_span()[1]
        if hi + 1e-6 < t < hi + 29.0:
            raise TemplateError(f"второстепенная дорога со стороны {q}: {what} примыкает в {t:.0f} м от оси, а ось "
                                f"кончается в {hi + 30.0:.0f} м — узел в {hi + 30.0 - t:.0f} м от узла на её конце "
                                f"(нужно ≥ 30 м или примыкание в самом конце)")
    try:
        for F, qa, qb in plan:
            if var == "A":
                if qa in quads:
                    lp = entry_loop_A(res, rn, F, R)
                    tl = lp.term["t"]
                    room(F, tl, "петля", qa)
                    t2 = tl + rn.w_right + rn.gap + 40.0
                    room(F, t2, "съезд-выезд за петлёй", qa)
                    res.hint(lp.P[0], "crossing_signal")
                    built.append(qa)
                    if qb in quads:
                        # outer entry in qb: one terminal with the exit beyond the loop's start (from t_term the
                        # entry would have to pass over the loop's acceleration lane)
                        _diag_pair(res, rn, F, t2, en_after=lp.merge_s + 30.0)
                        built.append(qb)
                    else:
                        ex = exit_diag(res, rn, F, t2, "arrive_far")
                        res.hint(ex.P[-1], "crossing_signal")
                else:
                    room(F, t_term, "съезды как у ромба", qa)
                    _diag_pair(res, rn, F, t_term)
                    res.notes.append(f"направление без петли ({qa}): съезды как у ромба")
            else:
                if qb in quads:
                    lp = exit_loop_B(res, rn, F, R)
                    tl = lp.term["t"]
                    room(F, tl, "петля", qb)
                    t2 = tl + rn.w_right + rn.gap + 40.0
                    room(F, t2, "въезд за петлёй", qb)
                    res.hint(lp.P[-1], "crossing_signal")
                    built.append(qb)
                    if qa in quads:
                        # outer exit in qa: one terminal with the entry beyond the loop's end (at t_term the exit
                        # would cross to the far carriageway right next to the loop)
                        _diag_pair(res, rn, F, t2)
                        built.append(qa)
                    else:
                        en = entry_diag(res, rn, F, t2, "depart_far")
                        res.hint(en.P[0], "crossing_signal")
                else:
                    room(F, t_term, "съезды как у ромба", qb)
                    _diag_pair(res, rn, F, t_term)
                    res.notes.append(f"направление без петли ({qb}): съезды как у ромба")
        F = plan[0][0]
        if _upper(params) == "major":
            lift_major(res, F, "partial_cloverleaf")
        else:
            lift_minor(res, F, "partial_cloverleaf")
        res.params = dict(params, variant=var, quadrants=sorted(set(built)), loop_r=R)
        res.notes.append(f"ParClo {var}{len(set(built))}: съезды в {', '.join(sorted(set(built)))}, R петли {R:.0f} м"
                         + (", второстепенная разделённая: съезды на ближних проезжих частях, связка через "
                            "разделительную полосу" if div else ""))
        self_check(res, rn)
    except TemplateError as e:
        raise TemplateError(f"неполный клевер {var}{len(set(quads))} ({', '.join(sorted(set(quads)))}"
                            f"{', второстепенная разделённая' if div else ''}): {e}")


# ------------------------------------------------------------------ cloverleaf
def _cw_frames(C, major, minor):
    """The four carriageways at C: list of dicts {way, s, w (travel dir), road, other}."""
    out = []
    for road, other in ((major, minor), (minor, major)):
        for sign in (+1, -1):
            w, s, t = road_at(C, road, sign)
            out.append({"way": w, "s": s, "w": t, "road": road, "other": other, "sign": sign})
    return out


def _circle_tangent_two_lines(p1, w1, p2, w2, R):
    """Centre of the circle of radius R tangent to line 1 (point p1, dir w1) and line 2, lying to the RIGHT of both."""
    a1 = p1 + G.right(w1) * R
    a2 = p2 + G.right(w2) * R
    # intersect a1 + λ w1 and a2 + μ w2
    M = np.array([w1, -w2]).T
    lam, mu = np.linalg.solve(M, a2 - a1)
    return a1 + lam * w1


def t_cloverleaf(res, N, major, minor, params):
    cd = bool(params.get("cd", False))
    exts = np.arange(100.0, 1500.0, 50.0) if cd else [0.0]
    last = None
    for ext in exts:
        res.ramps, res.hints, res.lifted, res.notes = [], [], [], []
        try:
            _cloverleaf(res, N, major, minor, params, float(ext))
            return
        except TemplateError as e:
            last = e
    raise last


def _cloverleaf(res, N, major, minor, params, cd_ext):
    """Full cloverleaf: 4 loops (left turns, 270°), 4 outer connectors (right turns), an auxiliary lane on every
    carriageway between its entering and leaving loop (the weaving lane under the structure). params: loop_r,
    cd (true → collector-distributor roads: the auxiliary lanes become separate C-D roads that also carry the outer
    connectors), upper ("minor" | "major")."""
    rn = RampNorms(N, major.cls)
    if not (major.divided and minor.divided):
        raise TemplateError("клевер: обе дороги должны быть разделёнными")
    R = float(params.get("loop_r", rn.loop_R))
    cd = bool(params.get("cd", False))
    C = res.C
    cws = _cw_frames(C, major, minor)
    sep = 4.0 if cd else 0.0
    for k in cws:
        k["d"] = k["road"].prof["cw_w"] / 2.0 + sep + (rn.cd_w if cd else rn.w_right) / 2.0
    # pair loops: K_out → K_in with dir(K_in) ≈ left(dir(K_out))
    def best(target):
        return max(cws, key=lambda k: float(np.dot(k["w"], target)))
    loops = []
    for ko in cws:
        ki = best(G.left(ko["w"]))
        # lines of the aux lanes near C (straight approximation for the tangent circle)
        p1 = ko["way"].at(ko["s"]) + G.right(ko["w"]) * ko["d"]
        p2 = ki["way"].at(ki["s"]) + G.right(ki["w"]) * ki["d"]
        c = _circle_tangent_two_lines(p1, ko["w"], p2, ki["w"], R)
        sA = ko["s"] + float(np.dot(c - p1, ko["w"]))           # chainage on K_out where the loop leaves
        sB = ki["s"] + float(np.dot(c - p2, ki["w"]))           # chainage on K_in where it arrives
        loops.append({"out": ko, "in": ki, "c": c, "sA": sA, "sB": sB})
    # aux lane range on every carriageway: from before the arriving loop to after the leaving loop
    for k in cws:
        arr = [lp["sB"] for lp in loops if lp["in"] is k]
        lea = [lp["sA"] for lp in loops if lp["out"] is k]
        s_in, s_out = min(arr), max(lea)
        weave = s_out - s_in
        Lt = rn.taper(k["d"])
        ext_dec = max(20.0, rn.decel - weave) if True else 20.0
        ext_acc = max(20.0, rn.accel - weave)
        k["aux_s0"] = s_in - ext_dec - Lt - cd_ext   # diverge node of the aux lane / C-D road on the carriageway
        k["aux_s1"] = s_out + ext_acc + Lt + cd_ext  # merge node
        k["Lt"] = Lt
        d = k["d"]
        s0, s1 = k["aux_s0"], k["aux_s1"]
        tf = taper_fn(Lt, d, rn.tip)
        f = lambda s, s0=s0, s1=s1, Lt=Lt, d=d, tf=tf: tf(s - s0) if s < s0 + Lt else (tf(s1 - s) if s > s1 - Lt else d)
        pts = lane_off(k["way"], s0, s1, f)
        pts[0], pts[-1] = k["way"].at(s0), k["way"].at(s1)
        aux = res.ramp(pts, "cd_road" if cd else "aux_lane", parents=[k["way"]], lane_w=rn.cd_w if cd else rn.w_right)
        aux.scl = [{"end": "a", "kind": "decel", "len_m": round(min(arr) - s0 - Lt, 1), "taper_m": round(Lt, 1), "offset_m": round(d, 2)},
                   {"end": "b", "kind": "accel", "len_m": round(s1 - Lt - s_out, 1), "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
        aux.weave_m = round(weave, 1)
        k["aux"] = aux
        res.hint(pts[0], "diverge")
        res.hint(pts[-1], "merge")
    # loops: tangent branches off one aux lane onto the other
    for lp in loops:
        ao, ai = lp["out"]["aux"], lp["in"]["aux"]
        sa = G.project(ao.P, lp["out"]["way"].at(lp["sA"]) + G.right(lp["out"]["w"]) * lp["out"]["d"])[0]
        sb = G.project(ai.P, lp["in"]["way"].at(lp["sB"]) + G.right(lp["in"]["w"]) * lp["in"]["d"])[0]
        pA, hA = ao.at(sa), ao.tan(sa)
        pB, hB = ai.at(sb), ai.tan(sb)
        mid, info = connect(pA, hA, pB, hB, R, words=["RSR"])
        turn = abs(math.degrees(G.turn_total(mid)))
        if turn < 200:
            raise TemplateError(f"петля клевера повернула на {turn:.0f}° (нужно ≈ 270°)")
        w = res.ramp(mid, "loop", parents=[ao, ai], lane_w=rn.w_left)
        w.loop_R = R
        w.branch = True
        res.hint(pA, "diverge")
        res.hint(pB, "merge")
    # outer connectors: right turns K_from (before C) → K_to (after C), around the loop of that quadrant
    for kf in cws:
        kt = best(G.right(kf["w"]))
        quad_loop = next(lp for lp in loops if lp["out"] is kt and lp["in"] is kf) if False else None
        built = None
        last = None
        for X in (np.arange(150.0, 1500.0, 20.0) if not cd else [0.0]):
            try:
                if cd:
                    w = _outer_cd(res, rn, kf, kt, X)
                else:
                    w = _outer_direct(res, rn, kf, kt, X)
            except TemplateError as e:
                last = e
                res.ramps = [r for r in res.ramps if getattr(r, "kind", "") != "_try"]
                continue
            # clear of every other ramp
            ok = True
            for o in res.ramps:
                if o is w:
                    continue
                if G.crossings(w.P, o.P) and _shared_end(w, o) is None:
                    ok = False
                    break
                need = rn.w_right + rn.gap
                if _shared_end(w, o) is None and G.min_distance(w.P, o.P) < need:
                    ok = False
                    break
            if ok and crosses_road(w.P[8:-8], kf["road"]) is None and crosses_road(w.P[8:-8], kt["road"]) is None:
                built = w
                break
            res.ramps.remove(w)
        if built is None:
            raise TemplateError(f"внешний съезд клевера не вписан ({last})")
        built.kind = "outer"
    upper = _upper(params)
    F = Frame(C, major, minor, +1)
    up_road, low_road = (minor, major) if upper == "minor" else (major, minor)
    half = low_road.half_width() + max(k["d"] for k in cws) + rn.w_right + 10.0
    for k in cws:
        if k["road"] is up_road:
            for w in (k["way"], k["aux"]):
                s, _, _ = G.project(w.P, C)
                res.lift(w, s - half * 1.3, s + half * 1.3, "cloverleaf")
            k["aux"].grade = N.slope_max(up_road.cls)
    res.params = dict(params, loop_r=R, cd=cd, upper=upper)
    res.notes.append(f"клевер{' с C-D дорогами' if cd else ''}: R петель {R:.0f} м, участки переплетения "
                     + ", ".join(f"{k['aux'].weave_m:.0f}" for k in cws) + " м")
    self_check(res, rn)


def _outer_direct(res, rn, kf, kt, X):
    """Outer connector attached to the carriageways: diverge X m before the aux lane of K_from, merge X m after the
    aux lane of K_to."""
    d = kf["road"].prof["cw_w"] / 2.0 + rn.w_right / 2.0
    Lt = rn.taper(d)
    s_d = kf["aux_s0"] - 30.0 - X
    lane1, s1 = diverge_lane(kf["way"], s_d, Lt, rn.decel, d, rn.tip)
    d2 = kt["road"].prof["cw_w"] / 2.0 + rn.w_right / 2.0
    Lt2 = rn.taper(d2)
    s_m = kt["aux_s1"] + 30.0 + X
    lane2, s2 = merge_lane(kt["way"], s_m, Lt2, rn.accel, d2, rn.tip)
    mid, info = connect(lane1[-1], kf["way"].tan(s1), lane2[0], kt["way"].tan(s2), rn.R, words=["RSR", "RSL", "LSR"])
    if abs(math.degrees(G.turn_total(mid))) > 135:
        raise TemplateError("внешний съезд петляет")
    pts = finish(G.concat(lane1, mid, lane2), min(40.0, 0.4 * rn.R), keep_a=G.length(lane1), keep_b=G.length(lane2))
    w = res.ramp(pts, "_try", parents=[kf["way"], kt["way"]])
    w.scl = [{"end": "a", "kind": "decel", "len_m": rn.decel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)},
             {"end": "b", "kind": "accel", "len_m": rn.accel, "taper_m": round(Lt2, 1), "offset_m": round(d2, 2)}]
    res.hints.append((pts[0], "diverge"))
    res.hints.append((pts[-1], "merge"))
    return w


def _outer_cd(res, rn, kf, kt, X):
    """Outer connector branching off the C-D road of K_from and onto the C-D road of K_to (tangent branches)."""
    af, at = kf["aux"], kt["aux"]
    s_a = kf["Lt"] + 30.0
    s_b = at.L - kt["Lt"] - 30.0
    pA, hA = af.at(s_a), af.tan(s_a)
    pB, hB = at.at(s_b), at.tan(s_b)
    mid, info = connect(pA, hA, pB, hB, rn.R, words=["RSR", "RSL", "LSR"])
    if abs(math.degrees(G.turn_total(mid))) > 135:
        raise TemplateError("внешний съезд петляет")
    w = res.ramp(G.resample(mid, 3.0, keep_vertices=False), "_try", parents=[af, at])
    w.branch = True
    res.hints.append((pA, "diverge"))
    res.hints.append((pB, "merge"))
    return w


# ------------------------------------------------------------------ trumpet
def t_trumpet(res, N, major, minor, params):
    """Trumpet for a 3-leg node: the stem (minor road) ends at the major road. The stem crosses the major road on a
    bridge as two oneway roadways; on the far ("bell") side the loop (one left turn, 270°) sits inside the semi-direct
    ramp (the other left turn); the right turns are direct ramps on the stem side that join / leave the stem roadways
    tangentially. An undivided stem is split into the two roadways (they converge onto its axis at the split point);
    a divided stem keeps its carriageways as the roadways. params: loop_r."""
    rn = RampNorms(N, major.cls)
    if not major.divided:
        raise TemplateError("труба: главная дорога должна быть разделённой")
    C = res.C
    R = float(params.get("loop_r", rn.loop_R))
    sA0, _, _ = G.project(minor.axis, C)
    Sm = G.chainage(minor.axis)
    far_end = minor.axis[-1] if (Sm[-1] - sA0) > sA0 else minor.axis[0]
    w0, s0, t0 = road_at(C, major, +1)
    vv = far_end - C
    sign = +1 if np.dot(vv, G.right(t0)) > 0 else -1
    F = Frame(C, major, minor, sign)            # stem on F's right side
    B = Frame(C, major, minor, -sign)           # the other direction: its right side is the bell side
    u = F.u
    v = F.mtan(30.0)                           # stem direction (from C towards the stem)
    eM = major.e()
    d = major.prof["cw_w"] / 2.0 + rn.w_right / 2.0
    Lt = rn.taper(d)
    divided_stem = minor.divided
    es = minor.e() if divided_stem else rn.w_right / 2.0 + 2.0
    Lt_s = 0.0 if divided_stem else rn.taper(es)
    V_r = eM + d + rn.R + 25.0                 # where the right-turn ramps meet the stem roadways
    T_split = V_r + 40.0 + Lt_s + 20.0
    lo, hi = F.minor_span()
    if T_split > hi:
        raise TemplateError(f"труба: стебель короче {T_split:.0f} м")
    P = lambda a, b: C + u * a + v * b
    p_split = F.mpoint(T_split)
    if divided_stem:
        # the stem carriageways at the split: outbound travels +v (on the −u side), inbound −v (+u side)
        cw_out = minor.cws[+1] if np.dot(minor.cws[+1].tan(G.project(minor.cws[+1].P, p_split)[0]), v) > 0 else minor.cws[-1]
        cw_in = minor.cws[-1] if cw_out is minor.cws[+1] else minor.cws[+1]
        p_out_split = G.project(cw_out.P, p_split)[2]
        p_in_split = G.project(cw_in.P, p_split)[2]
    else:
        p_out_split = p_in_split = p_split
    # 1. loop: B (travelling −u) leaves after C on the bell side, turns 270° right onto the outbound roadway
    pB = B.cw.at(B.sC) + G.right(B.u) * d
    pO = P(-es, 0.0)
    c = _circle_tangent_two_lines(pB, B.u, pO, v, R)
    A1 = pB + B.u * float(np.dot(c - pB, B.u))
    A2 = pO + v * float(np.dot(c - pO, v))
    sA = B.sC + float(np.dot(A1 - pB, B.u))
    laneB, s_endB = diverge_lane(B.cw, sA - rn.decel - Lt, Lt, rn.decel, d, rn.tip)
    arc, info = connect(laneB[-1], B.cw.tan(s_endB), A2, v, R, words=["RSR"])
    turn = abs(math.degrees(G.turn_total(arc)))
    if turn < 200:
        raise TemplateError(f"петля трубы повернула на {turn:.0f}°")
    v_conv0 = T_split - Lt_s
    loop_pts = finish(G.concat(laneB, arc, straight(A2, v, 30.0)), min(30.0, 0.5 * R), keep_a=G.length(laneB))
    # keep the loop up to A2 exactly (the outbound roadway starts there)
    k = int(np.argmin(np.hypot(*(loop_pts - A2).T)))
    loop_pts = np.vstack([loop_pts[:k], A2])
    loop = res.ramp(loop_pts, "loop", parents=[B.cw], lane_w=rn.w_left)
    loop.loop_R = R
    loop.scl = [{"end": "a", "kind": "decel", "len_m": rn.decel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
    res.hint(loop_pts[0], "diverge")
    out_line = straight(A2, v, float(np.dot(P(-es, v_conv0) - A2, v)))
    if divided_stem:
        out_tail = np.vstack([P(-es, v_conv0), p_out_split])
    else:
        out_tail = np.array([P(-es * (1 - G.smooth01(k / 30.0)), v_conv0 + Lt_s * k / 30.0) for k in range(31)])
        out_tail[-1] = p_split
    stem_out = res.ramp(G.concat(out_line, out_tail), "stem_out", parents=[cw_out] if divided_stem else [],
                        lane_w=rn.w_right)
    res.hint(A2, "ic")
    # 2. semi-direct: inbound roadway from the split across the bridge, left around the loop into B (accel, merge)
    if divided_stem:
        in_head = np.vstack([p_in_split, P(es, v_conv0)])
    else:
        in_head = np.array([P(es * G.smooth01(k / 30.0), T_split - Lt_s * k / 30.0) for k in range(31)])
        in_head[0] = p_split
    loop_far = eM + d + 2 * R                 # loop extent on the bell side (from the major axis)
    loop_w = es + 2 * R                       # loop extent along −u
    semi = None
    last = None
    for Vs in np.arange(loop_far + rn.gap + rn.w_right, loop_far + 3 * rn.R, 20.0):
        for X in np.arange(loop_w + 60.0, loop_w + 1400.0, 20.0):
            s_m = B.sC + X + rn.accel + Lt
            try:
                laneM, s_st = merge_lane(B.cw, s_m, Lt, rn.accel, d, rn.tip)
            except TemplateError as e:
                last = e
                break
            pV = P(es, -Vs)
            try:
                cur, info = connect(pV, -v, laneM[0], B.cw.tan(s_st), rn.R, words=["LSR", "LSL"])
            except TemplateError as e:
                last = e
                continue
            if abs(math.degrees(G.turn_total(cur))) > 120:
                last = "поворот > 120°"
                continue
            if G.crossings(cur, loop.P):
                last = "пересекает петлю"
                continue
            if G.min_distance(cur, loop.P) < rn.w_right + rn.gap:
                last = "близко к петле"
                continue
            if crosses_road(cur[3:-3], major) is not None:
                last = "пересекает главную дорогу"
                continue
            semi = finish(G.concat(straight(pV + v * 30.0, -v, 30.0), cur, laneM), min(40.0, 0.4 * rn.R),
                          keep_b=G.length(laneM))
            k = int(np.argmin(np.hypot(*(semi - pV).T)))
            semi = np.vstack([pV, semi[k + 1:]])
            break
        if semi is not None:
            break
    if semi is None:
        raise TemplateError(f"полупрямой съезд трубы не вписан ({last})")
    stem_in = res.ramp(G.concat(in_head, straight(P(es, v_conv0), -v, v_conv0 + Vs)), "stem_in",
                       parents=[cw_in] if divided_stem else [], lane_w=rn.w_right)
    sd = res.ramp(semi, "semi_direct", parents=[B.cw], lane_w=rn.w_left)
    sd.scl = [{"end": "b", "kind": "accel", "len_m": rn.accel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
    res.hint(semi[-1], "merge")
    res.hint(pV, "ic")
    # 3. right turns on the stem side: +u → outbound (tangent merge), inbound → +u (tangent diverge)
    sm = G.project(stem_out.P, P(-es, V_r))[0]
    pM, hM = stem_out.at(sm), stem_out.tan(sm)
    sb = G.project(stem_in.P, P(es, V_r))[0]
    pD, hD = stem_in.at(sb), stem_in.tan(sb)
    for kind in ("exit_right", "entry_right"):
        ok = None
        for X in np.arange(es + rn.R + 40.0, es + rn.R + 1400.0, 20.0):
            try:
                if kind == "exit_right":
                    lane, s_e = diverge_lane(F.cw, F.sC - X - rn.decel - Lt, Lt, rn.decel, d, rn.tip)
                    cur, info = connect(lane[-1], F.cw.tan(s_e), pM, hM, rn.R, words=["RSR", "RSL", "LSR"])
                    pts = G.concat(lane, cur)
                else:
                    lane, s_s = merge_lane(F.cw, F.sC + X + rn.accel + Lt, Lt, rn.accel, d, rn.tip)
                    cur, info = connect(pD, hD, lane[0], F.cw.tan(s_s), rn.R, words=["RSR", "LSR", "RSL"])
                    pts = G.concat(cur, lane)
            except TemplateError:
                continue
            if abs(math.degrees(G.turn_total(cur))) > 135:
                continue
            if any(G.crossings(pts[5:-5], o.P) for o in res.ramps):
                continue
            if crosses_road(cur[5:-5], major) is not None:
                continue
            ok = G.resample(pts, 3.0, keep_vertices=False)
            ok[0], ok[-1] = pts[0], pts[-1]
            break
        if ok is None:
            raise TemplateError(f"правый съезд трубы ({kind}) не вписан")
        if kind == "exit_right":
            w = res.ramp(ok, kind, parents=[F.cw, stem_out])
            w.scl = [{"end": "a", "kind": "decel", "len_m": rn.decel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
            res.hint(ok[0], "diverge")
            res.hint(ok[-1], "merge")
        else:
            w = res.ramp(ok, kind, parents=[stem_in, F.cw])
            w.scl = [{"end": "b", "kind": "accel", "len_m": rn.accel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
            res.hint(ok[0], "diverge")
            res.hint(ok[-1], "merge")
        w.branch = True
    # the stem is cut back to the split point (its carriageways too when divided)
    res.cut_minor = {"ways": list(minor.cws.values()), "point": p_split, "C": C}
    res.hint(p_split, "merge" if not divided_stem else "ic")
    # the roadways pass over the major road
    half = major.half_width() + d + rn.w_right + 12.0
    for w in (stem_out, stem_in):
        s, _, _ = G.project(w.P, C)
        res.lift(w, s - half, s + half, "trumpet")
        w.grade = rn.slope
    res.params = dict(params, loop_r=R)
    res.notes.append(f"труба: петля R {R:.0f} м внутри полупрямого съезда, стебель {'(две проезжие части) ' if divided_stem else ''}"
                     f"разделён на два направления в {T_split:.0f} м от оси главной дороги")
    self_check(res, rn)



def t_directional(res, N, major, minor, params):
    """Semi-directional T for a 3-leg node (the stem = minor road ends at the major road), no loops. Both left turns
    are direct flyovers over the major road: a right-hand exit from the far carriageway climbs, turns left over the
    major road and lands on the outbound stem roadway; the inbound stem roadway turns left over the major road and joins
    the far carriageway with an acceleration lane. The two flyovers cross each other once: the exit one passes over the
    other (a third level). Right turns are direct ramps on the stem side, joining / leaving the stem roadways
    tangentially (as in the trumpet). params: none required."""
    rn = RampNorms(N, major.cls)
    if not major.divided:
        raise TemplateError("направленная развязка: главная дорога должна быть разделённой")
    C = res.C
    H = float(N.norm("bridges.road_clearance_m")) + model("deck_depth_m")
    g = rn.slope
    sA0, _, _ = G.project(minor.axis, C)
    Sm = G.chainage(minor.axis)
    far_end = minor.axis[-1] if (Sm[-1] - sA0) > sA0 else minor.axis[0]
    w0, s0, t0 = road_at(C, major, +1)
    sign = +1 if np.dot(far_end - C, G.right(t0)) > 0 else -1
    F = Frame(C, major, minor, sign)            # stem on F's right side
    B = Frame(C, major, minor, -sign)           # far carriageway (travels −u)
    u = F.u
    v = F.mtan(30.0)
    eM = major.e()
    d = major.prof["cw_w"] / 2.0 + rn.w_right / 2.0
    Lt = rn.taper(d)
    divided_stem = minor.divided
    es = minor.e() if divided_stem else rn.w_right / 2.0 + 2.0
    Lt_s = 0.0 if divided_stem else rn.taper(es)
    P = lambda a, b: C + u * a + v * b
    half_major = major.half_width() + 6.0

    def chain_cross(pts):
        """Chainages along pts where it crosses the major carriageways."""
        S = G.chainage(pts)
        out = []
        for w in major.cws.values():
            for sa, sb, pt, ang in G.crossings(pts, w.P):
                if 1.0 < sa < S[-1] - 1.0:
                    out.append(sa)
        return sorted(out), S
    # Both flyovers are built exactly: a straight alongside the far carriageway (climb / descent), a 90° left arc of
    # the ramp radius over the major road, a straight along the stem. Their arcs mirror each other and cross once on
    # the stem side; the exit flyover is the upper one there.
    R = rn.R
    Lc_in = H / g + half_major
    Lc_out = 2.0 * H / g + half_major
    # left_in: P(es, V_in) → P(es, R − eM − d) straight (−v), left arc to P(es − R, −(eM + d)), straight Lc_in (−u), accel
    v_arc = R - eM - d
    if v_arc < 5.0:
        raise TemplateError("направленная: радиус съезда меньше полуширины главной дороги")
    def arc90(p, h):
        """90° left arc of radius R from pose (p, h)."""
        c = p + G.left(h) * R
        a0 = math.atan2(p[1] - c[1], p[0] - c[0])
        pts = G.arc_pts(c, R, a0, 0.5 * math.pi, step=1.0)
        pts[0] = p
        return pts
    V_in = v_arc + 40.0
    q = P(es, v_arc)
    a_in = arc90(q, -v)
    h_in = G.left(-v)
    # the accel lane starts where the descent straight ends (project onto the far carriageway)
    s_st = G.project(B.cw.P, a_in[-1] + h_in * Lc_in)[0]
    s_m = s_st + rn.accel + Lt
    laneM, s0m = merge_lane(B.cw, s_m, Lt, rn.accel, d, rn.tip)
    li_pts = G.concat(straight(P(es, V_in), -v, V_in - v_arc), a_in, straight(a_in[-1], h_in, Lc_in), laneM)
    # left_out: diverge, straight Lc_out (−u) ending at P(R − es, −(eM + d)), left arc to P(−es, v_arc), straight to V_out
    p_o = P(R - es, -(eM + d))
    s_e = G.project(B.cw.P, p_o - B.u * Lc_out)[0]
    lane, s_end = diverge_lane(B.cw, s_e - rn.decel - Lt, Lt, rn.decel, d, rn.tip)
    pre = straight(lane[-1], B.u, float(np.dot(p_o - lane[-1], B.u)))
    a_out = arc90(pre[-1], B.u)
    lo_tmp = G.concat(lane, pre, a_out)
    xr = G.crossings(lo_tmp, li_pts)
    if len(xr) != 1:
        raise TemplateError(f"направленная: эстакады пересекаются {len(xr)} раз")
    sa, sb = xr[0][0], xr[0][1]
    cl, _ = chain_cross(li_pts)
    yl = max(0.0, H - g * max(0.0, max(cl[0] - sb, sb - cl[-1], 0.0) - half_major))
    need = yl + H
    s_lane = G.length(lane)
    if sa - s_lane < need / g + half_major:
        raise TemplateError("направленная: мало места на подъём верхней эстакады")
    V_out = v_arc + max(40.0, need / g + half_major - (G.length(lo_tmp) - sa))
    lo_pts = G.concat(lo_tmp, straight(a_out[-1], v, V_out - v_arc))
    left_out = finish(lo_pts, min(40.0, 0.4 * rn.R), keep_a=G.length(lane))
    left_out[0], left_out[-1] = lo_pts[0], lo_pts[-1]
    left_in = finish(li_pts, min(40.0, 0.4 * rn.R), keep_b=G.length(laneM))
    left_in[0], left_in[-1] = li_pts[0], li_pts[-1]
    li = res.ramp(left_in, "flyover_entry", parents=[B.cw], lane_w=rn.w_left, grade=g)
    li.scl = [{"end": "b", "kind": "accel", "len_m": rn.accel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
    cs_li, _ = chain_cross(li.P)
    res.lift(li, cs_li[0] - half_major, cs_li[-1] + half_major, "directional")
    res.hint(li.P[-1], "merge")
    lo = res.ramp(left_out, "flyover_exit", parents=[B.cw], lane_w=rn.w_left, grade=g)
    lo.scl = [{"end": "a", "kind": "decel", "len_m": rn.decel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
    lo.over_ways = {id(li)}
    lo.cross_ok = li
    cs_lo, _ = chain_cross(lo.P)
    xr = G.crossings(lo.P, li.P)
    if len(xr) != 1:
        raise TemplateError("направленная: эстакады после сглаживания пересекаются не один раз")
    s_rr = xr[0][0]
    res.lift(lo, min(cs_lo[0], s_rr) - half_major, max(cs_lo[-1], s_rr) + half_major, "directional")
    res.hint(lo.P[0], "diverge")
    V_out = float(np.dot(lo.P[-1] - C, v))
    # 3. stem roadways and right turns
    V_r = max(eM + d + rn.R + 25.0, V_out + 150.0, V_in + 150.0)
    T_split = V_r + 60.0 + Lt_s + 20.0
    lo_, hi_ = F.minor_span()
    if T_split > hi_:
        raise TemplateError(f"направленная: стебель короче {T_split:.0f} м")
    p_split = F.mpoint(T_split)
    v_conv0 = T_split - Lt_s
    if divided_stem:
        cw_out = minor.cws[+1] if np.dot(minor.cws[+1].tan(G.project(minor.cws[+1].P, p_split)[0]), v) > 0 else minor.cws[-1]
        cw_in = minor.cws[-1] if cw_out is minor.cws[+1] else minor.cws[+1]
        p_out_split = G.project(cw_out.P, p_split)[2]
        p_in_split = G.project(cw_in.P, p_split)[2]
        out_tail = np.vstack([P(-es, v_conv0), p_out_split])
        in_head = np.vstack([p_in_split, P(es, v_conv0)])
    else:
        cw_out = cw_in = None
        out_tail = np.array([P(-es * (1 - G.smooth01(k / 30.0)), v_conv0 + Lt_s * k / 30.0) for k in range(31)])
        out_tail[-1] = p_split
        in_head = np.array([P(es * G.smooth01(k / 30.0), T_split - Lt_s * k / 30.0) for k in range(31)])
        in_head[0] = p_split
    stem_out = res.ramp(G.concat(straight(P(-es, V_out), v, v_conv0 - V_out), out_tail), "stem_out",
                        parents=[cw_out] if cw_out else [], lane_w=rn.w_right)
    stem_in = res.ramp(G.concat(in_head, straight(P(es, v_conv0), -v, v_conv0 - V_in)), "stem_in",
                       parents=[cw_in] if cw_in else [], lane_w=rn.w_right)
    lo.cross_ok = [li, stem_in]                 # passes over the end of the inbound roadway next to left_in
    stem_out.P[0] = lo.P[-1]
    stem_in.P[-1] = li.P[0]
    stem_out.refresh()
    stem_in.refresh()
    res.hint(lo.P[-1], "ic")
    res.hint(li.P[0], "ic")
    sm = G.project(stem_out.P, P(-es, V_r))[0]
    pM, hM = stem_out.at(sm), stem_out.tan(sm)
    sb = G.project(stem_in.P, P(es, V_r))[0]
    pD, hD = stem_in.at(sb), stem_in.tan(sb)
    for kind in ("exit_right", "entry_right"):
        ok = None
        for X in np.arange(es + rn.R + 40.0, es + rn.R + 1400.0, 20.0):
            try:
                if kind == "exit_right":
                    lane, s_e = diverge_lane(F.cw, F.sC - X - rn.decel - Lt, Lt, rn.decel, d, rn.tip)
                    cur, info = connect(lane[-1], F.cw.tan(s_e), pM, hM, rn.R, words=["RSR", "RSL", "LSR"])
                    pts = G.concat(lane, cur)
                else:
                    lane, s_s = merge_lane(F.cw, F.sC + X + rn.accel + Lt, Lt, rn.accel, d, rn.tip)
                    cur, info = connect(pD, hD, lane[0], F.cw.tan(s_s), rn.R, words=["RSR", "LSR", "RSL"])
                    pts = G.concat(cur, lane)
            except TemplateError:
                continue
            if abs(math.degrees(G.turn_total(cur))) > 135:
                continue
            if any(G.crossings(pts[5:-5], o.P) for o in res.ramps):
                continue
            if crosses_road(cur[5:-5], major) is not None:
                continue
            if min(G.min_distance(cur[5:-5], o.P) for o in (lo, li)) < rn.w_right + rn.gap:
                continue
            ok = G.resample(pts, 3.0, keep_vertices=False)
            ok[0], ok[-1] = pts[0], pts[-1]
            break
        if ok is None:
            raise TemplateError(f"направленная: правый съезд ({kind}) не вписан")
        if kind == "exit_right":
            w = res.ramp(ok, kind, parents=[F.cw, stem_out])
            w.scl = [{"end": "a", "kind": "decel", "len_m": rn.decel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
        else:
            w = res.ramp(ok, kind, parents=[stem_in, F.cw])
            w.scl = [{"end": "b", "kind": "accel", "len_m": rn.accel, "taper_m": round(Lt, 1), "offset_m": round(d, 2)}]
        res.hint(ok[0], "diverge")
        res.hint(ok[-1], "merge")
        w.branch = True
    res.cut_minor = {"ways": list(minor.cws.values()), "point": p_split, "C": C}
    res.hint(p_split, "merge" if not divided_stem else "ic")
    res.notes.append(f"направленная (полунаправленное Т): два левых поворота эстакадами над главной дорогой, "
                     f"в месте их пересечения третий уровень; стебель разделён в {T_split:.0f} м от оси")
    self_check(res, rn)


def _shared_end_pts(pts, o):
    for p in (pts[0], pts[-1]):
        for q in (o.P[0], o.P[-1]):
            if np.hypot(*(p - q)) < 0.5:
                return p
        if G.project(o.P, p)[1] < 0.3:
            return p
    return None


# ------------------------------------------------------------------ dispatcher
def build(kind, ic_id, C, major, minor, params, N):
    res = Result(ic_id, kind, C, major, minor, params or {})
    fn = {"diamond": t_diamond, "partial_cloverleaf": t_parclo, "cloverleaf": t_cloverleaf,
          "trumpet": t_trumpet, "grade_separation": t_grade_separation,
          "directional": t_directional}.get(kind)
    if fn is None:
        raise TemplateError(f"шаблон {kind} не реализован")
    fn(res, N, major, minor, params or {})
    return res
