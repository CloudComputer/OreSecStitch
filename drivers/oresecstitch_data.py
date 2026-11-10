"""Synthetic planar-contour datasets with analytic ground truth (OreSecStitch).

Every builder returns a :class:`ContourDataset` holding
``points (N,3) float64`` + ``lines`` (list of per-slice point-index arrays)
so the stack can be fed directly into :func:`oresecstitch.reconstruct`.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class ContourDataset:
    name: str
    points: np.ndarray            # (N,3) float64
    lines: list                   # list of (Mi,) int64 index arrays
    gt_volume: float | None = None
    meta: dict = field(default_factory=dict)
    # optional comparison meshes shipped with a case directory, keyed
    # "reference" / "result" / "implicit1" / ... -> (points, triangles)
    extra_meshes: dict = field(default_factory=dict)


def _append_contour(points: list, lines: list, xy: np.ndarray, z: float) -> None:
    """Register one closed contour (xy: (M,2)) on slice z."""
    base = sum(len(p) for p in points)
    pts = np.column_stack([xy, np.full(len(xy), float(z))])
    points.append(pts)
    lines.append(np.arange(base, base + len(pts), dtype=np.int64))


def _finish(name: str, points: list, lines: list, gt_volume, meta: dict) -> ContourDataset:
    return ContourDataset(name=name, points=np.vstack(points), lines=lines,
                          gt_volume=gt_volume, meta=meta)


def _circle_xy(r: float, n: int, jitter: float, rng: np.random.Generator) -> np.ndarray:
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    x = r * np.cos(ang) + rng.normal(0.0, jitter, n)
    y = r * np.sin(ang) + rng.normal(0.0, jitter, n)
    return np.column_stack([x, y])


def cylinder(n_slices: int = 21, radius: float = 10.0, height: float = 20.0,
             points_per_slice: int = 120, jitter: float = 0.0,
             seed: int = 0, name: str = "cylinder") -> ContourDataset:
    """Straight cylinder; ground truth volume = pi r^2 h."""
    rng = np.random.default_rng(seed)
    pts, lines = [], []
    zs = np.linspace(0.0, height, n_slices)
    for z in zs:
        _append_contour(pts, lines, _circle_xy(radius, points_per_slice, jitter, rng), z)
    return _finish(name, pts, lines, np.pi * radius ** 2 * height,
                   dict(n_slices=n_slices, radius=radius, height=height))


def tapered_tube(n_slices: int = 21, r0: float = 12.0, r1: float = 6.0,
                 height: float = 20.0, points_per_slice: int = 120,
                 jitter: float = 0.0, seed: int = 0,
                 name: str = "tapered_tube") -> ContourDataset:
    """Linearly tapered tube; ground truth = frustum volume."""
    rng = np.random.default_rng(seed)
    pts, lines = [], []
    zs = np.linspace(0.0, height, n_slices)
    for z in zs:
        r = r0 + (r1 - r0) * (z / height)
        _append_contour(pts, lines, _circle_xy(r, points_per_slice, jitter, rng), z)
    gt = np.pi * height * (r0 * r0 + r0 * r1 + r1 * r1) / 3.0
    return _finish(name, pts, lines, gt,
                   dict(n_slices=n_slices, r0=r0, r1=r1, height=height))


def y_bifurcation(trunk_slices: int = 8, branch_slices: int = 8, radius: float = 6.0,
                  trunk_height: float = 8.0, branch_height: float = 8.0,
                  split_offset: float = 6.0, points_per_slice: int = 120,
                  branch_radius_frac: float = 0.45,
                  jitter: float = 0.0, seed: int = 0,
                  name: str = "y_bifurcation") -> ContourDataset:
    """Trunk splitting into two branches: upper slices carry two contours
    (branch exercise for BranchMethod). No analytic volume.

    The two child contours must be *disjoint* on every slice, otherwise the
    input stack is geometrically ill-posed (two solids cannot occupy the same
    area of one section) and no stitching algorithm can produce a closed
    surface there.  The first branch slice therefore places the children
    tangent to the parent wall (``off = radius - r_branch``) and later slices
    splay outwards by up to ``split_offset``.
    """
    rng = np.random.default_rng(seed)
    pts, lines = [], []
    for z in np.linspace(0.0, trunk_height, trunk_slices, endpoint=False):
        _append_contour(pts, lines, _circle_xy(radius, points_per_slice, jitter, rng), z)
    r_branch = branch_radius_frac * radius
    off0 = radius - r_branch                      # tangent to the trunk wall
    zs = np.linspace(trunk_height, trunk_height + branch_height, branch_slices)
    for i, z in enumerate(zs):
        frac = (i + 1) / branch_slices
        off = off0 + split_offset * frac
        for sign in (-1.0, +1.0):
            xy = _circle_xy(r_branch, points_per_slice, jitter, rng)
            xy[:, 0] += sign * off
            _append_contour(pts, lines, xy, z)
    return _finish(name, pts, lines, None,
                   dict(trunk_slices=trunk_slices, branch_slices=branch_slices,
                        branch_radius=r_branch, split_offset=split_offset))


def keyhole_contour_xy(radius: float, n: int, neck_gap: float,
                       rng: np.random.Generator) -> np.ndarray:
    """One closed contour with a self-touching keyhole notch (exercises
    FixKeyholes): an outer circle with a narrow inward double radial line."""
    half_wedge = 0.012                     # wedge half-angle (rad)
    a1, a2 = np.pi / 2 - half_wedge, np.pi / 2 + half_wedge
    r_in = 0.8
    arc = _circle_xy(radius, int(n * 0.8), 0.0, rng)
    # keep only the long way around: drop arc points inside the wedge
    ang = np.arctan2(arc[:, 1], arc[:, 0])
    keep = (ang < a1) | (ang > a2)
    arc = arc[keep]
    t_in = np.linspace(radius, r_in, 24)
    t_out = np.linspace(r_in, radius, 24)
    # two nearly-coincident radial lines separated by neck_gap at the outer rim
    dtheta = neck_gap / max(radius, 1e-9)
    line_a = np.column_stack([t_in * np.cos(a1), t_in * np.sin(a1)])
    small = _circle_xy(r_in, 8, 0.0, rng)
    small = small[np.arctan2(small[:, 1], small[:, 0]) >= a1 - dtheta]
    small = small[np.arctan2(small[:, 1], small[:, 0]) <= a2 + dtheta]
    line_b = np.column_stack([t_out * np.cos(a2 + dtheta), t_out * np.sin(a2 + dtheta)])
    xy = np.vstack([arc, line_a, small, line_b])
    if rng is not None and neck_gap == 0.0:  # pragma: no cover - defensive
        xy = xy + rng.normal(0.0, 1e-6, xy.shape)
    return xy


def keyhole_stack(n_slices: int = 11, radius: float = 10.0, height: float = 10.0,
                  points_per_slice: int = 160, neck_gap: float = 5e-4,
                  jitter: float = 0.0, seed: int = 0,
                  name: str = "keyhole_stack") -> ContourDataset:
    """Cylinder stack whose middle slice contains a keyhole defect."""
    rng = np.random.default_rng(seed)
    pts, lines = [], []
    zs = np.linspace(0.0, height, n_slices)
    mid = n_slices // 2
    for i, z in enumerate(zs):
        if i == mid:
            xy = keyhole_contour_xy(radius, points_per_slice, neck_gap, rng)
        else:
            xy = _circle_xy(radius, points_per_slice, jitter, rng)
        _append_contour(pts, lines, xy, z)
    return _finish(name, pts, lines, None,
                   dict(n_slices=n_slices, radius=radius, neck_gap=neck_gap))


_BUILDERS = {}          # filled in at the end of the module


# --------------------------------------------------------------------------
# real contour files (examples/)
# --------------------------------------------------------------------------
# Supported on disk: the CAD polyline export used by cdVTKFunc fixtures
# (``POLYLINE: N`` header, N ``x,y,z`` lines, ``Sub End #`` terminator) as well as
# plain blank-line-separated vertex lists and ``x y z`` whitespace triples.
# Every non-coordinate line terminates the current contour, so headers and
# terminators need no special-casing.

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1")
CONTOUR_FILE_PATTERNS = ("*.txt", "*.dat", "*.csv", "*.xyz", "*.pts")


def _read_text(path) -> tuple[str, str]:
    raw = Path(path).read_bytes()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1"


def _coord(line: str):
    """Parse one coordinate line; ``None`` when the line is not a vertex."""
    parts = [p for p in re.split(r"[,\s]+", line.strip()) if p]
    if len(parts) < 2 or len(parts) > 3:
        return None
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return None
    return (vals[0], vals[1], vals[2] if len(vals) == 3 else 0.0)


def parse_contour_text(text: str) -> list:
    """Split a contour file into closed-ish polylines (list of (M,3) arrays)."""
    polys, cur = [], []
    for line in text.splitlines():
        c = _coord(line)
        if c is None:
            if len(cur) >= 1:
                polys.append(np.asarray(cur, dtype=np.float64))
            cur = []
        else:
            cur.append(c)
    if cur:
        polys.append(np.asarray(cur, dtype=np.float64))
    return polys


# --- GeoEAS-style variable tables (e.g. drill-hole section exports) --------
_VAR_RE = re.compile(r"^\s*(\d+)\s+VARIABLES\s*$", re.IGNORECASE)
_COLNAME_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*?)\s+([NC])\s+\d+\s+\d+\s*$")


def _looks_like_variables_table(text: str) -> bool:
    """A ``N VARIABLES`` header within the first 30 lines."""
    return any(_VAR_RE.match(ln) for ln in text[:4096].splitlines()[:30])


def _parse_variables_text(text: str) -> list:
    """Parse a ``N VARIABLES`` column table into contours.

    Header: one line ``<count>   VARIABLES`` followed by one definition line
    per column (``NAME TYPE width dec``), then rows of numbers.  The x/y/z
    columns are located by name (EAST/X, NORTH/Y, RL/Z/ELEV); contours are
    delimited by the id column (``LAYER``/``ID``/...) when present, otherwise
    by changes in the elevation value.  Returns the same shape as
    :func:`parse_contour_text`.
    """
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines[:40]) if _VAR_RE.match(ln))
    cols: list[str] = []
    i = start + 1
    while i < len(lines):
        m = _COLNAME_RE.match(lines[i])
        if not m:
            break
        cols.append(m.group(1).strip().upper())
        i += 1
    if not cols:
        raise ValueError("variable table: no column definition lines found")

    def col_of(names: tuple) -> int | None:
        for k, c in enumerate(cols):
            if c in names:
                return k
        return None

    xi = col_of(("EAST", "X", "EASTING"))
    yi = col_of(("NORTH", "Y", "NORTHING"))
    zi = col_of(("RL", "Z", "ELEV", "ELEVATION"))
    idi = col_of(("LAYER", "ID", "POLY", "SEG", "SEGMENT"))
    if xi is None or yi is None or zi is None:
        raise ValueError(f"variable table: cannot identify x/y/z columns in {cols}")
    need = max(xi, yi, zi)

    buckets: dict = {}
    order: list = []
    for ln in lines[i:]:
        parts = ln.split()
        if len(parts) <= need:
            continue
        try:
            xyz = (float(parts[xi]), float(parts[yi]), float(parts[zi]))
        except ValueError:
            continue
        key = parts[idi] if idi is not None and idi < len(parts) else xyz[2]
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(xyz)

    return [np.asarray(buckets[k], dtype=np.float64) for k in order
            if len(buckets[k]) >= 3]


def _newell_normal(p: np.ndarray) -> tuple:
    """Newell normal (unnormalised, magnitude = 2*area) and polygon area."""
    q = p[:-1] if len(p) > 1 and np.allclose(p[0], p[-1]) else p
    if len(q) < 3:
        return np.zeros(3), 0.0
    nxt = np.roll(q, -1, axis=0)
    n = np.array([
        np.sum((q[:, 1] - nxt[:, 1]) * (q[:, 2] + nxt[:, 2])),
        np.sum((q[:, 2] - nxt[:, 2]) * (q[:, 0] + nxt[:, 0])),
        np.sum((q[:, 0] - nxt[:, 0]) * (q[:, 1] + nxt[:, 1])),
    ])
    return n, float(np.linalg.norm(n) / 2.0)


def _dedupe(p: np.ndarray, tol: float) -> tuple:
    """Drop the repeated closing vertex and coincident consecutive vertices."""
    q = p
    n_closing = 0
    if len(q) > 1 and np.linalg.norm(q[0] - q[-1]) <= tol:
        q = q[:-1]
        n_closing = 1
    if len(q) == 0:
        return q, n_closing, 0
    keep = [q[0]]
    n_dup = 0
    for row in q[1:]:
        if np.linalg.norm(row - keep[-1]) <= tol:
            n_dup += 1
            continue
        keep.append(row)
    return np.asarray(keep), n_closing, n_dup


def group_by_plane(polys: list, plane_tol: float | None = None,
                   angle_tol: float = 0.98) -> tuple:
    """Group contours into parallel planes and sort them along the normal.

    Returns ``(planes, normal, info)`` where ``planes`` is a list of
    ``(offset, [polys])`` sorted by ascending offset.  The common normal is the
    area-weighted Newell sum with the signs harmonised, so it works for
    arbitrary (e.g. vertical, oblique) section orientations -- not only for
    slices stacked along z.
    """
    if not polys:
        raise ValueError("no contours parsed")
    normals, areas = [], []
    for p in polys:
        n, a = _newell_normal(p)
        normals.append(n)
        areas.append(a)
    normals = np.asarray(normals)
    areas = np.asarray(areas)

    acc = np.zeros(3)
    for n, a in zip(normals, areas):
        if a <= 0:
            continue
        acc += n if (acc @ n) >= 0 else -n
    if np.linalg.norm(acc) < 1e-12:            # all contours degenerate
        acc = np.array([0.0, 0.0, 1.0])
    normal = acc / np.linalg.norm(acc)

    unit = np.array([n / np.linalg.norm(n) for n in normals if np.linalg.norm(n) > 0])
    consistency = float((np.abs(unit @ normal) > angle_tol).mean()) if len(unit) else 0.0

    allp = np.vstack(polys)
    diag = float(np.linalg.norm(allp.max(0) - allp.min(0)))
    tol = plane_tol if plane_tol is not None else max(1e-6, 1e-4 * diag)

    offs = np.array([float(p.mean(axis=0) @ normal) for p in polys])
    order = np.argsort(offs, kind="stable")
    groups: list[list[int]] = []
    ref = None
    for idx in order:
        if ref is None or abs(offs[idx] - ref) > tol:
            groups.append([idx])
            ref = offs[idx]
        else:
            groups[-1].append(idx)
            ref = float(np.mean(offs[groups[-1]]))

    planes = [(float(np.mean(offs[g])), [polys[i] for i in g]) for g in groups]
    gaps = np.diff([p[0] for p in planes])
    info = dict(n_contours=len(polys), n_slices=len(planes),
                slice_normal=[round(float(v), 6) for v in normal],
                plane_tol=float(tol), normal_consistency=consistency,
                slice_spacing=float(np.median(gaps)) if len(gaps) else 0.0,
                slice_spacing_uniform=bool(len(gaps) == 0 or
                                           np.allclose(gaps, gaps[0], atol=max(tol, 1e-9))),
                extent=[round(float(v), 6) for v in (allp.max(0) - allp.min(0))])
    return planes, normal, info


def contour_file(path=None, name: str | None = None,
                 plane_tol: float | None = None, clean_input: bool = True,
                 angle_tol: float = 0.98) -> ContourDataset:
    """Load one real contour stack from disk (the ``examples/`` drop-in format).

    ``clean_input`` applies the S1-style input conditioning and records what it
    changed: the repeated closing vertex, coincident consecutive vertices, and
    contours with fewer than three distinct points (which carry no area and
    cannot bound a strip).
    """
    path = Path(path or os.environ.get("ORESECSTITCH_CONTOUR_FILE", ""))
    if not path.is_file():
        raise FileNotFoundError(f"contour file not found: {path}")
    text, enc = _read_text(path)
    if _looks_like_variables_table(text):
        polys = _parse_variables_text(text)
    else:
        polys = parse_contour_text(text)
    if not polys:
        raise ValueError(f"no contours parsed from {path}")

    stats = dict(n_parsed=len(polys), n_points_parsed=int(sum(len(p) for p in polys)),
                 closing_vertices_removed=0, duplicate_vertices_removed=0,
                 degenerate_contours_removed=0)
    if clean_input:
        kept = []
        allp = np.vstack(polys)
        tol = max(1e-9, 1e-9 * float(np.linalg.norm(allp.max(0) - allp.min(0))))
        for p in polys:
            q, n_close, n_dup = _dedupe(p, tol)
            stats["closing_vertices_removed"] += n_close
            stats["duplicate_vertices_removed"] += n_dup
            if len(np.unique(np.round(q, 9), axis=0)) < 3:
                stats["degenerate_contours_removed"] += 1
                continue
            kept.append(q)
        if not kept:
            raise ValueError(f"{path}: every contour is degenerate")
        polys = kept

    planes, normal, info = group_by_plane(polys, plane_tol=plane_tol, angle_tol=angle_tol)
    if info["normal_consistency"] < 0.9:
        print(f"WARNING {path}: only {info['normal_consistency']:.0%} of contours share "
              "the common normal; the stack is probably not a parallel section set",
              file=sys.stderr)

    pts, lines = [], []
    for _, group in planes:
        for poly in group:
            base = sum(len(q) for q in pts)
            pts.append(poly)
            lines.append(np.arange(base, base + len(poly), dtype=np.int64))

    meta = dict(source=str(path), encoding=enc, **stats, **info)
    meta["n_lines"] = len(lines)
    meta["n_points"] = int(sum(len(q) for q in pts))
    return ContourDataset(name=name or path.stem, points=np.vstack(pts),
                          lines=lines, gt_volume=None, meta=meta)


def iter_contour_files(directory, patterns=CONTOUR_FILE_PATTERNS) -> list:
    """Every contour file under ``directory`` (sorted, recursive)."""
    root = Path(directory)
    if not root.is_dir():
        return []
    hits = set()
    for pat in patterns:
        hits.update(root.rglob(pat))
    return sorted(p for p in hits if p.is_file())


_NAMED_MESHES = {"reference.obj": "reference", "result.obj": "result"}


def contour_case(directory=None, name: str | None = None, prefix: str = "case",
                 plane_tol: float | None = None, clean_input: bool = True,
                 angle_tol: float = 0.98) -> ContourDataset:
    """Load one case directory (``examples/<group>/<case>/`` drop-in format).

    Each case is a sub-directory holding ``input.txt`` (the contour stack)
    plus optional comparison meshes: ``reference.obj`` (expert-built model),
    ``result.obj`` (reference output of this method) and ``implicit*.obj``
    (implicit-baseline outputs).  The bundled cases contain only
    ``input.txt``; optional meshes are loaded with
    :func:`oresecstitch.metrics.load_obj` when present and attached to
    ``extra_meshes`` keyed ``reference`` / ``result`` / ``implicit1`` /
    ``implicit2`` ... (numerical suffixes preserved, sorted order).
    """
    from oresecstitch.metrics import load_obj      # lazy: avoid import cycle

    root = Path(directory or os.environ.get("ORESECSTITCH_CASE_DIR", ""))
    if not root.is_dir():
        raise FileNotFoundError(f"case directory not found: {root}")
    input_txt = next((p for p in sorted(root.glob("*.txt"))
                      if p.stem.lower() == "input"), None)
    if input_txt is None:
        raise FileNotFoundError(f"{root}: no input.txt contour stack")
    stem = re.sub(r"[^0-9A-Za-z_.-]+", "-", root.name).strip("-")
    ds = contour_file(input_txt, name=f"{prefix}_{stem}",
                      plane_tol=plane_tol, clean_input=clean_input,
                      angle_tol=angle_tol)
    ds.meta["source"] = str(root)
    meshes: dict = {}
    for p in sorted(root.glob("*.obj")):
        key = _NAMED_MESHES.get(p.name.lower())
        if key is None:
            m = re.fullmatch(r"implicit(\d*)\.obj", p.name.lower())
            if m:
                key = f"implicit{m.group(1) or '1'}"
        if key is None:
            continue
        meshes[key] = load_obj(p)
    ds.extra_meshes = meshes
    ds.meta["meshes"] = {k: {"n_points": int(len(v[0])),
                             "n_triangles": int(len(v[1]))}
                         for k, v in meshes.items()}
    return ds


def build_dataset(spec: dict) -> ContourDataset:
    """Build a dataset from an experiments.yaml dataset spec (dict with 'kind')."""
    spec = dict(spec)
    kind = spec.pop("kind")
    if kind not in _BUILDERS:
        raise KeyError(f"unknown dataset kind '{kind}'; known: {sorted(_BUILDERS)}")
    return _BUILDERS[kind](**spec)


_BUILDERS.update({
    "cylinder": cylinder,
    "tapered_tube": tapered_tube,
    "y_bifurcation": y_bifurcation,
    "keyhole_stack": keyhole_stack,
    "contour_file": contour_file,
    "contour_case": contour_case,
})
