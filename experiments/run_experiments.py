"""Run the OreSecStitch experiment matrix (experiments.yaml).

Usage (from the repository root):
    python experiments/run_experiments.py              # full matrix
    python experiments/run_experiments.py --quick      # first dataset x first combo
    python experiments/run_experiments.py --only dp_cost
    python experiments/run_experiments.py --list       # show the resolved matrix
    python experiments/run_experiments.py --datasets mine_cases      # the two cases

Real data: two example case directories are provided under
``examples/mine_cases/``.  A dataset spec with ``kind: contour_case`` and a
``dir`` is expanded into one dataset per case sub-directory; dropping another
case directory into that folder and re-running is enough -- no YAML edit needed.

Outputs:
    output/results/<exp>.csv         one row per (dataset, parameter combo)
    output/results/<exp>.json        same rows with full parameter values
    output/results/_run_meta.json    environment / versions / repeats
    output/meshes/<exp>/<dataset>_<combo>.obj
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import platform
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from oresecstitch import __version__, api, metrics, native     # noqa: E402
from drivers import oresecstitch_data as data                  # noqa: E402

OUT = REPO / "output" / "results"
MESH_DIR = REPO / "output" / "meshes"
CFG_PATH = REPO / "experiments" / "experiments.yaml"

# Extra spec keys that select files rather than being passed to the builder.
FILE_SPEC_KEYS = ("dir", "glob")


def _jsonable(obj):
    """Recursively convert numpy / Path values so json.dump accepts them."""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def _combo_slug(combo: dict, max_len: int = 110) -> str:
    """Deterministic file-safe slug for one experiment combo, used to name
    the exported OBJ files by parameter value."""
    parts = []
    for k in sorted(combo):
        s = re.sub(r"[^0-9A-Za-z_.-]+", "-", str(combo[k])).strip("-")
        parts.append(f"{k}-{s}")
    slug = "_".join(parts) or "default"
    if len(slug) > max_len:
        slug = slug[:max_len] + "-" + hashlib.md5(slug.encode()).hexdigest()[:8]
    return slug


# --------------------------------------------------------------------------
# dataset resolution (synthetic builders + examples/ auto-discovery)
# --------------------------------------------------------------------------
def resolve_datasets(cfg: dict) -> tuple[dict, dict]:
    """Expand ``dir``/``glob`` dataset specs into one dataset per file.

    Returns ``(specs, aliases)``: ``specs`` maps a concrete dataset name to its
    builder kwargs, ``aliases`` maps each YAML name to the list of concrete
    names it expands into (1:1 for ordinary datasets).
    """
    specs: dict[str, dict] = {}
    aliases: dict[str, list[str]] = {}
    taken: set[str] = set()

    for name, spec in cfg.items():
        spec = dict(spec)
        if spec.get("kind") == "contour_file" and spec.get("dir"):
            root = Path(spec["dir"])
            if not root.is_absolute():
                root = REPO / root
            patterns = spec.get("glob") or list(data.CONTOUR_FILE_PATTERNS)
            if isinstance(patterns, str):
                patterns = [patterns]
            files = data.iter_contour_files(root, patterns)
            keys: list[str] = []
            for f in files:
                key = re.sub(r"[^0-9A-Za-z_.-]+", "-", f.stem)
                if not key or key in taken:
                    key = f"{name}_{key or 'file'}"
                while key in taken:                       # pathological duplicates
                    key += "_"
                opts = {k: v for k, v in spec.items() if k not in FILE_SPEC_KEYS
                        and k != "kind"}
                specs[key] = dict(kind="contour_file", path=str(f), name=key, **opts)
                taken.add(key)
                keys.append(key)
            aliases[name] = keys
            if not keys:
                print(f"[datasets] {name}: no contour files under {root} "
                      f"(patterns={patterns}) -- experiments using it will be skipped")
        elif spec.get("kind") == "contour_case" and spec.get("dir"):
            root = Path(spec["dir"])
            if not root.is_absolute():
                root = REPO / root
            prefix = re.sub(r"[^0-9A-Za-z_.-]+", "-", str(spec.get("prefix") or name))
            keys = []
            for sub in sorted(p for p in root.iterdir() if p.is_dir()):
                if not list(sub.glob("input.txt")):
                    continue
                key = f"{prefix}_{re.sub(r'[^0-9A-Za-z_.-]+', '-', sub.name)}"
                while key in taken:
                    key += "_"
                specs[key] = dict(kind="contour_case", directory=str(sub), name=key)
                taken.add(key)
                keys.append(key)
            aliases[name] = keys
            if not keys:
                print(f"[datasets] {name}: no case directories with input.txt "
                      f"under {root} -- experiments using it will be skipped")
        elif spec.get("kind") == "group":
            aliases[name] = list(spec.get("datasets") or [])
        else:
            specs[name] = spec
            taken.add(name)
            aliases[name] = [name]

    # expand ``group`` datasets one level (member groups first, then leaves)
    for name, spec in cfg.items():
        if isinstance(spec, dict) and spec.get("kind") == "group":
            flat: list[str] = []
            for member in aliases[name]:
                flat.extend(aliases.get(member, [member]))
            seen: set[str] = set()
            aliases[name] = [n for n in flat if not (n in seen or seen.add(n))]
    return specs, aliases


def expand_dataset_names(requested, aliases) -> list[str]:
    names: list[str] = []
    for r in requested:
        if r not in aliases:
            raise KeyError(f"dataset '{r}' is not defined in experiments.yaml "
                           f"(known groups: {sorted(aliases)})")
        names.extend(aliases[r])
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def build_combos(exp: dict) -> list[dict]:
    grid = exp.get("grid") or {}
    keys = list(grid.keys())
    if not keys:
        return [{}]
    return [dict(zip(keys, vals))
            for vals in itertools.product(*(grid[k] for k in keys))]


# --------------------------------------------------------------------------
# one reconstruction
# --------------------------------------------------------------------------
def run_combo(ds, combo: dict, warmup: int, repeat: int):
    """Reconstruct once after warm-up, then ``repeat`` timed runs.

    Returns ``(result, times)`` where ``times`` are wall-clock seconds of the
    timed runs (the native call plus the numpy hand-off).
    """
    for _ in range(max(0, warmup)):
        api.reconstruct(ds.points, ds.lines, **combo)
    times: list[float] = []
    result = None
    for _ in range(max(1, repeat)):
        t0 = time.perf_counter()
        result = api.reconstruct(ds.points, ds.lines, **combo)
        times.append(time.perf_counter() - t0)
    return result, times


def evaluate_row(ds, name: str, result, times: list[float], combo: dict) -> dict:
    pts, tris = result.mesh.points, result.mesh.triangles
    row = {
        "dataset": name,
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
        "status": "ok",
        "error": "",
    }
    if ds.gt_volume:
        row["gt_volume"] = float(ds.gt_volume)
        row["volume_rel_err"] = metrics.relative_volume_error(row["volume"], ds.gt_volume)
    # comparison meshes shipped with the case directory: distances from this
    # reconstruction to each mesh, plus each mesh's volume
    extra = getattr(ds, "extra_meshes", {}) or {}
    for mesh_key, tag in (("reference", "ref"), ("result", "gold")):
        mesh = extra.get(mesh_key)
        if mesh is None:
            continue
        rp, rt = mesh
        dm = metrics.distance_metrics(pts, tris, rp, rt)
        row[f"{tag}_d_hausdorff"] = dm["hausdorff"]
        row[f"{tag}_d_h95"] = dm["hd95"]
        row[f"{tag}_d_mean"] = dm["mean_distance"]
        row[f"{tag}_volume"] = metrics.volume(rp, rt)
        # OBJ exports may carry inward normals, so compare |V| and take the
        # reference volume magnitude for the relative error.
        row[f"{tag}_volume_rel_err"] = metrics.relative_volume_error(
            abs(row["volume"]), abs(row[f"{tag}_volume"]))
        row[f"{tag}_n_triangles"] = int(len(rt))
    imp_keys = sorted(k for k in extra if k.startswith("implicit"))
    for key in imp_keys:
        ip, it = extra[key]
        dm = metrics.distance_metrics(pts, tris, ip, it)
        row[f"{key}_d_hausdorff"] = dm["hausdorff"]
        row[f"{key}_d_h95"] = dm["hd95"]
        row[f"{key}_d_mean"] = dm["mean_distance"]
        row[f"{key}_n_triangles"] = int(len(it))
        row[f"{key}_volume"] = metrics.volume(ip, it)
    for a, b in itertools.combinations(imp_keys, 2):
        dm = metrics.distance_metrics(*extra[a], *extra[b])
        row[f"{a}_vs_{b}_d_h95"] = dm["hd95"]
        row[f"{a}_vs_{b}_d_mean"] = dm["mean_distance"]
    for k, v in combo.items():
        row[f"param.{k}"] = v
    return row


def _error_row(name: str, combo: dict, exc: Exception) -> dict:
    row = {"dataset": name, "status": "error",
           "error": f"{type(exc).__name__}: {exc}"[:300]}
    for k, v in combo.items():
        row[f"param.{k}"] = v
    return row


# --------------------------------------------------------------------------
# experiment driver
# --------------------------------------------------------------------------
def run_experiment(exp_name: str, exp: dict, specs: dict, aliases: dict,
                   quick: bool, warmup: int, repeat: int,
                   save_mesh: bool = True, ds_meta: dict | None = None) -> list[dict]:
    combos = build_combos(exp)
    ds_names = expand_dataset_names(exp["datasets"], aliases)
    if quick:
        ds_names = ds_names[:1]
        combos = combos[:1]

    rows: list[dict] = []
    for ds_name in ds_names:
        try:
            ds = data.build_dataset(specs[ds_name])
        except Exception as exc:                       # noqa: BLE001
            print(f"[{exp_name}] {ds_name} DATASET FAILED: {exc}")
            rows.append(_error_row(ds_name, {}, exc))
            continue
        ds.meta["display_name"] = ds_name
        if ds_meta is not None:
            meta = dict(ds.meta)
            meta["n_lines"] = len(ds.lines)
            meta["n_points"] = int(len(ds.points))
            if "n_slices" not in meta and "n_planes" not in meta:
                # synthetic builders do not all record it; recompute it from
                # the generic plane grouping.
                try:
                    _, _, info = data.group_by_plane(
                        [ds.points[ln] for ln in ds.lines])
                    meta["n_slices"] = info["n_slices"]
                except Exception:           # noqa: BLE001 - metadata only
                    pass
            ds_meta[ds_name] = _jsonable(meta)
        for combo in combos:
            try:
                result, times = run_combo(ds, combo, warmup, repeat)
            except Exception as exc:                   # noqa: BLE001
                print(f"[{exp_name}] {ds_name} {combo} FAILED: {exc}")
                rows.append(_error_row(ds_name, combo, exc))
                continue

            row = evaluate_row(ds, ds_name, result, times, combo)
            rows.append(row)

            if save_mesh:
                obj_path = MESH_DIR / exp_name / f"{ds_name}_{_combo_slug(combo)}.obj"
                result.mesh.save_obj(obj_path)
            else:
                obj_path = None

            print(f"[{exp_name}] {ds_name} {combo} -> "
                  f"tris={row['n_triangles']} "
                  f"volume={row['volume']:.4g} time={row['time_s']:.3f}s"
                  + (f" vol_err={row['volume_rel_err']:.4f}"
                     if "volume_rel_err" in row else "")
                  + (f" obj={obj_path.name}" if obj_path else ""))
    return rows


def write_outputs(exp_name: str, rows: list[dict]) -> None:
    if not rows:
        print(f"[{exp_name}] no rows (no datasets) -- nothing written")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(OUT / f"{exp_name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="")
        w.writeheader()
        w.writerows(rows)
    (OUT / f"{exp_name}.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_run_meta(exp_names: list[str], repeat: int, warmup: int) -> None:
    pyd = sorted((REPO / "oresecstitch").glob("oresecstitch_native*.pyd"))
    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "repo": str(REPO),
        "experiments": exp_names,
        "repeats": repeat,
        "warmup": warmup,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "oresecstitch": __version__,
        "native_module": (str(native.native.__file__)
                          if native is not None and hasattr(native, "native") else ""),
        "native_pyd": [{"file": p.name, "bytes": p.stat().st_size} for p in pyd],
        "experiments_yaml_sha256": hashlib.sha256(
            CFG_PATH.read_bytes()).hexdigest(),
    }
    try:
        import scipy
        meta["scipy"] = scipy.__version__
    except ImportError:                                # pragma: no cover
        pass
    try:
        import matplotlib
        meta["matplotlib"] = matplotlib.__version__
    except ImportError:                                # pragma: no cover
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_run_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def print_matrix(experiments: dict, specs: dict, aliases: dict) -> None:
    print(f"datasets ({len(specs)} concrete):")
    for name, spec in specs.items():
        print(f"  {name:22s} kind={spec.get('kind')}"
              + (f" <- {spec['path']}" if spec.get("path") else ""))
    print("\ngroups:")
    for g, names in aliases.items():
        print(f"  {g:22s} -> {len(names)} dataset(s)")
    print("\nexperiments:")
    for name, exp in experiments.items():
        n_ds = len(expand_dataset_names(exp["datasets"], aliases))
        n_cb = len(build_combos(exp))
        print(f"  {name:22s} {n_ds} dataset(s) x {n_cb} combo(s) = {n_ds * n_cb} runs"
              f"   [{exp.get('description', '')}]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="first dataset x first combo only")
    ap.add_argument("--only", default=None, help="run a single experiment by name")
    ap.add_argument("--datasets", default=None,
                    help="comma-separated dataset group(s) to restrict to")
    ap.add_argument("--repeat", type=int, default=3, help="timed runs per combo (median reported)")
    ap.add_argument("--warmup", type=int, default=1, help="untimed runs before timing")
    ap.add_argument("--no-mesh", action="store_true", help="skip OBJ export")
    ap.add_argument("--list", action="store_true", help="print the resolved matrix and exit")
    ap.add_argument("--config", default=str(CFG_PATH), help="alternative experiments.yaml")
    args = ap.parse_args()

    if native is None:
        print("OreSecStitch native extension is unavailable. Check that "
              "oresecstitch/oresecstitch_native*.pyd and oresecstitch/dlls/ "
              "are installed, or set ORESECSTITCH_NATIVE_DIR and "
              "ORESECSTITCH_DLL_DIRS.")
        return 1

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    specs, aliases = resolve_datasets(cfg["datasets"])
    experiments = cfg["experiments"]
    if args.only:
        if args.only not in experiments:
            print(f"unknown experiment '{args.only}'; known: {sorted(experiments)}")
            return 2
        experiments = {args.only: experiments[args.only]}
    if args.datasets:
        groups = [s.strip() for s in args.datasets.split(",") if s.strip()]
        experiments = {k: v for k, v in experiments.items()
                       if set(v["datasets"]) & set(groups)}
        if not experiments:
            print(f"no experiment uses dataset group(s) {groups}")
            return 2

    if args.list:
        print_matrix(experiments, specs, aliases)
        return 0

    failures = 0
    ran = []
    ds_meta: dict = {}
    for exp_name, exp in experiments.items():
        try:
            rows = run_experiment(exp_name, exp, specs, aliases, args.quick,
                                  args.warmup, args.repeat, save_mesh=not args.no_mesh,
                                  ds_meta=ds_meta)
            write_outputs(exp_name, rows)
            ran.append(exp_name)
            if any(r.get("status") == "error" for r in rows):
                failures += 1
                print(f"[{exp_name}] finished with failed combos "
                      f"({sum(r.get('status') == 'error' for r in rows)}/{len(rows)})")
        except Exception as exc:                       # noqa: BLE001
            failures += 1
            print(f"[{exp_name}] FAILED: {exc}")

    write_run_meta(ran, args.repeat, args.warmup)
    if ds_meta:
        (OUT / "_datasets.json").write_text(
            json.dumps(ds_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
