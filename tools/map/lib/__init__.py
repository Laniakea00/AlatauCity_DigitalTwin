"""Shared library of the Stage 7 map pipeline (levels 1–2). Owner: w43. Others import it and never edit it.

    import os, sys
    sys.path.insert(0, "<repo>/tools/map")          # the folder that holds lib/, gen/, validate/
    from lib import paths, jio, norms, terrain, geom, years

* paths   — OUT, TWIN, W34, SPEC, out_dir(d), spec_path(d)
* jio     — load_json / save_json (compact when > 1 MB), load_spec(d), load_city(), load_geojson(path)
* norms   — N = norms.get(); N.norm(key), N.status(key), N.sev(key), N.profile(cls, overrides), N.red_line_w(cls),
            N.node_group(cls), N.matrix_cell(cls_a, cls_b), N.node_types
* terrain — h(x, z), slope(x, z) (the twin's terrain grid, as CityGround.HeightAt)
* geom    — polylines: chainage, point_at, resample, offset, cut, tapers, arcs, Dubins paths, ribbons, crossings
* years   — the 4 scenario years [base, fast, slow, infra], EXISTING, effective_year (port of TwinScenario)
* rail    — tracks(area, pad): operating railway tracks of W34 osm/rail.geojson (no tunnels, metro, abandoned lines)

Model constants that are not norms (and so are not in norms.json) live in MODEL below, each with its label.
"""
MODEL = {
    # «модель qTwin»: no norm gives a structure depth; a 1.5 m deck (slab + girders of a 20–35 m span) is a typical figure
    "deck_depth_m": {"value": 1.5, "why": "модель qTwin: строительная высота пролётного строения путепровода (норма не найдена)"},
    # the deck over a railway spans the track's structure gauge on each side of its axis (crossing at an angle: / sin)
    "rail_track_half_m": {"value": 2.45, "why": "модель qTwin: полуширина габарита приближения строений С от оси пути (ГОСТ 9238, 4900 мм; текст с числом не получен)"},
    # the vertical tolerance under which two road surfaces at one point count as the same level
    "same_level_tol_m": {"value": 0.5, "why": "модель qTwin: допуск отметок узла в одном уровне"},
    # the generator aims a little above the clearance norm so 1 cm rounding of exported heights never drops below it
    "clearance_margin_m": {"value": 0.1, "why": "модель qTwin: запас над нормой габарита (округление отметок, сглаживание)"},
    # heights are exported to 1 cm: two rounded values differ from the true difference by up to 2 cm
    "height_round_tol_m": {"value": 0.02, "why": "модель qTwin: допуск сравнения отметок, округлённых до 1 см"},
    # spacing of profile vertices along generated roads
    "profile_step_m": {"value": 10.0, "why": "модель qTwin: шаг вершин продольного профиля"},
    # straight run before a ramp terminal on the minor road, so the junction angle is measured on a straight
    "terminal_straight_m": {"value": 25.0, "why": "модель qTwin: прямой участок съезда перед примыканием"},
    # clear gap between the edges of two ramps that do not meet (paint + barrier)
    "ramp_clear_gap_m": {"value": 3.0, "why": "модель qTwin: зазор между кромками несвязанных съездов"},
    "lrt_rail_over_deck_m": {"value": 1.2, "why": "модель qTwin: головка рельса над низом пролёта эстакады ЛРТ (строительная высота)"},
    # LRT grade is measured over a chord of at least this length (and between neighbouring vertices, both less the
    # rounding tolerance of two heights): 1 cm rounding on a 2 m vertex pair alone is 0.5 % of grade
    "lrt_slope_base_m": {"value": 20.0, "why": "модель qTwin: база (хорда) измерения уклона пути ЛРТ"},
    "lrt_viaduct_w_m": {"value": 9.0, "why": "модель qTwin: ширина пролётного строения двухпутной эстакады ЛРТ"},
    # every existing village house gets a street (village_lane) within this distance (brief w43; no norm found)
    "house_access_m": {"value": 25.0, "why": "модель qTwin: дом не дальше 25 м от улицы (задание уровня 1)"},
    "village_lane_grid_m": {"value": 5.0, "why": "модель qTwin: шаг сетки поиска трассы проулка между домами"},
    # industrial blocks are longer than quarters.block_side_m (no norm number for them)
    "industrial_block_factor": {"value": 2.0, "why": "модель qTwin: промышленный квартал в 2 раза длиннее жилого"},
    # no local grid closer than this to an interchange's ramps
    "interchange_grid_clear_m": {"value": 60.0, "why": "модель qTwin: местная сеть не подходит к съездам развязки ближе 60 м"},
    # the ground LRT crosses a cross street near its junction with the street the line runs in (median): the junction is the
    # level crossing when it is this close, not a second node a few metres away
    "lrt_crossing_join_m": {"value": 15.0, "why": "модель qTwin: переезд ЛРТ совмещается с узлом улицы ближе 15 м"},
    # the railway viaduct of a spec `rail` block as merge (RAIL_DECK_M) and RailLayer (DeckBelow, OuterHalf) build it
    "rail_deck_below_m": {"value": 1.8, "why": "модель qTwin: низ пролёта ж/д эстакады на 1,8 м ниже головки рельса (Gate v1.2, RailLayer)"},
    "rail_deck_half_m": {"value": 2.6, "why": "модель qTwin: пролётное строение ж/д эстакады на 2,6 м в сторону от оси пути (RailLayer)"},
}


def model(key):
    return MODEL[key]["value"]
