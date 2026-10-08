"""Gate District Q1 BIM quarter (QTwin Alatau_Gate_Q1_4D.html → window.DATA) → Unity:
Assets/CityData/gate_q1.bytes (mesh in Unity world coordinates + element index per vertex) and StreamingAssets/twin/gate_q1.json
(elements with plan / fact completion day, stages, survey epochs). The QTwin schedule (2027) is shifted by SHIFT_YEARS so the quarter
is built when the city build-out scenario puts these master-plan buildings (2031–2032)."""
import sys, json, re, base64, struct, datetime as dt
import numpy as np

SHIFT_YEARS = 4
E0, N0 = 663000.0, 4830000.0          # Unity origin in UTM 43N
CLS = {"IfcColumn": "column", "IfcCurtainWall": "curtain", "IfcWall": "wall", "IfcSlab": "slab", "IfcFooting": "footing"}


def shift(d):
    x = dt.date.fromisoformat(d[:10]); return x.replace(year=x.year + SHIFT_YEARS)


def main(data_json, out_bytes, out_json):
    D = json.load(open(data_json, encoding="utf-8"))
    pp = D["passport"]
    # georeference (IfcMapConversion): E 660680, N 4810940, H 631.89 — from the IFC header
    E, N, H = 660680.0, 4810940.0, 631.8927612304688
    ox, oz = E - E0, N - N0
    g = D["geom"]
    q = np.frombuffer(base64.b64decode(g["verts"]), dtype=np.uint16).reshape(-1, 3).astype(np.float64)
    lo, hi = np.array(g["lo"]), np.array(g["hi"])
    P = lo + q / 65535.0 * (hi - lo)                     # local x east, y north, z up
    idx = np.frombuffer(base64.b64decode(g["idx"]), dtype=np.uint16).astype(np.int64)
    els = D["elements"]
    nv, nt = len(P), len(idx) // 3
    vert_elem = np.zeros(nv, dtype=np.int32); tris = np.zeros(nt * 3, dtype=np.int64)
    for k, e in enumerate(els):
        v0, n_v, t0, n_t = e["v0"], e["nv"], e["t0"], e["nt"]
        vert_elem[v0:v0 + n_v] = k
        tris[t0 * 3:(t0 + n_t) * 3] = idx[t0 * 3:(t0 + n_t) * 3] + v0
    U = np.stack([P[:, 0] + ox, P[:, 2] + H, P[:, 1] + oz], axis=1).astype(np.float32)   # Unity X, Y (a.s.l.), Z
    # Unity is left-handed with Y up: swapping y/z mirrors the mesh → flip the winding
    T = tris.reshape(-1, 3)[:, [0, 2, 1]].astype(np.uint32)
    with open(out_bytes, "wb") as f:
        f.write(b"BIM1"); f.write(struct.pack("<ii", nv, nt))
        f.write(U.tobytes()); f.write(T.tobytes()); f.write(vert_elem.astype(np.int32).tobytes())
    # ---------------- schedule: plan / fact completion day per element (day 0 = first stage start)
    sch = D["schedule"]; stages = sch["stages"]
    day0 = min(shift(s["start"]) for s in stages)
    dd = lambda d: (shift(d) - day0).days
    fact_by_stage = {}
    for fct in sch["fact"]: fact_by_stage.setdefault(fct["stage"], []).append((dd(fct["date"]), fct["pct"]))
    status = dd(sch["status_date"])
    el_stage = [-1] * len(els); plan = [9999] * len(els); fact = [9999] * len(els)
    for si, s in enumerate(stages):
        rx = re.compile(s["filter"]["name_re"]); cl = set(s["filter"]["classes"])
        members = [k for k, e in enumerate(els) if e["class"] in cl and rx.search(e["name"])]
        members.sort(key=lambda k: (els[k]["storey"], k))
        n = max(1, len(members)); a, b = dd(s["start"]), dd(s["end"])
        pts = [(a, 0.0)] + sorted(fact_by_stage.get(s["id"], []))
        # forecast after the last survey: keep the last observed pace (or the plan pace if none)
        (ta, pa), (tb, pb) = (pts[-2] if len(pts) > 1 else (a, 0.0)), pts[-1]
        rate = (pb - pa) / max(tb - ta, 1) if pb > pa else 100.0 / max(b - a, 1) * 0.6
        for r, k in enumerate(members):
            el_stage[k] = si
            need = (r + 1) / n * 100.0
            plan[k] = int(round(a + (r + 1) / n * (b - a)))
            day = None
            for (t1, p1), (t2, p2) in zip(pts, pts[1:]):
                if p2 >= need and p2 > p1: day = t1 + (need - p1) / (p2 - p1) * (t2 - t1); break
            if day is None: day = pts[-1][0] + (need - pts[-1][1]) / max(rate, 1e-3)
            fact[k] = int(round(min(day, 9000)))
    out = {
        "about": {"source": "QTwin Alatau_Gate_Q1_4D (IFC4, LOD 200, сгенерировано из генплана)", "shift_years": SHIFT_YEARS,
                  "note": "График QTwin (2027) сдвинут на +4 года, чтобы квартал строился тогда же, когда эти здания появляются в сценарии застройки города (2031–2032). Факт — по синтетическим съёмкам БПЛА."},
        "origin": {"E": E, "N": N, "H": H, "unity_x": ox, "unity_z": oz},
        "day0": day0.isoformat(), "status_day": status, "status_date": (day0 + dt.timedelta(days=status)).isoformat(),
        "end_day": max(dd(s["end"]) for s in stages),
        "stages": [{"id": s["id"], "name": s["name"], "start": dd(s["start"]), "end": dd(s["end"]), "workers": s.get("workers", 0),
                    "fact": sorted(fact_by_stage.get(s["id"], []))} for s in stages],
        "epochs": [{"day": dd(e["date"]), "source": e["source"], "points": e["points"]} for e in D["progress"]["epochs"]],
        "elements": [[e["guid"], e["name"], CLS.get(e["class"], e["class"]), e["props"].get("QTwin_Block.Complex", "?"), e["storey"], el_stage[k], plan[k], fact[k],
                      round(float((e.get("qto") or {}).get("NetVolume", 0) or 0), 2)] for k, e in enumerate(els)],
        "element_fields": ["guid", "name", "class", "complex", "storey", "stage", "plan_day", "fact_day", "volume_m3"],
        "buildings": pp.get("buildings", []), "summary": D["summary"], "storeys": D["storeys"],
    }
    json.dump(out, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    late = sum(1 for k in range(len(els)) if fact[k] > plan[k] + 7 and plan[k] < 9999)
    print(f"BIM: {nv} verts, {nt} tris, {len(els)} elements, {len(stages)} stages, day0 {day0}, status day {status}, late elements {late}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
