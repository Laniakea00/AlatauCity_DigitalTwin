"""Geometry helpers for roads (plan X = east, Z = north; angles CCW from +X, so a left turn is positive).

Polylines are numpy arrays N × 2 (x, z). Offsets are positive to the RIGHT of the direction of travel
(right-hand traffic: the carriageway of a heading lies to its right).
"""
import math

import numpy as np

TAU = 2.0 * math.pi


# ------------------------------------------------------------------ basics
def A(P):
    P = np.asarray(P, float)
    return P[:, :2] if P.ndim == 2 else P.reshape(-1, 2)


def unit(a):
    return np.array([math.cos(a), math.sin(a)])


def heading(v):
    return math.atan2(v[1], v[0])


def right(v):
    return np.array([v[1], -v[0]])


def left(v):
    return np.array([-v[1], v[0]])


def wrap(a):
    """Angle to (−π, π]."""
    return (a + math.pi) % TAU - math.pi


def mod2pi(a):
    return a % TAU


def angle_between(u, v):
    """Unsigned angle (rad, 0…π) between two direction vectors."""
    c = float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12))
    return math.acos(max(-1.0, min(1.0, c)))


def line_angle_deg(u, v):
    """Angle between two LINES (undirected), degrees 0…90."""
    a = math.degrees(angle_between(u, v))
    return min(a, 180.0 - a)


def dedup(P, eps=1e-6):
    P = A(P)
    if len(P) < 2:
        return P
    keep = np.ones(len(P), bool)
    keep[1:] = np.hypot(*np.diff(P, axis=0).T) > eps
    return P[keep]


def seglen(P):
    P = A(P)
    return np.hypot(*np.diff(P, axis=0).T)


def chainage(P):
    return np.concatenate([[0.0], np.cumsum(seglen(P))])


def length(P):
    return float(seglen(P).sum())


def _locate(S, s):
    i = int(np.searchsorted(S, s, side="right") - 1)
    return max(0, min(i, len(S) - 2))


def point_at(P, s, S=None):
    P = A(P)
    S = chainage(P) if S is None else S
    s = min(max(s, 0.0), S[-1])
    i = _locate(S, s)
    L = S[i + 1] - S[i]
    t = 0.0 if L <= 0 else (s - S[i]) / L
    return P[i] + t * (P[i + 1] - P[i])


def tangent_at(P, s, S=None):
    """Unit tangent at chainage s (the direction of the segment that holds s)."""
    P = A(P)
    S = chainage(P) if S is None else S
    s = min(max(s, 0.0), S[-1])
    i = _locate(S, s)
    # at an exact vertex take the mean of both sides
    if i > 0 and abs(s - S[i]) < 1e-9:
        v = (P[i + 1] - P[i]) / max(S[i + 1] - S[i], 1e-12) + (P[i] - P[i - 1]) / max(S[i] - S[i - 1], 1e-12)
    else:
        v = P[i + 1] - P[i]
    n = np.linalg.norm(v)
    return v / n if n > 0 else np.array([1.0, 0.0])


def project(P, pt):
    """(chainage, distance, foot point) of the nearest point of polyline P to pt."""
    P = A(P)
    pt = np.asarray(pt, float)
    a, b = P[:-1], P[1:]
    ab = b - a
    L2 = (ab ** 2).sum(1)
    t = np.clip(((pt - a) * ab).sum(1) / np.where(L2 > 0, L2, 1), 0, 1)
    F = a + ab * t[:, None]
    d = np.hypot(*(F - pt).T)
    i = int(np.argmin(d))
    S = chainage(P)
    return float(S[i] + t[i] * math.sqrt(L2[i])), float(d[i]), F[i]


