"""Unit tests for the pure-Python geometry metrics (no native extension needed)."""
from __future__ import annotations

import numpy as np
import pytest

from oresecstitch import metrics


def _cube():
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 1.0],
    ], dtype=float)
    triangles = np.array([
        [0, 2, 1], [0, 3, 2],      # bottom (normal -z)
        [4, 5, 6], [4, 6, 7],      # top    (normal +z)
        [0, 1, 5], [0, 5, 4],      # front  (normal -y)
        [3, 7, 6], [3, 6, 2],      # back   (normal +y)
        [0, 4, 7], [0, 7, 3],      # left   (normal -x)
        [1, 2, 6], [1, 6, 5],      # right  (normal +x)
    ], dtype=np.int64)
    return points, triangles


def test_cube_volume_and_area():
    points, triangles = _cube()
    assert metrics.volume(points, triangles) == pytest.approx(1.0)
    assert metrics.surface_area(points, triangles) == pytest.approx(6.0)


def test_load_obj_roundtrip(tmp_path):
    points, triangles = _cube()
    path = tmp_path / "cube.obj"
    with open(path, "w", encoding="utf-8") as fh:
        for x, y, z in points:
            fh.write(f"v {x} {y} {z}\n")
        for a, b, c in triangles:
            fh.write(f"f {a + 1} {b + 1} {c + 1}\n")

    loaded_points, loaded_triangles = metrics.load_obj(path)
    assert np.allclose(loaded_points, points)
    assert np.array_equal(loaded_triangles, triangles)


def test_distance_metrics_identical_mesh():
    points, triangles = _cube()
    dm = metrics.distance_metrics(points, triangles, points, triangles,
                                  n=1000, seed=0)
    assert dm["hausdorff"] < 1e-9
    assert dm["hd95"] < 1e-9
    assert dm["mean_distance"] < 1e-9
