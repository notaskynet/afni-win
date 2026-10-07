#ifndef AFNI_COMPAT_TEST_COMMON_H
#define AFNI_COMPAT_TEST_COMMON_H

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int test_failures = 0;

#define CHECK(cond)                                                              \
  do {                                                                           \
    if (!(cond)) {                                                               \
      fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
      ++test_failures;                                                           \
    }                                                                            \
  } while (0)

#define CHECK_ERRNO(call, expected)                                                       \
  do {                                                                                    \
    errno = 0;                                                                            \
    (void)(call);                                                                         \
    if (errno != (expected)) {                                                            \
      fprintf(stderr, "%s:%d: %s: errno %d, expected %d\n", __FILE__, __LINE__, #call, \
              errno, (expected));                                                         \
      ++test_failures;                                                                    \
    }                                                                                     \
  } while (0)

#define TEST_RESULT() (test_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE)

#endif
