cmake_minimum_required(VERSION 3.18)
project(oresecstitch_native LANGUAGES CXX)

# ---------------------------------------------------------------------------
# Configurable local roots (environment variables or -DVAR=...)
# ---------------------------------------------------------------------------
set(CLOUDEXTLIBS "$ENV{CLOUDEXTLIBS}" CACHE PATH "External C++ libraries root (pybind11, VTK)")
set(CDLIBS "$ENV{CDLIBS}" CACHE PATH "Directory containing cdVTKFunc")
if(NOT CLOUDEXTLIBS)
  message(FATAL_ERROR
    "CLOUDEXTLIBS is not set. Point it to the directory containing pybind11/ "
    "and VTK-9.4.2-VS2022/, or pass -DCLOUDEXTLIBS=...")
endif()
if(NOT CDLIBS)
  message(FATAL_ERROR
    "CDLIBS is not set. Point it to the directory containing cdVTKFunc/, or "
    "pass -DCDLIBS=...")
endif()
set(PYBIND11_DIR "${CLOUDEXTLIBS}/pybind11/pybind11/share/cmake/pybind11" CACHE PATH
    "Directory containing pybind11Config.cmake")
set(CDVTKFUNC_ROOT "${CDLIBS}/cdVTKFunc" CACHE PATH "cdVTKFunc project root")
set(VTK_ROOT "${CLOUDEXTLIBS}/VTK-9.4.2-VS2022" CACHE PATH "VTK root")

find_package(pybind11 CONFIG REQUIRED PATHS "${PYBIND11_DIR}")

pybind11_add_module(oresecstitch_native cpp/oresecstitch_native.cpp)

target_include_directories(oresecstitch_native PRIVATE
  "${CDVTKFUNC_ROOT}/include"
  "${CDLIBS}/cdCloud/include"
  "${VTK_ROOT}/include/vtk-9.4")

target_link_directories(oresecstitch_native PRIVATE
  "${CDVTKFUNC_ROOT}/lib/Release/x64"
  "${VTK_ROOT}/lib/release/x64")

