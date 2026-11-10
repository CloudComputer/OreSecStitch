// OreSecStitch native extension: pybind11 binding for vtkPlanarContour2Surface
// (exported from cdVTKFunc.dll; linked via cdVTKFunc.lib import library).
//
// Bridge conventions:
//   - input : points (N,3) float64 + lines = list of (Mi,) int64 index arrays
//   - output: (points (N',3) float64, triangles (M',3) int32)
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include "vtkPlanarContour2Surface.h"

#include <vtkPolyData.h>
#include <vtkPoints.h>
#include <vtkCellArray.h>
#include <vtkIdList.h>
#include <vtkTriangleFilter.h>

#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

using PyPoints = py::array_t<double, py::array::c_style | py::array::forcecast>;
using PyIds    = py::array_t<py::ssize_t, py::array::c_style | py::array::forcecast>;

// ---------------------------------------------------------------------------
// points (N,3) f8 + list of index polylines -> vtkPolyData with lines
static vtkSmartPointer<vtkPolyData> MakeContourPolyData(const PyPoints& points,
                                                        const std::vector<PyIds>& lines)
{
    if (points.ndim() != 2 || points.shape(1) != 3)
        throw std::invalid_argument("points must have shape (N, 3)");
    const py::ssize_t npts = points.shape(0);
    if (npts < 3)
        throw std::invalid_argument("points must contain at least 3 vertices");
    if (lines.empty())
        throw std::invalid_argument("lines must contain at least one polyline");

    auto pd      = vtkSmartPointer<vtkPolyData>::New();
    auto vtkPts  = vtkSmartPointer<vtkPoints>::New();
    vtkPts->SetDataTypeToDouble();
    vtkPts->SetNumberOfPoints(static_cast<vtkIdType>(npts));
    const double* src = points.data();
    for (py::ssize_t i = 0; i < npts; ++i) {
        const double* p = src + i * 3;
        vtkPts->SetPoint(static_cast<vtkIdType>(i), p[0], p[1], p[2]);
    }
    pd->SetPoints(vtkPts);

    auto cells = vtkSmartPointer<vtkCellArray>::New();
    for (const auto& line : lines) {
        if (line.ndim() != 1)
            throw std::invalid_argument("each polyline must be a 1-D index array");
        const py::ssize_t n = line.shape(0);
        if (n < 2) continue;
        cells->InsertNextCell(static_cast<vtkIdType>(n));
        const py::ssize_t* ids = line.data();
        for (py::ssize_t i = 0; i < n; ++i) {
            const py::ssize_t id = ids[i];
            if (id < 0 || id >= npts)
                throw std::invalid_argument("polyline point index out of range");
            cells->InsertCellPoint(static_cast<vtkIdType>(id));
        }
    }
    if (cells->GetNumberOfCells() == 0)
        throw std::invalid_argument("no polyline with >= 2 points");
    pd->SetLines(cells);
    return pd;
}

