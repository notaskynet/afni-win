cmake_minimum_required(VERSION 3.20)
project(afni_compat C)

option(AFNI_COMPAT_WERROR "Treat warnings in the compat layer as errors" ON)
option(AFNI_COMPAT_TESTS "Build the compat layer unit tests" ON)
set(AFNI_COMPAT_BUSYBOX "" CACHE FILEPATH "busybox-w32 executable for the shell tests that need a real sh")

if(NOT CMAKE_RUNTIME_OUTPUT_DIRECTORY)
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/bin")
endif()

set(AFNI_COMPAT_HEADER "${CMAKE_CURRENT_SOURCE_DIR}/include/afni_compat.h")
set(AFNI_COMPAT_WARNINGS -Wall -Wextra $<$<BOOL:${AFNI_COMPAT_WERROR}>:-Werror>)

try_compile(
  AFNI_COMPAT_ALARM_LINKS "${CMAKE_CURRENT_BINARY_DIR}/check_alarm"
  SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/tests/check_alarm_not_linkable.c"
)
if(AFNI_COMPAT_ALARM_LINKS)
  message(FATAL_ERROR "alarm() links (MinGW libmingwex stub); the toolchain must pass -Wl,--wrap=alarm")
endif()

add_library(afni_compat_winsock OBJECT src/winsock_bridge.c)
set_target_properties(
  afni_compat_winsock PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF
                                 POSITION_INDEPENDENT_CODE ON
)
target_compile_definitions(afni_compat_winsock PRIVATE AFNI_COMPAT_WINSOCK_BRIDGE)
target_compile_options(afni_compat_winsock PRIVATE ${AFNI_COMPAT_WARNINGS})

add_library(
  afni_compat SHARED
  $<TARGET_OBJECTS:afni_compat_winsock>
  src/dl.c
  src/env.c
  src/fs.c
  src/init.c
  src/mman.c
  src/net.c
  src/process.c
  src/rand48.c
  src/report.c
  src/shell.c
  src/signal.c
  src/stdio.c
  src/string.c
  src/sysconf.c
  src/time.c
  src/users.c
  src/utsname.c
)
add_library(AFNI_WIN::compat ALIAS afni_compat)
set_target_properties(
  afni_compat
  PROPERTIES C_STANDARD 11
             C_STANDARD_REQUIRED ON
             C_EXTENSIONS OFF
             PREFIX ""
             OUTPUT_NAME afni_compat
)
target_include_directories(
  afni_compat
  PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
  PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src"
)
target_compile_definitions(afni_compat PRIVATE AFNI_COMPAT_BUILDING)
target_compile_options(afni_compat PRIVATE "SHELL:-include \"${AFNI_COMPAT_HEADER}\"" ${AFNI_COMPAT_WARNINGS})
target_link_libraries(afni_compat PRIVATE advapi32)
target_link_options(afni_compat INTERFACE "LINKER:--require-defined=afni_compat_runtime")

# Every executable linked with the layer gets a manifest with the UTF-8 ANSI
# code page and long-path awareness (docs/DECISIONS.md D37). GCC links
# default-manifest.o from its startfile directories into every executable;
# -B puts this directory first, so our object replaces MinGW's (a second
# RT_MANIFEST resource would collide with it). DLLs are not affected.
set(AFNI_COMPAT_MANIFEST_DIR "${CMAKE_CURRENT_BINARY_DIR}/manifest")
add_custom_command(
  OUTPUT "${AFNI_COMPAT_MANIFEST_DIR}/default-manifest.o"
  COMMAND "${CMAKE_COMMAND}" -E make_directory "${AFNI_COMPAT_MANIFEST_DIR}"
  COMMAND "${CMAKE_RC_COMPILER}" -O coff --include-dir "${CMAKE_CURRENT_SOURCE_DIR}/src"
          -i "${CMAKE_CURRENT_SOURCE_DIR}/src/default-manifest.rc"
          -o "${AFNI_COMPAT_MANIFEST_DIR}/default-manifest.o"
  DEPENDS src/default-manifest.rc src/afni.manifest
  VERBATIM
)
add_custom_target(afni_compat_manifest DEPENDS "${AFNI_COMPAT_MANIFEST_DIR}/default-manifest.o")
add_dependencies(afni_compat afni_compat_manifest)
target_link_options(afni_compat INTERFACE "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>:-B${AFNI_COMPAT_MANIFEST_DIR}/>")

add_library(afni_compat_binmode STATIC src/binmode.c)
set_target_properties(afni_compat_binmode PROPERTIES C_STANDARD 11 C_EXTENSIONS OFF)
target_link_libraries(afni_compat INTERFACE "$<LINK_ONLY:afni_compat_binmode>")

install(TARGETS afni_compat RUNTIME DESTINATION bin LIBRARY DESTINATION lib ARCHIVE DESTINATION lib)

if(AFNI_COMPAT_TESTS)
  enable_testing()
  add_executable(compat_test_child tests/compat_test_child.c)
  set_target_properties(compat_test_child PROPERTIES C_STANDARD 11 C_EXTENSIONS OFF)
  target_compile_options(compat_test_child PRIVATE "SHELL:-include \"${AFNI_COMPAT_HEADER}\"" ${AFNI_COMPAT_WARNINGS})
  target_link_libraries(compat_test_child PRIVATE afni_compat)

  foreach(name codepage dl env fs init mman net process rand48 shell signal stdio string sysinfo time users)
    add_executable(test_${name} tests/test_${name}.c)
    set_target_properties(test_${name} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)
    target_compile_options(test_${name} PRIVATE "SHELL:-include \"${AFNI_COMPAT_HEADER}\"" ${AFNI_COMPAT_WARNINGS})
    target_link_libraries(test_${name} PRIVATE afni_compat)
    add_test(NAME compat_${name} COMMAND test_${name} WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
  endforeach()
  add_dependencies(test_process compat_test_child)

  add_library(compat_test_module MODULE tests/compat_test_module.c)
  set_target_properties(compat_test_module PROPERTIES PREFIX "" C_STANDARD 11 C_EXTENSIONS OFF
                                                      LIBRARY_OUTPUT_DIRECTORY "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
  add_dependencies(test_dl compat_test_module)

  add_executable(compat_test_sh tests/compat_test_sh.c)
  set_target_properties(compat_test_sh PROPERTIES C_STANDARD 11 C_EXTENSIONS OFF)
  target_compile_options(compat_test_sh PRIVATE ${AFNI_COMPAT_WARNINGS})
  add_dependencies(test_shell compat_test_sh)

  if(AFNI_COMPAT_BUSYBOX)
    configure_file("${AFNI_COMPAT_BUSYBOX}" "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/busybox.exe" COPYONLY)
    add_executable(test_shell_busybox tests/test_shell_busybox.c)
    set_target_properties(test_shell_busybox PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)
    target_compile_options(test_shell_busybox PRIVATE "SHELL:-include \"${AFNI_COMPAT_HEADER}\"" ${AFNI_COMPAT_WARNINGS})
    target_link_libraries(test_shell_busybox PRIVATE afni_compat)
    add_test(NAME compat_shell_busybox COMMAND test_shell_busybox WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
  endif()
endif()