def resample(P, step, keep_vertices=True):
    """Points every `step` m (ends kept; original vertices kept when keep_vertices)."""
    P = dedup(P)
    S = chainage(P)
    L = S[-1]
    if L <= 0:
        return P.copy()
    n = max(1, int(math.ceil(L / step)))
    s = np.linspace(0, L, n + 1)
    if keep_vertices:
        s = np.unique(np.concatenate([s, S]))
        # drop near-duplicates
        keep = np.concatenate([[True], np.diff(s) > 1e-6])
        s = s[keep]
    x = np.interp(s, S, P[:, 0])
    z = np.interp(s, S, P[:, 1])
    return np.column_stack([x, z])


def densify(P, max_step):
    return resample(P, max_step, keep_vertices=True)


def cut(P, s0, s1):
    """Sub-polyline between chainages s0 < s1 (ends interpolated)."""
    P = A(P)
    S = chainage(P)
    s0 = max(0.0, min(s0, S[-1]))
    s1 = max(0.0, min(s1, S[-1]))
    if s1 < s0:
        return cut(P, s1, s0)[::-1]
    inner = P[(S > s0 + 1e-9) & (S < s1 - 1e-9)]
    return np.vstack([point_at(P, s0, S), inner, point_at(P, s1, S)])


def reverse(P):
    return A(P)[::-1].copy()


def concat(*parts, eps=0.05):
    """Join polylines end to start (a joint closer than eps is merged)."""
    out = []
    for p in parts:
        p = A(p)
        if len(p) == 0:
            continue
        if out and np.hypot(*(out[-1][-1] - p[0])) < eps:
            p = p[1:]
        out.append(p)
    return dedup(np.vstack(out)) if out else np.zeros((0, 2))


# ------------------------------------------------------------------ offsets and tapers
def vertex_normals(P):
    """Right normals at vertices (mean of the adjacent segment normals) and the miter scale."""
    P = A(P)
    d = np.diff(P, axis=0)
    n = np.hypot(*d.T)[:, None]
    t = d / np.where(n > 0, n, 1)
    tv = np.vstack([t[:1], t[:-1] + t[1:], t[-1:]])
    tv /= np.maximum(np.hypot(*tv.T)[:, None], 1e-12)
    nr = np.column_stack([tv[:, 1], -tv[:, 0]])
    # miter: 1 / cos(half the turn) between the segment normals
    seg_n = np.column_stack([t[:, 1], -t[:, 0]])
    sc = np.ones(len(P))
    if len(P) > 2:
        c = (seg_n[:-1] * nr[1:-1]).sum(1)
        sc[1:-1] = 1.0 / np.clip(c, 0.5, 1.0)
    return nr, sc


def offset(P, d):
    """Polyline offset by d (m, + = right). For smooth roads densify first."""
    P = A(P)
    nr, sc = vertex_normals(P)
    return P + nr * (d * sc)[:, None]


def offset_var(P, dfun, step=2.0):
    """Polyline offset by a function of chainage d(s) (+ = right); P is densified to `step` first."""
    P = densify(P, step)
    S = chainage(P)
    nr, sc = vertex_normals(P)
    dv = np.array([dfun(s) for s in S])
    return P + nr * (dv * sc)[:, None]


def smooth01(u, shape="cos"):
    """Transition 0 → 1 on u ∈ [0, 1] with zero slope at both ends ("cos") or a straight ramp ("lin")."""
    u = min(max(u, 0.0), 1.0)
    if shape == "lin":
        return u
    return 0.5 - 0.5 * math.cos(math.pi * u)


def taper_len_for_angle(d, max_deg, shape="cos"):
    """Shortest taper that moves a lane sideways by d with the divergence angle never above max_deg."""
    k = math.pi / 2.0 if shape == "cos" else 1.0
    return k * abs(d) / math.tan(math.radians(max_deg))


def taper_max_angle_deg(d, L, shape="cos"):
    k = math.pi / 2.0 if shape == "cos" else 1.0
    return math.degrees(math.atan(k * abs(d) / max(L, 1e-9)))


