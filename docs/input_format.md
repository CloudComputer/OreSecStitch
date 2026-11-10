# Input contour format

OreSecStitch reads a stack of planar contours from a plain text file. The
loader is deliberately permissive: any line that is not a coordinate triple is
treated as a contour separator, so CAD headers and terminators need no special
handling.

## Accepted layouts

### 1. CAD polyline export (used by the bundled cases)

```
POLYLINE: 6
266739.02127158,291722.301332192,1230.00002732792
266737.083909549,291687.307864037,1230.00000176923
...
Sub End #
POLYLINE: 11
...
Sub End #
```

- The `POLYLINE: N` line and the `Sub End #` line are both non-coordinate
  lines and therefore terminate the current contour. `N` is the number of
  following coordinate lines, but the loader does not require it to be exact.
- The original CAD export used a localized header of the same shape. The
  bundled files use the English `POLYLINE: N`; the parser ignores both forms
  because they are non-coordinate lines.

### 2. Blank-line-separated vertex lists

```
835.0,-715.0,1206.4
1247.2,-352.7,1379.4
...

0.0,0.0,25.0
...
```

### 3. Whitespace-separated triples

```
835.0 -715.0 1206.4
1247.2 -352.7 1379.4
...
```

Two-value lines (`x,y` or `x y`) are also accepted; the missing `z` is set to
`0.0`.

## Parsing rules

- A coordinate line has 2 or 3 numeric values separated by commas, spaces, or
  a mixture of both (for example `x,y,z`, `x y z`, or `x, y, z`).
- Any line that cannot be parsed as a coordinate line ends the current
  contour. Empty lines, comments, headers and terminators all do this.
- A contour needs at least 3 distinct vertices. Contours with fewer vertices
  carry no area and are removed; the removal is counted in the dataset
  metadata.
- A repeated closing vertex (last point equal to the first point within a
  tolerance) is removed automatically. The native algorithm closes the
  polyline internally.
- Consecutive duplicate vertices are removed and counted.
- Multiple contours on the same slice are allowed. They must be **disjoint**
  on that slice; two solids cannot occupy the same area of one section, and
  overlapping contours make a closed surface geometrically ill-posed.

## Encoding

The loader tries the following encodings in order:

1. `utf-8-sig`
2. `utf-8`
3. `gb18030`
4. `gbk`
5. `latin-1`

The bundled `input.txt` files are UTF-8 without BOM. Legacy GB18030/GBK CAD
exports are read correctly without conversion.

## Plane grouping

Contours are not assumed to be stacked along the z axis. For every contour the
loader computes the area-weighted Newell normal, harmonises the normal signs,
and groups contours whose plane offsets agree within a tolerance derived from
the dataset bounding-box diagonal. The groups are then sorted by ascending
offset along the common normal. This handles vertical and oblique section
stacks.

If fewer than 90% of the contours share the common normal, the loader prints a
warning to stderr; that usually means the file is not a parallel section set.

## Input cleaning statistics

`dataset.meta` records what the loader changed:

| Key | Meaning |
|---|---|
| `n_parsed` | Contours found before cleaning |
| `n_points_parsed` | Vertices found before cleaning |
| `closing_vertices_removed` | Repeated closing vertices removed |
| `duplicate_vertices_removed` | Consecutive duplicate vertices removed |
| `degenerate_contours_removed` | Contours with fewer than 3 distinct vertices |
| `n_lines` | Contours after cleaning |
| `n_points` | Vertices after cleaning |
| `n_slices` | Number of parallel planes |
| `slice_normal` | Common unit normal |
| `plane_tol` | Plane-grouping tolerance |
| `normal_consistency` | Fraction of contours aligned with the common normal |
| `slice_spacing` | Median spacing between planes |
| `slice_spacing_uniform` | Whether all gaps are equal within tolerance |
| `extent` | Bounding-box extent of the input points |

The same metadata is written to `output/results/_datasets.json` by the
experiment driver.

## Units

Coordinates are in model units. The shipped mine datasets use metres; the
large easting/northing values are original survey coordinates and are not
recentred. All distances, volumes, and tolerances reported by the code are in
the same model units (metres for the shipped data).

## Quick check

```python
from drivers.oresecstitch_data import contour_case

ds = contour_case("examples/mine_cases/case01")
print(ds.meta["n_lines"], ds.meta["n_points"], ds.meta["n_slices"])
print(ds.meta["slice_spacing"], ds.meta["extent"])
print(ds.points.shape, len(ds.lines))
```

`ds.points` is an `(N, 3)` float64 array; `ds.lines` is a list of 1-D int64
arrays of point indices, one per contour.
