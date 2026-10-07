cmake_minimum_required(VERSION 3.20)
project(afni_compat C)

option(AFNI_COMPAT_WERROR "Treat warnings in the compat layer as errors" ON)
option(AFNI_COMPAT_TESTS "Build the compat layer unit tests" ON)

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

add_library(
  afni_compat SHARED
  src/fs.c
  src/mman.c
  src/net.c
  src/process.c
  src/rand48.c
  src/report.c
  src/shell.c
  src/signal.c
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

install(TARGETS afni_compat RUNTIME DESTINATION bin LIBRARY DESTINATION lib ARCHIVE DESTINATION lib)

if(AFNI_COMPAT_TESTS)
  enable_testing()
  add_executable(compat_test_child tests/compat_test_child.c)
  set_target_properties(compat_test_child PROPERTIES C_STANDARD 11 C_EXTENSIONS OFF)
  target_compile_options(compat_test_child PRIVATE "SHELL:-include \"${AFNI_COMPAT_HEADER}\"" ${AFNI_COMPAT_WARNINGS})
  target_link_libraries(compat_test_child PRIVATE afni_compat)

  foreach(name fs mman net process rand48 shell signal string sysinfo time users)
    add_executable(test_${name} tests/test_${name}.c)
    set_target_properties(test_${name} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)
    target_compile_options(test_${name} PRIVATE "SHELL:-include \"${AFNI_COMPAT_HEADER}\"" ${AFNI_COMPAT_WARNINGS})
    target_link_libraries(test_${name} PRIVATE afni_compat)
    add_test(NAME compat_${name} COMMAND test_${name} WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
  endforeach()
  add_dependencies(test_process compat_test_child)
endif()
