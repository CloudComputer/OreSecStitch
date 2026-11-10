"""Load the compiled C++ extension (oresecstitch_native*.pyd) and register
the runtime DLL directories required by cdVTKFunc.dll.

The package ships the extension in the package directory and the runtime DLLs
in ``oresecstitch/dlls/``.  Set ``ORESECSTITCH_NATIVE_DIR`` and
``ORESECSTITCH_DLL_DIRS`` to load them from another location.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_PKG = "oresecstitch"
_MOD = "oresecstitch_native"

# os.add_dll_directory() returns a handle that must stay alive for the
# directory to remain on the DLL search path.
_DLL_HANDLES: list = []


def _split_paths(value: str) -> list[Path]:
    return [Path(p) for p in value.split(os.pathsep) if p.strip()]


def _runtime_dirs() -> list[Path]:
    """Candidate directories that may contain cdVTKFunc.dll and its deps."""
    here = Path(__file__).resolve().parent
    dirs: list[Path] = []

    env = os.environ.get("ORESECSTITCH_DLL_DIRS", "")
    dirs.extend(_split_paths(env))

    # bundled runtime
    dirs.append(here / "dlls")
    dirs.append(here)

    # de-duplicate while preserving order
    out: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _add_runtime_dll_dirs() -> list[str]:
    added: list[str] = []
    for d in _runtime_dirs():
        if not d.is_dir():
            continue
        try:
            _DLL_HANDLES.append(os.add_dll_directory(str(d)))
            added.append(str(d))
        except OSError:
            pass
    return added


_added_dirs = _add_runtime_dll_dirs()


def _candidate_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent  # <repo>/oresecstitch/
    out: list[Path] = []
    env = os.environ.get("ORESECSTITCH_NATIVE_DIR")
    if env:
        out.append(Path(env))
    out.append(here)
    return out


def _load():
    for d in _candidate_dirs():
        if not d.is_dir():
            continue
        hits = sorted(d.glob(_MOD + "*.pyd"))
        if hits:
            spec = importlib.util.spec_from_file_location(f"{_PKG}.{_MOD}", str(hits[0]))
            try:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except (OSError, ImportError) as exc:
                raise ImportError(
                    f"Failed to load {hits[0]}: {exc}\n"
                    "Check that oresecstitch/dlls/ contains cdVTKFunc.dll, "
                    "cdCGALFunc.dll, gmp-10.dll, gmpxx-4.dll and mpfr-6.dll, "
                    "and that the Microsoft Visual C++ 2015-2022 Redistributable "
                    "(x64) is installed. The prebuilt extension requires "
                    "CPython 3.12 x64."
                ) from exc
            return mod
    raise ImportError(
        f"{_MOD}*.pyd not found (searched: {[str(d) for d in _candidate_dirs()]}).\n"
        "Install the package including the prebuilt extension, or set "
        "ORESECSTITCH_NATIVE_DIR to the directory containing it."
    )


native = _load()

# Re-export the extension's public attributes on this wrapper module so
# `native.reconstruct(...)` works the same as `native.native.reconstruct(...)`.
_PUBLIC = [n for n in dir(native) if not n.startswith("_")]
for _n in _PUBLIC:
    globals()[_n] = getattr(native, _n)

__all__ = ["native", *_PUBLIC]
