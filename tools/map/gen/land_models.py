"""Building typologies and the model catalogue of the land tools (w44): footprints inside a lot and model names (rule 18).

Shapes are design choices of the qTwin model (section depths, tower sides), not norms; every distance that a norm fixes
(gaps, fire passages, setbacks) is passed in by the caller from norms.json."""
import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import land_util as U

# design parameters of the model typologies (m) — «модель qTwin»
SECTION_DEPTH = {"housing": 15.0, "business": 18.0}       # perimeter sections
SECTION_LEN = 60.0                                         # one building per ≤ 60 m of frontage (validator.identical_models facade_repeat_max_m)
TOWER_SIDE = {"housing": 26.0, "business": 32.0}
SLAB_DEPTH = 13.0
WING_MIN = 9.0                                             # a hole of a perimeter section narrower than this is a slit, not a
#                                                            courtyard (m)
HAIRLINE = 2.0                                             # strips of a section narrower than this are cut off (m)
HOUSE_MIN_M2 = 60.0                                        # smallest detached house footprint the model places (m²)
NEIGHBOUR_DIFF_M = 80.0                                    # m between centres: buildings this near take different variants when
                                                           # the family has one left (модель qTwin, tester item 100)
VARIANTS = 12                                              # facade variants per family
SOCIAL_FLOORS = {"school": (3, 4), "kindergarten": (2, 3), "polyclinic": (3, 5), "pharmacy_shop": (1, 2), "fire_station": (2, 2)}
# class-A warehouses of a logistics park (industry and logistics lots): one shed is 120–200 m deep, up to 300 m long and
# 20–50 thousand m²; a truck yard lies in front of its dock side. Rule 18 checks the maximum on every industry building.
WAREHOUSE_DEPTH = (120.0, 200.0)
WAREHOUSE_LEN_MAX = 300.0
WAREHOUSE_M2 = (20000.0, 50000.0)
WAREHOUSE_DEPTH_MIN = 40.0                                 # a narrower strip of a lot holds no class-A row (m)
TRUCK_YARD = 38.0                                          # truck yard in front of the dock side (m), 35–40 m
DOCK_PITCH_M = 4.0                                         # dock doors along the dock side, one per this many metres
NOBUILD_CLEAR_M = 0.05                                     # a footprint keeps this much clear of a no-build strip, over the
#                                                            0.01 m rounding of buildings.json coordinates (m)
NOBUILD_KEEP_SHARE = 0.5                                   # a footprint cut by a strip stays when its largest piece keeps this
#                                                            share of it; else the building is left out


def clear_of(fp, nb, keep_share=NOBUILD_KEEP_SHARE):
    """A footprint cut off the no-build strips `nb` (already widened by NOBUILD_CLEAR_M): fp itself when it is clear, else its
    largest hole-free piece outside them, or None when that keeps less than keep_share of fp. No area tolerance: the
    validator takes a cable strip (utilities.to_foundations_m) by plain intersection."""
    if nb is None or nb.is_empty or not fp.intersects(nb):
        return fp
    rest = U.clean(fp.difference(nb))
    big = max(U.no_holes(rest, 1.0), key=lambda q: q.area, default=None)      # touches nb along the cut only
    if big is None or big.area < keep_share * fp.area:
        return None
    return big


REJOIN_TOUCH_M = 0.05   # m: a cut-out part of the band touches a section when nearer than this (model parameter)
SLAB_OUT_TOL_M2 = 0.01    # m²: a slab's rectangle may leave its buildable part by this much (float noise) — модель qTwin


