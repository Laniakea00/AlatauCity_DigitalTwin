"""Buildings of a district (w44, CONTRACT §4): python3 tools/map/gen/gen_buildings.py <district> [--out OUT] [--spec S]

Reads   spec, OUT/<d>/lots.json + blocks.json (gen_blocks_lots), OUT/<d>/network.json, the twin (buildings.csv, layer_buildings.bytes),
        Overture buildings of level 0, norms.json, the twin's panel formulas (Tools/twin_gen/norms.py: m² per resident and per job).
Writes  OUT/<d>/buildings.json {schema:"qtwin.buildings/1", buildings:[…], removed:[bids], solar:[{polygon, years}], log, totals}
        and updates lots.json capacity (homes, jobs) so the lots and the buildings carry the same numbers (rule 24).
        Then runs land_driveways.py: OUT/<d>/driveways.json (drives and fire lanes, network format).

Rules it follows
 * Existing houses (twin existing_osm rows and Overture houses the twin lacks) stay with source existing_osm and years 2025, unless
   they cross a new street's red line (then removed with a log line; twin bids go to `removed`). Twin rows keep their mesh (bid set,
   keep_mesh true); Overture-only houses get bid null and are extruded by merge.
 * Twin generated and master-plan buildings inside the area are replaced (their bids go to `removed`); solar panels go to `solar`.
 * New buildings stand inside their lot: setback from the red line by street class (setbacks.red_line_m), housing ≥ the norm from the
   carriageway of expressways and arterial roads (setbacks.housing_from_arterial_carriageway_m), school and kindergarten buildings
   ≥ schools/kindergartens.building_from_red_line_m from the red line, gaps by building_gaps and fire_access, floors and height cap
   of the zone; homes and jobs per zone are calibrated to the zone densities (district total vs spec.targets ±5 %).
 * Models: no more than validator.identical_models.max_same_model of one model in validator.identical_models.radius_m (rule 18);
   typical schools, kindergartens and warehouses keep one model.
 * Years: never earlier than the street that serves the lot, in every scenario; build_years = [land, frame, facade, landscaping]
   (base scenario); new buildings get bid null (merge numbers them)."""
import math
import re
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
import shapely.affinity  # noqa: E402
from shapely.geometry import Point  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import land_models as M  # noqa: E402
import land_util as U  # noqa: E402

KIND_OF = {"school": ("education", "social"), "kindergarten": ("education", "social"), "polyclinic": ("health", "social"),
           "hospital": ("health", "social"), "clinic": ("health", "social"), "pharmacy_shop": ("retail", "business"),
           "fire_station": ("public", "social"), "police": ("public", "social"), "college": ("education", "social"),
           "university": ("education", "social"), "culture": ("culture", "business"), "worship": ("culture", "business")}
MERGE_BRIDGE_M = 0.5    # the closing that joins two near sections of a lot reaches this past half their gap (m, model qTwin)
MERGE_GROW = 1.6        # … and the joined footprint is at most this × the two (a court left open, not filled; model qTwin)
SHRINK_MIN_M2 = 150.0   # a footprint of a low-density zone is not shrunk below this (m², model qTwin)
SWAP_ROUNDS = 6         # rounds of the local search over the tall / low pairs of the fire gaps (model qTwin)
VARY_NEAR_M = 30.0      # m: footprints this near are neighbours that should differ in height (tester item 100, model qTwin)
VARY_FP_TOL = 0.35      # … when their footprints differ by at most this share (one floor up and one down keeps the area; model qTwin)
STRAY_OUT_M2 = 1.0        # m²: an existing building off its own plot by more than this keeps new ones a fire gap away — модель qTwin
GAP_TOL_M = 0.05        # a fire gap within this of the norm counts as kept (footprints are written to 0.01 m; model qTwin)


def kind_for(use, floors):
    if use == "housing":
        return "res_high" if floors >= 10 else "res_mid"
    if use == "business":
        return "tower" if floors >= 16 else "business"
    if use == "industry":
        return "industry"
    return "public"


VILLAGE_NEAR_USES = ("village_existing", "reserve")   # zones whose social buildings stand near the street (village lanes)
NEAR_TOL = 1.0          # m inside the building-line limit for a building placed near the street: rounding (model qTwin)


def duration(floors):
    """Construction years by height (model qTwin; the twin's construction.json uses 2-year typical durations)."""
    return 2 if floors <= 5 else (3 if floors <= 16 else 4)


def years_for(street_years, y_land_min, floors, use):
    """Base completion year Y ≥ land + duration with land ≥ street base year and effective years ≥ street years in every
    scenario. Returns (years4, build_years)."""
    dur = duration(floors)
    sy = street_years or [2026] * 4
    Y = max(y_land_min, sy[0]) + dur
    for _ in range(40):
        e = U.effective_years(Y, use)
        if all(a >= b for a, b in zip(e, sy)) and Y <= 2050:
            break
        Y += 1
    Y = min(Y, 2050)
    land = Y - dur
    bys = [land, min(Y, land + 1), max(land + 1, Y - 1), Y]
    return U.effective_years(Y, use), bys


