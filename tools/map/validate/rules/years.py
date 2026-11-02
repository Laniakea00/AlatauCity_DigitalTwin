"""Rules 23–24 (w44): nothing opens before its street or its construction; one number everywhere. Interface: CONTRACT §5."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))
from shapely.geometry import Point  # noqa: E402

import land_rulekit as K  # noqa: E402
import land_util as U  # noqa: E402


def _late(a, b):
    """Scenario indices where years a open before years b."""
    return [i for i in range(4) if a[i] < b[i]]


def check_23(ctx):
    m = K.missing(ctx, 23, "lots", "buildings", "network")
    if m:
        return m
    out = []
    scen = K.nv(ctx, "validator.scenarios")
    ex = K.nv(ctx, "validator.existing_object_year")
    segs = K.segs(ctx)
    lotb = K.lot_by_id(ctx)

    def street_years(L):
        s = segs.get(L.get("access"))
        return (s["years"], s["id"]) if s else (None, None)
    for L in K.lots(ctx):
        sy, sid = street_years(L)
        c = L["_p"].representative_point()
        if sy is None:
            sev = "wait_neighbour" if L["_p"].distance(ctx.area.exterior) < 2.0 else None
            out.append(K.issue(ctx, 23, c.x, c.y, f"участок {L['id']}: нет улицы-въезда, год сравнить не с чем", [L["id"]], sev=sev))
            continue
        if L["source"] == "existing":
            if any(y != ex for y in L["years"]):
                out.append(K.issue(ctx, 23, c.x, c.y, f"существующий участок {L['id']}: годы {L['years']} ≠ {ex}", [L["id"]]))
            continue
        bad = _late(L["years"], sy)
        if bad and L["source"] != "keep":
            out.append(K.issue(ctx, 23, c.x, c.y, f"участок {L['id']} раньше улицы {sid}: {', '.join(f'{scen[i]} {L['years'][i]} < {sy[i]}' for i in bad)}", [L["id"], sid]))
    # driveways: a drive opens with its street at the earliest; a building it serves not before the drive
    dv = K.driveways(ctx)
    if dv is not None:
        nodes = {n["id"]: n for n in dv.get("nodes", [])}
        drv_years = {}
        for s in dv.get("segments", []):
            for nid in (s["a"], s["b"]):
                a = (nodes.get(nid) or {}).get("attach")
                st = segs.get((a or {}).get("segment"))
                if st is None:
                    continue
                bad = _late(s["years"], st["years"])
                if bad:
                    n = nodes[nid]
                    out.append(K.issue(ctx, 23, n["x"], n["z"], f"проезд {s['id']} раньше улицы {st['id']}: "
                                       f"{', '.join(f'{scen[i]} {s['years'][i]} < {st['years'][i]}' for i in bad)}", [s["id"], st["id"]]))
            for bid in s.get("serves", []):
                drv_years[bid] = [max(a, b) for a, b in zip(drv_years.get(bid, s["years"]), s["years"])]
        for b in K.buildings(ctx):
            dy = drv_years.get(b["id"])
            bad = _late(b["years"], dy) if dy else []
            if bad:
                c = b["_p"].centroid
                out.append(K.issue(ctx, 23, c.x, c.y, f"здание {b['id']} раньше своего проезда: "
                                   f"{', '.join(f'{scen[i]} {b['years'][i]} < {dy[i]}' for i in bad)}", [b["id"]]))
    for b in K.buildings(ctx):
        c = b["_p"].centroid
        if b["source"] == "existing_osm":
            if any(y != ex for y in b["years"]):
                out.append(K.issue(ctx, 23, c.x, c.y, f"существующее здание {b['id']}: годы {b['years']} ≠ {ex}", [b["id"]]))
            continue
        L = lotb.get(b.get("lot"))
        if L is None:
            continue
        sy, sid = street_years(L)
        for ref, what in ((sy, f"улицы {sid}"), (L["years"], f"участка {L['id']}")):
            if ref is None:
                continue
            bad = _late(b["years"], ref)
            if bad:
                out.append(K.issue(ctx, 23, c.x, c.y, f"здание {b['id']} раньше {what}: {', '.join(f'{scen[i]} {b['years'][i]} < {ref[i]}' for i in bad)}", [b["id"]]))
        by = b.get("build_years")
        if by and (len(by) != 4 or any(by[i] > by[i + 1] for i in range(3)) or by[-1] > b["years"][0]):
            out.append(K.issue(ctx, 23, c.x, c.y, f"здание {b['id']}: порядок 4D (земля → каркас → фасад → благоустройство) нарушен: {by}", [b["id"]]))
    f = ctx.features or {}
    for p_ in f.get("parking", []):
        L = lotb.get(p_.get("lot"))
        if L is None:
            continue
        sy, sid = street_years(L)
        if sy and _late(p_["years"], sy):
            pp = K.poly(p_["polygon"]).representative_point()
            out.append(K.issue(ctx, 23, pp.x, pp.y, f"стоянка {p_['id']} раньше улицы {sid}", [p_["id"], sid]))
    for st in f.get("stops", []):
        s = segs.get(st.get("segment"))
        if s and st.get("years") and _late(st["years"], s["years"]):
            out.append(K.issue(ctx, 23, st["x"], st["z"], f"остановка {st['id']} раньше улицы {s['id']}", [st["id"], s["id"]]))
    return out


def check_24(ctx):
    m = K.missing(ctx, 24, "lots", "buildings")
    if m:
        return m
    out = []
    c = ctx.area.centroid
    tol = K.nv(ctx, "validator.district_numbers_tolerance_pct") / 100.0
    exact = K.nv(ctx, "validator.panel_vs_data_tolerance")
    m2_res = U.twin_m2()[0]
    B = K.buildings(ctx)
    home_m2 = float((ctx.spec.get("targets") or {}).get("home_m2") or U.LEVEL0_HOME_M2)
    land = [L for L in K.lots(ctx) if L["use"] == "landmark"]
    homes = sum(b["homes"] for b in B) + sum(L["capacity"].get("homes", 0) for L in land)
    jobs = sum(b["jobs"] for b in B) + sum(L["capacity"].get("jobs", 0) for L in land)
    # residents: every building with homes (new housing and existing houses with homes), as rule 14 (buildings.has_homes)
    # and buildings.json totals.residents count them
    res = (sum(b["gfa_m2"] for b in B if _has_homes(b)) + sum(L["capacity"].get("homes", 0) for L in land) * home_m2) / m2_res
    ex = [b for b in B if b["source"] == "existing_osm"]
    ex_h, ex_j = sum(b["homes"] for b in ex), sum(b["jobs"] for b in ex)
    ex_res = sum(b["gfa_m2"] for b in ex if (b.get("homes") or 0) > 0) / m2_res
    # the same numbers in two files: lots.capacity vs buildings (exact)
    by_lot = {}
    for b in B:
        if b.get("lot"):
            h, j = by_lot.get(b["lot"], (0, 0))
            by_lot[b["lot"]] = (h + b["homes"], j + b["jobs"])
    for L in K.lots(ctx):
        if L["use"] == "landmark":
            continue
        h, j = by_lot.get(L["id"], (0, 0))
        ch, cj = L["capacity"].get("homes", 0), L["capacity"].get("jobs", 0)
        if abs(ch - h) > exact or abs(cj - j) > exact:
            p = L["_p"].representative_point()
            out.append(K.issue(ctx, 24, p.x, p.y, f"участок {L['id']}: в lots.json {ch} квартир / {cj} мест, в зданиях {h} / {j}", [L["id"]]))
    for b in B:
        if b["use"] == "housing" and b["homes"] != round(b["gfa_m2"] / home_m2):
            p = b["_p"].centroid
            out.append(K.issue(ctx, 24, p.x, p.y, f"здание {b['id']}: квартир {b['homes']}, по площади {b['gfa_m2'] / home_m2:.0f}", [b["id"]]))
    T = ctx.spec.get("targets") or {}
    # district targets count the new city only: keep quarters (as is) and existing (OSM) houses are not in them
    keep_h = sum(L["capacity"].get("homes", 0) for L in land if L["source"] == "keep")
    keep_j = sum(L["capacity"].get("jobs", 0) for L in land if L["source"] == "keep")
    new_h, new_j = homes - keep_h - ex_h, jobs - keep_j - ex_j
    new_res = res - keep_h * home_m2 / m2_res - ex_res
    # one number: buildings.json totals against the same counts from its buildings and the landmark lots
    tot = (ctx.buildings or {}).get("totals") or {}
    for k, got in (("homes", homes), ("jobs", jobs), ("residents", res), ("homes_existing", ex_h), ("jobs_existing", ex_j),
                   ("residents_existing", ex_res), ("homes_new", new_h), ("jobs_new", new_j)):
        if k in tot and abs(float(tot[k]) - round(got)) > exact:
            out.append(K.issue(ctx, 24, c.x, c.y, f"buildings.json totals.{k} = {tot[k]}, по зданиям и участкам-ориентирам {got:.0f}", []))
    for k, got in (("homes_2050", new_h), ("jobs_2050", new_j), ("population_2050", new_res)):
        t = T.get(k)
        if t:
            dev = (got - t) / float(t)
            if abs(dev) > tol:
                out.append(K.issue(ctx, 24, c.x, c.y, f"{k}: карта {got:.0f} против цели {t} ({dev * 100:+.1f} %, допуск ±{tol * 100:.0f} %; без кварталов "
                                   f"keep и существующих домов OSM)", []))
    return out


def _has_homes(b):
    """buildings.has_homes (rule 14): new housing or any building with homes."""
    return b["use"] == "housing" or (b.get("homes") or 0) > 0


RULES = [
    {"no": 23, "key": "years_order", "fn": check_23, "needs": ["lots", "buildings", "network", "features"]},
    {"no": 24, "key": "one_number", "fn": check_24, "needs": ["lots", "buildings"]},
]
