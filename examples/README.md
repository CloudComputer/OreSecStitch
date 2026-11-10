# Example contour stacks

This folder contains two example contour stacks:

```
examples/mine_cases/
|-- case01/input.txt
-- case02/input.txt
```

Only `input.txt` is distributed; no reconstructed meshes are included. Run
`python reproduce.py` at the repository root to generate meshes and metrics for
both cases.

## Case statistics

| Case | Contours | Slices | Points | Slice spacing | Extent (m) |
|---|---:|---:|---:|---:|---|
| `case01` | 33 | 17 | 583 | ~10 m | 612 x 394 x 160 |
| `case02` | 18 | 11 | 275 | ~10 m | 290 x 82 x 100 |

Coordinates are in metres and keep their original survey offsets. No
translation or scaling is applied.

## File format

Each file is a sequence of contours:

```text
POLYLINE: 6
x1 y1 z1
x2 y2 z2
...
x6 y6 z6
Sub End #
```

- `POLYLINE: N` is followed by exactly `N` coordinate lines.
- `Sub End #` terminates a contour.
- Blank lines separate contours and are ignored.
- Coordinates are `x y z`; two-column lines `x y` are read with `z = 0`.
- Files are decoded as UTF-8 (with or without BOM), then GB18030/GBK, then
  Latin-1.

See [`../docs/input_format.md`](../docs/input_format.md) for the full reader
contract.

## Loading and reconstructing

```python
from drivers.oresecstitch_data import contour_case
from oresecstitch import reconstruct, StitchParams, metrics

for case in ("case01", "case02"):
    ds = contour_case(f"examples/mine_cases/{case}")
    result = reconstruct(ds.points, ds.lines, StitchParams(
        branch_method="point_distance",
        triangulation_cost="perimeter",
        end_capping="smooth",
    ))
    result.mesh.save_obj(f"{case}.obj")
    print(case, len(ds.lines), result.mesh.n_triangles,
          metrics.volume(result.mesh.points, result.mesh.triangles))
```

To process every case directory in one go:

```bat
python reproduce.py
```

The script writes `output/results/reproduce.csv`,
`output/results/reproduce.json`, and one OBJ per case under `output/meshes/`.