# cdVTKFunc import library + full VTK 9.4 set (mirrors cdVTKFunc.vcxproj Release
# dependencies, minus cdCGALFunc/gmp/mpfr/gtest which the extension does not
# reference directly). VTK is statically linked, so only referenced objects are
# pulled into the module.
set(VTK_LIBS
  vtkcgns-9.4 vtkChartsCore-9.4 vtkCommonColor-9.4 vtkCommonComputationalGeometry-9.4
  vtkCommonCore-9.4 vtkCommonDataModel-9.4 vtkCommonExecutionModel-9.4 vtkCommonMath-9.4
  vtkCommonMisc-9.4 vtkCommonSystem-9.4 vtkCommonTransforms-9.4 vtkDICOMParser-9.4
  vtkDomainsChemistry-9.4 vtkDomainsChemistryOpenGL2-9.4 vtkdoubleconversion-9.4
  vtkexodusII-9.4 vtkexpat-9.4 vtkFiltersAMR-9.4 vtkFiltersCellGrid-9.4 vtkFiltersCore-9.4
  vtkFiltersExtraction-9.4 vtkFiltersFlowPaths-9.4 vtkFiltersGeneral-9.4 vtkFiltersGeneric-9.4
  vtkFiltersGeometry-9.4 vtkFiltersGeometryPreview-9.4 vtkFiltersHybrid-9.4
  vtkFiltersHyperTree-9.4 vtkFiltersImaging-9.4 vtkFiltersModeling-9.4 vtkFiltersParallel-9.4
  vtkFiltersParallelImaging-9.4 vtkFiltersPoints-9.4 vtkFiltersProgrammable-9.4
  vtkFiltersReduction-9.4 vtkFiltersSelection-9.4 vtkFiltersSMP-9.4 vtkFiltersSources-9.4
  vtkFiltersStatistics-9.4 vtkFiltersTemporal-9.4 vtkFiltersTensor-9.4 vtkFiltersTexture-9.4
  vtkFiltersTopology-9.4 vtkFiltersVerdict-9.4 vtkfmt-9.4 vtkfreetype-9.4 vtkGeovisCore-9.4
  vtkgl2ps-9.4 vtkglad-9.4 vtkhdf5-9.4 vtkhdf5_hl-9.4 vtkImagingColor-9.4 vtkImagingCore-9.4
  vtkImagingFourier-9.4 vtkImagingGeneral-9.4 vtkImagingHybrid-9.4 vtkImagingMath-9.4
  vtkImagingMorphological-9.4 vtkImagingSources-9.4 vtkImagingStatistics-9.4
  vtkImagingStencil-9.4 vtkInfovisCore-9.4 vtkInfovisLayout-9.4 vtkInteractionImage-9.4
  vtkInteractionStyle-9.4 vtkInteractionWidgets-9.4 vtkIOAMR-9.4 vtkIOAsynchronous-9.4
  vtkIOCellGrid-9.4 vtkIOCesium3DTiles-9.4 vtkIOCGNSReader-9.4 vtkIOChemistry-9.4
  vtkIOCityGML-9.4 vtkIOCONVERGECFD-9.4 vtkIOCore-9.4 vtkIOEngys-9.4 vtkIOEnSight-9.4
  vtkIOERF-9.4 vtkIOExodus-9.4 vtkIOExport-9.4 vtkIOExportGL2PS-9.4 vtkIOExportPDF-9.4
  vtkIOFDS-9.4 vtkIOFLUENTCFF-9.4 vtkIOGeometry-9.4 vtkIOHDF-9.4 vtkIOImage-9.4
  vtkIOImport-9.4 vtkIOInfovis-9.4 vtkIOIOSS-9.4 vtkIOLegacy-9.4 vtkIOLSDyna-9.4
  vtkIOMINC-9.4 vtkIOMotionFX-9.4 vtkIOMovie-9.4 vtkIONetCDF-9.4 vtkIOOggTheora-9.4
  vtkIOParallel-9.4 vtkIOParallelXML-9.4 vtkIOPLY-9.4 vtkIOSegY-9.4 vtkIOSQL-9.4
  vtkioss-9.4 vtkIOTecplotTable-9.4 vtkIOVeraOut-9.4 vtkIOVideo-9.4 vtkIOXML-9.4
  vtkIOXMLParser-9.4 vtkjpeg-9.4 vtkjsoncpp-9.4 vtkkissfft-9.4 vtklibharu-9.4
  vtklibproj-9.4 vtklibxml2-9.4 vtkloguru-9.4 vtklz4-9.4 vtklzma-9.4 vtkmetaio-9.4
  vtknetcdf-9.4 vtkogg-9.4 vtkParallelCore-9.4 vtkParallelDIY-9.4 vtkpng-9.4
  vtkpugixml-9.4 vtkRenderingAnnotation-9.4 vtkRenderingCellGrid-9.4
  vtkRenderingContext2D-9.4 vtkRenderingContextOpenGL2-9.4 vtkRenderingCore-9.4
  vtkRenderingFreeType-9.4 vtkRenderingGL2PSOpenGL2-9.4 vtkRenderingHyperTreeGrid-9.4
  vtkRenderingImage-9.4 vtkRenderingLabel-9.4 vtkRenderingLOD-9.4 vtkRenderingOpenGL2-9.4
  vtkRenderingSceneGraph-9.4 vtkRenderingUI-9.4 vtkRenderingVolume-9.4
  vtkRenderingVolumeOpenGL2-9.4 vtkRenderingVtkJS-9.4 vtksqlite-9.4 vtksys-9.4
  vtkTestingCore-9.4 vtkTestingRendering-9.4 vtktheora-9.4 vtktiff-9.4 vtktoken-9.4
  vtkverdict-9.4 vtkViewsContext2D-9.4 vtkViewsCore-9.4 vtkViewsInfovis-9.4
  vtkWrappingTools-9.4 vtkzlib-9.4)

target_link_libraries(oresecstitch_native PRIVATE cdVTKFunc ${VTK_LIBS})

target_compile_definitions(oresecstitch_native PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
target_compile_options(oresecstitch_native PRIVATE /utf-8 /bigobj)
set_target_properties(oresecstitch_native PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
