# Programs that only src/Makefile.INCLUDE builds (upstream CMake has no
# target for them) but that upstream scripts call, e.g. count_afni in every
# afni_proc.py script. Each is one source file linked like `count` upstream.
# Included by afni-win-project.cmake and, for the Linux reference build, by
# afni-linux-reference.cmake.
set(AFNI_WIN_EXTRA_PROGRAMS "" CACHE STRING "Single-file upstream programs to add as targets")

function(_afni_win_add_extra_programs)
  foreach(target IN LISTS AFNI_WIN_EXTRA_PROGRAMS)
    add_afni_executable(${target} "${CMAKE_SOURCE_DIR}/src/${target}.c")
    target_link_libraries(${target} PRIVATE AFNI::mri NIFTI::nifti2 m)
  endforeach()
endfunction()
cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL _afni_win_add_extra_programs)

# src/ptaylor (3dClusterize, 3dNetCorr, 3dTrackID, ...) holds console programs
# but upstream adds it only together with SUMA, which needs X11 and OpenGL.
# 3dClusterize is run by @radial_correlate in every afni_proc.py script.
# Added here, at project() time, because subdirectories cannot be added from
# a deferred call; its targets link to libmri targets defined later, which
# CMake resolves at generate time.
option(AFNI_WIN_PTAYLOR "Build src/ptaylor without SUMA" OFF)
if(AFNI_WIN_PTAYLOR AND NOT COMP_SUMA)
  set(COMP_COREBINARIES ON CACHE BOOL "")
  # Same defaults that cmake/afni_cmake_build_options.cmake sets later with
  # set_if_not_defined, so these targets land next to all others.
  if(NOT DEFINED CMAKE_LIBRARY_OUTPUT_DIRECTORY)
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${PROJECT_BINARY_DIR}/targets_built")
  endif()
  if(NOT DEFINED CMAKE_RUNTIME_OUTPUT_DIRECTORY)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${PROJECT_BINARY_DIR}/targets_built")
  endif()
  find_package(GSL REQUIRED)
  add_subdirectory("${CMAKE_SOURCE_DIR}/src/ptaylor" "${CMAKE_BINARY_DIR}/src/ptaylor")
endif()
