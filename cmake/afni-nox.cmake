# Console programs that upstream links with X11 but that use no display:
# 3dSkullStrip (SUMA) and 1dplot with image output (docs/DECISIONS.md D35).
# Included by afni-win-project.cmake at project() time, because
# subdirectories cannot be added later from a deferred call.
#
# Upstream builds src/SUMA only with COMP_SUMA and 1dplot only with COMP_GUI,
# both of which need X11 and Motif. libSUMA mixes the computational code of
# 3dSkullStrip with the display code, and 1dplot shares its source with the
# interactive viewer. Here they are compiled against X11/Motif/OpenGL headers
# only (AFNI_WIN_X_HEADERS) and linked against afni_x_absent.dll in place of
# the X libraries and of AFNI's X library (mrix). That library holds the
# parts of mrix these programs run and that draw into memory (suma_help.c,
# coxplot/plot_ts.c, mri_coxplot.c), plus every X entry point listed in
# manifests/x-absent.txt, generated as a function that prints its name and
# exits with status 1.

option(AFNI_WIN_NOX "Build X-linked console programs (3dSkullStrip, 1dplot) without X11" OFF)
set(AFNI_WIN_X_HEADERS "" CACHE PATH "Directory with the X11/, Xm/ and GL/ headers")

function(_afni_win_write_x_absent manifest output)
  file(STRINGS "${manifest}" _lines REGEX "^[^#]")
  set(_code "/* Generated from manifests/x-absent.txt by cmake/afni-nox.cmake. */\n")
  string(APPEND _code "#include <stdio.h>\n#include <stdlib.h>\n\n")
  string(APPEND _code "static void afni_x_absent(const char *name)\n{\n")
  string(APPEND _code "  fprintf(stderr, \"** afni-win: %s needs X11/OpenGL, which this build does not have\\n\", name);\n")
  string(APPEND _code "  exit(1);\n}\n\n")
  foreach(_line IN LISTS _lines)
    separate_arguments(_fields UNIX_COMMAND "${_line}")
    list(GET _fields 0 _name)
    list(GET _fields 1 _kind)
    if(_kind STREQUAL "function")
      string(APPEND _code "void ${_name}(void) { afni_x_absent(\"${_name}\"); }\n")
    elseif(_kind STREQUAL "data")
      list(GET _fields 2 _size)
      string(APPEND _code "char ${_name}[${_size}];\n")
    else()
      message(FATAL_ERROR "manifests/x-absent.txt: unknown kind '${_kind}' for ${_name}")
    endif()
  endforeach()
  file(WRITE "${output}" "${_code}")
endfunction()

# Compile a target against the X headers. MinGW predefines WIN32, which makes
# the X11 headers include windows.h (their native Win32 X port); these
# headers describe a POSIX X11. The GL headers test _WIN32 instead;
# cmake/x-headers-shim hides it from them. The coxplot library of this build
# is X-free (patch 0009) and exports COXPLOT_WITHOUT_X11; these sources need
# the full coxplot.h, so the definition is removed again.
function(_afni_win_use_x_headers target)
  target_include_directories(${target} PRIVATE
    "${_afni_win_root}/cmake/x-headers-shim" "${AFNI_WIN_X_HEADERS}" "${CMAKE_SOURCE_DIR}/src/coxplot")
  target_compile_options(${target} PRIVATE -UWIN32 -UCOXPLOT_WITHOUT_X11)
endfunction()

if(AFNI_WIN_NOX AND NOT COMP_GUI)
  if(NOT AFNI_WIN_PTAYLOR)
    message(FATAL_ERROR "AFNI_WIN_NOX needs AFNI_WIN_PTAYLOR (libSUMA links track_tools)")
  endif()
  foreach(_header X11/Intrinsic.h Xm/Xm.h GL/glx.h GL/glu.h GL/glut.h)
    if(NOT EXISTS "${AFNI_WIN_X_HEADERS}/${_header}")
      message(FATAL_ERROR "AFNI_WIN_NOX: ${_header} not found in AFNI_WIN_X_HEADERS='${AFNI_WIN_X_HEADERS}'")
    endif()
  endforeach()

  set(_afni_win_x_absent_c "${CMAKE_BINARY_DIR}/afni_x_absent/afni_x_absent.c")
  _afni_win_write_x_absent("${_afni_win_root}/manifests/x-absent.txt" "${_afni_win_x_absent_c}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_afni_win_root}/manifests/x-absent.txt")

  add_library(afni_x_absent SHARED
    "${_afni_win_x_absent_c}"
    "${CMAKE_SOURCE_DIR}/src/suma_help.c"
    "${CMAKE_SOURCE_DIR}/src/coxplot/plot_ts.c"
    "${CMAKE_SOURCE_DIR}/src/mri_coxplot.c")
  _afni_win_use_x_headers(afni_x_absent)
  target_link_libraries(afni_x_absent PRIVATE AFNI::mri AFNI::coxplot f2c m)
  add_library(AFNI::mrix ALIAS afni_x_absent)

  # Link items of SUMA programs that are not built here (suma GUI,
  # prompt_popup, ...); they must exist as targets for the configure step.
  foreach(_target Motif::Motif X11::Xmu)
    if(NOT TARGET ${_target})
      add_library(${_target} INTERFACE IMPORTED)
    endif()
  endforeach()

  add_subdirectory("${CMAKE_SOURCE_DIR}/src/avovk" "${CMAKE_BINARY_DIR}/src/avovk")
  add_subdirectory("${CMAKE_SOURCE_DIR}/src/SUMA" "${CMAKE_BINARY_DIR}/src/SUMA")
  get_property(_afni_win_suma_targets DIRECTORY "${CMAKE_SOURCE_DIR}/src/SUMA" PROPERTY BUILDSYSTEM_TARGETS)
  foreach(_target IN LISTS _afni_win_suma_targets)
    _afni_win_use_x_headers(${_target})
  endforeach()

  # 1dplot as in src/CMakeLists_binaries.txt (COMP_GUI block).
  add_afni_executable(1dplot "${CMAKE_SOURCE_DIR}/src/1dplot.c" "${CMAKE_SOURCE_DIR}/src/display.c")
  _afni_win_use_x_headers(1dplot)
  target_link_libraries(1dplot PRIVATE AFNI::mrix AFNI::coxplot AFNI::eispack NIFTI::nifti2 AFNI::mri)
endif()

# `afni` itself: version queries only (programs/afni_console.c, D36).
if(NOT COMP_GUI)
  add_afni_executable(afni "${_afni_win_root}/programs/afni_console.c")
  target_compile_definitions(afni PRIVATE SHOWOFF)
  target_link_libraries(afni PRIVATE AFNI::mri)
endif()