// ---------------------------------------------------------------------------
// vtkPolyData -> (points (N,3) f8, triangles (M,3) i4)
// All cells are normalized to triangles via vtkTriangleFilter, which handles
// triangle strips (with alternating winding) and concave polygons correctly.
static py::tuple PolyDataToArrays(vtkPolyData* pd)
{
    if (!pd)
        throw std::runtime_error("algorithm produced no output polydata");

    auto tf = vtkSmartPointer<vtkTriangleFilter>::New();
    tf->SetInputData(pd);
    tf->PassVertsOff();
    tf->PassLinesOff();
    tf->Update();
    vtkPolyData* tri = tf->GetOutput();

    vtkPoints* vp = tri->GetPoints();
    const vtkIdType np = vp ? vp->GetNumberOfPoints() : 0;
    py::array_t<double> outPts({static_cast<py::ssize_t>(np), static_cast<py::ssize_t>(3)});
    for (vtkIdType i = 0; i < np; ++i) {
        double x[3];
        vp->GetPoint(i, x);
        double* dst = outPts.mutable_data() + static_cast<std::ptrdiff_t>(i) * 3;
        dst[0] = x[0]; dst[1] = x[1]; dst[2] = x[2];
    }

    vtkCellArray* ca = tri->GetPolys();
    const vtkIdType nc = ca ? ca->GetNumberOfCells() : 0;
    std::vector<int> tris;
    tris.reserve(static_cast<std::size_t>(nc) * 3);
    auto ids = vtkSmartPointer<vtkIdList>::New();
    for (vtkIdType c = 0; c < nc; ++c) {
        tri->GetCellPoints(c, ids);
        if (ids->GetNumberOfIds() < 3) continue;
        tris.push_back(static_cast<int>(ids->GetId(0)));
        tris.push_back(static_cast<int>(ids->GetId(1)));
        tris.push_back(static_cast<int>(ids->GetId(2)));
    }
    py::array_t<int> outTris({static_cast<py::ssize_t>(tris.size() / 3),
                              static_cast<py::ssize_t>(3)});
    if (!tris.empty())
        std::copy(tris.begin(), tris.end(), outTris.mutable_data());
    return py::make_tuple(outPts, outTris);
}

// ---------------------------------------------------------------------------
// Thin wrapper holding the VTK object alive between calls
class PyStitcher
{
public:
    PyStitcher() : algo_(vtkSmartPointer<vtkPlanarContour2Surface>::New()) {}

    void set_input(const PyPoints& points, const std::vector<PyIds>& lines)
    {
        input_ = MakeContourPolyData(points, lines);
        algo_->SetInputData(input_);
    }
    void update() { algo_->Update(); }
    py::tuple get_output() const { return PolyDataToArrays(algo_->GetOutput()); }

    void set_default_slice_thickness(double v) { algo_->SetDefaultSliceThickness(v); }
    double get_default_slice_thickness() const { return algo_->GetDefaultSliceThickness(); }
    void set_end_capping_mode(int m) { algo_->SetEndCappingMode(m); }
    int get_end_capping_mode() const { return algo_->GetEndCappingMode(); }
    void set_triangulation_cost_method(int m) { algo_->SetTriangulationCostMethod(m); }
    int get_triangulation_cost_method() const { return algo_->GetTriangulationCostMethod(); }
    void set_branch_method(int m) { algo_->SetBranchMethod(m); }
    int get_branch_method() const { return algo_->GetBranchMethod(); }
    void set_greedy(bool v) { algo_->SetGreedyMethod(v); }
    bool get_greedy() const { return algo_->GetGreedyMethod(); }
    void set_logging(bool v) { algo_->SetLoggingEnabled(v); }
    void set_branch_densify(bool v) { algo_->SetBranchDensifyEnabled(v); }
    void set_contour_densify(bool v) { algo_->SetContourDensifyEnabled(v); }
    void set_filter_small_branches(bool v) { algo_->SetFilterSmallBranchesEnabled(v); }
    void set_use_cgal(bool v) { algo_->SetUseCGALTriangulation(v); }
    void set_debug_obj(bool v) { algo_->SetDebugOBJEnabled(v); }

private:
    vtkSmartPointer<vtkPlanarContour2Surface> algo_;
    vtkSmartPointer<vtkPolyData> input_;
};

