# CMAKE_PROJECT_AFNI_INCLUDE of the Linux reference build in
# build-windows.yml: the same additions to upstream as on Windows that do not
# need the compat layer, i.e. the Makefile-only programs and R_io.so.
include("${CMAKE_CURRENT_LIST_DIR}/afni-extra-programs.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/afni-rio.cmake")
