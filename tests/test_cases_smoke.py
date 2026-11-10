"""Smoke tests for the two example case directories under examples/mine_cases/.

Each case is a sub-directory holding ``input.txt``.  These tests assert that the
data parse and that one quick reconstruction produces a non-empty mesh with
finite volume and surface area.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
CASES = REPO / "examples" / "mine_cases"

_pyd_ok = bool(list((REPO / "oresecstitch").glob("oresecstitch_native*.pyd")))
pytestmark = pytest.mark.skipif(not _pyd_ok,
                                reason="oresecstitch_native pyd not available")


def _case_dirs() -> list[Path]:
    if not CASES.is_dir():
        return []
    return sorted(p for p in CASES.iterdir()
                  if p.is_dir() and (p / "input.txt").is_file())


CASE_DIRS = _case_dirs()
EXPECTED_SLICES = {"case01": 17, "case02": 11}


def _has_py() -> bool:
    try:
        import oresecstitch  # noqa: F401
        from drivers import oresecstitch_data as data  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_py(), reason="python package not importable")
@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=[p.name for p in CASE_DIRS])
def test_case_directories_parse(case_dir):
    """Every shipped case parses: contours and points are found and counted."""
    from drivers import oresecstitch_data as data

    ds = data.contour_case(case_dir, name=case_dir.name)
    assert ds.meta["n_lines"] > 0, f"{case_dir}: no contours parsed"
    assert ds.meta["n_points"] > 0, f"{case_dir}: no points parsed"
    assert len(ds.points) == ds.meta["n_points"]
    if case_dir.name in EXPECTED_SLICES:
        assert ds.meta["n_slices"] == EXPECTED_SLICES[case_dir.name]


@pytest.mark.skipif(not _has_py(), reason="python package not importable")
def test_quick_reconstruction_nonempty():
    """One real case through the full reconstruct() path: non-empty mesh with
    finite volume and surface area."""
    if not CASE_DIRS:
        pytest.skip("no case directories shipped")
    from drivers import oresecstitch_data as data
    from oresecstitch import api, metrics

    ds = data.contour_case(CASE_DIRS[0], name=CASE_DIRS[0].name)
    result = api.reconstruct(ds.points, ds.lines,
                             api.StitchParams(end_capping="smooth"))

    assert result.mesh.n_triangles > 0, "no triangles generated"
    assert np.isfinite(metrics.volume(result.mesh.points, result.mesh.triangles))
    assert np.isfinite(metrics.surface_area(result.mesh.points, result.mesh.triangles))
