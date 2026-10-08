# Programs that only src/Makefile.INCLUDE builds (upstream CMake has no
# target for them) but that upstream scripts call, e.g. count_afni in every
# afni_proc.py script. Each is one source file linked like `count` upstream.
# Included by afni-win-project.cmake; the Linux reference build uses it alone
# as CMAKE_PROJECT_AFNI_INCLUDE.
set(AFNI_WIN_EXTRA_PROGRAMS "" CACHE STRING "Single-file upstream programs to add as targets")

function(_afni_win_add_extra_programs)
  foreach(target IN LISTS AFNI_WIN_EXTRA_PROGRAMS)
    add_afni_executable(${target} "${CMAKE_SOURCE_DIR}/src/${target}.c")
    target_link_libraries(${target} PRIVATE AFNI::mri NIFTI::nifti2 m)
  endforeach()
endfunction()
cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL _afni_win_add_extra_programs)
