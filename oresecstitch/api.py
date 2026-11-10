"""OreSecStitch high-level API: planar contour stacks -> closed surface mesh.

Typical use::

    from oresecstitch import reconstruct, StitchParams
    ds = make_cylinder()                # from drivers.oresecstitch_data
    res = reconstruct(ds.points, ds.lines, StitchParams(end_capping="smooth"))
    res.mesh.save_obj("out.obj")
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

# --- string -> native enum maps -------------------------------------------
END_CAPPING = {"none": 0, "smooth": 1, "straight": 2}
TRIANGULATION_COST = {"perimeter": 0, "area": 1}
BRANCH_METHOD = {"point_distance": 0, "triangulation_region": 1}


def _map(table: dict, value):
    return table[value] if isinstance(value, str) else int(value)


@dataclass(frozen=True)
class StitchParams:
    """Reconstruction parameters. ``None`` keeps the native default."""
    default_slice_thickness: float | None = None
    end_capping: str | int | None = None            # none | smooth | straight
    triangulation_cost: str | int | None = None     # perimeter | area
    branch_method: str | int | None = None          # point_distance | triangulation_region
    greedy: bool | None = True                      # greedy branch pairing
    branch_densify: bool | None = None
    contour_densify: bool | None = None
    filter_small_branches: bool | None = None
    use_cgal: bool | None = True                    # CGAL triangulation
    logging: bool | None = False
    debug_obj: bool | None = False

    def to_kwargs(self) -> dict:
        kw: dict = {}
        if self.default_slice_thickness is not None:
            kw["default_slice_thickness"] = float(self.default_slice_thickness)
        if self.end_capping is not None:
            kw["end_capping_mode"] = _map(END_CAPPING, self.end_capping)
        if self.triangulation_cost is not None:
            kw["triangulation_cost"] = _map(TRIANGULATION_COST, self.triangulation_cost)
        if self.branch_method is not None:
            kw["branch_method"] = _map(BRANCH_METHOD, self.branch_method)
        for name in ("greedy", "branch_densify", "contour_densify",
                     "filter_small_branches", "use_cgal", "logging", "debug_obj"):
            v = getattr(self, name)
            if v is not None:
                kw[name] = bool(v)
        return kw


@dataclass(frozen=True)
class SurfaceMesh:
    """Closed triangulated surface."""
    points: np.ndarray      # (N,3) float64
    triangles: np.ndarray   # (M,3) int32

    @property
    def n_points(self) -> int:
        return int(len(self.points))

    @property
    def n_triangles(self) -> int:
        return int(len(self.triangles))

    def save_obj(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("# OreSecStitch OBJ export\n")
            for x, y, z in self.points:
                f.write(f"v {x:.9g} {y:.9g} {z:.9g}\n")
            for a, b, c in self.triangles:
                f.write(f"f {a + 1} {b + 1} {c + 1}\n")

    def save_ply(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="ascii") as f:
            f.write("ply\nformat ascii 1.0\ncomment OreSecStitch export\n")
            f.write(f"element vertex {self.n_points}\n"
                    "property float x\nproperty float y\nproperty float z\n")
            f.write(f"element face {self.n_triangles}\n"
                    "property list uchar int vertex_indices\nend_header\n")
            for x, y, z in self.points:
                f.write(f"{x:.9g} {y:.9g} {z:.9g}\n")
            for a, b, c in self.triangles:
                f.write(f"3 {a} {b} {c}\n")


@dataclass(frozen=True)
class StitchResult:
    mesh: SurfaceMesh
    time_s: float
    params: StitchParams


def _normalize_input(points, lines):
    """points -> (N,3) float64; lines -> list of int64 index arrays.

    ``lines`` accepts either a list of (Mi,) point-index arrays or a list of
    (Mi,3) coordinate arrays (coordinates are appended to ``points``).
    """
    points = np.ascontiguousarray(points, dtype=np.float64).reshape(-1, 3)
    if len(points) < 3:
        raise ValueError("points must contain at least 3 vertices")
    idx_lines: list[np.ndarray] = []
    extra: list[np.ndarray] = []
    for ln in lines:
        arr = np.asarray(ln)
        if arr.ndim == 2:  # coordinate polyline
            base = len(points) + sum(len(e) for e in extra)
            idx_lines.append(np.arange(base, base + len(arr), dtype=np.int64))
            extra.append(np.ascontiguousarray(arr, dtype=np.float64))
        elif arr.ndim == 1:
            idx_lines.append(np.ascontiguousarray(arr, dtype=np.int64))
        else:
            raise ValueError("each polyline must be a 1-D index or (Mi,3) array")
    if extra:
        points = np.vstack([points, *extra])
    return points, idx_lines


def reconstruct(points, lines, params: StitchParams | None = None,
                **overrides) -> StitchResult:
    """Reconstruct a closed surface from a planar contour stack."""
    from . import native

    if native is None:
        detail = ""
        try:
            from . import _native_import_error
            detail = f"\nOriginal import error: {_native_import_error}"
        except ImportError:
            pass
        raise ImportError(
            "The OreSecStitch native extension is unavailable. Install the "
            "package including oresecstitch_native*.pyd and the runtime DLLs in "
            "oresecstitch/dlls/, or set ORESECSTITCH_NATIVE_DIR and "
            "ORESECSTITCH_DLL_DIRS to their locations." + detail
        )
    params = params or StitchParams()
    if overrides:
        params = replace(params, **overrides)
    pts_in, idx_lines = _normalize_input(points, lines)

    t0 = time.perf_counter()
    pts, tris = native.reconstruct(pts_in, idx_lines, **params.to_kwargs())
    elapsed = time.perf_counter() - t0

    mesh = SurfaceMesh(points=np.asarray(pts), triangles=np.asarray(tris, dtype=np.int32))
    if mesh.n_triangles == 0:
        raise RuntimeError("reconstruction produced an empty mesh")
    return StitchResult(mesh=mesh, time_s=elapsed, params=params)
