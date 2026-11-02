"""Scheme picture of Growing-East (level 0): spec/growing_e.json → OUT/scheme.png. North up, Unity X/Z, Russian labels.
Called by growing_e_scheme.py draw; reuses tools/map/geo/render_maps.py helpers (scale bar, north arrow, line/poly packers)."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "geo"))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, PathPatch  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402

import frames  # noqa: E402
import layers  # noqa: E402
from render_maps import _lines, _polys, north_arrow, scale_bar  # noqa: E402

USE = {  # use: (colour, label)
    "mixed_centre": ("#d7301f", "центр (офисы, торговля, жильё)"),
    "business": ("#8c6bb1", "деловая зона, сервис (без жилья)"),
    "residential_high": ("#ef6548", "жильё 9–12 этажей (у ЛРТ)"),
    "residential_mid": ("#fc9272", "жильё 5–8 этажей"),
    "residential_low": ("#fdd9b5", "жильё 2–4 этажа"),
    "village_existing": ("#c9a77c", "существующие сёла и постройки"),
    "medical": ("#e7298a", "больничный городок"),
    "sport": ("#41ab5d", "спортпарк"),
    "park": ("#a1d99b", "парки, реки, защитная зелень"),
    "waterfront": ("#9ecae1", "набережная"),
    "campus": ("#bf812d", "кампус"),
    "industry": ("#969696", "промышленность"),
    "logistics": ("#b3b3d9", "логистика, склады (классы IV–V)"),
    "utility": ("#f0e68c", "энергетика, СЭС, полосы ЛЭП и ж/д"),
    "reserve": ("#f2f0eb", "резерв (сельхоз до освоения)"),
}
AX = {  # class: (colour, width px, label)
    "expressway": ("#7f0000", 11, "скоростная дорога А-3"),
    "trunk": ("#d7301f", 8, "магистраль городского значения"),
    "arterial": ("#ef6548", 5.5, "магистральная улица"),
    "boulevard": ("#238b45", 6, "бульвар с ЛРТ по оси"),
    "district": ("#525252", 3, "улица района / существующая улица"),
    "pedestrian": ("#41ab5d", 3, "пешеходная ось, набережная"),
}
LRT_C = "#c51b8a"
QUEUE_C = {1: "#2166ac", 2: "#4dac26", 3: "#f1a340", 4: "#b2182b"}


def zone_path(z):
    rings = [z["polygon"]] + (z.get("holes") or [])
    verts, codes = [], []
    for r in rings:
        r = np.asarray(r, float)
        verts.extend(r.tolist()); codes.extend([Path.MOVETO] + [Path.LINETO] * (len(r) - 2) + [Path.CLOSEPOLY])
    return Path(verts, codes)


def halo(w=4, c="white"):
    return [pe.withStroke(linewidth=w, foreground=c)]


def draw(spec, out_png):
    C = json.load(open(os.path.join(frames.SPEC_DIR, "city.json"), encoding="utf-8"))
    P = Polygon(C["districts"]["growing_e"]["polygon"])
    x0, z0, x1, z1 = -1600, -4700, 15400, 16400
    mpp = 4.9
    Wm, H = (x1 - x0) / mpp, (z1 - z0) / mpp
    SB = 880  # sidebar width, px: title, idea, legend, object list, queue inset
    W = Wm + SB
    fm = Wm / W  # map share of the figure width
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, fm, 1])
    ax.set_facecolor("#e9e9e6")
    clip = shapely.box(x0, z0, x1, z1)
    # terrain contours (10 m) for the feel of the ground
    import terrain
    T = terrain.terrain()
    xs = np.arange(x0, x1, 100.0); zs = np.arange(z0, z1, 100.0)
    X, Z = np.meshgrid(xs, zs); Hh = T.height(X, Z)
    ax.contour(X, Z, Hh, levels=np.arange(440, 700, 10), colors="#b7b2a6", linewidths=0.6, zorder=1, alpha=0.7)
    # neighbours, muted
    for k, nm in (("golden", "GOLDEN"), ("green", "GREEN"), ("growing_w", "GROWING-ЗАПАД")):
        g = Polygon(C["districts"][k]["polygon"]).buffer(0)
        ax.add_collection(PolyCollection(_polys([g]), facecolor="#f7f7f4", edgecolor="#9a9a9a", linewidths=1.5, zorder=0.5))
    for x, z, nm in ((-1150, 6000, "GROWING-\nЗАПАД"), (8200, 14600, "GREEN"), (-350, -4350, "GOLDEN")):
        ax.text(x, z, nm, fontsize=34, color="#9a9a9a", fontweight="bold", ha="center", va="center", zorder=2, rotation=90 if "ЗАПАД" in nm else 0)
    # zones
    for z in spec["zones"]:
        col = USE.get(z["use"], ("#ffffff", ""))[0]
        p = PathPatch(zone_path(z), facecolor=col, edgecolor="white", linewidth=0.5, zorder=3)
        ax.add_patch(p)
        if z["use"] == "reserve":
            p.set_hatch("//"); p.set_edgecolor("#d5d1c8")
        if z["use"] == "utility" and "СЭС" in z["name_ru"]:
            p.set_hatch("||"); p.set_edgecolor("#cdbb3c")
    # water
    wg, wp = layers.load("water")
    sel = shapely.intersects(clip, wg)
    ax.add_collection(PolyCollection(_polys([g for g, s in zip(wg, sel) if s and g.geom_type in ("Polygon", "MultiPolygon")]),
                                     facecolor="#6baed6", edgecolor="#2171b5", linewidths=0.5, zorder=4))
    ax.add_collection(LineCollection(_lines([g for g, s in zip(wg, sel) if s and "Line" in g.geom_type]), colors="#2171b5", linewidths=1.6, zorder=4))
    # existing context: roads (muted), rail, power
    rg, rp = layers.load("roads")
    sel = np.flatnonzero(shapely.intersects(clip, rg))
    keep = ("motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified")
    ax.add_collection(LineCollection(_lines([rg[i] for i in sel if rp[i].get("class") in keep]), colors="#8c8c8c", linewidths=0.6, zorder=5, alpha=0.8))
    rl, _ = layers.load("rail")
    s = shapely.intersects(clip, rl)
    ax.add_collection(LineCollection(_lines(rl[s]), colors="#252525", linewidths=2.6, zorder=6))
    ax.add_collection(LineCollection(_lines(rl[s]), colors="#ffffff", linewidths=1.2, linestyles=(0, (5, 5)), zorder=6.1))
    ig, ip = layers.load("infrastructure")
    ax.add_collection(LineCollection(_lines([g for g, p in zip(ig, ip) if p.get("class") == "power_line" and g.intersects(clip)]),
                                     colors="#6a51a3", linewidths=1.2, linestyles=(0, (10, 3, 2, 3)), zorder=6.2))
    # district outline
    ax.add_collection(LineCollection(_lines([P.exterior]), colors="#e0884f", linewidths=5, zorder=7))
    # airfield: runway, KTA, 10 km circle, approach
    af = next(a for a in C["height_limits"]["airfields"] if a["id"] == "zhetygen_mil")
    R = json.load(open(os.path.join(frames.SPEC_DIR, "registry.json"), encoding="utf-8"))
    rw = next(r for r in R["rows"] if r["id"] == "airfield_zhetygen")
    from shapely.geometry import shape
    ax.add_collection(PolyCollection(_polys([shape(rw["geom"])]), facecolor="#525252", edgecolor="k", zorder=8))
    ax.plot([af["x"]], [af["z"]], marker="^", ms=20, color="k", zorder=40)
    ax.text(af["x"] + 250, af["z"], "Военный аэродром Жетыген\n(ВПП 01/19, КТА)", fontsize=17, zorder=41, va="center", path_effects=halo())
    th = np.linspace(0, 2 * np.pi, 400)
    ax.plot(af["x"] + 10000 * np.cos(th), af["z"] + 10000 * np.sin(th), color="#252525", lw=1.6, ls=(0, (8, 6)), zorder=8.5)
    a10 = math.radians(-57)
    ax.text(af["x"] + 10000 * math.cos(a10), af["z"] + 10000 * math.sin(a10), "10 км от КТА: согласование всех объектов", fontsize=15,
            rotation=33, zorder=41, color="#252525", ha="center", va="bottom", rotation_mode="anchor", path_effects=halo())
    ap = Polygon(spec["checks"]["airfields"]["approach_runway01"]["polygon"])
    ax.add_patch(PathPatch(Path(np.asarray(ap.exterior.coords)), facecolor="none", edgecolor="#cb181d", hatch="xx", lw=2.2, zorder=9, alpha=0.8))
    c = ap.centroid
    ax.text(c.x - 600, c.y + 300, "зона подлёта ВПП 01\nбез застройки", fontsize=17, color="#cb181d", ha="center", zorder=41,
            fontweight="bold", path_effects=halo())
    # axes
    order = ["district", "pedestrian", "arterial", "boulevard", "trunk", "expressway"]
    for cls in order:
        for a in spec["axes"]:
            if a["class"] != cls:
                continue
            L = np.asarray(a["line"], float)
            col, w, _ = AX[cls]
            ls = (0, (2, 2)) if cls == "pedestrian" else "-"
            if a["status"] == "keep_existing" and cls != "expressway":
                ax.plot(L[:, 0], L[:, 1], color="white", lw=w + 3, zorder=10 + order.index(cls), solid_capstyle="round")
                ax.plot(L[:, 0], L[:, 1], color=col, lw=w, zorder=10.1 + order.index(cls), ls=(0, (6, 3)))
            else:
                ax.plot(L[:, 0], L[:, 1], color="white", lw=w + 3, zorder=10 + order.index(cls), solid_capstyle="round")
                ax.plot(L[:, 0], L[:, 1], color=col, lw=w, zorder=10.1 + order.index(cls), ls=ls, solid_capstyle="round")
    # axis names (a few)
    names = {"ax_central": "Центральная магистраль", "ax_south": "Южная промышленная магистраль", "ax_east_n": "Восточная магистраль (обход Жетыгена)",
             "ax_east_s": "Восточная магистраль", "ax_lrt_blvd": "Бульвар Growing + ЛРТ", "ax_a3": "А-3 Алматы – Қонаев",
             "ax_n48": "развязка км ≈ 48 (новая)", "ax_n50": "развязка км ≈ 50,5 (новая)"}
    for a in spec["axes"]:
        if a["id"] not in names:
            continue
        L = LineString(a["line"])
        fr = {"ax_a3": 0.86, "ax_lrt_blvd": 0.5, "ax_central": 0.72, "ax_south": 0.77, "ax_east_n": 0.3, "ax_east_s": 0.25,
              "ax_n48": 0.14, "ax_n50": 0.16}.get(a["id"], 0.5)
        p = L.interpolate(fr, normalized=True); q = L.interpolate(min(1, fr + 0.02), normalized=True)
        ang = math.degrees(math.atan2(q.y - p.y, q.x - p.x))
        if ang > 90: ang -= 180
        if ang < -90: ang += 180
        ax.text(p.x, p.y, names[a["id"]], fontsize=16, rotation=ang, ha="center", va="center", zorder=45, fontweight="bold",
                color=AX[a["class"]][0], rotation_mode="anchor", path_effects=halo(5))
    # LRT
    lrt = spec["lrt"]
    L = np.asarray(lrt["line"], float)
    ax.plot(L[:, 0], L[:, 1], color="white", lw=8, zorder=20)
    ax.plot(L[:, 0], L[:, 1], color=LRT_C, lw=4.5, zorder=20.1)
    B = np.asarray(lrt["west_branch"], float)
    ax.plot(B[:, 0], B[:, 1], color=LRT_C, lw=4, ls=(0, (4, 2)), zorder=20.1)
    for st in lrt["stations"]:
        ax.plot(st["x"], st["z"], "o", ms=13, mfc="white", mec=LRT_C, mew=3, zorder=21)
        ax.text(st["x"] - 120, st["z"], st["name_ru"], fontsize=12, color=LRT_C, ha="right", va="center", zorder=42, path_effects=halo(3))
    # joints (the ones that matter)
    J = {j["id"]: j for j in C["joints"]["items"]}
    for jid in ("J027", "J046", "J062", "J072", "J104", "J123", "J028", "J047", "J063", "J082", "J085"):
        j = J[jid]
        ax.plot(j["x"], j["z"], marker="D", ms=13, mfc="#ffeb3b", mec="k", mew=1.5, zorder=43)
        ax.text(j["x"] + 110, j["z"] - 170, jid, fontsize=12, zorder=43, path_effects=halo(3))
    # centres
    for cdef in spec["centres"]:
        k = cdef["kind"]
        ms = {"main": 46, "sub": 30, "local": 18}[k]
        mk = {"main": "*", "sub": "o", "local": "o"}[k]
        ax.plot(cdef["x"], cdef["z"], marker=mk, ms=ms, mfc="#ffd92f" if k != "local" else "white", mec="k", mew=2.2, zorder=46)
        fs = {"main": 30, "sub": 22, "local": 15}[k]
        dx = {"c_main": -300, "c_zhetygen": 350, "c_zhanaarna": 380}.get(cdef["id"], 220)
        dz = {"c_main": 230, "c_zhanaarna": -330}.get(cdef["id"], 0)
        ax.text(cdef["x"] + dx, cdef["z"] + dz, cdef["name_ru"], fontsize=fs, fontweight="bold" if k != "local" else "normal",
                ha="right" if dx < 0 else "left", va="center", zorder=47, path_effects=halo(6 if k == "main" else 4))
    # objects: numbered; arrows for moves
    objs = [o for o in spec["objects"] if o["to"] is not None and o["action"] != "remove"]
    num = {}
    for i, o in enumerate(objs, 1):
        num[o["registry_id"]] = i
    placed = []
    for o in objs:
        i = num[o["registry_id"]]
        tx, tz = o["to"]
        if not (x0 < tx < x1 and z0 < tz < z1):
            continue
        # avoid stacking identical points (several Zhetygen rows share the settlement point)
        k = sum(1 for p in placed if abs(p[0] - tx) < 60 and abs(p[1] - tz) < 60)
        ox, oz = (k % 4) * 170, -(k // 4) * 170
        placed.append((tx, tz))
        col = {"move": "#08519c", "add": "#006d2c", "by_rule": "#7a0177", "keep": "#252525"}.get(o["action"], "#252525")
        ax.plot(tx + ox, tz + oz, "o", ms=17, mfc="white", mec=col, mew=2.4, zorder=50)
        ax.text(tx + ox, tz + oz, str(i), fontsize=10, ha="center", va="center", zorder=51, color=col, fontweight="bold")
        if o["action"] in ("move", "by_rule") and o.get("from") and math.hypot(o["from"][0] - tx, o["from"][1] - tz) > 200:
            fx, fz = o["from"]
            ax.plot(fx, fz, "o", ms=13, mfc="#d9d9d9", mec="#636363", mew=1.5, zorder=49)
            ax.annotate("", xy=(tx, tz), xytext=(fx, fz), zorder=48,
                        arrowprops=dict(arrowstyle="-|>,head_length=1.2,head_width=0.6", lw=2.6, color="#08519c", ls="--", shrinkA=6, shrinkB=14))
    # PepsiCo leaves for Gate
    pep = next((o for o in spec["objects"] if o["registry_id"] == "pepsico"), None)
    if pep and pep.get("from"):
        fx, fz = pep["from"]
        ax.plot(fx, fz, "o", ms=13, mfc="#d9d9d9", mec="#636363", mew=1.5, zorder=49)
        ax.annotate("PepsiCo → в Gate", xy=(fx - 1500, fz - 1600), xytext=(fx, fz), fontsize=15, zorder=48, color="#08519c",
                    arrowprops=dict(arrowstyle="-|>", lw=2.6, color="#08519c", ls="--"), path_effects=halo(4))
    # ---- sidebar (right): title, idea, legend, objects, build queues
    sx = fm + 12 / W  # left edge of the sidebar, figure fraction
    fig.text(sx, 1 - 30 / H, "GROWING-ВОСТОК", fontsize=44, fontweight="bold", va="top")
    fig.text(sx, 1 - 100 / H, "схема района · уровень 0 · v0", fontsize=24, va="top", color="#444")
    t = spec["targets"]
    fig.text(sx + 16 / W, 1 - 160 / H,
             "Жить — на западе: у А-3, вдоль ЛРТ\nи Малой Алматинки.\n"
             "Работать — на востоке, за Турксибом.\n"
             "Три магистрали запад–восток сшивают\nрайон; сёла остаются со своими улицами.\n"
             f"2050: {t['population_2050'] / 1000:.0f} тыс. жителей ·\n{t['jobs_2050'] / 1000:.0f} тыс. рабочих мест · 15 566 га",
             fontsize=17, va="top", linespacing=1.35, bbox=dict(facecolor="#f4f4f1", edgecolor="#ccc", pad=10))
    h = [Patch(facecolor=USE[u][0], edgecolor="#777", label=USE[u][1]) for u in
         ("mixed_centre", "business", "residential_high", "residential_mid", "residential_low", "village_existing", "medical", "sport",
          "park", "industry", "logistics", "utility", "reserve")]
    h[-1].set_hatch("//")
    h += [Line2D([], [], color=AX[c][0], lw=AX[c][1] * 0.8, label=AX[c][2], ls=(0, (2, 2)) if c == "pedestrian" else "-")
          for c in ("expressway", "trunk", "arterial", "boulevard", "district", "pedestrian")]
    h += [Line2D([], [], color="#525252", lw=3, ls=(0, (6, 3)), label="существующая дорога (сохраняется)"),
          Line2D([], [], color=LRT_C, lw=4.5, marker="o", mfc="white", mec=LRT_C, ms=10, label="ЛРТ и станции (пунктир — ветка)"),
          Line2D([], [], color="#252525", lw=3, label="железная дорога (OSM)"),
          Line2D([], [], color="#6a51a3", lw=1.5, ls=(0, (10, 3, 2, 3)), label="ЛЭП 220 кВ (OSM)"),
          Patch(facecolor="#6baed6", edgecolor="#2171b5", label="вода (OSM)"),
          Patch(facecolor="none", edgecolor="#cb181d", hatch="xx", label="зона подлёта аэродрома"),
          Line2D([], [], ls="", marker="*", ms=26, mfc="#ffd92f", mec="k", label="главный центр"),
          Line2D([], [], ls="", marker="o", ms=18, mfc="#ffd92f", mec="k", label="подцентр"),
          Line2D([], [], ls="", marker="o", ms=12, mfc="white", mec="k", label="местный центр"),
          Line2D([], [], ls="", marker="D", ms=11, mfc="#ffeb3b", mec="k", label="стык с соседом (city.json)"),
          Line2D([], [], ls="", marker="o", ms=13, mfc="white", mec="#08519c", mew=2.4, label="объект реестра: перенесён"),
          Line2D([], [], ls="", marker="o", ms=13, mfc="white", mec="#7a0177", mew=2.4, label="   по правилу (модель qTwin)"),
          Line2D([], [], ls="", marker="o", ms=13, mfc="white", mec="#006d2c", mew=2.4, label="   добавлен"),
          Line2D([], [], ls="", marker="o", ms=13, mfc="white", mec="#252525", mew=2.4, label="   как есть"),
          Line2D([], [], color="#08519c", lw=2.6, ls="--", label="перенос: откуда → куда")]
    leg = fig.legend(handles=h, loc="upper left", fontsize=16, framealpha=1, borderpad=0.8, handlelength=3.0, labelspacing=0.5,
                     title="Условные обозначения", title_fontsize=19, bbox_to_anchor=(sx - 4 / W, 1 - 470 / H), alignment="left")
    # objects list (numbers), two columns
    lines_txt = []
    for o in objs:
        i = num[o["registry_id"]]
        nm = o["name_ru"].split("(")[0].strip()
        nm = nm if len(nm) <= 30 else nm[:29] + "…"
        lines_txt.append(f"{i:>2} {nm}")
    half = (len(lines_txt) + 1) // 2
    ytop = 1 - 1880 / H
    fig.text(sx, ytop, "Объекты реестра (номера на карте)", fontsize=18, fontweight="bold", va="top")
    for k, chunk in enumerate((lines_txt[:half], lines_txt[half:])):
        fig.text(sx + k * 430 / W, ytop - 40 / H, "\n".join(chunk), fontsize=12, family="DejaVu Sans Mono", va="top", linespacing=1.25)
    # queue inset (bottom of the sidebar)
    iw = SB - 30
    ih = iw * (20300 / 16200)
    ia = fig.add_axes([sx, 12 / H, iw / W, ih / H])
    ia.set_facecolor("white")
    zq = {}
    for ph in spec["phases"]:
        for zid in ph["zones"]:
            zq[zid] = ph["queue"]
    for z in spec["zones"]:
        base = z["id"]
        q = zq.get(base) or zq.get(base.rsplit("_", 1)[0]) if base not in zq else zq[base]
        col = QUEUE_C.get(q, "#f0f0f0") if z["use"] not in ("village_existing",) else "#c9a77c"
        ia.add_patch(PathPatch(zone_path(z), facecolor=col, edgecolor="none", alpha=0.85 if q else 1))
    for ph in spec["phases"]:
        for aid in ph["axes"]:
            a = next((a for a in spec["axes"] if a["id"] == aid), None)
            if a:
                L = np.asarray(a["line"], float)
                ia.plot(L[:, 0], L[:, 1], color=QUEUE_C[ph["queue"]], lw=2.2)
                ia.plot(L[:, 0], L[:, 1], color="k", lw=0.5)
    ia.add_collection(LineCollection(_lines([P.exterior]), colors="#e0884f", linewidths=1.5))
    ia.set_xlim(-1200, 15000); ia.set_ylim(-4300, 16000); ia.set_aspect("equal"); ia.set_xticks([]); ia.set_yticks([])
    hq = [Patch(facecolor=QUEUE_C[ph["queue"]], label=f"{ph['queue']}: {ph['years'][0]}–{ph['years'][1]}") for ph in spec["phases"]]
    ia.legend(handles=hq, loc="upper right", fontsize=15, title="Очереди строительства", title_fontsize=17, framealpha=0.95)
    # scale bar, north, attribution
    scale_bar(ax, 300, -4400, 2000, "2 км", lw=12)
    north_arrow(ax, 13900, 9300, 700)
    ax.text(x0 + 200, z0 + 60, "© OpenStreetMap contributors, Overture Maps Foundation · рельеф двойника (горизонтали 10 м) · "
            "система Unity X/Z · всё без источника — модель qTwin", fontsize=12, zorder=60, va="bottom",
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"))
    ax.set_xlim(x0, x1); ax.set_ylim(z0, z1); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    tmp = out_png + ".tmp.png"
    fig.savefig(tmp, dpi=100)
    plt.close(fig)
    os.replace(tmp, out_png)
    print(f"[draw] {out_png}: {round(W)} × {round(H)} px, {os.path.getsize(out_png) / 1e6:.1f} MB")


def main(spec_path, outdir):
    spec = json.load(open(spec_path, encoding="utf-8"))
    draw(spec, os.path.join(outdir, "scheme.png"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(frames.SPEC_DIR, "growing_e.json"),
         sys.argv[2] if len(sys.argv) > 2 else "/mnt/project-files/alatau_stage7/level0/schemes/growing_e")
