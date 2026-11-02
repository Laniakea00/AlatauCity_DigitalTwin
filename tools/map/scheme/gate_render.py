"""The Gate scheme picture (called by gate_scheme.py): north up, scale bar, Russian legend and labels, ≈ 3200 × 4600 px."""
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, Patch  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402

import gate_scheme as GS  # noqa: E402

USE_COL = {
    "mixed_centre": ("#c0392b", "смешанный центр (Iconic, админцентр)"), "business": ("#ef7564", "деловая зона, офисы, ТПУ"),
    "residential_high": ("#e67e22", "жильё высокое (9–16 эт.)"), "residential_mid": ("#f7c46c", "жильё среднеэтажное (5–8 эт.)"),
    "residential_low": ("#fbe9a7", "жильё малоэтажное (3–4 эт.)"), "village_existing": ("#cbb89a", "существующие сёла (остаются)"),
    "industry": ("#8e7cc3", "промышленность"), "logistics": ("#b4add6", "логистика"), "utility": ("#c4c4c4", "трассы, развязки, ВЛ, инженерия"),
    "park": ("#86c97c", "парки и берега рек"), "waterfront": ("#45c1a8", "набережная"), "sport": ("#c6ebc0", "спорт"),
    "medical": ("#f4a7b9", "медицина"), "campus": ("#5dade2", "кампус"), "reserve": ("#eeeae0", "резерв после 2050"),
}
AX_STYLE = {  # class: colour, width (pt), z, dashes
    "expressway": ("#5d4037", 7.5, 30, None), "arterial": ("#d35400", 6.0, 32, None), "district": ("#f39c12", 3.6, 31, None),
    "boulevard": ("#1e8449", 5.0, 33, (0, (3, 1.2))), "pedestrian": ("#1e8449", 3.0, 33, (0, (1, 1))),
}
LRT_COL = "#c2185b"


