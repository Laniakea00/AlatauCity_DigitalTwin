"""Drawing of the Golden scheme (called by golden_scheme.py): north up, Russian legend, scale bar, ~4300 px wide."""
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
from matplotlib.colors import LightSource  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Patch  # noqa: E402

import render_maps as RM  # noqa: E402
import terrain  # noqa: E402

USE_STYLE = {   # use: (fill, label)
    "mixed_centre": ("#d7301f", "центр: торговля, офисы, жильё"),
    "business": ("#8c6bb1", "технологический коридор, офисы"),
    "residential_high": ("#f16913", "жильё 9–12 этажей у станций"),
    "residential_mid": ("#fdae6b", "жильё 5–8 этажей"),
    "residential_low": ("#fee6ce", "жильё 2–4 этажа"),
    "village_existing": ("#bfa58a", "существующие посёлки и дачи"),
    "campus": ("#3182bd", "кампусы вузов"),
    "medical": ("#e7298a", "медкластер"),
    "industry": ("#636363", "промышленность"),
    "logistics": ("#9e9ac8", "склады, агропереработка, цеха"),
    "utility": ("#737373", "инженерные объекты"),
    "park": ("#74c476", "парки, речные коридоры, лесопарк"),
    "waterfront": ("#9ecae1", "вода и водоохранная полоса"),
    "sport": ("#41ab5d", "спорт, ипподром"),
    "reserve": ("#efefe6", "резерв после 2050"),
}
AXIS_STYLE = {  # class: (colour, width pt, dash, label)
    "expressway": ("#1a1a1a", 9.0, None, "скоростная дорога"),
    "trunk": ("#b30000", 6.5, None, "магистраль города"),
    "arterial": ("#e34a33", 4.5, None, "магистраль района"),
    "district": ("#7f2704", 2.8, None, "главная улица района"),
    "boulevard": ("#006d2c", 3.6, (0, (5, 2)), "бульвар"),
    "pedestrian": ("#238b45", 2.4, (0, (1.5, 1.5)), "пешеходно-велосипедная ось"),
    "lrt_corridor": ("#c51b8a", 3.2, (0, (3, 3)), "коридор 2-й линии ЛРТ (резерв)"),
}


def _polys(g):
    return [np.asarray(p.exterior.coords) for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and not p.is_empty]


