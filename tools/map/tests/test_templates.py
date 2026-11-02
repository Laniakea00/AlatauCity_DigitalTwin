"""Proof of the road templates (w43): synthetic crosses built with each template through the whole chain
(gen_network → validate_map rules 0 and 5–11), 0 validator errors each, and a sheet with every template top-down and
in long-section.

    python3 tools/map/tests/test_templates.py [--out OUT] [--only diamond,trumpet_t]

Writes OUT/_tools/templates/tpl_<case>/{network.json, report.*} and OUT/_tools/templates.png. The crosses stand on
flat ground far outside the twin (x, z ≈ 30 km, no OSM roads, no water) so only the template is tested; the *_oblique
cases turn the major road to 81° (as w50 golden ic_kokterek on A-3), so coordinates rounded to 1 cm lie off the axes.
Every merge / diverge tip is checked: a ramp meets its carriageway in one level only at their node (w50 golden: the
cos taper's first metres touched the carriageway 3.1 m before the merge).
Exit code 0 when every case has 0 errors.
"""
import argparse
import io
import json
import math
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
sys.path.insert(0, MAP)
sys.path.insert(0, os.path.join(MAP, "gen"))
sys.path.insert(0, os.path.join(MAP, "validate"))
from lib import paths  # noqa: E402

C = (30000.0, 30000.0)        # flat test ground (terrain 475 m), no OSM, no water
HALF = 1500.0
YEARS = [2030, 2029, 2033, 2030]

# (case, template, major class, minor class, layout, params)
CASES = [
    ("diamond", "diamond", "expressway", "arterial_regulated", "cross", {}),
    ("partial_cloverleaf", "partial_cloverleaf", "expressway", "arterial_regulated", "cross", {}),
    ("cloverleaf", "cloverleaf", "expressway", "expressway", "cross", {}),
    ("directional", "directional", "expressway", "expressway", "T", {}),
    ("trumpet", "trumpet", "expressway", "expressway", "T", {}),
    ("trumpet_t", "trumpet", "expressway", "arterial_regulated", "T", {}),
    ("parclo_A1", "partial_cloverleaf", "expressway", "arterial_regulated", "cross", {"variant": "A", "quadrants": ["sw"]}),
    ("parclo_A4", "partial_cloverleaf", "expressway", "arterial_regulated", "cross",
     {"variant": "A", "quadrants": ["sw", "ne", "se", "nw"]}),
    ("parclo_B2", "partial_cloverleaf", "expressway", "arterial_regulated", "cross", {"variant": "B"}),
    ("parclo_B1", "partial_cloverleaf", "expressway", "arterial_regulated", "cross", {"variant": "B", "quadrants": ["se"]}),
    ("parclo_B4", "partial_cloverleaf", "expressway", "arterial_regulated", "cross",
     {"variant": "B", "quadrants": ["sw", "ne", "se", "nw"]}),
    ("parclo_A1_undiv", "partial_cloverleaf", "expressway", "district_transport", "cross",
     {"variant": "A", "quadrants": ["sw"]}),
    ("parclo_B4_undiv", "partial_cloverleaf", "expressway", "district_transport", "cross",
     {"variant": "B", "quadrants": ["sw", "ne", "se", "nw"]}),
    ("parclo_A_stray", "partial_cloverleaf", "expressway", "arterial_regulated", "cross", {"variant": "A", "quadrants": ["se"]}),
    # an oblique major road (81°, as w50 golden ic_kokterek on A-3): coordinates rounded to 1 cm off the axes
    ("diamond_oblique", "diamond", "expressway", "arterial_regulated", "oblique", {}),
    ("parclo_B4_oblique", "partial_cloverleaf", "expressway", "arterial_regulated", "oblique",
     {"variant": "B", "quadrants": ["sw", "ne", "se", "nw"]}),
    ("parclo_A4_oblique", "partial_cloverleaf", "expressway", "arterial_regulated", "oblique",
     {"variant": "A", "quadrants": ["sw", "ne", "se", "nw"]}),
    # spec ramps (per-ramp lanes): the exit from M eastbound gets 2 lanes from 2040 (a reconstruction), the exit from M
    # westbound 2 lanes from its opening (its profile)
    ("diamond_lanes", "diamond", "expressway", "arterial_regulated", "cross",
     {"ramps": {"M E → m S": {"lanes": 2, "from_year": 2040}, "M W → m N": {"lanes": 2}}}),
    ("split_signal", "crossing_signal", "arterial_regulated", "district_transport", "split", {}),
    ("split_ring", "roundabout", "arterial_regulated", "district_transport", "split", {}),
    ("grade_separation", "grade_separation", "arterial_regulated", "local", "cross", {}),
    ("roundabout", "roundabout", "arterial_regulated", "district_transport", "cross", {}),
    ("square", "square", "arterial_regulated", "district_transport", "cross", {}),
]

