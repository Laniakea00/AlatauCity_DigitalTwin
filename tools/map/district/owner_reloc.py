"""Industry moved to the edges of the city by the owner's own map (05.11.2026, second round): «в 4 фото я показал, где хочу видеть
эти заводы … вместо тех, которые стоят ближе к городу, ты их не убирал, а заменил на жилые дома (5 фото)».

The owner's circles, read off his screenshots by the landmarks on them (airport, Mars, TLC Zhetygen, GTES, PS Arna, KAIST, marina;
projective fit, ±0.5 km), in Unity metres:
  H — the industry and logistics between Golden and Growing (PS Arna, the Golden warehouses, the southern industry of Growing-West):
      becomes housing (residential_mid; the district builders give it streets, schools and parks by their rules and scale the
      densities to the district targets);
  A — the empty land north of the airport, between it and Green; B — west and south-west of the airport: new industrial parks
      on the reserve land there, never nearer than KEEP_M to housing (the builders then draw the SZZ green gaps as for every plant);
  C — the eastern belt round Mars Petcare and the GTES: stays industrial as it is.
Applied by golden_zones / growing_w_zones / growing_e_zones at the end of plan(): their zones are cut by these polygons.
"""
import json
import os

import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "..", "spec")
MODEL = "модель qTwin"
WHY = "решение владельца 05.11.2026 (его схема промзон)"
KEEP_M = 1000.0            # СЗЗ класса I (szz.class_width_m): a new plant stands at least this far from housing
MIN_PIECE_M2 = 20e4        # a new industrial park piece smaller than 20 ha is left as reserve
HOUSING = ("residential_low", "residential_mid", "residential_high", "mixed_centre", "campus", "medical", "resort")

H = Polygon([[2340, -3909], [1491, -6698], [-1495, -7693], [-4870, -6312], [-6656, -3363], [-5808, -574], [-2821, 421], [554, -960]])
A = Polygon([[3002, 7460], [2115, 4894], [127, 3186], [-2399, 2737], [-4815, 3613], [-6533, 5577], [-7127, 8156], [-6412, 10714],
             [-4518, 12572], [-1916, 13178], [672, 12311], [2485, 10196]])
B = Polygon([[-2658, -2856], [-3554, -5434], [-5696, -7068], [-8469, -7385], [-11161, -6359], [-13124, -4266], [-13875, -1607],
             [-13187, 966], [-11170, 2771], [-8316, 3263], [-5416, 2242], [-3327, -22]])
IND_AREAS = {"A": A, "B": B}
NAMES = {"A": "Северный промпарк (за аэропортом)", "B": "Западный промпарк (у аэропорта и БАКАД)"}

_HOUSING_CACHE = None


def _housing_elsewhere():
    """Housing of all districts as the specs have it now, plus the converted land of H (the zones of H that were industry or
    logistics): the new parks keep KEEP_M from all of it, across district borders."""
    global _HOUSING_CACHE
    if _HOUSING_CACHE is not None:
        return _HOUSING_CACHE
    homes, conv = [], []
    for d in ("gate", "golden", "green", "growing_w", "growing_e"):
        p = os.path.join(SPEC, d + ".json")
        if not os.path.exists(p):
            continue
        for z in json.load(open(p, encoding="utf-8"))["zones"]:
            g = shapely.make_valid(Polygon([q[:2] for q in z["polygon"]])).buffer(0)
            if z["use"] in HOUSING and not z["id"].endswith("_ind"):
                homes.append(g)
            elif z["use"] in ("industry", "logistics", "business") and g.intersects(H):
                conv.append(g.intersection(H))
    _HOUSING_CACHE = unary_union(homes + conv)
    return _HOUSING_CACHE


def _parts(g):
    out = []
    for q in getattr(g, "geoms", [g]):
        if q.geom_type == "Polygon" and not q.is_empty:
            out.append(q)
        elif q.geom_type == "MultiPolygon":
            out += list(q.geoms)
    return out