// ---------------------------------------------------------------------------
// One-shot: build input, apply kwargs (only those present -> native defaults
// preserved for the rest), update, return (points, triangles).
static py::tuple reconstruct(const PyPoints& points, const std::vector<PyIds>& lines,
                             py::kwargs kw)
{
    PyStitcher s;
    s.set_input(points, lines);

    auto has = [&](const char* k) { return kw.contains(k) && !kw[k].is_none(); };
    if (has("default_slice_thickness")) s.set_default_slice_thickness(kw["default_slice_thickness"].cast<double>());
    if (has("end_capping_mode"))        s.set_end_capping_mode(kw["end_capping_mode"].cast<int>());
    if (has("triangulation_cost"))      s.set_triangulation_cost_method(kw["triangulation_cost"].cast<int>());
    if (has("branch_method"))           s.set_branch_method(kw["branch_method"].cast<int>());
    if (has("greedy"))                  s.set_greedy(kw["greedy"].cast<bool>());
    if (has("branch_densify"))          s.set_branch_densify(kw["branch_densify"].cast<bool>());
    if (has("contour_densify"))         s.set_contour_densify(kw["contour_densify"].cast<bool>());
    if (has("filter_small_branches"))   s.set_filter_small_branches(kw["filter_small_branches"].cast<bool>());
    if (has("use_cgal"))                s.set_use_cgal(kw["use_cgal"].cast<bool>());
    if (has("logging"))                 s.set_logging(kw["logging"].cast<bool>());
    if (has("debug_obj"))               s.set_debug_obj(kw["debug_obj"].cast<bool>());

    s.update();
    return s.get_output();
}

PYBIND11_MODULE(oresecstitch_native, m)
{
    m.doc() = "OreSecStitch: planar contour stacks -> closed triangulated surface "
              "(pybind11 binding of vtkPlanarContour2Surface / cdVTKFunc)";

    py::class_<PyStitcher>(m, "PlanarContour2Surface")
        .def(py::init<>())
        .def("set_input", &PyStitcher::set_input, py::arg("points"), py::arg("lines"),
             "points: (N,3) float64; lines: list of (Mi,) int index arrays")
        .def("update", &PyStitcher::update)
        .def("get_output", &PyStitcher::get_output,
             "returns (points (N,3) float64, triangles (M,3) int32)")
        .def_property("default_slice_thickness",
                      &PyStitcher::get_default_slice_thickness,
                      &PyStitcher::set_default_slice_thickness)
        .def_property("end_capping_mode",
                      &PyStitcher::get_end_capping_mode, &PyStitcher::set_end_capping_mode)
        .def_property("triangulation_cost_method",
                      &PyStitcher::get_triangulation_cost_method,
                      &PyStitcher::set_triangulation_cost_method)
        .def_property("branch_method",
                      &PyStitcher::get_branch_method, &PyStitcher::set_branch_method)
        .def_property("greedy", &PyStitcher::get_greedy, &PyStitcher::set_greedy)
        .def("set_logging", &PyStitcher::set_logging, py::arg("on"))
        .def("set_branch_densify", &PyStitcher::set_branch_densify, py::arg("on"))
        .def("set_contour_densify", &PyStitcher::set_contour_densify, py::arg("on"))
        .def("set_filter_small_branches", &PyStitcher::set_filter_small_branches, py::arg("on"))
        .def("set_use_cgal", &PyStitcher::set_use_cgal, py::arg("on"),
             "Use CGAL triangulation instead of the VTK one (gtest default: on)")
        .def("set_debug_obj", &PyStitcher::set_debug_obj, py::arg("on"));

    m.def("reconstruct", &reconstruct,
          "reconstruct(points, lines, **params) -> (points, triangles).\n"
          "Keyword params: default_slice_thickness, end_capping_mode, "
          "triangulation_cost, branch_method, greedy, branch_densify, "
          "contour_densify, filter_small_branches, use_cgal, logging, debug_obj.\n"
          "Params left as None keep the native defaults.");

    // enum constants (mirror vtkPlanarContour2Surface enums)
    m.attr("END_CAPPING_NONE")   = 0;
    m.attr("END_CAPPING_SMOOTH") = 1;
    m.attr("END_CAPPING_STRAIGHT") = 2;
    m.attr("COST_MIN_PERIMETER")   = 0;
    m.attr("COST_MIN_SURFACE_AREA") = 1;
    m.attr("BRANCH_POINT_DISTANCE") = 0;
    m.attr("BRANCH_TRIANGULATION_REGION") = 1;
}
