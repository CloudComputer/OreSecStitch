"""Geometry metrics: volume, surface area and sampled surface distances.

All functions take ``points`` as an ``(N, 3)`` float array and ``triangles`` as
an ``(M, 3)`` integer array.  Distances use scipy's KD-tree; the remaining
functions are plain NumPy.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def triangle_areas(points, triangles) -> np.ndarray:
    """Area of every triangle, shape (M,)."""
    p = np.asarray(points, dtype=float)
    t = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if len(t) == 0:
        return np.zeros(0, dtype=float)
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)


def surface_area(points, triangles) -> float:
    """Total surface area."""
    return float(triangle_areas(points, triangles).sum())


def volume(points, triangles) -> float:
    """Signed volume via the divergence theorem (positive for outward normals)."""
    p = np.asarray(points, dtype=float)
    t = np.asarray(triangles, dtype=np.int64)
    if len(t) == 0:
        return 0.0
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def sample_surface(points, triangles, n: int = 20000, seed: int = 0) -> np.ndarray:
    """Uniform-area sampling of points on the triangle surface."""
    rng = np.random.default_rng(seed)
    p = np.asarray(points, dtype=float)
    t = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = areas.sum()
    if total <= 0:
        raise ValueError("degenerate mesh: zero total area")
    idx = rng.choice(len(t), size=n, p=areas / total)
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1.0
    u[flip], v[flip] = 1.0 - u[flip], 1.0 - v[flip]
    w = (1.0 - u - v)[:, None]
    return p[t[idx, 0]] * w + p[t[idx, 1]] * u[:, None] + p[t[idx, 2]] * v[:, None]


def distance_metrics(points_a, tris_a, points_b, tris_b, n: int = 20000,
                     seed: int = 0) -> dict:
    """Symmetric sampled surface-to-surface distances between two meshes."""
    from scipy.spatial import cKDTree

    sa = sample_surface(points_a, tris_a, n, seed)
    sb = sample_surface(points_b, tris_b, n, seed)
    ta, tb = cKDTree(sa), cKDTree(sb)
    da, _ = tb.query(sa)   # A samples -> mesh B
    db, _ = ta.query(sb)   # B samples -> mesh A
    return dict(
        hausdorff=float(max(da.max(), db.max())),
        hd95=float(max(np.percentile(da, 95), np.percentile(db, 95))),
        mean_distance=float(max(da.mean(), db.mean())),
    )


def relative_volume_error(value: float, ground_truth: float) -> float:
    if ground_truth == 0:
        return float("nan")
    return abs(value - ground_truth) / abs(ground_truth)


def load_obj(path) -> tuple[np.ndarray, np.ndarray]:
    """Read an ASCII OBJ mesh -> ``(points (N,3) float64, triangles (M,3) int64)``.

    Handles ``f i j k`` and slashed forms (``f i/j k/l ...``) with negative
    indices; polygons with more than three vertices are fan-triangulated.
    """
    pts: list[list[float]] = []
    tris: list[tuple[int, int, int]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.split()
                pts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    s = tok.split("/")[0]
                    if not s:
                        continue
                    i = int(s)
                    idx.append(i - 1 if i > 0 else len(pts) + i)
                for k in range(1, len(idx) - 1):
                    tris.append((idx[0], idx[k], idx[k + 1]))
    if not pts or not tris:
        raise ValueError(f"{path}: no mesh data (v={len(pts)}, f={len(tris)})")
    return np.asarray(pts, dtype=np.float64), np.asarray(tris, dtype=np.int64)


def save_json(path, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def metrics_row(**kw) -> dict:
    """Coerce numpy scalars to plain Python for CSV/JSON serialisation."""
    out = {}
    for k, v in kw.items():
        if isinstance(v, (bool, int, str)) or v is None:
            out[k] = v
        else:
            out[k] = float(v) if isinstance(v, float) else v.item() if hasattr(v, "item") else v
    return out
