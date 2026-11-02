#!/usr/bin/env python3
"""Intent picture of the Gate trial quarter (w47): OUT/gate_trial/intent.png from spec/gate_trial.json + open data context.

    python3 -I tools/map/district/gate_trial_draw.py [--dpi 110] [--out PATH] [--zoom x0 x1 z0 z1]
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.patches as mp  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402

import gate_common as C  # noqa: E402

ZONE_COL = {"mixed_centre": "#e9c46a", "business": "#f4a3a8", "residential_high": "#f6d6a8", "residential_mid": "#f9e2c0",
            "residential_low": "#fbefd9", "village_existing": "#e3d5c3", "logistics": "#c9c3e6", "industry": "#c9c3e6",
            "utility": "#ececec", "park": "#bfe3b4", "reserve": "#eeeeee"}
CLS_W = {"expressway": 3.2, "ramp": 1.4, "arterial_regulated": 3.0, "district_transport": 2.2, "boulevard": 2.2, "local": 1.2,
         "industrial": 1.2, "pedestrian_street": 1.4, "village_main": 1.0, "village_secondary": 0.8, "village_lane": 0.6,
         "driveway_secondary": 0.8}
CLS_COL = {"expressway": "#7a1f1f", "ramp": "#b23a3a", "arterial_regulated": "#d1495b", "district_transport": "#ef8a17",
           "boulevard": "#2a9d8f", "local": "#444444", "industrial": "#6d597a", "pedestrian_street": "#2a9d8f",
           "village_main": "#8d6e63", "village_secondary": "#8d6e63", "village_lane": "#a1887f", "driveway_secondary": "#777777"}


def main(argv):
    dpi = int(argv[argv.index("--dpi") + 1]) if "--dpi" in argv else 110
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(C.OUT, "gate_trial", "intent.png")
    spec = json.load(open(os.path.join(C.SPEC_DIR, "gate_trial.json"), encoding="utf-8"))
    area = Polygon(spec["area"])
    if "--zoom" in argv:
        i = argv.index("--zoom"); x0, x1, z0, z1 = [float(v) for v in argv[i + 1:i + 5]]
    else:
        x0, z0, x1, z1 = area.bounds; x0 -= 60; x1 += 60; z0 -= 60; z1 += 60
    V = box(x0, z0, x1, z1)
    W = 17.0
    fig, ax = plt.subplots(figsize=(W, W * (z1 - z0) / (x1 - x0) + 1.2))
    ax.set_facecolor("#fafafa")
    # zones
    for z in spec["zones"]:
        p = Polygon(z["polygon"])
        ax.fill(*p.exterior.xy, color=ZONE_COL.get(z["use"], "#eee"), lw=0, zorder=1)
        ax.plot(*p.exterior.xy, color="#bbbbbb", lw=0.4, zorder=1)
        if z["use"] not in ("utility",) and p.area > 6e4:
            q = p.representative_point()
            ax.text(q.x, q.y + 25, z["name_ru"], fontsize=7, ha="center", color="#555", zorder=9, clip_on=True)
    # keep
    for k in spec["keep"]:
        p = Polygon(k["polygon"])
        ax.fill(*p.exterior.xy, color="#e9c46a", alpha=0.9, lw=0, zorder=2)
    d = C.gate_district_bytes()
    tri = d["p"][d["idx"]]; tags = d["tg"][d["idx"][:, 0]]
    for tag, col in ((29, "#a8d5a2"), (26, "#7fbf7a"), (30, "#d6d0c4"), (31, "#5a5a5a"), (28, "#6aa6d6")):
        m = tags == tag
        if m.any():
            for t in tri[m][:: max(1, int(m.sum() / 6000))]:
                x, z = C.local_to_world(t[:, 0], t[:, 2])
                ax.fill(x, z, color=col, lw=0, zorder=3)
    for tag in range(20, 26):
        m = tags == tag
        for t in tri[m]:
            x, z = C.local_to_world(t[:, 0], t[:, 2])
            ax.fill(x, z, color="#b5651d", lw=0, zorder=3)
    # context: existing buildings, water, power lines
    for g, p in C.layer_in("buildings", V):
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "Polygon":
                ax.fill(*q.exterior.xy, color="#6d4c41", lw=0, zorder=4)
    for g, p in C.layer_in("water", V):
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "Polygon":
                ax.fill(*q.exterior.xy, color="#8ecae6", lw=0, zorder=2)
            elif q.geom_type == "LineString":
                ax.plot(*q.xy, color="#219ebc", lw=1.0, zorder=2)
    for g, p in C.layer_in("infrastructure", V):
        if p.get("class") == "power_line":
            for q in getattr(g, "geoms", [g]):
                if q.geom_type == "LineString":
                    ax.plot(*q.xy, color="#9b5de5", lw=0.8, ls=(0, (2, 3)), alpha=0.6, zorder=5)
    # views
    for v in spec["views"]:
        a = v["apex"]; t0 = math.radians(v["dir_deg"] - v["fov_deg"] / 2); t1 = math.radians(v["dir_deg"] + v["fov_deg"] / 2)
        ts = np.linspace(t0, t1, 20)
        xs = [a[0]] + [a[0] + v["len_m"] * math.sin(t) for t in ts] + [a[0]]
        zs = [a[1]] + [a[1] + v["len_m"] * math.cos(t) for t in ts] + [a[1]]
        ax.fill(xs, zs, color="#ffd166", alpha=0.25, lw=0.8, ec="#e09f3e", zorder=6)
    # streets
    for s in sorted(spec["streets"], key=lambda s: CLS_W.get(s["class"], 1)):
        L = np.array(s["line"])
        lw = CLS_W.get(s["class"], 1.0)
        col = CLS_COL.get(s["class"], "#333")
        ls = "-" if s["class"] != "pedestrian_street" else (0, (3, 2))
        ax.plot(L[:, 0], L[:, 1], color=col, lw=lw, ls=ls, zorder=7, solid_capstyle="round")
        for st in s.get("struct", []):
            if st["kind"] in ("overpass", "bridge"):
                ax.plot([st["from"][0], st["to"][0]], [st["from"][1], st["to"][1]], color="white", lw=lw + 3.5, zorder=7.5)
                ax.plot([st["from"][0], st["to"][0]], [st["from"][1], st["to"][1]], color=col, lw=lw, zorder=7.6)
    # ramps of the new interchanges as gen_network built them (OUT/gate_trial/network.json, when the pipeline has run)
    netp = os.path.join(C.OUT, "gate_trial", "network.json")
    net = json.load(open(netp, encoding="utf-8")) if os.path.exists(netp) else {"segments": []}
    new_ic = {n["id"] for n in spec["nodes"] if n["type"] in ("diamond", "partial_cloverleaf", "cloverleaf", "trumpet")}
    for sg in net["segments"]:
        if sg["class"] == "ramp" and sg.get("ic") in new_ic:
            L = np.array([q[:2] for q in sg["pts"]])
            ax.plot(L[:, 0], L[:, 1], color="#b23a3a", lw=1.4, ls=(0, (4, 2)), zorder=7)
    # LRT
    for ln in spec["lrt"]["lines"]:
        L = LineString(ln["line"])
        for sec in ln["sections"]:
            a = L.project(Point(sec["from"])); b = L.project(Point(sec["to"]))
            pts = np.array([L.interpolate(t).coords[0] for t in np.linspace(a, b, 80)])
            ax.plot(pts[:, 0], pts[:, 1], color="#0077b6", lw=2.4 if sec["kind"] == "ground" else 3.6,
                    ls="-" if sec["kind"] == "ground" else (0, (1.2, 0.8)), zorder=8)
        for st in ln["stations"]:
            ax.add_patch(mp.Rectangle((st["x"] - 9, st["z"] - 45), 18, 90, color="#0077b6", zorder=9))
            ax.text(st["x"] + 22, st["z"], "ЛРТ «%s»" % st["name_ru"], fontsize=8, color="#03045e", zorder=10, va="center",
                    fontweight="bold", clip_on=True)
    # objects
    for o in spec["objects"]:
        if o.get("footprint") and o.get("registry_id") not in ("gate_district_ring",):
            p = Polygon(o["footprint"])
            ax.plot(*p.exterior.xy, color="#1d3557", lw=1.1, zorder=8)
            k = o.get("kind")
            lab = {"school": "школа", "kindergarten": "д/с", "polyclinic": "поликл.", "fire_station": "пож. депо",
                   "transit": "", "parking": "P+R", "logistics": "", "business": "", "landmark": ""}.get(k, "")
            if k in ("transit", "logistics", "business", "landmark"):
                lab = o["name_ru"].split("(")[0].split("—")[0][:34]
            if lab:
                c = p.centroid
                ax.text(c.x, c.y, lab, fontsize=7, ha="center", va="center", color="#1d3557", zorder=10, clip_on=True,
                        bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.5))
    # utilities
    for u in spec.get("utilities", []):
        L = np.array(u["line"])
        ax.plot(L[:, 0], L[:, 1], color="#7b2cbf", lw=1.6, ls=(0, (6, 2, 1, 2)), zorder=6)
    # nodes of interest
    for n in spec["nodes"]:
        if n["type"] in ("diamond", "cloverleaf", "grade_separation", "roundabout"):
            ax.plot(n["x"], n["z"], "o", ms=9 if n["type"] != "roundabout" else 7, mfc="white", mec="#7a1f1f", mew=1.6, zorder=11)
    # area and edge joints
    ax.plot(*area.exterior.xy, color="#d00000", lw=1.8, ls=(0, (6, 3)), zorder=12)
    for e in spec["edge_joints"]:
        ax.plot(e["x"], e["z"], "s", ms=4 if e.get("street") else 2.5, color="#d00000" if e.get("street") else "#f4978e", zorder=12)
    # labels of streets
    LBL = {"s_west_ave": "Западный проспект", "s_ave": "Проспект Ворот", "s_bakad_st": "улица вдоль БАКАД", "s_dubler": "дублёр А-3",
           "s_east": "Восточная ул. + ЛРТ", "s_north": "Северная улица", "s_park": "Парковая улица", "s_boulevard": "Бульвар Gate",
           "s_south_link": "Южный проезд", "s_ped_bridge": "пеш. мост", "s_tpu1": "улица ТПУ"}
    for s in spec["streets"]:
        if s["id"] in LBL:
            L = LineString(s["line"]); p = L.interpolate(0.42, normalized=True); q = L.interpolate(min(1, 0.42 + 0.02), normalized=True)
            ang = math.degrees(math.atan2(q.y - p.y, q.x - p.x))
            ang = ang - 180 if ang > 90 else (ang + 180 if ang < -90 else ang)
            ax.text(p.x, p.y, LBL[s["id"]], fontsize=8.5, rotation=ang, rotation_mode="anchor", ha="center", va="bottom",
                    color="#222", fontweight="bold", zorder=13, clip_on=True,
                    bbox=dict(fc="white", ec="none", alpha=0.7, pad=0.4))
    notes = [((-2270, -20315), "развязка А-3 × БАКАД\n(существующая, OSM)"), ((-3970, -20013), "новый неполный клевер B2\nЗап. проспект × БАКАД"),
             ((-3500, -19500), "Iconic\n(квартал Gate District, keep)"), ((-3020, -20112), "путепровод +\nэстакада ЛРТ")]
    for (x, z), t in notes:
        ax.annotate(t, (x, z), xytext=(x + 140, z + 150), fontsize=8.5, color="#7a1f1f", fontweight="bold", zorder=14,
                    arrowprops=dict(arrowstyle="-", color="#7a1f1f", lw=0.8), bbox=dict(fc="white", ec="#7a1f1f", lw=0.6, alpha=0.85))
    ax.set_xlim(x0, x1); ax.set_ylim(z0, z1); ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.set_xlabel("X, м (восток)", fontsize=8); ax.set_ylabel("Z, м (север)", fontsize=8)
    leg = [Line2D([0], [0], color=CLS_COL[c], lw=CLS_W[c], label=t) for c, t in
           (("expressway", "скоростная (БАКАД, А-3), OSM"), ("ramp", "съезд"), ("arterial_regulated", "магистраль регулируемая"),
            ("district_transport", "улица районного значения"), ("local", "местная улица"), ("boulevard", "бульвар / пешеходная"),
            ("village_secondary", "улица села (OSM)"))]
    leg += [Line2D([0], [0], color="#b23a3a", lw=1.4, ls=(0, (4, 2)), label="съезды новой развязки (gen_network, шаблон)"),
            Line2D([0], [0], color="#0077b6", lw=2.4, label="ЛРТ на земле"), Line2D([0], [0], color="#0077b6", lw=3.6, ls=(0, (1.2, 0.8)), label="ЛРТ на эстакаде"),
            Line2D([0], [0], color="#7b2cbf", lw=1.6, ls=(0, (6, 2, 1, 2)), label="кабель 220 кВ (вместо ВЛ)"),
            Line2D([0], [0], color="#d00000", lw=1.8, ls=(0, (6, 3)), label="граница пробной зоны (area)"),
            mp.Patch(color="#ffd166", alpha=0.4, label="сектор обзора фасада"), mp.Patch(color="#6d4c41", label="существующие здания (OSM/Overture)")]
    leg += [mp.Patch(color=ZONE_COL[u], label=t) for u, t in (("business", "деловая"), ("residential_high", "жильё многоэтажное"),
                                                               ("park", "парк"), ("logistics", "логистика"), ("village_existing", "село"),
                                                               ("residential_low", "малоэтажное"))]
    ax.legend(handles=leg, loc="lower left", fontsize=7.5, framealpha=0.92, ncol=2)
    ax.set_title("Gate · пробная зона у Iconic — замысел картографа (spec v1, gate_trial.json)", fontsize=12, loc="left")
    ax.text(0.0, -0.045, "Модель qTwin поверх открытых данных: " + C.ATTRIBUTION + ". Квартал Gate District — данные двойника, сдвиг Δ = (−330, −420).",
            fontsize=7.5, color="#555", transform=ax.transAxes, va="top")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out + ".tmp.png", dpi=dpi, bbox_inches="tight")
    os.replace(out + ".tmp.png", out)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1:])
