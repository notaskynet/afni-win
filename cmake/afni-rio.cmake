# R_io.so for the AFNI R programs (docs/DECISIONS.md D39). Included by
# afni-win-project.cmake. AFNIio.R loads a library named R_io.so from PATH
# and stops without it; upstream builds it with `R CMD SHLIB` (Makefile) or
# as `rio` with COMP_RSTATS (CMake), both against an installed R. Here it is
# built against the R of AFNI_WIN_R_HOME (CRAN R for Windows, which ships the
# headers and R.dll); the Windows DLL keeps the name R_io.so that AFNIio.R
# looks for (LoadLibrary does not depend on the extension). The Linux
# reference build includes this file too (against lib/libR.so), so that both
# platforms build R_io.so the same way.

set(AFNI_WIN_R_HOME "" CACHE PATH "R installation to build R_io.so against (R_HOME: include/ and bin/x64/R.dll or lib/libR.so)")

if(AFNI_WIN_R_HOME)
  if(WIN32)
    set(_afni_win_libr "${AFNI_WIN_R_HOME}/bin/x64/R.dll")
  else()
    set(_afni_win_libr "${AFNI_WIN_R_HOME}/lib/libR.so")
  endif()
  foreach(_file include/R.h "${_afni_win_libr}")
    if(NOT IS_ABSOLUTE "${_file}")
      set(_file "${AFNI_WIN_R_HOME}/${_file}")
    endif()
    if(NOT EXISTS "${_file}")
      message(FATAL_ERROR "AFNI_WIN_R_HOME: ${_file} not found")
    endif()
  endforeach()
  add_library(R_io SHARED "${CMAKE_SOURCE_DIR}/src/R_io.c")
  set_target_properties(R_io PROPERTIES PREFIX "" SUFFIX ".so" OUTPUT_NAME "R_io"
    RUNTIME_OUTPUT_DIRECTORY "${PROJECT_BINARY_DIR}/targets_built"
    LIBRARY_OUTPUT_DIRECTORY "${PROJECT_BINARY_DIR}/targets_built")
  target_include_directories(R_io PRIVATE "${AFNI_WIN_R_HOME}/include")
  target_link_libraries(R_io PRIVATE AFNI::mri "${_afni_win_libr}")
endif()