def apply(district, zones, rules_of, changes=None):
    """Cuts the zone list in place. rules_of(zone_id, use, density) gives a zone's rules in this district's builder.
    Industry / logistics inside H → residential_mid (the part outside H keeps its use and id); reserve inside A or B, KEEP_M
    from housing → industry. Returns the list of (id, why) changes for the scheme_changes / numbers report."""
    made = []
    out = []
    removed = 0.0
    cands = []                  # (area, zone index in out, key, piece) of the possible new parks
    home = None
    for z in zones:
        p = z["poly"]
        if z["use"] in ("industry", "logistics") and p.intersects(H):
            inside = p.intersection(H).buffer(0)
            rest = p.difference(H).buffer(0)
            big_in = inside.area >= rest.area
            pieces = [(q, "residential_mid", False) for q in _parts(inside)] + [(q, z["use"], False) for q in _parts(rest)]
            pieces = [pc for pc in pieces if pc[0].area >= 200.0]
            # the largest piece of the side that holds more land keeps the zone's id; every piece is its own zone (one polygon)
            side_use = "residential_mid" if big_in else z["use"]
            same = [i for i, pc in enumerate(pieces) if pc[1] == side_use]
            if same:
                k = max(same, key=lambda i: pieces[i][0].area); pieces[k] = (pieces[k][0], pieces[k][1], True)
            seen = {}
            for part, use, keep_id in pieces:
                zz = dict(z)
                zz["poly"] = part
                if use != z["use"]:
                    removed += part.area
                    zz["use"] = use
                    seen["h"] = seen.get("h", 0) + 1
                    zz["id"] = z["id"] if keep_id else z["id"] + "_h" + (str(seen["h"]) if seen["h"] > 1 else "")
                    zz["name_ru"] = "Жилой квартал на месте «" + z["name_ru"][:60] + "»"
                    zz["density"] = {}
                    zz["rules"] = rules_of(zz["id"], use, {})
                    zz["why"] = (f"{MODEL}, {WHY}: промзона у города заменена жильём (5 фото владельца); "
                                 f"заводы и склады — в новых промпарках A/B по краям")
                    made.append((zz["id"], f"{z['use']} → жильё ({part.area / 1e4:.0f} га) в зоне H схемы владельца"))
                else:
                    seen["k"] = seen.get("k", 0) + 1
                    zz["id"] = z["id"] if keep_id else z["id"] + "_k" + (str(seen["k"]) if seen["k"] > 1 else "")
                out.append(zz)
            continue
        if z["use"] == "reserve" and any(p.intersects(C) for C in IND_AREAS.values()):
            if home is None:
                home = _housing_elsewhere().buffer(KEEP_M, quad_segs=8)
            for key, C in IND_AREAS.items():
                ind = p.intersection(C).difference(home).buffer(-15.0).buffer(15.0)
                for q in _parts(ind):
                    if q.area >= MIN_PIECE_M2:
                        cands.append((q.area, len(out), key, q))
        out.append(z)
    # the new parks: the largest pieces first, until they hold as much land as the district gave up in H (the rest stays reserve)
    cands.sort(key=lambda c: -c[0])
    taken, n_of = 0.0, {}
    new_by_zone = {}
    for area, idx, key, q in cands:
        if taken >= removed:
            break
        new_by_zone.setdefault(idx, []).append((key, q)); taken += area
    final = []
    for idx, z in enumerate(out):
        if idx not in new_by_zone:
            final.append(z); continue
        rest = z["poly"]
        for key, q in new_by_zone[idx]:
            n_of[(z["id"], key)] = n_of.get((z["id"], key), 0) + 1
            i = n_of[(z["id"], key)]
            zid = f"{z['id']}_ind{key}{i if i > 1 else ''}"
            final.append({"id": zid, "use": "industry", "name_ru": NAMES[key], "poly": q, "years": [2034, 2048],
                          "rules": rules_of(zid, "industry", {}), "density": {}, "src": "owner_reloc",
                          "why": f"{MODEL}, {WHY}: новый промпарк в зоне {key} (4 фото владельца) вместо промзон у "
                                 f"жилья; не ближе {KEEP_M:.0f} м к жилью"})
            made.append((zid, f"резерв → промпарк {key} ({q.area / 1e4:.0f} га)"))
            rest = rest.difference(q)
        rest = rest.buffer(0)
        if not rest.is_empty and rest.area >= 200.0:
            zz = dict(z); zz["poly"] = rest; final.append(zz)
    out = final
    zones[:] = out
    if changes is not None:
        changes.extend(made)
    return made
