"""Draw the Growing-West scheme picture (north up, Russian legend) from tools/map/spec/growing_w.json."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "geo"))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Polygon as MPoly, FancyArrowPatch  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402

import growing_w_design as D  # noqa: E402
import layers  # noqa: E402
import render_maps  # noqa: E402
import terrain  # noqa: E402

UCOL = {"mixed_centre": "#d7263d", "business": "#9b5de5", "residential_high": "#f4a259", "residential_mid": "#f7c873", "residential_low": "#fbe7a8",
        "village_existing": "#a9746e", "campus": "#3a86ff", "medical": "#ff5d8f", "industry": "#8d99ae", "logistics": "#b8a1d9", "utility": "#cfcfcf",
        "park": "#7bc47f", "waterfront": "#5fb7d4", "sport": "#2ec4b6", "reserve": "#efeee6"}
AX = {"expressway": ("#7a0010", 13, 30), "trunk": ("#e4572e", 10, 29), "arterial": ("#f29e4c", 7, 28), "district": ("#c9a227", 4.5, 27),
      "boulevard": ("#1b7f3b", 6, 27.5), "pedestrian": ("#1b7f3b", 3.5, 27.6)}
HALO = [pe.withStroke(linewidth=6, foreground="white")]


def P(z):
    g = shapely.make_valid(Polygon(z["polygon"], z.get("holes", [])))
    return [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon"]


def text(ax, x, z, s, fs=24, col="#111", w="bold", ha="center", va="center", zo=60, box=False):
    kw = dict(fontsize=fs, color=col, fontweight=w, ha=ha, va=va, zorder=zo, path_effects=HALO)
    if box:
        kw.pop("path_effects")
        kw["bbox"] = dict(facecolor="white", alpha=0.85, edgecolor="#555", boxstyle="round,pad=0.25")
    ax.text(x, z, s, **kw)


def draw(spec, path, mpp=5.0):
    c, W, E = D.load_ctx()
    x0, z0, x1, z1 = -19600, -4300, 1600, 17000
    Wpx, Hpx = (x1 - x0) / mpp, (z1 - z0) / mpp
    fig = plt.figure(figsize=(Wpx / 100, Hpx / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#f4f2ec")
    # hillshade
    T = terrain.terrain()
    xs = np.arange(x0, x1, 50.0); zs = np.arange(z0, z1, 50.0)
    X, Z = np.meshgrid(xs, zs)
    Hh = T.height(X, Z)
    gx, gz = np.gradient(Hh, 50.0)
    az, alt = np.radians(315), np.radians(40)
    sl = np.arctan(np.hypot(gx, gz) * 3); asp = np.arctan2(-gx, gz)
    hs = np.sin(alt) * np.cos(sl) + np.cos(alt) * np.sin(sl) * np.cos(az - asp)
    ax.imshow(hs, origin="lower", extent=(x0, x1, z0, z1), cmap="gray", vmin=0.2, vmax=1.1, alpha=0.55, zorder=0)
    cs = ax.contour(X, Z, Hh, levels=np.arange(500, 700, 20), colors="#6b5b45", linewidths=0.8, alpha=0.45, zorder=1)
    # neighbours (muted)
    for k, nm, at in (("golden", "GOLDEN", (-12500, -2600)), ("green", "GREEN", (-2500, 16420)), ("growing_e", "GROWING-\nВОСТОК\n(w41)", (650, 11300))):
        g = Polygon(c["districts"][k]["polygon"]).buffer(0)
        ax.add_collection(PolyCollection(render_maps._polys([g]), facecolor="white", alpha=0.45, edgecolor="none", zorder=2))
        text(ax, at[0], at[1], nm, fs=34, col="#777", zo=8, w="bold")
    # zones
    for z in spec["zones"]:
        for q in P(z):
            ax.add_patch(MPoly(np.asarray(q.exterior.coords), closed=True, facecolor=UCOL[z["use"]], edgecolor="white", linewidth=0.8, alpha=0.82, zorder=5))
            for r in q.interiors:
                pass
    # water
    wg, wp = layers.load("water")
    clip = shapely.box(x0, z0, x1, z1)
    sel = shapely.intersects(clip, wg)
    ax.add_collection(PolyCollection(render_maps._polys([g for g, s in zip(wg, sel) if s and g.geom_type in ("Polygon", "MultiPolygon")]),
                                     facecolor="#4ea8de", edgecolor="#1d6fa5", linewidths=0.8, zorder=9))
    ax.add_collection(LineCollection(render_maps._lines([g for g, s, p in zip(wg, sel, wp) if s and "Line" in g.geom_type and (p.get("name") or p.get("class") == "river")]),
                                     colors="#1d6fa5", linewidths=3.2, zorder=9))
    # existing roads (muted), rail, power
    rg, rp = layers.load("roads")
    sel = np.flatnonzero(shapely.intersects(clip, rg))
    keep = [rg[i] for i in sel if rp[i].get("class") in ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential")]
    ax.add_collection(LineCollection(render_maps._lines(keep), colors="#7d7d7d", linewidths=1.0, alpha=0.6, zorder=10))
    rl, _ = layers.load("rail")
    sel = shapely.intersects(clip, rl)
    ax.add_collection(LineCollection(render_maps._lines(rl[sel]), colors="#222", linewidths=5, zorder=24))
    ax.add_collection(LineCollection(render_maps._lines(rl[sel]), colors="white", linewidths=2.4, linestyles=(0, (5, 5)), zorder=24.1))
    ig, ip = layers.load("infrastructure")
    pl = [g for g, p in zip(ig, ip) if p.get("class") in ("power_line", "minor_line") and g.intersects(clip)]
    ax.add_collection(LineCollection(render_maps._lines(pl), colors="#6a3d9a", linewidths=1.8, linestyles=(0, (10, 4, 2, 4)), zorder=23))
    # district boundary
    ax.add_collection(LineCollection(render_maps._lines([W.exterior]), colors="#c2410c", linewidths=6, zorder=40))
    # airport: runway, surfaces
    import growing_w_scheme as S
    for k, poly in S.airport_surfaces().items():
        ax.add_patch(MPoly(np.asarray(poly.exterior.coords), closed=True, fill=False, edgecolor="#333", linewidth=2, linestyle=(0, (8, 6)), zorder=20, alpha=0.6))
    rw = D.rwy_rect(-D.RWY["length"] / 2, D.RWY["length"] / 2, -45, 45)
    ax.add_patch(MPoly(np.asarray(rw.exterior.coords), closed=True, facecolor="#222", edgecolor="#000", linewidth=2, zorder=35))
    zh = [a for a in c["height_limits"]["airfields"] if a["id"] == "zhetygen_mil"][0]
    circ = Point(zh["x"], zh["z"]).buffer(10000, 256).exterior
    ax.add_collection(LineCollection(render_maps._lines([circ]), colors="#555", linewidths=3, linestyles=(0, (12, 6)), zorder=21))
    text(ax, -1900, 13300, "граница 10 км от\nаэродрома Жетыген", fs=20, col="#444", zo=45, w="normal")
    # axes
    for a in spec["axes"]:
        col, lw, zo = AX[a["class"]]
        L = np.asarray(a["line"])
        ls = (0, (2, 1.5)) if a["class"] == "pedestrian" else ((0, (1, 0.6)) if a["class"] == "boulevard" else "-")
        if a["status"] != "new":
            ax.plot(L[:, 0], L[:, 1], color=col, lw=lw, zorder=zo, solid_capstyle="round", alpha=0.9)
        else:
            ax.plot(L[:, 0], L[:, 1], color="white", lw=lw + 4, zorder=zo - 0.1, solid_capstyle="round")
            ax.plot(L[:, 0], L[:, 1], color=col, lw=lw, zorder=zo, linestyle=ls, solid_capstyle="round")
    # rail spur
    spur = [o for o in spec["objects"] if o.get("line")][0]["line"]
    L = np.asarray(spur)
    ax.plot(L[:, 0], L[:, 1], color="#222", lw=6, zorder=31)
    ax.plot(L[:, 0], L[:, 1], color="#ffd166", lw=2.6, linestyle=(0, (4, 4)), zorder=31.1)
    # LRT
    L = np.asarray(spec["lrt"]["line"])
    ax.plot(L[:, 0], L[:, 1], color="white", lw=10, zorder=32)
    ax.plot(L[:, 0], L[:, 1], color="#c2187a", lw=6, zorder=32.1)
    for s in spec["lrt"]["stations"]:
        ax.scatter([s["x"]], [s["z"]], s=420, marker="s", facecolor="white", edgecolor="#c2187a", linewidths=3.5, zorder=33)
    lab_off = {"L1": (0, -330), "L2": (0, 330), "L3": (-80, -360), "L4": (0, 330), "L5": (0, 330), "L6": (0, -330), "L7": (0, 330), "L8": (0, -330),
               "L9": (0, 330), "L10": (0, 330), "L11": (0, 330)}
    for s in spec["lrt"]["stations"]:
        dx, dz = lab_off.get(s["id"], (0, 300))
        text(ax, s["x"] + dx, s["z"] + dz, s["name_ru"], fs=17, col="#8e0f57", zo=34, w="bold")
    # joints
    J = {j["id"]: j for j in c["joints"]["items"]}
    pts = np.array([[J[m["joint_id"]]["x"], J[m["joint_id"]]["z"]] for m in spec["joints"]])
    ax.scatter(pts[:, 0], pts[:, 1], s=260, marker="o", facecolor="#ffe600", edgecolor="#111", linewidths=2.2, zorder=42)
    # centres
    for ce in spec["centres"]:
        mk, sz, col = {"main": ("*", 3800, "#d7263d"), "sub": ("o", 1500, "#7b2cbf"), "local": ("o", 600, "#ffffff")}[ce["kind"]]
        ax.scatter([ce["x"]], [ce["z"]], s=sz, marker=mk, facecolor=col, edgecolor="#111", linewidths=3, zorder=50)
    cl = {"c_main": (0, 520, "ЦЕНТР «КАСКЕЛЕН»", 34), "c_airport": (0, 700, "АЭРОСИТИ «АЛАТАУ»\nтерминал · вокзал · ЛРТ", 28),
          "c_dryport": (0, -430, "Сухой порт", 22), "c_westbank": (-300, 420, "Левобережный центр", 20), "c_north": (1250, 150, "Северный\nцентр", 21),
          "c_plateau": (0, 450, "Технопарк «Плато»", 22)}
    for ce in spec["centres"]:
        dx, dz, s, fs = cl[ce["id"]]
        text(ax, ce["x"] + dx, ce["z"] + dz, s, fs=fs, col="#111", zo=51)
    # registry objects: numbered markers
    num = {}
    k = 0
    for o in spec["objects"]:
        if o["to"] is None:
            continue
        k += 1
        num[o["registry_id"]] = k
        x, z = o["to"]
        ax.scatter([x], [z], s=900, marker="o", facecolor="#0b3d91", edgecolor="white", linewidths=3, zorder=55)
        ax.text(x, z, str(k), fontsize=17, color="white", fontweight="bold", ha="center", va="center", zorder=56)
    # moves
    for o in spec["objects"]:
        if o["action"] == "move":
            if o["registry_id"] != "airport_alatau":
                continue
            for fr, lab in ((o["from"], "точка реестра\n(в Golden)"), (o.get("from_twin"), "в двойнике\nсейчас")):
                if not fr:
                    continue
                ax.scatter([fr[0]], [fr[1]], s=500, marker="X", color="#555", zorder=52)
                arr = FancyArrowPatch(tuple(fr), tuple(o["to"]), arrowstyle="-|>,head_length=1.6,head_width=0.9", mutation_scale=30, lw=4,
                                      color="#333", linestyle=(0, (6, 4)), zorder=53, shrinkA=20, shrinkB=40, connectionstyle="arc3,rad=0.12")
                ax.add_patch(arr)
                if o["registry_id"] == "airport_alatau":
                    text(ax, fr[0] + (0 if fr[1] < 1000 else 0), fr[1] + (-450 if fr[1] < 1000 else 520), lab, fs=18, col="#333", w="normal", zo=54)
    # key zone labels with build queue
    qz = {}
    for q in spec["phases"]:
        for zid in q["zones"]:
            qz.setdefault(zid, q["queue"])
    labels = {"ctr_main": None, "res_centre_e": "Кварталы у ЛРТ\n9–12 эт.", "res_westbank": "Левобережные\nкварталы 5–8 эт.", "res_north": "Правобережные\nкварталы 5–8 эт.",
              "res_low_north": "Малоэтажные\nкварталы 2–3 эт.", "log_dryport": "Сухой порт · сортировочная\nстанция · Rhenus", "ind_south": "Южная промзона",
              "ind_plateau": "Западная промзона\n(плато 600–640 м)", "log_cargo": "Грузовой\nтерминал", "air_airside": "ВПП 4 000 м · 095°/275°",
              "biz_a3": "Деловая\nполоса А-3", "park_escarpment": "Лесопарк «Уступ»", "res_reserve_plateau": "Резерв плато (после 2050)",
              "res_reserve_valley": "Резерв долины\n(после 2050)", "park_lakes": "Природный парк\nу озёр Жаманкум", "campus_voc": "Профтех-\nинститут",
              "river_kaskelen": None, "air_reserve": "Охранная зона аэропорта"}
    at = {"air_airside": (-14600, 750), "park_escarpment": (-5000, 9100), "res_reserve_plateau": (-8200, 11800), "res_reserve_valley": (-2600, 11800),
          "ind_plateau": (-10300, 2100), "log_dryport": (-2900, 1250), "ind_south": (-4300, -1100), "biz_a3": (-350, 6000), "res_low_north": (-2300, 7350),
          "res_north": (-1700, 4700), "res_centre_e": (-1700, 3100), "res_westbank": (-6100, 2650), "log_cargo": (-13500, 3600), "park_lakes": (-10400, 8600),
          "campus_voc": (-2450, 4150), "air_reserve": (-17300, 3300)}
    for zid, lab in labels.items():
        if not lab:
            continue
        x, z = at[zid]
        q = qz.get(zid) or next((qz[i] for i in qz if i.startswith(zid + "_")), None)
        s = lab + (f"\n[{q}]" if q else "")
        text(ax, x, z, s, fs=22 if zid != "campus_voc" else 17, col="#222", zo=46)
    text(ax, -5500, 1450, "Каскелен", fs=24, col="#0b4f7a", w="bold", zo=46)
    text(ax, -500, 9800, "дачные массивы\n(остаются)", fs=20, col="#5b2a26", zo=46)
    text(ax, -16000, -500, "→ ст. Мойынкум, Сорбулак", fs=18, col="#333", w="normal", zo=46)
    text(ax, 300, -1000, "А-3", fs=30, col="#7a0010", zo=46)
    text(ax, 1000, 400, "Жанаарна,\nOIZ TULIP\n(w41)", fs=19, col="#555", w="normal", zo=46)
    # legend (top-left, outside the district)
    h = [Patch(facecolor=UCOL[u], edgecolor="#777", label=USE) for u, USE in (
        ("mixed_centre", "центр: офисы, торговля, жильё"), ("business", "деловая зона, аэросити"), ("residential_high", "жильё 9–12 этажей"),
        ("residential_mid", "жильё 5–8 этажей"), ("residential_low", "жильё 2–3 этажа"), ("village_existing", "существующие посёлки и дачи (остаются)"),
        ("campus", "профтехинститут"), ("industry", "промышленность"), ("logistics", "логистика, сухой порт, грузы"),
        ("utility", "лётное поле, ПС, СЭС, коридоры ЛЭП и ж/д"), ("park", "парки, лесопарк, озёрный парк"), ("waterfront", "река Каскелен и набережная"),
        ("reserve", "резерв после 2050, охранная зона аэропорта"))]
    h += [Line2D([], [], color=AX["expressway"][0], lw=9, label="скоростная дорога А-3 (есть)"),
          Line2D([], [], color=AX["trunk"][0], lw=7, label="магистраль (новая)"),
          Line2D([], [], color=AX["arterial"][0], lw=5, label="улица общегородская (новая)"),
          Line2D([], [], color=AX["district"][0], lw=3.5, label="улица районная (новая)"),
          Line2D([], [], color=AX["boulevard"][0], lw=5, ls=(0, (1, 0.6)), label="бульвар, набережная"),
          Line2D([], [], color="#c2187a", lw=6, marker="s", mfc="white", mec="#c2187a", ms=16, mew=3, label="ЛРТ и станции (модель qTwin)"),
          Line2D([], [], color="#222", lw=5, label="ж/д обход Жетыген – Казыбек би (есть)"),
          Line2D([], [], color="#ffd166", lw=4, ls=(0, (2, 2)), label="ж/д ветка к аэропорту (новая)"),
          Line2D([], [], color="#6a3d9a", lw=2.5, ls=(0, (10, 4, 2, 4)), label="ЛЭП 220–500 кВ (есть)"),
          Line2D([], [], color="#7d7d7d", lw=2, label="дороги сегодня (OSM)"),
          Patch(facecolor="#222", label="ВПП аэропорта; пунктир — поверхности захода и взлёта 15 км"),
          Line2D([], [], ls="", marker="*", ms=40, mfc="#d7263d", mec="k", label="главный центр"),
          Line2D([], [], ls="", marker="o", ms=26, mfc="#7b2cbf", mec="k", label="центр аэросити"),
          Line2D([], [], ls="", marker="o", ms=17, mfc="white", mec="k", label="местный центр"),
          Line2D([], [], ls="", marker="o", ms=20, mfc="#0b3d91", mec="white", label="объект реестра (номер в списке)"),
          Line2D([], [], ls="", marker="X", ms=18, color="#555", label="старое место → новое (стрелка)"),
          Line2D([], [], ls="", marker="o", ms=15, mfc="#ffe600", mec="k", label="стык с соседним районом"),
          Line2D([], [], color="#c2410c", lw=5, label="граница Growing-запад")]
    leg = ax.legend(handles=h, loc="upper left", fontsize=19, framealpha=0.94, borderpad=0.8, handlelength=3.2, labelspacing=0.55,
                    title="Условные обозначения", title_fontsize=24)
    leg.set_zorder(1000)
    # objects list + queues (bottom-left, over Golden)
    names = []
    for o in spec["objects"]:
        if o["registry_id"] in num:
            act = {"move": "переносим", "by_rule": "по правилу", "keep": "остаётся", "add": "добавляем"}[o["action"]]
            names.append(f"{num[o['registry_id']]:>2}  {o['name_ru'][:46]} — {act}")
    qtxt = "\n".join(f"[{q['queue']}] {q['years'][0]}–{q['years'][1]}: {q['what_ru'][:92]}" for q in spec["phases"])
    ax.text(x0 + 300, z0 + 300, "Объекты реестра\n" + "\n".join(names), fontsize=17, va="bottom", ha="left", zorder=1000, family="DejaVu Sans",
            bbox=dict(facecolor="white", alpha=0.94, edgecolor="#555", boxstyle="round,pad=0.5"))
    import textwrap
    qtxt = "\n".join("[" + str(q["queue"]) + "] " + f"{q['years'][0]}–{q['years'][1]}: " + textwrap.fill(q["what_ru"], 70, subsequent_indent="      ") for q in spec["phases"])
    ax.text(x0 + 5800, z0 + 300, "Очереди строительства (улица раньше домов)\n" + qtxt, fontsize=17, va="bottom", ha="left", zorder=1000,
            bbox=dict(facecolor="white", alpha=0.94, edgecolor="#555", boxstyle="round,pad=0.5"))
    # numbers box
    ck = spec["checks"].get("capacity", {})
    t = spec["targets"]
    info = (f"Growing-запад · 20 928 га\nжителей 2050: {ck.get('residents_new', 0):,} (цель {t['population_2050']:,})\n"
            f"рабочих мест: {ck.get('jobs', 0):,} (цель {t['jobs_2050']:,})").replace(",", " ")
    ax.text(x1 - 300, z1 - 300, info, fontsize=22, va="top", ha="right", zorder=1000, fontweight="bold",
            bbox=dict(facecolor="white", alpha=0.94, edgecolor="#c2410c", boxstyle="round,pad=0.5"))
    render_maps.scale_bar(ax, x1 - 7600, z0 + 500, 5000, "5 км", lw=14)
    render_maps.north_arrow(ax, x1 - 700, z1 - 3300, 900)
    ax.text((x0 + x1) / 2, z1 - 120, "GROWING-ЗАПАД · схема района (уровень 0) · аэропорт, логистика и жильё вдоль Каскелена", fontsize=34, fontweight="bold",
            ha="center", va="top", zorder=1001, bbox=dict(facecolor="white", alpha=0.9, edgecolor="none"))
    ax.text(x0 + 300, z1 - 900 - 0, "", fontsize=10)
    ax.text((x0 + x1) / 2, z0 + 60, "© OpenStreetMap contributors, Overture Maps Foundation · рельеф двойника · аэропорт, ЛРТ, центры и зоны — модель qTwin · Unity X/Z, м",
            fontsize=15, ha="center", va="bottom", zorder=1001, bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"))
    ax.set_xlim(x0, x1); ax.set_ylim(z0, z1); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.png"
    fig.savefig(tmp, dpi=100)
    plt.close(fig)
    os.replace(tmp, path)
    print("[draw]", path, int(Wpx), "×", int(Hpx), "px", round(os.path.getsize(path) / 1e6, 1), "MB")