# ------------------------------------------------------------------ arcs, Dubins paths
def arc_pts(c, R, a0, sweep, step=2.0):
    """Points on a circle of centre c, radius R, from polar angle a0 sweeping `sweep` rad (+ = CCW)."""
    n = max(2, int(math.ceil(abs(sweep) * R / step)) + 1)
    a = a0 + np.linspace(0, sweep, n)
    return np.column_stack([c[0] + R * np.cos(a), c[1] + R * np.sin(a)])


def _dubins_words(alpha, beta, d):
    sa, sb, ca, cb = math.sin(alpha), math.sin(beta), math.cos(alpha), math.cos(beta)
    cab = math.cos(alpha - beta)
    out = {}
    # LSL
    p2 = 2 + d * d - 2 * cab + 2 * d * (sa - sb)
    if p2 >= 0:
        t1 = math.atan2(cb - ca, d + sa - sb)
        out["LSL"] = (mod2pi(-alpha + t1), math.sqrt(p2), mod2pi(beta - t1))
    # RSR
    p2 = 2 + d * d - 2 * cab + 2 * d * (sb - sa)
    if p2 >= 0:
        t1 = math.atan2(ca - cb, d - sa + sb)
        out["RSR"] = (mod2pi(alpha - t1), math.sqrt(p2), mod2pi(-beta + t1))
    # LSR
    p2 = -2 + d * d + 2 * cab + 2 * d * (sa + sb)
    if p2 >= 0:
        p = math.sqrt(p2)
        t2 = math.atan2(-ca - cb, d + sa + sb) - math.atan2(-2.0, p)
        out["LSR"] = (mod2pi(-alpha + t2), p, mod2pi(-mod2pi(beta) + t2))
    # RSL
    p2 = d * d - 2 + 2 * cab - 2 * d * (sa + sb)
    if p2 >= 0:
        p = math.sqrt(p2)
        t2 = math.atan2(ca + cb, d - sa - sb) - math.atan2(2.0, p)
        out["RSL"] = (mod2pi(alpha - t2), p, mod2pi(beta - t2))
    # RLR
    tmp = (6.0 - d * d + 2 * cab + 2 * d * (sa - sb)) / 8.0
    if abs(tmp) <= 1:
        p = mod2pi(TAU - math.acos(tmp))
        t = mod2pi(alpha - math.atan2(ca - cb, d - sa + sb) + p / 2.0)
        out["RLR"] = (t, p, mod2pi(alpha - beta - t + p))
    # LRL
    tmp = (6.0 - d * d + 2 * cab + 2 * d * (-sa + sb)) / 8.0
    if abs(tmp) <= 1:
        p = mod2pi(TAU - math.acos(tmp))
        t = mod2pi(-alpha - math.atan2(ca - cb, d + sa - sb) + p / 2.0)
        out["LRL"] = (t, p, mod2pi(mod2pi(beta) - alpha - t + p))
    return out


def _dubins_sample(p0, th0, word, params, R, step):
    pts = [np.asarray(p0, float)]
    x, z, th = float(p0[0]), float(p0[1]), th0
    for ch, L in zip(word, params):
        if ch == "S":
            dist = L * R
            n = max(1, int(math.ceil(dist / step)))
            for k in range(1, n + 1):
                pts.append(np.array([x + math.cos(th) * dist * k / n, z + math.sin(th) * dist * k / n]))
            x += math.cos(th) * dist
            z += math.sin(th) * dist
        else:
            sgn = 1.0 if ch == "L" else -1.0
            c = np.array([x, z]) + R * (left(unit(th)) if sgn > 0 else right(unit(th)))
            a0 = math.atan2(z - c[1], x - c[0])
            sweep = sgn * L
            arc = arc_pts(c, R, a0, sweep, step)
            pts.extend(list(arc[1:]))
            x, z = arc[-1]
            th = th + sweep
    return np.array(pts), wrap(th)


