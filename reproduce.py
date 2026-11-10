"""Reconstruct every bundled case and write meshes plus a metrics summary.

Usage (from the repository root)::

    python reproduce.py
    python reproduce.py --repeat 5 --warmup 2
    python reproduce.py --no-mesh

Outputs:
    output/results/reproduce.csv
    output/results/reproduce.json
    output/meshes/<case>.obj          (unless --no-mesh)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from oresecstitch import __version__, api, metrics      # noqa: E402
from drivers.oresecstitch_data import contour_case      # noqa: E402

CASES_DIR = REPO / "examples" / "mine_cases"
OUT_RESULTS = REPO / "output" / "results"
OUT_MESHES = REPO / "output" / "meshes"

# Default settings for the bundled cases.
REFERENCE_PARAMS = dict(
    branch_method="point_distance",
    triangulation_cost="perimeter",
    end_capping="smooth",
    use_cgal=True,
    filter_small_branches=False,
    contour_densify=False,
    greedy=True,
)


def discover_cases() -> list[Path]:
    if not CASES_DIR.is_dir():
        return []
    return sorted(p for p in CASES_DIR.iterdir()
                  if p.is_dir() and (p / "input.txt").is_file())


def run_case(case_dir: Path, warmup: int, repeat: int,
             save_mesh: bool) -> dict:
    ds = contour_case(case_dir, name=case_dir.name)
    params = api.StitchParams(**REFERENCE_PARAMS)

    for _ in range(max(0, warmup)):
        api.reconstruct(ds.points, ds.lines, params)

    times: list[float] = []
    result = None
    for _ in range(max(1, repeat)):
        t0 = time.perf_counter()
        result = api.reconstruct(ds.points, ds.lines, params)
        times.append(time.perf_counter() - t0)

    pts, tris = result.mesh.points, result.mesh.triangles

    row = {
        "case": case_dir.name,
        "status": "ok",
        "error": "",
        "n_contours_in": len(ds.lines),
        "n_points_in": int(len(ds.points)),
        "n_points": int(len(pts)),
        "n_triangles": int(len(tris)),
        "volume": metrics.volume(pts, tris),
        "surface_area": metrics.surface_area(pts, tris),
        "time_s": float(np.median(times)),
        "time_std_s": float(np.std(times)),
        "time_min_s": float(np.min(times)),
        "repeats": len(times),
        "oresecstitch": __version__,
    }
    for key, value in REFERENCE_PARAMS.items():
        row[f"param.{key}"] = value

    if save_mesh:
        mesh_path = OUT_MESHES / f"{case_dir.name}.obj"
        result.mesh.save_obj(mesh_path)
        row["mesh_path"] = str(mesh_path.relative_to(REPO))
    else:
        row["mesh_path"] = ""
    return row


def write_outputs(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with open(out_dir / "reproduce.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, restval="")
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "reproduce.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeat", type=int, default=3,
                    help="timed runs per case (median reported)")
    ap.add_argument("--warmup", type=int, default=1,
                    help="untimed runs before timing")
    ap.add_argument("--no-mesh", action="store_true", help="skip OBJ export")
    ap.add_argument("--out", default=str(OUT_RESULTS),
                    help="directory for reproduce.csv / reproduce.json")
    args = ap.parse_args()

    cases = discover_cases()
    if not cases:
        print(f"No case directories with input.txt under {CASES_DIR}")
        return 2

    rows: list[dict] = []
    for case_dir in cases:
        try:
            row = run_case(case_dir, args.warmup, args.repeat,
                           save_mesh=not args.no_mesh)
        except Exception as exc:                       # noqa: BLE001
            row = {"case": case_dir.name, "status": "error",
                   "error": f"{type(exc).__name__}: {exc}"[:500]}
        rows.append(row)
        if row["status"] == "ok":
            print(f"[{row['case']}] tris={row['n_triangles']} "
                  f"volume={row['volume']:.4g} area={row['surface_area']:.4g} "
                  f"time={row['time_s']:.3f}s")
        else:
            print(f"[{row['case']}] FAILED: {row['error']}")

    write_outputs(rows, Path(args.out))
    print(f"Wrote {args.out}/reproduce.csv and reproduce.json")
    return 0 if all(r["status"] == "ok" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
