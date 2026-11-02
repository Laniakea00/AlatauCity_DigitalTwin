"""Terrain height and slope (wraps tools/map/geo/terrain.py, which samples the twin's grid exactly like CityGround.HeightAt)."""
import os
import sys

from . import paths

_T = None


def _terrain():
    global _T
    if _T is None:
        os.environ.setdefault("ALATAU_ASSETS", paths.TWIN)
        if paths.GEO not in sys.path:
            sys.path.insert(0, paths.GEO)
        import terrain as geo_terrain  # tools/map/geo/terrain.py
        _T = geo_terrain.terrain()
    return _T


def h(x, z):
    """Ground height (m a.s.l., the twin's datum) at x, z; scalars or numpy arrays."""
    return _terrain().height(x, z)


def slope(x, z, d=25.0):
    """Ground slope as a fraction."""
    return _terrain().slope(x, z, d)


def profile(pts, step=10.0):
    """(s, x, z, h) every `step` metres along a polyline."""
    return _terrain().profile(pts, step)
