"""Validator context (CONTRACT §5), built by w43. Rule modules get one `ctx`:

ctx.d, ctx.spec, ctx.city, ctx.norms (raw norms.json), ctx.N (lib.norms.Norms), ctx.norm(key, sub=None),
ctx.sev(key) → "error" | "warning", ctx.rules (rules.json), ctx.rule(no) → its record,
ctx.network, ctx.lrt, ctx.blocks, ctx.lots, ctx.buildings, ctx.features, ctx.driveways (raw dicts, None when the
file is missing), ctx.area (shapely polygon), ctx.h(x, z) terrain height, ctx.water (shapely), ctx.flood_485 (land
below the Kapchagay design level, shapely or None), ctx.villages_houses (existing house footprints in village zones),
ctx.years = [2026, 2030, 2034, 2040, 2050], ctx.shift(year, scenario) (effective year of a base year in a scenario),
ctx.issue(rule, sev, x, z, what_ru, ids=(), lv=0) → issue dict, ctx.standing(years4, year, scenario=0).
Heavy members (water, houses, flood) are computed on first use.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
if MAP not in sys.path:
    sys.path.insert(0, MAP)
from lib import jio, norms, paths, terrain  # noqa: E402
from lib import years as Y  # noqa: E402

FILES = {"network": "network.json", "lrt": "lrt.json", "blocks": "blocks.json", "lots": "lots.json",
         "buildings": "buildings.json", "features": "features.json", "driveways": "driveways.json"}


class Ctx:
    def __init__(self, district, out=None):
        import shapely
        self.district_arg = district
        self.d = paths.district_id(district)
        self.out = out or paths.OUT
        self.spec = jio.load_spec(district)
        self.city = jio.load_city()
        self.N = norms.get()
        self.norms = self.N.raw if hasattr(self.N, "raw") else jio.load_json(os.path.join(paths.SPEC, "norms.json"))
        self.rules = jio.load_json(os.path.join(paths.SPEC, "rules.json"))
        self._rules_by_no = {r["id"]: r for r in self.rules["rules"]}
        for k, f in FILES.items():
            setattr(self, k, jio.load_out(self.d, f, self.out))
        a = self.spec.get("area")
        if a:
            self.area = shapely.Polygon(a).buffer(0)
        elif self.network and self.network.get("area"):
            self.area = shapely.Polygon(self.network["area"]).buffer(0)
        else:
            b = self.spec.get("boundary")
            self.area = shapely.Polygon(b if isinstance(b, list) else b.get("polygon")).buffer(0)
        self.years = list(self.N.norm("validator.years"))
        self._water = self._flood = self._houses = None

    # ------------------------------------------------------------------ norms and rules
    def norm(self, key, sub=None):
        return self.N.norm(key, sub)

    def sev(self, key):
        return self.N.sev(key)

    def rule(self, no):
        return self._rules_by_no.get(no)

    # ------------------------------------------------------------------ terrain, water, houses
    def h(self, x, z):
        return terrain.h(x, z)

    @property
    def water(self):
        if self._water is None:
            import shapely
            polys = []
            for f in jio.load_geojson(paths.w34("osm", "water.geojson")):
                g = shapely.geometry.shape(f["geometry"])
                if g.geom_type in ("Polygon", "MultiPolygon") and g.intersects(self.area):
                    polys.append(g.intersection(self.area))
            self._water = shapely.union_all(polys) if polys else shapely.Polygon()
        return self._water

    @property
    def flood_485(self):
        if self._flood is None:
            # the design level + freeboard (flood.kapchagay_levels_m npu_design_max + flood.freeboard_m = real 485.5 m,
            # twin 483.5 m: FloodModel.Datum), the same land gen_blocks_lots keeps as park (land_util.flood_poly)
            gen = os.path.join(MAP, "gen")
            if gen not in sys.path:
                sys.path.insert(0, gen)
            import land_util
            self._flood = land_util.flood_poly(self.area, land_util.Norms())[0]
        return self._flood

    @property
    def villages_houses(self):
        if self._houses is None:
            import shapely
            sys.path.insert(0, os.path.join(MAP, "gen"))
            from net_osm import houses_in
            zones = [shapely.Polygon(z["polygon"]).buffer(0).intersection(self.area)
                     for z in self.spec.get("zones", []) if z.get("use") == "village_existing"]
            zones = [z for z in zones if not z.is_empty]
            self._houses = houses_in(zones) if zones else []
        return self._houses

    # ------------------------------------------------------------------ years
    def shift(self, year, scenario="base", use="road", source="new"):
        """Effective year of an object whose base-scenario year is `year` in a scenario (base, fast, slow, infra or
        its index 0..3)."""
        if isinstance(scenario, int):
            scenario = Y.SCENARIOS[scenario]
        return Y.effective_year(int(year), use, source, scenario)

    @staticmethod
    def standing(y4, year, scenario=0):
        return Y.standing(y4, year, scenario)

    # ------------------------------------------------------------------ issues
    @staticmethod
    def issue(rule, sev, x, z, what_ru, ids=(), lv=0):
        return {"rule": rule, "sev": sev, "x": round(float(x), 1), "z": round(float(z), 1), "lv": int(lv),
                "what_ru": what_ru, "ids": list(ids)}


def build(district, out=None):
    return Ctx(district, out)
