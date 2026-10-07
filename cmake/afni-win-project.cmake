get_filename_component(_afni_win_root "${CMAKE_CURRENT_LIST_DIR}/.." REALPATH)

set(AFNI_COMPAT_TESTS OFF CACHE BOOL "Build the compat layer unit tests" FORCE)
add_subdirectory("${_afni_win_root}/compat" "${CMAKE_BINARY_DIR}/afni_compat")
link_libraries("$<BUILD_INTERFACE:AFNI_WIN::compat>")

function(_afni_win_place_compat)
  if(CMAKE_RUNTIME_OUTPUT_DIRECTORY)
    set_target_properties(afni_compat PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
  endif()
endfunction()
cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL _afni_win_place_compat)
