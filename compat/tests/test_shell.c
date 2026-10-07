#include <stdio.h>
#include <stdlib.h>

#include "test_common.h"

int main(void) {
  CHECK(system(NULL) == 0);
  CHECK_ERRNO(system("echo hi"), ENOSYS);
  CHECK(popen("echo hi", "r") == NULL);
  CHECK_ERRNO(popen("echo hi", "r"), ENOSYS);
  return TEST_RESULT();
}
