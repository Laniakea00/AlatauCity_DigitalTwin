#!/usr/bin/env python3
"""Pictures of the whole Golden district (w50; gate_draw.py of w47 for Golden) from the pipeline outputs in OUT/golden (network, lrt, lots, buildings, driveways,
features) and spec/golden.json, at an exact scale:

    python3 -I tools/map/district/golden_draw.py            # overview.png at 10 m/px + three 2 × 2 km tiles at 1 m/px
    python3 -I tools/map/district/golden_draw.py --overview # only the overview
    python3 -I tools/map/district/golden_draw.py --tile x0 z0 [name]   # one 2 × 2 km tile with its south-west corner at (x0, z0)

The map area of each picture has exactly the stated metres per pixel; the legend sits in a strip to the right of it.
Tiles: the centre (K-Park, C1) and the two densest 2 × 2 km windows by homes + jobs per km² that overlap neither the
centre tile nor each other by more than a quarter (written to OUT/golden/tiles/tiles.json with their numbers).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.patches import Polygon as MPoly  # noqa: E402
from shapely.geometry import Polygon, box  # noqa: E402

import golden_common as C  # noqa: E402
import land_util as U  # noqa: E402

D = "golden"
OD = os.path.join(C.OUT, D)
CENTRE = (-850.0, -8800.0)       # C1 «Центр Golden у K-Park», the main centre of the scheme
TILE = 2000.0
LEGEND_PX = 330

USE_COL = {"residential_high": "#f0b48a", "residential_mid": "#f5cda6", "residential_low": "#f8e0c2", "mixed_centre": "#e9967a",
           "business": "#c3b5e0", "logistics": "#d5d0c6", "industry": "#c9c1b3", "village_existing": "#f1e9cf", "utility": "#e2e2e2",
           "park": "#c3e3b3", "square": "#a9d695", "playground": "#a9d695", "reserve": "#efefef", "landmark": "#f6e6a4",
           "school": "#8fb3e0", "kindergarten": "#b0cdee", "polyclinic": "#e79aa5", "hospital": "#e79aa5", "pharmacy_shop": "#f2c983",
           "fire_station": "#c46a83", "transit": "#bdbdbd", "waterfront": "#b5dfe1", "parking": "#d0d0d0", "sport": "#cfe6b8",
           "medical": "#f1c0c8", "campus": "#d9cdea"}
PK_COL = {"surface": "#6b6b6b", "multi": "#2a9d8f", "underground": "#264653"}
GREEN_COL = {"park": "#6aaa5a", "square": "#4f9a45", "yard": "#9acb90", "buffer": "#b4cfad", "boulevard": "#6aaa5a", "sport": "#7aa95e"}
USE_RU = {"residential_high": "жильё многоэтажное", "residential_mid": "жильё среднеэтажное", "residential_low": "жильё малоэтажное",
          "mixed_centre": "смешанная центральная", "business": "деловая", "logistics": "логистика", "industry": "производство",
          "village_existing": "село (существующее)", "utility": "инженерная, полосы отвода", "park": "парк", "square": "сквер, площадь",
          "playground": "площадка", "reserve": "резерв", "landmark": "ориентир (keep, двойник)", "school": "школа", "kindergarten": "детский сад",
          "polyclinic": "поликлиника", "hospital": "больница", "pharmacy_shop": "аптека, магазин", "fire_station": "пожарное депо",
          "transit": "ТПУ, транспорт", "waterfront": "набережная", "parking": "паркинг", "sport": "спорт", "medical": "медицина", "campus": "кампус"}
SOCIAL = {"school", "kindergarten", "polyclinic", "hospital", "fire_station", "clinic", "pharmacy_shop"}


def rd(n):
    p = os.path.join(OD, n + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def patches(polys, **kw):
    return PatchCollection([MPoly(np.asarray(p)[:, :2], closed=True) for p in polys if p is not None and len(p) >= 3], **kw)


def gcoords(g):
    out = []
    for q in getattr(g, "geoms", [g]):
        if q.geom_type == "Polygon" and not q.is_empty:
            out.append(list(q.exterior.coords))
    return out


class Data:
    def __init__(self):
        self.spec = json.load(open(os.path.join(C.SPEC_DIR, D + ".json"), encoding="utf-8"))
        self.net, self.lrt, self.lots, self.bld, self.feat, self.drv = (rd(n) for n in ("network", "lrt", "lots", "buildings", "features", "driveways"))
        self.area = Polygon(self.spec["area"])
        norms = U.Norms()
        self.red = [(s, p, lv) for s, p, lv in U.network_polys(self.net, norms, "red")]
        self.car = [(s, p, lv) for s, p, lv in U.network_polys(self.net, norms, "carriage")]
        self.dcar = [p for _, p, _ in U.network_polys(self.drv, norms, "carriage")] if self.drv.get("segments") else []
        self.corr = U.corridors(self.spec)


def draw(Dt, x0, z0, x1, z1, mpp, out, title, labels=True):
    V = box(x0, z0, x1, z1)
    wpx, hpx = int(round((x1 - x0) / mpp)), int(round((z1 - z0) / mpp))
    dpi = 100
    fig = plt.figure(figsize=((wpx + LEGEND_PX) / dpi, max(hpx, 900) / dpi), dpi=dpi)
    fh = max(hpx, 900)
    ax = fig.add_axes([0, (fh - hpx) / fh, wpx / (wpx + LEGEND_PX), hpx / fh])
    ax.set_xlim(x0, x1); ax.set_ylim(z0, z1); ax.set_aspect("auto"); ax.axis("off")
    ax.add_patch(MPoly([[x0, z0], [x1, z0], [x1, z1], [x0, z1]], closed=True, fc="#f4f4f2", ec="none", zorder=0))
    fine = mpp <= 2.0
    lw = 1.0 / mpp if fine else 0.0
    inV = lambda poly: poly is not None and len(poly) >= 3 and Polygon(np.asarray(poly)[:, :2]).intersects(V)  # noqa: E731
    by_use = {}
    for L in Dt.lots.get("lots", []):
        if inV(L["polygon"]):
            by_use.setdefault(L["use"], []).append(L["polygon"])
    for u, ps in by_use.items():
        ax.add_collection(patches(ps, facecolor=USE_COL.get(u, "#eeeeee"), edgecolor="#ffffff", linewidth=0.25 if fine else 0, zorder=1))
    ax.add_collection(patches([c for _, p, lv in Dt.red if lv == 0 and p.intersects(V) for c in gcoords(p)],
                              facecolor="#ffffff", edgecolor="none", zorder=2))
    for lv, col, z in ((0, "#9b9b9b", 3), (-1, "#b9b9b9", 2.9), (1, "#7d7d7d", 3.3)):
        ps = [c for s, p, l_ in Dt.car if l_ == lv and p.intersects(V) for c in gcoords(p)]
        ax.add_collection(patches(ps, facecolor=col, edgecolor="#555555" if lv == 1 and fine else "none", linewidth=0.4, zorder=z))
    if fine:
        ax.add_collection(patches([c for p in Dt.dcar if p.intersects(V) for c in gcoords(p)] +
                                  [pd["polygon"] for pd in Dt.drv.get("pads", []) if inV(pd["polygon"])],
                                  facecolor="#cdb889", edgecolor="none", zorder=3.5))
    for g in Dt.feat.get("greens", []):
        if inV(g["polygon"]):
            ax.add_collection(patches([g["polygon"]], facecolor=GREEN_COL.get(g["kind"], "#9acb90"), edgecolor="none",
                                      alpha=0.75 if g["kind"] != "yard" else 0.6, zorder=4))
    for p_ in Dt.feat.get("parking", []):
        if not inV(p_["polygon"]):
            continue
        st = dict(facecolor=PK_COL[p_["type"]], edgecolor="none", alpha=0.85, zorder=5) if p_["type"] != "underground" else \
            dict(facecolor="none", edgecolor=PK_COL["underground"], linewidth=0.5 if fine else 0.25, linestyle=":", zorder=5)
        ax.add_collection(patches([p_["polygon"]], **st))
    old, new, soc = [], [], []
    for b in Dt.bld.get("buildings", []):
        if not inV(b["footprint"]):
            continue
        if b.get("kind") in SOCIAL or b.get("use") in SOCIAL:
            soc.append(b["footprint"])
        elif b["source"] == "existing_osm":
            old.append(b["footprint"])
        else:
            new.append(b["footprint"])
    ax.add_collection(patches(old, facecolor="#8d7b68", edgecolor="none", zorder=6))
    ax.add_collection(patches(new, facecolor="#3a3a3a", edgecolor="none", zorder=6))
    ax.add_collection(patches(soc, facecolor="#1d4e89", edgecolor="#ffffff" if fine else "none", linewidth=0.5, zorder=7))
    for c in Dt.corr:
        L = np.asarray(c["line"])
        ax.plot(L[:, 0], L[:, 1], color="#6a040f" if c["state"] == "overhead" else "#7b2cbf", lw=1.2 if fine else 0.8,
                ls="--" if c["state"] == "overhead" else (0, (5, 2, 1, 2)), zorder=8)
    for Ln in Dt.lrt.get("lines", []):
        P = np.asarray(Ln["pts"])
        ax.plot(P[:, 0], P[:, 1], color="#c1121f", lw=2.6 if fine else 1.6, zorder=8.5)
        for st in Ln.get("stations", []):
            ax.plot(st["x"], st["z"], marker="s", ms=7 if fine else 4.5, color="#c1121f", mec="white", mew=0.8, zorder=9.5)
            if labels:
                ax.text(st["x"] + 6 * mpp, st["z"], "ЛРТ «%s»" % st.get("name_ru", st["id"]), fontsize=9 if fine else 6.5, color="#7a0010",
                        fontweight="bold", zorder=12, clip_on=True, va="center", bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.3))
    for dp in Dt.lrt.get("depots", []):
        if dp.get("polygon"):
            ax.add_collection(patches([dp["polygon"]], facecolor="none", edgecolor="#c1121f", linewidth=1.0, zorder=8.4))
    stops = Dt.feat.get("stops", [])
    for kind, mk, col, ms in (("bus", "o", "#000000", 3.5 if fine else 1.6), ("rail", "D", "#003049", 6 if fine else 4)):
        pts = [(s["x"], s["z"]) for s in stops if s["kind"] == kind]
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], ls="none", marker=mk, ms=ms, color=col, zorder=9)
    for k in Dt.spec.get("keep", []):
        kp = np.asarray(k["polygon"] + [k["polygon"][0]])
        ax.plot(kp[:, 0], kp[:, 1], color="#b08900", lw=1.6 if fine else 0.9, zorder=10)
    ax.plot(*Dt.area.exterior.xy, color="#d00000", lw=2.0 if fine else 1.2, ls=(0, (6, 3)), zorder=11)
    if labels:
        for o in Dt.spec.get("objects", []):
            x, z = o.get("x"), o.get("z")
            if o.get("footprint"):
                c = Polygon(o["footprint"]).centroid; x, z = c.x, c.y
            if x is None or not V.buffer(-30 * mpp).contains(Polygon([(x - 1, z - 1), (x + 1, z - 1), (x + 1, z + 1)])):
                continue
            if fine or o.get("kind") in (None, "landmark", "transit", "hospital", "logistics", "business") and o.get("geom") != "line":
                name = o.get("name_ru", o["registry_id"]).split("(")[0].split("—")[0].strip()[:38]
                if o.get("geom") == "line" or o["registry_id"].startswith(("road_", "settlement_", "district_", "river_", "canals_", "hv_")):
                    continue
                ax.text(x, z, name, fontsize=8 if fine else 5.5, ha="center", va="center", color="#1d3557", zorder=12, clip_on=True,
                        bbox=dict(fc="white", ec="#1d3557", lw=0.4, alpha=0.8, pad=0.3))
    # scale bar
    sb = 500.0 if not fine else 200.0
    bx, bz = x0 + 40 * mpp, z0 + 40 * mpp
    ax.plot([bx, bx + sb], [bz, bz], color="black", lw=3, zorder=13, solid_capstyle="butt")
    ax.text(bx + sb / 2, bz + 12 * mpp, f"{int(sb)} м", ha="center", fontsize=8, zorder=13)
    # legend strip
    lg = fig.add_axes([wpx / (wpx + LEGEND_PX), 0, LEGEND_PX / (wpx + LEGEND_PX), 1]); lg.axis("off")
    cu = {}
    for L in Dt.lots.get("lots", []):
        cu[L["use"]] = cu.get(L["use"], 0) + 1
    h = [Patch(color=USE_COL.get(u, "#eee"), label=USE_RU.get(u, u)) for u in sorted(cu, key=lambda u: -cu[u])[:18]]
    h += [Patch(color="#3a3a3a", label="новое здание (модель qTwin)"), Patch(color="#8d7b68", label="существующий дом (OSM/Overture/двойник)"),
          Patch(color="#1d4e89", label="школа, д/с, поликлиника, пожарное депо"), Patch(color="#9b9b9b", label="проезжая часть"),
          Patch(color="#ffffff", ec="#cccccc", label="красные линии"), Patch(color="#cdb889", label="проезды и площадки (land_driveways)"),
          Patch(color=GREEN_COL["park"], label="парк, сквер"), Patch(color=GREEN_COL["yard"], label="двор"),
          Patch(color=PK_COL["surface"], label="парковка открытая"), Patch(color=PK_COL["multi"], label="паркинг многоуровневый"),
          Line2D([], [], color=PK_COL["underground"], ls=":", label="паркинг подземный (контур)"),
          Line2D([], [], color="#c1121f", lw=2, marker="s", label="ЛРТ, станции"), Line2D([], [], color="#000", marker="o", ls="none", ms=3, label="остановка автобуса"),
          Line2D([], [], color="#6a040f", ls="--", label="ВЛ (OSM)"), Line2D([], [], color="#7b2cbf", ls=(0, (5, 2, 1, 2)), label="кабель 220 кВ (вместо ВЛ)"),
          Line2D([], [], color="#b08900", lw=1.6, label="сохраняемый квартал (keep)"), Line2D([], [], color="#d00000", ls=(0, (6, 3)), label="граница района")]
    lg.legend(handles=h, loc="upper left", fontsize=7.5, frameon=False, title=title, title_fontsize=8.5, alignment="left")
    T = Dt.bld.get("totals", {})
    lg.text(0.03, 0.02, f"{mpp:g} м/пкс · окно X {x0:.0f}…{x1:.0f}, Z {z0:.0f}…{z1:.0f}\nдомов {T.get('homes')}, мест работы {T.get('jobs')}\n"
            "Модель qTwin поверх открытых данных:\n" + C.ATTRIBUTION[:120], fontsize=6.5, color="#444", transform=lg.transAxes, va="bottom", wrap=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out + ".tmp.png", dpi=dpi)
    plt.close(fig)
    os.replace(out + ".tmp.png", out)
    print("wrote", out, f"({wpx}×{hpx} px map, {mpp:g} m/px)")


def densest(Dt, n=2, avoid=()):
    """The n densest 2 × 2 km windows (homes + jobs per km²) inside the district, overlapping each other and `avoid` ≤ 25 %."""
    pts = []
    for b in Dt.bld.get("buildings", []):
        w = (b.get("homes") or 0) + (b.get("jobs") or 0)
        if w:
            q = np.asarray(b["footprint"])[:, :2].mean(axis=0)
            pts.append((q[0], q[1], w))
    P = np.asarray(pts)
    x0, z0, x1, z1 = Dt.area.bounds
    cand = []
    for x in np.arange(x0, x1 - TILE + 1, 125.0):
        for z in np.arange(z0, z1 - TILE + 1, 125.0):
            if Dt.area.intersection(box(x, z, x + TILE, z + TILE)).area < 0.6 * TILE * TILE:
                continue
            m = (P[:, 0] >= x) & (P[:, 0] < x + TILE) & (P[:, 1] >= z) & (P[:, 1] < z + TILE)
            cand.append((float(P[m, 2].sum()), float(x), float(z)))
    cand.sort(reverse=True)
    chosen = []
    taken = [box(*a) for a in avoid]
    for w, x, z in cand:
        b = box(x, z, x + TILE, z + TILE)
        if all(b.intersection(t).area <= 0.25 * TILE * TILE for t in taken):
            chosen.append((w, x, z)); taken.append(b)
            if len(chosen) == n:
                break
    return chosen


def main(argv):
    Dt = Data()
    if "--tile" in argv:
        i = argv.index("--tile"); x, z = float(argv[i + 1]), float(argv[i + 2])
        name = argv[i + 3] if len(argv) > i + 3 else f"tile_{int(x)}_{int(z)}"
        draw(Dt, x, z, x + TILE, z + TILE, 1.0, os.path.join(OD, "tiles", name + ".png"), f"Golden · {name} · 1 м/пкс")
        return
    x0, z0, x1, z1 = Dt.area.bounds
    x0, z0, x1, z1 = x0 - 100, z0 - 100, x1 + 100, z1 + 100
    draw(Dt, x0, z0, x1, z1, 10.0, os.path.join(OD, "overview.png"), "Golden · весь район · 10 м/пкс (spec v1)")
    if "--overview" in argv:
        return
    cx, cz = CENTRE[0] - TILE / 2, CENTRE[1] - TILE / 2
    tiles = [{"name": "centre", "x0": cx, "z0": cz, "why": "центр: K-Park, главный центр C1, развязка «K-Park», станция ЛРТ «Golden-Центр»"}]
    for k, (w, x, z) in enumerate(densest(Dt, 2, avoid=[(cx, cz, cx + TILE, cz + TILE)])):
        tiles.append({"name": f"dense_{k + 1}", "x0": x, "z0": z, "why": f"плотнейшее окно 2×2 км: домов + мест работы {int(w)} (на 4 км²)"})
    for t in tiles:
        t["x1"], t["z1"] = t["x0"] + TILE, t["z0"] + TILE
        draw(Dt, t["x0"], t["z0"], t["x1"], t["z1"], 1.0, os.path.join(OD, "tiles", t["name"] + ".png"), f"Golden · {t['name']} · 1 м/пкс")
    json.dump(tiles, open(os.path.join(OD, "tiles", "tiles.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