# layout "split": a divided arterial in two spec streets meeting at C (A from the south, An to the north, other years)
# crossed by W (local, from the west, listed first) and E (minor class, to the east, slightly skewed): as Western avenue
# × Gate avenue in w47's gate_trial. One 4-arm junction of the node's type, never two


def _rings(net):
    return sorted({ic["id"] for ic in net["interchanges"] if ic["template"] == "roundabout"} |
                  {n.get("ic") for n in net["nodes"] if n.get("kind") == "roundabout"})


def _one_junction(kind):
    def f(net):
        r = _rings(net)
        if kind == "roundabout":
            return None if len(r) == 1 else f"колец {len(r)} ({', '.join(map(str, r))}), нужно одно"
        return None if not r else f"колец {len(r)} ({', '.join(map(str, r))}), нужен один светофорный узел"
    return f


def _lanes(net):
    """diamond_lanes: each key found exactly the exit ramp (one way from M to the terminal on m); «M E → m S» has a
    stage of 2 lanes from 2040 on the 1-lane profile, «M W → m N» the 2-lane profile from its opening, no stage."""
    ic = net["interchanges"][0] if net["interchanges"] else {}
    got = {r["key"]: r for r in ic.get("ramp_lanes") or []}
    seg = {s["id"]: s for s in net["segments"]}
    bad = []
    for key, fy in (("M E → m S", 2040), ("M W → m N", None)):
        r = got.get(key)
        if not r or not r["segments"]:
            bad.append(f"ramps «{key}»: съезд не найден")
            continue
        ss = [seg[i] for i in r["segments"]]
        streets = {tuple(sorted({n for n in (s["a"], s["b"])})) for s in ss}
        for s in ss:
            lanes = max(net["profiles"][s["pid"]]["lanes"])
            st = s.get("stages") or []
            if fy is None and (st or lanes != 2):
                bad.append(f"«{key}» {s['id']}: {lanes} полос, stages {st}")
            if fy is not None and (lanes != 1 or len(st) != 1 or st[0]["years"] != [max(fy, y) for y in s["years"]]
                                   or max(net["profiles"][st[0]["pid"]]["lanes"]) != 2):
                bad.append(f"«{key}» {s['id']}: {lanes} полос, stages {st}")
        if len(streets) > 3:
            bad.append(f"«{key}»: {len(ss)} отрезков — больше одного съезда")
    return "; ".join(bad) or None


EXPECT = {"split_signal": _one_junction("crossing_signal"), "split_ring": _one_junction("roundabout"), "diamond_lanes": _lanes}

# cases where the template must refuse with this text in the generator log (and fall back to a plain overpass)
REFUSE = {"parclo_A_stray": "петли варианта A нет"}


