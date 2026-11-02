"""Open map data for Alatau City from Overture Maps (OSM-derived, ODbL), in the Unity frame.

    python3 -I tools/map/geo/fetch_overture.py              # download what is missing, then convert all layers
    python3 -I tools/map/geo/fetch_overture.py --refresh    # download everything again
    python3 -I tools/map/geo/fetch_overture.py --no-download

1) Download (anonymous S3, release frames.OVERTURE_RELEASE, box lon 76.55–77.50, lat 43.25–44.05, filter on the bbox columns):
   OUT/overture_raw/<type>.parquet — lon/lat WKB geometry plus the attribute columns a planner needs (flattened).
2) Convert: lon/lat → UTM 43N (pyproj) → Unity X/Z (X = E − 663000, Z = N − 4830000), clip to the city (twin outline ∪ genplan
   outline) + 5 km, write compact GeoJSON (coordinates in Unity metres, 0.1 m) to OUT/osm/ and OUT/osm/README.md.
Attribution for anything shown to users: «© OpenStreetMap contributors, Overture Maps Foundation»."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import frames  # noqa: E402

S3_ROOT = f"overturemaps-us-west-2/release/{frames.OVERTURE_RELEASE}"
TYPES = {
    "segment": "transportation/type=segment",
    "connector": "transportation/type=connector",
    "building": "buildings/type=building",
    "water": "base/type=water",
    "land_use": "base/type=land_use",
    "land_cover": "base/type=land_cover",
    "infrastructure": "base/type=infrastructure",
    "place": "places/type=place",
    "division": "divisions/type=division",
    "division_area": "divisions/type=division_area",
}


def _cols(t, pc):
    f = pc.field
    name = {"name": f("names", "primary")}
    base = {"id": f("id"), "geometry": f("geometry")}
    if t == "segment":
        return {**base, **name, "subtype": f("subtype"), "class": f("class"), "subclass": f("subclass"),
                "connectors": f("connectors"), "road_flags": f("road_flags"), "rail_flags": f("rail_flags"),
                "level_rules": f("level_rules"), "speed_limits": f("speed_limits"), "road_surface": f("road_surface"),
                "width_rules": f("width_rules"), "routes": f("routes"), "sources": f("sources")}
    if t == "connector":
        return base
    if t == "building":
        return {**base, **name, "subtype": f("subtype"), "class": f("class"), "height": f("height"),
                "num_floors": f("num_floors"), "is_underground": f("is_underground"), "has_parts": f("has_parts"),
                "sources": f("sources")}
    if t in ("water", "land_use", "infrastructure"):
        d = {**base, **name, "subtype": f("subtype"), "class": f("class"), "level": f("level"), "wikidata": f("wikidata")}
        if t == "water":
            d.update({"is_intermittent": f("is_intermittent"), "is_salt": f("is_salt")})
        if t == "infrastructure":
            d.update({"height": f("height"), "surface": f("surface")})
        if t == "land_use":
            d.update({"surface": f("surface"), "elevation": f("elevation")})
        return d
    if t == "land_cover":
        return {**base, "subtype": f("subtype")}
    if t == "place":
        return {**base, **name, "basic_category": f("basic_category"), "category": f("taxonomy", "primary"),
                "confidence": f("confidence"), "operating_status": f("operating_status")}
    if t == "division":
        return {**base, **name, "subtype": f("subtype"), "class": f("class"), "admin_level": f("admin_level"),
                "population": f("population"), "wikidata": f("wikidata"), "parent_division_id": f("parent_division_id")}
    if t == "division_area":
        return {**base, **name, "subtype": f("subtype"), "class": f("class"), "admin_level": f("admin_level"),
                "division_id": f("division_id"), "is_land": f("is_land")}
    raise KeyError(t)


def download(types, refresh=False):
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.fs as pafs
    import pyarrow.parquet as pq
    s3 = pafs.S3FileSystem(anonymous=True, region="us-west-2", connect_timeout=30, request_timeout=120)
    lon0, lat0, lon1, lat1 = frames.BBOX_LONLAT
    rawdir = os.path.join(frames.OUT, "overture_raw")
    os.makedirs(rawdir, exist_ok=True)
    for t in types:
        dst = os.path.join(rawdir, t + ".parquet")
        if os.path.exists(dst) and not refresh:
            print(f"[fetch] {t}: have {dst}", flush=True)
            continue
        t0 = time.time()
        d = ds.dataset(f"{S3_ROOT}/theme={TYPES[t].split('/')[0]}/{TYPES[t].split('/')[1]}", filesystem=s3, format="parquet")
        flt = ((pc.field("bbox", "xmin") <= lon1) & (pc.field("bbox", "xmax") >= lon0) &
               (pc.field("bbox", "ymin") <= lat1) & (pc.field("bbox", "ymax") >= lat0))
        tab = d.to_table(columns=_cols(t, pc), filter=flt)
        tmp = os.path.join(frames.OUT, "overture_raw", "." + t + ".tmp.parquet")
        pq.write_table(tab, tmp, compression="zstd")
        os.replace(tmp, dst)
        print(f"[fetch] {t}: {tab.num_rows} rows, {os.path.getsize(dst) / 1e6:.1f} MB, {time.time() - t0:.0f} s", flush=True)


# ------------------------------------------------------------------ conversion helpers
def _to_unity(geoms):
    import shapely
    def f(c):
        x, z = frames.lonlat_to_unity(c[:, 0], c[:, 1])
        return np.column_stack([x, z])
    return shapely.transform(geoms, f)


def _clip(geoms, region, keep_partial=True, dim=None):
    """Returns (mask, clipped geoms) for geometries that touch the region; lines and polygons are cut at its edge."""
    import shapely
    shapely.prepare(region)
    hit = shapely.intersects(region, geoms)
    g = geoms[hit]
    inside = shapely.contains(region, g)
    if keep_partial and (~inside).any():
        g = g.copy()
        g[~inside] = shapely.intersection(g[~inside], region)
        if dim is not None:
            g[~inside] = _dims(g[~inside], dim)
    ok = ~shapely.is_empty(g)
    idx = np.flatnonzero(hit)[ok]
    return idx, g[ok]


def _round(geoms, nd=1):
    import shapely
    return shapely.transform(geoms, lambda c: np.round(c, nd))


def _flags(rules):
    s = set()
    for r in rules or []:
        for v in (r.get("values") or []):
            s.add(v)
    return sorted(s)


def _level(rules):
    vals = [r.get("value") for r in (rules or []) if r.get("value") is not None]
    return int(max(vals, key=abs)) if vals else 0


def _speed(rules):
    best = None
    for r in rules or []:
        ms = r.get("max_speed")
        if ms and ms.get("value"):
            v = ms["value"] * (1.609 if (ms.get("unit") or "km/h") == "mph" else 1)
            best = max(best or 0, int(round(v)))
    return best


def _first_val(rules):
    for r in rules or []:
        if r.get("value") is not None:
            return r["value"]
    return None


def _refs(routes):
    s = []
    for r in routes or []:
        v = r.get("ref") or r.get("name")
        if v and v not in s:
            s.append(v)
    return s


def _clean(p):
    """Drop empty fields (None, False, empty list); zeros stay."""
    return {k: v for k, v in p.items() if not (v is None or v is False or (isinstance(v, list) and not v))}


def _dims(geoms, dim):
    """Keep only the parts of each geometry with the given dimension (1 lines, 2 polygons) after clipping."""
    import shapely
    out = []
    for g in geoms:
        if shapely.get_dimensions(g) == dim and g.geom_type != "GeometryCollection":
            out.append(g)
            continue
        parts = [q for q in getattr(g, "geoms", [g]) if shapely.get_dimensions(q) == dim]
        out.append(shapely.union_all(parts) if parts else shapely.Point())
    return np.array(out, dtype=object)


def _src(sources):
    for s in sources or []:
        if s.get("dataset"):
            return s["dataset"]
    return None


def write_geojson(path, geoms, props, meta):
    """Compact GeoJSON: one feature per line, Unity coordinates, 0.1 m."""
    import shapely
    gj = shapely.to_geojson(_round(geoms))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        head = {"type": "FeatureCollection", "name": os.path.basename(path)[:-8], **meta}
        f.write(json.dumps(head, ensure_ascii=False)[:-1] + ',"features":[\n')
        for i, (g, p) in enumerate(zip(gj, props)):
            f.write(('' if i == 0 else ',\n') + '{"type":"Feature","properties":' +
                    json.dumps(p, ensure_ascii=False, separators=(",", ":")) + ',"geometry":' + g + '}')
        f.write("\n]}\n")
    os.replace(tmp, path)
    return os.path.getsize(path)


META = {"crs": "Unity twin frame: X = E − 663000, Z = N − 4830000 (UTM 43N, EPSG:32643), metres",
        "source": f"Overture Maps {frames.OVERTURE_RELEASE} (s3://{S3_ROOT})", "attribution": frames.ATTRIBUTION}

ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "residential", "living_street", "unclassified",
                "service", "track", "unknown"}
PATH_CLASSES = {"pedestrian", "footway", "sidewalk", "crosswalk", "cycleway", "path", "steps", "bridleway"}


def convert(only=None):
    import pyarrow.parquet as pq
    import shapely
    import twin
    region = twin.clip_region(5000.0)
    rawdir = os.path.join(frames.OUT, "overture_raw")
    osmdir = os.path.join(frames.OUT, "osm")
    os.makedirs(osmdir, exist_ok=True)
    readme = []

    def load(t):
        tab = pq.read_table(os.path.join(rawdir, t + ".parquet"))
        g = _to_unity(shapely.from_wkb(tab.column("geometry").to_numpy(zero_copy_only=False)))
        return tab, g

    def col(tab, name, idx):
        return [tab.column(name)[int(i)].as_py() for i in idx]

    def emit(fname, geoms, props, what, extra_meta=None):
        size = write_geojson(os.path.join(osmdir, fname), geoms, props, {**META, **(extra_meta or {})})
        kinds = {}
        for g in shapely.get_type_id(geoms):
            kinds[int(g)] = kinds.get(int(g), 0) + 1
        readme.append((fname, len(props), size, what))
        print(f"[osm] {fname}: {len(props)} features, {size / 1e6:.2f} MB", flush=True)

    todo = only or ["segment", "building", "water", "land_use", "land_cover", "infrastructure", "place", "division_area"]

    # --- transportation: segments (roads, paths, rail) + the connectors they use
    if "segment" in todo:
        tab, g = load("segment")
        idx, gg = _clip(g, region, dim=1)
        sub = tab.take(idx).to_pylist()
        roads, paths, rail = ([], []), ([], []), ([], [])
        used = {}
        for row, geom in zip(sub, gg):
            st, cl = row["subtype"], row["class"]
            fl = _flags(row["road_flags"]) + [f for f in _flags(row["rail_flags"]) if f not in _flags(row["road_flags"])]
            p = {"id": row["id"], "class": cl, "sub": row["subclass"], "name": row["name"], "ref": _refs(row["routes"]) or None,
                 "bridge": "is_bridge" in fl, "tunnel": "is_tunnel" in fl,
                 "flags": [f for f in fl if f not in ("is_bridge", "is_tunnel")] or None,
                 "level": _level(row["level_rules"]) or None, "speed": _speed(row["speed_limits"]),
                 "surface": _first_val(row["road_surface"]), "width": _first_val(row["width_rules"]),
                 "len": round(float(shapely.length(geom)), 1), "src": _src(row["sources"])}
            conn = []
            for c in row["connectors"] or []:
                cid = c["connector_id"]
                if cid not in used:
                    used[cid] = len(used)
                conn.append(used[cid])
            p["conn"] = conn
            p = _clean(p)
            if st == "rail":
                tgt = rail
            elif cl in PATH_CLASSES:
                tgt = paths
            else:
                tgt = roads
            tgt[0].append(geom)
            tgt[1].append(p)
        emit("roads.geojson", np.array(roads[0]), roads[1],
             "дороги (transportation/segment, subtype road): class (motorway…residential, service, track, unknown), sub (link, driveway…), name, ref, bridge, tunnel, flags, level, speed (км/ч), surface, width, len (м), conn (индексы узлов connectors.geojson)")
        emit("paths.geojson", np.array(paths[0]), paths[1],
             "пешеходные и велопути (footway, sidewalk, crosswalk, cycleway, path, steps, pedestrian, bridleway), те же поля")
        emit("rail.geojson", np.array(rail[0]), rail[1], "железные дороги (subtype rail): class (standard_gauge, …), name, bridge, tunnel, flags, level")
        ctab, cg = load("connector")
        ids = ctab.column("id").to_pylist()
        pos = {cid: i for i, cid in enumerate(ids)}
        order = sorted(used.items(), key=lambda kv: kv[1])
        cgeom, cprops = [], []
        for cid, k in order:
            j = pos.get(cid)
            if j is None:
                continue
            cgeom.append(cg[j]); cprops.append({"i": k, "id": cid})
        emit("connectors.geojson", np.array(cgeom), cprops, "узлы графа дорог (transportation/connector), на которые ссылаются сегменты: i (индекс из conn), id (GERS)")

    if "building" in todo:
        tab, g = load("building")
        idx, gg = _clip(g, region, keep_partial=False)
        names = tab.column("name"); hts = tab.column("height"); fl = tab.column("num_floors"); cl = tab.column("class")
        st = tab.column("subtype"); und = tab.column("is_underground"); src = tab.column("sources"); ids = tab.column("id")
        props = []
        for i in idx:
            i = int(i)
            p = {"id": ids[i].as_py(), "class": cl[i].as_py(), "sub": st[i].as_py(), "name": names[i].as_py(),
                 "h": hts[i].as_py(), "floors": fl[i].as_py(), "under": und[i].as_py() or None, "src": _src(src[i].as_py()),
                 "area": round(float(shapely.area(g[i])), 1)}
            if p["h"] is not None:
                p["h"] = round(p["h"], 1)
            props.append(_clean(p))
        emit("buildings.geojson", gg, props, "здания (buildings/building): class, sub, name, h (м), floors, src (OpenStreetMap / Microsoft ML Buildings / …), area (м²); целиком, если касаются области")

    def simple(t, fname, what, fields, tol=None, keep_partial=True, filt=None):
        tab, g = load(t)
        dims = shapely.get_dimensions(g)
        idx, gg = _clip(g, region, keep_partial)
        if keep_partial:
            gg = np.array([q if shapely.get_dimensions(q) == dims[i] and q.geom_type != "GeometryCollection" else _dims([q], int(dims[i]))[0]
                           for q, i in zip(gg, idx)], dtype=object)
            ok = ~shapely.is_empty(gg)
            idx, gg = idx[ok], gg[ok]
        rows = tab.take(idx).drop(["geometry"]).to_pylist()
        if filt is not None:
            m = np.array([filt(r) for r in rows], bool)
            rows = [r for r, k in zip(rows, m) if k]
            gg = gg[m]
        if tol:
            gg = shapely.simplify(gg, tol, preserve_topology=True)
        props = [_clean({k: r.get(k) for k in fields}) for r in rows]
        emit(fname, gg, props, what)

    if "water" in todo:
        simple("water", "water.geojson", "вода (base/water): реки, каналы, озёра, водохранилище; class, sub (subtype), name, is_intermittent, is_salt, level, wikidata",
               ["id", "class", "subtype", "name", "is_intermittent", "is_salt", "level", "wikidata"], tol=0.5)
    if "land_use" in todo:
        simple("land_use", "land_use.geojson", "землепользование (base/land_use): class, subtype, name, surface", ["id", "class", "subtype", "name", "surface"], tol=0.5)
    if "land_cover" in todo:
        simple("land_cover", "land_cover.geojson", "покров земли (base/land_cover, спутниковая классификация): subtype (crop, grass, shrub, barren, urban, wetland, forest…); упрощён до 5 м",
               ["id", "subtype"], tol=5.0)
    if "infrastructure" in todo:
        simple("infrastructure", "infrastructure.geojson", "инфраструктура (base/infrastructure): ЛЭП и опоры (subtype power: power_line, minor_line, power_tower, power_pole, substation…), мосты (bridge), аэродромы (airport), переходы, барьеры и др.; class, subtype, name, height, surface",
               ["id", "class", "subtype", "name", "height", "surface", "level", "wikidata"])
    if "place" in todo:
        simple("place", "places.geojson", "места (places/place): name, category (taxonomy), basic_category, confidence, operating_status", ["id", "name", "category", "basic_category", "confidence", "operating_status"], keep_partial=False)
    if "division_area" in todo:
        simple("division_area", "divisions.geojson", "границы административных единиц и населённых пунктов (divisions/division_area): subtype (country, region, county, locality, neighborhood…), class, name, admin_level, division_id",
               ["id", "subtype", "class", "name", "admin_level", "division_id", "is_land"], tol=1.0)
        simple("division", "division_points.geojson", "точки административных единиц (divisions/division): subtype, class, name, population, wikidata, parent_division_id",
               ["id", "subtype", "class", "name", "admin_level", "population", "wikidata", "parent_division_id"], keep_partial=False)

    # README (merge with what is already there so a partial run keeps the other rows)
    rp = os.path.join(osmdir, "README.md")
    old = {}
    if os.path.exists(rp):
        for line in open(rp, encoding="utf-8"):
            if line.startswith("| `") and line.count("|") >= 5:
                old[line.split("`")[1]] = line.rstrip("\n")
    for fname, n, size, what in readme:
        old[fname] = f"| `{fname}` | {n:,} | {size / 1e6:.2f} МБ | {what} |".replace(f"{n:,}", f"{n:,}".replace(",", " "), 1)
    with open(rp, "w", encoding="utf-8") as f:
        f.write("# Открытые данные карты Alatau City (Overture Maps), система координат Unity\n\n")
        f.write(f"Источник: Overture Maps, релиз {frames.OVERTURE_RELEASE} (`s3://{S3_ROOT}`, анонимный доступ), выборка по bbox "
                f"lon {frames.BBOX_LONLAT[0]}–{frames.BBOX_LONLAT[2]}, lat {frames.BBOX_LONLAT[1]}–{frames.BBOX_LONLAT[3]}. "
                f"Overture собирает данные OpenStreetMap (ODbL) и другие открытые наборы; подпись для пользователей: «{frames.ATTRIBUTION}».\n\n")
        f.write("Координаты: X = E − 663000, Z = N − 4830000, метры (UTM 43N, EPSG:32643; пересчёт lon/lat через pyproj, `tools/map/geo/frames.py`). "
                "Округление 0,1 м. Обрезка: город (контур районов двойника ∪ контур города генплана) + 5 км; линии и полигоны режутся по краю, "
                "здания и точки берутся целиком, если касаются области. Пересобрать: `python3 -I tools/map/geo/fetch_overture.py` "
                "(сырые выборки лежат в `../overture_raw/*.parquet`, lon/lat WKB).\n\n")
        f.write("Формат: GeoJSON FeatureCollection, одна запись на строку; координаты [x, z] Unity. Загрузка: `json.load` или "
                "`shapely.from_geojson`; в Python удобно `tools/map/geo/layers.py: load('roads')`.\n\n")
        f.write("| Файл | Объектов | Размер | Что внутри |\n|---|---:|---:|---|\n")
        for k in sorted(old):
            f.write(old[k] + "\n")
    print("[osm] README written", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--no-convert", action="store_true")
    ap.add_argument("--only", nargs="*", help="types: " + " ".join(TYPES))
    a = ap.parse_args()
    if not a.no_download:
        want = a.only or list(TYPES)
        if "segment" in want and "connector" not in want:
            want.append("connector")
        if "division_area" in want and "division" not in want:
            want.append("division")
        download(want, a.refresh)
    if not a.no_convert:
        convert(a.only)


if __name__ == "__main__":
    main()
