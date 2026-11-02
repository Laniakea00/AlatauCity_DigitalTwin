"""Compatibility checks (w43, rule 0): the outputs can be merged into the twin and read by Unity.

- network.json: unique node and segment ids, every segment end a node, ≥ 2 points of [x, z, y], a known profile,
  interchange ramps / structures and joints pointing at existing segments / nodes (the indices roads.json and the
  traffic readers build from);
- 4 scenario years on every object of every output that carries years;
- lrt.json: every station within the LrtLayer snap distance of its line (Unity snaps stations to the route within
  400 m; farther ones are dropped there), ends of a known kind;
- buildings.json: twin bids < 131 072 and unique.
The old `validate_twin.py` runs on the merged output (OUT/_merged/<run>) in w45's `export/check_merge.py`.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lib import geom as G  # noqa: E402

LRT_SNAP_M = 400.0          # Unity LrtLayer: a station farther than this from its route is not drawn (code constant)
BID_MAX = 256 * 512         # Unity's per-building lookups are 256 × 512 texels (BidTable.cs, AlatauLit tuv); the binary layers
                            # carry the bid as int32 (AQL1 bid[nt], HID1) or as an ABB1 index, so the table is the only limit
END_KINDS = {"depot", "terminus", "joint"}


def _c(ctx):
    c = ctx.area.centroid
    return c.x, c.y


def _years_ok(y):
    return isinstance(y, list) and len(y) == 4 and all(isinstance(v, int) for v in y)


def rule0_network(ctx):
    net = ctx.network
    out = []
    x0, z0 = _c(ctx)
    nodes = {}
    for n in net.get("nodes", []):
        if n["id"] in nodes:
            out.append(ctx.issue(0, "error", n["x"], n["z"], f"network: узел {n['id']} повторяется", [n["id"]]))
        nodes[n["id"]] = n
    seg_ids = set()
    profiles = net.get("profiles") or {}
    for s in net.get("segments", []):
        p = s["pts"][0] if s.get("pts") else [x0, z0]
        if s["id"] in seg_ids:
            out.append(ctx.issue(0, "error", p[0], p[1], f"network: отрезок {s['id']} повторяется", [s["id"]]))
        seg_ids.add(s["id"])
        for e in ("a", "b"):
            if s.get(e) not in nodes:
                out.append(ctx.issue(0, "error", p[0], p[1], f"network: конец {e} отрезка {s['id']} — нет узла {s.get(e)}",
                                     [s["id"]]))
        if len(s.get("pts") or []) < 2 or any(len(q) != 3 for q in s["pts"]):
            out.append(ctx.issue(0, "error", p[0], p[1], f"network: у отрезка {s['id']} точки не [x, z, y] или их меньше двух",
                                 [s["id"]]))
        if s.get("pid") not in profiles:
            out.append(ctx.issue(0, "error", p[0], p[1], f"network: профиль {s.get('pid')} отрезка {s['id']} не описан",
                                 [s["id"]]))
        if not _years_ok(s.get("years")):
            out.append(ctx.issue(0, "error", p[0], p[1], f"network: у отрезка {s['id']} не 4 года сценариев", [s["id"]]))
        # end points on the nodes (the twin's roads.json takes node positions from these)
        for e, q in (("a", s["pts"][0]), ("b", s["pts"][-1])):
            n = nodes.get(s.get(e))
            if n is not None and np.hypot(n["x"] - q[0], n["z"] - q[1]) > 0.5:
                out.append(ctx.issue(0, "error", q[0], q[1], f"network: конец {e} отрезка {s['id']} в "
                                     f"{np.hypot(n['x'] - q[0], n['z'] - q[1]):.1f} м от узла {n['id']}", [s["id"], n["id"]]))
    for ic in net.get("interchanges", []):
        bad = [r for r in (ic.get("ramps") or []) + (ic.get("structures") or []) if r not in seg_ids]
        if bad:
            out.append(ctx.issue(0, "error", ic["x"], ic["z"], f"network: развязка {ic['id']} ссылается на несуществующие отрезки",
                                 [ic["id"]] + bad[:5]))
    for j in net.get("joints", []):
        if j.get("node") not in nodes:
            out.append(ctx.issue(0, "error", x0, z0, f"network: стык {j.get('id')} — нет узла {j.get('node')}", [j.get("id")]))
    jid = [j["id"] for j in net.get("joints", [])]
    if len(jid) != len(set(jid)):
        out.append(ctx.issue(0, "error", x0, z0, "network: id стыков повторяются", sorted({x for x in jid if jid.count(x) > 1})[:6]))
    return out


def rule0_lrt(ctx):
    out = []
    for ln in ctx.lrt.get("lines", []):
        P = np.array([q[:2] for q in ln.get("pts", [])], float)
        if len(P) < 2:
            out.append(ctx.issue(0, "error", *_c(ctx), f"lrt: у линии {ln['id']} меньше двух точек", [ln["id"]]))
            continue
        if not _years_ok(ln.get("years")):
            out.append(ctx.issue(0, "error", P[0, 0], P[0, 1], f"lrt: у линии {ln['id']} не 4 года сценариев", [ln["id"]]))
        if any(len(q) != 3 for q in ln["pts"]):
            out.append(ctx.issue(0, "error", P[0, 0], P[0, 1], f"lrt: точки линии {ln['id']} не [x, z, y_rail]", [ln["id"]]))
        for st in ln.get("stations", []):
            d = G.project(P, [st["x"], st["z"]])[1]
            if d > LRT_SNAP_M:
                out.append(ctx.issue(0, "error", st["x"], st["z"], f"lrt: станция {st['id']} в {d:.0f} м от линии — "
                                     f"Unity (LrtLayer, {LRT_SNAP_M:.0f} м) её не покажет", [ln["id"], st["id"]]))
        for e in ln.get("ends") or []:
            if e.get("kind") not in END_KINDS:
                out.append(ctx.issue(0, "error", P[0, 0], P[0, 1], f"lrt: конец линии {ln['id']} вида {e.get('kind')}",
                                     [ln["id"]]))
    for dp in ctx.lrt.get("depots", []):
        if not _years_ok(dp.get("years")):
            out.append(ctx.issue(0, "error", *_c(ctx), f"lrt: у депо {dp['id']} не 4 года", [dp["id"]]))
    return out


def rule0_buildings(ctx):
    out = []
    seen = {}
    for b in ctx.buildings.get("buildings", []):
        fp = b.get("footprint") or [[*_c(ctx)]]
        x, z = fp[0][0], fp[0][1]
        bid = b.get("bid")
        if bid is not None:
            if not isinstance(bid, int) or bid < 0 or bid >= BID_MAX:
                out.append(ctx.issue(0, "error", x, z, f"buildings: bid {bid} здания {b['id']} вне 0…{BID_MAX - 1}", [b["id"]]))
            elif bid in seen:
                out.append(ctx.issue(0, "error", x, z, f"buildings: bid {bid} у {seen[bid]} и {b['id']}", [seen[bid], b["id"]]))
            seen[bid] = b["id"]
        if not _years_ok(b.get("years")):
            out.append(ctx.issue(0, "error", x, z, f"buildings: у здания {b['id']} не 4 года сценариев", [b["id"]]))
    return out


def rule0_years(ctx):
    """4 scenario years on every object of the land outputs that carries `years` (lots, features)."""
    out = []
    for name, keys in (("lots", ["lots"]), ("features", ["parking", "greens"])):
        doc = getattr(ctx, name, None)
        if not doc:
            continue
        for k in keys:
            bad = [o.get("id") for o in doc.get(k, []) if "years" in o and not _years_ok(o["years"])]
            if bad:
                out.append(ctx.issue(0, "error", *_c(ctx), f"{name}.{k}: не 4 года сценариев у {len(bad)}", bad[:6]))
    return out


RULES = [{"no": 0, "key": "compat_network", "fn": rule0_network, "needs": ["network"]},
         {"no": 0, "key": "compat_lrt", "fn": rule0_lrt, "needs": ["lrt"]},
         {"no": 0, "key": "compat_buildings", "fn": rule0_buildings, "needs": ["buildings"]},
         {"no": 0, "key": "compat_years", "fn": rule0_years, "needs": []}]