def spec_for(case, tmpl, cmaj, cmin, layout, params):
    x0, z0 = C
    area = [[x0 - HALF, z0 - HALF], [x0 + HALF, z0 - HALF], [x0 + HALF, z0 + HALF], [x0 - HALF, z0 + HALF]]
    major = {"id": "M", "class": cmaj, "line": [[x0 - HALF, z0], [x0 + HALF, z0]], "name_ru": "главная", "years": YEARS,
             "source": "new"}
    if layout == "split":
        y2 = [2033, 2033, 2035, 2033]
        sts = [{"id": "A", "class": cmaj, "line": [[x0, z0 - HALF], [x0, z0]], "name_ru": "проспект (юг)", "years": y2,
                "source": "new"},
               {"id": "An", "class": cmaj, "line": [[x0, z0], [x0, z0 + HALF]], "name_ru": "проспект (север)",
                "years": YEARS, "source": "new"},
               {"id": "W", "class": "local", "line": [[x0 - HALF, z0], [x0, z0]], "name_ru": "запад", "years": YEARS,
                "source": "new"},
               {"id": "E", "class": cmin, "line": [[x0, z0], [x0 + 95.0, z0 + 5.0], [x0 + HALF, z0 + 5.0]],
                "name_ru": "восток", "years": YEARS, "source": "new"}]
        return {"district": f"tpl_{case}", "version": 1, "level": 1, "made_by": "w43 tests", "area": area,
                "boundary": area, "area_ignores_boundary": True, "zones": [], "streets": sts,
                "nodes": [{"id": f"n_{case}", "x": x0, "z": z0, "type": tmpl, "streets": ["A", "An", "E", "W"],
                           "params": dict(params)}],
                "lrt": {}, "edge_joints": [], "keep": []}
    if layout == "oblique":
        u = np.array([math.cos(math.radians(81.0)), math.sin(math.radians(81.0))])
        v = np.array([-u[1], u[0]])

        def across(d):                  # the line through C along d from boundary to boundary
            r = HALF / float(np.max(np.abs(d)))
            return [[round(x0 - r * d[0], 2), round(z0 - r * d[1], 2)], [round(x0 + r * d[0], 2), round(z0 + r * d[1], 2)]]
        major["line"] = across(u)
        mline = across(v)
    elif layout == "T":
        mline = [[x0, z0 - HALF], [x0, z0]]
    else:
        mline = [[x0, z0 - HALF], [x0, z0 + HALF]]
    minor = {"id": "m", "class": cmin, "line": mline, "name_ru": "второстепенная", "years": YEARS, "source": "new"}
    p = dict(params)
    p.setdefault("major", "M")
    return {"district": f"tpl_{case}", "version": 1, "level": 1, "made_by": "w43 tests", "area": area,
            "boundary": area, "area_ignores_boundary": True, "zones": [], "streets": [major, minor],
            "nodes": [{"id": f"ic_{case}", "x": x0, "z": z0, "type": tmpl, "streets": ["M", "m"], "params": p}],
            "lrt": {}, "edge_joints": [], "keep": []}


def _chain(seg):
    P = np.array([v[:2] for v in seg["pts"]], float)
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])


def tips(net):
    """Merge / diverge tips: a ramp meets the carriageway it joins only at their node, from its own side (no touch or
    crossing of the two lines anywhere else, w50 golden ic_kokterek). Returns (problems, smallest offset at 3–30 m from
    the node / distance)."""
    import shapely
    nodes = {n["id"]: n for n in net["nodes"]}
    at = {}
    for s in net["segments"]:
        at.setdefault(s["a"], []).append(s)
        at.setdefault(s["b"], []).append(s)
    bad, slope = [], float("inf")
    for nid, ss in at.items():
        if nodes[nid]["kind"] not in ("merge", "diverge"):
            continue
        p = shapely.Point(nodes[nid]["x"], nodes[nid]["z"])
        ramps = [s for s in ss if s["class"] == "ramp"]
        cws = [s for s in ss if s["class"] != "ramp"]
        for r in ramps:
            R = shapely.LineString([q[:2] for q in r["pts"]])
            for c in cws:
                Cl = shapely.LineString([q[:2] for q in c["pts"]])
                x = R.intersection(Cl).difference(p.buffer(0.05))
                for q in getattr(x, "geoms", [x]) if not x.is_empty else []:
                    q = q.representative_point()
                    hr = float(np.interp(R.project(q), _chain(r), [v[2] for v in r["pts"]]))
                    hc = float(np.interp(Cl.project(q), _chain(c), [v[2] for v in c["pts"]]))
                    if abs(hr - hc) < 1.0:          # in one level (a ramp passing over or under elsewhere is fine)
                        bad.append(f"съезд {r['id']} касается проезжей части {c['id']} в {q.distance(p):.1f} м от узла "
                                   f"{nid} ({nodes[nid]['kind']})")
                for v in r["pts"]:
                    dn = p.distance(shapely.Point(v[:2]))
                    if 3.0 <= dn <= 30.0:
                        slope = min(slope, Cl.distance(shapely.Point(v[:2])) / dn)
    return bad, slope


