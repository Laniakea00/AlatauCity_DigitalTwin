"""Shared helpers of the land rule modules (validate/rules/{land,buildings,green,years}.py, w44).

Works on the validator ctx of CONTRACT §5 only (ctx.norms / ctx.norm / ctx.rules / ctx.<file dicts> / ctx.area / ctx.h …);
geometry built from the ctx files is cached per ctx. Rule texts come from rules.json, numbers from norms.json by key."""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import land_util as U  # noqa: E402

_CACHE = {}


def cache(ctx):
    k = id(ctx)
    if k not in _CACHE:
        _CACHE.clear()
        _CACHE[k] = {}
    return _CACHE[k]


def norms(ctx):
    """A land_util.Norms over ctx.norms (dict of norms.json, or an object that has .doc / .n)."""
    c = cache(ctx)
    if "norms" not in c:
        src = ctx.norms
        N = U.Norms.__new__(U.Norms)
        doc = src if isinstance(src, dict) else getattr(src, "doc", None)
        if doc is None:
            N.__init__()
        else:
            N.doc = doc
            N.n = doc["norms"] if "norms" in doc else doc
            N.used = {}
        c["norms"] = N
    return c["norms"]


def nv(ctx, key, *sub):
    return norms(ctx).v(key, *sub)


def weak(ctx, *keys):
    """True when any key has status analogue / not_verified (CONTRACT §5: such a norm gives a warning)."""
    N = norms(ctx)
    return any(N.status(k) in ("analogue", "not_verified") for k in keys)


def rule(ctx, no):
    rr = ctx.rules["rules"] if isinstance(ctx.rules, dict) and "rules" in ctx.rules else ctx.rules
    for r in rr:
        if r.get("id") == no or r.get("no") == no:
            return r
    return {"text_ru": f"правило {no}", "severity": {"default": "error"}}


def issue(ctx, no, x, z, what, ids=(), sev=None, lv=0):
    r = rule(ctx, no)
    s = sev or (r.get("severity") or {}).get("default", "error")
    return {"rule": no, "sev": s, "x": round(float(x), 1), "z": round(float(z), 1), "lv": lv,
            "what_ru": f"{what}", "ids": [str(i) for i in ids], "rule_ru": r.get("text_ru")}


def missing(ctx, no, *names):
    """Issue list for missing files (warning «нет файла»), or None if everything is there."""
    miss = [n for n in names if getattr(ctx, n, None) is None]
    if not miss:
        return None
    c = ctx.area.centroid if getattr(ctx, "area", None) is not None else Point(0, 0)
    return [issue(ctx, no, c.x, c.y, "нет файла: " + ", ".join(m + ".json" for m in miss), [], sev="warning")]


def poly(c):
    return U.from_coords(c)


def geom(rec):
    return U.geom(rec)


def edge_dist(ctx, x, z):
    """Distance from a point to the edge of the checked area (for «ждёт соседа»)."""
    return ctx.area.exterior.distance(Point(x, z))


# --------------------------------------------------------------------------------------------- cached geometry
def lots(ctx):
    c = cache(ctx)
    if "lots" not in c:
        L = (ctx.lots or {}).get("lots", [])
        for l in L:
            l["_p"] = geom(l)
        c["lots"] = L
        c["lot_by_id"] = {l["id"]: l for l in L}
    return c["lots"]


def lot_by_id(ctx):
    lots(ctx)
    return cache(ctx)["lot_by_id"]


def buildings(ctx):
    c = cache(ctx)
    if "b" not in c:
        B = (ctx.buildings or {}).get("buildings", [])
        for b in B:
            b["_p"] = poly(b["footprint"])
        c["b"] = B
    return c["b"]


def blocks(ctx):
    c = cache(ctx)
    if "blocks" not in c:
        B = (ctx.blocks or {}).get("blocks", [])
        for b in B:
            b["_p"] = geom(b)
        c["blocks"] = B
    return c["blocks"]


def segs(ctx):
    return {s["id"]: s for s in (ctx.network or {}).get("segments", [])}


def road_polys(ctx, part):
    c = cache(ctx)
    k = "road_" + part
    if k not in c:
        c[k] = U.network_polys(ctx.network or {"segments": []}, norms(ctx), part)
    return c[k]


def driveways(ctx):
    """ctx.driveways (OUT/<d>/driveways.json, network format) or None when the file is missing."""
    return getattr(ctx, "driveways", None)


def drive_polys(ctx, part):
    """[(segment or pad, polygon)] of the driveways: part 'carriage' / 'walk' / 'red' per segment, plus turnaround pads."""
    c = cache(ctx)
    k = "drive_" + part
    if k not in c:
        dv = driveways(ctx) or {"segments": []}
        res = [(s, p) for s, p, lv in U.network_polys(dv, norms(ctx), part)]
        res += [({"id": f"pad_{pd['node']}", "years": pd["years"], "pad": True}, poly(pd["polygon"])) for pd in dv.get("pads", [])]
        c[k] = res
    return c[k]


def walknet(ctx):
    c = cache(ctx)
    if "walk" not in c:
        c["walk"] = U.WalkNet(ctx.network or {"segments": []})
    return c["walk"]


def zone_rules(ctx):
    c = cache(ctx)
    if "zr" not in c:
        c["zr"] = {z["id"]: (z, U.zone_rules(z), poly(z["polygon"])) for z in ctx.spec.get("zones", [])}
    return c["zr"]


def lot_zone(ctx, L):
    blk = cache(ctx).get("blk")
    if blk is None:
        blk = {b["id"]: b for b in blocks(ctx)}
        cache(ctx)["blk"] = blk
    b = blk.get(L.get("block"))
    return zone_rules(ctx).get(b["zone"]) if b and b.get("zone") else None


def exists_in(years, Y, i=0):
    return years is not None and years[i] <= Y


def stage_years(ctx):
    return list(getattr(ctx, "years", None) or nv(ctx, "validator.years"))