def run(d, out, spec_path=None, dense_zones=frozenset(), _memo=None):
    """dense_zones: tall zones that keep sections on the lot lines inside a block (no fire lane there) because their floor
    area does not fit otherwise; filled by the first pass itself. _memo: what the first pass read and found that the second
    pass reuses as it is (the twin's buildings, the existing houses)."""
    memo = {} if _memo is None else _memo
    t0 = memo.setdefault("t0", time.time())       # both passes in the time printed
    spec = U.load_spec(d, spec_path)
    norms = U.Norms()
    log = U.Log()
    od = U.out_dir(out, d)
    out_root = out
    lots_doc = U.read_json(os.path.join(od, "lots.json"))
    blocks_doc = U.read_json(os.path.join(od, "blocks.json"))
    net = U.read_json(os.path.join(od, "network.json"))
    if not lots_doc or not net:
        raise SystemExit("run gen_blocks_lots first")
    work = U.work_polygon(spec)
    m2_res, m2_job, _, _ = U.twin_m2()
    m2_seat, m2_kg = U.social_m2(norms)
    # the smallest school and kindergarten of the norms (as gen_blocks_lots sizes them): the lowest band of the plot table or the
    # city minimum, a kindergarten at least one full group
    soc_min = {"school": max(min(U._band(k)[0] for k in norms.v("schools.plot_m2_per_pupil")), norms.num("schools.min_places_city")),
               "kindergarten": max(norms.v("kindergartens.group_size_max", "3-7_years"), norms.num("kindergartens.min_places_city"))}
    import importlib.util
    sp = importlib.util.spec_from_file_location("twin_gen_norms", os.path.join(U.TWIN_GEN, "norms.py"))
    tn = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(tn)
    home_m2 = float((spec.get("targets") or {}).get("home_m2") or U.LEVEL0_HOME_M2)
    fh = U.floor_heights()
    lots = lots_doc["lots"]
    for L in lots:
        L["_p"] = U.geom(L)
    blk = {b["id"]: b for b in blocks_doc["blocks"]}
    zones = {z["id"]: (z, U.from_coords(z["polygon"]), U.zone_rules(z)) for z in spec["zones"]}
    segs = {s["id"]: s for s in net["segments"]}

    # ---------------------------------------------------------------- the twin inside the area
    import twin
    if "df" not in memo:
        memo["df"] = twin.buildings()
    df = memo["df"]
    x0, z0, x1, z1 = work.bounds
    m = (df.x > x0) & (df.x < x1) & (df.z > z0) & (df.z < z1)
    rows = df[m]
    inside = shapely.contains_xy(work, rows.x.values, rows.z.values)
    rows = rows[inside]
    removed, solar = [], []
    fps = twin.footprints(rows[rows.kind == "solar"].bid.values) if (rows.kind == "solar").any() else {}
    for r in rows.itertuples():
        if r.source == "existing_osm":
            continue
        removed.append(int(r.bid))
        if r.kind == "solar":
            p = fps.get(int(r.bid))
            if p is not None:
                solar.append({"polygon": U.coords(p), "years": U.effective_years(int(r.year), r.use, r.source), "bid_was": int(r.bid)})
    log("сгенерированные здания двойника внутри area заменены", [], count=len(removed) - len(solar))
    if solar:
        log("панели СЭС двойника перенесены в слой solar", [], count=len(solar))

    # ---------------------------------------------------------------- existing houses
    from gen_blocks_lots import existing_houses
    keep_union = unary_union([U.from_coords(k["polygon"]) for k in spec.get("keep", [])]) if spec.get("keep") else U.Polygon()
    if "houses" not in memo:
        memo["houses"] = existing_houses(work, keep_union)
    houses = memo["houses"]
    if "red_polys" not in memo:
        memo["red_polys"] = U.network_polys(net, norms, "red")
    red = memo["red_polys"]
    new_red = [(s, p) for s, p, lv in red if s["years"][0] > 2025]
    nt = U.strtree([p for _, p in new_red]) if new_red else None
    ltree = U.strtree([L["_p"] for L in lots])
    csv_fl = {int(b_): (int(f_), float(h_)) for b_, f_, h_ in zip(rows.bid.values, rows.floors.values, rows.height_m.values)}
    out = []
    for hh in houses:
        fp = hh["fp"]
        hit = []
        if nt is not None:
            hit = [new_red[j][0]["id"] for j in nt.query(fp, predicate="intersects") if new_red[j][1].intersection(fp).area > 1.0]
        if hit:
            log("существующий дом снесён: его пересекает новая улица", [hh["bid"] if hh["bid"] is not None else hh["src"]], streets=hit)
            if hh["bid"] is not None:
                removed.append(hh["bid"])
            continue
        if hh["bid"] is not None and hh["bid"] in csv_fl:
            fl, hgt = csv_fl[hh["bid"]]
        else:
            fl = int(hh.get("floors") or 1)          # Overture's floor count, as gen_blocks_lots counts its residents
            hgt = round(fl * fh.get("existing", 4.8), 1)
        c = fp.centroid
        lot = None
        for j in ltree.query(c, predicate="intersects"):
            lot = lots[int(j)]["id"]
            break
        gfa_e = round(fp.area * fl, 1)
        h_e, j_e = U.existing_load(gfa_e, home_m2)          # the traffic model's rule: a home up to 600 m², else workplaces
        out.append({"id": None, "bid": hh["bid"], "lot": lot, "footprint": U.coords(fp), "floors": fl, "height_m": round(hgt, 1),
                    "base_y": round(float(U.h(c.x, c.y)), 2), "use": "existing", "kind": "existing", "model": "existing",
                    "source": "existing_osm", "registry_id": None, "years": list(U.EXISTING_YEARS), "build_years": list(U.EXISTING_YEARS),
                    "gfa_m2": gfa_e, "homes": h_e, "jobs": j_e, "keep_mesh": hh["bid"] is not None,
                    "origin": "twin" if hh["bid"] is not None else hh["src"]})

    # ---------------------------------------------------------------- new buildings: layout per lot
    if "corr_red" not in memo:      # the network's own geometry: the same in both passes
        memo["corr_red"] = unary_union([p for _, p, _ in red]) if red else U.Polygon()
        memo["housing_ban"] = U.clean(unary_union([p for s, p, lv in U.network_polys(net, norms, "carriage") if s["class"] in U.ARTERIAL_ROADS]).buffer(
            norms.v("setbacks.housing_from_arterial_carriageway_m", "default")))
        memo["offgrade"] = U.offgrade(net, norms)
        # homes keep szz.rail_m from railway tracks too (rule 15: a new house nearer is an error): offices there
        rail_b = U.rail_housing_band(work, norms)
        memo["rail_band"] = rail_b
        if not rail_b.is_empty:
            memo["housing_ban"] = U.clean(unary_union([memo["housing_ban"], rail_b]))
            log("жильё не ближе szz.rail_m (от оси крайнего пути) к железной дороге: пятна в этой полосе — офисы (правило 15)", [],
                band_ha=round(rail_b.intersection(work).area / 1e4, 1))
    corr_red = memo["corr_red"]

    def red_buf(dist):
        """The red lines widened by dist (once per distance: the whole network is buffered)."""
        if ("red", dist) not in memo:
            memo[("red", dist)] = corr_red.buffer(dist)
        return memo[("red", dist)]
    rl_tree = U.strtree([p for _, p, _ in red])
    housing_ban = memo["housing_ban"]
    nobuild = []
    w_cable = norms.v("utilities.to_foundations_m", "cables")
    for c in U.corridors(spec):
        if c.get("state") != "cable":
            # the protected zone as gen_blocks_lots and rule 4 take it (by voltage for a power line), else the axis ± 1 m
            key = {"power_line": "utilities.power_line_protection_zone_m", "gas": "utilities.gas_pipeline_protection_zone_m"}.get(c["kind"])
            w = U.power_zone_m(norms, c)[0] if c["kind"] == "power_line" else (c.get("width_m") or (norms.v(key) if key else None))
            nobuild.append(shapely.geometry.LineString(c["line"]).buffer(max(1.0, w if isinstance(w, (int, float)) else 0.0)))
        else:
            nobuild.append(shapely.geometry.LineString(c["line"]).buffer(w_cable))      # a cable: foundations keep off it
    nobuild += [p["poly"] for p in memo["offgrade"]]     # landings, ramps, embankments and cuts of streets with their slopes
    # the elevated spans (LRT viaduct, street bridges and overpasses) with the fire gap round them: no building under a deck
    # (golden B2127: three offices under the LRT span, roof 633.1 m over a span bottom of 612.4 m, rule 25 — w50)
    if "spans" not in memo:
        memo["spans"] = U.span_bands(net, U.read_json(os.path.join(od, "lrt.json")), norms, spec)
    span_gap = norms.v("building_gaps.fire_between_buildings_m", "I-II_to_I-II")
    nobuild += [q.buffer(span_gap, cap_style="flat", join_style="mitre") for q in memo["spans"]]
    # an existing building that stays on land of a new lot (no existing lot round it: a twin building the lots were cut over)
    # keeps the fire gap from the new ones (Gate: a school 87 m² and a pharmacy 207 m² over two twin buildings, rule 1)
    fire_gap_ = norms.v("building_gaps.fire_between_buildings_m", "I-II_to_I-II")
    # — and one that stands partly off its own existing plot (a village cell cut through a large house: a kindergarten and a
    # polyclinic over b00827, Gate G4)
    src_of = {L["id"]: L["source"] for L in lots}
    lot_p_ = {L["id"]: L["_p"] for L in lots}
    stray = [fo.buffer(fire_gap_, join_style="mitre") for o in out for fo in [U.from_coords(o["footprint"])]
             if o["lot"] is None or src_of.get(o["lot"]) not in ("existing", "keep") or fo.difference(lot_p_[o["lot"]]).area > STRAY_OUT_M2]
    if stray:
        nobuild += stray
        log("существующие здания на земле новых участков (без своего участка или за его границей): новые здания держат от них пожарный разрыв", [],
            n=len(stray), gap_m=fire_gap_)
    nobuild = U.clean(unary_union(nobuild)) if nobuild else U.Polygon()
    sb_art = norms.v("setbacks.red_line_m", "arterial_streets")
    sb_res = norms.v("setbacks.red_line_m", "residential_streets")
    gap_low = norms.v("building_gaps.long_sides_m", "2_3_floors")
    gap_4 = norms.v("building_gaps.long_sides_m", "4_floors")
    fire_w = norms.v("fire_access.width_min_m", "default")
    dw_keys = norms.v("fire_access.distance_to_wall_m")
    hi_key = next(k for k in dw_keys if re.search(r"over_(\d+)m", k))
    tall_h = float(re.search(r"over_(\d+)m", hi_key).group(1))        # 28 m: the fire band 8–10 m from the wall applies
    wall_hi = dw_keys[hi_key]["min"]
    wall_hi_max = dw_keys[hi_key]["max"]
    drive_sw = U.profile_from_norms(norms, "driveway_main")["sidewalk_w"][0]     # an inner fire lane's sidewalk
    wall_lo = norms.v("fire_access.distance_to_wall_m", "building_10_28m")["min"]
    wall_lo_max = norms.v("fire_access.distance_to_wall_m", "building_10_28m")["max"]
    fire_gap = norms.v("building_gaps.fire_between_buildings_m", "I-II_to_I-II")
    # between warehouse sheds (fire_access.industrial_sides: access on all sides over 10 000 m²): a fire lane with the
    # wall distances on both sides, never less than the fire gap between buildings
    ind_gap = max(fire_gap, norms.v("fire_access.width_min_m", "default") + 2 * norms.v("fire_access.distance_to_wall_m", "building_10_28m")["min"])
    line_max = norms.v("setbacks.building_line_max_m", "max_from_carriageway")
    if "street_car" not in memo:
        memo["street_car"] = [p for s, p, lv in U.network_polys(net, norms, "carriage")
                              if s["class"] in U.DRIVABLE and s["class"] not in U.NO_ACCESS and lv == 0]
        memo["street_car_t"] = U.strtree(memo["street_car"]) if memo["street_car"] else None
    ring_res = norms.v("fire_access.ring_required", "residential_over_m")
    ring_other = norms.v("fire_access.ring_required", "other_over_m")

    ind_area, ind_need = defaultdict(float), {}
    blk_net = defaultdict(float)
    for bb in blk.values():
        blk_net[bb["zone"]] += U.geom(bb).area
    for L in lots:
        z, zp, rules = zones.get(blk[L["block"]]["zone"], (None, None, {}))
        # every industrial plot of the zone shares its job floor area — a registry park too (else a zone whose only rule plot
        # was merged into the registry one would lose its need)
        if z is not None and rules.get("lot_split") == "industrial" and L["source"] in ("rule", "registry") and not L.get("nobuild") \
                and L["use"] in ("logistics", "industry"):
            ind_area[z["id"]] += L["_p"].area
            # the zone's job floor area on its net block area (the zone report and the spec targets read the densities so)
            ind_need[z["id"]] = (rules.get("jobs_per_ha") or 0) * blk_net.get(z["id"], 0.0) / 1e4 * m2_job.get("industry", 100.0)
    cand = []     # new buildings before floors: {lot, fp, use, family, ...}
    lane_zones = set()      # tall zones with fire lanes kept along the inner lot lines
    landmark_cap = []
    for L in lots:
        b = blk[L["block"]]
        z, zp, rules = zones.get(b["zone"], (None, None, {}))
        if L["use"] == "landmark":
            landmark_cap.append(L)          # a keep quarter or a registry object with its own Unity model: no buildings by rule
            continue
        hub = L.get("hub") or {}
        if hub.get("build"):
            # a transit hub's part (land_transit, модель qTwin): its station hall / bus terminal / canopy as laid out on the lot
            for hb in hub["build"]:
                fp = U.from_coords(hb["footprint"])
                if not L["_p"].buffer(0.5).contains(fp):
                    continue            # the building stands on the other piece of this part
                gfa = hb.get("gfa_m2", fp.area * hb["floors"])
                cand.append({"lot": L["id"], "_lot": L, "_zone": b["zone"], "_rules": rules, "fp": fp, "use": "business",
                             "kind": hb["kind"], "_family": hb["family"], "_typical": True, "_fixed_gfa": max(gfa, 1.0),
                             "_floors": (hb["floors"], hb["floors"]), "_height": hb["height_m"], "_no_gfa": gfa <= 0,
                             "registry_id": hub.get("of")})
            continue
        if L["source"] in ("existing", "keep") or L.get("nobuild") or L["use"] in ("park", "square", "reserve", "utility", "village_existing", "transit", "playground", "sport_ground", "parking"):
            continue
        p = L["_p"]
        # setback by the classes of the streets that touch the lot
        near = [red[int(j)][0] for j in rl_tree.query(p.buffer(2.0), predicate="intersects")]
        sb = max([sb_art if s["class"] in U.ARTERIAL_STREETS | U.ARTERIAL_ROADS else sb_res for s in near] + [rules.get("setback_m") or sb_res])
        fl_top = (rules.get("floors") or [3, 9])[1]
        if L["use"] not in KIND_OF and rules.get("lot_split") == "towers" and fl_top * fh.get("tower", 4.0) > ring_other:
            # buildings that may rise over the ring height need a fire lane on every side: where the street carriageway
            # is too far from the building line (wide streets), the lane runs inside the lot, so the line steps back
            for s_ in near:
                if s_["class"] in U.DRIVABLE:
                    pr_ = U.seg_profile(net, s_, norms)
                    if U.red_half(pr_) - U.carriage_half(pr_) + sb > wall_hi_max:
                        sb = max(sb, wall_hi + fire_w + drive_sw)
        region = U.clean(p.buffer(-sb, join_style="mitre").difference(nobuild))
        if region.is_empty:
            continue
        acc = segs.get(L.get("access"))
        ang = U.edge_angle_to(p, U.seg_line(acc)) if acc else U.axis(p)[0]
        base = {"lot": L["id"], "_lot": L, "_zone": b["zone"], "_rules": rules}
        if L["use"] in KIND_OF:
            kind, use = KIND_OF[L["use"]]
            cap = L.get("capacity", {})
            fl = M.SOCIAL_FLOORS.get(L["use"], (2, 4))
            vil = "village" if (z and z["use"] == "village_existing") else "city"
            if L["use"] == "school":
                gfa = cap.get("places", 0) * m2_seat
                region = U.clean(region.difference(red_buf(norms.v("schools.building_from_red_line_m", vil))))
            elif L["use"] == "kindergarten":
                gfa = cap.get("places", 0) * m2_kg
                region = U.clean(region.difference(red_buf(norms.v("kindergartens.building_from_red_line_m", vil))))
            elif L["use"] == "polyclinic":
                gfa = cap.get("visits_per_shift", 0) * tn.M2_PER_CLINIC_VISIT
            elif L["use"] == "pharmacy_shop":
                gfa = p.area * 0.35
            elif L["use"] == "fire_station":
                gfa = p.area * 0.25
            else:
                gfa, fl = p.area * 0.5, (2, 4)
            if gfa <= 0:
                log("участок соцобъекта без вместимости: здание не ставится", [L["id"]], use=L["use"], warn=True)
                continue
            fp = None
            if z and z["use"] in VILLAGE_NEAR_USES:
                # a village (or village-edge) plot: the building stands within the building-line limit of the street
                # carriageway on every side, so the village lane is its fire access all round — a drive may not attach to a
                # village service lane (driveway_* in the network; merge takes it for a drive) and rarely gets through
                cs_ = [memo["street_car"][int(j)] for j in memo["street_car_t"].query(region, predicate="dwithin", distance=line_max)] \
                    if memo["street_car_t"] is not None else []
                near_r = U.clean(region.intersection(unary_union(cs_).buffer(line_max - NEAR_TOL))) if cs_ else U.Polygon()
                if not near_r.is_empty:
                    fp = M.social_place(near_r, gfa, fl[1], ang, None)
            # with the fire ring inside the lot first; without it (ring on the street) if the lot is too small
            if fp is None:
                fp = M.social_place(region, gfa, fl[1], ang, (fire_w + wall_lo) if L["use"] in M.SOCIAL_RING_LOT else None)
            ax_ = U.axis(p)[0]
            if fp is None and abs(ax_ - ang) > 1e-6:
                # square to the plot's own axis, as gen_blocks_lots tested the plot (building_fit): a long plot oblique to its
                # access street held the building that way only (Gate G8: five school and kindergarten plots left empty, rule 13)
                fp = M.social_place(region, gfa, fl[1], ax_, (fire_w + wall_lo) if L["use"] in M.SOCIAL_RING_LOT else None)
            if fp is None:
                # the plot is too tight for the floor area of its capacity with the norm setbacks: the spec's own plot of a
                # registry object (w47), or a plot the lot shaping changed after gen_blocks_lots tested it — a smaller building
                fp = M.social_place(region, gfa, fl[1], ang, (fire_w + wall_lo) if L["use"] in M.SOCIAL_RING_LOT else None,
                                    share=M.SOCIAL_FIT_TIGHT)
                if fp is not None:
                    # the data says what the building holds (tester item 42: 200 places in lots.json, a building for 170):
                    # places = floor area / m² per place (kindergartens.building_m2_per_place, schools.building_m2_per_seat)
                    key_, per_ = {"school": ("places", m2_seat), "kindergarten": ("places", m2_kg),
                                  "polyclinic": ("visits_per_shift", tn.M2_PER_CLINIC_VISIT)}.get(L["use"], (None, None))
                    was_ = cap.get(key_) if key_ else None
                    if key_ and was_:
                        cap[key_] = int(math.floor(fp.area * fl[1] / per_ + 1e-6))
                    if key_ and was_ and cap[key_] < soc_min.get(L["use"], 0):
                        # under the smallest school or kindergarten of the norms (Gate G4: a village school of 18 places,
                        # below the plot table's lowest band — rule 13 could not read it): no building, the plot a playground
                        log("участок соцобъекта не вмещает здание и на наименьшую вместимость по нормам: здания нет, участок — "
                            "сквер-площадка у домов", [L["id"]], use=L["use"], capacity_was=was_, holds=cap[key_],
                            min_capacity=soc_min[L["use"]], warn=True)
                        for k_ in ("norm_key", "plot_norm_m2"):
                            L.pop(k_, None)
                        L.update(use="playground", capacity={}, label_ru="сквер-площадка у домов: участок соцобъекта мал для здания (модель qTwin)")
                        continue
                    log("участок соцобъекта не вмещает здание на всю вместимость с нормативными отступами — здание меньше, "
                        "вместимость участка по зданию" + (" (участок спецификации, w47)" if L["source"] == "registry" else ""),
                        [L["id"], L.get("registry_id")], use=L["use"], need_m2=round(gfa), got_m2=round(fp.area * fl[1]),
                        capacity_was=was_, capacity=cap.get(key_) if key_ else None, warn=True)
                    gfa = fp.area * fl[1]
            if fp is None:
                log("социальное здание не помещается на участке с нормативными отступами", [L["id"]], use=L["use"], warn=True)
                continue
            cand.append({**base, "fp": fp, "use": use, "kind": kind, "_family": L["use"] + "_typical", "_typical": True,
                         "_fixed_gfa": gfa, "_floors": fl, "registry_id": L.get("registry_id")})
            continue
        split = rules.get("lot_split", "none")
        fl_lo, fl_hi = (rules.get("floors") or [3, 9])
        n0 = len(cand)
        if split == "perimeter":
            depth = M.SECTION_DEPTH["housing"]
            secs = M.ring_sections(p, sb, depth, M.SECTION_LEN, max(fire_gap, 2 * fire_w))
            for s_ in secs:
                cand.append({**base, "fp": s_, "use": "housing", "_family": "res_perim", "_typical": False})
        elif split == "towers":
            # perimeter sections on the street frontage and towers in the court (gaps: building_gaps, fire_access)
            hgt = fl_hi * fh.get("res_high", 3.4)
            fam = "office" if b["use"] in ("business", "mixed_centre") else "res_perim"
            depth = M.SECTION_DEPTH["business" if fam == "office" else "housing"]
            gap = max(gap_4, 2 * (fire_w + (wall_hi if hgt > tall_h else wall_lo)))
            sec_gap = max(fire_gap, 2 * fire_w)
            inner_ban = U.Polygon()
            p_sec = p
            join_ = None
            if fl_lo * fh.get("business" if fam == "office" else "res_high", 3.4) > tall_h:
                lane_zones.add(b["zone"])
                # the zone's lowest buildings are already over 28 m: a fire lane 8–10 m from every wall must fit between
                # sections (2 × wall distance + lane) and along the lot lines inside the block (half of that on each side)
                sec_gap = max(sec_gap, 2 * wall_hi + fire_w + 2 * GAP_TOL_M)      # over the 0.01 m rounding
                join_ = sec_gap         # sections of the ring nearer than the gap (across a corner) are one building
                inner_edge = p.exterior.difference(red_buf(sb + 2.0))
                if not inner_edge.is_empty:
                    half = wall_hi + fire_w / 2.0 + GAP_TOL_M
                    inner_ban = inner_edge.buffer(half)
                    if b["zone"] not in dense_zones and half > sb:
                        # the sections along a lot line inside the block step back to half the lane gap from it (they were
                        # left out before, tester items 118–119: the zone short of floor area): the neighbour's sections do
                        # the same, so the two rows stand a fire gap apart with the lane between them, and all may rise
                        p_sec = U.clean(p.difference(inner_edge.buffer(half - sb + GAP_TOL_M, join_style="mitre")))
                        p_sec = max(U.polys(p_sec, 1.0), key=lambda q: q.area, default=p)
            for s_ in M.ring_sections(p_sec, sb, depth, M.SECTION_LEN, sec_gap, join_below=join_):
                if not inner_ban.is_empty and s_.intersects(inner_ban) and b["zone"] not in dense_zones:
                    continue
                cand.append({**base, "fp": s_, "use": "housing", "_family": fam, "_typical": False})
            court = U.clean(p.buffer(-(sb + depth + gap), join_style="mitre").difference(nobuild).difference(inner_ban if b["zone"] not in dense_zones else U.Polygon()))
            side = M.TOWER_SIDE["business" if b["use"] == "business" else "housing"]
            if not court.is_empty:
                for t in M.towers(court, side, gap, ang):
                    cand.append({**base, "fp": t, "use": "housing", "_family": "tower", "_typical": False})
        elif split == "houses":
            # one detached house per plot: floor area by the zone's far (else the estate kpz of quarters.kz_kpz_residential)
            # over the plot, footprint over the top floors, as large as the buildable part holds
            far = rules.get("far") or norms.v("quarters.kz_kpz_residential", "estate")["kpz"]
            want = p.area * far / max(fl_hi, 1)
            fp = None
            for aspect in (1.4, 1.0, 2.0):
                fp = M.place_rect(region, min(want, region.area * 0.8), ang, aspect, min_area=M.HOUSE_MIN_M2)
                if fp is not None:
                    break
            if fp is not None:
                cand.append({**base, "fp": fp, "use": "housing", "_family": "house", "_typical": False})
            else:
                log("дом не помещается на участке с отступами (раздел houses)", [L["id"]], plot_m2=round(p.area), buildable_m2=round(region.area),
                    error=True)
        elif split == "rows":
            gap = gap_low if fl_hi <= 3 else gap_4
            n_s = len(cand)
            for s_ in M.slabs(region, M.SLAB_DEPTH, gap, ang, M.SECTION_LEN):
                cand.append({**base, "fp": s_, "use": "housing", "_family": "slab", "_typical": False})
            if len(cand) == n_s:
                # a plot too narrow for the slab depth: a house-sized block instead of nothing
                fp = M.place_rect(region, region.area * 0.5, ang, 1.4, min_area=M.HOUSE_MIN_M2)
                if fp is not None:
                    cand.append({**base, "fp": fp, "use": "housing", "_family": "house", "_typical": False})
                else:
                    log("секция ряда не помещается на участке с отступами", [L["id"]], plot_m2=round(p.area), buildable_m2=round(region.area),
                        error=True)
        elif split == "industrial":
            # warehouse footprint = the zone's job floor area spread over its industrial lots (1-storey sheds of the zone)
            want = ind_need.get(b["zone"], 0.0) * p.area / max(ind_area.get(b["zone"], 1.0), 1.0) / max(fl_lo, 1)
            big = max(U.polys(region, 1.0), key=lambda q: q.area, default=None)
            if big is not None and want and big.area * 0.9 <= want:
                basis = min(big.area, want)          # the zone's floor area, as far as a shed filling the buildable part holds it
                fp = M.place_rect(region, big.area * 0.9, ang, 2.5)       # as a rectangle
            else:
                fp = M.place_rect(region, min(region.area * 0.9, want or region.area * 0.5), ang, 2.5)
                basis = fp.area if fp is not None else 0.0
            sheds = M.warehouses(region, ang, M.TRUCK_YARD, ind_gap, p) if basis > 0 else []
            if sheds:
                # a logistics park: class-A sheds round shared truck courts with fire gaps; the lot keeps the zone's floor
                # area (the sheds' footprint, mezzanine and office floors carry the rest), shared out by footprint
                tot = sum(q["fp"].area for q in sheds)
                for q in sheds:
                    cand.append({**base, "fp": q["fp"], "use": "industry", "kind": "industry", "_family": "warehouse", "_typical": True,
                                 "_gfa_lot": max(basis, tot), "_gfa_share": q["fp"].area / tot, "_dock": q})
                log("склады: участок разбит на корпуса класса А вокруг общих дворов для фур с пожарными разрывами (модель qTwin)", [L["id"]],
                    sheds=len(sheds), footprint_m2=round(tot), gfa_m2=round(max(basis, tot)), zone_need_m2=round(want))
            elif fp is not None:
                cand.append({**base, "fp": fp, "use": "industry", "kind": "industry", "_family": "warehouse", "_typical": True,
                             "_gfa_lot": basis, "_gfa_share": 1.0})
        elif split == "campus":
            for t in M.towers(region, 40.0, max(gap_4, 2 * (fire_w + wall_lo)), ang, max_n=8):
                cand.append({**base, "fp": t, "use": "business", "_family": "campus", "_typical": False})
        if not housing_ban.is_empty:
            for c_ in cand[n0:]:
                if c_["use"] == "housing" and c_["fp"].intersection(housing_ban).area > 1.0:
                    c_["_noh"] = True        # within the norm distance of an expressway carriageway or a railway: offices only

    cand = [dict(c_, fp=q) for c_ in cand for q in U.no_holes(c_["fp"], 20.0)]
    if not nobuild.is_empty:
        # sections are laid from the lot edge, and the other footprints only inside region: every footprint is cut off the
        # strips with a margin over the coordinate rounding (no area tolerance: a building 0.9 m² into the 0.6 m strip of a
        # cable stood there before); a footprint left with less than NOBUILD_KEEP_SHARE of itself is left out
        if "nb_clear" not in memo:
            memo["nb_clear"] = U.clean(nobuild.buffer(M.NOBUILD_CLEAR_M))
            shapely.prepare(memo["nb_clear"])
        nb = memo["nb_clear"]
        kept, n_cut, n_out = [], 0, 0
        for c_ in cand:
            q = M.clear_of(c_["fp"], nb)
            if q is None:
                n_out += 1
            elif q is c_["fp"]:
                kept.append(c_)
            else:
                kept.append(dict(c_, fp=q))
                n_cut += 1
        cand = kept
        if n_cut or n_out:
            log("здания на охранной зоне, кабеле или насыпи улицы: обрезаны по полосе или убраны", [], cut=n_cut, removed=n_out)

    # ---------------------------------------------------------------- fire gaps between tall buildings
    # two buildings over 28 m stand at least 2 × the near band edge + the lane width apart, so a fire lane 8–10 m from both
    # walls fits between them (fire_access.distance_to_wall_m, fire_access.width_min_m; CONTRACT §8 «high-rise zones keep
    # 22 m fire gaps», tester item 71). Of a nearer pair only one may rise over 28 m: the larger footprint first (greedy
    # independent set over the pairs); the other keeps to 28 m (`_low`), and where the zone's lowest floors are already over
    # 28 m it is left out in the calibration below (its land stays as courtyard)
    tall_gap = 2 * wall_hi + fire_w

    def low_floors(use):
        """Most floors a building of this use has at or below the fire-band height."""
        f = 1
        while (f + 1) * fh.get(kind_for(use, f + 1), 3.6) <= tall_h + 1e-9:
            f += 1
        return f

    def may_rise(c_):
        if c_.get("_fixed_gfa") is not None or c_["use"] == "industry":
            return False
        r_ = c_["_rules"]
        top = (r_.get("floors") or [3, 9])[1]
        hmax_ = max(top * fh.get(kind_for(u, top), 3.6) for u in ("housing", "business"))
        if r_.get("height_cap_m"):
            hmax_ = min(hmax_, r_["height_cap_m"])
        return hmax_ > tall_h
    # sections of one lot nearer than the fire gap (pieces of a ring cut at its hole, the two legs at a corner, a row cut by the
    # blades) become one building, nearest pair first, while the union stays one polygon without a court inside: the whole
    # may rise, where before one of each pair kept to 28 m (tester items 118–119)
    by_lot_r = defaultdict(list)
    for c_ in cand:
        if may_rise(c_) and not c_.get("_drop") and c_["_zone"] in lane_zones:
            by_lot_r[c_["lot"]].append(c_)
    nb_m = memo.get("nb_clear")
    n_merge = 0
    gone_ = set()
    for lid, cs_ in by_lot_r.items():
        while len(cs_) >= 2:
            best = None
            for i in range(len(cs_)):
                for j in range(i + 1, len(cs_)):
                    a_, b_ = cs_[i], cs_[j]
                    if a_["use"] != b_["use"] or a_["_family"] != b_["_family"]:
                        continue
                    d_ = a_["fp"].distance(b_["fp"])
                    if d_ >= tall_gap - GAP_TOL_M or (best is not None and d_ >= best[0]):
                        continue
                    r_ = d_ / 2.0 + MERGE_BRIDGE_M
                    u_ = U.clean(unary_union([a_["fp"].buffer(r_, join_style="mitre"), b_["fp"].buffer(r_, join_style="mitre")])
                                 .buffer(-r_, join_style="mitre"))
                    if u_.geom_type != "Polygon" or u_.interiors or u_.area > MERGE_GROW * (a_["fp"].area + b_["fp"].area) \
                            or not a_["_lot"]["_p"].contains(u_) or (nb_m is not None and u_.intersects(nb_m)):
                        continue
                    best = (d_, i, j, u_)
            if best is None:
                break
            _, i, j, u_ = best
            cs_[i]["fp"] = u_
            gone_.add(id(cs_[j]))
            del cs_[j]
            n_merge += 1
    if gone_:
        cand = [c_ for c_ in cand if id(c_) not in gone_]
        log(f"секции одного участка ближе {tall_gap:.0f} м друг к другу слиты в одно здание (без двора внутри): всё здание может "
            f"подниматься выше {tall_h:.0f} м (модель qTwin)", [], merged=n_merge)
    rise = [c_ for c_ in cand if may_rise(c_)]
    # a landmark lot whose Unity model rises over 28 m (LandmarkData.cs Height) counts as a tall building of the pairs: a
    # building nearer to its lot than the fire gap keeps to 28 m (tester item 108: an office of 48.7 m 6 m from L7's lot)
    lm_h = landmark_heights()
    lmod = U.read_json(os.path.join(os.path.dirname(os.path.abspath(__file__)), "landmark_models.json")) or {}
    models_ = lmod.get("models") or {}
    lm_tall = [L for L in landmark_cap
               if lm_h.get(L.get("landmark_model") or models_.get(L.get("registry_id")), math.inf) > tall_h]
    # a registry landmark's own plot; a keep quarter (a whole district quarter round its object) by the spec's contours of
    # its tall objects inside it (objects[].footprint of a registry id with a tall Unity model)
    lm_polys = []
    for L in lm_tall:
        if L["source"] == "registry":
            lm_polys.append(L["_p"])
            continue
        for o in spec.get("objects", []):
            if o.get("footprint") and len(o["footprint"]) >= 3 and lm_h.get(models_.get(o.get("registry_id")), 0.0) > tall_h:
                q = U.clean(U.from_coords(o["footprint"]))
                if q.intersects(L["_p"]):
                    lm_polys.append(U.clean(q.intersection(L["_p"])))
    # as-is buildings over 28 m rule 12 pairs a new one with (integ 4314976): the blocks of a kept model quarter (the Gate
    # District model round Iconic, gate_district.bytes; gate_trial b00289 stood 6.5 m from k_gate_district:m0) and existing
    # or kept houses over that height
    lm_polys += [g for g, _ in U.keep_models_tall(spec, tall_h)]
    lm_polys += [U.from_coords(r["footprint"]) for r in out if r["height_m"] > tall_h]
    if lm_polys and rise:
        lm_u = unary_union(lm_polys)
        n_lm = 0
        for c_ in rise:
            if c_["fp"].distance(lm_u) < tall_gap - GAP_TOL_M:
                c_["_low"] = True
                n_lm += 1
        if n_lm:
            log(f"здания ближе {tall_gap:.0f} м к участку ориентира выше {tall_h:.0f} м (модель Unity, LandmarkData.cs Height) не выше "
                f"{tall_h:.0f} м (модель qTwin)", sorted(L["id"] for L in lm_tall), kept_low=n_lm)
    if rise:
        r_tree = U.strtree([c_["fp"] for c_ in rise])
        order = sorted(range(len(rise)), key=lambda i: (-round(rise[i]["fp"].area, 1), round(rise[i]["fp"].centroid.x, 2), round(rise[i]["fp"].centroid.y, 2)))
        tall_ok = {}
        nbr = {}
        for i in order:
            near_ = [int(j) for j in r_tree.query(rise[i]["fp"], predicate="dwithin", distance=tall_gap - GAP_TOL_M) if int(j) != i]
            nbr[i] = near_
            tall_ok[i] = not any(tall_ok.get(j) for j in near_) and not rise[i].get("_low")
        # one tall footprint swapped for the low neighbours it alone holds down, when they have more footprint together
        # (tester items 118–119: the greedy order by size left more floor area low than it needs) — local search, a few rounds
        for _ in range(SWAP_ROUNDS):
            better = False
            for v in [i for i in order if tall_ok[i]]:
                if not tall_ok[v]:
                    continue
                cand_ = sorted([u for u in nbr[v] if not tall_ok[u] and not rise[u].get("_low")
                                and not any(tall_ok[w] for w in nbr[u] if w != v)], key=lambda u: -rise[u]["fp"].area)
                pick = []
                for u in cand_:
                    if not any(u in nbr[q] for q in pick):
                        pick.append(u)
                if sum(rise[u]["fp"].area for u in pick) > rise[v]["fp"].area + 1.0:
                    tall_ok[v] = False
                    for u in pick:
                        tall_ok[u] = True
                    better = True
            if not better:
                break
        for i in order:
            if not tall_ok[i]:
                rise[i]["_low"] = True
        n_low = sum(1 for v in tall_ok.values() if not v)
        if n_low:
            log(f"пожарные разрывы между зданиями выше {tall_h:.0f} м: ближе {tall_gap:.0f} м друг к другу выше {tall_h:.0f} м "
                "поднимается только одно (большее), остальные не выше (модель qTwin)", [], gap_m=tall_gap, kept_low=n_low, may_rise=len(rise))

    # ---------------------------------------------------------------- uses and floors per zone, calibrated to the densities
    keep_area = defaultdict(float)
    for L in landmark_cap:
        b = blk[L["block"]]
        z, zp, rules = zones.get(b["zone"], (None, None, {}))
        ha = L["_p"].area / 1e4
        L["capacity"]["homes"] = int(round(ha * (rules.get("homes_per_ha") or 0)))
        L["capacity"]["jobs"] = int(round(ha * (rules.get("jobs_per_ha") or 0)))
        L["capacity"]["by"] = "плотность зоны (здание — модель ориентира / квартала, не строка buildings.csv)"
        keep_area[b["zone"]] += L["_p"].area
    zone_net = defaultdict(float)
    for bb in blk.values():
        zone_net[bb["zone"]] += U.geom(bb).area
    byzone = defaultdict(list)
    for c_ in cand:
        byzone[c_["_zone"]].append(c_)
    zone_report = {}
    for zid, cs in byzone.items():
        z, zp, rules = zones.get(zid, (None, None, {}))
        # densities are per hectare of the zone's blocks (net of streets, LRT, water; the spec targets read them the same
        # way: «× 0,75 доля кварталов без улиц»), keep land excluded
        za = zone_net.get(zid, 0.0) - keep_area.get(zid, 0.0)
        ha = max(za, 0.0) / 1e4
        homes_t = ha * (rules.get("homes_per_ha") or 0)
        jobs_t = ha * (rules.get("jobs_per_ha") or 0)
        fl_lo, fl_hi = rules.get("floors") or [3, 9]
        cap_h = rules.get("height_cap_m")
        job_use = "industry" if z and z["use"] in ("logistics", "industry") else ("social" if z and z["use"] == "medical" else "business")
        fixed = [c_ for c_ in cs if c_.get("_fixed_gfa") is not None]
        for c_ in fixed:
            c_["_floors_set"] = max(c_["_floors"][0], min(c_["_floors"][1], int(math.ceil(c_["_fixed_gfa"] / c_["fp"].area))))
        soc_jobs = sum(c_["fp"].area * c_["_floors_set"] / m2_job.get(c_["use"], 50.0) for c_ in fixed)
        free = [c_ for c_ in cs if c_.get("_fixed_gfa") is None]
        res_need = homes_t * home_m2
        job_need = max(jobs_t - soc_jobs, 0.0) * m2_job.get(job_use, 90.0)
        # which footprints carry jobs: near expressways first (housing ban), then by distance to arterials / LRT
        tot_fp = sum(c_["fp"].area for c_ in free) or 1.0
        share_jobs = job_need / max(res_need + job_need, 1.0)
        free.sort(key=lambda c_: (not c_.get("_noh"), c_["fp"].centroid.distance(housing_ban) if not housing_ban.is_empty else 0))
        acc = 0.0
        for c_ in free:
            if c_["use"] == "industry":
                continue
            if c_.get("_noh") or acc < share_jobs * tot_fp:
                c_["use"] = job_use if job_use != "industry" else "business"
                acc += c_["fp"].area
            else:
                c_["use"] = "housing"
        # the footprints come in sizes (a ring joined at its corners is one building): when one group cannot hold its floor
        # area at the zone's top floors while the other could spare a footprint, the smallest that keeps the other group
        # whole moves over (b_cbd_n: homes 9 % short at 11 floors beside offices with room to spare)
        def top_gfa(c_, use):
            k = kind_for(use, fl_hi)
            f = fl_hi if not cap_h else min(fl_hi, int(cap_h // fh.get(k, 3.5)))
            if c_.get("_low"):
                f = min(f, low_floors(use))
            return c_["fp"].area * max(f, 1)
        jobs_use = job_use if job_use != "industry" else "business"
        for _ in range(len(free)):
            hs = [c_ for c_ in free if c_["use"] == "housing"]
            js = [c_ for c_ in free if c_["use"] != "housing" and c_["use"] != "industry"]
            cap_hh = sum(top_gfa(c_, "housing") for c_ in hs)
            cap_jj = sum(top_gfa(c_, jobs_use) for c_ in js)
            mv = None
            if res_need > 0 and cap_hh < res_need:
                ok_ = [c_ for c_ in js if not c_.get("_noh") and cap_jj - top_gfa(c_, jobs_use) >= job_need]
                mv = (min(ok_, key=lambda c_: c_["fp"].area), "housing") if ok_ else None
            elif job_need > 0 and cap_jj < job_need:
                ok_ = [c_ for c_ in hs if cap_hh - top_gfa(c_, "housing") >= res_need]
                mv = (min(ok_, key=lambda c_: c_["fp"].area), jobs_use) if ok_ else None
            if mv is None:
                break
            mv[0]["use"] = mv[1]
        if res_need <= 0:
            for c_ in free:
                if c_["use"] == "housing":
                    c_["use"] = job_use if job_use != "industry" else "business"
        for grp, need in (("housing", res_need), ("jobs", job_need)):
            g = [c_ for c_ in free if (c_["use"] == "housing") == (grp == "housing") and c_["use"] != "industry"]
            if not g:
                continue

            soft = {"on": True}

            def hmax(c_):
                k = kind_for(c_["use"], fl_hi)
                f = fl_hi
                if cap_h:
                    f = min(f, int(cap_h // fh.get(k, 3.5)))
                if c_.get("_low"):
                    f = min(f, low_floors(c_["use"]))        # its pair partner rises over 28 m: this one keeps below
                if soft["on"]:
                    # stay at or below the height that asks for ring fire access (fire_access.ring_required) while the
                    # zone's floor area allows: a ring around every tower does not fit a dense block
                    rh = ring_res if c_["use"] == "housing" else ring_other
                    f = min(f, int(rh // fh.get(k, 3.5)))
                return max(f, 1)
            fpa = sum(c_["fp"].area for c_ in g)
            f0 = need / fpa if fpa else 0
            for c_ in g:
                c_["_floors_set"] = int(min(max(round(f0), fl_lo), hmax(c_)))
            tot = sum(c_["fp"].area * c_["_floors_set"] for c_ in g)
            order = sorted(g, key=lambda c_: -c_["fp"].area)
            for _ in range(4000):
                if soft["on"] and tot < need * 0.985 and all(c_["_floors_set"] >= hmax(c_) for c_ in g):
                    soft["on"] = False        # the floor area needs the height: towers over the ring height, rings follow
                if tot < need * 0.985:
                    moved = False
                    for c_ in order:
                        if c_["_floors_set"] < hmax(c_):
                            c_["_floors_set"] += 1
                            tot += c_["fp"].area
                            moved = True
                            if tot >= need * 0.985:
                                break
                    if not moved:
                        break
                elif tot > need * 1.015:
                    moved = False
                    for c_ in order[::-1]:
                        if c_["_floors_set"] > fl_lo and tot - c_["fp"].area >= need * 0.985:
                            c_["_floors_set"] -= 1
                            tot -= c_["fp"].area
                            moved = True
                    if not moved:
                        break
                else:
                    break
            if tot > need * 1.015:
                # every footprint at the zone's lowest floors and still too much floor area: leave out court towers first,
                # then the smallest footprints (the land stays as courtyard) — but every lot keeps a building (tester item
                # 98: lots cut and left empty), and the rest is taken off the footprints themselves
                drop_order = sorted(g, key=lambda c_: (c_["_family"] != "tower", c_["fp"].area))
                left = Counter(c_["lot"] for c_ in g)
                for c_ in drop_order:
                    if tot - c_["fp"].area * c_["_floors_set"] < need * 0.985 or left[c_["lot"]] <= 1:
                        continue
                    c_["_drop"] = True
                    left[c_["lot"]] -= 1
                    tot -= c_["fp"].area * c_["_floors_set"]
                    if tot <= need * 1.015:
                        break
                if tot > need * 1.015:
                    keep_ = [c_ for c_ in g if not c_.get("_drop")]
                    f_ = need / tot
                    for c_ in keep_:
                        q = shapely.affinity.scale(c_["fp"], math.sqrt(f_), math.sqrt(f_), origin=c_["fp"].centroid)
                        if q.area >= SHRINK_MIN_M2:
                            tot -= (c_["fp"].area - q.area) * c_["_floors_set"]
                            c_["fp"] = q
                    log("зона с малой плотностью: на каждом участке здание, площадь снята с пятен зданий (модель qTwin)", [zid],
                        group=grp, need=round(need), got=round(tot), lots=len(left), share=round(f_, 3))
            # neighbours of one use at one height differ (tester item 100: identical buildings side by side): of two near
            # footprints of about one size at the same floors one goes a floor up and the other a floor down, while the
            # zone's floor area stays within its band
            live = [c_ for c_ in g if not c_.get("_drop")]
            if len(live) > 1 and need > 0:
                v_tree = U.strtree([c_["fp"] for c_ in live])
                paired = set()
                n_vary = 0
                for i in sorted(range(len(live)), key=lambda i: (round(live[i]["fp"].centroid.x, 2), round(live[i]["fp"].centroid.y, 2))):
                    if i in paired:
                        continue
                    a_ = live[i]
                    for j in sorted(int(j) for j in v_tree.query(a_["fp"], predicate="dwithin", distance=VARY_NEAR_M)):
                        b_ = live[j]
                        if j == i or j in paired or b_["use"] != a_["use"] or b_["_floors_set"] != a_["_floors_set"] \
                                or abs(a_["fp"].area - b_["fp"].area) > VARY_FP_TOL * max(a_["fp"].area, b_["fp"].area):
                            continue
                        # the smaller up while the zone has more than it needs, the larger up while it has less
                        up, dn = sorted((a_, b_), key=lambda c_: c_["fp"].area * (1 if tot > need else -1))
                        f_ = up["_floors_set"]
                        nt = tot + up["fp"].area - dn["fp"].area
                        if f_ + 1 <= hmax(up) and f_ - 1 >= max(fl_lo, 1) and need * 0.985 <= nt <= need * 1.015:
                            up["_floors_set"], dn["_floors_set"] = f_ + 1, f_ - 1
                            tot = nt
                            paired |= {i, j}
                            n_vary += 1
                            break
                if n_vary:
                    log("соседние здания одного назначения разной высоты: пара соседей одной этажности — одно на этаж выше, другое "
                        "ниже (модель qTwin, замечание 100)", [zid], group=grp, pairs=n_vary)
            zone_report.setdefault(zid, {})[grp] = {"need_m2": round(need), "got_m2": round(tot),
                                                    "footprints": len([c_ for c_ in g if not c_.get("_drop")])}
            if tot < need * 0.95:
                log("зона не набирает плотность: не хватает места при потолке этажности", [zid], group=grp, need=round(need), got=round(tot), warn=True)
        for c_ in cs:
            if c_["use"] == "industry":
                c_["_floors_set"] = max(fl_lo, 1)
        ind = [c_ for c_ in cs if c_["use"] == "industry" and not c_.get("_drop")]
        if ind and job_use == "industry":
            # the zone's sheds: the floor area the buildings carry (a park's lot floor area shared by footprint), as written
            got_i = sum(c_["_gfa_lot"] * c_["_gfa_share"] * c_["_floors_set"] if c_.get("_gfa_lot") is not None
                        else c_["fp"].area * c_["_floors_set"] for c_ in ind)
            need_i = job_need
            zone_report.setdefault(zid, {})["jobs"] = {"need_m2": round(need_i), "got_m2": round(got_i), "footprints": len(ind),
                                                       "footprint_m2": round(sum(c_["fp"].area for c_ in ind))}
            if got_i < need_i * 0.95:
                log("зона не набирает плотность: склады не вмещают площадь зоны", [zid], group="jobs", need=round(need_i), got=round(got_i), warn=True)

    under = Counter(c_["_zone"] for c_ in cand if c_.get("_low") and not c_.get("_drop")
                    and c_.get("_floors_set", 99) < (c_["_rules"].get("floors") or [3, 9])[0])
    if under:
        log(f"здания ниже нижней этажности зоны: пожарный разрыв с соседним зданием выше {tall_h:.0f} м меньше {tall_gap:.0f} м, "
            f"поэтому не выше {tall_h:.0f} м (модель qTwin; норма пожарного проезда важнее этажности зоны)", sorted(under), by_zone=dict(under))
    # a zone takes the pass that gives it more of its floor area: the pass without fire lanes on the inner lot lines is
    # tried for a zone short with them, and kept only where it does better (round 4: b_cbd_e lost 7 % in it)
    def reached(rep):
        need_ = sum(r_["need_m2"] for r_ in rep.values())
        return sum(min(r_["got_m2"], r_["need_m2"]) for r_ in rep.values()) / need_ if need_ else 1.0
    tried = memo.setdefault("reached", {})
    for zid in lane_zones:
        tried.setdefault(zid, {})[zid in dense_zones] = reached(zone_report.get(zid, {}))
    worse = {zid for zid in dense_zones if tried.get(zid, {}).get(False, -1.0) >= tried.get(zid, {}).get(True, 2.0)}
    if worse and not memo.get("final"):
        memo["final"] = True
        print(f"{d}: zones {sorted(worse)} reach less without the fire lanes on the inner lot lines: last pass with them")
        return run(d, out_root, spec_path, dense_zones=frozenset(dense_zones) - worse, _memo=memo)
    short = {zid for zid in lane_zones - set(dense_zones)
             if any(r_["got_m2"] < r_["need_m2"] * 0.95 for r_ in zone_report.get(zid, {}).values())}
    if short and not memo.get("final"):
        print(f"{d}: zones {sorted(short)} short of floor area with fire lanes on the inner lot lines: second pass without them")
        return run(d, out_root, spec_path, dense_zones=frozenset(dense_zones) | short, _memo=memo)
    for zid in sorted(dense_zones):
        log("высокая зона не набирает плотность с пожарными проездами между участками: секции стоят на внутренних границах участков, "
            "кольцевой проезд к части зданий не помещается (правило 12)", [zid], warn=True)

    # ---------------------------------------------------------------- finalize records
    plinth_pct = norms.v("validator.grading", "plinth_or_terrace_if_slope_over_pct")
    fall_max = norms.v("validator.grading", "cut_fill_max_m")
    new = []
    for c_ in cand:
        if c_.get("_drop"):
            continue
        fl = int(c_.get("_floors_set") or 1)
        use = c_["use"]
        kind = c_.get("kind") if c_.get("_typical") and c_.get("kind") else kind_for(use, fl)
        if use == "industry":
            kind = "industry"
        rules = c_["_rules"]
        hgt = round(c_["_height"] if c_.get("_height") else fl * fh.get(kind, 3.6), 1)
        if rules.get("height_cap_m") and hgt > rules["height_cap_m"] and not c_.get("_typical"):
            fl = max(1, int(rules["height_cap_m"] // fh.get(kind, 3.6)))
            hgt = round(fl * fh.get(kind, 3.6), 1)
        L = c_["_lot"]
        fp = c_["fp"]
        gfa = 0.0 if c_.get("_no_gfa") else round(fp.area * fl, 1)
        if c_.get("_gfa_lot") is not None:
            gfa = round(c_["_gfa_lot"] * fl * c_["_gfa_share"], 1)       # a shed of a logistics park: its share of the lot
        homes = int(round(gfa / home_m2)) if use == "housing" else 0
        jobs = int(round(gfa / m2_job[use])) if use in m2_job else 0
        acc = segs.get(L.get("access"))
        z, zp, zr = zones.get(c_["_zone"], (None, None, {}))
        y0, y1 = U.zone_years(z) if z else (2030, 2040)
        # phase inside the zone by the lot's place in the zone (deterministic): early lots near the access street's opening
        frac = (U.stable_hash(L["id"]) % 1000) / 1000.0
        land_min = int(round(y0 + frac * max(0, (y1 - y0) - duration(fl))))
        if L["source"] == "registry":
            # a registry object's buildings open in the object's own years (the lot's: the spec's, never before its street);
            # construction ends in the base year
            ys = list(L["years"])
            land = ys[0] - duration(fl)
            bys = [land, min(ys[0], land + 1), max(land + 1, ys[0] - 1), ys[0]]
        else:
            ys, bys = years_for(acc["years"] if acc else L["years"], max(land_min, L["years"][0]), fl, use if use != "industry" else "industry")
        g_y = L["grade_y"]
        if L.get("terraces"):
            # the terrace nearest the centroid of the footprint as written (2 decimals), as rule 3 takes it: a centroid on the
            # line between two terraces went to the other one by a millimetre (Gate G4: two schools 0.6–0.9 m off, rule 3)
            cc = U.from_coords(U.coords(fp)).centroid
            best = min(L["terraces"], key=lambda t: U.from_coords(t["polygon"]).distance(cc))
            g_y = best["grade_y"]
        plinth = None
        # on a slope over validator.grading plinth_or_terrace_if_slope_over_pct, or on ground that falls more than its
        # cut_fill_max_m under the footprint (a terraced lot and a gentle slope under a long building too: tester item 74,
        # 57 buildings), the building stands on a plinth from the lowest ground under it up to its base (tester items 4–8);
        # the terrain is sampled as merge measures it (outline and a grid inside, PLINTH_STEP_M)
        lo_, hi_ = footprint_relief(fp)
        if hi_ is not None:
            span_ = max(1.0, fp.bounds[2] - fp.bounds[0], fp.bounds[3] - fp.bounds[1])
            sl_ = (hi_ - lo_) / span_ * 100.0
            if sl_ > plinth_pct or hi_ - lo_ > fall_max:
                plinth = {"from_y": round(lo_, 2), "h_m": round(max(g_y - lo_, 0.0), 2), "slope_pct": round(sl_, 1),
                          "fall_m": round(hi_ - lo_, 2)}
        rec = {"id": None, "bid": None, "lot": L["id"], "footprint": U.coords(fp), "floors": fl, "height_m": hgt, "base_y": g_y,
               "use": use, "kind": kind, "model": None, "source": "registry" if c_.get("registry_id") else "model",
               "registry_id": c_.get("registry_id"), "years": ys, "build_years": bys, "gfa_m2": gfa, "homes": homes, "jobs": jobs,
               "keep_mesh": False, "_family": c_["_family"], "_typical": c_.get("_typical", False), "_c": (fp.centroid.x, fp.centroid.y),
               "_lotid": L["id"]}
        if hgt >= norms.num("heights.airfield_height_threshold_m"):
            rec["aviation"] = "нужно согласование"
        if plinth is not None:
            rec["plinth"] = plinth
        dk = c_.get("_dock")
        if dk is not None and fp.equals(dk["fp"]):
            # a class-A shed: its dock side (on the truck yard), dock doors and the yard in front of them (tester item 90)
            rec["dock_side"] = [[round(x, 2), round(z, 2)] for x, z in dk["dock"].coords]
            rec["docks"] = dk["docks"]
            if dk.get("yard") is not None:
                rec["truck_yard"] = U.coords(dk["yard"])        # a shared court is written once, with one of its sheds
        new.append(rec)
    idm = norms.v("validator.identical_models")
    M.assign_models(new, idm["radius_m"], idm["max_same_model"])
    for r in new:
        for k in ("_family", "_typical", "_c", "_lotid"):
            r.pop(k, None)
    allb = out + new
    allb.sort(key=lambda r: (r["lot"] or "", r["footprint"][0][0], r["footprint"][0][1]))
    for i, r in enumerate(allb):
        r["id"] = f"b{i:05d}"

    # built-in kindergartens where the houses stand (rule 14 as the validator measures it): a multi-storey house that no
    # kindergarten plot or built-in group reaches on foot within the radius puts a one-group built-in kindergarten on its lot
    # (kindergartens.placement) — the lot with most such homes first. gen_blocks_lots placed them for its provisional lots;
    # the houses of the final lots can stand farther out
    n_kg = builtin_kindergartens(lots, allb, net, norms)
    if n_kg:
        log("встроенные детсады на одну группу в многоэтажных домах, до которых не дотягивается ни один сад (kindergartens.placement)",
            [L for L, _ in n_kg], n=len(n_kg), group=norms.v("kindergartens.group_size_max", "3-7_years"))

    for L in lots:
        L.pop("_p", None)
    T = spec.get("targets") or {}

    def write_out():
        """lots.json capacity from the buildings (one number in both files, rule 24), buildings.json with its totals."""
        # a service plot made by rule opens with its building (tester items 73, 78: plots open years before their buildings,
        # empty grounds on the frames): its years are the earliest of its buildings', scenario by scenario
        by_lot_y = defaultdict(list)
        for r in allb:
            if r["lot"]:
                by_lot_y[r["lot"]].append(r["years"])
        n_sy = 0
        for L in lots:
            if L["use"] in U.SOCIAL_USES and L["source"] == "rule" and by_lot_y.get(L["id"]):
                ys_ = [min(y[k] for y in by_lot_y[L["id"]]) for k in range(len(L["years"]))]
                if ys_ != list(L["years"]):
                    L["years"] = ys_
                    n_sy += 1
        if n_sy:
            log.rows[:] = [r_ for r_ in log.rows if not r_.get("what", "").startswith("участки соцобъектов по правилу открываются")]
            log("участки соцобъектов по правилу открываются с первым зданием на них (годы участка = годы здания)", [], lots=n_sy)
        agg = defaultdict(lambda: [0, 0])
        for r in allb:
            if r["lot"]:
                agg[r["lot"]][0] += r["homes"]
                agg[r["lot"]][1] += r["jobs"]
        for L in lots:
            if L in landmark_cap:
                continue
            hj = agg.get(L["id"], [0, 0])
            if hj[0] or hj[1] or "homes" in L["capacity"] or "jobs" in L["capacity"]:
                L["capacity"]["homes"], L["capacity"]["jobs"] = hj        # also back to 0 where no building stands any more
        U.write_json(os.path.join(od, "lots.json"), lots_doc)
        homes = sum(r["homes"] for r in allb) + sum(L["capacity"].get("homes", 0) for L in landmark_cap)
        jobs = sum(r["jobs"] for r in allb) + sum(L["capacity"].get("jobs", 0) for L in landmark_cap)
        # residents: new housing and every building with homes (existing houses up to U.EXISTING_HOME_M2), as the validator's
        # has_homes selects them
        res_gfa = sum(r["gfa_m2"] for r in allb if r["use"] == "housing" or r["homes"] > 0) + \
            sum(L["capacity"].get("homes", 0) for L in landmark_cap) * home_m2
        ex = [r for r in allb if r["source"] == "existing_osm"]
        ex_h, ex_j = sum(r["homes"] for r in ex), sum(r["jobs"] for r in ex)
        totals = {"buildings": len(allb), "by_source": dict(Counter(r["source"] for r in allb)), "homes": homes, "jobs": jobs,
                  "residents": int(round(res_gfa / m2_res)), "targets": {k: T.get(k) for k in ("homes_2050", "population_2050", "jobs_2050")},
                  "zones": zone_report, "removed": len(set(removed)), "solar": len(solar),
                  "homes_existing": ex_h, "jobs_existing": ex_j, "residents_existing": int(round(sum(r["gfa_m2"] for r in ex if r["homes"] > 0) / m2_res)),
                  # comparable with the spec targets: the new city only, without keep quarters (their capacity is the zone
                  # density over the keep) and existing houses
                  "homes_new": homes - ex_h - sum(L["capacity"].get("homes", 0) for L in landmark_cap if L["source"] == "keep"),
                  "jobs_new": jobs - ex_j - sum(L["capacity"].get("jobs", 0) for L in landmark_cap if L["source"] == "keep")}
        doc_ = {"schema": "qtwin.buildings/1", "district": d, "buildings": allb, "removed": sorted(set(removed)), "solar": solar,
                "log": log.rows, "totals": totals, "made_by": "w44 gen_buildings.py"}
        U.write_json(os.path.join(od, "buildings.json"), doc_)
        return doc_
    doc = write_out()
    import land_driveways
    dv = land_driveways.run(d, out_root, spec_path, og=memo["offgrade"])        # driveways and fire lanes to the buildings just placed
    # a building over 28 m the drives leave without carriageway in its fire band (no free land for a lane there, a pad or a
    # drive at the wall) keeps to 28 m where some carriageway lies within the building-line limit: rule 12 asks no band of it
    # likewise a building the drives cannot ring where its height asks for the ring (fire_access.ring_required: residential
    # over 75 m, other over 50 m) keeps to that height
    lim = norms.v("setbacks.building_line_max_m", "max_from_carriageway")
    # rule 12 asks a building of 10–28 m with no street within the limit for a drive edge 5–8 m from its wall: where the drives
    # give none (a nearer one only), the building keeps under 10 m, where the limit is all it asks
    mid_h0 = land_driveways.fire_params(norms)["mid_h"][0]

    def under_mid(use):
        """Most floors a building of this use has below the 5–8 m band's height range (10 m)."""
        f = 1
        while (f + 1) * fh.get(kind_for(use, f + 1), 3.6) < mid_h0 - 1e-9:
            f += 1
        return f
    ok28 = (dv or {}).get("_ok28", set())
    mid_miss = (dv or {}).get("_mid_miss", {})
    lowered, ringed, under = [], [], []
    for r in allb:
        if r["source"] == "existing_osm" or r["kind"] != kind_for(r["use"], r["floors"]):
            continue
        dn = (dv or {}).get("_band_miss", {}).get(r["id"])
        f = r["floors"]
        if dn is not None and dn <= lim:
            f = min(f, low_floors(r["use"]) if r["id"] in ok28 else under_mid(r["use"]))
            if r["id"] not in ok28 and f < r["floors"]:
                under.append(r["id"])
        elif mid_miss.get(r["id"]) is not None:
            f = min(f, under_mid(r["use"]))
            if f < r["floors"]:
                under.append(r["id"])
        elif r["id"] in (dv or {}).get("_ring_miss", {}):
            rh = ring_res if r["use"] == "housing" else ring_other
            while f > 1 and f * fh.get(kind_for(r["use"], f), 3.6) > rh:
                f -= 1
        if f >= r["floors"]:
            continue
        if r["id"] not in under:
            (lowered if dn is not None else ringed).append(r["id"])
        a_ = U.from_coords(r["footprint"]).area
        r["floors"], r["kind"] = f, kind_for(r["use"], f)
        r["height_m"] = round(f * fh.get(r["kind"], 3.6), 1)
        r["gfa_m2"] = round(a_ * f, 1)
        r["homes"] = int(round(r["gfa_m2"] / home_m2)) if r["use"] == "housing" else 0
        r["jobs"] = int(round(r["gfa_m2"] / m2_job[r["use"]])) if r["use"] in m2_job else 0
        if r["height_m"] < norms.num("heights.airfield_height_threshold_m"):
            r.pop("aviation", None)
    if lowered:
        log(f"здания без проезжей части в полосе {wall_hi}–{wall_hi_max} м от стены (места под пожарный проезд нет) не выше "
            f"{tall_h:.0f} м: улица или проезд ближе {lim} м (правило 12)", lowered)
    if under:
        log(f"здания без улицы в {lim} м и без проезда в {wall_lo}–{wall_lo_max} м от стены (места под пожарный проезд нет) ниже "
            f"{mid_h0:.0f} м (правило 12, fire_access.distance_to_wall_m building_10_28m)", under)
    if ringed:
        log(f"здания, к которым кольцевой пожарный проезд не помещается, не выше высоты кольца (fire_access.ring_required: жильё "
            f"{ring_res} м, прочие {ring_other} м; правило 12)", ringed)
    # a building no drive reaches (no free land to it) and no street within the building-line limit is not built: rule 12
    # has no fire access to it (school, kindergarten, polyclinic and other typical buildings stay: their service counts)
    gone = {i for i, dn in ((dv or {}).get("_unserved") or {}).items() if dn > lim}
    gone = {r["id"] for r in allb if r["id"] in gone and r["source"] != "existing_osm" and r["kind"] == kind_for(r["use"], r["floors"])}
    if gone:
        allb[:] = [r for r in allb if r["id"] not in gone]
        log(f"здания без проезда и без улицы ближе {lim} м не строятся (места под проезд нет; правило 12)", sorted(gone))
    late = (dv or {}).get("_acc_late") or {}
    shifted, late_reg = [], []
    for r in allb:
        a = (late.get(r["id"]) or {}).get("tall" if r["height_m"] > tall_h else "low")
        if a is None or r["source"] == "existing_osm":
            continue
        if r["source"] == "registry" or r.get("registry_id"):
            late_reg.append((r["id"], r.get("registry_id"), r["years"][0], a["by"], a["years"][0]))
            continue
        Y0 = r["build_years"][-1]
        Y = max(Y0, a["years"][0])
        e = U.effective_years(Y, r["use"])
        while not all(x >= y for x, y in zip(e, a["years"])) and Y < 2050:
            Y += 1
            e = U.effective_years(Y, r["use"])
        if Y > Y0:
            r["years"], r["build_years"] = e, [y + Y - Y0 for y in r["build_years"]]
            shifted.append(r["id"])
    if shifted:
        log("здания открываются не раньше первой улицы или проезда в зоне досягаемости (правило 12: 25 м, выше 28 м — 10 м)",
            shifted)
    if late_reg:
        log("объекты реестра открываются раньше улицы или проезда в зоне досягаемости: год объекта по спецификации (w47)",
            [x[0] for x in late_reg], objects=[{"building": i, "registry_id": rid, "opens": y, "access": by, "access_opens": ay}
                                                for i, rid, y, by, ay in late_reg], warn=True)
    if lowered or ringed or gone or under or shifted:
        doc = write_out()
        # driveways.json keeps in its log only the buildings still without fire access: a building kept low is served by the
        # street within the limit, a building left out is not built (tester item 72: the log named a building rule 12 passed)
        if dv:
            fixed = set(lowered) | set(ringed) | gone | set(under)
            rows = []
            for row in dv["log"]:
                if row.get("what", "").startswith(("здания без проезда", f"здания выше {tall_h:.0f} м без проезжей части",
                                                   f"здания {mid_h0:.0f}–{tall_h:.0f} м без улицы")):
                    row = {**row, "ids": [i for i in row["ids"] if str(i).split(" ")[0] not in fixed]}
                    if not row["ids"]:
                        continue
                rows.append(row)
            if fixed:
                rows.append({"what": "после проезда: здания без пожарной полосы или кольца понижены, здания без проезда и без улицы "
                                     "не строятся (buildings.json)", "ids": sorted(fixed)})
            dv["log"] = rows
            U.write_json(os.path.join(od, "driveways.json"), {k: v for k, v in dv.items() if not k.startswith("_")})
    # built-in kindergartens sized to the houses the providers within their radius cannot seat (rule 14's capacity flow, read
    # with the validator's own measure on the files just written: tester items 30, 48, 49)
    n_kgf = kg_builtin_fill(spec_path or d, out_root, od, lots_doc, allb, norms, log, m2_kg)
    if n_kgf:
        doc = write_out()
    T_ = doc["totals"]
    print(f"{d}: {len(allb)} buildings {T_['by_source']}, homes {T_['homes']} (new {T_['homes_new']}, existing {T_['homes_existing']}, "
          f"target {T.get('homes_2050')}), jobs {T_['jobs']} (new {T_['jobs_new']}, target {T.get('jobs_2050')}), "
          f"removed {len(set(removed))}, solar {len(solar)}, kept to {tall_h:.0f} m without a fire band {len(lowered)}, to the ring height {len(ringed)}, "
          f"left out without a drive {len(gone)}, under 10 m without the 5–8 m band {len(under)}, opening moved to the access {len(shifted)}; "
          f"{time.time() - t0:.1f} s")
    return doc


KG_FILL_ROUNDS = 3      # rounds of the built-in kindergarten fill (each re-reads the capacity flow; model qTwin)
BUILTIN_FLOORS = 2      # floors of a house that may hold a built-in kindergarten (kindergartens.placement: «1–2 этажей»)


def kg_builtin_fill(district, out_root, od, lots_doc, allb, norms, log, m2_kg):
    """Raise the built-in kindergarten places of house lots (kindergartens.placement: in the 1st–2nd floors of a house) where
    rule 14's capacity flow leaves a house's demand unmet: the validator's capacity_gaps (walking radius, providers' places,
    maximum flow) on the lots.json / buildings.json just written, whole groups (kindergartens.group_size_max) on the house's
    own lot, up to the floor area of its houses' two lower floors / kindergartens.building_m2_per_place. Returns the lots raised
    (lots.json rewritten by the caller)."""
    try:
        vdir = os.path.join(U.MAP, "validate")
        for p_ in (U.MAP, vdir, os.path.join(vdir, "rules")):
            if p_ not in sys.path:
                sys.path.insert(0, p_)
        import context as VC
        import buildings as VB
        import land_rulekit as K
    except Exception as e:          # the validator's modules missing: nothing to measure against
        log("встроенные детсады по потоку мест правила 14 не досчитаны: модули валидатора не загрузились", [], error=str(e), warn=True)
        return 0
    g = norms.v("kindergartens.group_size_max", "3-7_years")
    lot = {L["id"]: L for L in lots_doc["lots"]}
    room = defaultdict(float)
    for r in allb:
        if r["use"] == "housing" and r["lot"]:
            room[r["lot"]] += U.from_coords(r["footprint"]).area * min(BUILTIN_FLOORS, r["floors"]) / m2_kg
    raised = {}
    for _ in range(KG_FILL_ROUNDS):
        U.write_json(os.path.join(od, "lots.json"), lots_doc)
        ctx = VC.build(district, out_root)
        gaps = VB.capacity_gaps(ctx, max(K.stage_years(ctx)))
        add = defaultdict(float)
        for (blk_, s_), ws in gaps.items():
            if s_ != "kindergarten":
                continue
            for b, unmet, *_ in ws:
                if b.get("lot") in lot and b["use"] == "housing":
                    add[b["lot"]] += unmet
        more = 0
        for lid, u in add.items():
            L = lot[lid]
            have = L["capacity"].get("kindergarten_builtin_places", 0)
            want = int(math.ceil((have + u) / g) * g)
            cap_ = int(math.floor(room.get(lid, 0.0) / g) * g)
            new = min(want, max(cap_, have))
            if new > have:
                L["capacity"]["kindergarten_builtin_places"] = new
                raised[lid] = new
                more += 1
        if not more:
            break
    if raised:
        log("встроенные детсады досчитаны по потоку мест правила 14: дома, которых сады в радиусе не вмещают, получают группы на "
            "своём участке (kindergartens.placement, 1–2 этажи; kindergartens.group_size_max)", sorted(raised), places=raised)
    return len(raised)


def landmark_heights():
    """Unity landmark model id → its height (m), read from Assets/Scripts/DigitalTwin/Landmarks/LandmarkData.cs (`Id = "…"` …
    `Height = …f`); {} when the file is not there (every landmark lot then counts as tall)."""
    path = os.path.join(U.REPO, "UnityProject", "Assets", "Scripts", "DigitalTwin", "Landmarks", "LandmarkData.cs")
    try:
        t = open(path, encoding="utf-8").read()
    except OSError:
        return {}
    out = {}
    for ch in t.split('Id = "')[1:]:
        own = ch.split('Id = "')[0]
        m = re.search(r"\bHeight\s*=\s*([0-9.]+)f", own)
        if m:
            out[ch.split('"')[0]] = float(m.group(1))
    return out


PLINTH_STEP_M = 4.0     # the terrain under a footprint: its outline every this many metres and a grid inside (as merge samples it)
PLINTH_PTS_MAX = 2500   # … the grid widened for a large footprint to keep the samples under this (model qTwin)


def footprint_relief(fp):
    """(lowest, highest) terrain under a footprint: its vertices, its outline every PLINTH_STEP_M m and a grid inside
    (export/merge_districts.footprint_relief measures the same way); (None, None) for an empty one."""
    if fp is None or fp.is_empty:
        return None, None
    pts = []
    for ring in [fp.exterior] + list(fp.interiors):
        ln = shapely.geometry.LineString(ring.coords)
        pts += [ln.interpolate(t).coords[0] for t in np.arange(0.0, ln.length, PLINTH_STEP_M)]
    x0, z0, x1, z1 = fp.bounds
    step = max(PLINTH_STEP_M, math.sqrt(fp.area / PLINTH_PTS_MAX))
    gx, gz = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(z0 + step / 2, z1, step))
    gx, gz = gx.ravel(), gz.ravel()
    if len(gx):
        m = shapely.contains_xy(fp, gx, gz)
        pts += list(zip(gx[m], gz[m]))
    if not pts:
        return None, None
    a = np.asarray(pts, float)
    h = np.asarray(U.terrain().height(a[:, 0], a[:, 1]), float)
    return float(h.min()), float(h.max())


def builtin_kindergartens(lots, allb, net, norms, Y=2050):
    """One-group built-in kindergartens on the lots of the multi-storey houses no kindergarten reaches within the radius
    (validator rule 14: kindergarten plots and lots with a built-in group of at least one group, both with a building, on foot
    through the walk network, a provider on the house's own lot across the yard). Returns [(lot id, group)]."""
    g = norms.v("kindergartens.group_size_max", "3-7_years")
    R = norms.v("kindergartens.radius_m", "multi_storey")
    lowmax = U.low_rise_max(norms)
    lot = {L["id"]: L for L in lots}
    built = {r["lot"] for r in allb if r["lot"] and r["years"][0] <= Y}

    def group(L):
        return (L.get("capacity") or {}).get("kindergarten_builtin_places", 0) >= g
    houses = []
    for r in allb:
        L = lot.get(r["lot"])
        if r["use"] != "housing" or L is None or r["floors"] <= lowmax or L["use"] == "village_existing" or r["years"][0] > Y \
                or L["years"][0] > Y:
            continue
        c = U.from_coords(r["footprint"]).centroid
        houses.append([r, L, c.x, c.y, float("inf")])
    if not houses:
        return []
    walk = U.WalkNet(net)
    prov = [(L["_p"].centroid.x, L["_p"].centroid.y) for L in lots if L["id"] in built and L["years"][0] <= Y
            and (L["use"] == "kindergarten" or group(L))]
    if prov:
        D = walk.dist_from(prov)
        for h in houses:
            h[4] = 0.0 if group(h[1]) else walk.dist_to(h[2], h[3], D)
    out = []
    while True:
        far = defaultdict(int)
        for h in houses:
            if h[4] > R and not group(h[1]):
                far[h[1]["id"]] += h[0]["homes"]
        if not far:
            return out
        L = lot[max(far, key=lambda k: (far[k], k))]
        L["capacity"]["kindergarten_builtin_places"] = max(g, L["capacity"].get("kindergarten_builtin_places", 0))
        out.append((L["id"], g))
        c = L["_p"].centroid
        D1 = walk.dist_from([(c.x, c.y)])
        for h in houses:
            if h[4] > R:
                h[4] = 0.0 if h[1] is L else min(h[4], walk.dist_to(h[2], h[3], D1))


if __name__ == "__main__":
    a = U.cli(__doc__).parse_args()
    run(a.district, a.out, a.spec)