def run_case(case, spec, out, tmp):
    import gen_network
    import validate_map
    path = os.path.join(tmp, f"tpl_{case}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    t0 = time.time()
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen_network.main([path, "--out", out, "--no-village"])
        rc = validate_map.main([path, "--out", out, "--rules", "0,5,6,7,8,9,10,11"])
    rep = json.load(open(os.path.join(out, f"tpl_{case}", "report.json"), encoding="utf-8"))
    net = json.load(open(os.path.join(out, f"tpl_{case}", "network.json"), encoding="utf-8"))
    return rc, rep, net, time.time() - t0


def section_chain(net):
    """[x, z, y] polyline for the long-section: the highest structure (overpass / bridge) and the segments that continue
    it at both ends (same street, else same class, leaving / entering in the direction of travel); for an at-grade
    template the minor street."""
    segs = net["segments"]
    out_of, into = {}, {}
    for k, s in enumerate(segs):
        out_of.setdefault(s["a"], []).append(k)
        into.setdefault(s["b"], []).append(k)
    cand = [k for k, s in enumerate(segs) if any(r["kind"] in ("overpass", "bridge") for r in s["struct"])]
    if not cand:
        cand = [k for k, s in enumerate(segs) if s.get("street") == "m"]
    if not cand:
        return np.zeros((0, 3)), ""
    seed = max(cand, key=lambda k: max(p[2] for p in segs[k]["pts"]))

    def pick(ks, ref):
        ks = [k for k in ks if k not in used]
        same = [k for k in ks if ref.get("street") and segs[k].get("street") == ref.get("street")] or \
               [k for k in ks if segs[k]["class"] == ref["class"]]
        return same[0] if len(same) == 1 else None

    used = {seed}
    chain = [seed]
    for _ in range(60):                                   # forward
        k = pick(out_of.get(segs[chain[-1]]["b"], []), segs[chain[-1]])
        if k is None:
            break
        used.add(k)
        chain.append(k)
    for _ in range(60):                                   # backward
        k = pick(into.get(segs[chain[0]]["a"], []), segs[chain[0]])
        if k is None:
            break
        used.add(k)
        chain.insert(0, k)
    pts = list(segs[chain[0]]["pts"])
    for k in chain[1:]:
        pts += segs[k]["pts"][1:]
    s0 = segs[seed]
    return np.array(pts, float), (s0.get("street") or s0["class"])


COL = {"expressway": "#c0392b", "arterial_regulated": "#e67e22", "district_transport": "#d4ac0d", "local": "#7f8c8d",
       "ramp": "#8e44ad"}


def draw_sheet(results, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(results)
    rows = (n + 1) // 2
    fig, axs = plt.subplots(rows, 4, figsize=(22, 5.2 * rows), gridspec_kw={"width_ratios": [1, 1.4, 1, 1.4]})
    axs = np.atleast_2d(axs)
    for k, (case, tmpl, cmaj, cmin, rc, rep, net) in enumerate(results):
        ax, sx = axs[k // 2, 2 * (k % 2)], axs[k // 2, 2 * (k % 2) + 1]
        x0, z0 = C
        for s in net["segments"]:
            P = np.array(s["pts"], float)
            ax.plot(P[:, 0] - x0, P[:, 1] - z0, color=COL.get(s["class"], "#555"),
                    lw=1.6 if s["class"] != "ramp" else 1.0, zorder=2)
            S = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])
            for r in s["struct"]:
                if r["kind"] in ("overpass", "bridge"):
                    m = (S >= r["from_m"] - 0.5) & (S <= r["to_m"] + 0.5)
                    if m.sum() >= 2:
                        ax.plot(P[m, 0] - x0, P[m, 1] - z0, color="black", lw=4, zorder=1)
        ax.set_aspect("equal")
        ax.set_xlim(-650, 650)
        ax.set_ylim(-650, 650)
        ax.tick_params(labelsize=6)
        ne = rep["counts"]["error"]
        ax.set_title(f"{case}: {tmpl}, {cmaj} × {cmin}\nошибок {ne}, предупреждений {rep['counts']['warning']}",
                     fontsize=8.5, color="black" if ne == 0 else "red")
        # long-section through the highest structure and the roads it continues into
        P, what = section_chain(net)
        if len(P) >= 2:
            import shapely
            S = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])
            cls0 = next((s["class"] for s in net["segments"] if (s.get("street") or s["class"]) == what), "")
            sx.plot(S, P[:, 2], color=COL.get(cls0, "#333"), lw=1.4)
            L = shapely.LineString(P[:, :2])
            peak = float(S[int(np.argmax(P[:, 2]))])
            for s in net["segments"]:
                Q = np.array(s["pts"], float)
                q = shapely.LineString(Q[:, :2])
                if not L.intersects(q):
                    continue
                g = L.intersection(q)
                for g in getattr(g, "geoms", [g]):
                    if g.geom_type != "Point":
                        continue
                    sa = L.project(g)
                    ya = float(np.interp(sa, S, P[:, 2]))
                    SQ = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(Q[:, :2], axis=0).T))])
                    yb = float(np.interp(q.project(g), SQ, Q[:, 2]))
                    if ya - yb > 1.0:
                        sx.plot([sa - 6, sa + 6], [yb, yb], color=COL.get(s["class"], "#555"), lw=3)
                        sx.annotate(f"{ya - yb - 1.5:.1f}", (sa, yb), xytext=(0, -9), textcoords="offset points",
                                    fontsize=6, ha="center")
            sx.set_xlim(max(0.0, peak - 450), min(S[-1], peak + 450))
            sx.set_ylim(472, max(484, P[:, 2].max() + 2))
        sx.axhline(475.0, color="#2e7d32", lw=0.6, ls="--")
        sx.set_title(f"продольный профиль через путепровод: {what} (цифры — низ пролёта над дорогой под ним, норма ≥ 5,0 м)",
                     fontsize=7.5)
        sx.tick_params(labelsize=6)
        sx.set_xlabel("м по оси", fontsize=7)
        sx.set_ylabel("отметка, м", fontsize=7)
    for k in range(n, rows * 2):
        axs[k // 2, 2 * (k % 2)].axis("off")
        axs[k // 2, 2 * (k % 2) + 1].axis("off")
    fig.suptitle("Шаблоны развязок и пересечений (w43): план и продольный профиль; чёрная обводка — путепровод", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(path, dpi=90)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None)
    a = ap.parse_args(argv)
    base = os.path.join(a.out or paths.OUT, "_tools")
    out = os.path.join(base, "templates")
    os.makedirs(out, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    results = []
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for case, tmpl, cmaj, cmin, layout, params in CASES:
            if only and case not in only:
                continue
            spec = spec_for(case, tmpl, cmaj, cmin, layout, params)
            rc, rep, net, dt = run_case(case, spec, out, tmp)
            ne = rep["counts"]["error"]
            # a template that did not fit falls back to a plain overpass with an error in the network log: that is a
            # failure of the case unless the case expects exactly that refusal (REFUSE)
            gerr = [e["what"] for e in net.get("log", []) if e.get("error")]
            want = REFUSE.get(case)
            if want:
                hit = [g for g in gerr if want in g]
                fail = ne > 0 or not hit
                gerr = [] if hit else gerr + [f"ожидался отказ шаблона с «{want}»"]
            else:
                fail = ne > 0 or bool(gerr)
            if case in EXPECT:
                why = EXPECT[case](net)
                if why:
                    gerr.append(why)
                    fail = True
            tbad, tslope = tips(net)
            if tbad:
                gerr += tbad
                fail = True
            bad += fail
            ics = net["interchanges"]
            print(f"{'ERR' if fail else 'ok '} {case:20s} {tmpl:18s} {cmaj} × {cmin}: отрезков съездов "
                  f"{len(ics[0]['ramps']) if ics else 0}, отрезков с путепроводом {len(ics[0]['structures']) if ics else 0}, "
                  f"всего отрезков {len(net['segments'])}, ошибок {ne}, предупреждений {rep['counts']['warning']}, {dt:.1f} с"
                  + (f", отказ шаблона как ожидалось" if want and not gerr else "")
                  + (f", кончики съездов ≥ 1:{1.0 / tslope:.0f}" if 0 < tslope < float("inf") else ""))
            for g in gerr:
                print(f"      ! генератор: {g}")
            for i in rep["issues"]:
                if i["sev"] == "error":
                    print(f"      ! п.{i['rule']}: {i['what_ru']}")
            results.append((case, tmpl, cmaj, cmin, rc, rep, net))
    if results:
        draw_sheet(results, os.path.join(base, "templates.png"))
        print(f"→ {os.path.join(base, 'templates.png')}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
