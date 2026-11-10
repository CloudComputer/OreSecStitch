# OreSecStitch

OreSecStitch reconstructs a closed triangulated surface from a stack of planar
contours, such as geological cross-sections of an orebody. The package provides
a Python API, contour loaders, geometry metrics, and a small batch/experiment
driver. The reconstruction core is exposed as a Windows x64 extension, with the
required runtime libraries bundled in the repository, so no external
installation is needed.

## Features

- Planar contour stacks with arbitrary slice orientation (vertical or oblique),
  grouped by the area-weighted Newell normal.
- Multiple contours per slice and automatic branch splitting.
- End capping modes: `none`, `smooth`, and `straight`.
- Branch strategies: `point_distance` and `triangulation_region`.
- Triangulation cost: `perimeter` or `area`.
- CGAL triangulation is enabled by default.
- Geometry metrics: signed volume, surface area, and sampled Hausdorff/HD95
  distances.
- OBJ and PLY export.
- Batch runner that reconstructs every bundled case and writes CSV/JSON
  summaries, plus a configurable parameter-study matrix.

## Requirements

### Platform

- Windows 10 or 11, x64.
- Microsoft Visual C++ 2015-2022 Redistributable (x64).

### Python

- Python 3.10 or newer.
- The bundled extension is built for **CPython 3.12 x64**; it will not load on
  other Python versions or on 32-bit interpreters.

### Dependencies

| Package | Version | Used by |
|---|---|---|
| NumPy | >= 1.24 | core |
| SciPy | >= 1.10 | geometry metrics |
| PyYAML | >= 6.0 | experiment matrix |
| pytest | >= 7 | tests |

## Installation

```bat
git clone https://github.com/CloudComputer/OreSecStitch.git
cd OreSecStitch
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -c "import oresecstitch; print(oresecstitch.__version__)"
```

The last command prints `1.0.0`. The native extension is loaded from
`oresecstitch/oresecstitch_native*.pyd`, and the runtime DLLs are loaded from
`oresecstitch/dlls/`.

If the import fails with `DLL load failed`, install the VC++ 2015-2022
Redistributable (x64) and check that `oresecstitch/dlls/` contains
`cdVTKFunc.dll`, `cdCGALFunc.dll`, `gmp-10.dll`, `gmpxx-4.dll`, and
`mpfr-6.dll`.

## Usage

### Load a contour stack

```python
from drivers.oresecstitch_data import contour_case

ds = contour_case("examples/mine_cases/case01")
print(ds.meta["n_lines"], ds.meta["n_slices"], ds.meta["slice_spacing"])
print(ds.points.shape, len(ds.lines))
```

`ds.points` is an `(N, 3)` float64 array. `ds.lines` is a list of 1-D int64
index arrays, one per contour; each polyline is closed internally by the
reconstruction.

### Reconstruct a surface

```python
from oresecstitch import StitchParams, reconstruct

result = reconstruct(ds.points, ds.lines, StitchParams(
    branch_method="point_distance",
    triangulation_cost="perimeter",
    end_capping="smooth",
))

print(result.mesh.n_points, result.mesh.n_triangles)
print(result.time_s)
```

`StitchParams` accepted values:

| Field | Values | Default |
|---|---|---|
| `end_capping` | `none`, `smooth`, `straight` | native default |
| `branch_method` | `point_distance`, `triangulation_region` | native default |
| `triangulation_cost` | `perimeter`, `area` | native default |
| `greedy` | `True`, `False` | `True` |
| `use_cgal` | `True`, `False` | `True` |
| `contour_densify` | `True`, `False` | native default |
| `filter_small_branches` | `True`, `False` | native default |
| `default_slice_thickness` | float | native default |

### Export a mesh

```python
result.mesh.save_obj("case01.obj")
result.mesh.save_ply("case01.ply")
```

### Compute geometry metrics

```python
from oresecstitch import metrics

pts, tris = result.mesh.points, result.mesh.triangles
print(metrics.volume(pts, tris))          # signed volume
print(metrics.surface_area(pts, tris))    # total area
print(metrics.distance_metrics(pts, tris, pts, tris))   # hausdorff / hd95
```

### Batch run all bundled cases

```bat
python reproduce.py
python reproduce.py --repeat 5 --warmup 2
python reproduce.py --no-mesh
```

Outputs are written to `output/results/reproduce.csv`,
`output/results/reproduce.json`, and one OBJ per case under
`output/meshes/`.

### Parameter studies

`experiments/experiments.yaml` defines a matrix of parameter combinations and
datasets. Any sub-directory of `examples/mine_cases/` that contains `input.txt`
is picked up automatically.

```bat
python experiments\run_experiments.py --list
python experiments\run_experiments.py
python experiments\run_experiments.py --only end_capping_study
python experiments\run_experiments.py --quick
```

Results are written to `output/results/<experiment>.csv` and `.json`, with the
generated meshes under `output/meshes/<experiment>/`.

### Use your own contours

Put a case directory with an `input.txt` file under `examples/mine_cases/`, or
pass any path to `contour_case()`. The accepted file layouts are documented in
[`docs/input_format.md`](docs/input_format.md). In short:

```text
POLYLINE: 6
x1 y1 z1
...
x6 y6 z6
Sub End #
```

Blank-line-separated vertex lists, whitespace-separated triples, and two-column
`x y` lines (`z = 0`) are also accepted.

## Bundled data

| Case | Contours | Slices | Points | Slice spacing | Extent (m) |
|---|---:|---:|---:|---:|---|
| `mine_cases/case01` | 33 | 17 | 583 | ~10 m | 612 x 394 x 160 |
| `mine_cases/case02` | 18 | 11 | 275 | ~10 m | 290 x 82 x 100 |

Coordinates are in metres and keep their original survey offsets; no
translation or scaling is applied. Only input contours are distributed. See
[`examples/README.md`](examples/README.md).

## Project structure

```
OreSecStitch/
|-- README.md
|-- LICENSE                          GPL-3.0-only
|-- CITATION.cff
|-- requirements.txt
|-- pyproject.toml
|-- CMakeLists.txt                   C++ binding build definition
|-- reproduce.py                     batch reconstruction of all cases
|-- oresecstitch/                    Python package
|   |-- api.py                       StitchParams / reconstruct / SurfaceMesh
|   |-- metrics.py                   volume, area, surface distances
|   |-- native.py                    loads the compiled extension
|   |-- oresecstitch_native*.pyd     prebuilt Windows x64 extension
|   -- dlls/                         bundled runtime DLLs
|-- drivers/                         contour loaders and synthetic datasets
|-- cpp/                             pybind11 binding source
|-- examples/
|   |-- README.md
|   -- mine_cases/
|       |-- case01/input.txt
|       -- case02/input.txt
|-- experiments/
|   |-- experiments.yaml
|   -- run_experiments.py
|-- tests/
|   |-- test_cases_smoke.py
|   -- test_metrics.py
-- docs/
    -- input_format.md
```

## Known limitations

- The bundled extension only runs on Windows x64 with CPython 3.12.
- `smooth` end capping extends the surface beyond the first and last contour,
  which increases the enclosed volume.
- Contours on the same slice must be disjoint; overlapping contours make the
  surface ill-defined.

## License

Released under the **GNU General Public License v3.0 only** (`GPL-3.0-only`).
See [`LICENSE`](LICENSE).

## Contact

Issues and questions: <https://github.com/CloudComputer/OreSecStitch/issues>.