def _polys(g):
    return [np.asarray(q.exterior.coords) for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon" and not q.is_empty]


def _lines(geoms):
    out = []
    for g in geoms:
        for q in getattr(g, "geoms", [g]):
            if q.geom_type in ("LineString", "LinearRing") and len(q.coords) > 1:
                out.append(np.asarray(q.coords))
            elif q.geom_type == "Polygon":
                out.append(np.asarray(q.exterior.coords))
    return out


HALO = [pe.withStroke(linewidth=4, foreground="white")]


def label(ax, x, z, txt, fs=15, col="#222", weight="bold", z_=60, ha="center", va="center", box_=False):
    kw = dict(fontsize=fs, color=col, fontweight=weight, ha=ha, va=va, zorder=z_, path_effects=HALO)
    if box_:
        kw["bbox"] = dict(facecolor="white", alpha=0.85, edgecolor="#888", boxstyle="round,pad=0.25")
        kw.pop("path_effects")
    ax.text(x, z, txt, **kw)


def render(spec, D, C, zones, axes, ax_geo, outdir, quantize=True):
    os.makedirs(outdir, exist_ok=True)
    G = GS.G
    x0, z0, x1, z1 = G.bounds
    x0 -= 350; z0 -= 300; x1 += 1300; z1 += 350
    mpp = 2.7
    W, H = (x1 - x0) / mpp, (z1 - z0) / mpp
    dpi = 100
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#f4f2ec")
    clip = box(x0, z0, x1, z1)
    # terrain contours (5 m) — muted
    xs = np.arange(x0, x1, 50.0); zs = np.arange(z0, z1, 50.0)
    X, Z = np.meshgrid(xs, zs)
    Hh = GS.T.height(X, Z)
    cs = ax.contour(X, Z, Hh, levels=np.arange(590, 700, 5), colors="#b8ad99", linewidths=0.5, alpha=0.55, zorder=1)
    ax.clabel(cs, levels=np.arange(600, 700, 20), fontsize=9, fmt="%d м", colors="#9c907a")
    # context outside Gate: existing roads, buildings
    rg, rp = D["roads"]
    sel = shapely.intersects(clip, rg)
    minor = [g for g, p, s in zip(rg, rp, sel) if s and p.get("class") not in ("motorway", "trunk")]
    ax.add_collection(LineCollection(_lines(minor), colors="#bdb6a8", linewidths=0.6, zorder=2))
    # zones
    for z in zones:
        col = USE_COL[z["use"]][0]
        g = z["_g"]
        hatch = "///" if z["use"] == "reserve" else None
        pc = PolyCollection(_polys(g), facecolor=col, edgecolor="white", linewidths=1.2, alpha=0.92 if z["use"] != "village_existing" else 0.85,
                            zorder=5, hatch=hatch)
        ax.add_collection(pc)
    # buildings: villages and existing (muted)
    bg, _ = D["buildings"]
    bs = bg[shapely.intersects(clip, bg)]
    ax.add_collection(PolyCollection([np.asarray(q.exterior.coords) for q in bs if q.geom_type == "Polygon"], facecolor="#8d7b62",
                                     edgecolor="none", alpha=0.75, zorder=7))
    # water on top
    ax.add_collection(PolyCollection(_polys(C["water"].intersection(clip)), facecolor="#6fb7e6", edgecolor="#3b8fd0", linewidths=0.6, zorder=8))
    # power lines (existing) and the moved north line
    ax.add_collection(LineCollection(_lines([h for h in C["hv"] if h.intersects(clip)]), colors="#7d3c98", linewidths=1.3,
                                     linestyles=(0, (8, 3, 1, 3)), zorder=9, alpha=0.8))
    newhv = LineString([(-4380, -19320), (-4250, -19810), (-3100, -19985), (-2450, -20050)])
    ax.add_collection(LineCollection(_lines([newhv]), colors="#7d3c98", linewidths=2.2, linestyles=(0, (2, 2)), zorder=9))
    # existing other roads in Gate (muted) and district boundary
    ax.add_collection(LineCollection(_lines([G.exterior]), colors="#1f4e9a", linewidths=4.5, zorder=40, linestyles=(0, (6, 2))))
    # axes
    for a in axes:
        L = np.asarray(a["line"], float)
        if a["class"] == "lrt_corridor":
            if a["id"] == "ax_metro3":
                ax.plot(L[:, 0], L[:, 1], color="#555", lw=3, ls=(0, (2, 2)), zorder=34, solid_capstyle="round")
            continue
        col, lw, zz, ds = AX_STYLE[a["class"]]
        if a["status"] == "keep_existing" and a["class"] != "expressway":
            col, lw = "#7f7366", lw * 0.7
        kw = dict(color=col, lw=lw, zorder=zz, solid_capstyle="round")
        if ds:
            kw["ls"] = ds
        if a["class"] in ("arterial", "district", "expressway"):
            ax.plot(L[:, 0], L[:, 1], color="white", lw=lw + 2.5, zorder=zz - 0.5, solid_capstyle="round")
        ax.plot(L[:, 0], L[:, 1], **kw)
    # LRT
    lrt = np.asarray(spec["lrt"]["line"], float)
    ax.plot(lrt[:, 0], lrt[:, 1], color="white", lw=9, zorder=35)
    ax.plot(lrt[:, 0], lrt[:, 1], color=LRT_COL, lw=5.5, zorder=36)
    for s in spec["lrt"]["stations"]:
        ax.add_patch(Circle((s["x"], s["z"]), 55, facecolor="white", edgecolor=LRT_COL, lw=3.5, zorder=37))
        off = 95 if s["id"] not in ("st_tpu", "st_gatecity") else -95
        label(ax, s["x"] + off, s["z"], s["name_ru"], fs=13, col=LRT_COL, ha="left" if off > 0 else "right")
    # Gate District + Iconic
    ix, iz = GS.ICONIC
    ax.add_patch(Circle((ix, iz), GS.QT_R, facecolor="none", edgecolor="#7b241c", lw=3, ls=(0, (5, 2)), zorder=41))
    # centres
    for c in spec["centres"]:
        if c["kind"] == "main":
            ax.scatter([c["x"]], [c["z"]], s=2600, marker="*", color="#f1c40f", edgecolor="#5b2c00", linewidths=2.5, zorder=50)
        elif c["kind"] == "sub":
            ax.scatter([c["x"]], [c["z"]], s=700, marker="D", color="#f1c40f", edgecolor="#5b2c00", linewidths=2, zorder=50)
        else:
            ax.scatter([c["x"]], [c["z"]], s=380, marker="o", color="#fdebd0", edgecolor="#5b2c00", linewidths=2, zorder=50)
    label(ax, ix - 380, iz + 420, "ICONIC\nцентр Gate", fs=26, col="#7b241c", ha="right")
    label(ax, -4000, -23000 + 0, "Административный\nцентр", fs=17, col="#7b241c", ha="center")
    # old Iconic and moves
    oi = (spec["checks"]["iconic_candidates"][4]["x"], spec["checks"]["iconic_candidates"][4]["z"])
    ax.scatter([oi[0]], [oi[1]], s=900, marker="*", facecolor="none", edgecolor="#7b241c", linewidths=2, zorder=49)
    ax.add_patch(FancyArrowPatch(oi, (ix + 60, iz + 80), arrowstyle="-|>", mutation_scale=35, lw=3, color="#7b241c", zorder=49))
    label(ax, oi[0] + 120, oi[1] + 120, "Iconic сейчас", fs=13, col="#7b241c", ha="left", weight="normal")
    # objects
    obj_lbl = {
        "griffin_logopark": "Griffin Logopark", "pepsico": "PepsiCo (завод)", "l7_lotte": "L7 by Lotte", "datacenter_alatau_data_hub": "Alatau Data Hub",
        "agglo_rail_station_1": "ст. агломерационной ж/д", "admin_centre_new": "", "akimat_koyankus": "акимат", "school_gate_city_20_keleshek": "школа № 20",
        "zhk_gate_city": "ЖК Gate City", "hospitals_stage1": "больница 500 коек", "park_gate_city_yntymak": "Парк Gate", "metro_line3_reserve": "резерв метро",
        "jti_factory": "JTI", "dolce_pharm": "Dolce-Pharm", "ps_kokpa_1": "инж. узел: ПС «Кокпа-1», котельная, КНС, АГРС, водозабор",
        "interchange_a3_bakad": "развязка А-3 × БАКАД", "interchange_a3_yntymak_zhanadaur": "развязка Ынтымақ–Жанадаур", "interchange_a3_km18_5": "развязка км 18,5",
        "sport_complex_koyankus": "спорткомплекс", "ambulatory_zhanadaur": "амбулатория", "avz_fan_plant": "заводы Қоянқұс (АВЗ и др.)",
        "school_koyankus_old": "школа Қоянқұс", "water_intake_yntymak": "водозабор", "kindergarten_gate_city_280": "сад 280",
    }
    seen = set()
    for o in spec["objects"]:
        if not o["to"]:
            continue
        x, z = o["to"]
        if not (x0 < x < x1 and z0 < z < z1):
            continue
        k = (round(x / 40), round(z / 40))
        mk_col = "#1a5276" if o["action"] in ("keep",) else "#117a65" if o["action"] == "add" else "#7b241c" if o["action"] == "move" else "#7f8c8d"
        if o["registry_id"].startswith("iconic") or o["registry_id"] in ("gate_district_ring", "gateway_district_som"):
            continue
        if k not in seen:
            ax.scatter([x], [z], s=170, marker="o", color=mk_col, edgecolor="white", linewidths=1.8, zorder=52)
            seen.add(k)
        t = obj_lbl.get(o["registry_id"])
        if t:
            label(ax, x + 70, z - 70, t, fs=12, col=mk_col, ha="left", va="top", weight="bold")
        if o["action"] == "move" and o["from"] and o["registry_id"] not in ("water_intake_gate_city",):
            fx, fz = o["from"]
            if x0 < fx < x1 and z0 < fz < z1:
                ax.add_patch(FancyArrowPatch((fx, fz), (x, z), arrowstyle="-|>", mutation_scale=28, lw=2.5, color="#7b241c", zorder=51,
                                             connectionstyle="arc3,rad=0.15"))
                ax.scatter([fx], [fz], s=160, marker="o", facecolor="none", edgecolor="#7b241c", linewidths=2, zorder=51)
            else:
                ex, ez = x + 900, z + 600
                ax.add_patch(FancyArrowPatch((ex, ez), (x + 40, z + 30), arrowstyle="-|>", mutation_scale=28, lw=2.5, color="#7b241c",
                                             zorder=51, connectionstyle="arc3,rad=0.2"))
                label(ax, ex + 40, ez + 40, f"из Growing ({fx}, {fz})", fs=11, col="#7b241c", ha="left", weight="normal")
    # joints
    J = [j for j in GS.CITY["joints"]["items"] if "gate" in j["between"]]
    jk = {"road": "o", "rail": "D", "lrt": "^"}
    for j in J:
        ax.scatter([j["x"]], [j["z"]], s=110, marker=jk[j["kind"]], color="#ffeb3b", edgecolor="#333", linewidths=1.3, zorder=55)
    # names of villages and zones
    for nm, (x, z) in {"Жаңадәуір": (-4550, -18200), "Ынтымақ": (-3650, -21200), "Қоянқұс": (-5950, -24200)}.items():
        label(ax, x, z, nm, fs=20, col="#5d4037")
    for t, (x, z), r in [("Сити Gate", (-3600, -19020), 0), ("Griffin\nлогистика", (-2400, -18860), 0), ("Центральный\nпарк", (-3505, -18710), 0),
                         ("Больница", (-2450, -18100), 0), ("ТПУ", (-2860, -20330), 0), ("Парк Gate", (-4150, -22560), 0),
                         ("Резерв после 2050", (-7150, -22000), 90), ("Резерв после 2050", (-5000, -16300), 0), ("Резерв за А-19", (-900, -16200), 0),
                         ("Логистика за А-3", (-1650, -21200), 0), ("Технопарк", (-1400, -17350), 0), ("PepsiCo\nи теплицы", (-3150, -22950), 0),
                         ("Набережная Есентай", (-3300, -16100), 0)]:
        ax.text(x, z, t, fontsize=16, color="#333", fontweight="bold", ha="center", va="center", rotation=r, zorder=45, path_effects=HALO, alpha=0.95)
    # queues: circled numbers on the largest piece of each queue's zones
    QC = {1: "#922b21", 2: "#b9770e", 3: "#1e8449", 4: "#2471a3", 5: "#6c3483"}
    for ph in spec["phases"]:
        q = ph["queue"]
        for zid in ph["zones"][:4]:
            pieces = [z for z in zones if z["_base"] == zid]
            if not pieces:
                continue
            p = max(pieces, key=lambda z: z["_g"].area)["_g"]
            c = p.representative_point()
            ax.add_patch(Circle((c.x + 90, c.y - 90), 70, facecolor=QC[q], edgecolor="white", lw=2.5, zorder=46))
            ax.text(c.x + 90, c.y - 90, str(q), fontsize=15, color="white", fontweight="bold", ha="center", va="center", zorder=47)
    ax.set_xlim(x0, x1); ax.set_ylim(z0, z1); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    # title
    ax.text(x0 + 200, z1 - 120, "Gate · схема района (уровень 0)", fontsize=40, fontweight="bold", va="top", ha="left", zorder=80, color="#1b2631")
    ax.text(x0 + 200, z1 - 560, "Iconic — в центре Gate: у узла БАКАД, где сходятся ЛРТ, Проспект Ворот и Западный проспект.\n"
            "Сёла остаются, оси их обходят. Плотный Сити у Iconic и станций, внутри — 5–8 этажей.", fontsize=17, va="top", ha="left",
            zorder=80, color="#1b2631", bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"))
    # legend
    h = [Patch(facecolor=c, edgecolor="#999", label=l, hatch="///" if k == "reserve" else None) for k, (c, l) in USE_COL.items()
         if any(z["use"] == k for z in zones)]
    h += [Line2D([], [], color=AX_STYLE["expressway"][0], lw=6, label="скоростная дорога (существует)"),
          Line2D([], [], color=AX_STYLE["arterial"][0], lw=5, label="магистраль (новая)"),
          Line2D([], [], color=AX_STYLE["district"][0], lw=3.5, label="улица районного значения (новая)"),
          Line2D([], [], color="#7f7366", lw=3, label="существующая улица (остаётся)"),
          Line2D([], [], color=AX_STYLE["boulevard"][0], lw=4, ls=(0, (3, 1.2)), label="бульвар / пешеходный мост"),
          Line2D([], [], color=LRT_COL, lw=5, marker="o", mfc="white", mec=LRT_COL, ms=12, label="ЛРТ и станции"),
          Line2D([], [], color="#555", lw=3, ls=(0, (2, 2)), label="резерв метро (решение не принято)"),
          Line2D([], [], color="#7d3c98", lw=1.5, ls=(0, (8, 3, 1, 3)), label="ВЛ существующая; пунктир — перенос в парк БАКАД"),
          Line2D([], [], color="#1f4e9a", lw=3, ls=(0, (6, 2)), label="граница Gate"),
          Line2D([], [], ls="", marker="*", color="#f1c40f", mec="#5b2c00", ms=26, label="главный центр (Iconic)"),
          Line2D([], [], ls="", marker="D", color="#f1c40f", mec="#5b2c00", ms=14, label="подцентр: ТПУ, админцентр"),
          Line2D([], [], ls="", marker="o", color="#fdebd0", mec="#5b2c00", ms=13, label="местный центр"),
          Line2D([], [], ls="", marker="o", color="#1a5276", mec="white", ms=12, label="объект реестра: стоит / остаётся"),
          Line2D([], [], ls="", marker="o", color="#117a65", mec="white", ms=12, label="объект реестра: добавляется"),
          Line2D([], [], ls="", marker="o", color="#7b241c", mec="white", ms=12, label="объект переносится (стрелка — откуда)"),
          Line2D([], [], ls="", marker="o", color="#ffeb3b", mec="#333", ms=11, label="стык с соседом (city.json)"),
          Line2D([], [], ls="", marker="o", color="#922b21", mec="white", ms=16, label="номер очереди строительства (1–5)")]
    leg = ax.legend(handles=h, loc="upper left", bbox_to_anchor=(0.005, 0.905), fontsize=15, framealpha=0.94, borderpad=0.9, handlelength=2.6,
                    title="Условные обозначения", title_fontsize=18)
    leg.set_zorder(100)
    # right column: queues table, candidates, candidates inset — stacked top-down without overlaps
    import textwrap
    rend = fig.canvas.get_renderer()
    qt = "\n".join(f"{p['queue']}   {p['years'][0]}–{p['years'][1]}   " + p["what_ru"].split(". ")[0].split("· ")[-1] for p in spec["phases"])
    t1 = fig.text(0.74, 0.47, "Очереди 4D (сначала улицы, потом дома)\n" + qt, fontsize=15, va="top", ha="left", zorder=80,
                  bbox=dict(facecolor="white", alpha=0.95, edgecolor="#999", boxstyle="round,pad=0.6"), linespacing=1.5)
    y = (t1.get_window_extent(rend).y0 - 45) / fig.bbox.height
    txt = [f"{r['id']}: {r['name_ru']} — {r['verdict']}" if r["id"] != "ВЫБОР" else
           f"★ {r['name_ru']} ({r['x']}, {r['z']}): 0 домов, до трассы {r['gap_to_motorway_m']} м, ЛРТ {r['lrt_m']} м — выбран"
           for r in spec["checks"]["iconic_candidates"]]
    txt = "Где центр Gate: кандидаты\n" + "\n".join(textwrap.fill(t, 80, subsequent_indent="      ") for t in txt)
    t2 = fig.text(0.74, y, txt, fontsize=12.5, va="top", ha="left", zorder=80, linespacing=1.25,
                  bbox=dict(facecolor="white", alpha=0.95, edgecolor="#999", boxstyle="round,pad=0.5"))
    y2 = (t2.get_window_extent(rend).y0 - 40) / fig.bbox.height
    ia = fig.add_axes([0.74, 0.035, 0.245, y2 - 0.035])
    ia.set_facecolor("white")
    ia.add_collection(PolyCollection(_polys(G), facecolor="#e8eef7", edgecolor="#1f4e9a", linewidths=1.5))
    vz = [z["_g"] for z in zones if z["use"] == "village_existing"]
    ia.add_collection(PolyCollection(sum((_polys(g) for g in vz), []), facecolor="#cbb89a", edgecolor="none"))
    for k in ("a3", "bakad", "kaz06"):
        L = np.asarray(ax_geo[k].coords)
        ia.plot(L[:, 0], L[:, 1], color="#5d4037", lw=3)
    ia.plot(lrt[:, 0], lrt[:, 1], color=LRT_COL, lw=2.5)
    ia.add_patch(Circle(GS.ICONIC, GS.QT_R, facecolor="none", edgecolor="#c0392b", lw=2, ls="--", zorder=4))
    for r in spec["checks"]["iconic_candidates"]:
        ch = r["id"] == "ВЫБОР"
        ia.scatter([r["x"]], [r["z"]], s=700 if ch else 140, marker="*" if ch else "o", color="#f1c40f" if ch else "#444", edgecolor="k", zorder=5)
        if not ch:
            dx = -110 if r["id"] in ("K6", "K3") else 110
            ia.text(r["x"] + dx, r["z"], r["id"], fontsize=15, fontweight="bold", va="center", ha="right" if dx < 0 else "left", zorder=6,
                    path_effects=HALO)
    ia.text(-5300, -19720, "БАКАД", fontsize=13, color="#5d4037", fontweight="bold", ha="left", va="bottom", path_effects=HALO)
    ia.text(-2420, -22400, "А-3", fontsize=13, color="#5d4037", fontweight="bold", ha="right", va="center", path_effects=HALO)
    ia.set_xlim(-5400, -2150); ia.set_ylim(-23500, -18250); ia.set_aspect("equal", adjustable="datalim"); ia.set_xticks([]); ia.set_yticks([])
    ia.set_title("Кандидаты на карте (бежевое — сёла, красное — ЛРТ)", fontsize=13, fontweight="bold")
    # scale bar and north arrow
    sx, sz = x0 + 300, z0 + 250
    ax.plot([sx, sx + 1000], [sz, sz], color="k", lw=10, solid_capstyle="butt", zorder=90)
    ax.plot([sx, sx + 500], [sz, sz], color="white", lw=5, solid_capstyle="butt", zorder=91)
    ax.text(sx + 500, sz + 90, "1 км", fontsize=18, ha="center", va="bottom", zorder=92, fontweight="bold", path_effects=HALO)
    ax.annotate("С", xy=(x0 + 1700, z0 + 900), xytext=(x0 + 1700, z0 + 350), ha="center", va="center", fontsize=24, fontweight="bold",
                zorder=92, arrowprops=dict(arrowstyle="-|>", lw=4, color="k"))
    ax.text(x0 + 2200, z0 + 120, "© OpenStreetMap contributors, Overture Maps Foundation · рельеф двойника, горизонтали 5 м · система Unity X/Z · "
            "схема — модель qTwin", fontsize=11, zorder=92, va="bottom", color="#555")
    out = os.path.join(outdir, "scheme.png")
    tmp = os.path.join(outdir, ".scheme_tmp.png")
    fig.savefig(tmp, dpi=dpi)
    plt.close(fig)
    from PIL import Image   # flat colours: a 256-colour palette keeps the look and cuts the file ~3×
    if quantize:
        Image.open(tmp).convert("RGB").quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(tmp, optimize=True)
    os.replace(tmp, out)
    print(f"[gate] {out}: {W:.0f} × {H:.0f} px, {os.path.getsize(out) / 1e6:.1f} MB")
