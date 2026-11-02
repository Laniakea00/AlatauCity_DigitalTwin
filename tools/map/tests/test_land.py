"""Unit checks of the land helpers (w44) on hand-made data. Only the norms are read; nothing is written.

    python3 tools/map/tests/test_land.py [--out OUT --districts a,b]

With --out, the written lots of each district are checked too: every lot inside its block (within 0.1 m²), no two lots of a
block overlapping by more than 0.1 m² (written_tiling).

Cable strip: see cable_case.

Divided street (the Gate cartographer's case, s_east_s / s_ave): network.json draws each carriageway of a divided road as a
oneway segment on its own line, cw_offset off the road axis, with a '/cw' profile that carries the road's whole median and red
line. Its red-line band must reach red/2 from the ROAD axis, not red/2 from the carriageway line (that ate a 7.8 m strip of land
along every divided street, the TPU bus station lot among them); its carriageway is its own lanes only. Exit code 0 when every
check passes.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
from shapely.geometry import LineString, Point, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import land_models as M  # noqa: E402
import land_util as U  # noqa: E402

# the profile of s_east_s as network.json has it (district_transport, 2 + 2 lanes, median 8 m, red line 40 m)
CW = {"class": "district_transport", "lanes": [2, 0], "lane_w": 3.75, "median_w": 8.0, "sidewalk_w": [0.0, 3.0],
      "verge_w": [0.0, 2.7], "bike_w": [0.0, 1.5], "parking_w": [0.0, 0.0], "red_line_w": 40.0}
TWO = {"class": "local", "lanes": [1, 1], "lane_w": 3.0, "median_w": 0.0, "sidewalk_w": [1.5, 1.5], "verge_w": [1.0, 1.0],
       "bike_w": [0.0, 0.0], "parking_w": [0.0, 0.0], "red_line_w": 15.0}

# a lot of green (w51: zone terr, residential_low rows, w 25) whose mitre dilation GEOS returns self-intersecting
OPENING_LOT_WKT = (
    "POLYGON ((-1934.2798097937093 20053.04168455636, -1919.2275498832398 20052.901245552675, "
    "-1914.2179177753274 20052.854505212934, -1883.3052052857256 20052.56608669179, "
    "-1883.3096235238368 20052.125146528295, -1883.3097600115193 20052.10999808009, "
    "-1883.3496975992623 20047.117799612206, -1883.3996189562652 20042.165600997545, "
    "-1883.3999991903152 20042.090160645574, -1883.4396976029093 20037.13778367446, "
    "-1883.4896204879815 20032.17544889827, -1883.4899234967436 20032.115209232205, "
    "-1883.5149899442729 20029.613577768778, -1883.515250638294 20029.587560505468, "
    "-1883.5396233280126 20027.155166071567, -1883.5397559484193 20027.140501466827, "
    "-1883.579756125319 20022.180481904234, -1883.5799493320387 20022.132565858657, "
    "-1883.629621988274 20017.165300235152, -1883.6714176526127 20013.01917031987, "
    "-1883.6796189562651 20012.205600997542, -1883.68 20012.12999952001, -1883.7196969883953 20007.16787597061, "
    "-1883.7696174152572 20002.225753711267, -1883.77 20002.15, -1883.77 20002.14757420721, "
    "-1883.7824812887893 20000.901941586028, -1886.8608673224423 20000.92959175998, "
    "-1887.820118291261 20000.941219044453, -1888.4990975867063 20000.94944909652, "
    "-1888.5147025902572 20000.94962201048, -1893.4946975728471 20000.999621960105, "
    "-1893.5022266604099 20000.99969377619, -1893.9985823458544 20001.004178919375, "
    "-1896.8222316823123 20001.02969382409, -1896.8450906254916 20001.029865541997, "
    "-1897.9750243220258 20001.036631612038, -1897.9771370609305 20001.085643668983, "
    "-1897.9840449291687 20001.13422205756, -1897.9956809922717 20001.18188945224, "
    "-1898.0119331913033 20001.22818680107, -1898.0326450124649 20001.27266824598, "
    "-1898.0576169944507 20001.314905416784, -1898.08660864921 20001.354491556212, "
    "-1898.1193407780127 20001.39104543732, -1898.1554981601853 20001.42421503477, "
    "-1898.194732588781 20001.453680914918, -1898.2366662239435 20001.47915931209, "
    "-1898.2808952316016 20001.500404861323, -1898.3269936725146 20001.517212961306, "
    "-1898.3745176042114 20001.529421744755, -1898.4230093564338 20001.536913637283, "
    "-1898.4720019381816 20001.539616489572, -1898.4971962832062 20001.53976831111, "
    "-1898.546156342607 20001.53766177672, -1898.5946750295382 20001.53077251531, "
    "-1898.6422862686438 20001.519166705806, -1898.6885327016369 20001.50295583477, "
    "-1898.7329700806583 20001.482295625447, -1898.7751715358286 20001.45738454186, "
    "-1898.8147316757622 20001.428461882366, -1898.851270481818 20001.395805480908, "
    "-1898.8844369585786 20001.359729038137, -1898.9139125055688 20001.32057910795, "
    "-1898.9394139777467 20001.27873176848, -1898.9606964054306 20001.23458900944, "
    "-1898.9775553474997 20001.188574870568, -1898.9898288552772 20001.141131368266, "
    "-1898.997399028225 20001.092714249542, -1899.0001361640466 20001.044786389688, "
    "-1902.8641077411007 20001.08350131964, -1903.4813922131927 20001.08968618012, "
    "-1906.2359418238218 20001.11488024227, -1906.2379010770778 20001.163908397302, "
    "-1906.2446565435137 20001.212508789307, -1906.2561431498007 20001.260213006164, "
    "-1906.2722502737488 20001.306561630623, -1906.2928227950702 20001.351108300456, "
    "-1906.3176625893607 20001.39342400736, -1906.346530436017 20001.43310122827, "
    "-1906.3791483221592 20001.469757850227, -1906.4152021200057 20001.503040850253, "
    "-1906.454344612097 20001.532629695153, -1906.4961988351818 20001.55823942845, "
    "-1906.5403617105953 20001.579623414633, -1906.5864079260928 20001.596575714422, "
    "-1906.6338940318603 20001.608933068055, -1906.6823627111628 20001.616576467568, "
    "-1906.731347184564 20001.619432302912, -1906.747281286224 20001.619578064892, "
    "-1906.7962701748577 20001.617622368936, -1906.8448320140292 20001.61087820611, "
    "-1906.8924998843872 20001.59941042116, -1906.9388154620374 20001.5833292762, "
    "-1906.9833334252946 20001.562789390533, -1907.025625736452 20001.537988254, "
    "-1907.065285757307 20001.509164328145, -1907.1019321589977 20001.47659475339, "
    "-1907.1352125884068 20001.440592684372, -1907.1648070561062 20001.40150427895, "
    "-1907.190431012927 20001.359705369963, -1907.2118380859765 20001.31559785156, "
    "-1907.2288224474455 20001.269605815058, -1907.2412207936538 20001.222171471305, "
    "-1907.2489139151971 20001.17375089885, -1907.2517899453142 20001.125446176542, "
    "-1908.4522867008907 20001.13948707427, -1908.4798816909833 20001.139759048725, "
    "-1912.9578676295973 20001.17565472759, -1912.9598816788302 20001.224676134978, "
    "-1912.9666915815294 20001.273268661207, -1912.978231565625 20001.320959720615, "
    "-1912.9943904960678 20001.367290027625, -1913.0150127553516 20001.411813401282, "
    "-1913.0398997421796 20001.454101062216, -1913.068811784079 20001.4937457619, "
    "-1913.1014704455592 20001.530365704715, -1913.1375612095326 20001.5636082247, "
    "-1913.1767365063208 20001.59315318201, -1913.2186190608186 20001.61871604588, "
    "-1913.2628055258667 20001.64005063485, -1913.3088703666576 20001.656951487585, "
    "-1913.3563699588085 20001.66925584154, -1913.4048468606422 20001.67684520046, "
    "-1913.453834218584 20001.67964647552, -1913.4614252076644 20001.67970746533, "
    "-1913.5104329255198 20001.67769533516, -1913.5590076889525 20001.6708911133, "
    "-1913.6066820523 20001.659360278278, -1913.652997234673 20001.64321379386, "
    "-1913.6975075348623 20001.622607041223, -1913.7397846204456 20001.59773832369, "
    "-1913.7794216497111 20001.568846958402, -1913.8160371867984 20001.53621097334, "
    "-1913.8492788723281 20001.50014443177, -1913.8788268142243 20001.46099440998, "
    "-1913.9043966661493 20001.419137657238, -1913.9257423637755 20001.374976970306, "
    "-1913.9426584927535 20001.32893731721, -1913.9549822654476 20001.28146174766, "
    "-1913.9625950874788 20001.233007129533, -1913.965406432736 20001.184338656123, "
    "-1916.7022853895048 20001.209602154184, -1918.4337877463488 20001.229504480125, "
    "-1918.4448424026068 20001.22962340476, -1921.5357366442267 20001.260593149644, "
    "-1937.0772075999187 20039.4591439139, -1938.423290961368 20040.968998741268, "
    "-1938.3103008079274 20053.07928941741, -1934.2798097937086 20053.041684556356, "
    "-1934.2798097937093 20053.04168455636))"
)
OPENING_W = 25.0


def seg(sid, pts, pid, oneway):
    return {"id": sid, "a": sid + "a", "b": sid + "b", "class": "district_transport" if "cw" in pid else "local", "pid": pid,
            "oneway": oneway, "pts": [[x, z, 600.0] for x, z in pts], "years": [2030] * 4}


def cable_case(norms, check):
    """Cable strip (the Gate case: b00412 on hv220_cable_n, 0.9 m² into the 0.6 m strip, kept by a 1 m² tolerance): a footprint
    cut off the strip keeps clear of it as the validator measures it (plain intersection with line.buffer(w)), even after the
    0.01 m rounding of buildings.json; one mostly in a strip drops out."""
    w = norms.v("utilities.to_foundations_m", "cables")
    cable = LineString([(0.0, 0.0), (0.0, 200.0)])
    strip = cable.buffer(w)
    nb = U.clean(strip.buffer(M.NOBUILD_CLEAR_M))
    sec = box(w - 0.015, 50.0, w - 0.015 + 18.0, 110.0)          # an 18 × 60 m section whose wall is 0.015 m into the strip
    check("the section starts inside the cable strip, under the old 1 m² tolerance", sec.intersects(strip) and sec.intersection(strip).area < 1.0,
          f"{sec.intersection(strip).area:.2f} m²")
    q = M.clear_of(sec, nb)
    qr = U.from_coords(U.coords(q)) if q is not None else None
    check("cut off the strip: clear of it after rounding", qr is not None and not qr.intersects(strip),
          f"{qr.distance(cable):.3f} m from the cable" if qr is not None else "dropped")
    check("the cut keeps the section", q is not None and q.area > 0.98 * sec.area)
    check("a footprint clear of the strip stays as it is", M.clear_of(box(5.0, 0.0, 20.0, 10.0), nb).equals(box(5.0, 0.0, 20.0, 10.0)))
    check("a footprint astride the strip keeps its larger side", (lambda r: r is not None and r.bounds[0] > w)(M.clear_of(box(-3.0, 0.0, 15.0, 10.0), nb)))
    check("a footprint mostly in a wide strip drops out", M.clear_of(box(-2.0, 0.0, 2.5, 10.0), U.clean(cable.buffer(2.0))) is None)


def existing_case(check):
    """Existing houses (tester item 75): homes up to U.EXISTING_HOME_M2, workplaces above, by the same constants as the traffic
    model (export/twin_rerun.py), so buildings.json, the validator and traffic give one number."""
    import re
    src = open(os.path.join(os.path.dirname(HERE), "export", "twin_rerun.py")).read()
    for k in ("EXISTING_HOME_M2", "EXISTING_M2_PER_JOB"):
        m = re.search(rf"^{k} = ([0-9.]+)", src, re.M)
        check(f"{k} as in export/twin_rerun.py", m is not None and float(m.group(1)) == getattr(U, k), m.group(1) if m else "not found")
    check("a 120 m² house is one home or more", U.existing_load(120.0, 75.0) == (2, 0))
    check("a 30 m² house is still a home", U.existing_load(30.0, 75.0) == (1, 0))
    check("a 2000 m² building holds workplaces", U.existing_load(2000.0, 75.0) == (0, 20))


def fire_band_case(norms, check):
    """Rule 12's bands as land_driveways takes them (validator round 4): up to 28 m a building's own drive and a school's or
    kindergarten's ring keep their edge 5–8 m from the wall, not anywhere within 25 m; a short dead-end branch looks for its
    turnaround back past its junction."""
    import networkx as nx
    from shapely.geometry import LineString
    import land_driveways as LD
    F = LD.fire_params(norms)
    check("the 5–8 m band holds for 10–28 m (fire_access.distance_to_wall_m building_10_28m)",
          F["mid_h"] == (10.0, 28.0) and tuple(F["mid"]) == (5, 8), f"{F['mid_h']} {F['mid']}")
    (lo, hi), ring = LD.needs({"height_m": 13.0, "use": "social"}, "kindergarten", F, norms)
    check("a 13 m kindergarten: drive and ring in 5–8 m, the ring required", (lo, hi) == (5, 8) and ring, f"{(lo, hi)} {ring}")
    (lo, hi), _ = LD.needs({"height_m": 40.0, "use": "business"}, "business", F, norms)
    check("over 28 m: 8–10 m", (lo, hi) == (8, 10))
    G = nx.MultiGraph()
    ch = LineString([(0.0, 0.0), (0.0, 5.0)])
    G.add_edge(LD.key((0.0, 0.0)), LD.key((0.0, 5.0)), ls=ch)
    G.add_edge(LD.key((0.0, 5.0)), LD.key((30.0, 5.0)), ls=LineString([(0.0, 5.0), (30.0, 5.0)]))
    G.add_edge(LD.key((0.0, 5.0)), LD.key((-8.0, 5.0)), ls=LineString([(0.0, 5.0), (-8.0, 5.0)]))
    bl = LD.back_line(G, LD.key((0.0, 0.0)), ch)
    check("a 5 m dead-end branch is carried on past its junction along the longest drive there",
          abs(bl.length - 35.0) < 1e-6 and bl.coords[-1] == (30.0, 5.0), f"{bl.length}")


def opening_case(check):
    """gen_blocks_lots.opening on a lot whose mitre dilation GEOS returns self-intersecting (w51, green: «TopologyException:
    side location conflict» in the intersection): no exception, a valid part of the lot."""
    import shapely.wkt
    import gen_blocks_lots as G
    p = shapely.wkt.loads("".join(OPENING_LOT_WKT))
    try:
        q = G.opening(p, OPENING_W)
        err = ""
    except Exception as e:      # noqa: BLE001
        q, err = None, str(e)[:80]
    check("opening of a lot with a self-intersecting mitre dilation: valid, inside the lot", q is not None and q.is_valid
          and q.difference(p).area < 0.01 and q.area > 0.9 * p.area, err or f"{q.area:.0f} of {p.area:.0f} m²")


def ring_case(check):
    """Ring sections of a tall zone (tester items 118–119): with join_below the sections of one ring stand a fire gap apart
    or are one building (no two 4 m apart across a corner), each one polygon without a court, and no land is lost to it."""
    import itertools
    lot = box(0.0, 0.0, 130.0, 110.0)
    gap = 22.02
    plain = M.ring_sections(lot, 6.0, M.SECTION_DEPTH["business"], M.SECTION_LEN, gap)
    joined = M.ring_sections(lot, 6.0, M.SECTION_DEPTH["business"], M.SECTION_LEN, gap, join_below=gap)
    dmin = min((a.distance(b) for a, b in itertools.combinations(joined, 2)), default=gap)
    check("ring sections of a tall zone: a fire gap apart or one building", dmin >= gap - 1e-6 and len(joined) < len(plain),
          f"{len(plain)} → {len(joined)} sections, nearest {dmin:.2f} m")
    check("joined sections: one polygon each, no court inside, more footprint than the cut ones",
          all(q.geom_type == "Polygon" and not q.interiors for q in joined) and sum(q.area for q in joined) > sum(q.area for q in plain))


def disjoint_case(check):
    """gen_blocks_lots.make_disjoint (Gate G1, rule 1: 22 lots over a neighbour by 1–5 m²): a rule lot that filled a notch of an
    existing plot gives the land back; two rule lots of different blocks split their overlap by block."""
    from shapely.geometry import Polygon
    import gen_blocks_lots as G
    blk = {"B1": {"poly": box(0.0, 0.0, 100.0, 50.0)}, "B2": {"poly": box(100.0, 0.0, 200.0, 50.0)}}
    ex = {"block": "B1", "use": "village_existing", "source": "existing", "poly": Polygon([(0, 0), (40, 0), (40, 30), (70, 30.1), (40, 30.2), (40, 50), (0, 50)])}
    ru = {"block": "B1", "use": "village_existing", "source": "rule", "poly": box(40.0, 0.0, 100.3, 50.0)}
    nb = {"block": "B2", "use": "park", "source": "rule", "poly": box(100.0, 0.0, 200.0, 50.0)}
    lots = [ex, ru, nb]
    for L in lots:
        L["grade_y"], L["_dev"] = 0.0, 0.0
    n, m2, both = G.make_disjoint(lots, blk)
    worst = max(a["poly"].intersection(b["poly"]).area for i, a in enumerate(lots) for b in lots[i + 1:])
    check("overlapping lots made disjoint: the existing plot keeps its needle, the block keeps its land",
          n == 2 and worst < 1e-6 and ex["poly"].area == Polygon(ex["poly"]).area and nb["poly"].area == 5000.0,
          f"{n} pairs, {m2:.1f} m², worst left {worst:.2g} m²")


def gap_case(check):
    """gen_blocks_lots.fill_gaps (Gate, rule 2: cracks of 1–2 m² between existing plots): block land in no lot joins the lot
    made here next to it, the existing plot keeps its outline."""
    import gen_blocks_lots as G
    blk = {"B1": {"poly": box(0.0, 0.0, 100.0, 50.0)}}
    ex = {"block": "B1", "use": "village_existing", "source": "existing", "poly": box(0.0, 0.0, 40.0, 50.0)}
    ru = {"block": "B1", "use": "village_existing", "source": "rule", "poly": box(41.0, 0.0, 100.0, 50.0)}
    n, m2 = G.fill_gaps([ex, ru], blk)
    left = blk["B1"]["poly"].difference(unary_union([ex["poly"], ru["poly"]])).area
    check("a crack between plots joins the lot made here", n == 1 and left < 1e-6 and ex["poly"].area == 2000.0, f"{n} pieces, {m2:.1f} m², left {left:.2g} m²")


def written_tiling(lots_doc, blocks_doc, tol=0.1):
    """Lots as written: (lots more than tol m² outside their block, pairs of lots of one block overlapping by more than tol m²)."""
    import shapely
    from collections import defaultdict
    B = {b["id"]: U.geom(b) for b in blocks_doc["blocks"]}
    out, by = [], defaultdict(list)
    for L in lots_doc["lots"]:
        p = U.geom(L)
        a = p.difference(B[L["block"]]).area if L["block"] in B else p.area
        if a > tol:
            out.append((L["id"], round(a, 2)))
        by[L["block"]].append((L["id"], p))
    pairs = []
    for ls in by.values():
        if len(ls) < 2:
            continue
        t = shapely.STRtree([p for _, p in ls])
        for i, (a_, p) in enumerate(ls):
            for j in t.query(p, predicate="intersects"):
                if int(j) > i:
                    ov = p.intersection(ls[int(j)][1]).area
                    if ov > tol:
                        pairs.append((a_, ls[int(j)][0], round(ov, 2)))
    return out, pairs


def tiling_case(check):
    """gen_blocks_lots.to_grid (growing_w, w52: lots 1–6 m² into the next block, rule 1): on the written grid every lot is in
    its block (within 0.1 m²) and two lots of a block overlap by no more than 0.1 m², by written_tiling."""
    from shapely.geometry import Polygon
    import gen_blocks_lots as G
    b1 = {"id": "B1", "use": "park", "poly": Polygon([(0, 0), (100.0004, 0), (100.0137, 50), (0, 50)])}
    b2 = {"id": "B2", "use": "park", "poly": Polygon([(100.0001, 0), (200, 0), (200, 50), (100.0131, 50)])}
    blocks = [b1, b2]
    L1 = {"block": "B1", "use": "park", "source": "rule", "poly": Polygon([(0, 0), (100.12, 0), (100.12, 50), (0, 50)])}   # 6 m² over
    L2 = {"block": "B2", "use": "park", "source": "rule", "poly": Polygon([(100.0001, 0), (200, 0), (200, 50), (100.0131, 50)])}
    lots = [L1, L2]
    for L in lots:
        L["grade_y"], L["_dev"] = 0.0, 0.0
    G.to_grid(blocks, lots, {b["id"]: b for b in blocks})
    G.make_disjoint(lots, {b["id"]: b for b in blocks}, G.WRITE_GRID)
    doc_l = {"lots": [dict({"id": f"L{i}", "block": L["block"]}, **U.poly_fields(L["poly"], G.WRITE_ND)) for i, L in enumerate(lots)]}
    doc_b = {"blocks": [dict({"id": b["id"]}, **U.poly_fields(b["poly"], G.WRITE_ND)) for b in blocks]}
    out, pairs = written_tiling(doc_l, doc_b)
    check("written lots inside their blocks (≤ 0.1 m²), no two of a block over 0.1 m²", not out and not pairs, f"{out} {pairs}")


def slab_case(check):
    """land_models.slabs (Gate G1, rule 1: two-storey slabs 1–9 m² over local streets): on a plot cut by a slanted line no slab
    leaves the buildable part (its rotated rectangle only when that stays inside)."""
    from shapely.geometry import Polygon
    region = Polygon([(0, 0), (51, 0), (58.6, 33.7), (0, 38.9)])       # the old rectangles left it by 94 m²
    out = M.slabs(region, M.SLAB_DEPTH, 12.0, 0.05, M.SECTION_LEN)
    worst = max((q.difference(region).area for q in out), default=0.0)
    check("slabs of a slanted plot stay on its buildable part", out and worst <= M.SLAB_OUT_TOL_M2, f"{len(out)} slabs, worst out {worst:.3f} m²")


def site_case(check):
    """place_services carves a service plot only where it fronts an access street (street_front, growing_w w52: schools and
    kindergartens in farm gardens 88–397 m from any carriageway, rule 12): a garden 300 m from the only road takes no school,
    the same garden on the road does."""
    import gen_blocks_lots as G
    road = U.strtree([LineString([(0.0, 0.0), (400.0, 0.0)]).buffer(7.5, cap_style="flat")])
    far = box(0.0, 307.5, 200.0, 507.5)            # its near edge 300 m from the red line
    near = box(0.0, 7.5, 200.0, 207.5)
    need = 14400.0
    f = lambda q: G.street_front(road, q)            # noqa: E731
    check("a garden 300 m from any road takes no school plot; the same garden on the road does",
          G.carve(far, need, front=f) is None and G.carve(near, need, front=f) is not None)


def strip_case(norms, check):
    """gen_blocks_lots.join_strips (golden B2127, w50 / w52: u_lrt_viaduct_1, a 17 m utility strip under the LRT span, joined
    the business block behind it and took three offices, rule 25): a strip of a spec zone kept whole (lot_split none) or under
    an elevated span stays its own block; a plain strip on the street joins; gen_buildings keeps the span band free
    (U.span_bands)."""
    import gen_blocks_lots as G
    acc_red = box(0.0, -10.0, 300.0, 0.0)                         # the street's red line along z < 0
    lrt = {"lines": [{"pts": [[0.0, 8.5, 620.0], [300.0, 8.5, 620.0]],
                      "sections": [{"from_m": 0.0, "to_m": 300.0, "kind": "elevated"}]}]}
    spans = U.span_bands({"segments": []}, lrt, norms)

    def blocks(zone):
        return [{"zone": zone, "use": "utility", "poly": box(0.0, 0.0, 300.0, 17.0)},
                {"zone": "Z-B", "use": "business", "poly": box(0.0, 17.0, 300.0, 120.0)}]
    b1 = blocks("u_lrt_viaduct_1")
    n1, _, kept1 = G.join_strips(b1, {"u_lrt_viaduct_1": {"lot_split": "none"}, "Z-B": {}}, acc_red, [])
    b2 = blocks(None)
    n2, _, kept2 = G.join_strips(b2, {"Z-B": {}}, acc_red, spans)
    b3 = blocks(None)
    n3, _, _ = G.join_strips(b3, {"Z-B": {}}, acc_red, [])
    check("a 17 m utility strip of a zone kept whole beside a business block stays its own block", n1 == 0 and len(kept1) == 1
          and not b1[0].get("_gone") and abs(b1[1]["poly"].area - 300 * 103) < 1e-6)
    check("a strip under an elevated LRT span stays its own block", n2 == 0 and len(kept2) == 1 and not b2[0].get("_gone"))
    check("a plain strip on the street joins the block behind it", n3 == 1 and b3[0].get("_gone"))
    fp = box(100.0, 2.0, 130.0, 15.0)                             # an office in the strip
    gap = norms.v("building_gaps.fire_between_buildings_m", "I-II_to_I-II")
    nb = unary_union([q.buffer(gap, join_style="mitre") for q in spans])
    check("the span band with its fire gap covers the strip: no building under the deck", spans and nb.contains(fp)
          and nb.contains(box(0.0, 0.0, 300.0, 17.0)))


def pad_case(norms, check):
    """land_driveways.pad_ahead (T9 gate_trial dn99: a 31 m drive between walls 9 m apart, no turnaround pad, rule 12): the
    dead end is carried on to open ground where a 15 × 15 m pad fits, and not through a wall."""
    import land_driveways as D
    F = D.fire_params(norms)
    walls = [box(0.0, 4.3, 31.0, 20.0), box(0.0, -20.0, 31.0, -4.7)]
    ch = LineString([(31.0, 0.0), (0.0, 0.0)])                     # starts at the dead end
    area = box(-50.0, -60.0, 120.0, 60.0)
    back = D.find_pad(ch, F["turn"], 6.0, walls, area)
    ah = D.pad_ahead(ch, F["turn"], 6.0, walls, area, F["dead_end_max"] - ch.length)
    shut = D.pad_ahead(ch, F["turn"], 6.0, walls + [box(33.0, -30.0, 40.0, 30.0)], area, F["dead_end_max"] - ch.length)
    ok = back is None and ah is not None and not ah[1].intersects(unary_union(walls).buffer(D.PAD_CLEAR)) and ah[0][0] > 31.0 \
        and ah[0][0] - 31.0 <= D.PAD_AHEAD_MAX and shut is None
    check("a dead end with no room for its pad is carried on to open ground for it (not through a wall)", ok,
          f"ahead to x = {ah[0][0]:.0f}" if ah else "none")


def rail_deck_case(norms, check):
    """land_util.rail_low_decks (rule 25 since integ eaa6287: gate_trial drive ds329 and the pad of dn431 under the spec rail
    viaduct rail_agglo_1 at 3.7 m): a viaduct piece with less than fire_access.arches.height_min_m under its deck is a drive
    obstacle, a high one is not; both keep buildings off (span_bands)."""
    x0, z0 = -3000.0, -20000.0
    g = float(U.h(x0, z0))
    sys.path.insert(0, U.MAP)
    from lib import model
    below = float(model("rail_deck_below_m"))

    def spec(head):
        return {"rail": {"lines": [{"id": "r", "years": [2030, 2030, 2030, 2030], "tracks": [
            {"id": "t", "pts": [[x0, z0, g + head], [x0 + 100.0, z0, g + head]], "struct": [{"from_m": 0.0, "to_m": 100.0, "kind": "overpass"}]}]}]}}
    clear = norms.v("fire_access.arches", "height_min_m")
    low = U.rail_low_decks(spec(below + clear - 1.0), norms)
    high = U.rail_low_decks(spec(below + clear + 3.0), norms)
    bands = U.span_bands({"segments": []}, {}, norms, spec(below + clear + 3.0))
    check("a rail viaduct piece under the fire clearance is a drive obstacle, a high one is not; both keep buildings off",
          len(low) == 1 and low[0].area > 400 and not high and len(bands) == 1 and bands[0].area > 400,
          f"low {[round(q.area) for q in low]}, high {len(high)}, bands {len(bands)}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="land helper checks; with --out also the written lots of --districts")
    ap.add_argument("--out", help="output root holding <district>/lots.json and blocks.json")
    ap.add_argument("--districts", default="", help="comma-separated districts to check under --out")
    a = ap.parse_args()
    written = [(a.out, d) for d in a.districts.split(",") if d] if a.out else []
    norms = U.Norms()
    e = U.cw_offset(CW)
    # the road axis is z = 0 from x = 0 to 200; each carriageway on the right of its direction of travel
    net = {"profiles": {"district_transport/cw+t": CW, "local": TWO},
           "segments": [seg("s1", [(0.0, -e), (200.0, -e)], "district_transport/cw+t", True),       # eastbound, south side
                        seg("s2", [(200.0, e), (0.0, e)], "district_transport/cw+t", True),         # westbound, north side
                        seg("s3", [(100.0, -150.0), (100.0, -60.0)], "local", False)]}
    fails = []

    def check(name, ok, detail=""):
        print(f"{'ok ' if ok else 'ERR'} {name}{(': ' + detail) if detail else ''}")
        if not ok:
            fails.append(name)

    check("cw offset = median/2 + lanes·lane_w/2", abs(e - 7.75) < 1e-9, f"{e}")
    check("an undivided profile has no offset", U.cw_offset(TWO) == 0.0 and not U.is_cw(TWO))
    red = {s["id"]: p for s, p, lv in U.network_polys(net, norms, "red")}
    car = {s["id"]: p for s, p, lv in U.network_polys(net, norms, "carriage")}
    both = unary_union([red["s1"], red["s2"]])
    r = CW["red_line_w"] / 2.0
    for z in (-r + 0.1, r - 0.1, 0.0):
        check(f"red corridor holds z = {z:+.1f} at x = 100", both.contains(Point(100.0, z)))
    for z in (-r - 0.1, r + 0.1):
        check(f"red corridor ends at red/2 from the road axis: z = {z:+.1f} is outside", not both.contains(Point(100.0, z)))
    check("each carriageway's band covers the median axis", red["s1"].contains(Point(100.0, 0.0)) and red["s2"].contains(Point(100.0, 0.0)))
    check("each carriageway's band keeps to its side (not past the far carriageway)",
          not red["s1"].contains(Point(100.0, e)) and not red["s2"].contains(Point(100.0, -e)))
    half = CW["lanes"][0] * CW["lane_w"] / 2.0
    check("carriageway = its own lanes", car["s1"].contains(Point(100.0, -e + half - 0.05)) and car["s1"].contains(Point(100.0, -e - half + 0.05))
          and not car["s1"].contains(Point(100.0, -e - half - 0.05)) and not car["s1"].contains(Point(100.0, -e + half + 0.05)))
    check("an undivided street keeps red/2 round its line", abs(red["s3"].distance(Point(100.0 + TWO["red_line_w"] / 2.0 + 0.1, -100.0)) - 0.1) < 0.02)
    # walk band (rule 1's land of a street, w52): each side its own verge and sidewalk, none on a carriageway's median side,
    # so an LRT in the median (axis z = 0, corridor ±3.8 m) is on its own land
    walk = {s["id"]: p for s, p, lv in U.network_polys(net, norms, "walk")}
    out_w = half + CW["verge_w"][1] + CW["sidewalk_w"][1]
    check("walk band of a carriageway: its outer sidewalk is inside", walk["s1"].contains(Point(100.0, -e - out_w + 0.05))
          and walk["s2"].contains(Point(100.0, e + out_w - 0.05)) and not walk["s1"].contains(Point(100.0, -e - out_w - 0.05)))
    check("walk band of a carriageway ends at its lanes on the median side (LRT corridor ±3.8 m in the median is clear)",
          walk["s1"].contains(Point(100.0, -e + half - 0.05)) and not walk["s1"].contains(Point(100.0, -e + half + 0.05))
          and not walk["s2"].contains(Point(100.0, e - half - 0.05)) and not walk["s1"].intersects(LineString([(0.0, 0.0), (200.0, 0.0)]).buffer(3.8))
          and not walk["s2"].intersects(LineString([(0.0, 0.0), (200.0, 0.0)]).buffer(3.8)))
    check("walk band of an undivided street: both sidewalks", abs(walk["s3"].area - 90.0 * 2 * U.walk_half(TWO, 0)) < 0.5, f"{walk['s3'].area:.1f}")
    gap = U.red_half(CW) - U.carriage_half(CW)
    check("red line to the outer carriageway edge = red/2 − median/2 − lanes·lane_w", abs(gap - (r - CW["median_w"] / 2.0 - 2 * half)) < 1e-9, f"{gap}")
    cable_case(norms, check)
    existing_case(check)
    fire_band_case(norms, check)
    opening_case(check)
    ring_case(check)
    disjoint_case(check)
    gap_case(check)
    tiling_case(check)
    site_case(check)
    strip_case(norms, check)
    pad_case(norms, check)
    rail_deck_case(norms, check)
    for od, d in written:
        lots_doc, blocks_doc = (U.read_json(os.path.join(od, d, f)) for f in ("lots.json", "blocks.json"))
        if not lots_doc or not blocks_doc:
            check(f"{d}: lots.json and blocks.json in {od}", False)
            continue
        out, pairs = written_tiling(lots_doc, blocks_doc)
        check(f"{d}: every written lot inside its block (≤ 0.1 m²), no two lots of a block overlapping over 0.1 m²", not out and not pairs,
              f"{len(lots_doc['lots'])} lots; outside {out[:5]}{' …' if len(out) > 5 else ''}; overlaps {pairs[:5]}{' …' if len(pairs) > 5 else ''}")
    slab_case(check)
    print("all checks passed" if not fails else f"{len(fails)} check(s) failed: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
