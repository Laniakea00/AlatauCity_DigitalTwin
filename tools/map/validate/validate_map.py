"""Map validator (CONTRACT §5), core by w43.

    python3 tools/map/validate/validate_map.py <district | spec.json> [--out OUT] [--rules 1,5,7]

Loads every rule module in validate/rules/*.py (each exposes RULES = [{"no", "key", "fn", "needs"}]), runs the rules
on one context and writes OUT/<d>/report.json, report.md (Russian, one line per issue) and report.png (the network
coloured by class, structures highlighted, every issue as a numbered red marker with a legend in Russian).
Exit code 0 only when there is no `error` issue. A rule whose input file is missing gives one `warning` «нет файла».
After the summary line the log has one timing line per rule (and the files and context), as report.json rules[].s.
"""
import argparse
import glob
import importlib.util
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
sys.path.insert(0, MAP)
sys.path.insert(0, HERE)
from lib import jio, paths  # noqa: E402
import context  # noqa: E402

SEV_RU = {"error": "ошибка", "warning": "предупреждение", "wait_neighbour": "ждёт соседа", "info": "сведения"}


def load_rules():
    rules = []
    for f in sorted(glob.glob(os.path.join(HERE, "rules", "*.py"))):
        name = os.path.splitext(os.path.basename(f))[0]
        if name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"qtwin_rules_{name}", f)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:      # a broken rule file must not stop the others
            rules.append({"no": 0, "key": f"load:{name}", "fn": None, "needs": [], "module": name, "load_error": repr(e)})
            continue
        for r in getattr(mod, "RULES", []):
            r = dict(r)
            r["module"] = name
            rules.append(r)
    return rules


def run(ctx, rules, only=None):
    issues = []
    ran = []
    for r in sorted(rules, key=lambda r: (r["no"], r["key"])):
        if only and r["no"] not in only:
            continue
        t0 = time.time()
        if r.get("load_error"):
            issues.append(ctx.issue(0, "error", *_centre(ctx), f"файл правил {r['module']} не загружается: {r['load_error']}"))
            continue
        missing = [n for n in r.get("needs", []) if getattr(ctx, n, None) is None]
        if missing:
            issues.append(ctx.issue(r["no"], "warning", *_centre(ctx),
                                    f"правило {r['no']} ({r['key']}): нет файла " + ", ".join(context.FILES.get(m, m) for m in missing)))
            ran.append({"no": r["no"], "key": r["key"], "module": r["module"], "skipped": True})
            continue
        try:
            out = r["fn"](ctx) or []
        except Exception:
            tb = traceback.format_exc(limit=3)
            out = [ctx.issue(r["no"], "error", *_centre(ctx), f"правило {r['no']} ({r['key']}) упало: {tb.splitlines()[-1]}")]
        for i in out:
            i.setdefault("rule", r["no"])
            i.setdefault("lv", 0)
            i.setdefault("ids", [])
        issues.extend(out)
        ran.append({"no": r["no"], "key": r["key"], "module": r["module"], "issues": len(out),
                    "s": round(time.time() - t0, 2)})
    for k, i in enumerate(issues):
        i["n"] = k + 1
    return issues, ran


def _centre(ctx):
    c = ctx.area.centroid
    return c.x, c.y


def write_md(ctx, issues, ran, path):
    lines = [f"# Проверка карты · {ctx.d}", ""]
    ne = sum(1 for i in issues if i["sev"] == "error")
    nw = sum(1 for i in issues if i["sev"] != "error")
    lines.append(f"Ошибок: {ne}, предупреждений и прочего: {nw}. Правил запущено: {len(ran)}.")
    lines.append("")
    for i in issues:
        r = ctx.rule(i["rule"])
        title = r["text_ru"] if r else "совместимость"
        lines.append(f"{i['n']}. [{SEV_RU.get(i['sev'], i['sev'])}] правило {i['rule']} ({title}): {i['what_ru']} "
                     f"— x {i['x']:.0f}, z {i['z']:.0f}" + (f", уровень {i['lv']}" if i.get("lv") else "")
                     + (f"; {', '.join(map(str, i['ids'][:6]))}" if i.get("ids") else ""))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


