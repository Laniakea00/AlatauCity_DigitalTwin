"""Terrain sampler of the twin (Unity frame): height at (x, z) and slope, exactly as CityGround.HeightAt.

    python3 -I tools/map/geo/terrain.py -3170 -19080          # height and slope at Iconic
    python3 -I tools/map/geo/terrain.py --grid                 # grid facts

Grid: CityData/terrain_heights.bytes (float32, 873 × 1235, 50 m, x0 −21800, z0 −30300, row 0 = south, col 0 = west),
meta in CityData/city_meta.json. Heights are the twin's metres (= Copernicus GLO-30 − 2 m at the reservoir, FloodModel.Datum)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import frames  # noqa: E402


class Terrain:
    def __init__(self, heights=None, meta=None):
        m = meta or frames.terrain_meta()
        self.nx, self.ny, self.step, self.x0, self.z0 = int(m["nx"]), int(m["ny"]), float(m["step"]), float(m["x0"]), float(m["z0"])
        path = heights or frames.asset("CityData/terrain_heights.bytes")
        h = np.fromfile(path, dtype="<f4")
        if h.size < self.nx * self.ny:
            raise ValueError(f"{path}: {h.size} values, need {self.nx * self.ny}")
        self.h = h[: self.nx * self.ny].reshape(self.ny, self.nx).astype(np.float64)
        self.x1 = self.x0 + (self.nx - 1) * self.step
        self.z1 = self.z0 + (self.ny - 1) * self.step

    def height(self, x, z):
        """Bilinear height (m), clamped at the grid edge like CityGround.HeightAt. Scalars or arrays."""
        x = np.asarray(x, float); z = np.asarray(z, float)
        c = np.clip((x - self.x0) / self.step, 0, self.nx - 1.001)
        r = np.clip((z - self.z0) / self.step, 0, self.ny - 1.001)
        c0 = c.astype(int); r0 = r.astype(int); a = c - c0; b = r - r0
        h = self.h
        v = (h[r0, c0] * (1 - a) * (1 - b) + h[r0, c0 + 1] * a * (1 - b) + h[r0 + 1, c0] * (1 - a) * b + h[r0 + 1, c0 + 1] * a * b)
        return float(v) if v.ndim == 0 else v

    def gradient(self, x, z, d=25.0):
        """(dh/dx, dh/dz) by central differences over ±d metres."""
        x = np.asarray(x, float); z = np.asarray(z, float)
        gx = (self.height(x + d, z) - self.height(x - d, z)) / (2 * d)
        gz = (self.height(x, z + d) - self.height(x, z - d)) / (2 * d)
        return gx, gz

    def slope(self, x, z, d=25.0):
        """Slope as a fraction (rise/run); × 100 for percent, arctan for degrees."""
        gx, gz = self.gradient(x, z, d)
        return np.hypot(gx, gz)

    def slope_deg(self, x, z, d=25.0):
        return np.degrees(np.arctan(self.slope(x, z, d)))

    def aspect_deg(self, x, z, d=25.0):
        """Direction the ground falls towards, degrees clockwise from north (Z)."""
        gx, gz = self.gradient(x, z, d)
        return (np.degrees(np.arctan2(-gx, -gz)) + 360.0) % 360.0

    def profile(self, pts, step=10.0):
        """Heights along a polyline [(x, z), …] every `step` metres: returns (s, x, z, h)."""
        P = np.asarray(pts, float)
        seg = np.hypot(*np.diff(P, axis=0).T)
        S = np.concatenate([[0], np.cumsum(seg)])
        s = np.arange(0, S[-1] + 1e-9, step)
        x = np.interp(s, S, P[:, 0]); z = np.interp(s, S, P[:, 1])
        return s, x, z, self.height(x, z)

    def inside(self, x, z):
        return (self.x0 <= x <= self.x1) and (self.z0 <= z <= self.z1)


_T = None


def terrain():
    global _T
    if _T is None:
        _T = Terrain()
    return _T


def height(x, z):
    return terrain().height(x, z)


def slope(x, z):
    return terrain().slope(x, z)


if __name__ == "__main__":
    t = terrain()
    if len(sys.argv) >= 3 and sys.argv[1] != "--grid":
        x, z = float(sys.argv[1]), float(sys.argv[2])
        print(f"x {x:.1f} z {z:.1f}: height {t.height(x, z):.2f} m, slope {t.slope(x, z) * 100:.2f} % "
              f"({t.slope_deg(x, z):.2f}°), falls towards {t.aspect_deg(x, z):.0f}° from north")
    else:
        print(f"grid {t.nx} × {t.ny}, step {t.step} m, x {t.x0}…{t.x1}, z {t.z0}…{t.z1}, "
              f"height {t.h.min():.1f}…{t.h.max():.1f} m")
