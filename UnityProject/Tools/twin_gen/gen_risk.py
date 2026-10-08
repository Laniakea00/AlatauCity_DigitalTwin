"""Flood exposure of every building (model): depth of water for two river-flood scenarios on the Kaskelen / Ili river network.
depth = stage − (ground − river level) − 2.5 m per km away from the channel; only channels ≥ 20 m wide count."""
import sys, json, numpy as np
from scipy.spatial import cKDTree
from twin_common import load_buildings, dump

SCEN = [("flood_1pct", "Паводок 1 % (раз в 100 лет)", 1.6), ("flood_ext", "Экстремальный паводок 0,1 % + сброс Капшагайской ГЭС", 3.0)]

def main(bcsv, geo, out):
    B = load_buildings(bcsv); g = json.load(open(geo, encoding="utf-8"))
    r = np.array(g["layers"]["Rivers"]); r = r[r[:, 4] >= 20]
    pts = []; z = []
    for s in r:
        n = max(1, int(np.hypot(s[2] - s[0], s[3] - s[1]) // 25))
        for t in np.linspace(0, 1, n + 1): pts.append((s[0] + (s[2] - s[0]) * t, s[1] + (s[3] - s[1]) * t)); z.append(s[5])
    kd = cKDTree(np.array(pts)); z = np.array(z)
    nb = max(b["bid"] for b in B) + 1
    xy = np.array([[b["x"], b["z"]] for b in B]); dist, idx = kd.query(xy)
    import csv
    ground = {int(row["bid"]): float(row["ground_m"]) for row in csv.DictReader(open(bcsv, encoding="utf-8"))}
    res = {}
    for key, name, stage in SCEN:
        depth = np.zeros(nb, dtype=int)
        for k, b in enumerate(B):
            dpt = stage - max(0.0, ground[b["bid"]] - z[idx[k]]) - dist[k] / 400.0   # river z is the bank line: never deeper than the stage
            if dist[k] < 1200 and dpt > 0.05: depth[b["bid"]] = int(round(min(dpt, 6.0) * 100))
        res[key] = {"name": name, "stage_m": stage, "depth_cm": depth.tolist()}
        print(key, "buildings flooded:", int((depth > 0).sum()), "deep >1 m:", int((depth > 100).sum()))
    dump({"scenarios": res, "river_dist_m": [0] * 0}, out, {"what": "Подтопление зданий при паводках (модель): глубина воды у здания, см; bid → см",
          "note": "Демо-модель: уровень воды над урезом рек шириной ≥ 20 м, затухание 2,5 м на км. Не заменяет гидрологический расчёт."})

if __name__ == "__main__":
    main(*sys.argv[1:4])
