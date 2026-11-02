"""Check pictures of level 0: OUT/city_overview.png (whole city, 10 m/px) and OUT/gate_overview.png (Gate, 2 m/px).

    python3 -I tools/map/geo/render_maps.py            (build_city.py runs it at the end)

North up, Unity X to the right, Z up; legend, scale bar. Layers: districts, water, existing roads by class (OSM), rail, power
lines, settlements, trunk draft and LRT draft of the twin, joints, Iconic, the Gate centre; Gate also OSM buildings and the
twin's existing buildings."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import frames  # noqa: E402
import layers  # noqa: E402
import twin  # noqa: E402

DCOL = {"gate": "#2e63b0", "golden": "#d9a621", "growing_w": "#f27336", "growing_e": "#e0884f", "green": "#339e5c"}
ROAD_STYLE = {  # class: (colour, width at 10 m/px in points, z)
    "motorway": ("#c0392b", 2.6, 9), "trunk": ("#d35400", 2.3, 9), "primary": ("#e67e22", 1.8, 8), "secondary": ("#f1c40f", 1.4, 7),
    "tertiary": ("#9a7d0a", 1.0, 6), "residential": ("#555555", 0.45, 5), "living_street": ("#555555", 0.45, 5), "unclassified": ("#777777", 0.45, 5),
    "service": ("#999999", 0.3, 4), "track": ("#a68a64", 0.3, 3), "unknown": ("#999999", 0.3, 3)}
TRUNK_COL = {"highway": "#1f3a93", "ring": "#8e44ad", "main": "#2980b9"}


def _lines(geoms):
    segs = []
    for g in geoms:
        for q in getattr(g, "geoms", [g]):
            if q.geom_type in ("LineString", "LinearRing") and len(q.coords) >= 2:
                segs.append(np.asarray(q.coords))
            elif q.geom_type == "Polygon":
                segs.append(np.asarray(q.exterior.coords))
    return segs


def _polys(geoms):
    out = []
    for g in geoms:
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "Polygon" and not q.is_empty:
                out.append(np.asarray(q.exterior.coords))
    return out


def scale_bar(ax, x0, z0, length, label, lw=4):
    ax.plot([x0, x0 + length], [z0, z0], color="k", lw=lw, solid_capstyle="butt", zorder=50)
    ax.plot([x0, x0 + length / 2], [z0, z0], color="w", lw=lw * 0.5, solid_capstyle="butt", zorder=51)
    ax.text(x0 + length / 2, z0 + length * 0.06, label, ha="center", va="bottom", fontsize=14, zorder=52,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"))


def north_arrow(ax, x, z, size):
    ax.annotate("N", xy=(x, z + size), xytext=(x, z), ha="center", va="center", fontsize=20, fontweight="bold", zorder=52,
                arrowprops=dict(arrowstyle="-|>", lw=3, color="k"))


def draw(ax, spec, box, mpp, gate_mode=False):
    x0, z0, x1, z1 = box
    clip = shapely.box(x0, z0, x1, z1)
    k = 10.0 / mpp          # line widths scale with the resolution
    k = min(k, 2.5)
    # districts
    dg, dp = layers.load("derived/districts")
    for g, p in zip(dg, dp):
        if p["id"] in DCOL:
            ax.add_collection(PolyCollection(_polys([g]), facecolor=DCOL[p["id"]], alpha=0.10, edgecolor="none", zorder=1))
    for g, p in zip(dg, dp):
        if p["id"] in ("gate", "golden", "growing", "green"):
            ax.add_collection(LineCollection(_lines([g.exterior]), colors=DCOL.get(p["id"], "#f27336"), linewidths=3.0 * k, zorder=20, alpha=0.9))
        elif p["id"].endswith("_geojson"):
            ax.add_collection(LineCollection(_lines([g.exterior if g.geom_type == "Polygon" else shapely.MultiLineString([q.exterior for q in g.geoms])]),
                                             colors="#444444", linewidths=1.0 * k, linestyles=(0, (6, 6)), zorder=19, alpha=0.6))
        elif p["id"] == "growing_split":
            ax.add_collection(LineCollection(_lines([g]), colors="#f27336", linewidths=2.2 * k, linestyles=(0, (4, 3)), zorder=21))
    # land use hint: water
    wg, wp = layers.load("water")
    sel = shapely.intersects(clip, wg)
    polys = [g for g, s in zip(wg, sel) if s and g.geom_type in ("Polygon", "MultiPolygon")]
    lines = [g for g, s, p in zip(wg, sel, wp) if s and g.geom_type in ("LineString", "MultiLineString")]
    ax.add_collection(PolyCollection(_polys(polys), facecolor="#9cc9e8", edgecolor="#4a90c2", linewidths=0.4, zorder=2))
    ax.add_collection(LineCollection(_lines(lines), colors="#3d8fd1", linewidths=0.9 * k, zorder=3))
    # settlements
    sg, sp = layers.load("derived/settlements")
    for g, p in zip(sg, sp):
        if not g.intersects(clip):
            continue
        ax.add_collection(LineCollection(_lines([g.exterior if g.geom_type == "Polygon" else shapely.MultiLineString([q.exterior for q in g.geoms])]),
                                         colors="#8b5a2b", linewidths=1.2 * k, linestyles=(0, (2, 2)), zorder=12))
        c = g.representative_point()
        if clip.contains(c) and (p.get("share_in_city", 0) > 0 or gate_mode):
            ax.text(c.x, c.y, p["name"], fontsize=11 if not gate_mode else 18, color="#5b3a1a", ha="center", va="center", zorder=40,
                    bbox=dict(facecolor="white", alpha=0.55, edgecolor="none", pad=0.5))
    # buildings (Gate only)
    if gate_mode:
        bg, bp = layers.load("buildings")
        sel = shapely.intersects(clip, bg)
        ax.add_collection(PolyCollection(_polys(bg[sel]), facecolor="#b9b2a6", edgecolor="#8c857a", linewidths=0.2, zorder=10))
        B = twin.buildings()
        ex = B[(B.source == "existing_osm") & (B.x > x0) & (B.x < x1) & (B.z > z0) & (B.z < z1)]
        fp = twin.footprints(ex.bid.values)
        ax.add_collection(PolyCollection(_polys(fp.values()), facecolor="none", edgecolor="#1f5fbf", linewidths=0.5, zorder=11))
    # existing roads by class
    rg, rp = layers.load("roads")
    sel = np.flatnonzero(shapely.intersects(clip, rg))
    byc = {}
    for i in sel:
        byc.setdefault(rp[i].get("class", "unknown"), []).append(rg[i])
    for c, gs in byc.items():
        col, w, z = ROAD_STYLE.get(c, ROAD_STYLE["unknown"])
        ax.add_collection(LineCollection(_lines(gs), colors=col, linewidths=w * k, zorder=z, capstyle="round"))
    br = [rg[i] for i in sel if rp[i].get("bridge")]
    ax.add_collection(LineCollection(_lines(br), colors="#000000", linewidths=3.2 * k, zorder=8.5, alpha=0.6))
    # rail
    rl, _ = layers.load("rail")
    sel = shapely.intersects(clip, rl)
    ax.add_collection(LineCollection(_lines(rl[sel]), colors="#222222", linewidths=1.6 * k, zorder=13))
    ax.add_collection(LineCollection(_lines(rl[sel]), colors="#ffffff", linewidths=0.7 * k, linestyles=(0, (4, 4)), zorder=13.1))
    # power lines
    ig, ip = layers.load("infrastructure")
    pl = [g for g, p in zip(ig, ip) if p.get("class") in ("power_line", "minor_line") and g.intersects(clip)]
    ax.add_collection(LineCollection(_lines(pl), colors="#8e44ad", linewidths=0.8 * k, linestyles=(0, (8, 3, 1, 3)), zorder=14, alpha=0.9))
    subs = [g for g, p in zip(ig, ip) if p.get("class") == "substation" and g.intersects(clip)]
    ax.add_collection(PolyCollection(_polys(subs), facecolor="#8e44ad", edgecolor="#5b2c6f", alpha=0.7, zorder=14))
    # trunk draft (twin)
    tg, tp = layers.load("derived/trunk_v0")
    for c, col in TRUNK_COL.items():
        gs = [g for g, p in zip(tg, tp) if p["class"] == c and g.intersects(clip)]
        ax.add_collection(LineCollection(_lines(gs), colors=col, linewidths=(2.8 if c != "main" else 1.8) * k, zorder=15, alpha=0.55))
    # LRT draft
    lg, lp = layers.load("derived/lrt_v0")
    routes = [g for g, p in zip(lg, lp) if p["kind"] == "route"]
    ax.add_collection(LineCollection(_lines(routes), colors="#e91e63", linewidths=2.2 * k, zorder=16, linestyles=(0, (6, 2))))
    st = np.array([(g.x, g.y) for g, p in zip(lg, lp) if p["kind"] == "station"])
    ax.scatter(st[:, 0], st[:, 1], s=60 * k, marker="s", facecolor="white", edgecolor="#e91e63", linewidths=1.5, zorder=17)
    # joints
    J = spec["joints"]["items"]
    jk = {"road": ("o", "#1f3a93"), "rail": ("D", "#222222"), "lrt": ("^", "#e91e63")}
    for kind, (mk, col) in jk.items():
        pts = np.array([(j["x"], j["z"]) for j in J if j["kind"] == kind])
        if len(pts):
            ax.scatter(pts[:, 0], pts[:, 1], s=90 * k, marker=mk, facecolor="#ffeb3b", edgecolor=col, linewidths=1.6, zorder=30)
    # Iconic and the Gate centre
    ic = spec["iconic"]
    ax.scatter([ic["x"]], [ic["z"]], s=520 * k, marker="*", color="#d4ac0d", edgecolor="k", linewidths=1.2, zorder=45)
    ax.text(ic["x"] + 120 / (10 / mpp) * 1.5, ic["z"], "Iconic", fontsize=16, fontweight="bold", zorder=46, va="center",
            bbox=dict(facecolor="white", alpha=0.75, edgecolor="none"))
    gc = spec["centres"]["gate"]
    for key, mk, lab in (("centroid", "P", "центроид Gate"), ("pole_of_inaccessibility", "X", "полюс недоступности Gate")):
        x, z = gc[key]
        ax.scatter([x], [z], s=300 * k, marker=mk, color="#2e63b0", edgecolor="white", linewidths=1.2, zorder=44)
    for af in spec["height_limits"]["airfields"]:
        if x0 < af["x"] < x1 and z0 < af["y" if False else "z"] < z1:
            ax.scatter([af["x"]], [af["z"]], s=200 * k, marker="^", color="#7f8c8d", edgecolor="k", zorder=42)
            ax.text(af["x"], af["z"] - 250 * mpp / 10 * 2, "аэродром", fontsize=10, ha="center", va="top", zorder=42)
    ax.set_xlim(x0, x1); ax.set_ylim(z0, z1); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])


def legend(ax, gate_mode):
    h = [Patch(facecolor=DCOL[k], alpha=0.35, edgecolor=DCOL[k], label=n) for k, n in
         (("gate", "Gate"), ("golden", "Golden"), ("growing_w", "Growing-запад"), ("growing_e", "Growing-восток"), ("green", "Green"))]
    h += [Line2D([], [], color="#444444", lw=1.5, ls=(0, (6, 6)), label="районы по geojson генплана (альтернатива)"),
          Line2D([], [], color="#f27336", lw=3, ls=(0, (4, 3)), label="ось деления Growing (А-3)"),
          Patch(facecolor="#9cc9e8", edgecolor="#4a90c2", label="вода (OSM)")]
    for c in ("motorway", "trunk", "primary", "secondary", "tertiary", "residential", "track"):
        col, w, _ = ROAD_STYLE[c]
        h.append(Line2D([], [], color=col, lw=max(1.2, w * 1.5), label=f"дорога OSM: {c}"))
    h += [Line2D([], [], color="#000000", lw=4, alpha=0.6, label="мост (OSM)"),
          Line2D([], [], color="#222222", lw=3, label="железная дорога (OSM)"),
          Line2D([], [], color="#8e44ad", lw=1.5, ls=(0, (8, 3, 1, 3)), label="ЛЭП (OSM), ■ подстанция"),
          Line2D([], [], color="#8b5a2b", lw=2, ls=(0, (2, 2)), label="посёлок (OSM / модель)")]
    if gate_mode:
        h += [Patch(facecolor="#b9b2a6", edgecolor="#8c857a", label="здание OSM (Overture)"),
              Patch(facecolor="none", edgecolor="#1f5fbf", label="существующее здание двойника (existing_osm)")]
    h += [Line2D([], [], color=TRUNK_COL["highway"], lw=4, alpha=0.55, label="черновик: трасса двойника (highway)"),
          Line2D([], [], color=TRUNK_COL["ring"], lw=4, alpha=0.55, label="черновик: кольцо (ring)"),
          Line2D([], [], color=TRUNK_COL["main"], lw=3, alpha=0.55, label="черновик: магистраль (main)"),
          Line2D([], [], color="#e91e63", lw=3, ls=(0, (6, 2)), marker="s", mfc="white", label="черновик: ЛРТ и станции"),
          Line2D([], [], ls="", marker="o", mfc="#ffeb3b", mec="#1f3a93", ms=10, label="стык: магистраль × граница"),
          Line2D([], [], ls="", marker="D", mfc="#ffeb3b", mec="#222222", ms=9, label="стык: ж/д × граница"),
          Line2D([], [], ls="", marker="^", mfc="#ffeb3b", mec="#e91e63", ms=10, label="стык: ЛРТ × граница"),
          Line2D([], [], ls="", marker="*", color="#d4ac0d", mec="k", ms=18, label="Iconic (−3170, −19080)"),
          Line2D([], [], ls="", marker="P", color="#2e63b0", ms=13, label="центроид Gate"),
          Line2D([], [], ls="", marker="X", color="#2e63b0", ms=13, label="полюс недоступности Gate")]
    leg = ax.legend(handles=h, loc="upper left", fontsize=22 if gate_mode else 20, framealpha=0.92, ncol=1, borderpad=0.8, markerscale=1.4, handlelength=3)
    leg.set_zorder(1000)


def render(spec, box, mpp, path, title, gate_mode=False):
    x0, z0, x1, z1 = box
    W = (x1 - x0) / mpp; H = (z1 - z0) / mpp
    dpi = 100
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#f7f5ef")
    draw(ax, spec, box, mpp, gate_mode)
    legend(ax, gate_mode)
    L = 5000 if not gate_mode else 1000
    scale_bar(ax, x1 - (x1 - x0) * 0.05 - L, z0 + (z1 - z0) * 0.02, L, f"{L / 1000:.0f} км" if L >= 1000 else f"{L} м", lw=10)
    north_arrow(ax, x1 - (x1 - x0) * 0.04, z1 - (z1 - z0) * 0.08, (z1 - z0) * 0.035)
    ax.text(x0 + (x1 - x0) * 0.5, z1 - (z1 - z0) * 0.008, title, ha="center", va="top", fontsize=22, fontweight="bold", zorder=60,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"))
    ax.text(x0 + (x1 - x0) * 0.01, z0 + (z1 - z0) * 0.005, "© OpenStreetMap contributors, Overture Maps Foundation · двойник Alatau (черновики) · "
            f"система Unity X/Z, {mpp:g} м/пикс.", fontsize=11, zorder=60, va="bottom", bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"))
    tmp = path + ".tmp.png"
    fig.savefig(tmp, dpi=dpi)
    plt.close(fig)
    os.replace(tmp, path)
    print(f"[render] {path}: {W:.0f} × {H:.0f} px, {os.path.getsize(path) / 1e6:.1f} MB")


def main():
    spec = json.load(open(os.path.join(frames.SPEC_DIR, "city.json"), encoding="utf-8"))
    D, _ = twin.district_polygons()
    city = twin.city_outline(D)
    x0, z0, x1, z1 = city.bounds
    m = 1500
    render(spec, (x0 - m, z0 - m, x1 + m, z1 + m), 10.0, frames.out("city_overview.png"),
           "Alatau City · уровень 0: районы, вода, существующая сеть (OSM), черновик магистралей и ЛРТ, стыки")
    gx0, gz0, gx1, gz1 = D["Gate"].bounds
    m = 300
    render(spec, (gx0 - m, gz0 - m, gx1 + m, gz1 + m), 2.0, frames.out("gate_overview.png"),
           "Gate · уровень 0: здания OSM и существующие здания двойника, сеть, черновики, стыки, Iconic и центр района", gate_mode=True)


if __name__ == "__main__":
    main()