CLASS_COLOR = {"expressway": "#c0392b", "arterial_continuous": "#d35400", "arterial_road_regulated": "#e67e22",
               "arterial_regulated": "#e67e22", "district_transport": "#f1c40f", "district_pedestrian": "#f39c12",
               "local": "#7f8c8d", "local_secondary": "#95a5a6", "industrial": "#8e6e53", "park_road": "#27ae60",
               "driveway_main": "#bdc3c7", "driveway_secondary": "#d5d8dc", "village_main": "#a1887f",
               "village_secondary": "#bcaaa4", "village_lane": "#d7ccc8", "pedestrian_street": "#2e86c1",
               "boulevard": "#1abc9c", "bike_path": "#16a085", "ramp": "#8e44ad"}


def draw(ctx, issues, path, title=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    net = ctx.network or {"segments": [], "nodes": []}
    fig = plt.figure(figsize=(20, 13))
    ax = fig.add_axes([0.01, 0.02, 0.62, 0.94])
    lg = fig.add_axes([0.64, 0.02, 0.35, 0.94])
    lg.axis("off")
    x0, z0, x1, z1 = ctx.area.bounds
    ax.plot(*ctx.area.exterior.xy, color="#999", lw=0.8, ls="--")
    import numpy as np
    from matplotlib.collections import LineCollection
    used = set()
    roads, spans = {}, {}            # one LineCollection per style: one artist per segment is slow on a district
    for s in net["segments"]:
        P = np.array(s["pts"], float)
        c = CLASS_COLOR.get(s["class"], "#555")
        used.add(s["class"])
        w = {"expressway": 2.2, "ramp": 1.2}.get(s["class"], 1.0)
        roads.setdefault((c, w), []).append(P[:, :2])
        # structures: overpass / bridge spans in black under the road colour, tunnels dashed
        S = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])
        for r in s["struct"]:
            if r["kind"] in ("overpass", "bridge", "tunnel"):
                m = (S >= r["from_m"] - 0.5) & (S <= r["to_m"] + 0.5)
                if m.sum() >= 2:
                    spans.setdefault((w + 3, "--" if r["kind"] == "tunnel" else "-"), []).append(P[m, :2])
    for (c, w), segs in roads.items():
        ax.add_collection(LineCollection(segs, colors=c, linewidths=w, zorder=2, capstyle="projecting",
                                         joinstyle="round"))
    for (w, ls), segs in spans.items():
        ax.add_collection(LineCollection(segs, colors="black", linewidths=w, linestyles=ls, zorder=1,
                                         capstyle="projecting", joinstyle="round"))
    if ctx.lrt:
        for ln in ctx.lrt.get("lines", []):
            P = [p[:2] for p in ln["pts"]]
            ax.plot([p[0] for p in P], [p[1] for p in P], color="#2980b9", lw=2.5, alpha=0.6, zorder=3)
            for st in ln.get("stations", []):
                ax.plot(st["x"], st["z"], "s", color="#2980b9", ms=6, zorder=4)
    # issue markers and their numbers: one artist per colour (a Line2D of markers, a PathCollection of the number
    # glyphs centred on each issue), not two artists per issue — thousands of them on a district
    from matplotlib.collections import PathCollection
    from matplotlib.font_manager import FontProperties
    from matplotlib.path import Path
    from matplotlib.textpath import TextPath
    from matplotlib.transforms import Affine2D
    fp = FontProperties(size=6.5, weight="bold")
    digit = {ch: TextPath((0, 0), ch, prop=fp) for ch in "0123456789"}       # the font's digits are all one width
    adv = float(TextPath((0, 0), "00", prop=fp).vertices[:, 0].max() - digit["0"].vertices[:, 0].max())

    def number(t):
        p = Path.make_compound_path(*[digit[ch].transformed(Affine2D().translate(k * adv, 0.0)) for k, ch in enumerate(t)])
        v = p.vertices[p.codes != Path.CLOSEPOLY]
        return p.transformed(Affine2D().translate(-(v[:, 0].min() + v[:, 0].max()) / 2.0,
                                                  -(v[:, 1].min() + v[:, 1].max()) / 2.0))
    by_col = {"#7f8c8d": [], "#e67e22": [], "red": []}         # errors drawn last, on top
    for i in issues:
        col = "red" if i["sev"] == "error" else ("#e67e22" if i["sev"] == "warning" else "#7f8c8d")
        by_col[col].append(i)
    for col, its in by_col.items():
        if not its:
            continue
        ax.plot([i["x"] for i in its], [i["z"] for i in its], "o", ls="none", ms=11, mfc="white", mec=col, mew=2,
                zorder=5)
        paths = [number(str(i["n"])) for i in its]
        ax.add_collection(PathCollection(paths, offsets=[(i["x"], i["z"]) for i in its], offset_transform=ax.transData,
                                         transform=Affine2D().scale(1.0 / 72.0) + fig.dpi_scale_trans, facecolors=col,
                                         edgecolors="none", zorder=6))
    ax.set_xlim(x0 - 50, x1 + 50)
    ax.set_ylim(z0 - 50, z1 + 50)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ne = sum(1 for i in issues if i["sev"] == "error")
    ax.set_title(title or f"{ctx.d}: сеть по классам, сооружения — чёрная обводка; ошибок {ne}, "
                 f"прочих замечаний {len(issues) - ne}", fontsize=11)
    handles = [Line2D([0], [0], color=CLASS_COLOR.get(c, "#555"), lw=2, label=c) for c in sorted(used)]
    handles.append(Line2D([0], [0], color="black", lw=4, label="путепровод / мост"))
    handles.append(Line2D([0], [0], marker="o", color="w", mec="red", mew=2, ms=9, label="ошибка (номер)"))
    handles.append(Line2D([0], [0], marker="o", color="w", mec="#e67e22", mew=2, ms=9, label="предупреждение"))
    ax.legend(handles=handles, loc="lower left", fontsize=7, ncol=2, framealpha=0.85)
    # legend text in Russian: the issues (first 70, grouped lines when longer)
    rows = []
    for i in issues[:70]:
        rows.append(f"{i['n']:>3}. {'●' if i['sev'] == 'error' else '○'} п.{i['rule']}: {i['what_ru']}")
    if len(issues) > 70:
        rows.append(f"… и ещё {len(issues) - 70} (report.md)")
    import textwrap
    wrapped = []
    for r in rows:
        wrapped.extend(textwrap.wrap(r, 92, subsequent_indent="       ") or [r])
    lg.text(0.0, 1.0, "\n".join(wrapped[:150]), va="top", ha="left", fontsize=6.6, family="DejaVu Sans")
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="map validator")
    ap.add_argument("district")
    ap.add_argument("--out", default=None)
    ap.add_argument("--rules", default=None, help="comma-separated rule numbers")
    ap.add_argument("--no-png", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    ctx = context.build(a.district, a.out)
    t_ctx = time.time() - t0
    only = {int(x) for x in a.rules.split(",")} if a.rules else None
    rules = load_rules()
    issues, ran = run(ctx, rules, only)
    t_rep = time.time()
    d_out = paths.out_dir(ctx.d, a.out)
    rep = {"schema": "qtwin.report/1", "district": ctx.d, "made": time.strftime("%Y-%m-%d %H:%M:%S"),
           "rules": ran, "counts": {s: sum(1 for i in issues if i["sev"] == s) for s in SEV_RU},
           "issues": issues}
    jio.save_json(rep, os.path.join(d_out, "report.json"), indent=1)
    write_md(ctx, issues, ran, os.path.join(d_out, "report.md"))
    if not a.no_png:
        draw(ctx, issues, os.path.join(d_out, "report.png"))
    ne = rep["counts"]["error"]
    print(f"validate_map {ctx.d}: правил {len(ran)}, ошибок {ne}, предупреждений {rep['counts']['warning']}, "
          f"ждёт соседа {rep['counts']['wait_neighbour']}, {time.time() - t0:.1f} с → {d_out}/report.*")
    # one timing line per rule (report.json rules[].s): the slow rule of a large district shows in the run log
    print(f"  время: файлы и контекст {t_ctx:.1f} с, отчёт {time.time() - t_rep:.1f} с")
    for r in ran:
        print(f"  время п.{r['no']} {r['key']}: " + ("пропущено (нет файла)" if r.get("skipped") else f"{r['s']:.1f} с, замечаний {r['issues']}"))
    return 0 if ne == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
