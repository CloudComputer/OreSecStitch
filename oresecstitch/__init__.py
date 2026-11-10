"""OreSecStitch: planar contour stacks -> closed surfaces via optimal DP
triangulation (pybind11 binding of vtkPlanarContour2Surface / cdVTKFunc)."""
from .api import (
    BRANCH_METHOD,
    END_CAPPING,
    TRIANGULATION_COST,
    StitchParams,
    StitchResult,
    SurfaceMesh,
    reconstruct,
)
from . import metrics

try:  # the native extension is optional for pure-Python metric work
    from . import native
except ImportError as _exc:  # pragma: no cover - depends on the local build
    native = None
    _native_import_error = _exc

__version__ = "1.0.0"

__all__ = [
    "BRANCH_METHOD",
    "END_CAPPING",
    "TRIANGULATION_COST",
    "StitchParams",
    "StitchResult",
    "SurfaceMesh",
    "reconstruct",
    "metrics",
    "native",
    "__version__",
]
