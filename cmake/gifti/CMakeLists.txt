cmake_minimum_required(VERSION 3.20)
project(afni_win_gifti C)

# Builds the gifti library from the copy inside the upstream AFNI tree
# (src/gifti) instead of an unpinned gifti_clib checkout. The in-tree
# src/gifti/CMakeLists.txt cannot be used directly: it downloads nifti_clib
# master again and redefines the NIfTI targets.

set(_gifti_src "${CMAKE_SOURCE_DIR}/src/gifti")
if(NOT EXISTS "${_gifti_src}/gifti_io.c")
  message(FATAL_ERROR "In-tree gifti sources not found in ${_gifti_src}")
endif()

find_package(EXPAT REQUIRED)
find_package(ZLIB REQUIRED)

add_library(giftiio "${_gifti_src}/gifti_io.c" "${_gifti_src}/gifti_xml.c")
add_library(GIFTI::giftiio ALIAS giftiio)
target_compile_definitions(giftiio PRIVATE HAVE_ZLIB)
target_include_directories(giftiio PUBLIC "${_gifti_src}")
target_link_libraries(giftiio PUBLIC NIFTI::nifti2 ${EXPAT_LIBRARIES} ZLIB::ZLIB)
target_include_directories(giftiio PRIVATE ${EXPAT_INCLUDE_DIRS})
