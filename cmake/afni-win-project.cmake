get_filename_component(_afni_win_root "${CMAKE_CURRENT_LIST_DIR}/.." REALPATH)

set(AFNI_COMPAT_TESTS OFF CACHE BOOL "Build the compat layer unit tests" FORCE)
add_subdirectory("${_afni_win_root}/compat" "${CMAKE_BINARY_DIR}/afni_compat")
link_libraries(AFNI_WIN::compat)
