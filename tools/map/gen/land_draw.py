"""Picture of the land layer of a district (w44): python3 tools/map/gen/land_draw.py <district> [--out OUT] [--spec S] [--png P]

Lots coloured by use, buildings (social ones outlined), parking by type, greens, streets (red lines), LRT, stops and the
land-rule issues (land_check report) on one map. Default PNG: OUT/_tools/land_<district>.png."""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.patches import Polygon as MPoly  # noqa: E402

import land_util as U  # noqa: E402

USE_COL = {
    "residential_high": "#e8a87c", "residential_mid": "#f2c49b", "residential_low": "#f7dcb9", "mixed_centre": "#e07a5f",
    "business": "#b5a4d6", "logistics": "#c9c3b8", "industry": "#b0a89a", "village_existing": "#efe6c8", "utility": "#dcdcdc",
    "park": "#b8dca7", "square": "#9fd08a", "playground": "#9fd08a", "reserve": "#eeeeee", "landmark": "#f4d35e",
    "school": "#4f86c6", "kindergarten": "#7fb3e6", "polyclinic": "#d1495b", "pharmacy_shop": "#edae49", "fire_station": "#8b1e3f",
    "transit": "#5c5c5c", "waterfront": "#9ad1d4",
}
PK_COL = {"surface": "#555555", "multi": "#2a9d8f", "underground": "#264653"}
GREEN_COL = {"park": "#5a9e4b", "square": "#3f8f3a", "yard": "#8cc084", "buffer": "#a7c4a0", "boulevard": "#5a9e4b", "sport": "#6a994e"}
SEV_COL = {"error": "#d00000", "warning": "#f48c06", "wait_neighbour": "#7b2cbf"}


def patches(polys, **kw):
    return PatchCollection([MPoly(p, closed=True) for p in polys if len(p) >= 3], **kw)