def dubins(p0, th0, p1, th1, R, words=None, step=2.0, accept=None):
    """Shortest Dubins path (arcs of radius R and straights) from pose (p0, th0) to (p1, th1).

    `words` limits the path types (e.g. ["RSL", "LSR"]); `accept(pts)` may veto a candidate.
    Returns (pts, info) or (None, None). Each candidate is re-checked: its end must hit p1 / th1."""
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    dx, dz = p1 - p0
    D = math.hypot(dx, dz)
    d = D / R
    th = math.atan2(dz, dx) if D > 1e-12 else 0.0
    alpha = mod2pi(th0 - th)
    beta = mod2pi(th1 - th)
    cands = []
    for w, prm in _dubins_words(alpha, beta, d).items():
        if words and w not in words:
            continue
        L = sum(prm) * R
        cands.append((L, w, prm))
    cands.sort()
    for L, w, prm in cands:
        pts, the = _dubins_sample(p0, th0, w, prm, R, step)
        if np.hypot(*(pts[-1] - p1)) > 1e-3 * max(1.0, D) or abs(wrap(the - th1)) > 1e-4:
            continue
        pts[-1] = p1
        if accept is not None and not accept(pts):
            continue
        turns = [(ch, (v if ch != "S" else v * R)) for ch, v in zip(w, prm)]
        return pts, {"word": w, "length": L, "turns": turns, "R": R}
    return None, None


def smooth_transitions(P, Lt, step=1.0):
    """Clothoid-like transitions: the curvature of P (as a function of arc length) is averaged over Lt, which turns
    every arc ↔ straight jump into a linear curvature ramp (an exact clothoid), then the end point is pinned back with
    a correction whose slope is zero at both ends, so the end positions and end tangents are kept exactly.
    P must start and end with straights at least Lt/2 long (tapers / parallel lanes / terminal straights)."""
    P = resample(dedup(P), step, keep_vertices=False)
    if len(P) < 5 or Lt <= step:
        return P
    d = np.diff(P, axis=0)
    ds = np.hypot(*d.T)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    k = max(1, int(round(Lt / step)))
    dth = np.diff(th)
    ker = np.ones(k) / k
    dth_s = np.convolve(dth, ker, mode="same")
    # keep the total turn exactly (the kernel may lose a little at the very ends)
    tot, tot_s = dth.sum(), dth_s.sum()
    if abs(tot_s) > 1e-12:
        dth_s *= tot / tot_s
    th_s = np.concatenate([[th[0]], th[0] + np.cumsum(dth_s)])
    Q = np.vstack([P[0], P[0] + np.cumsum(np.column_stack([np.cos(th_s), np.sin(th_s)]) * ds[:, None], axis=0)])
    err = P[-1] - Q[-1]
    S = chainage(Q)
    u = S / S[-1]
    w = 3 * u ** 2 - 2 * u ** 3
    Q = Q + w[:, None] * err[None, :]
    Q[0], Q[-1] = P[0], P[-1]
    return Q


def turn_total(P):
    """Signed total heading change (rad, + = left)."""
    d = np.diff(A(P), axis=0)
    th = np.arctan2(d[:, 1], d[:, 0])
    return float(np.sum([wrap(b - a) for a, b in zip(th[:-1], th[1:])]))


def min_radius(P, base=10.0):
    """Smallest circumradius of point triples spaced ≈ base m apart (∞ for a straight)."""
    Q = resample(P, base, keep_vertices=False)
    if len(Q) < 3:
        return math.inf
    a, b, c = Q[:-2], Q[1:-1], Q[2:]
    ab = np.hypot(*(b - a).T)
    bc = np.hypot(*(c - b).T)
    ca = np.hypot(*(a - c).T)
    cross = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        r = ab * bc * ca / (2 * cross)
    r = r[np.isfinite(r)]
    return float(r.min()) if len(r) else math.inf