def ring_sections(lot, setback, depth, sec_len, gap, join_below=None):
    """Perimeter-block sections: the band between lot−setback and lot−(setback+depth), cut every sec_len m by gaps.
    join_below: two sections of one ring nearer than this (a blade near a corner leaves the two legs a few metres apart
    across it) are one building again through the band between them, while that stays one polygon without a court (tall
    zones: two towers 4–8 m apart across a corner kept one of them at 28 m, tester items 118–119)."""
    outer = U.clean(lot.buffer(-setback, join_style="mitre"))
    inner = U.clean(lot.buffer(-(setback + depth), join_style="mitre"))
    if outer.is_empty:
        return []
    band = U.clean(outer.difference(inner)) if not inner.is_empty else outer
    res = []
    for part in U.polys(outer, 50.0):
        ring = part.exterior
        L = ring.length
        n = max(1, int(round(L / sec_len)))
        blades = []
        for k in range(n):
            p = ring.interpolate(k * L / n)
            c = part.centroid
            d = np.array([c.x - p.x, c.y - p.y])
            nd = np.hypot(*d)
            if nd < 1e-6:
                continue
            d = d / nd
            # blade along the inward direction of the nearest edge normal
            q = ring.interpolate(k * L / n + 1.0)
            t = np.array([q.x - p.x, q.y - p.y])
            nt = np.hypot(*t)
            if nt > 1e-6:
                t = t / nt
                nrm = np.array([-t[1], t[0]])
                if np.dot(nrm, d) < 0:
                    nrm = -nrm
            else:
                nrm = d
            a = np.array([p.x, p.y]) - nrm * 2
            b = np.array([p.x, p.y]) + nrm * (depth + 4)
            blades.append(LineString([a, b]).buffer(gap / 2.0, cap_style="flat"))
        bpart = band.intersection(part)
        cut = U.clean(bpart.difference(unary_union(blades))) if blades else bpart
        pcs = []
        for q in U.polys(cut, depth * 8.0):
            # a slit inside a section (a narrow lot's bands meet round it) is no courtyard: the section is one building, not
            # pieces cut through the slit that share their walls (gen_buildings splits polygons at their holes); hairline
            # strips and pinches (a narrow lot's band thinned to nothing) are no part of a building
            q = Polygon(q.exterior, [h for h in q.interiors if not Polygon(h).buffer(-WING_MIN / 2).is_empty])
            q = U.clean(U.clean(q.buffer(-HAIRLINE / 2, join_style="mitre").buffer(HAIRLINE / 2, join_style="mitre")).intersection(q))
            pcs += U.polys(q, depth * 8.0)
        res += rejoin(pcs, U.clean(bpart), join_below) if join_below and len(pcs) > 1 else pcs
    # corners may produce L-shapes: keep them as they are (one section each)
    return res


def rejoin(pcs, band, dmin):
    """Sections nearer than dmin joined back through the band between them (the parts of the band cut out that touch both),
    nearest pair first, while the union is one polygon without a hole."""
    pcs = list(pcs)
    tried = set()
    while True:
        best = None
        for i in range(len(pcs)):
            for j in range(i + 1, len(pcs)):
                k = (pcs[i].wkb, pcs[j].wkb)
                if k in tried:
                    continue
                d = pcs[i].distance(pcs[j])
                if d < dmin and (best is None or d < best[0]):
                    best = (d, i, j, k)
        if best is None:
            return pcs
        _, i, j, k = best
        gaps = U.polys(U.clean(band.difference(unary_union(pcs))), 0.01)
        tie = [g for g in gaps if g.distance(pcs[i]) < REJOIN_TOUCH_M and g.distance(pcs[j]) < REJOIN_TOUCH_M]
        u = U.merge([pcs[i], pcs[j]] + tie) if tie else None
        if u is None or u.geom_type != "Polygon" or u.interiors:
            tried.add(k)
            continue
        pcs[i] = u
        del pcs[j]