def run(d, out, spec_path=None, png=None, report=None):
    spec = U.load_spec(d, spec_path)
    od = U.out_dir(out, d)
    rd = lambda n: U.read_json(os.path.join(od, n + ".json")) or {}  # noqa: E731
    net, lrt, lots, bld, feat, drv = rd("network"), rd("lrt"), rd("lots"), rd("buildings"), rd("features"), rd("driveways")
    rep = U.read_json(report or os.path.join(od, "land_check.json")) or U.read_json(os.path.join(out, "_tools", f"land_check_{d}.json")) or {}
    norms = U.Norms()
    work = U.work_polygon(spec)
    x0, z0, x1, z1 = work.bounds
    fig, ax = plt.subplots(figsize=(18, 18 * (z1 - z0) / (x1 - x0) + 1.2), dpi=110)
    ax.set_facecolor("#fafafa")
    by_use = {}
    for L in lots.get("lots", []):
        by_use.setdefault(L["use"], []).append(L["polygon"])
    for u, ps in by_use.items():
        ax.add_collection(patches(ps, facecolor=USE_COL.get(u, "#f0f0f0"), edgecolor="#ffffff", linewidth=0.3, zorder=1))
    red = [U.coords(p) for _, p, lv in U.network_polys(net, norms, "red") if lv == 0]
    ax.add_collection(patches(red, facecolor="#ffffff", edgecolor="#cfcfcf", linewidth=0.2, zorder=2))
    car = [U.coords(p) for _, p, lv in U.network_polys(net, norms, "carriage")]
    ax.add_collection(patches(car, facecolor="#9a9a9a", edgecolor="none", zorder=3))
    for g in feat.get("greens", []):
        if g["kind"] in ("yard",):
            ax.add_collection(patches([g["polygon"]], facecolor=GREEN_COL[g["kind"]], edgecolor="none", alpha=0.6, zorder=4))
    dcar = [U.coords(p) for _, p, lv in U.network_polys(drv, norms, "carriage")] if drv.get("segments") else []
    ax.add_collection(patches(dcar + [pd["polygon"] for pd in drv.get("pads", [])], facecolor="#c9b27c", edgecolor="none", zorder=4.5))
    for p_ in feat.get("parking", []):
        st = dict(facecolor=PK_COL[p_["type"]], edgecolor="none", alpha=0.85, zorder=5) if p_["type"] != "underground" else \
            dict(facecolor="none", edgecolor=PK_COL["underground"], linewidth=0.6, linestyle=":", zorder=5)
        ax.add_collection(patches([p_["polygon"]], **st))
    soc = {L["id"] for L in lots.get("lots", []) if L["use"] in U.SOCIAL_USES}
    fp_new = [b["footprint"] for b in bld.get("buildings", []) if b["source"] != "existing_osm"]
    fp_old = [b["footprint"] for b in bld.get("buildings", []) if b["source"] == "existing_osm"]
    fp_soc = [b["footprint"] for b in bld.get("buildings", []) if b.get("lot") in soc]
    ax.add_collection(patches(fp_old, facecolor="#8d7b68", edgecolor="none", zorder=6))
    ax.add_collection(patches(fp_new, facecolor="#3d3d3d", edgecolor="none", zorder=6))
    ax.add_collection(patches(fp_soc, facecolor="#1d4e89", edgecolor="#ffffff", linewidth=0.6, zorder=7))
    for Ln in lrt.get("lines", []):
        xs, zs = [p[0] for p in Ln["pts"]], [p[1] for p in Ln["pts"]]
        ax.plot(xs, zs, color="#c1121f", linewidth=2.2, zorder=8)
    for s in feat.get("stops", []):
        ax.plot(s["x"], s["z"], marker={"bus": "o", "lrt": "s", "rail": "D"}[s["kind"]], color="#000000" if s["kind"] == "bus" else "#c1121f",
                markersize=4 if s["kind"] == "bus" else 7, zorder=9)
    for k in spec.get("keep", []):
        kp = k["polygon"]
        ax.plot([p[0] for p in kp] + [kp[0][0]], [p[1] for p in kp] + [kp[0][1]], color="#b08900", linewidth=1.5, zorder=8)
    for c in U.corridors(spec):
        ax.plot([p[0] for p in c["line"]], [p[1] for p in c["line"]], color="#6a040f", linewidth=1.0, linestyle="--", zorder=8)
    iss = rep.get("issues", [])
    for sev, col in SEV_COL.items():
        pts = [(i["x"], i["z"]) for i in iss if i["sev"] == sev and i["x"]]
        if pts:
            ax.scatter([p[0] for p in pts], [p[1] for p in pts], marker="x", s=14, linewidths=0.8, color=col, zorder=10)
    wx, wz = work.exterior.xy
    ax.plot(wx, wz, color="#000000", linewidth=0.8, zorder=11)
    ax.set_xlim(x0 - 20, x1 + 20)
    ax.set_ylim(z0 - 20, z1 + 20)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    cu = Counter(L["use"] for L in lots.get("lots", []))
    h = [Patch(color=USE_COL.get(u, "#f0f0f0"), label=f"{u} ({n})") for u, n in sorted(cu.items(), key=lambda t: -t[1])]
    h += [Patch(color=PK_COL[t], label=f"parking {t}") for t in ("surface", "multi")]
    h += [Line2D([], [], color=PK_COL["underground"], linestyle=":", label="parking underground (outline)")]
    h += [Patch(color="#3d3d3d", label="new building"), Patch(color="#8d7b68", label="existing house"), Patch(color="#1d4e89", label="social building"),
          Patch(color=GREEN_COL["yard"], label="yard (green)"), Patch(color="#c9b27c", label="driveway / fire lane / turnaround"), Line2D([], [], color="#c1121f", linewidth=2, label="LRT"),
          Line2D([], [], marker="o", color="#000", linestyle="none", markersize=4, label="bus stop")]
    rc = Counter(i["sev"] for i in iss)
    h += [Line2D([], [], marker="x", color=c, linestyle="none", label=f"issue {s} ({rc.get(s, 0)})") for s, c in SEV_COL.items()]
    ax.legend(handles=h, loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=8, frameon=False)
    T = bld.get("totals", {})
    ax.set_title(f"{d}: lots by use, buildings, parking, greens, stops and land-rule issues · homes {T.get('homes')} · jobs {T.get('jobs')} · "
                 f"buildings {T.get('buildings')} {T.get('by_source')}", fontsize=10)
    fig.tight_layout()
    path = png or os.path.join(out if not out.endswith("_fixtures") else os.path.dirname(out), "_tools", f"land_{d}.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path)
    print("→", path)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("district")
    ap.add_argument("--out", default=U.OUT)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    run(a.district, a.out, a.spec, a.png, a.report)
