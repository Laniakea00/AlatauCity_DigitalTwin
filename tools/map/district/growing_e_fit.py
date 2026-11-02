#!/usr/bin/env python3
"""Growing-East · level 2 · what the blocks held (w53): reads a gen_buildings run of spec/growing_e.json (OUT/growing_e/
buildings.json totals.zones need_m2 / got_m2) and writes district/growing_e_fit.json, which growing_e_build.py reads to keep
the zone densities at what the blocks hold (as Gate v1.1 did: «jobs per ha to what the blocks hold»).

    python3 tools/map/district/growing_e_fit.py [--out OUT] [--spec spec.json]

Per zone: the density the run asked for (jobs_per_ha, homes_per_ha) and the share it got (got_m2 / need_m2); plus the new jobs
the run put in the villages (social buildings of the village centres), which the builder takes off the zones' share.
"""
import argparse
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "..", "spec", "growing_e.json")
OUT = os.environ.get("ALATAU_MAP_OUT", "/mnt/project-files/alatau_stage7/out")
FIT = os.path.join(HERE, "growing_e_fit.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--spec", default=SPEC)
    a = ap.parse_args()
    od = os.path.join(a.out, "growing_e")
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    with open(os.path.join(od, "buildings.json"), encoding="utf-8") as f:
        B = json.load(f)
    with open(os.path.join(od, "blocks.json"), encoding="utf-8") as f:
        blk = {b["id"]: b.get("zone") for b in json.load(f)["blocks"]}
    with open(os.path.join(od, "lots.json"), encoding="utf-8") as f:
        lot_zone = {l_["id"]: blk.get(l_["block"]) for l_ in json.load(f)["lots"]}
    use = {z["id"]: z["use"] for z in spec["zones"]}
    jobs_by_use = defaultdict(float)
    for b in B["buildings"]:
        if b.get("source") == "existing_osm":
            continue
        jobs_by_use[use.get(lot_zone.get(b.get("lot")), "?")] += b.get("jobs") or 0
    zones = {}
    for z in spec["zones"]:
        t = B["totals"]["zones"].get(z["id"]) or {}
        r = z.get("rules") or {}
        row = {"use": z["use"]}
        for grp, key in (("jobs", "jobs_per_ha"), ("housing", "homes_per_ha")):
            if grp in t and t[grp]["need_m2"] > 0:
                row[key] = r.get(key)
                row[grp + "_ratio"] = round(t[grp]["got_m2"] / t[grp]["need_m2"], 4)
        if len(row) > 1:
            zones[z["id"]] = row
    fit = {"what": "доля плотности, которую набрали кварталы (gen_buildings totals.zones got_m2 / need_m2)",
           "run": {"homes_new": B["totals"].get("homes_new"), "jobs_new": B["totals"].get("jobs_new"),
                   "targets": B["totals"].get("targets")},
           "village_jobs": round(jobs_by_use.get("village_existing", 0.0)),
           "jobs_by_use": {k: round(v) for k, v in sorted(jobs_by_use.items())}, "zones": zones}
    with open(FIT, "w", encoding="utf-8") as f:
        json.dump(fit, f, ensure_ascii=False, indent=1)
    print("fit", FIT, len(zones), "zones; village jobs", fit["village_jobs"], fit["jobs_by_use"])


if __name__ == "__main__":
    main()
