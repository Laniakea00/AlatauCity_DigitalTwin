"""Tiny runner of the land rules (w44) until w43's validate_map.py exists:
python3 tools/map/gen/land_check.py <district> [--out OUT] [--spec S] [--rules 1,2,14] [--report PATH]

Builds a ctx with the attributes of CONTRACT §5 from the files in OUT/<d>/, loads validate/rules/{land,buildings,green,years}.py
by path, runs every RULES entry and writes the issues, counts per rule and severity, the rule 14 service table per residential
block and the places check to PATH (default OUT/_tools/land_check_<d>.json)."""
import argparse
import importlib.util
import json
import os
import sys
import time as _time
from collections import Counter
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.ops import unary_union  # noqa: E402

import land_util as U  # noqa: E402

RULE_FILES = ["land", "buildings", "green", "years"]


def make_ctx(d, out, spec_path=None):
    spec = U.load_spec(d, spec_path)
    N = U.Norms()
    od = U.out_dir(out, d)
    work = U.work_polygon(spec)
    wpol, _ = U.water_geoms(work)
    flood, _ = U.flood_poly(work, N)

    def rd(name):
        return U.read_json(os.path.join(od, name + ".json"))
    b = rd("buildings")
    vh = [U.from_coords(x["footprint"]) for x in (b or {}).get("buildings", []) if x["source"] == "existing_osm"]
    ctx = SimpleNamespace(
        d=d, spec=spec, city=U.city(), norms=N.doc, norm=lambda k: N.v(k), sev=lambda k: N.sev(k),
        rules=U.read_json(os.path.join(U.SPEC_DIR, "rules.json")),
        network=rd("network"), lrt=rd("lrt"), blocks=rd("blocks"), lots=rd("lots"), buildings=b, features=rd("features"),
        driveways=rd("driveways"),
        area=work, h=U.h, water=U.clean(unary_union(wpol)) if wpol else U.Polygon(), flood_485=flood, villages_houses=vh,
        years=list(N.v("validator.years")),
        shift=lambda year, scenario: U.effective_years(year)[["Base", "Fast", "Slow", "InfraFirst"].index(scenario)])
    return ctx


def load_rules():
    here = os.path.join(U.MAP, "validate", "rules")
    mods = []
    for name in RULE_FILES:
        sp = importlib.util.spec_from_file_location("w44_rules_" + name, os.path.join(here, name + ".py"))
        m = importlib.util.module_from_spec(sp)
        sys.modules["w44_rules_" + name] = m
        sp.loader.exec_module(m)
        mods.append(m)
    return [r for m in mods for r in m.RULES]


def run(d, out, spec_path=None, only=None, report=None):
    t0 = _time.time()
    ctx = make_ctx(d, out, spec_path)
    issues, timing = [], {}
    for r in load_rules():
        if only and r["no"] not in only:
            continue
        t1 = _time.time()
        try:
            res = r["fn"](ctx)
        except Exception as e:          # a rule that crashes is an error of the rule, reported, not a silent pass
            import traceback
            traceback.print_exc()
            res = [{"rule": r["no"], "sev": "error", "x": 0, "z": 0, "lv": 0, "what_ru": f"правило упало: {e!r}", "ids": []}]
        timing[r["no"]] = round(_time.time() - t1, 2)
        issues += res
    bmod = sys.modules.get("w44_rules_buildings")
    table = bmod.service_table(ctx, max(ctx.years)) if bmod and ctx.buildings and ctx.network else []
    places = {Y: bmod.places_check(ctx, Y) for Y in ctx.years} if bmod and ctx.buildings else {}
    cnt = Counter((i["rule"], i["sev"]) for i in issues)
    doc = {"district": d, "made_by": "w44 land_check.py", "counts": {f"{k[0]}:{k[1]}": v for k, v in sorted(cnt.items())},
           "timing_s": timing, "places": places, "service_table": table, "issues": issues}
    path = report or os.path.join(out, "_tools", f"land_check_{d}.json")
    U.write_json(path, doc)
    print(f"{d}: {len(issues)} issues {dict(Counter(i['sev'] for i in issues))}; by rule "
          f"{dict(sorted(Counter(i['rule'] for i in issues).items()))}; {_time.time() - t0:.1f} s → {path}")
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("district")
    ap.add_argument("--out", default=U.OUT)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--rules", default=None)
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    only = {int(x) for x in a.rules.split(",")} if a.rules else None
    run(a.district, a.out, a.spec, only, a.report)
