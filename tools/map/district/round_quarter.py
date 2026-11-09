"""A round quarter of the master plan drawing (decree 727, owner 09.11.2026): ring streets and radial streets, the blocks between
them are filled by the same generators as the rest of the city, no model of its own.

add(N, ...) puts the streets into a district's net module N before its generate_local; the circle goes to the barriers, so the
rectangular grid of the neighbours stops at the outer ring.
"""
import math

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

HOSTS = ("arterial_regulated", "district_transport", "boulevard")


def add(N, prefix, centre, radii, arms, year, name_ru, why, avoid=None, reach=600.0):
    """radii ascending, arms radial streets. Pieces touching `avoid` (water, villages) are left out. Returns the street count."""
    cx, cz = centre
    host = [(s["id"], LineString(s["line"])) for s in N.STREETS if s["class"] in HOSTS and not s["id"].startswith(prefix)]

    def pt(r, a):
        return (cx + r * math.sin(a), cz + r * math.cos(a))

    def put(sid, line, name):
        L = LineString(line)
        if avoid is not None and L.intersects(avoid):
            return 0
        N.street(sid, "local", line, name, year, why=why)
        return 1

    made = 0
    ang = [2 * math.pi * k / arms for k in range(arms)]
    has_ring = set()                                       # (ring, arm) nodes an arc of the ring really reaches
    for i, r in enumerate(radii):
        n = max(4, int(math.ceil(2 * math.pi * r / arms / 30.0)))
        for k, a in enumerate(ang):
            line = [pt(r, a + (2 * math.pi / arms) * j / n) for j in range(n + 1)]
            if put(f"{prefix}_r{i}_{k}", line, f"{name_ru}: кольцевая улица"):
                made += 1
                has_ring |= {(i, k), (i, (k + 1) % arms)}
    for k, a in enumerate(ang):
        for i in range(len(radii) - 1):
            if (i, k) in has_ring and (i + 1, k) in has_ring:  # no radial left hanging where a ring was cut by `avoid`
                made += put(f"{prefix}_a{k}_{i}", [pt(radii[i], a), pt(radii[i + 1], a)], f"{name_ru}: радиальная улица")
    # every second arm goes on to the nearest street of the city
    for k, a in enumerate(ang):
        if k % 2 or (len(radii) - 1, k) not in has_ring:
            continue
        p = Point(pt(radii[-1], a))
        best = min(host, key=lambda h: h[1].distance(p), default=None)
        if best is None or best[1].distance(p) > reach:
            continue
        q = best[1].interpolate(best[1].project(p))
        made += put(f"{prefix}_x{k}", [(p.x, p.y), (q.x, q.y)], f"{name_ru}: выезд")
    return made


def circle(centre, r):
    return Point(centre).buffer(r, quad_segs=24)


def union(*g):
    return unary_union(list(g))