def _holes(g):
    return [np.asarray(r.coords) for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" for r in p.interiors]


def draw(spec, I, built, out_dir):
    from golden_scheme import GOLD, ZONES, AXES, LRT_LINE, LRT_STATIONS, CENTRES, OBJECTS, PHASES, A3_INTERCHANGES, CITY
    os.makedirs(out_dir, exist_ok=True)
    x0, z0, x1, z1 = -19300, -16900, 3700, 1900
    mpp = 5.4
    W, H = (x1 - x0) / mpp, (z1 - z0) / mpp
    dpi = 100
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#f4f2ec")
    # terrain shading
    T = terrain.terrain()
    xs = np.arange(x0, x1, 50.0); zs = np.arange(z0, z1, 50.0)
    X, Z = np.meshgrid(xs, zs)
    Hh = T.height(X, Z)
    ls = LightSource(azdeg=315, altdeg=40)
    shade = ls.hillshade(Hh, vert_exag=6, dx=50, dy=50)
    ax.imshow(shade, origin="lower", extent=(x0, x1, z0, z1), cmap="gray", alpha=0.22, zorder=0, vmin=0, vmax=1)
    cs = ax.contour(X, Z, Hh, levels=np.arange(500, 700, 25), colors="#8a7f6a", linewidths=0.6, alpha=0.45, zorder=0.5)
    ax.clabel(cs, levels=np.arange(500, 700, 50), fontsize=13, fmt="%d м", inline=True)
    # zones
    order = ["reserve", "park", "waterfront", "village_existing", "residential_low", "residential_mid", "residential_high", "logistics",
             "industry", "utility", "business", "sport", "campus", "medical", "mixed_centre"]
    zs_by = {}
    for z in ZONES:
        zs_by.setdefault(z["use"], []).append(built[z["id"]])
    for u in order:
        for g in zs_by.get(u, []):
            col = USE_STYLE[u][0]
            ax.add_collection(PolyCollection(_polys(g), facecolor=col, edgecolor="white" if u != "reserve" else "#d9d6c8",
                                             linewidths=0.8, alpha=0.92 if u not in ("reserve",) else 1.0, zorder=2))
            if u == "village_existing":
                ax.add_collection(PolyCollection(_polys(g), facecolor="none", edgecolor="#7a5c3e", hatch="....", linewidths=0.0, zorder=2.1))
    # water polygons on top of zones (exact)
    ax.add_collection(PolyCollection(_polys(I["water_polys"]), facecolor="#6baed6", edgecolor="#2171b5", linewidths=0.6, zorder=3))
    for wl in I["water_lines"]:
        for q in getattr(wl, "geoms", [wl]):
            if q.geom_type == "LineString":
                ax.plot(*q.xy, color="#2171b5", lw=1.6, zorder=3.1, solid_capstyle="round")
    # existing roads (muted), rail, power
    segs = [np.asarray(g.coords) for g, c in I["roads"] for g in getattr(g, "geoms", [g]) if c in ("trunk", "primary", "secondary", "tertiary", "residential", "unclassified")]
    ax.add_collection(LineCollection(segs, colors="#9b9488", linewidths=0.7, zorder=4, alpha=0.7))
    rails = [np.asarray(q.coords) for g in I["rail"] for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString"]
    ax.add_collection(LineCollection(rails, colors="#3a3a3a", linewidths=3.2, zorder=4.2))
    ax.add_collection(LineCollection(rails, colors="#ffffff", linewidths=1.4, linestyles=(0, (5, 5)), zorder=4.3))
    pl = [np.asarray(q.coords) for g in I["power"] for q in getattr(g, "geoms", [g]) if q.geom_type == "LineString"]
    ax.add_collection(LineCollection(pl, colors="#6a51a3", linewidths=1.1, linestyles=(0, (8, 3, 1, 3)), zorder=4.4, alpha=0.8))
    # district boundary
    for p in _polys(GOLD):
        ax.plot(p[:, 0], p[:, 1], color="#b8860b", lw=5.5, zorder=20, solid_joinstyle="round")
        ax.plot(p[:, 0], p[:, 1], color="#fff3b0", lw=1.6, zorder=20.1)
    # axes, thick to thin
    for cls in ["pedestrian", "boulevard", "lrt_corridor", "district", "arterial", "trunk", "expressway"]:
        col, w, dash, _ = AXIS_STYLE[cls]
        for a in AXES:
            if a["class"] != cls:
                continue
            P = np.asarray(a["line"], float)
            kw = dict(color=col, lw=w, zorder=10 + ["pedestrian", "boulevard", "lrt_corridor", "district", "arterial", "trunk", "expressway"].index(cls) * 0.1,
                      solid_capstyle="round")
            if dash:
                kw["linestyle"] = dash
            if a["status"] == "keep_existing" and cls != "expressway":
                kw["alpha"] = 0.85
            ax.plot(P[:, 0], P[:, 1], **kw, path_effects=[pe.Stroke(linewidth=w + 2.4, foreground="white"), pe.Normal()])
    # interchanges
    for it in A3_INTERCHANGES:
        ax.scatter([it["x"]], [it["z"]], s=520, marker="o", facecolor="white", edgecolor="#1a1a1a", linewidths=3.0, zorder=12)
        ax.scatter([it["x"]], [it["z"]], s=120, marker="o", facecolor="#1a1a1a" if it["status"] == "keep_existing" else "#b30000", zorder=12.1)
    # LRT
    P = np.asarray(LRT_LINE)
    ax.plot(P[:, 0], P[:, 1], color="#c51b8a", lw=6.5, zorder=13, solid_capstyle="round",
            path_effects=[pe.Stroke(linewidth=10, foreground="white"), pe.Normal()])
    right = {"L6", "L9", "L10"}
    for s in LRT_STATIONS:
        if s["id"] == "L8":
            ax.scatter([s["x"]], [s["z"]], s=420, marker="o", facecolor="white", edgecolor="#c51b8a", linewidths=4, zorder=14)
            continue
        ax.scatter([s["x"]], [s["z"]], s=420, marker="o", facecolor="white", edgecolor="#c51b8a", linewidths=4, zorder=14)
        r = s["id"] in right
        ax.text(s["x"] + (520 if s["id"] == "L6" else 170 if r else -170), s["z"] + (260 if s["id"] == "L6" else 60), s["name_ru"], fontsize=17, color="#7a0177", fontweight="bold", zorder=15,
                va="center", ha="left" if r else "right", path_effects=[pe.withStroke(linewidth=4, foreground="white")])
    # joints
    J = [j for j in CITY["joints"]["items"] if "golden" in j["between"]]
    jk = {"road": "o", "rail": "D", "lrt": "^"}
    for j in J:
        ax.scatter([j["x"]], [j["z"]], s=260, marker=jk[j["kind"]], facecolor="#ffeb3b", edgecolor="#222222", linewidths=2, zorder=16)
    # centres
    for c in CENTRES:
        sz = {"main": 3200, "sub": 1500, "local": 700}[c["kind"]]
        ax.scatter([c["x"]], [c["z"]], s=sz, marker="*" if c["kind"] == "main" else "o", facecolor="#ffd700" if c["kind"] == "main" else "#ffffff",
                   edgecolor="#7f0000", linewidths=3.5, zorder=17)
        fs = {"main": 30, "sub": 23, "local": 18}[c["kind"]]
        dx = {"C1": 420, "C2": 900, "C3": -1100, "C4": -700, "C5": 260, "C7": 260}.get(c["id"], 300)
        dz = {"C1": -250, "C2": -650, "C3": -150, "C4": 250, "C5": -250, "C7": -250}.get(c["id"], -210)
        ax.text(c["x"] + dx, c["z"] + dz, c["name_ru"], fontsize=fs, fontweight="bold", color="#7f0000", zorder=18,
                ha="left" if dx > 0 else "right", va="top", path_effects=[pe.withStroke(linewidth=6, foreground="white")])
    # objects
    num = 0
    labels = []
    for o in OBJECTS:
        to = o.get("to")
        if not to or o["action"] == "remove":
            continue
        if o["registry_id"].startswith(("road_", "interchange_", "rail_", "settlement_", "district_", "hv_")):
            continue
        num += 1
        fr = o.get("from")
        if o["action"] == "move" and fr:
            ax.add_patch(FancyArrowPatch(fr, to, arrowstyle="-|>", mutation_scale=45, lw=4, color="#08306b", zorder=18.5,
                                         connectionstyle="arc3,rad=-0.25"))
            ax.scatter([fr[0]], [fr[1]], s=360, marker="o", facecolor="white", edgecolor="#08306b", linewidths=2.5, linestyle="--", zorder=18.6)
        ax.scatter([to[0]], [to[1]], s=900, marker="s" if o["action"] in ("keep", "move") else "D", facecolor="#08306b", edgecolor="white",
                   linewidths=2.5, zorder=19)
        ax.text(to[0], to[1], str(num), fontsize=17, color="white", fontweight="bold", ha="center", va="center", zorder=19.1)
        labels.append((num, o))
    # airport note (Growing-W)
    ap = next(o for o in OBJECTS if o["registry_id"] == "airport_alatau")
    ax.scatter([ap["from"][0]], [ap["from"][1]], s=700, marker="x", color="#08306b", linewidths=4, zorder=19)
    ax.annotate("точка реестра аэропорта (−16 488, 561):\nаэропорт — Growing-запад, здесь не планируем",
                xy=ap["from"], xytext=(ap["from"][0] + 400, ap["from"][1] - 1500), fontsize=17, color="#08306b", zorder=19,
                arrowprops=dict(arrowstyle="-|>", color="#08306b", lw=2), path_effects=[pe.withStroke(linewidth=5, foreground="white")])
    # queue labels on zones
    qcol = {1: "#08519c", 2: "#3182bd", 3: "#6baed6", 4: "#9ecae1"}
    for ph in PHASES:
        for zid in ph["zones"]:
            g = built.get(zid)
            if g is None or g.is_empty:
                continue
            big = max(getattr(g, "geoms", [g]), key=lambda p: p.area)
            if big.area < 30e4 and zid not in ("Z-P3",):
                continue
            pnt = big.representative_point()
            ax.text(pnt.x, pnt.y, ["", "I", "II", "III", "IV"][ph["queue"]], fontsize=21, fontweight="bold", color="white", ha="center", va="center", zorder=21,
                    bbox=dict(boxstyle="circle,pad=0.25", facecolor=qcol[ph["queue"]], edgecolor="white", lw=2))
    # zone names for the big areas
    for zid, txt in (("Z-R0", "Резерв после 2050\n(западное плато, только в контуре двойника)"), ("Z-F1", "Лесопарк\n(пески Мойынкум)"),
                     ("Z-L1", "Агропереработка, склады, цеха МСБ"), ("Z-P2", "Долина Каскелена"), ("Z-C1", "QAIST"),
                     ("Z-C2", "Кластер вузов"), ("Z-S1", "Спорт и ипподром"), ("Z-V1", "Жаңаталап"), ("Z-RW", "Резерв роста после 2050")):
        g = built.get(zid)
        if g is None or g.is_empty:
            continue
        big = max(getattr(g, "geoms", [g]), key=lambda p: p.area)
        pnt = big.representative_point()
        ax.text(pnt.x, pnt.y + 260, txt, fontsize=20 if zid in ("Z-R0", "Z-F1", "Z-L1") else 17, color="#333333", ha="center", va="bottom",
                zorder=21, fontstyle="italic", path_effects=[pe.withStroke(linewidth=5, foreground="white")])
    ax.set_xlim(x0, x1); ax.set_ylim(z0, z1); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    # ------------------------------------------------ legend panel in the empty south-west (outside the district)
    lx0 = x0 + 250
    ax.text(lx0, z1 - 250, "Golden — схема района (уровень 0)", fontsize=46, fontweight="bold", va="top", zorder=60,
            path_effects=[pe.withStroke(linewidth=8, foreground="white")])
    ax.text(lx0, z1 - 1150, "Город знаний и здоровья вдоль А-3 и ствола ЛРТ: Университетский город у «Көктерек» — главный центр у K-Park —\n"
            "Северный Golden; жильё 5–12 этажей между речными парками Теренкары и Малой Алматинки; запад — резерв и лесопарк",
            fontsize=21, va="top", zorder=60, path_effects=[pe.withStroke(linewidth=6, foreground="white")])
    h = []
    for u in ["mixed_centre", "residential_high", "residential_mid", "residential_low", "village_existing", "campus", "medical", "sport",
              "business", "logistics", "utility", "park", "waterfront", "reserve"]:
        h.append(Patch(facecolor=USE_STYLE[u][0], edgecolor="#999999", hatch="...." if u == "village_existing" else None, label=USE_STYLE[u][1]))
    for cls in ["expressway", "trunk", "arterial", "district", "boulevard", "pedestrian", "lrt_corridor"]:
        col, w, dash, lab = AXIS_STYLE[cls]
        h.append(Line2D([], [], color=col, lw=w * 0.9, ls=dash if dash else "-", label=lab))
    h += [Line2D([], [], color="#c51b8a", lw=6, marker="o", mfc="white", mec="#c51b8a", mew=3, ms=14, label="ствол ЛРТ и станции"),
          Line2D([], [], ls="", marker="o", mfc="#b30000", mec="#1a1a1a", mew=3, ms=16, label="развязка А-3: новая (красная) / существующая"),
          Line2D([], [], ls="", marker="*", mfc="#ffd700", mec="#7f0000", mew=2, ms=30, label="главный центр"),
          Line2D([], [], ls="", marker="o", mfc="white", mec="#7f0000", mew=3, ms=20, label="подцентр / местный центр"),
          Line2D([], [], ls="", marker="s", mfc="#08306b", mec="white", ms=20, label="объект реестра (номер — список справа)"),
          Line2D([], [], color="#08306b", lw=3, marker=">", ms=12, label="перенос объекта (откуда → куда)"),
          Line2D([], [], ls="", marker="o", mfc="#ffeb3b", mec="#222", ms=14, label="стык с соседом: дорога (●) ж/д (◆) ЛРТ (▲)"),
          Line2D([], [], color="#3a3a3a", lw=3, label="железная дорога (OSM)"),
          Line2D([], [], color="#6a51a3", lw=1.5, ls=(0, (8, 3, 1, 3)), label="ЛЭП (OSM)"),
          Line2D([], [], color="#9b9488", lw=1.2, label="существующие дороги (OSM)"),
          Line2D([], [], color="#b8860b", lw=5, label="граница Golden (city.json)"),
          Line2D([], [], ls="", marker="o", mfc="#3182bd", mec="white", ms=22, label="I–IV — очередь строительства зоны")]
    leg = ax.legend(handles=h, loc="lower left", bbox_to_anchor=(0.004, 0.006), fontsize=18, framealpha=0.95, ncol=2, borderpad=1.0,
                    handlelength=3.2, labelspacing=0.75, columnspacing=1.6, title="Условные обозначения", title_fontsize=23)
    leg.set_zorder(100)
    # objects list + queues (text box) placed in the outside-the-district band north of the legend
    lines = ["Объекты реестра:"]
    for n, o in labels:
        tag = {"keep": "на месте", "move": "перенос", "add": "добавляем", "by_rule": "по правилу"}[o["action"]]
        lines.append(f"{n}. {o['name_ru']} — {tag}")
    lines.append("Аэропорт «Алатау» — Growing-запад; стадион 50 тыс. — отменён")
    ax.text(-11800, -11150, "\n".join(_wrap(lines, 60)), fontsize=17, va="top", ha="left", zorder=100, linespacing=1.35,
            bbox=dict(facecolor="white", alpha=0.95, edgecolor="#999999", boxstyle="round,pad=0.6"))
    q = ["Очереди строительства (сначала улицы и ЛРТ, потом дома, которые они обслуживают):"]
    for ph in PHASES:
        q.append(f"{['', 'I', 'II', 'III', 'IV'][ph['queue']]}  {ph['years'][0]}–{ph['years'][1]}: " + ph["what_ru"].split(";")[0])
    ax.text(x0 + 200, -9350, "\n".join(_wrap(q, 95)), fontsize=17.5, va="top", ha="left", zorder=100, linespacing=1.35,
            bbox=dict(facecolor="white", alpha=0.95, edgecolor="#999999", boxstyle="round,pad=0.6"))
    RM.scale_bar(ax, x1 - 3600, z0 + 350, 2000, "2 км", lw=14)
    RM.north_arrow(ax, x1 - 500, z1 - 1400, 700)
    ax.text(x1 - 150, z0 + 60, "© OpenStreetMap contributors, Overture Maps Foundation · рельеф и контуры — двойник Alatau · "
            "система Unity X/Z · места по правилу — модель qTwin", fontsize=13, ha="right", va="bottom", zorder=60,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"))
    path = os.path.join(out_dir, "scheme.png")
    tmp = path + ".tmp.png"
    fig.savefig(tmp, dpi=dpi)
    plt.close(fig)
    os.replace(tmp, path)
    print(f"[draw] {path}: {W:.0f} × {H:.0f} px, {os.path.getsize(path) / 1e6:.1f} MB")


def _wrap(lines, n):
    out = []
    for s in lines:
        while len(s) > n:
            k = s.rfind(" ", 0, n)
            k = n if k < 10 else k
            out.append(s[:k]); s = "     " + s[k + 1:]
        out.append(s)
    return out