def place_rect(region, area, ang, aspect=1.6, min_area=None):
    """Largest oriented rectangle of ≈ area (long side along ang) inside region; shrinks until it fits. None if nothing fits."""
    if region.is_empty:
        return None
    parts = U.polys(region, 10.0)
    if not parts:
        return None
    reg = max(parts, key=lambda q: q.area)
    try:
        c = shapely.ops.polylabel(reg, tolerance=1.0)
    except Exception:
        c = reg.representative_point()
    a = area
    lo = min_area or area * 0.3
    while a >= lo:
        L = math.sqrt(a * aspect)
        W = a / L
        r = U.oriented_rect(c.x, c.y, ang, L, W)
        if reg.buffer(0.01).contains(r):
            return r
        r2 = U.oriented_rect(c.x, c.y, ang + math.pi / 2, L, W)
        if reg.buffer(0.01).contains(r2):
            return r2
        a *= 0.85
    return None


def warehouses(region, ang, yard, gap, lot=None):
    """Class-A sheds over the buildable region of a logistics lot: rows along ang, the sheds WAREHOUSE_DEPTH deep, each with
    a truck yard (`yard` m) in front of its dock side; two rows face one yard between them (a shared truck court: tester item
    61, the sheds of a park held 42 of the zone's 99 thousand m² with a yard per row), the number of rows chosen so the depth
    stays in that range as far as the region allows; along a row, sheds of ≤ WAREHOUSE_LEN_MAX m and ≤ WAREHOUSE_M2 max, with
    fire gaps `gap` between them. A shed a no-build hole (a street's turning circle, its setback) cuts at the dock side keeps
    its length and gives up depth down to WAREHOUSE_DEPTH min (the yard widens there). Each is {fp, yard (the court in front
    of it, clipped to `lot`; one shed of a pair carries the shared court), dock (the dock side, a line on the yard), docks
    (doors, one per DOCK_PITCH_M)}: rectangles whole inside the region. [] when the region is smaller than one shed
    (WAREHOUSE_M2 min) or too narrow for a row: the caller keeps one."""
    import shapely.affinity as aff
    if region is None or region.is_empty or region.area < WAREHOUSE_M2[0]:
        return []
    c = region.centroid
    R = aff.rotate(region, -ang, origin=c, use_radians=True)
    LT = aff.rotate(lot, -ang, origin=c, use_radians=True) if lot is not None else None
    u0, v0, u1, v1 = R.bounds
    W, H = u1 - u0, v1 - v0
    dlo, dhi = WAREHOUSE_DEPTH
    best = None
    for n in range(1, 16):
        ny = (n + 1) // 2                    # yards: one per pair of rows, one more for an odd last row
        D = (H - ny * yard) / n
        if D < WAREHOUSE_DEPTH_MIN:
            break
        dev = max(dlo - D, D - dhi, 0.0)
        if best is None or dev < best[0] - 1e-6:
            best = (dev, n, min(D, dhi))
    if best is None:
        return []
    _, n, D = best
    Lmax = min(WAREHOUSE_LEN_MAX, WAREHOUSE_M2[1] / D)
    nseg = max(1, int(math.ceil((W + gap) / (Lmax + gap))))
    Ls = (W - (nseg - 1) * gap) / nseg
    # rows bottom-up: (shed v-range, dock at its top (True) or bottom, the yard's v-range)
    rows, v = [], v0
    for i in range(0, n, 2):
        if i + 1 < n:            # a pair: shed (dock up), court, shed (dock down)
            rows.append((v, v + D, True, (v + D, v + D + yard)))
            rows.append((v + D + yard, v + 2 * D + yard, False, None))
            v += 2 * D + yard
        else:                    # the last odd row: its own yard below it
            rows.append((v + yard, v + yard + D, False, (v, v + yard)))
            v += yard + D
    out = []
    back = lambda g: aff.rotate(g, ang, origin=c, use_radians=True)      # noqa: E731
    for k in range(nseg):
        ua = u0 + k * (Ls + gap)
        docks_at = []
        for va, vb, dock_up, yv in rows:
            sh = box(ua, va, ua + Ls, vb)
            bad = U.clean(sh.difference(R))
            a0, a1 = va, vb
            if not bad.is_empty:
                # a hole at the dock side: the shed gives up depth there (down to the minimum) and keeps its length
                b0, b1 = bad.bounds[1], bad.bounds[3]
                if dock_up and b0 > va + dlo:
                    a1 = b0 - 0.01
                elif not dock_up and b1 < vb - dlo:
                    a0 = b1 + 0.01
            sh = box(ua, a0, ua + Ls, a1)
            spans = [(ua, ua + Ls)]
            for g in U.polys(U.clean(sh.difference(R)), 0.01):
                g0, _, g1, _ = g.bounds
                spans = [s_ for b0_, b1_ in spans for s_ in ((b0_, min(b1_, g0)), (max(b0_, g1), b1_)) if s_[1] - s_[0] > 1e-6]
            if not spans:
                continue
            s0, s1 = max(spans, key=lambda s_: s_[1] - s_[0])
            if (s1 - s0) * (a1 - a0) < 0.5 * Ls * D:
                continue
            dv = a1 if dock_up else a0
            docks_at.append((s0, s1, dv, dock_up, yv, a0, a1))
        for s0, s1, dv, dock_up, yv, a0, a1 in docks_at:
            if yv is not None:
                ylo, yhi = (a1, a1 + yard) if dock_up else (a0 - yard, a0)
                if dock_up:      # the shared court reaches the facing shed's dock (or the court's far side)
                    up = [q for q in docks_at if not q[3] and q[5] >= a1 - 1e-6]
                    yhi = min([q[5] for q in up], default=yv[1])
                yd = box(s0, ylo, s1, yhi)
                if LT is not None:
                    yd = U.clean(yd.intersection(LT))
                    yd = max(U.polys(yd, 1.0), key=lambda q: q.area, default=yd)
            else:
                yd = None
            out.append({"fp": back(box(s0, a0, s1, a1)), "yard": back(yd) if yd is not None and not yd.is_empty else None,
                        "dock": back(LineString([(s0, dv), (s1, dv)])), "docks": int((s1 - s0) // DOCK_PITCH_M)})
    return out


SOCIAL_ASPECTS = (2.0, 1.0, 3.0)
SOCIAL_FIT_SHARE = 1.0      # a social building holds this share of its capacity's floor area (places × the twin's m² per place);
#                             before, a footprint down to half of it was taken and the floors capped, so the building held less
SOCIAL_FIT_TIGHT = 0.5      # a plot that cannot hold it (the spec's own plot of a registry object, or one reshaped after the
#                             test): the building down to this share, logged
SOCIAL_RING_LOT = ("school", "kindergarten", "polyclinic")      # lots that try to keep the fire ring inside


def social_place(region, gfa, fl_hi, ang, ring=None, share=SOCIAL_FIT_SHARE, ring_only=False):
    """Footprint of a social building (gfa over its top floor count) in the buildable region of its lot: with the fire ring
    inside the lot first (region shrunk by `ring`), then without it unless ring_only; aspects SOCIAL_ASPECTS. None if nothing
    fits. gen_buildings places with it, and gen_blocks_lots checks a plot with it (ring_only) before making the lot."""
    if region is None or region.is_empty or gfa <= 0:
        return None
    for reg2 in ((U.clean(region.buffer(-ring)) if ring else None), None if (ring and ring_only) else region):
        if reg2 is None or reg2.is_empty:
            continue
        for aspect in SOCIAL_ASPECTS:
            fp = place_rect(reg2, gfa / fl_hi, ang, aspect, min_area=gfa / fl_hi * share)
            if fp is not None:
                return fp
    return None


def grid_points(region, ang, step_l, step_w):
    """Grid of points inside region aligned to ang (for towers / slabs)."""
    c = region.centroid
    lo, hi = U._proj_range(region, ang)
    lo2, hi2 = U._proj_range(region, ang + math.pi / 2)
    d = np.array([math.cos(ang), math.sin(ang)])
    n = np.array([-d[1], d[0]])
    pts = []
    for s in np.arange(lo + step_l / 2, hi, step_l):
        for t in np.arange(lo2 + step_w / 2, hi2, step_w):
            p = np.array([c.x, c.y]) + d * s + n * t
            pts.append(p)
    return pts


def towers(region, side, gap, ang, max_n=40):
    out = []
    step = side + gap
    for p in grid_points(region, ang, step, step):
        r = U.oriented_rect(p[0], p[1], ang, side, side)
        if region.contains(r):
            out.append(r)
        if len(out) >= max_n:
            break
    return out


def slabs(region, depth, gap, ang, length_max):
    """Rows of slabs parallel to ang, depth deep, gap apart, cut to ≤ length_max."""
    out = []
    lo2, hi2 = U._proj_range(region, ang + math.pi / 2)
    c = region.centroid
    d = np.array([math.cos(ang), math.sin(ang)])
    n = np.array([-d[1], d[0]])
    for t in np.arange(lo2 + depth / 2, hi2 - depth / 2 + 1e-6, depth + gap):
        p = np.array([c.x, c.y]) + n * t
        band = U.oriented_rect(p[0], p[1], ang, 1e4, depth)
        q = U.clean(region.intersection(band))
        for part in U.polys(q, depth * 10):
            ang2, L, W = U.axis(part)
            if W < depth * 0.8:
                continue
            k = max(1, int(math.ceil(L / length_max)))
            pieces = U.strips(part, ang2, k) if k > 1 else [part]
            for pc in pieces:
                pc2 = pc.buffer(-gap / 4.0, join_style="mitre") if k > 1 else pc
                for pp in U.polys(U.clean(pc2), depth * 10):
                    # the rectangle only while it stays on the buildable part: a piece cut by a slanted lot line has one up to
                    # 15 % larger that stood over the setback and the lot line onto the street (Gate G1: 7 two-storey slabs,
                    # 1–9 m² on local streets, rule 1)
                    mrr = pp.minimum_rotated_rectangle
                    out.append(mrr if mrr.area < pp.area * 1.15 and mrr.difference(region).area <= SLAB_OUT_TOL_M2 else pp)
    return out


def assign_models(buildings, radius, max_same):
    """Model per building: family + variant so that no circle of `radius` around a building of the model holds more than
    max_same buildings of that model (rule 18, validator.identical_models)."""
    from collections import defaultdict
    placed = defaultdict(list)     # model -> [[x, z, count_in_radius]]
    for b in sorted(buildings, key=lambda b: (b["_family"], b["_c"][0], b["_c"][1])):
        fam = b["_family"]
        if b.get("_typical"):
            b["model"] = fam
            continue
        h0 = U.stable_hash(b["_lotid"] + fam) % VARIANTS
        chosen = None
        # first a variant no building within NEIGHBOUR_DIFF_M has (neighbours differ: tester item 100, sections of one lot
        # side by side had one model), then any the rule allows
        for strict in (True, False):
            for k in range(VARIANTS if strict else 200):
                v = (h0 + k) % VARIANTS if k < VARIANTS else k
                m = f"{fam}_{v:02d}"
                near = [q for q in placed[m] if math.hypot(q[0] - b["_c"][0], q[1] - b["_c"][1]) <= radius]
                if strict and any(math.hypot(q[0] - b["_c"][0], q[1] - b["_c"][1]) <= NEIGHBOUR_DIFF_M for q in near):
                    continue
                if len(near) + 1 <= max_same and all(q[2] + 1 <= max_same for q in near):
                    for q in near:
                        q[2] += 1
                    placed[m].append([b["_c"][0], b["_c"][1], len(near) + 1])
                    chosen = m
                    break
            if chosen:
                break
        b["model"] = chosen or f"{fam}_x{len(placed)}"
