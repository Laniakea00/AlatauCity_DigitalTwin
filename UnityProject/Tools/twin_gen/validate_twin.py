"""Consistency checks of StreamingAssets/twin/*.json against buildings.csv and each other. Exit code 1 on failure."""
import sys, json, math
import numpy as np
from twin_common import *
import norms as N

ok = True


def check(cond, msg):
    global ok
    print(("  ok   " if cond else "  FAIL ") + msg)
    ok &= bool(cond)


def main(bcsv, d):
    J = {k: json.load(open(f"{d}/{k}.json", encoding="utf-8")) for k in ("roads", "networks", "loads", "construction", "finance", "traffic", "scenarios")}
    B = load_buildings(bcsv)
    versions = {J[k]["version"] for k in J}
    check(len(versions) == 1, f"one data version in all files: {versions}")
    L = J["loads"]; CATS = L["cats"]
    print("Population / jobs (CityStats formula)")
    for s in SCENARIOS:
        hous = sum(b["gfa"] for b in B if b["use"] == "housing" and b["d"] >= 0 and b["source"] != "existing_osm" and b["eff"][s] <= Y1)
        res = sum(L["loads"][s]["res"][dd][-1] for dd in range(4))
        check(abs(res - hous / N.M2_PER_RESIDENT) < 50, f"{s}: residents 2050 = housing GFA / 30 m² ({res:,.0f})")
    jobs = sum(L["loads"]["base"]["jobs"][dd][-1] for dd in range(4))
    check(0.9e6 < jobs < 1.2e6, f"jobs 2050 ≈ 1 mln (official target): {jobs:,.0f}")
    res = sum(L["loads"]["base"]["res"][dd][-1] for dd in range(4))
    check(1.7e6 < res < 2.0e6, f"residents 2050 ≈ 1.8 mln (official target): {res:,.0f}")
    print("GFA per district = buildings.csv")
    for dd in range(4):
        g = sum(b["gfa"] for b in B if b["d"] == dd and b["use"] in CATS and b["year"] <= Y1) / 1e6
        gj = sum(L["loads"]["base"]["gfa"][dd][c][-1] for c in range(len(CATS)))
        check(abs(g - gj) < 0.2, f"{DISTRICTS[dd]}: {gj:.1f} vs {g:.1f} mln m²")
    print("Networks and facilities")
    Nw = J["networks"]; ne = len(J["roads"]["edges"])
    for res, segs in Nw["networks"].items():
        check(all(0 <= s[0] < ne for s in segs), f"{res}: {len(segs)} segments reference valid road edges")
        check(all(2025 <= y <= 2099 for s in segs for y in s[2:6]), f"{res}: segment years in range (2025 = existing)")
    for f in Nw["facilities"]:
        if f["cap"]:
            check(all(all(a <= b for a, b in zip(c, c[1:])) for c in f["cap"]), f"{f['id']}: capacity never decreases") if f["res"] != "renewable" else None
    for res in ("power", "heat", "sewer", "power_hv"):
        fac = [f for f in Nw["facilities"] if f["res"] == res]
        tot = sum(f["demand"][0][-1] for f in fac)
        key = "power" if res == "power_hv" else res
        ld = sum(L["loads"]["base"][key][dd][-1] for dd in range(4))
        check(abs(tot - ld) / max(ld, 1) < 0.01, f"{res}: facility demand sums to district loads ({tot:,.0f} vs {ld:,.0f})")
    bal = L["balance"]
    for s in SCENARIOS:
        tot = {r: max(bal[s][r]["city"]["deficit"]) for r in bal[s]}
        print(f"  {s}: max deficit " + ", ".join(f"{r} {v:,.0f}" for r, v in tot.items()))
    check(all(max(bal["infra"][r]["city"]["deficit"]) == 0 for r in bal["infra"]), "infra-first scenario: no deficits")
    check(max(bal["base"]["power_hv"]["city"]["deficit"]) > 10, "base scenario: the designed Golden power deficit is visible")
    check(sum(max(bal["fast"][r]["city"]["deficit"]) > 0 for r in bal["fast"]) >= 4, "accelerated scenario: deficits in most networks")
    print("Roads")
    R = J["roads"]
    check(all(len(e["g"]) >= 4 and len(e["y"]) == 4 for e in R["edges"]), f"{len(R['edges'])} edges with geometry and 4 scenario years")
    km = sum(e["len"] for e in R["edges"]) / 1000
    check(2000 < km < 5000, f"road network {km:,.0f} km")
    print("Construction")
    C = J["construction"]; nb = max(b["bid"] for b in B) + 1
    check(all(len(C["per_building"][k]) == nb for k in C["per_building"]), "per-building arrays cover every bid")
    for s in SCENARIOS:
        sc = C["s_curves"][s]
        check(all(f <= p + 0.05 for dd in range(4) for p, f in zip(sc["plan"][dd], sc["fact"][dd])), f"{s}: fact never ahead of plan")
    print("Finance")
    F = J["finance"]["by_scenario"]["base"]
    infra = sum(sum(v[YEARS.index(y)] for y in range(2026, 2031)) for k, v in F["infra"].items() if k not in ("lrt", "roads"))
    allin = sum(sum(v[YEARS.index(y)] for y in range(2026, 2031)) for k, v in F["infra"].items())
    print(f"  base engineering infrastructure CAPEX 2026–2030: {infra:,.0f} bln ₸ (open data: 365.1 + 312.5 = 677.6 bln ₸ for stages 1–2); with streets and LRT {allin:,.0f}")
    check(0.6 < infra / 677.6 < 1.6, "engineering CAPEX 2026–2030 within ×1.6 of the published stage 1–2 programme")
    bld = sum(sum(sum(c) for c in dd) for dd in F["buildings"])
    exp = sum(b["gfa"] * N.COST_TG_M2[b["use"]] / 1e9 for b in B if b["d"] >= 0 and b["use"] in CATS and b["source"] != "existing_osm" and b["year"] <= Y1)
    check(abs(bld - exp) / exp < 0.03, f"buildings CAPEX = Σ GFA × unit cost ({bld:,.0f} vs {exp:,.0f} bln ₸)")
    src = sum(sum(sum(k) for k in dd) for dd in F["sources"])
    check(abs(src - bld) / bld < 0.01, "funding sources add up to buildings CAPEX")
    print("Traffic")
    T = J["traffic"]
    check(all(len(T["by_scenario"][s][str(y)]["vc"]) == ne for s in SCENARIOS for y in T["years"]), "v/c arrays match road edges")
    print("RESULT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1], sys.argv[2]) else 1)