# ------------------------------------------------------------------ crossings
def crossings(P, Q, skip_ends=0.0):
    """Proper crossings of two polylines: list of (sP, sQ, point, angle_deg). Touching ends within skip_ends of
    either polyline's end are ignored."""
    P = A(P)
    Q = A(Q)
    if len(P) < 2 or len(Q) < 2:
        return []
    a0, a1 = P[:-1], P[1:]
    b0, b1 = Q[:-1], Q[1:]
    # bbox prefilter
    amin, amax = np.minimum(a0, a1), np.maximum(a0, a1)
    bmin, bmax = np.minimum(b0, b1), np.maximum(b0, b1)
    if (amax[:, 0].max() < bmin[:, 0].min() or bmax[:, 0].max() < amin[:, 0].min() or
            amax[:, 1].max() < bmin[:, 1].min() or bmax[:, 1].max() < amin[:, 1].min()):
        return []
    ov = ((amin[:, None, 0] <= bmax[None, :, 0]) & (bmin[None, :, 0] <= amax[:, None, 0]) &
          (amin[:, None, 1] <= bmax[None, :, 1]) & (bmin[None, :, 1] <= amax[:, None, 1]))
    I, J = np.nonzero(ov)
    if len(I) == 0:
        return []
    r = a1[I] - a0[I]
    s = b1[J] - b0[J]
    den = r[:, 0] * s[:, 1] - r[:, 1] * s[:, 0]
    qp = b0[J] - a0[I]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]) / den
        u = (qp[:, 0] * r[:, 1] - qp[:, 1] * r[:, 0]) / den
    ok = (np.abs(den) > 1e-12) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
    SP, SQ = chainage(P), chainage(Q)
    LP, LQ = SP[-1], SQ[-1]
    out = []
    for k in np.nonzero(ok)[0]:
        i, j = I[k], J[k]
        sp = SP[i] + t[k] * (SP[i + 1] - SP[i])
        sq = SQ[j] + u[k] * (SQ[j + 1] - SQ[j])
        if skip_ends > 0 and (sp < skip_ends or sp > LP - skip_ends or sq < skip_ends or sq > LQ - skip_ends):
            continue
        pt = a0[i] + t[k] * r[k]
        ang = line_angle_deg(r[k], s[k])
        out.append((float(sp), float(sq), pt, ang))
    # merge duplicates (a crossing exactly at a shared vertex is found twice)
    out.sort(key=lambda c: c[0])
    merged = []
    for c in out:
        if merged and abs(c[0] - merged[-1][0]) < 1e-6 and abs(c[1] - merged[-1][1]) < 1e-6:
            continue
        merged.append(c)
    return merged


def min_distance(P, Q):
    """Smallest distance between two polylines (0 when they cross)."""
    import shapely
    return float(shapely.LineString(A(P)).distance(shapely.LineString(A(Q))))


# ------------------------------------------------------------------ ribbons
def ribbon(P, w_left, w_right=None):
    """Polygon of a band around centreline P: w_left to the left, w_right to the right (flat ends)."""
    import shapely
    from shapely.geometry import LineString, Polygon
    P = dedup(P)
    if w_right is None:
        w_right = w_left
    if len(P) < 2 or (w_left + w_right) <= 0:
        return Polygon()
    if abs(w_left - w_right) < 1e-9:
        return LineString(P).buffer(w_left, cap_style="flat", join_style="round", quad_segs=4)
    L = LineString(P).offset_curve(w_left, join_style="round", quad_segs=4) if w_left > 0 else LineString(P)
    Rr = LineString(P).offset_curve(-w_right, join_style="round", quad_segs=4) if w_right > 0 else LineString(P)
    ring = np.vstack([np.asarray(L.coords), np.asarray(Rr.coords)[::-1]])
    poly = Polygon(ring)
    return poly if poly.is_valid else shapely.make_valid(poly)
